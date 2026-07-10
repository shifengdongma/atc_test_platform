# -*- coding: utf-8 -*-
"""参考 run_kafka.py：Mock 注入遥测与 trace 消费；每架机飞行计划跑完一轮立即重飞并刷新该机 Redis，不退出。"""
import sys
import time
import threading
import os
import copy
from typing import List, Dict, Any

# 将项目根目录加入 path，便于从 tools 下直接运行
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from kafka_proc import KafkaConsumerClient, KafkaProducerClient
import json
from redis_client import RedisClient
from env import redis_ip, redis_port, redis_password, kafka_url
import env as _env

# mock 目录与 JSON 路径（相对项目根目录）
MOCK_DIR = os.path.join(_root, "..", "data", "mock")
REDIS_ROUTE_JSON_PATH = os.path.join(MOCK_DIR, "redis_route.json")
KAFKA_DATA_JSON_PATH = os.path.join(MOCK_DIR, "kafka_data.json")
kafka_uav_data_topic = 'uav_runtime_data'
uav_runtime_trace_topic = 'uav_runtime_trace'
redis_flight_plan_key = "BIZ_DATA:UAV_ROUTE"


class DataSource:
    """数据获取模块：从 redis_route.json 写入 Redis，从 kafka_data.json 按秒发送到 Kafka；每架机遥测跑完一轮即单独从头循环并刷新该机 Redis 航线。"""

    def __init__(self):
        self.redis_client = RedisClient(redis_ip, redis_port, redis_password)
        self.kafka_producer = KafkaProducerClient(
            kafka_url, bootstrap_servers_mirror=getattr(_env, "kafka_url2", None)
        )
        # 每个进程使用独立的 group_id，多实例同时运行时各自都能收到全部消息（否则同组会瓜分分区，后启动的收不到）
        # consume_from_latest_on_start=True：启动时跳过历史积压，只消费连接之后产生的新消息
        self.kafka_consumer = KafkaConsumerClient(
            bootstrap_servers=kafka_url,
            group_id=f"utm_demo_group_{os.getpid()}",
            consume_from_latest_on_start=True,
        )
        self.kafka_consumer.subscribe([uav_runtime_trace_topic])

        # 读取预生成的 kafka_data.json，并提取所有无人机 uid 作为合法列表（监听 Kafka 前）
        self.kafka_data_list: List[Dict[str, Any]] = []
        self.allowed_uav_uids: List[str] = []  # 多个无人机 uid 数组，消息的 uniqueProductIdentificationCode 在此数组中即合法
        self._allowed_uav_uids_set: set = set()  # 同上，set 便于 O(1) 判断
        self._uid_record_indices: Dict[str, List[int]] = {}  # uid -> 在 kafka_data_list 中该 uid 且 active 的条目的下标列表
        self._uid_cursor: Dict[str, int] = {}  # uid -> 当前取到第几条（用于按 uid 各取一条）
        self.data_exhausted = False  # 无 kafka 数据时为 True；有数据时每架机独立循环，不再全局耗尽
        self._route_list_source: List[Dict[str, Any]] = []  # redis_route.json 深拷贝，供单机重飞时按原始计划重算时间
        self._load_kafka_data()
        # 读取 redis_route.json 并写入 Redis
        self._load_redis_route()

    def __del__(self):
        if hasattr(self, 'kafka_consumer') and self.kafka_consumer:
            try:
                self.kafka_consumer.close()
            except Exception:
                pass

    def _shift_plan_times_to_now(self, value: Dict[str, Any]) -> float:
        """将 value 内飞行计划的起降时间平移到「当前时刻」为起飞，保持原时长；返回当前时间戳。"""
        now = time.time()
        flight_plan_list = value.get("flightPlanList") or []
        for plan in flight_plan_list:
            try:
                takeoff = plan.get("planTakeoffTime")
                land = plan.get("planLandTime")
                if takeoff is not None and land is not None:
                    diff = now - takeoff
                    plan["planTakeoffTime"] = now
                    plan["planLandTime"] = land + diff
            except (TypeError, ValueError):
                pass
        return now

    def _write_route_value_to_redis(self, key: str, value: Dict[str, Any]) -> None:
        json_data = json.dumps(value, ensure_ascii=False)
        self.redis_client.hset(redis_flight_plan_key, key, json_data)

    def _load_redis_route(self) -> None:
        """从 redis_route.json 读取并全部写入 Redis。上传前将每个飞行计划的 planTakeoffTime 改为当前时间，planLandTime 延长相同时间差。"""
        try:
            with open(REDIS_ROUTE_JSON_PATH, 'r', encoding='utf-8') as f:
                route_list = json.load(f)
            self._route_list_source = copy.deepcopy(route_list)
            for item in route_list:
                key = item.get("key")
                value = item.get("value")
                if key is None or value is None:
                    continue
                val = copy.deepcopy(value)
                now = self._shift_plan_times_to_now(val)
                self._write_route_value_to_redis(key, val)
                print(f"向Redis插入无人机航线数据成功: {key}，起飞时间为 {now}")
        except Exception as e:
            print(f"从 redis_route.json 读取并写入 Redis 失败: {e}")

    def _refresh_single_route_redis(self, uid: str) -> None:
        """某架机遥测跑完一轮后：按原始 redis_route 重算起降时间并仅更新该机 Redis 航线。"""
        if not self._route_list_source:
            print(f"无航线缓存，跳过单机 Redis 刷新: {uid}")
            return
        for item in self._route_list_source:
            if item.get("key") != uid:
                continue
            value = item.get("value")
            if value is None:
                return
            val = copy.deepcopy(value)
            now = self._shift_plan_times_to_now(val)
            self._write_route_value_to_redis(uid, val)
            print(f"单机飞行计划已立即重飞: {uid}，起飞时间已更新为 {now}")
            return

    def _load_kafka_data(self) -> None:
        """从 kafka_data.json 读取预生成数据，按 uid 建立 active 条目的下标列表，并提取合法 uid 数组"""
        try:
            with open(KAFKA_DATA_JSON_PATH, 'r', encoding='utf-8') as f:
                self.kafka_data_list = json.load(f)
            # 按 uid 收集在 kafka_data_list 中的下标（含 active==0，发送时再跳过）
            self._uid_record_indices = {}
            for i, item in enumerate(self.kafka_data_list):
                uid_val = item.get("uniqueProductIdentificationCode")
                if not uid_val:
                    continue
                if uid_val not in self._uid_record_indices:
                    self._uid_record_indices[uid_val] = []
                self._uid_record_indices[uid_val].append(i)
            self.allowed_uav_uids = list(self._uid_record_indices)
            self._allowed_uav_uids_set = set(self.allowed_uav_uids)
            self._uid_cursor = {uid: 0 for uid in self.allowed_uav_uids}
            print(f"已加载 kafka_data.json，共 {len(self.kafka_data_list)} 条，合法 uid 数组: {self.allowed_uav_uids}")
        except Exception as e:
            print(f"读取 kafka_data.json 失败: {e}")

    def reset_for_next_round(self) -> None:
        """无 kafka 数据等异常时可用：重置各 uid 游标，重新按当前时间写入全部 Redis 航线。"""
        self._uid_cursor = {uid: 0 for uid in self.allowed_uav_uids}
        self.data_exhausted = False
        self._load_redis_route()
        print("本轮已完成，已重置并开始新一轮仿真（持续循环，Ctrl+C 退出）")

    def get_flight_plans_simulator(self) -> None:
        """若有 n 个飞行计划，则每秒发送 n 条：从 kafka_data.json 按 uid 各取一条，时间戳改为当前时间后发送到 Kafka。
        单个 uid 的游标走完一轮后立即归零并按原始航线重算起降时间写入 Redis，再从头发送，不等待其他飞机。"""
        if not self.kafka_data_list or not self.allowed_uav_uids:
            self.data_exhausted = True
            return
        try:
            records_to_send = []
            now_ts = int(time.time())*1000
            for uid in self.allowed_uav_uids:
                indices = self._uid_record_indices.get(uid)
                if not indices:
                    continue
                if self._uid_cursor[uid] >= len(indices):
                    self._uid_cursor[uid] = 0
                    print(f"无人机 {uid} 本轮遥测已发完（模拟完成降落），正刷新 Redis 航线并重新起飞")
                    self._refresh_single_route_redis(uid)
                pos = self._uid_cursor[uid]
                self._uid_cursor[uid] += 1
                idx = indices[pos]
                record = self.kafka_data_list[idx]
                if record.get("active") == 0:
                    print(f"跳过 active==0 的数据，uid={uid}, idx={idx}")
                    continue
                record["timestamp"] = now_ts
                records_to_send.append(record)
            if records_to_send:
                self.kafka_producer.send_bulk(records_to_send, kafka_uav_data_topic)
        except Exception as e:
            print(f"get_flight_plans_simulator 失败: {e}")

