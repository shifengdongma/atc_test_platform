# -*- coding: utf-8 -*-
import sys
import time
import threading
import os
import copy
import subprocess
from typing import List, Dict, Any, Optional

# 将项目根目录加入 path，便于从 tools 下直接运行
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from core.kafka_proc import KafkaConsumerClient, KafkaProducerClient
import json
from core.redis_client import RedisClient
import env as _env
from env import redis_ip, redis_port, redis_password, kafka_url

# mock 目录与 JSON 路径（相对项目根目录）
MOCK_DIR = os.path.join(_root, "data", "mock")
REDIS_ROUTE_JSON_PATH = os.path.join(MOCK_DIR, "redis_route.json")
KAFKA_DATA_JSON_PATH = os.path.join(MOCK_DIR, "kafka_data.json")
REDIS_TRACE_JSON_PATH = os.path.join(MOCK_DIR, "redis_trace.json")

kafka_uav_data_topic = 'uav_runtime_data'
uav_runtime_trace_topic = 'uav_runtime_trace'
redis_flight_plan_key = "BIZ_DATA:UAV_ROUTE"


class DataSource:
    """数据获取模块：从 redis_route.json 写入 Redis，从 kafka_data.json 按秒发送到 Kafka，结束时生成 redis_trace.json"""

    def __init__(self, kafka_url: Optional[str] = None):
        _kafka = kafka_url or getattr(_env, 'kafka_url', 'localhost:9092')
        self.redis_client = RedisClient(redis_ip, redis_port, redis_password)
        self.kafka_producer = KafkaProducerClient(
            _kafka, bootstrap_servers_mirror=getattr(_env, "kafka_url2", None)
        )
        # 每个进程使用独立的 group_id，多实例同时运行时各自都能收到全部消息（否则同组会瓜分分区，后启动的收不到）
        # consume_from_latest_on_start=True：启动时跳过历史积压，只消费连接之后产生的新消息
        self.kafka_consumer = KafkaConsumerClient(
            bootstrap_servers=_kafka,
            group_id=f"utm_demo_group_{os.getpid()}",
            consume_from_latest_on_start=True,
        )
        self.kafka_consumer.subscribe([uav_runtime_trace_topic])
        self.redis_trace_log: List[Dict[str, Any]] = []

        # 读取预生成的 kafka_data.json，并提取所有无人机 uid 作为合法列表（监听 Kafka 前）
        self.kafka_data_list: List[Dict[str, Any]] = []
        self.allowed_uav_uids: List[str] = []  # 多个无人机 uid 数组，消息的 uniqueProductIdentificationCode 在此数组中即合法
        self._allowed_uav_uids_set: set = set()  # 同上，set 便于 O(1) 判断
        self._uid_record_indices: Dict[str, List[int]] = {}  # uid -> 在 kafka_data_list 中该 uid 且 active 的条目的下标列表
        self._uid_cursor: Dict[str, int] = {}  # uid -> 当前取到第几条（用于按 uid 各取一条）
        self.data_exhausted = False  # 当本秒待发送条数为 0 时置为 True，用于主循环自动停止
        self._load_kafka_data()
        # 读取 redis_route.json 并写入 Redis
        self._load_redis_route()

    def __del__(self):
        if hasattr(self, 'kafka_consumer') and self.kafka_consumer:
            try:
                self.kafka_consumer.close()
            except Exception:
                pass

    def _load_redis_route(self) -> None:
        """从 redis_route.json 读取并全部写入 Redis。上传前将每个飞行计划的 planTakeoffTime 改为当前时间，planLandTime 延长相同时间差。"""
        try:
            with open(REDIS_ROUTE_JSON_PATH, 'r', encoding='utf-8') as f:
                route_list = json.load(f)
            now = time.time()
            for item in route_list:
                key = item.get("key")
                value = item.get("value")
                if key is None or value is None:
                    continue
                # 上传前：将每个飞行计划的 planTakeoffTime 改为当前时间，planLandTime 延长相同时间差
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
                json_data = json.dumps(value, ensure_ascii=False)
                self.redis_client.hset(redis_flight_plan_key, key, json_data)
                print(f"向Redis插入无人机航线数据成功: {key}，起飞时间为 {now}")
        except Exception as e:
            print(f"从 redis_route.json 读取并写入 Redis 失败: {e}")

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

    def get_flight_plans_simulator(self) -> None:
        """若有 n 个飞行计划，则每秒发送 n 条：从 kafka_data.json 按 uid 各取一条，时间戳改为当前时间后发送到 Kafka。
        单个飞行计划游标到达最后一条后，后续不再发送该飞行计划的模拟数据。
        当本秒待发送条数为 0 时设置 data_exhausted，主循环将自动停止。"""
        if not self.kafka_data_list or not self.allowed_uav_uids:
            self.data_exhausted = True
            return
        try:
            records_to_send = []
            now_ts = int(time.time())*1000
            for uid in self.allowed_uav_uids:
                indices = self._uid_record_indices.get(uid)
                if not indices or self._uid_cursor[uid] >= len(indices):
                    continue
                pos = self._uid_cursor[uid]
                self._uid_cursor[uid] += 1
                idx = indices[pos]
                telemetry_finished_for_uid = self._uid_cursor[uid] >= len(indices)
                record = self.kafka_data_list[idx]
                if record.get("active") == 0:
                    print(f"跳过 active==0 的数据，uid={uid}, idx={idx}")
                    if telemetry_finished_for_uid:
                        print(f"无人机 {uid} 遥测已结束")
                    continue
                record["timestamp"] = now_ts
                records_to_send.append(record)
                if telemetry_finished_for_uid:
                    print(f"无人机 {uid} 遥测已结束")
            if records_to_send:
                self.kafka_producer.send_bulk(records_to_send, kafka_uav_data_topic)
            else:
                # 仅当所有 uid 游标均到末尾时才标记耗尽；本秒全为 active==0 跳过时不停止
                all_at_end = all(
                    self._uid_cursor[uid] >= len(self._uid_record_indices.get(uid, []))
                    for uid in self.allowed_uav_uids
                )
                if all_at_end:
                    self.data_exhausted = True
        except Exception as e:
            print(f"get_flight_plans_simulator 失败: {e}")

    def _save_kafka_data(self) -> None:
        """将内存中已更新的 kafka_data_list（含 timestamp）同步回 kafka_data.json"""
        try:
            with open(KAFKA_DATA_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.kafka_data_list, f, ensure_ascii=False, indent=2)
            print(f"已同步更新后的 timestamp 到: {KAFKA_DATA_JSON_PATH} (共 {len(self.kafka_data_list)} 条)")
        except Exception as e:
            print(f"保存 kafka_data.json 失败: {e}")

    def save_logs_to_files(self) -> None:
        """结束时生成 redis_trace.json，并同步 kafka_data.json 中的 timestamp"""
        os.makedirs(MOCK_DIR, exist_ok=True)
        try:
            with open(REDIS_TRACE_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.redis_trace_log, f, ensure_ascii=False, indent=2)
            print(f"已保存 uav_runtime_trace 按 redisKey 查出的数据到: {REDIS_TRACE_JSON_PATH} (共 {len(self.redis_trace_log)} 条)")
        except Exception as e:
            print(f"保存 redis_trace 数据到 JSON 失败: {e}")
        self._save_kafka_data()


