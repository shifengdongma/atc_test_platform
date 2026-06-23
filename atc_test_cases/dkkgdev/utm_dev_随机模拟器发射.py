# -*- coding: utf-8 -*-
"""
utm_dev_随机模拟器发射.py

向 dkkgdev 环境发送随机模拟器数据的独立脚本。
用于高可用测试、压力测试等场景。

核心特性：
- 使用 dev_env.py 环境配置
- UID 从 100 开始偏移（避免内置模拟器冲突）
- 支持命令行参数配置（数量、坐标、ID范围等）
- 支持指定特定模拟器ID发射

前置要求：
- 必须先激活 utm conda 环境：`conda activate utm`
- 或使用 `conda run -n utm python <script>` 直接执行

使用方法：
    conda activate utm
    python utm_dev_随机模拟器发射.py --count 10
    
    # 或直接使用 conda run
    conda run -n utm python utm_dev_随机模拟器发射.py --count 10
"""

import time
import threading
import os
import sys
import argparse
from typing import Dict, Any, List, Optional

# 导入 dev_env 环境配置
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dev_env as _env

# 导入 utm_simulator 相关模块
# 路径: d:/AI_Test_2026/atc_test_platform/atc_test_cases/dkkgdev/ -> ../../utm_simulator/
utm_simulator_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'utm_simulator'))
pylib_path = os.path.join(utm_simulator_path, 'pylib')

if os.path.exists(utm_simulator_path):
    sys.path.insert(0, utm_simulator_path)
    sys.path.insert(0, pylib_path)
else:
    print(f"[错误] utm_simulator 路径不存在: {utm_simulator_path}")
    sys.exit(1)

from simulation_core import Simulator
from kafka_proc import KafkaProducerClient, KafkaConsumerClient
from redis_client import RedisClient
import json

# Kafka topics
kafka_uav_data_topic = 'uav_runtime_data'
uav_runtime_trace_topic = 'uav_runtime_trace'
redis_flight_plan_key = "BIZ_DATA:UAV_ROUTE"


