# -*- coding: utf-8 -*-
import time
import threading
import os
from typing import Dict, Any, List
from kafka_proc import KafkaConsumerClient, KafkaProducerClient
from simulation_core import Simulator
import json
from redis_client import RedisClient
from env import redis_ip, redis_port, redis_password, kafka_url
import env as _env

kafka_uav_data_topic = 'uav_runtime_data'
uav_runtime_trace_topic = 'uav_runtime_trace'
redis_flight_plan_key = "BIZ_DATA:UAV_ROUTE"

class DataSource:
    """数据获取模块"""
    
    def __init__(
        self,
        target_drones: int = 10,
        origin_lat: float = None,
        origin_lon: float = None,
        sim_radius_m: float = None,
        uid_start_offset: int = 0,
    ):
        """初始化数据源
        
        Args:
            target_drones: 维持的活跃无人机数量，默认10
            origin_lat: 仿真中心纬度，默认使用 simulation_core 模块默认值
            origin_lon: 仿真中心经度，默认使用 simulation_core 模块默认值
            sim_radius_m: 仿真有效半径（米），默认使用 simulation_core 模块默认值
            uid_start_offset: 预置 ID 列表起始偏移量，用于跳过固定轨迹已占用的 ID
        """
        self.active_plans = []
        self.target_drones = target_drones
        self.redis_client = RedisClient(redis_ip, redis_port, redis_password)
        self.simulator = Simulator(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            sim_radius_m=sim_radius_m,
            uid_start_offset=uid_start_offset,
        )
        self.kafka_producer = KafkaProducerClient(
            kafka_url, bootstrap_servers_mirror=getattr(_env, "kafka_url2", None)
        )
        # 每个进程使用独立的 group_id，多实例同时运行时各自都能收到全部消息（否则同组会瓜分分区，后启动的收不到）
        self.kafka_consumer = KafkaConsumerClient(
            bootstrap_servers=kafka_url,
            group_id=f"utm_demo_group_{os.getpid()}",
            consume_from_latest_on_start=True
        )
        self.kafka_consumer.subscribe([uav_runtime_trace_topic])
    
    def __del__(self):
        """析构函数，清理资源"""
        if hasattr(self, 'kafka_consumer') and self.kafka_consumer:
            try:
                self.kafka_consumer.close()
            except Exception:
                pass  # 退出时消费者可能已析构，忽略关闭异常
    
    def _plan_to_route_data(self, plan) -> Dict[str, Any]:
        """将飞行计划转为 Redis 航线 Hash 的一条 value 结构（算法对接格式）。"""
        uid = plan.aircraft.uid.decode('utf-8')
        routeList = []
        wps_count = plan.data.traj.count
        for i in range(wps_count - 1):
            w0, w1 = plan.data.traj.wps[i], plan.data.traj.wps[i + 1]
            routeList.append({
                "sequence": i,
                "type": 2,
                "segmentStartLon": w0.point.lon,
                "segmentStartLat": w0.point.lat,
                "segmentEndLon": w1.point.lon,
                "segmentEndLat": w1.point.lat,
                "segmentStartHeight": w0.point.alt,
                "segmentEndHeight": w1.point.alt,
                "segmentProtectHeight": w1.segmentVerticalleight,
                "segmentProtectHeightType": w1.segmentProtectHeightType,
                "segmentWidth": w1.segmentWidth,
            })
        flightPlan = {
            "flightPlanId": 1,
            "planTakeoffTime": plan.start_time,
            "planLandTime": plan.end_time,
            "flightTaskId": 1,
            "flightTaskName": "test",
            "routeList": routeList,
        }
        return {
            "uniqueProductIdentificationCode": uid,
            "flightPlanList": [flightPlan],
        }

    def add_redis_plan(self, plan):
        """将单机航线写入 Redis BIZ_DATA:UAV_ROUTE。"""
        try:
            route_data = self._plan_to_route_data(plan)
            uid = route_data["uniqueProductIdentificationCode"]
            result = self.redis_client.hset(redis_flight_plan_key, uid, json.dumps(route_data, ensure_ascii=False))
            if result:
                print(f"向Redis插入无人机航线数据成功: {uid}")
            return result
        except Exception as e:
            print(f"向Redis插入无人机航线数据失败:{e}")
                
    def _maintain_traffic(self) -> List[str]:
        """维持活跃无人机数量：不足时生成新计划并写入 Redis。返回本帧新补充任务的 uid 列表（用于重飞日志）。"""
        needed = self.target_drones - len(self.active_plans)
        if needed <= 0:
            return []
        new_uids: List[str] = []
        for _ in range(needed):
            new_plan = self.simulator.generate_plan()
            self.add_redis_plan(new_plan)
            self.active_plans.append(new_plan)
            new_uids.append(new_plan.aircraft.uid.decode("utf-8"))
        return new_uids

    def _telemetry_to_kafka_message(self, t) -> Dict[str, Any]:
        """将单条遥测 current 转为 uav_runtime_data 的一条消息（算法对接格式）。"""
        uav_vid = t.uid.decode('utf-8')
        return {
            "uniqueProductIdentificationCode": uav_vid,
            "realNameRegistrationSign": t.realNameRegistrationSign,
            "uasOperationCategory": 1,
            "classification": 1,
            "rpsLocationType": 1,
            "rpsLongitude": 0,
            "rpsLatitude": 0,
            "rpsAltitude": 0,
            "longitude": t.location.lon,
            "latitude": t.location.lat,
            "trackAngle": t.heading,
            "speed": t.speed,
            "geodeticAltitude": t.location.alt,
            "verticalSpeed": t.verticalSpeed,
            "relativeAltitude": t.relativeAltitude,
            "ressureAltitude": t.ressureAltitude,
            "operatingStatus": t.operatingStatus,
            "coordinateSystemType": t.coordinateSystemType,
            "horizontalAccuracy": t.horizontalAccuracy,
            "verticalAccuracy": t.verticalAccuracy,
            "speedAccuracy": t.speedAccuracy,
            "timestamp": t.timestamp * 1000,
            "timestampAccuracy": 0,
            "sourceType": t.sourceType,
            "addInf": t.addInf,
        }

    def get_flight_plans_simulator(self) -> None:
        """仿真一步：维持机数、步进仿真、同步活跃计划、构造遥测并写 Kafka。"""
        try:
            telemetries = self.simulator.step(1.0)
            for uid in self.simulator.last_finished_uids:
                print(f"无人机 {uid} 已降落，本架次结束（已从仿真移除）")
            active_uids = set(self.simulator.agents.keys())
            self.active_plans = [p for p in self.active_plans if p.aircraft.uid.decode() in active_uids]
            # 每步补充：确保活跃无人机数量始终维持在 TARGET_DRONES
            new_uids = self._maintain_traffic()
            for uid in new_uids:
                print(f"无人机 {uid} 新航线已写入 Redis，开始新一轮飞行（维持场域 {self.target_drones} 架）")
            data = []
            for item in telemetries:
                t = item["current"]
                kafka_data = self._telemetry_to_kafka_message(t)
                uav_vid = kafka_data["uniqueProductIdentificationCode"]
                if t.operatingStatus != 2:
                    print(f'simulator uav:{uav_vid} status={t.operatingStatus}, stop fly')
                data.append(kafka_data)
                if uav_vid == 'UAV_00100':
                    print(f"uav data: {kafka_data}, timestamp: {int(time.time())}")
            self.kafka_producer.send_bulk(data, kafka_uav_data_topic)
        except Exception as e:
            print(f"get_flight_plans_simulator失败:{e}")