class DataFlow:
    """主流程：启动数据源、仿真线程与 trace 消费线程。"""

    def __init__(self):
        self.data_source = DataSource()
        self.running = True
        self.thread = threading.Thread(target=self._simulation)
        self.thread.daemon = True
        self.thread.start()

        self.trace_consumer_thread = threading.Thread(target=self._consume_uav_runtime_trace)
        self.trace_consumer_thread.daemon = True
        self.trace_consumer_thread.start()

    def _consume_uav_runtime_trace(self):
        """消费 uav_runtime_trace：按 redisKey 从 Redis 查出数据并打印。"""
        while self.running:
            try:
                messages = self.data_source.kafka_consumer.poll(timeout_ms=500)
                for msg in messages:
                    if isinstance(msg, dict):
                        redis_key = msg.get("redisKey") or msg.get("redis_key")
                        if redis_key:
                            value = self.data_source.redis_client.get_value_by_key(redis_key)
                            if value is not None:
                                allowed = self.data_source._allowed_uav_uids_set
                                # value 中可能有多架无人机预测数据，只保留合法 uid 的条目
                                filtered_value = [
                                    copy.deepcopy(p) for p in value
                                    if p.get("uniqueProductIdentificationCode") in allowed
                                ]
                                if not filtered_value:
                                    continue
                                print(f"\033[32m[uav_runtime_trace] {int(msg.get('timestamp'))} 收到 {len(filtered_value)} 条\033[0m")
            except Exception as e:
                print(f"消费 uav_runtime_trace 异常: {e}")
            time.sleep(0.05)

    def _simulation(self):
        """严格每秒调用一次 get_flight_plans_simulator（发送一条）"""
        while self.running:
            t0 = time.perf_counter()
            self.data_source.get_flight_plans_simulator()
            elapsed = time.perf_counter() - t0
            sleep_time = max(0, 1.0 - elapsed)
            time.sleep(sleep_time)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)  # 等待模拟线程结束，最多5秒
        if self.trace_consumer_thread and self.trace_consumer_thread.is_alive():
            self.trace_consumer_thread.join(timeout=5)  # 等待 Kafka 消费线程结束
        self.data_source.kafka_producer.close()
        print("run_kafka_alive 已停止")


if __name__ == '__main__':
    print('main begin (alive 模式：每架机飞完一轮立即重飞并刷新该机 Redis 航线，Ctrl+C 退出)')
    flow = DataFlow()
    try:
        while True:
            if flow.data_source.data_exhausted:
                flow.data_source.reset_for_next_round()
            time.sleep(1)
    except KeyboardInterrupt:
        print("收到停止信号，正在停止程序...")
        flow.stop()