class SimulatorEmitter:
    """模拟器发射器：向 dkkgdev 环境发送随机无人机模拟数据"""
    
    def __init__(
        self,
        target_drones: int = 10,      # 维持的活跃无人机数量，不足时自动补充（指定UID时不生效）
        uid_start_offset: int = 200,  # UID起始偏移，从预置ID列表的第N个开始分配（避免与内置模拟器冲突）
        origin_lat: float = 31.0927,   # 仿真中心纬度（度），31.0927 ≈ 上海附近
        origin_lon: float = 121.5084,   # 仿真中心经度（度），121.5084 ≈ 上海附近
        sim_radius_m: float = None,   # 仿真有效半径（米），None=使用默认值10万米
        cruise_speed: float = None,   # 巡航速度(m/s)，None=使用默认值30m/s
        min_alt: float = None,        # 最小巡航高度(米)，None=使用默认值50米
        max_alt: float = None,        # 最大巡航高度(米)，None=使用默认值200米
        specified_uids: List[str] = None,  # 指定特定UID列表发射，如为None则自动随机生成
        # 示例: ['DJI1MAV3Z5A6B7C8D9E0', 'DJI1PHN4F1G2H3J4K5L6']
    ):
        """
        初始化模拟器发射器
        
        Args:
            target_drones: 维持的活跃无人机数量，不足时自动补充（指定UID时不生效）
            uid_start_offset: UID起始偏移量，从预置ID列表的第N个开始分配，避免与内置模拟器ID冲突
            origin_lat: 仿真中心纬度，默认31.0927（约上海附近）
            origin_lon: 仿真中心经度，默认121.5084（约上海附近）
            sim_radius_m: 仿真有效半径（米），默认100000米（100公里）
            cruise_speed: 巡航速度(m/s)，默认30m/s
            min_alt: 最小巡航高度(米)，默认50米
            max_alt: 最大巡航高度(米)，默认200米
            specified_uids: 指定特定UID列表发射，若为None则随机生成
        """
        self.target_drones = target_drones
        self.uid_start_offset = uid_start_offset
        self.specified_uids = specified_uids
        self.active_plans = []
        self.running = True
        self.emitted_count = 0
        
        # 初始化 Redis 客户端（使用 dev_env 配置）
        self.redis_client = RedisClient(
            _env.redis_ip, 
            _env.redis_port, 
            _env.redis_password
        )
        
        # 初始化 Kafka 生产者（使用 dev_env 配置）
        self.kafka_producer = KafkaProducerClient(
            bootstrap_servers=_env.kafka_url,
            bootstrap_servers_mirror=getattr(_env, "kafka_url2", None)
        )
        
        # 初始化 Kafka 消费者
        self.kafka_consumer = KafkaConsumerClient(
            bootstrap_servers=_env.kafka_url,
            group_id=f"dev_simulator_group_{os.getpid()}",
            consume_from_latest_on_start=True
        )
        self.kafka_consumer.subscribe([uav_runtime_trace_topic])
        
        # 初始化仿真器（传递 uid_start_offset）
        print(f"[初始化] Simulator 参数: origin_lat={origin_lat}, origin_lon={origin_lon}, uid_start_offset={uid_start_offset}")
        self.simulator = Simulator(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            sim_radius_m=sim_radius_m,
            uid_start_offset=uid_start_offset,
        )
        print(f"[初始化] Simulator 实际使用: origin_lat={self.simulator.origin_lat}, origin_lon={self.simulator.origin_lon}")
        print(f"[初始化] UID偏移设置: uid_start_offset={self.simulator.uid_start_offset}")
        
        # 如果指定了特定UID，使用指定的模拟器
        if specified_uids:
            self._emit_specified_uids(specified_uids)
    
    def _emit_specified_uids(self, uids: List[str]):
        """发射指定UID的无人机"""
        print(f"[配置] 将发射指定UID的无人机: {uids}")
        for uid in uids:
            plan = self.simulator.generate_plan()
            # 覆盖 UID 为指定值
            plan.aircraft.uid = uid.encode('utf-8')
            # 更新 agents 中的 key
            old_uid = plan.aircraft.uid.decode('utf-8')
            if old_uid in self.simulator.agents:
                agent = self.simulator.agents.pop(old_uid)
                agent.uid = uid
                self.simulator.agents[uid] = agent
            self._add_redis_plan(plan)
            self.active_plans.append(plan)
            self.emitted_count += 1
            print(f"[发射] 无人机 {uid} 已发射")
    
    def _plan_to_route_data(self, plan) -> Dict[str, Any]:
        """将飞行计划转为 Redis 航线 Hash 的一条 value 结构（算法对接格式）"""
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
            "flightTaskName": "dev_simulator",
            "routeList": routeList,
        }
        return {
            "uniqueProductIdentificationCode": uid,
            "flightPlanList": [flightPlan],
        }
    
    def _add_redis_plan(self, plan):
        """将单机航线写入 Redis BIZ_DATA:UAV_ROUTE"""
        try:
            route_data = self._plan_to_route_data(plan)
            uid = route_data["uniqueProductIdentificationCode"]
            result = self.redis_client.hset(
                redis_flight_plan_key, 
                uid, 
                json.dumps(route_data, ensure_ascii=False)
            )
            if result:
                print(f"[Redis] 插入无人机航线数据成功: {uid}")
            return result
        except Exception as e:
            print(f"[Redis] 插入无人机航线数据失败: {e}")
    
    def _maintain_traffic(self) -> List[str]:
        """维持活跃无人机数量：不足时生成新计划并写入 Redis"""
        needed = self.target_drones - len(self.active_plans)
        if needed <= 0:
            return []
        
        # 如果指定了特定UID，不再自动生成
        if self.specified_uids:
            return []
        
        new_uids: List[str] = []
        for _ in range(needed):
            new_plan = self.simulator.generate_plan()
            uid = new_plan.aircraft.uid.decode('utf-8')
            # 获取第一个航点的坐标
            if new_plan.data.traj.count > 0:
                first_wp = new_plan.data.traj.wps[0]
                start_lat, start_lon = first_wp.point.lat, first_wp.point.lon
                print(f"[生成] UID={uid}, 起始坐标: lat={start_lat:.6f}, lon={start_lon:.6f}")
            self._add_redis_plan(new_plan)
            self.active_plans.append(new_plan)
            new_uids.append(uid)
            self.emitted_count += 1
        return new_uids
    
    def _telemetry_to_kafka_message(self, t) -> Dict[str, Any]:
        """将单条遥测 current 转为 uav_runtime_data 的一条消息"""
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
        """仿真一步：维持机数、步进仿真、同步活跃计划、构造遥测并写 Kafka"""
        try:
            telemetries = self.simulator.step(1.0)
            
            # 处理已降落的无人机
            for uid in self.simulator.last_finished_uids:
                print(f"[降落] 无人机 {uid} 已降落，本架次结束")
            
            # 同步活跃计划列表
            active_uids = set(self.simulator.agents.keys())
            self.active_plans = [
                p for p in self.active_plans 
                if p.aircraft.uid.decode() in active_uids
            ]
            
            # 补充无人机
            new_uids = self._maintain_traffic()
            for uid in new_uids:
                print(f"[发射] 无人机 {uid} 新航线已写入 Redis")
            
            # 发送遥测数据
            data = []
            for item in telemetries:
                t = item["current"]
                kafka_data = self._telemetry_to_kafka_message(t)
                uav_vid = kafka_data["uniqueProductIdentificationCode"]
                
                if t.operatingStatus != 2:
                    print(f'[状态] uav:{uav_vid} status={t.operatingStatus}, stop fly')
                
                data.append(kafka_data)
                
                # 打印第一个无人机的详细数据
                if uav_vid == 'UAV_00100' or (self.specified_uids and uav_vid == self.specified_uids[0]):
                    print(f"[遥测] {uav_vid}: lat={t.location.lat:.6f}, lon={t.location.lon:.6f}, alt={t.location.alt:.1f}m")
            
            if data:
                self.kafka_producer.send_bulk(data, kafka_uav_data_topic)
                
        except Exception as e:
            print(f"[仿真] get_flight_plans_simulator失败: {e}")
    
    def _consume_uav_runtime_trace(self):
        """消费 topic uav_runtime_trace"""
        while self.running:
            try:
                messages = self.kafka_consumer.poll(timeout_ms=1000)
                for msg in messages:
                    if isinstance(msg, dict):
                        redis_key = msg.get("redisKey") or msg.get("redis_key")
                        if redis_key:
                            value = self.redis_client.get_value_by_key(redis_key)
                            if value is not None:
                                active_uids = set(self.simulator.agents.keys())
                                if isinstance(value, list):
                                    value = [
                                        item for item in value 
                                        if item.get('uniqueProductIdentificationCode') in active_uids
                                    ]
                                if value:
                                    ts = int(value[0].get('timestamp', 0) / 1000)
                                    print(f"\033[32m[trace] {ts} 收到 {len(value)} 条预测数据\033[0m")
            except Exception as e:
                print(f"[消费] 消费 uav_runtime_trace 异常: {e}")
            time.sleep(0.1)
    
    def _simulation_loop(self):
        """每秒执行一次仿真步"""
        while self.running:
            t0 = time.perf_counter()
            self.get_flight_plans_simulator()
            elapsed = time.perf_counter() - t0
            time.sleep(max(0.0, 1.0 - elapsed))
    
    def start(self):
        """启动发射器"""
        print("=" * 60)
        print("🚀 dkkgdev 环境随机模拟器发射器启动")
        print("=" * 60)
        print(f"[配置] 目标无人机数量: {self.target_drones}")
        print(f"[配置] UID起始偏移: {self.uid_start_offset}")
        print(f"[配置] Redis: {_env.redis_ip}:{_env.redis_port}")
        print(f"[配置] Kafka: {_env.kafka_url}")
        if self.specified_uids:
            print(f"[配置] 指定UID发射: {self.specified_uids}")
        print("=" * 60)
        
        # 启动仿真线程
        self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.thread.start()
        
        # 启动 trace 消费线程
        self.trace_thread = threading.Thread(
            target=self._consume_uav_runtime_trace, 
            daemon=True
        )
        self.trace_thread.start()
        
        return self
    
    def stop(self):
        """停止发射器"""
        print("\n[停止] 正在停止发射器...")
        self.running = False
        
        if hasattr(self, 'thread') and self.thread:
            self.thread.join(timeout=5)
        
        if hasattr(self, 'trace_thread') and self.trace_thread:
            self.trace_thread.join(timeout=5)
        
        if hasattr(self, 'kafka_producer'):
            self.kafka_producer.close()
        
        print(f"[统计] 共发射 {self.emitted_count} 架次无人机")
        print("[停止] 发射器已停止")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='dkkgdev 环境随机模拟器发射器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例用法:
  # 发射 10 架无人机，UID 从 100 开始
  python utm_dev_随机模拟器发射.py --count 10

  # 发射 5 架无人机，UID 从 200 开始
  python utm_dev_随机模拟器发射.py --count 5 --uid-offset 200

  # 指定特定 UID 发射
  python utm_dev_随机模拟器发射.py --uids UAV_00100,UAV_00101,UAV_00102

  # 自定义坐标和范围
  python utm_dev_随机模拟器发射.py --origin-lat 39.9 --origin-lon 116.4 --radius 50000

  # 自定义高度和速度
  python utm_dev_随机模拟器发射.py --alt-min 100 --alt-max 300 --speed 40