class DataFlow:
    """数据流：仿真线程 + uav_runtime_trace 消费线程。"""

    def __init__(
        self,
        target_drones: int = 10,
        origin_lat: float = None,
        origin_lon: float = None,
        sim_radius_m: float = None,
        uid_start_offset: int = 0,
    ):
        self.data_source = DataSource(
            target_drones=target_drones,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            sim_radius_m=sim_radius_m,
            uid_start_offset=uid_start_offset,
        )
        self.running = True
        self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.thread.start()
        self.trace_consumer_thread = threading.Thread(target=self._consume_uav_runtime_trace, daemon=True)
        self.trace_consumer_thread.start()
                    
    def _consume_uav_runtime_trace(self):
        """消费 topic uav_runtime_trace：读取消息中的 redisKey，从 Redis 查出具体数据并打印。"""
        while self.running:
            try:
                messages = self.data_source.kafka_consumer.poll(timeout_ms=1000)
                for msg in messages:
                    if isinstance(msg, dict):
                        redis_key = msg.get("redisKey") or msg.get("redis_key")
                        if redis_key:
                            value = self.data_source.redis_client.get_value_by_key(redis_key)
                            if value is not None:
                                # 只保留仿真器中仍存在的无人机（合法 uid）的预测条目
                                active_uids = set(self.data_source.simulator.agents.keys())
                                if isinstance(value, list):
                                    value = [item for item in value if item.get('uniqueProductIdentificationCode') in active_uids]
                                if value:
                                    unique_codes = list({item.get('uniqueProductIdentificationCode') for item in value if item.get('uniqueProductIdentificationCode') is not None})
                                    print(f"\033[32m[uav_runtime_trace] {int(value[0]['timestamp']/1000)} 收到 {len(value)} 条\033[0m")
            except Exception as e:
                print(f"消费 uav_runtime_trace 异常: {e}")
            time.sleep(0.1)

    def _simulation_loop(self):
        """每秒执行一次仿真步（约 1s 周期）。"""
        while self.running:
            t0 = time.perf_counter()
            self.data_source.get_flight_plans_simulator()
            elapsed = time.perf_counter() - t0
            time.sleep(max(0.0, 1.0 - elapsed))

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.trace_consumer_thread and self.trace_consumer_thread.is_alive():
            self.trace_consumer_thread.join(timeout=5)
        self.data_source.kafka_producer.close()
        print("程序已停止")

if __name__ == '__main__':
    print('main begin')
    
    cFlow = DataFlow()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("收到停止信号，正在停止程序...")
        cFlow.stop()
    print('app run exit')
