#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞行器状态告警数据点位生成
参考 create_data.py / create_data_scene.py 生成逻辑

场景：
1. 状态3：地面(1)→升空(2)→飞行N分钟→紧急状态(3)发射M条→恢复正常(2)
2. 状态5：地面(1)→升空(2)→飞行N分钟→航空器丢失(5)→停止
3. 状态3转5：地面(1)→升空(2)→飞行N分钟→紧急状态(3)发射M条→丢失(5)→停止

UAV ID 从 uav_identifiers_extended.py 倒序获取
"""
import os
import sys
import json
import math
import argparse
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ROOT)

from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED

# ID 偏移记录文件：自动递增，每次运行使用不同的 UAV ID
_ID_OFFSET_RECORD = os.path.join(_SCRIPT_DIR, ".last_id_offset")


def _get_next_id_offset(total_needed, pool_size):
    """读取记录文件获取下次偏移，运行后自动递增 total_needed"""
    offset = 0
    if os.path.exists(_ID_OFFSET_RECORD):
        try:
            with open(_ID_OFFSET_RECORD, "r", encoding="utf-8") as f:
                offset = int(f.read().strip())
        except (ValueError, IOError):
            offset = 0
    offset = offset % pool_size
    next_offset = (offset + total_needed) % pool_size
    try:
        with open(_ID_OFFSET_RECORD, "w", encoding="utf-8") as f:
            f.write(str(next_offset))
    except IOError:
        pass
    return offset

RE_EARTH = 6371000.0

# ========== 默认配置（IDE 直接修改此处即可运行）==========
DEFAULT_COUNT = 1                    # UAV 数量（多架时自动经纬度偏移，避免位置重叠）
DEFAULT_CENTER_LNG = 120.7418        # 默认中心经度（苏州金鸡湖附近，可覆盖测试空域）
DEFAULT_CENTER_LAT = 31.3689         # 默认中心纬度
DEFAULT_ALTITUDE = 50.0              # 巡航高度（米），爬升阶段目标高度
DEFAULT_SPEED = 15.0                 # 巡航速度（米/秒），决定每步经纬度增量
DEFAULT_HEADING = 90.0               # 航向角（度）：0=正北, 90=正东, 180=正南, 270=正西
DEFAULT_INTERVAL_MS = 1000           # 采样间隔（毫秒），即每秒生成一个轨迹点
DEFAULT_GROUND_SECONDS = 0          # 地面状态(operatingStatus=1)持续时间（秒）
DEFAULT_CLIMB_SECONDS = 0           # 爬升阶段(operatingStatus=2)持续时间（秒），高度从0升至巡航高度
DEFAULT_FLIGHT_MINUTES = 1           # 正常飞行(operatingStatus=2)持续时间（分钟），之后触发告警状态
DEFAULT_EMERGENCY_COUNT = 5          # 紧急状态(operatingStatus=3)发射的数据条数，范围 1~10
DEFAULT_SPACING = 2000               # 多架UAV时的横向间距（米），避免位置重叠
DEFAULT_CLASSIFICATION = 2           # 航空器分类（模拟器类型）：0=微型 1=轻型 2=小型 3=中型 4=大型
DEFAULT_SIM_RADIUS = 100000.0        # 仿真有效半径（米），与 simulation_core.py SIM_RADIUS_M 默认值一致

# 场景开关
SCENE_3_ENABLED = True
SCENE_5_ENABLED = False
SCENE_3_5_ENABLED = False
# ==========================================================


def make_telemetry_point(uid, reg_sign, ts, lon, lat, alt, speed, heading, status, classification=DEFAULT_CLASSIFICATION):
    return {
        "uniqueProductIdentificationCode": uid,
        "realNameRegistrationSign": reg_sign,
        "uasOperationCategory": 1,
        "classification": classification,
        "rpsLocationType": 1,
        "rpsLongitude": 0,
        "rpsLatitude": 0,
        "rpsAltitude": 0,
        "longitude": round(lon, 14),
        "latitude": round(lat, 14),
        "trackAngle": round(heading, 2),
        "speed": round(speed, 2),
        "geodeticAltitude": round(alt, 1),
        "verticalSpeed": 0.0,
        "relativeAltitude": 0.0,
        "pressureAltitude": 0.0,
        "operatingStatus": status,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1,
        "verticalAccuracy": 0,
        "speedAccuracy": 0,
        "timestamp": ts,
        "timestampAccuracy": 0,
    }


def calc_step_offsets(speed_ms, heading_deg, center_lat):
    heading_rad = math.radians(heading_deg)
    dn = speed_ms * math.cos(heading_rad)
    de = speed_ms * math.sin(heading_rad)
    meters_per_deg_lat = 111320.0
    meters_per_deg_lng = 111320.0 * math.cos(math.radians(center_lat))
    return dn / meters_per_deg_lat, de / meters_per_deg_lng


def generate_scene_data(
    uid, reg_sign, start_lng, start_lat, altitude, speed, heading,
    interval_ms, ground_s, climb_s, flight_min, emergency_cnt, scene_type,
    classification=DEFAULT_CLASSIFICATION
):
    trajectory = []
    base_time = int(datetime.now().timestamp() * 1000)
    d_lat, d_lon = calc_step_offsets(speed, heading, start_lat)

    # 阶段1: 地面 status=1
    for i in range(ground_s):
        ts = base_time + i * interval_ms
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, start_lng, start_lat, 0.0, 0.0, 0.0, 1, classification))

    # 阶段2: 爬升 status=2
    for i in range(climb_s):
        ts = base_time + (ground_s + i) * interval_ms
        p = (i + 1) / climb_s
        alt = altitude * p
        lon = start_lng + d_lon * i * 0.3
        lat = start_lat + d_lat * i * 0.3
        spd = speed * p
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, alt, spd, heading, 2, classification))

    # 阶段3: 巡航 status=2
    flight_s = int(flight_min * 60)
    base_idx = ground_s + climb_s
    for i in range(flight_s):
        ts = base_time + (base_idx + i) * interval_ms
        lon = start_lng + d_lon * (climb_s * 0.3 + i)
        lat = start_lat + d_lat * (climb_s * 0.3 + i)
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 2, classification))

    # 阶段4: 告警
    base_idx = ground_s + climb_s + flight_s
    if scene_type == 3:
        for i in range(emergency_cnt):
            ts = base_time + (base_idx + i) * interval_ms
            lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + i)
            lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + i)
            trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 3, classification))
        base_idx += emergency_cnt
        for i in range(60):
            ts = base_time + (base_idx + i) * interval_ms
            lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + emergency_cnt + i)
            lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + emergency_cnt + i)
            trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 2, classification))
    elif scene_type == 5:
        ts = base_time + base_idx * interval_ms
        lon = start_lng + d_lon * (climb_s * 0.3 + flight_s)
        lat = start_lat + d_lat * (climb_s * 0.3 + flight_s)
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 5, classification))
    elif scene_type == '3_5':
        for i in range(emergency_cnt):
            ts = base_time + (base_idx + i) * interval_ms
            lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + i)
            lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + i)
            trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 3, classification))
        base_idx += emergency_cnt
        ts = base_time + base_idx * interval_ms
        lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + emergency_cnt)
        lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + emergency_cnt)
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 5, classification))

    return trajectory


def main():
    parser = argparse.ArgumentParser(description="飞行器状态告警数据点位生成")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="UAV数量")
    parser.add_argument("--center-lng", type=float, default=DEFAULT_CENTER_LNG)
    parser.add_argument("--center-lat", type=float, default=DEFAULT_CENTER_LAT)
    parser.add_argument("--altitude", type=float, default=DEFAULT_ALTITUDE)
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED)
    parser.add_argument("--heading", type=float, default=DEFAULT_HEADING)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MS)
    parser.add_argument("--ground-seconds", type=int, default=DEFAULT_GROUND_SECONDS)
    parser.add_argument("--climb-seconds", type=int, default=DEFAULT_CLIMB_SECONDS)
    parser.add_argument("--flight-minutes", type=int, default=DEFAULT_FLIGHT_MINUTES)
    parser.add_argument("--emergency-count", type=int, default=DEFAULT_EMERGENCY_COUNT, help="紧急状态数据条数(1~10)")
    parser.add_argument("--spacing", type=float, default=DEFAULT_SPACING, help="多架UAV横向间距(米)，默认2000")
    parser.add_argument("--classification", type=int, default=DEFAULT_CLASSIFICATION,
                        help="航空器分类/模拟器类型: 0=微型 1=轻型 2=小型 3=中型 4=大型，默认2")
    parser.add_argument("--sim-radius", type=float, default=DEFAULT_SIM_RADIUS, help="仿真有效半径(米)，默认100000")
    parser.add_argument("--id-offset", type=int, default=None, help="ID起始偏移量(倒序列表中的索引)，默认自动递增，每次运行换不同ID")
    parser.add_argument("--scene3", action="store_true", default=SCENE_3_ENABLED)
    parser.add_argument("--scene5", action="store_true", default=SCENE_5_ENABLED)
    parser.add_argument("--scene3-5", action="store_true", default=SCENE_3_5_ENABLED)
    parser.add_argument("--output-dir", default=os.path.join(_ROOT, "mock"))
    args = parser.parse_args()

    mock_dir = args.output_dir
    os.makedirs(mock_dir, exist_ok=True)

    scenes = []
    if args.scene3:
        scenes.append(("飞行器丢失状态3.json", 3, "状态3(紧急后恢复)"))
    if args.scene5:
        scenes.append(("飞行器丢失状态5.json", 5, "状态5(丢失)"))
    if args.scene3_5:
        scenes.append(("飞行器丢失状态3-5.json", '3_5', "状态3转5(紧急后丢失)"))

    if not scenes:
        print("[警告] 没有启用的场景，请通过 --scene3 / --scene5 / --scene3-5 指定")
        return

    total_needed = args.count * len(scenes)
    id_pool = UAV_IDENTIFIERS_EXTENDED[::-1]
    if args.id_offset is not None:
        id_offset = args.id_offset % len(id_pool)
        print(f"[手动指定] ID偏移: {id_offset}")
    else:
        id_offset = _get_next_id_offset(total_needed, len(id_pool))
        print(f"[自动递增] ID偏移: {id_offset}")
    # 处理循环绕回：如果尾部不够，从头部补足
    if id_offset + total_needed > len(id_pool):
        all_uav_ids = id_pool[id_offset:] + id_pool[:total_needed - (len(id_pool) - id_offset)]
    else:
        all_uav_ids = id_pool[id_offset:id_offset + total_needed]
    print(f"总场景数: {len(scenes)}, 每场景 UAV 数: {args.count}, 共需 ID: {total_needed}")
    if total_needed > len(id_pool):
        print(f"❌ 错误: 总需求 {total_needed} 超过扩展ID上限 {len(id_pool)}")
        return

    for scene_idx, (filename, scene_type, label) in enumerate(scenes):
        all_data = []
        # 多架UAV时按spacing间距分布（垂直于航向方向展开）
        meters_per_degree_lat = 111320.0
        meters_per_degree_lng = 111320.0 * math.cos(math.radians(args.center_lat))
        spacing_deg_lng = args.spacing / meters_per_degree_lng
        spacing_deg_lat = args.spacing / meters_per_degree_lat
        heading_rad = math.radians(args.heading)
        perp_heading_rad = heading_rad + math.pi / 2
        half_n = (args.count - 1) / 2 if args.count % 2 == 1 else args.count / 2

        # 场景级偏移：不同场景的UAV群整体错开，避免场景间产生短期冲突告警
        # 偏移量 = scene_idx * spacing * (count + 1)，保证相邻场景UAV群间距 >= spacing
        scene_offset_meters = scene_idx * args.spacing * (args.count + 1)
        scene_offset_lng = scene_offset_meters * math.sin(perp_heading_rad) / meters_per_degree_lng
        scene_offset_lat = scene_offset_meters * math.cos(perp_heading_rad) / meters_per_degree_lat
        scene_center_lng = args.center_lng + scene_offset_lng
        scene_center_lat = args.center_lat + scene_offset_lat

        start_idx = scene_idx * args.count
        uav_list = all_uav_ids[start_idx:start_idx + args.count]
        print(f"  [{label}] 使用 UAV ID (倒序): {[u[0] for u in uav_list]}")
        print(f"  [{label}] 场景中心偏移: ({scene_offset_lng:.6f}°, {scene_offset_lat:.6f}°) ≈ {scene_offset_meters:.0f}m")

        for idx, (uid, reg_sign) in enumerate(uav_list):
            if args.count % 2 == 1:
                lateral_idx = idx - half_n
            else:
                lateral_idx = idx - half_n + 0.5
            offset_lng = lateral_idx * spacing_deg_lng * math.sin(perp_heading_rad)
            offset_lat = lateral_idx * spacing_deg_lat * math.cos(perp_heading_rad)
            data = generate_scene_data(
                uid, reg_sign,
                scene_center_lng + offset_lng, scene_center_lat + offset_lat,
                args.altitude, args.speed, args.heading, args.interval,
                args.ground_seconds, args.climb_seconds, args.flight_minutes,
                args.emergency_count, scene_type, args.classification
            )
            all_data.extend(data)
        path = os.path.join(mock_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"[{label}] {path} ({len(all_data)} 条)")


if __name__ == "__main__":
    main()
