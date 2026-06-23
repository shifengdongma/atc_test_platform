#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高可用多点多组发送脚本 (HA Multi-Endpoint Sender)

功能：
- 支持配置多个 Kafka/Redis 端点（多点）
- 每个端点独立进程运行（多组），互不干扰
- 支持从 JSON 场景文件加载数据循环发送
- 支持实时仿真生成数据发送
- 支持 alive 模式：数据耗尽后自动循环/重飞
- 每个端点独立消费 uav_runtime_trace
- 连接断开自动重连与发送失败重试
- 配置驱动，通过 YAML 管理所有端点

参考：utm_moc52_ha 多进程高可用设计

用法：
    python ha_multi_sender.py --config ha_multi_sender_config.yaml

配置示例见 ha_multi_sender_config.yaml
"""

import os
import sys
import time
import json
import copy
import signal
import argparse
import multiprocessing
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.kafka_client import create_kafka_producer
from core.redis_client import RedisClient
from core.config_manager import ConfigManager


# ==================== 常量 ====================
KAFKA_UAV_DATA_TOPIC = 'uav_runtime_data'
KAFKA_UAV_TRACE_TOPIC = 'uav_runtime_trace'
REDIS_FLIGHT_PLAN_KEY = "BIZ_DATA:UAV_ROUTE"


@dataclass
class EndpointConfig:
    """单个端点配置"""
    name: str
    kafka_url: str
    redis_host: str
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    topic: str = KAFKA_UAV_DATA_TOPIC
    trace_topic: str = KAFKA_UAV_TRACE_TOPIC
    # 数据源配置
    data_source_type: str = "scene_file"  # scene_file | simulation
    scene_file: Optional[str] = None
    # 多线程仿真参数（参考 main_multi.py）
    num_workers: int = 15               # 工作线程数（仿真模式使用）
    drone_count: int = 3000             # 总活跃无人机数量（仿真模式使用）
    timestamp_offset_ms: int = -1000    # 时间戳偏移量（毫秒）
    enable_worker_log: bool = False     # 是否打印 Worker 详细日志
    # 发送参数
    interval_ms: int = 1000
    alive_mode: bool = True  # True=数据耗尽后循环; False=发送完停止
    # 重连/重试
    reconnect_interval: int = 5
    max_retry: int = 3
    # 消费 trace
    consume_trace: bool = True


# ==================== 数据源 ====================

class SceneFileDataSource:
    """基于 JSON 场景文件的数据源"""

    def __init__(self, scene_file: str, alive_mode: bool = True):
        self.scene_file = scene_file
        self.alive_mode = alive_mode
        self.records: List[Dict[str, Any]] = []
        self.allowed_uav_uids: List[str] = []
        self._uid_record_indices: Dict[str, List[int]] = {}
        self._uid_cursor: Dict[str, int] = {}
        self._load_data()

    def _load_data(self) -> None:
        try:
            with open(self.scene_file, 'r', encoding='utf-8') as f:
                self.records = json.load(f)
            # 按 uid 分组索引
            self._uid_record_indices = {}
            for i, item in enumerate(self.records):
                uid = item.get("uniqueProductIdentificationCode")
                if not uid:
                    continue
                if uid not in self._uid_record_indices:
                    self._uid_record_indices[uid] = []
                self._uid_record_indices[uid].append(i)
            self.allowed_uav_uids = list(self._uid_record_indices)
            self._uid_cursor = {uid: 0 for uid in self.allowed_uav_uids}
            print(f"[数据源] 加载场景文件: {self.scene_file}, 共 {len(self.records)} 条, UAV: {self.allowed_uav_uids}")
        except Exception as e:
            print(f"[数据源] 加载场景文件失败: {e}")
            self.records = []

    def get_next_batch(self) -> List[Dict[str, Any]]:
        """按 uid 各取一条，时间戳更新为当前时间"""
        if not self.records or not self.allowed_uav_uids:
            return []
        now_ts = int(time.time() * 1000)
        batch = []
        for uid in self.allowed_uav_uids:
            indices = self._uid_record_indices.get(uid)
            if not indices:
                continue
            # alive 模式下循环
            if self._uid_cursor[uid] >= len(indices):
                if self.alive_mode:
                    self._uid_cursor[uid] = 0
                else:
                    continue
            pos = self._uid_cursor[uid]
            self._uid_cursor[uid] += 1
            idx = indices[pos]
            record = copy.deepcopy(self.records[idx])
            record["timestamp"] = now_ts
            batch.append(record)
        return batch

    def is_exhausted(self) -> bool:
        if self.alive_mode:
            return False
        return all(
            self._uid_cursor.get(uid, 0) >= len(self._uid_record_indices.get(uid, []))
            for uid in self.allowed_uav_uids
        )


# ==================== 多线程仿真 Worker（参考 main_multi.py） ====================

def get_worker_target(worker_index: int, num_workers: int, target_drones: int) -> int:
    """计算指定线程应维护的活跃无人机数量（均分，余数分配给前面线程）"""
    drones_per_worker = target_drones // num_workers
    remainder = target_drones % num_workers
    base = drones_per_worker
    if worker_index < remainder:
        base += 1
    return base


class SimulationWorker:
    """
    单个仿真工作线程（参考 main_multi.py WorkerDataSource）
    每个 Worker 拥有独立的 Simulator，共享 Kafka Producer / Redis
    """

    def __init__(
        self,
        worker_id: int,
        target_drones: int,
        kafka_producer,
        redis_client,
        timestamp_offset_ms: int = -1000,
        enable_worker_log: bool = False,
    ):
        self.worker_id = worker_id
        self.target_drones = target_drones
        self.kafka_producer = kafka_producer
        self.redis_client = redis_client
        self.timestamp_offset_ms = timestamp_offset_ms
        self.enable_worker_log = enable_worker_log

        self.init_plan = False
        self.all_plans_ended = False
        self.active_plans = []
        self.simulator = None
        self._init_simulator()

    def _init_simulator(self):
        try:
            from simulation.simulation_core import Simulator
            self.simulator = Simulator()
        except Exception as e:
            print(f"[Worker-{self.worker_id}] 仿真器初始化失败: {e}")

    def _plan_to_route_data(self, plan) -> Dict[str, Any]:
        """将飞行计划转为 Redis 航线 Hash 的 value 结构"""
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
        """将单机航线写入 Redis"""
        try:
            route_data = self._plan_to_route_data(plan)
            uid = route_data["uniqueProductIdentificationCode"]
            result = self.redis_client.hset(REDIS_FLIGHT_PLAN_KEY, uid, json.dumps(route_data, ensure_ascii=False))
            if result and self.enable_worker_log:
                print(f"[Worker-{self.worker_id}] 向Redis插入无人机航线数据成功: {uid}")
            return result
        except Exception as e:
            print(f"[Worker-{self.worker_id}] 向Redis插入无人机航线数据失败:{e}")

    def _maintain_traffic(self):
        """维持本线程的活跃无人机数量（参考 main_multi.py）"""
        # 先清理已落地的 agents
        finished_ids = [uid for uid, agent in self.simulator.agents.items() if agent.state == 5]
        for uid in finished_ids:
            del self.simulator.agents[uid]

        # 同步 active_plans
        active_uids = set(self.simulator.agents.keys())
        self.active_plans = [p for p in self.active_plans if p.aircraft.uid.decode() in active_uids]

        needed = self.target_drones - len(self.active_plans)
        if needed <= 0:
            return
        # 每轮最多补充 5 架，避免 generate_plan 阻塞循环
        max_generate_per_step = 5
        for _ in range(min(needed, max_generate_per_step)):
            new_plan = self.simulator.generate_plan()
            self.add_redis_plan(new_plan)
            self.active_plans.append(new_plan)

    def _telemetry_to_kafka_message(self, t) -> Dict[str, Any]:
        """将单条遥测转为 uav_runtime_data 消息"""
        uav_vid = t.uid.decode('utf-8')
        return {
            "uniqueProductIdentificationCode": uav_vid,
            "realNameRegistrationSign": uav_vid,
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
            "timestamp": t.timestamp * 1000 + self.timestamp_offset_ms,
            "timestampAccuracy": 0,
        }

    def step(self) -> None:
        """仿真一步：维持机数、步进仿真、构造遥测并写 Kafka"""
        if not self.simulator:
            return
        try:
            self._maintain_traffic()
            if not self.init_plan:
                self.init_plan = True

            telemetries = self.simulator.step(1.0)
            active_uids = set(self.simulator.agents.keys())
            self.active_plans = [p for p in self.active_plans if p.aircraft.uid.decode() in active_uids]

            if self.init_plan and len(self.active_plans) == 0 and len(active_uids) == 0:
                self.all_plans_ended = True

            data = []
            for item in telemetries:
                t = item["current"]
                kafka_data = self._telemetry_to_kafka_message(t)
                if t.operatingStatus != 2 and self.enable_worker_log:
                    print(f'[Worker-{self.worker_id}] simulator uav:{kafka_data["uniqueProductIdentificationCode"]} status={t.operatingStatus}')
                data.append(kafka_data)

            if data and self.kafka_producer:
                self.kafka_producer.send_bulk(data, KAFKA_UAV_DATA_TOPIC)
        except Exception as e:
            print(f"[Worker-{self.worker_id}] step 失败:{e}")

    def active_drone_count(self) -> int:
        return len(self.active_plans)


# ==================== 端点发送器 ====================

class EndpointSender:
    """单个端点的数据发送与消费管理"""

    def __init__(self, config: EndpointConfig, instance_id: str):
        self.config = config
        self.instance_id = instance_id
        self.running = True
        self.kafka_producer = None
        self.redis_client = None
        self.kafka_consumer = None
        self.data_source = None          # scene_file 模式使用
        self.workers: List[SimulationWorker] = []      # simulation 模式使用
        self.worker_threads: List[threading.Thread] = []  # simulation 模式使用
        self.trace_log: List[Dict[str, Any]] = []
        self.sent_count = 0
        self.failed_count = 0
        self._connect_clients()
        self._init_data_source()

    def _connect_clients(self):
        """连接 Kafka 和 Redis，支持自动重连"""
        # Kafka Producer
        try:
            self.kafka_producer = create_kafka_producer(
                self.config.kafka_url,
                client_type="kafka-python",
                verbose=True
            )
            print(f"[{self.instance_id}] Kafka 连接成功: {self.config.kafka_url}")
        except Exception as e:
            print(f"[{self.instance_id}] Kafka 连接失败: {e}")
            self.kafka_producer = None

        # Redis
        try:
            self.redis_client = RedisClient(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                db=self.config.redis_db
            )
            print(f"[{self.instance_id}] Redis 连接成功: {self.config.redis_host}:{self.config.redis_port}")
        except Exception as e:
            print(f"[{self.instance_id}] Redis 连接失败: {e}")
            self.redis_client = None

        # Kafka Consumer（用于消费 trace）
        if self.config.consume_trace:
            try:
                from core.kafka_client import create_kafka_consumer
                self.kafka_consumer = create_kafka_consumer(
                    bootstrap_servers=self.config.kafka_url,
                    group_id=f"ha_sender_group_{os.getpid()}_{self.instance_id}",
                    consume_from_latest_on_start=True
                )
                self.kafka_consumer.subscribe([self.config.trace_topic])
                print(f"[{self.instance_id}] Kafka Consumer 订阅成功: {self.config.trace_topic}")
            except Exception as e:
                print(f"[{self.instance_id}] Kafka Consumer 初始化失败: {e}")
                self.kafka_consumer = None

    def _init_data_source(self):
        if self.config.data_source_type == "scene_file":
            if self.config.scene_file and os.path.exists(self.config.scene_file):
                self.data_source = SceneFileDataSource(
                    self.config.scene_file,
                    alive_mode=self.config.alive_mode
                )
            else:
                print(f"[{self.instance_id}] 场景文件不存在: {self.config.scene_file}")
        elif self.config.data_source_type == "simulation":
            self._init_simulation_workers()
        else:
            print(f"[{self.instance_id}] 未知数据源类型: {self.config.data_source_type}")

    def _init_simulation_workers(self):
        """创建多线程仿真 Worker（参考 main_multi.py）"""
        print(f"[{self.instance_id}] 初始化 {self.config.num_workers} 个仿真 Worker，目标机数: {self.config.drone_count}")
        for i in range(self.config.num_workers):
            target = get_worker_target(i, self.config.num_workers, self.config.drone_count)
            worker = SimulationWorker(
                worker_id=i,
                target_drones=target,
                kafka_producer=self.kafka_producer,
                redis_client=self.redis_client,
                timestamp_offset_ms=self.config.timestamp_offset_ms,
                enable_worker_log=self.config.enable_worker_log,
            )
            self.workers.append(worker)
            print(f"[{self.instance_id}] Worker-{i} 已创建，目标无人机数: {target}")

    def _send_batch(self, records: List[Dict[str, Any]]) -> bool:
        """发送一批数据到 Kafka"""
        if not records:
            return True
        if not self.kafka_producer:
            print(f"[{self.instance_id}] Kafka 未连接，跳过发送")
            return False
        try:
            self.kafka_producer.send_bulk(records, self.config.topic)
            self.sent_count += len(records)
            return True
        except Exception as e:
            print(f"[{self.instance_id}] Kafka 发送失败: {e}")
            self.failed_count += len(records)
            return False

    def _consume_trace(self):
        """消费 uav_runtime_trace 线程"""
        if not self.kafka_consumer:
            return
        while self.running:
            try:
                messages = self.kafka_consumer.poll(timeout_ms=500)
                for msg in messages:
                    if isinstance(msg, dict):
                        redis_key = msg.get("redisKey") or msg.get("redis_key")
                        if redis_key and self.redis_client:
                            try:
                                value = self.redis_client.get_value_by_key(redis_key)
                                if value:
                                    self.trace_log.append({"key": redis_key, "value": value})
                                    print(f"\033[32m[{self.instance_id}] [trace] 收到 {len(value) if isinstance(value, list) else 1} 条\033[0m")
                            except Exception as e:
                                print(f"[{self.instance_id}] Redis 查询失败: {e}")
            except Exception as e:
                print(f"[{self.instance_id}] trace 消费异常: {e}")
            time.sleep(0.05)

    def _send_loop(self):
        """主发送循环"""
        if not self.data_source:
            print(f"[{self.instance_id}] 数据源未初始化，发送循环无法启动")
            return
        while self.running:
            t0 = time.perf_counter()
            try:
                batch = self.data_source.get_next_batch()
                if batch:
                    self._send_batch(batch)
                elif self.config.data_source_type == "scene_file" and not self.config.alive_mode:
                    if self.data_source.is_exhausted():
                        print(f"[{self.instance_id}] 数据已耗尽，发送循环停止")
                        break
            except Exception as e:
                print(f"[{self.instance_id}] 发送循环异常: {e}")
            elapsed = time.perf_counter() - t0
            sleep_time = max(0, self.config.interval_ms / 1000.0 - elapsed)
            time.sleep(sleep_time)

    def _worker_loop(self, worker: SimulationWorker, worker_index: int):
        """单个仿真 Worker 的主循环（参考 main_multi.py _worker_loop）"""
        initial_jitter = worker_index * 0.05
        time.sleep(initial_jitter)
        while self.running:
            t0 = time.perf_counter()
            worker.step()
            elapsed = time.perf_counter() - t0
            jitter = random.uniform(-0.03, 0.03)
            sleep_time = max(0.0, 1.0 - elapsed + jitter)
            time.sleep(sleep_time)

    def _periodic_flush(self):
        """后台定时 flush Kafka 缓冲区，避免 Worker 线程阻塞"""
        while self.running:
            time.sleep(5)
            if self.kafka_producer and hasattr(self.kafka_producer, 'flush'):
                try:
                    self.kafka_producer.flush()
                except Exception as e:
                    print(f"[{self.instance_id}] [PeriodicFlush] Kafka flush 异常: {e}")

    def active_drone_count(self) -> int:
        """当前所有 Worker 活跃无人机总数（simulation 模式）"""
        return sum(w.active_drone_count() for w in self.workers)

    def all_plans_ended(self) -> bool:
        """所有 Worker 的计划是否都已结束（simulation 模式）"""
        return all(w.all_plans_ended for w in self.workers)

    def start(self):
        """启动发送线程和 trace 消费线程"""
        if self.config.data_source_type == "scene_file":
            self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
            self.send_thread.start()
        elif self.config.data_source_type == "simulation":
            for i, worker in enumerate(self.workers):
                t = threading.Thread(target=self._worker_loop, args=(worker, i), daemon=True)
                self.worker_threads.append(t)
                t.start()
                time.sleep(0.05)  # 错开启动，避免同时抢 GIL
            # 启动后台 flush 线程
            self._flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
            self._flush_thread.start()
            print(f"[{self.instance_id}] {len(self.workers)} 个仿真 Worker 已启动")

        if self.config.consume_trace and self.kafka_consumer:
            self.trace_thread = threading.Thread(target=self._consume_trace, daemon=True)
            self.trace_thread.start()
        print(f"[{self.instance_id}] 端点已启动")

    def stop(self):
        self.running = False
        # 停止 scene_file 发送线程
        if hasattr(self, 'send_thread') and self.send_thread:
            self.send_thread.join(timeout=5)
        # 停止 simulation Worker 线程
        for i, t in enumerate(self.worker_threads):
            if t and t.is_alive():
                t.join(timeout=5)
                if t.is_alive():
                    print(f"[{self.instance_id}] Worker-{i} 线程未能在 5 秒内结束")
        # 停止后台 flush
        if getattr(self, '_flush_thread', None) and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=2)
        # 停止 trace 消费
        if hasattr(self, 'trace_thread') and self.trace_thread:
            self.trace_thread.join(timeout=5)
        # flush 剩余数据
        if self.kafka_producer and hasattr(self.kafka_producer, 'flush'):
            try:
                self.kafka_producer.flush()
            except Exception:
                pass
        if self.kafka_consumer:
            try:
                self.kafka_consumer.close()
            except Exception:
                pass
        print(f"[{self.instance_id}] 端点已停止")


# ==================== 进程入口 ====================

def run_endpoint_process(config_dict: Dict[str, Any], instance_id: str):
    """子进程入口函数"""
    config = EndpointConfig(**config_dict)
    sender = EndpointSender(config, instance_id)
    sender.start()
    try:
        if config.data_source_type == "simulation":
            # simulation 模式：每秒打印活跃数量汇总，支持自动停止
            while True:
                if sender.all_plans_ended():
                    print(f"[{instance_id}] 所有飞行计划已全部完成，自动停止...")
                    sender.stop()
                    break
                time.sleep(1)
                current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                active_count = sender.active_drone_count()
                if sender.kafka_producer and hasattr(sender.kafka_producer, 'get_and_reset_stats'):
                    stats = sender.kafka_producer.get_and_reset_stats()
                    print(f"{current_time} [{instance_id}] 活跃无人机: {active_count} | Kafka 成功:{stats['success']} 失败:{stats['failed']}")
                else:
                    print(f"{current_time} [{instance_id}] 活跃无人机: {active_count}")
        else:
            # scene_file 模式：简单循环，发送完自动停止由 _send_loop 处理
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sender.stop()


# ==================== 主入口 ====================

def load_endpoint_configs(config_path: str) -> List[EndpointConfig]:
    """从 YAML 配置加载端点列表

    配置层级（后者覆盖前者）：
        defaults -> cluster -> endpoint
    """
    config_manager = ConfigManager(config_path)
    full_config = config_manager.get_full_config()

    clusters = full_config.get('clusters', {})
    defaults = full_config.get('defaults', {})
    endpoints_raw = full_config.get('endpoints', [])

    endpoints = []
    for ep in endpoints_raw:
        # 跳过禁用的端点
        if not ep.get('enabled', True):
            continue

        # 合并配置：defaults -> cluster -> endpoint
        merged = dict(defaults)

        cluster_name = ep.get('cluster')
        if cluster_name and cluster_name in clusters:
            merged.update(clusters[cluster_name])
        elif cluster_name:
            print(f"警告: 端点 {ep.get('name')} 引用的集群 '{cluster_name}' 不存在")

        merged.update(ep)

        # 移除非 EndpointConfig 字段
        merged.pop('cluster', None)
        merged.pop('enabled', None)

        endpoints.append(EndpointConfig(**merged))

    return endpoints


def main():
    parser = argparse.ArgumentParser(description='高可用多点多组发送脚本')
    parser.add_argument('--config', '-c', type=str, required=True, help='YAML 配置文件路径')
    parser.add_argument('--dry-run', action='store_true', help='仅打印配置，不实际启动')
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"配置文件不存在: {args.config}")
        sys.exit(1)

    endpoints = load_endpoint_configs(args.config)
    if not endpoints:
        print("配置中未找到启用的端点（请检查 enabled 开关）")
        sys.exit(1)

    print("=" * 60)
    print("高可用多点多组发送脚本")
    print(f"配置文件: {args.config}")
    print(f"启用端点数量: {len(endpoints)}")
    for i, ep in enumerate(endpoints):
        print(f"  [{i+1}] {ep.name}: Kafka={ep.kafka_url}, Redis={ep.redis_host}:{ep.redis_port}, 模式={ep.data_source_type}")
    print("=" * 60)

    if args.dry_run:
        print("Dry-run 模式，仅打印配置，不启动进程")
        return

    # 启动子进程
    processes = []
    for i, ep in enumerate(endpoints):
        instance_id = f"{ep.name}_ep{i+1}"
        # dataclass 转 dict
        ep_dict = {
            'name': ep.name,
            'kafka_url': ep.kafka_url,
            'redis_host': ep.redis_host,
            'redis_port': ep.redis_port,
            'redis_password': ep.redis_password,
            'redis_db': ep.redis_db,
            'topic': ep.topic,
            'trace_topic': ep.trace_topic,
            'data_source_type': ep.data_source_type,
            'scene_file': ep.scene_file,
            'drone_count': ep.drone_count,
            'interval_ms': ep.interval_ms,
            'alive_mode': ep.alive_mode,
            'reconnect_interval': ep.reconnect_interval,
            'max_retry': ep.max_retry,
            'consume_trace': ep.consume_trace,
        }
        p = multiprocessing.Process(
            target=run_endpoint_process,
            args=(ep_dict, instance_id)
        )
        p.start()
        processes.append((instance_id, p))
        print(f"已启动端点进程: {instance_id} (PID: {p.pid})")

    # 主进程等待信号
    def signal_handler(signum, frame):
        print(f"\n收到信号 {signum}，正在停止所有端点进程...")
        for instance_id, p in processes:
            if p.is_alive():
                print(f"  终止 {instance_id} (PID: {p.pid})")
                p.terminate()
        for instance_id, p in processes:
            p.join(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("\n所有端点已启动，按 Ctrl+C 停止\n")
    try:
        while True:
            # 检查子进程状态
            all_alive = True
            for instance_id, p in processes:
                if not p.is_alive():
                    print(f"[{instance_id}] 子进程已退出 (exitcode: {p.exitcode})")
                    all_alive = False
            if not all_alive and not any(p.is_alive() for _, p in processes):
                print("所有端点进程均已退出")
                break
            time.sleep(2)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

    print("主程序退出")


if __name__ == '__main__':
    main()
