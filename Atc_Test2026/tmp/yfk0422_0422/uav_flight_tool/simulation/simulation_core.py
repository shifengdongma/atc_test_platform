"""
simulation/simulation_core.py
UTM 仿真核心
"""

import time
import math
import random
import uuid
import ctypes
from collections import deque
from typing import List, Dict, Any

from simulation.structs import (
    GeoPoint, Vec3, Waypoint, FlightPlan, TelemetryData, TelemetrySnapshot,
    UAVClassification, NFZ_TYPE_MAP, NFZ_STATUS_MAP
)


# 全局常量
ORIGIN_LAT = 31.309724
ORIGIN_LON = 120.695422
RE_EARTH = 6371000.0
SIM_RADIUS_M = 50000.0
CLIMB_RATE = 15.0
CRUISE_SPEED = 15.0


def meters_to_geo(lat: float, lon: float, dn: float, de: float) -> tuple[float, float]:
    """将局部东北坐标（米）转换为经纬度增量"""
    d_lat = dn / RE_EARTH
    d_lon = de / (RE_EARTH * math.cos(math.radians(lat)))
    return lat + math.degrees(d_lat), lon + math.degrees(d_lon)


class DroneAgent:
    """单架无人机仿真代理"""

    def __init__(self, plan: FlightPlan):
        self.plan = plan
        self.uid = plan.aircraft.uid.decode('utf-8')

        # 状态机: 0=IDLE, 1=TAKEOFF, 2=CRUISE, 3=HOVER, 4=LANDING, 5=FINISHED
        self.state = 0
        self.current_wp_idx = 0

        self.history_buffer = deque(maxlen=10)

        if plan.type == 0:
            start_p = plan.data.traj.wps[0].point
        else:
            start_p = plan.data.area.vertices[0]

        self.lat = start_p.lat
        self.lon = start_p.lon
        self.alt = 0.0

        self.vn = self.ve = self.vd = 0.0
        self.heading = 0.0

        self.cruise_speed = CRUISE_SPEED + random.uniform(-2, 5)
        self.climb_rate = CLIMB_RATE
        self.hover_timer = 0.0

        if plan.type == 0 and plan.data.traj.count > 1:
            self.target_alt = plan.data.traj.wps[1].point.alt
        else:
            self.target_alt = (plan.data.area.min_alt + plan.data.area.max_alt) / 2

        self.pos_noise_std = 1.0

    def update(self, current_time: float, dt: float):
        """无人机状态更新主入口"""
        if current_time < self.plan.start_time:
            self.state = 0
            return

        if self.state == 0:
            self.state = 1

        if self.plan.type == 0:
            self._update_trajectory_mode(dt)
        else:
            self._update_loiter_mode(dt)

        self.lat, self.lon = meters_to_geo(self.lat, self.lon, self.vn * dt, self.ve * dt)
        self.alt += self.vd * dt
        self.alt = max(0.0, self.alt)

        self.meas_lat, self.meas_lon = self.lat, self.lon
        self.meas_alt = self.alt

        if self.state in (1, 2, 3, 4):
            snapshot = TelemetrySnapshot()
            snapshot.location = GeoPoint(self.lon, self.lat, self.alt)
            snapshot.timestamp = current_time
            snapshot.h_accuracy = int(self.pos_noise_std)
            snapshot.v_accuracy = int(self.pos_noise_std)
            snapshot.speed_accuracy = int(1.0)
            snapshot.speed = math.sqrt(self.vn**2 + self.ve**2)
            snapshot.heading = self.heading
            if snapshot.heading < 0.0:
                snapshot.heading += 360.0
            snapshot.verticalSpeed = self.vd
            self.history_buffer.append(snapshot)

    def _update_trajectory_mode(self, dt: float):
        """航路点模式更新逻辑"""
        wps = self.plan.data.traj.wps
        count = self.plan.data.traj.count

        if self.current_wp_idx >= count - 1:
            self.state = 4

        if self.state == 1:
            target = wps[self.current_wp_idx + 1].point
            dn = (target.lat - self.lat) * RE_EARTH * math.pi / 180.0
            de = (target.lon - self.lon) * RE_EARTH * math.cos(math.radians(self.lat)) * math.pi / 180.0
            da = target.alt - self.alt
            h_dist = math.sqrt(dn**2 + de**2)
            dist = math.sqrt(dn**2 + de**2 + da**2)

            if h_dist > 10.0:
                self.vn = (dn / dist) * self.cruise_speed
                self.ve = (de / dist) * self.cruise_speed
                self.heading = math.degrees(math.atan2(self.ve, self.vn))
                self.vd = (da / dist) * self.cruise_speed
            else:
                self.vn = self.ve = 0.0

            self.vd = self.climb_rate

            if self.alt >= self.target_alt - 5.0 or dist < self.cruise_speed * dt:
                self.current_wp_idx += 1
                self.state = 2

        elif self.state == 2:
            target = wps[self.current_wp_idx + 1].point
            dn = (target.lat - self.lat) * RE_EARTH * math.pi / 180.0
            de = (target.lon - self.lon) * RE_EARTH * math.cos(math.radians(self.lat)) * math.pi / 180.0
            da = target.alt - self.alt
            dist = math.sqrt(dn**2 + de**2 + da**2)

            if dist < self.cruise_speed * dt:
                if wps[self.current_wp_idx + 1].stay_duration > 0:
                    self.state = 3
                    self.hover_timer = wps[self.current_wp_idx + 1].stay_duration
                else:
                    self.current_wp_idx += 1
                self.vn = dn / dt
                self.ve = de / dt
                self.vd = da / dt
                self.heading = math.degrees(math.atan2(self.ve, self.vn))
            else:
                self.vn = (dn / dist) * self.cruise_speed
                self.ve = (de / dist) * self.cruise_speed
                self.vd = (da / dist) * self.cruise_speed
                self.heading = math.degrees(math.atan2(self.ve, self.vn))

        elif self.state == 3:
            self.vn = self.ve = self.vd = 0.0
            self.hover_timer -= dt
            if self.hover_timer <= dt:
                self.current_wp_idx += 1
                self.state = 2

        elif self.state == 4:
            self.vn = self.ve = 0.0
            self.vd = -CLIMB_RATE / 2
            if self.alt <= 0.1:
                self.state = 5

    def _update_loiter_mode(self, dt: float):
        """区域盘旋模式更新逻辑"""
        center = GeoPoint(0.0, 0.0, 0.0)
        center.lat = (self.plan.data.area.vertices[0].lat +
                      self.plan.data.area.vertices[int(self.plan.data.area.vertex_count / 2)].lat) / 2
        center.lon = (self.plan.data.area.vertices[0].lon +
                      self.plan.data.area.vertices[int(self.plan.data.area.vertex_count / 2)].lon) / 2

        if self.state == 1:
            self.vd = self.climb_rate
            if self.alt >= self.target_alt:
                self.state = 2
                self.vd = 0.0
        else:
            radius = 200.0
            angular_speed = self.cruise_speed / radius
            self.heading += angular_speed * dt * 5.0
            rad = math.radians(self.heading)

            t_lat, t_lon = meters_to_geo(
                center.lat, center.lon,
                radius * math.cos(rad),
                radius * math.sin(rad)
            )

            dn = (t_lat - self.lat) * RE_EARTH * math.pi / 180.0
            de = (t_lon - self.lon) * RE_EARTH * math.cos(math.radians(self.lat)) * math.pi / 180.0
            self.vn = dn
            self.ve = de
            self.vd = 0.0

            if time.time() >= self.plan.end_time:
                self.state = 4

        if self.state == 4:
            self.vn = self.ve = 0.0
            self.vd = -CLIMB_RATE / 2
            if self.alt <= 0.1:
                self.state = 5

    def get_telemetry_payload(self, timestamp: float) -> Dict[str, Any]:
        """生成遥测数据包"""
        t = TelemetryData()
        t.uid = self.uid.encode('utf-8')
        t.location = GeoPoint(self.meas_lon, self.meas_lat, self.meas_alt)
        t.classification = self.plan.aircraft.classification
        t.velocity = Vec3(0, 0, 0)
        t.speed = math.sqrt(self.vn**2 + self.ve**2)
        t.heading = self.heading
        if t.heading < 0.0:
            t.heading += 360.0
        t.verticalSpeed = self.vd
        t.longitudinal_threshold = self.plan.aircraft.longitudinal_threshold
        t.lateral_threshold = self.plan.aircraft.lateral_threshold
        t.v_threshold = self.plan.aircraft.v_threshold
        t.timestamp = int(timestamp)
        t.horizontalAccuracy = int(self.pos_noise_std)
        if self.state == 5:
            t.operatingStatus = 1
        else:
            t.operatingStatus = 2

        t.horizontalAccuracy = int(self.pos_noise_std)
        t.verticalAccuracy = int(self.pos_noise_std)
        t.speedAccuracy = int(1.0)

        return {
            "current": t,
            "history": list(self.history_buffer)
        }