class DataFlow:
    """主流程：启动数据源、仿真线程与 trace 消费线程，结束时落盘并调用准确度脚本。"""

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
        """消费 uav_runtime_trace：按 redisKey 从 Redis 查出数据并记录，结束时写入 redis_trace.json"""
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
                                self.data_source.redis_trace_log.append({
                                    "key": redis_key,
                                    "value": filtered_value,
                                })
                                unique_codes = list({p.get("uniqueProductIdentificationCode") for p in filtered_value})
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
            self.trace_consumer_thread.join(timeout=5)  # 等待 Kafka 消费线程结束，避免与 save_logs_to_files 竞态
        self.data_source.kafka_producer.close()
        self.data_source.save_logs_to_files()
        # 生成文件后调用航迹准确度计算脚本（使用 mock 目录下的 kafka_data.json / redis_trace.json）
        _accuracy_script = os.path.join(_root, "tools", "trajectory_accuracy.py")
        if os.path.isfile(_accuracy_script):
            print("正在调用 trajectory_accuracy.py 计算航迹准确度...")
            try:
                subprocess.run(
                    [sys.executable, _accuracy_script],
                    cwd=_root,
                    check=False,
                )
            except Exception as e:
                print(f"调用 trajectory_accuracy.py 失败: {e}")
        else:
            print(f"未找到脚本: {_accuracy_script}")
        print("程序已停止")


if __name__ == '__main__':
    print('main begin')
    flow = DataFlow()
    try:
        while True:
            if flow.data_source.data_exhausted:
                print("飞行计划已全部完成，自动停止...")
                flow.stop()
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("收到停止信号，正在停止程序...")
        flow.stop()
    print('app run exit')