'''
    )
    
    parser.add_argument(
        '--count', '-c',
        type=int,
        default=10,
        help='模拟器数量 (默认: 10)'
    )
    
    parser.add_argument(
        '--uid-offset', '-o',
        type=int,
        default=200,
        help='UID起始偏移量，用于避免ID冲突 (默认: 200)'
    )
    
    # 默认坐标（与 SimulatorEmitter.__init__() 默认值保持一致）
    DEFAULT_ORIGIN_LAT = 31.0927   # 纬度：上海附近
    DEFAULT_ORIGIN_LON = 121.5084  # 经度：上海附近
    
    parser.add_argument(
        '--origin-lat',
        type=float,
        default=DEFAULT_ORIGIN_LAT,
        help=f'仿真中心纬度 (默认: {DEFAULT_ORIGIN_LAT})'
    )
    
    parser.add_argument(
        '--origin-lon',
        type=float,
        default=DEFAULT_ORIGIN_LON,
        help=f'仿真中心经度 (默认: {DEFAULT_ORIGIN_LON})'
    )
    
    parser.add_argument(
        '--radius', '-r',
        type=float,
        default=None,
        help='仿真有效半径（米）(默认: 使用 simulation_core 默认值)'
    )
    
    parser.add_argument(
        '--speed', '-s',
        type=float,
        default=None,
        help='巡航速度(m/s) (默认: 使用 simulation_core 默认值)'
    )
    
    parser.add_argument(
        '--alt-min',
        type=float,
        default=None,
        help='最小巡航高度 (默认: 使用 simulation_core 默认值)'
    )
    
    parser.add_argument(
        '--alt-max',
        type=float,
        default=None,
        help='最大巡航高度 (默认: 使用 simulation_core 默认值)'
    )
    
    parser.add_argument(
        '--uids', '-u',
        type=str,
        default=None,
        help='指定特定UID列表（逗号分隔），例如: UAV_00100,UAV_00101,UAV_00102'
    )
    
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    
    # 解析指定UID列表
    specified_uids = None
    if args.uids:
        specified_uids = [uid.strip() for uid in args.uids.split(',') if uid.strip()]
    
    # 配置仿真参数
    if args.speed or args.alt_min or args.alt_max:
        import simulation_core as sim
        sim.set_simulation_params(
            cruise_speed=args.speed,
            min_cruise_alt=args.alt_min,
            max_cruise_alt=args.alt_max,
        )
    
    # 创建并启动发射器
    emitter = SimulatorEmitter(
        target_drones=args.count,
        uid_start_offset=args.uid_offset,
        origin_lat=args.origin_lat,
        origin_lon=args.origin_lon,
        sim_radius_m=args.radius,
        cruise_speed=args.speed,
        min_alt=args.alt_min,
        max_alt=args.alt_max,
        specified_uids=specified_uids,
    ).start()
    
    try:
        print("\n[运行] 按 Ctrl+C 停止发射器")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[信号] 收到停止信号")
        emitter.stop()
    
    print("[退出] 程序结束")
