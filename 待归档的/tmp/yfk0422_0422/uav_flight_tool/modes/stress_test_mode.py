#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
压力测试模式
3000 架批量性能测试（原 main_multi2.py 功能）
P3: 仿真与发送解耦
P4: 使用 confluent-kafka (librdkafka)
"""

import sys
import time
import threading
import os
import copy
import random
from typing import List, Dict, Any
from queue import Queue, Empty

from modes.base_mode import BaseMode
from core.kafka_client import create_kafka_producer, create_kafka_consumer
from core.redis_client import RedisClient
from core.aircraft_name_generator import AircraftNameGenerator
from simulation.simulation_core import Simulator
import json


class ThreadSafeDataLog:
    """线程安全的数据日志收集器"""

    def __init__(self):
        self._lock = threading.Lock()
        self.kafka_data_log: List[Dict[str, Any]] = []
        self.redis_data_log: List[Dict[str, Any]] = []
        self.redis_trace_log: List[Dict[str, Any]] = []

    def extend_kafka(self, data: List[Dict[str, Any]]):
        with self._lock:
            self.kafka_data_log.extend(copy.deepcopy(data))

    def append_redis(self, item: Dict[str, Any]):
        with self._lock:
            self.redis_data_log.append(copy.deepcopy(item))

    def append_trace(self, item: Dict[str, Any]):
        with self._lock:
            self.redis_trace_log.append(copy.deepcopy(item))

    def get_logs(self):
        with self._lock:
            return (
                copy.deepcopy(self.kafka_data_log),
                copy.deepcopy(self.redis_data_log),
                copy.deepcopy(self.redis_trace_log),
            )


class KafkaSenderThread(threading.Thread):
    """P3: Kafka 发送线程"""

    def __init__(self, sender_id: int, kafka_producer, queue: Queue, topic: str):
        super().__init__(daemon=True)
        self.sender_id = sender_id
        self.kafka_producer = kafka_producer
        self.queue = queue
        self.topic = topic
        self.running = True

    def run(self):
        print(f"[Sender-{self.sender_id}] 启动")
        while self.running:
            batch = []
            deadline = time.time() + 0.05
            while time.time() < deadline and len(batch) < 1000:
                try:
                    worker_data = self.queue.get(timeout=0.01)
                    if isinstance(worker_data, list):
                        batch.extend(worker_data)
                    else:
                        batch.append(worker_data)
                except Empty:
                    break
                except Exception:
                    break

            if batch:
                self.kafka_producer.send_bulk(batch, self.topic)

            self.kafka_producer.poll(0)

        print(f"[Sender-{self.sender_id}] 正在退出，flush 剩余数据...")
        self.kafka_producer.flush()
        print(f"[Sender-{self.sender_id}] 已退出")


class WorkerDataSource:
    """P3: 单个工作线程的数据源（只做仿真，不直接发送）"""

    def __init__(
        self,
        worker_id: int,
        target_drones: int,
        sender_queue: Queue,
        redis_client: RedisClient,
        shared_log: ThreadSafeDataLog,
        timestamp_offset_ms: int,
        redis_flight_plan_key: str,
        enable_worker_log: bool,
        name_gen: AircraftNameGenerator = None,
    ):
        self.worker_id = worker_id
        self.target_drones = target_drones
        self.sender_queue = sender_queue
        self.redis_client = redis_client
        self.shared_log = shared_log
        self.timestamp_offset_ms = timestamp_offset_ms
        self.redis_flight_plan_key = redis_flight_plan_key
        self.enable_worker_log = enable_worker_log
        self.name_gen = name_gen

        self.init_plan = False
        self.all_plans_ended = False
        self.active_plans = []
        self.simulator = Simulator()

    def _plan_to_route_data(self, plan) -> Dict[str, Any]:
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
        try:
            route_data = self._plan_to_route_data(plan)
            uid = route_data["uniqueProductIdentificationCode"]
            self.shared_log.append_redis({"key": uid, "value": copy.deepcopy(route_data)})
            result = self.redis_client.hset(self.redis_flight_plan_key, uid, json.dumps(route_data, ensure_ascii=False))
            if result and self.enable_worker_log:
                print(f"[Worker-{self.worker_id}] 向Redis插入无人机航线数据成功: {uid}")
            return result
        except Exception as e:
            print(f"[Worker-{self.worker_id}] 向Redis插入无人机航线数据失败:{e}")

    def _maintain_traffic(self):
        finished_ids = [uid for uid, agent in self.simulator.agents.items() if agent.state == 5]
        for uid in finished_ids:
            del self.simulator.agents[uid]

        active_uids = set(self.simulator.agents.keys())
        self.active_plans = [p for p in self.active_plans if p.aircraft.uid.decode() in active_uids]

        needed = self.target_drones - len(self.active_plans)
        if needed <= 0:
            return
        max_generate_per_step = 5
        for _ in range(min(needed, max_generate_per_step)):
            new_plan = self.simulator.generate_plan()
            self.add_redis_plan(new_plan)
            self.active_plans.append(new_plan)

    def _telemetry_to_kafka_message(self, t) -> Dict[str, Any]:
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
                uav_vid = kafka_data["uniqueProductIdentificationCode"]
                if t.operatingStatus != 2 and self.enable_worker_log:
                    print(f'[Worker-{self.worker_id}] simulator uav:{uav_vid} send operating status={t.operatingStatus}, means stop fly')
                data.append(kafka_data)

            if data:
                self.shared_log.extend_kafka(data)
                try:
                    self.sender_queue.put(data, timeout=1.0)
                except Exception as e:
                    print(f"[Worker-{self.worker_id}] 发送队列满，数据丢弃: {e}")
        except Exception as e:
            print(f"[Worker-{self.worker_id}] step 失败:{e}")


class StressTestMode(BaseMode):
    """压力测试模式"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.stress_cfg = config.get('stress_test_mode', {})
        self.kafka_cfg = config.get('kafka', {})
        self.redis_cfg = config.get('redis', {})

        self.num_workers = self.stress_cfg.get('num_workers', 10)
        self.target_drones = self.stress_cfg.get('target_drones', 3000)
        self.enable_worker_log = self.stress_cfg.get('enable_worker_log', False)
        self.timestamp_offset_ms = self.stress_cfg.get('timestamp_offset_ms', -1000)
        self.sender_threads_count = self.stress_cfg.get('sender_threads', 2)
        self.sender_queue_size = self.stress_cfg.get('sender_queue_size', 10000)
        self.enable_trace_consumer = self.stress_cfg.get('enable_trace_consumer', True)

        self.running = False
        self.shared_log = ThreadSafeDataLog()
        self.redis_client = None
        self.kafka_consumer = None
        self.sender_queue = None
        self.sender_threads: List[KafkaSenderThread] = []
        self.workers: List[WorkerDataSource] = []
        self.worker_threads: List[threading.Thread] = []
        self.trace_consumer_thread = None

        self.name_gen = AircraftNameGenerator(config.get('aircraft_name', {}))

    def start(self):
        if self.running:
            print("压力测试模式已在运行")
            return

        print('=' * 60)
        print(f"压力测试模式启动（解耦 + librdkafka）")
        print(f"工作线程数: {self.num_workers}")
        print(f"发送线程数: {self.sender_threads_count}")
        print(f"总活跃无人机目标: {self.target_drones}")
        print('=' * 60)

        self.running = True

        # 连接 Redis
        self.redis_client = RedisClient(
            self.redis_cfg.get('host', '127.0.0.1'),
            self.redis_cfg.get('port', 6379),
            self.redis_cfg.get('password', ''),
            self.redis_cfg.get('db', 0)
        )

        # 连接 Kafka Consumer (trace)
        if self.enable_trace_consumer:
            self.kafka_consumer = create_kafka_consumer(
                self.kafka_cfg.get('url', 'localhost:9092'),
                f"utm_stress_group_{os.getpid()}",
                consume_from_latest_on_start=True,
            )
            self.kafka_consumer.subscribe([self.kafka_cfg.get('consumer_topic', 'uav_runtime_trace')])

        # P3: 创建发送队列
        self.sender_queue = Queue(maxsize=self.sender_queue_size)

        # P3 + P4: 创建 Sender 线程
        client_type = self.kafka_cfg.get('client_type', 'kafka-python')
        topic = self.kafka_cfg.get('topic', 'uav_runtime_data')
        for i in range(self.sender_threads_count):
            kafka_producer = create_kafka_producer(
                self.kafka_cfg.get('url', 'localhost:9092'),
                client_type,
                verbose=self.enable_worker_log
            )
            t = KafkaSenderThread(
                sender_id=i,
                kafka_producer=kafka_producer,
                queue=self.sender_queue,
                topic=topic,
            )
            self.sender_threads.append(t)
            t.start()

        # 计算每个线程的无人机数
        drones_per_worker = self.target_drones // self.num_workers
        drones_remainder = self.target_drones % self.num_workers

        def get_worker_target(worker_index: int) -> int:
            base = drones_per_worker
            if worker_index < drones_remainder:
                base += 1
            return base

        # 创建工作线程
        for i in range(self.num_workers):
            target = get_worker_target(i)
            worker = WorkerDataSource(
                worker_id=i,
                target_drones=target,
                sender_queue=self.sender_queue,
                redis_client=self.redis_client,
                shared_log=self.shared_log,
                timestamp_offset_ms=self.timestamp_offset_ms,
                redis_flight_plan_key=self.redis_cfg.get('flight_plan_key', 'BIZ_DATA:UAV_ROUTE'),
                enable_worker_log=self.enable_worker_log,
                name_gen=self.name_gen,
            )
            self.workers.append(worker)
            t = threading.Thread(target=self._worker_loop, args=(worker, i), daemon=True)
            self.worker_threads.append(t)
            t.start()
            time.sleep(0.05)
            print(f"[StressTestMode] Worker-{i} 已启动，目标无人机数: {target}")

        # 启动 trace 消费线程
        if self.enable_trace_consumer:
            self.trace_consumer_thread = threading.Thread(target=self._consume_trace, daemon=True)
            self.trace_consumer_thread.start()

    def stop(self):
        self.running = False

        for i, t in enumerate(self.worker_threads):
            if t and t.is_alive():
                t.join(timeout=5)
                if t.is_alive():
                    print(f"[StressTestMode] Worker-{i} 线程未能在 5 秒内结束")

        for i, t in enumerate(self.sender_threads):
            t.running = False
            if t.is_alive():
                t.join(timeout=5)
                if t.is_alive():
                    print(f"[StressTestMode] Sender-{i} 线程未能在 5 秒内结束")

        if self.trace_consumer_thread and self.trace_consumer_thread.is_alive():
            self.trace_consumer_thread.join(timeout=5)

        try:
            if self.kafka_consumer:
                self.kafka_consumer.close()
        except Exception:
            pass

        self._save_logs()
        print("压力测试模式已停止")

    def is_running(self) -> bool:
        return self.running

    def get_status(self) -> Dict[str, Any]:
        return {
            'mode': 'stress_test',
            'running': self.running,
            'active_drones': self.active_drone_count(),
            'target_drones': self.target_drones,
            'num_workers': self.num_workers,
            'sender_threads': self.sender_threads_count,
            'kafka_stats': self.get_kafka_stats(),
        }

    def active_drone_count(self) -> int:
        return sum(len(w.active_plans) for w in self.workers)

    def all_plans_ended(self) -> bool:
        return all(w.all_plans_ended for w in self.workers)

    def get_kafka_stats(self) -> Dict[str, int]:
        total = {'success': 0, 'failed': 0, 'total': 0}
        for t in self.sender_threads:
            stats = t.kafka_producer.get_and_reset_stats()
            total['success'] += stats['success']
            total['failed'] += stats['failed']
            total['total'] += stats['total']
        return total

    def _worker_loop(self, worker: WorkerDataSource, worker_index: int):
        initial_jitter = worker_index * 0.05
        time.sleep(initial_jitter)
        while self.running:
            t0 = time.perf_counter()
            worker.step()
            elapsed = time.perf_counter() - t0
            jitter = random.uniform(-0.03, 0.03)
            sleep_time = max(0.0, 1.0 - elapsed + jitter)
            time.sleep(sleep_time)

    def _consume_trace(self):
        while self.running:
            try:
                messages = self.kafka_consumer.poll(timeout_ms=1000)
                for msg in messages:
                    if isinstance(msg, dict):
                        redis_key = msg.get("redisKey") or msg.get("redis_key")
                        if redis_key:
                            value = self.redis_client.get_value_by_key(redis_key)
                            if value is not None:
                                active_uids = set()
                                for w in self.workers:
                                    active_uids.update(w.simulator.agents.keys())

                                if isinstance(value, list):
                                    value = [item for item in value if item.get('uniqueProductIdentificationCode') in active_uids]
                                self.shared_log.append_trace({
                                    "key": redis_key,
                                    "value": value,
                                })
            except Exception as e:
                print(f"消费 trace 异常: {e}")
            time.sleep(0.1)

    def _save_logs(self):
        json_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "json")
        try:
            os.makedirs(json_dir, exist_ok=True)
        except Exception:
            pass

        kafka_log, redis_log, trace_log = self.shared_log.get_logs()

        entries = [
            (os.path.join(json_dir, "kafka_data.json"), kafka_log, "Kafka"),
            (os.path.join(json_dir, "redis_route.json"), redis_log, "Redis"),
            (os.path.join(json_dir, "redis_trace.json"), trace_log, "redis_trace"),
        ]
        for path, log_list, name in entries:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(log_list, f, ensure_ascii=False, indent=2)
                print(f"已保存{name}数据到: {path} (共 {len(log_list)} 条)")
            except Exception as e:
                print(f"保存{name}数据到 JSON 失败: {e}")