class Simulator:
    """仿真管理器"""

    def __init__(self):
        self.agents: Dict[str, DroneAgent] = {}
        self.plan_counter = 0
        self.nfz_counter = 0
        self._keep_alive = []

    def generate_plan(self, type_hint: str = "plan") -> FlightPlan:
        """随机生成一个飞行计划"""
        self.plan_counter += 1
        uid_str = f"UAV_{uuid.uuid4().hex}"

        plan = FlightPlan()
        plan.plan_id = self.plan_counter
        plan.priority = random.randint(1, 10)

        now = time.time()
        plan.start_time = int(now)
        plan.end_time = plan.start_time + 5400

        plan.aircraft.uid = uid_str.encode('utf-8')
        plan.aircraft.longitudinal_threshold = 200.0
        plan.aircraft.lateral_threshold = 100.0
        plan.aircraft.v_threshold = 100.0
        plan.aircraft.max_speed = CRUISE_SPEED
        random_uav = random.choice(list(UAVClassification))
        plan.aircraft.classification = random_uav.value
        cruise_alt = random.uniform(50.0, 200.0)

        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0, SIM_RADIUS_M)
        base_lat, base_lon = meters_to_geo(
            ORIGIN_LAT, ORIGIN_LON,
            dist * math.cos(angle), dist * math.sin(angle)
        )

        plan_num = random.random()

        if plan_num < 0:
            plan.type = 1
            num_vertices = random.randint(3, 10)
            base_radius = random.uniform(150.0, 5000.0)
            angles = []
            for i in range(num_vertices):
                base_angle = i * 2 * math.pi / num_vertices
                jitter = random.uniform(-math.pi / (num_vertices * 2), math.pi / (num_vertices * 2))
                angles.append(base_angle + jitter)
            angles.sort()

            points = []
            for angle_v in angles:
                radius = base_radius * random.uniform(0.8, 1.2)
                dn = radius * math.cos(angle_v)
                de = radius * math.sin(angle_v)
                plat, plon = meters_to_geo(base_lat, base_lon, dn, de)
                points.append(GeoPoint(plon, plat, 0.0))

            arr = (GeoPoint * num_vertices)(*points)
            self._keep_alive.append(arr)

            plan.data.area.vertices = arr
            plan.data.area.vertex_count = num_vertices
            plan.data.area.min_alt = 0
            plan.data.area.max_alt = cruise_alt + 25.0

        elif plan_num < 0.5:
            plan.type = 0
            wps = []
            curr_lat, curr_lon = base_lat, base_lon
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), plan.start_time, 0, 100, 1, 100 / 2))
            curr_time = plan.start_time + (cruise_alt / CLIMB_RATE)
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, cruise_alt), 0, 0, 100, 1, 1))

            num_points = random.randint(10, 30)
            current_heading = random.uniform(0, 2 * math.pi)
            for _ in range(num_points):
                d_dist = random.uniform(90, 3000)
                delta_angle = random.uniform(-math.pi / 2, math.pi / 2)
                current_heading += delta_angle
                d_ang = current_heading
                curr_lat, curr_lon = meters_to_geo(
                    curr_lat, curr_lon,
                    d_dist * math.cos(d_ang), d_dist * math.sin(d_ang)
                )
                wp_alt = cruise_alt + random.uniform(-50, 200)
                travel_time = d_dist / CRUISE_SPEED
                curr_time += travel_time
                wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, wp_alt), 0, 0, 100, 1, 100 / 2))

            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), curr_time + 100, 0, 100, 1, 100 / 2))

            arr = (Waypoint * len(wps))(*wps)
            self._keep_alive.append(arr)
            plan.data.traj.wps = arr
            plan.data.traj.count = len(wps)
            plan.end_time = curr_time + 100

        else:
            plan.type = 0
            wps = []
            curr_lat, curr_lon = base_lat, base_lon
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), plan.start_time, 0, 100, 1, 100 / 2))
            curr_time = plan.start_time + (cruise_alt / CLIMB_RATE)
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, cruise_alt), 0, 0, 100, 1, 5))

            poly_sides = random.randint(4, 30)
            side_len = random.uniform(200.0, 1000.0)
            current_heading = random.uniform(0, 2 * math.pi)
            turn_dir = 1 if random.random() > 0.5 else -1
            turn_angle = (2 * math.pi / poly_sides) * turn_dir
            steps = poly_sides

            for _ in range(steps):
                dn = side_len * math.cos(current_heading)
                de = side_len * math.sin(current_heading)
                curr_lat, curr_lon = meters_to_geo(curr_lat, curr_lon, dn, de)
                travel_time = side_len / CRUISE_SPEED
                curr_time += travel_time
                wp_alt = cruise_alt + random.uniform(-30, 30)
                wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, wp_alt), 0, 0, 100, 1, 100 / 2))
                current_heading += turn_angle

            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), curr_time + 100, 0, 100, 1, 100 / 2))

            arr = (Waypoint * len(wps))(*wps)
            self._keep_alive.append(arr)
            plan.data.traj.wps = arr
            plan.data.traj.count = len(wps)
            plan.end_time = curr_time + 100

        self.agents[uid_str] = DroneAgent(plan)
        return plan

    def step(self, step_size_sec: float = 1.0, sim_time: float = None) -> List[Dict[str, Any]]:
        """仿真推进一步"""
        current_time = int(sim_time) if sim_time is not None else int(time.time())
        payloads = []

        finished_ids = [uid for uid, agent in self.agents.items() if agent.state == 5]
        for uid in finished_ids:
            del self.agents[uid]

        for agent in self.agents.values():
            agent.update(current_time, step_size_sec)
            if agent.state != 0:
                payloads.append(agent.get_telemetry_payload(current_time))

        return payloads
