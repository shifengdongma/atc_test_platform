#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上图时间指标获取.py

端到端上图时间测试脚本：
1. 发射 mock/kafka_data_scene_bj_tsjk.json 数据到 Kafka
2. 消费 uav_runtime_data 记录 Kafka 接收时间
3. 连接 WebSocket 接收 flightTrack 记录 WS 接收时间
4. 计算并输出上图时间指标
5. 输出结果计算方式：
        上图-A(ms)	WS-A收到时间 - Kafka-A时间	： 数据从 Kafka 到 WS 的延迟
        上图2-A(ms)	WS-A收到时间 - Kafka-A时间	： 端到端总延迟（含 Kafka 入队）
        上图-B(ms)	WS-B收到时间 - Kafka-B时间	： 数据从 Kafka 到 WS 的延迟
        上图2-B(ms)	WS-B收到时间 - Kafka-B时间	： 端到端总延迟（含 Kafka 入队）
用法：
    python 上图时间指标获取.py
"""

import os
import sys
import json
import time
import bisect
import threading
import subprocess
from datetime import datetime
from typing import Dict, Tuple, List, Any
import redis

# ========== 路径配置 ==========
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
TOOLS_DIR = os.path.join(ENGINE_DIR, "tools")

sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, TOOLS_DIR)

# ========== 导入项目模块 ==========
from kafka_proc import KafkaProducerClient, KafkaConsumerClient
from ws_client_check import ReceiverWsStats
import ha_env

# ========== 常量配置 ==========
SCENE_FILE = os.path.join(ENGINE_DIR, "mock", "kafka_data_scene_bj_tsjk.json")
GENERATOR_PY = os.path.join(TOOLS_DIR, "航空器上图时间指标数据生成.py")
KAFKA_TOPIC = "uav_runtime_data"
WS_URL_A = f"wss://{ha_env.atc_a}/la-atc-ws-backend/ws/stomp"
WS_URL_B = f"wss://{ha_env.atc_b}/la-atc-ws-backend/ws/stomp"
WS_DESTINATION = "/flightTrack/SEAT0001"
LOG_DIR = os.path.join(SCRIPT_DIR, "log")
EMIT_INTERVAL_SEC = 1.0    # 轮次发射间隔（秒），与场景文件采样间隔一致


# ========== Redis 航线写入 ==========
def _build_route_data(records: List[dict]) -> dict:
    """根据 UAV 遥测记录生成航线字典（兼容 SceneEmitter 格式）"""
    if len(records) < 2:
        return None
    route_list = []
    for i in range(len(records) - 1):
        p0 = records[i]
        p1 = records[i + 1]
        route_list.append({
            "sequence": i,
            "type": 2,
            "segmentStartLon": p0.get("longitude", 0),
            "segmentStartLat": p0.get("latitude", 0),
            "segmentEndLon": p1.get("longitude", 0),
            "segmentEndLat": p1.get("latitude", 0),
            "segmentStartHeight": p0.get("geodeticAltitude", 0),
            "segmentEndHeight": p1.get("geodeticAltitude", 0),
            "segmentProtectHeight": 0,
            "segmentProtectHeightType": 0,
            "segmentWidth": 0,
        })
    start_ts = records[0].get("timestamp", int(time.time()))
    end_ts = records[-1].get("timestamp", start_ts + 600)
    if start_ts > 1e10:
        start_ts = start_ts / 1000.0
    if end_ts > 1e10:
        end_ts = end_ts / 1000.0
    uid = records[0].get("uniqueProductIdentificationCode", "")
    return {
        "uniqueProductIdentificationCode": uid,
        "flightPlanList": [
            {
                "flightPlanId": 1,
                "planTakeoffTime": start_ts,
                "planLandTime": end_ts,
                "flightTaskId": 1,
                "flightTaskName": "test",
                "routeList": route_list,
            }
        ],
    }


def _write_redis_routes(scene_file: str):
    """读取场景文件并写入 Redis 航线数据（A/B 双集群）"""
    with open(scene_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    # 按 uid 分组并排序
    uav_records: Dict[str, List[dict]] = {}
    for r in records:
        uid = r.get("uniqueProductIdentificationCode")
        if uid:
            uav_records.setdefault(uid, []).append(r)
    for uid in uav_records:
        uav_records[uid].sort(key=lambda x: x.get("timestamp", 0))

    route_data_map: Dict[str, str] = {}
    for uid, recs in uav_records.items():
        route = _build_route_data(recs)
        if route:
            route_data_map[uid] = json.dumps(route, ensure_ascii=False)

    if not route_data_map:
        print("[Redis] 无可写入的航线数据")
        return

    # 连接 A/B Redis 并写入
    for label, ip, port, pwd in [
        ("A", ha_env.redis_ip_a, ha_env.redis_port_a, ha_env.redis_password_a),
        ("B", ha_env.redis_ip_b, ha_env.redis_port_b, ha_env.redis_password_b),
    ]:
        try:
            client = redis.Redis(
                host=ip, port=int(port), password=pwd,
                db=0, decode_responses=True,
            )
            client.ping()
        except Exception as e:
            print(f"[Redis-{label}] 连接失败: {e}")
            continue

        pipeline = client.pipeline(transaction=False)
        current_batch: List[str] = []
        for uid, route_json in route_data_map.items():
            pipeline.hset("BIZ_DATA:UAV_ROUTE", uid, route_json)
            current_batch.append(uid)
            if len(current_batch) >= 200:
                try:
                    pipeline.execute()
                except Exception as e:
                    print(f"[Redis-{label}] 批量写入失败: {e}")
                pipeline = client.pipeline(transaction=False)
                current_batch = []
        if current_batch:
            try:
                pipeline.execute()
            except Exception as e:
                print(f"[Redis-{label}] 批量写入失败: {e}")
        print(f"[Redis-{label}] 航线写入完成: {len(route_data_map)} 架")
        try:
            client.close()
        except Exception:
            pass


# ========== 工具函数 ==========
def fmt_ms(ts_ms: int) -> str:
    """毫秒时间戳转格式化字符串（含毫秒）"""
    if not ts_ms:
        return "-"
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# ========== 自定义 WS 客户端：只提取 flightTrack 的 uid + timestamp ==========
class TimingWsClient(ReceiverWsStats):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # (uid, msg_timestamp) -> ws本地接收时间ms（兼容旧逻辑）
        self.ws_records: Dict[Tuple[str, int], int] = {}
        # uid -> [ws接收时间ms列表]（按时间排序，用于精确匹配本次发射的每条记录）
        self.ws_records_by_uid: Dict[str, List[int]] = {}
        self.ws_lock = threading.Lock()
        # 诊断计数
        self.msg_received = 0      # 收到的总消息数
        self.msg_filtered = 0      # 被过滤的消息数
        self.msg_matched = 0       # 匹配到 flightTrack/uavs 的消息数

    def _process_body(self, body: str):
        """重写：仅提取 flightTrack / uavs 消息中的 uid 与 timestamp"""
        body = body.rstrip("\x00").strip()
        if not body:
            return

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return

        self.msg_received += 1

        # 过滤：只处理含 flightTrack / uavs / data.flightTrack 的消息
        has_uavs = "uavs" in data and isinstance(data.get("uavs"), list)
        has_ft = "flightTrack" in data
        has_nested = "data" in data and isinstance(data.get("data"), dict)
        if not has_uavs and not has_ft and not has_nested:
            self.msg_filtered += 1
            return

        ws_time_ms = time.time_ns() // 1_000_000
        items = []

        # 情况1: uavs 列表
        uavs = data.get("uavs")
        if isinstance(uavs, list):
            items.extend(uavs)

        # 情况2: flightTrack 列表/字典
        ft = data.get("flightTrack")
        if isinstance(ft, list):
            items.extend(ft)
        elif isinstance(ft, dict):
            items.append(ft)

        # 情况3: data 嵌套
        nested = data.get("data")
        if isinstance(nested, dict):
            nd_ft = nested.get("flightTrack")
            if isinstance(nd_ft, list):
                items.extend(nd_ft)
            elif isinstance(nd_ft, dict):
                items.append(nd_ft)

        # WS 消息的 timestamp 在顶层，所有 UAV 共享
        ws_ts = data.get("timestamp", 0)

        for item in items:
            if not isinstance(item, dict):
                continue
            # WS 消息使用 "id" 字段作为 UAV 标识
            uid = item.get("id") or item.get("uniqueProductIdentificationCode") or item.get("uavIdentifyCode", "")
            if uid:
                key = (uid, ws_ts)
                with self.ws_lock:
                    # 只记录第一次收到的时间（兼容旧逻辑）
                    if key not in self.ws_records:
                        self.ws_records[key] = ws_time_ms
                        self.msg_matched += 1
                    # 同时记录 uid-only key，用于与 Kafka 数据模糊匹配
                    uid_only_key = (uid, 0)
                    if uid_only_key not in self.ws_records:
                        self.ws_records[uid_only_key] = ws_time_ms
                    # 按 uid 收集所有 WS 接收时间（保持排序，用于精确匹配本次发射的每条记录）
                    if uid not in self.ws_records_by_uid:
                        self.ws_records_by_uid[uid] = []
                    # 使用 bisect 保持列表有序，避免重复记录相同时间
                    idx = bisect.bisect_left(self.ws_records_by_uid[uid], ws_time_ms)
                    if idx == len(self.ws_records_by_uid[uid]) or self.ws_records_by_uid[uid][idx] != ws_time_ms:
                        self.ws_records_by_uid[uid].insert(idx, ws_time_ms)


# ========== Kafka 消费线程 ==========
def kafka_consume_loop(stop_event: threading.Event, ready_event: threading.Event, kafka_url: str, topic: str,
                       records_dict: Dict[Tuple[str, int], bool], cluster_name: str = "A"):
    """
    后台消费 uav_runtime_data，仅记录 (uid, timestamp) -> True 用于确认消息已到达。
    不记录消费本地时间戳，避免 poll 延迟导致的测量误差。
    上图时间统一使用 WS收到时间 - 发射时间（emit_t）。
    """
    consumer = KafkaConsumerClient(
        bootstrap_servers=kafka_url,
        group_id=f"timing_test_{cluster_name}_{int(time.time() * 1000)}",
        consume_from_latest_on_start=True,
    )
    consumer.subscribe([topic])
    print(f"[Kafka-{cluster_name}] 消费者已启动，订阅 topic: {topic}")
    ready_event.set()  # 通知主进程：消费者已就绪

    while not stop_event.is_set():
        messages = consumer.poll(timeout_ms=500)
        for msg in messages:
            uid = msg.get("uniqueProductIdentificationCode")
            ts = msg.get("timestamp", 0)
            if uid and ts:
                key = (uid, ts)
                records_dict[key] = True  # 仅标记为"已消费"，不记录时间戳

    consumer.close()
    print(f"[Kafka-{cluster_name}] 消费者已停止")


def trace_consume_loop(stop_event: threading.Event, ready_event: threading.Event, kafka_url: str,
                       records_dict: Dict[Tuple[str, int], int], cluster_name: str = "A"):
    """后台消费 uav_runtime_trace，记录 (uid, timestamp) -> 消费本地时间ms"""
    consumer = KafkaConsumerClient(
        bootstrap_servers=kafka_url,
        group_id=f"trace_test_{cluster_name}_{int(time.time() * 1000)}",
        consume_from_latest_on_start=True,
    )
    consumer.subscribe(["uav_runtime_trace"])
    print(f"[Trace-{cluster_name}] 消费者已启动，订阅 topic: uav_runtime_trace")
    ready_event.set()  # 通知主进程：消费者已就绪

    poll_counter = 0
    while not stop_event.is_set():
        messages = consumer.poll(timeout_ms=500)
        poll_counter += 1
        if messages:
            # uav_runtime_trace 消息可能没有 uid，只要有消息就计数
            for msg in messages:
                uid = msg.get("uniqueProductIdentificationCode") or msg.get("uavIdentifyCode", "")
                ts = msg.get("timestamp", 0)
                # trace 的 timestamp 可能是秒级，统一转为毫秒级作为 key
                if ts and ts < 1e10:
                    ts = int(ts * 1000)
                if uid and ts:
                    key = (uid, ts)
                else:
                    # 如果消息没有 uid，使用 (cluster_name, ts) 作为占位 key
                    key = (f"__trace_{cluster_name}", ts if ts else poll_counter)
                records_dict[key] = time.time_ns() // 1_000_000
        # 每 10 秒打印一次累计接收量
        if poll_counter % 20 == 0:
            print(f"[Trace-{cluster_name}] 累计收到 {len(records_dict)} 条 (已 poll {poll_counter} 次)")

    consumer.close()
    print(f"[Trace-{cluster_name}] 消费者已停止")


# ========== 数据发射 ==========
def load_and_emit(producer: KafkaProducerClient, scene_file: str,
                  kafka_records_a: Dict, kafka_records_b: Dict,
                  trace_records_a: Dict, trace_records_b: Dict) -> Dict[Tuple[str, int], int]:
    """
    加载 JSON 并按 uid 轮询发射，确保每轮所有 UAV 同时发射（每架1条）。
    场景文件通常包含 N 架无人机 × M 个轨迹点，按时间戳排序。
    本函数将数据按 uid 分组，然后逐轮发射：每轮每架 UAV 取下一个轨迹点，
    实现 N 架无人机同时发射的效果。
    返回: {(uid, timestamp): emit_time_ms}
    """
    with open(scene_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    # 1. 按 uid 分组（保留每个 uid 的轨迹点顺序）
    uid_records: Dict[str, List[dict]] = {}
    for r in records:
        uid = r.get("uniqueProductIdentificationCode", "UNKNOWN")
        if uid not in uid_records:
            uid_records[uid] = []
        uid_records[uid].append(r)

    uids = list(uid_records.keys())
    max_points = max(len(v) for v in uid_records.values())
    print(f"[发射] 场景文件共 {len(records)} 条记录，{len(uids)} 架无人机，每架最多 {max_points} 个轨迹点")
    print(f"[发射] 采用轮询发射：每轮同时发射 {len(uids)} 架无人机（各1条），共 {max_points} 轮")

    emit_records: Dict[Tuple[str, int], int] = {}

    # 2. 逐轮发射：每轮从每个 uid 取下一个点
    for round_idx in range(max_points):
        now_ms = time.time_ns() // 1_000_000
        batch: List[dict] = []
        batch_keys: List[Tuple[str, int]] = []

        for uid in uids:
            points = uid_records[uid]
            if round_idx < len(points):
                r = points[round_idx]
                r["timestamp"] = now_ms
                key = (uid, now_ms)
                # 每轮每个 uid 只发1条，key 唯一
                emit_records[key] = now_ms
                batch.append(r)
                batch_keys.append(key)

        if not batch:
            break

        producer.send_bulk(batch, KAFKA_TOPIC)
        print(f"  轮次 {round_idx + 1}/{max_points}: 同时发射 {len(batch)} 架无人机 (timestamp={now_ms})")

        # 异步确认：打印消费状态但不阻塞发射节奏
        ka = sum(1 for k in batch_keys if k in kafka_records_a)
        kb = sum(1 for k in batch_keys if k in kafka_records_b)
        ta = len(trace_records_a)
        tb = len(trace_records_b)
        if round_idx % 10 == 0 or round_idx == max_points - 1:
            print(f"    [确认] Kafka-A:{ka}/{len(batch)} Kafka-B:{kb}/{len(batch)} "
                  f"Trace-A:{ta} Trace-B:{tb}")

        # 轮次间隔：与场景文件采样间隔保持一致（1秒），最后一轮不 sleep
        if round_idx < max_points - 1:
            time.sleep(EMIT_INTERVAL_SEC)

    print("[发射] 全部数据发射完成")
    return emit_records


# ========== 分析与报告 ==========
def find_ws_time_after_emit(ws_records_by_uid: Dict[str, List[int]], uid: str, emit_t: int):
    """
    在 uid 的 WS 接收时间列表中，二分查找第一个 >= emit_t 的时间。
    返回匹配的 WS 时间，如无则返回 None。
    用于区分已有 100 个模拟器的历史数据和本次新发射的数据。
    """
    times = ws_records_by_uid.get(uid)
    if not times:
        return None
    idx = bisect.bisect_left(times, emit_t)
    if idx < len(times):
        return times[idx]
    return None


def analyze_and_report(emit_records: Dict[Tuple[str, int], int],
                       kafka_records_a: Dict[Tuple[str, int], bool],
                       kafka_records_b: Dict[Tuple[str, int], bool],
                       ws_records_by_uid_a: Dict[str, List[int]],
                       ws_records_by_uid_b: Dict[str, List[int]],
                       trace_records_a: Dict[Tuple[str, int], int] = None,
                       trace_records_b: Dict[Tuple[str, int], int] = None,
                       ws_client_a=None, ws_client_b=None):
    """
    匹配发射记录与 WS 接收时间，计算上图时间（WS收到时间 - 发射时间）。
    Kafka 消费者仅用于确认消息已到达，不参与时间计算（避免 poll 延迟误差）。
    输出报告包含分位数统计，用于 A/B 集群性能对比。
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(LOG_DIR, f"上图时间统计_{timestamp_str}.txt")

    lines = []
    lines.append("=" * 160)
    lines.append("上图时间指标统计报告（A/B 集群对比 / 按无人机汇总）")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 160)
    lines.append("")

    # 诊断信息
    lines.append("【诊断信息】")
    if ws_client_a:
        lines.append(f"  WS-A: 收到 {ws_client_a.msg_received} 条消息，过滤 {ws_client_a.msg_filtered} 条，匹配 {ws_client_a.msg_matched} 条")
        lines.append(f"  WS-A: 按 uid 记录 WS 时间条数: {sum(len(v) for v in ws_records_by_uid_a.values())}")
    if ws_client_b:
        lines.append(f"  WS-B: 收到 {ws_client_b.msg_received} 条消息，过滤 {ws_client_b.msg_filtered} 条，匹配 {ws_client_b.msg_matched} 条")
        lines.append(f"  WS-B: 按 uid 记录 WS 时间条数: {sum(len(v) for v in ws_records_by_uid_b.values())}")
    if trace_records_a is not None:
        lines.append(f"  Trace-A: 收到 {len(trace_records_a)} 条 uav_runtime_trace 消息")
    if trace_records_b is not None:
        lines.append(f"  Trace-B: 收到 {len(trace_records_b)} 条 uav_runtime_trace 消息")
    lines.append("")

    # 按 uid 分组收集数据（上图时间 = WS收到时间 - 发射时间）
    uid_stats: Dict[str, dict] = {}
    total = len(emit_records)
    all_dt_a, all_dt_b = [], []
    matched_ws_a = matched_ws_b = 0
    # 匹配方式统计
    match_list_a = match_miss_a = 0
    match_list_b = match_miss_b = 0

    for key in sorted(emit_records.keys()):
        uid, msg_ts = key
        if uid not in uid_stats:
            uid_stats[uid] = {
                "dt_a": [], "dt_b": [],
                "count": 0, "matched_ws_a": 0, "matched_ws_b": 0,
            }
        s = uid_stats[uid]
        s["count"] += 1

        emit_t = emit_records.get(key)

        # WS 匹配：在 ws_records_by_uid[uid] 列表中二分查找第一个 >= emit_t 的时间
        ws_a = find_ws_time_after_emit(ws_records_by_uid_a, uid, emit_t)
        if ws_a:
            match_list_a += 1
        else:
            match_miss_a += 1

        ws_b = find_ws_time_after_emit(ws_records_by_uid_b, uid, emit_t)
        if ws_b:
            match_list_b += 1
        else:
            match_miss_b += 1

        # 上图时间 = WS收到时间 - 发射时间（端到端延迟）
        dt_a = ws_a - emit_t if (ws_a and emit_t) else None
        dt_b = ws_b - emit_t if (ws_b and emit_t) else None

        if dt_a is not None:
            s["dt_a"].append(dt_a)
            s["matched_ws_a"] += 1
            all_dt_a.append(dt_a)
            matched_ws_a += 1
        if dt_b is not None:
            s["dt_b"].append(dt_b)
            s["matched_ws_b"] += 1
            all_dt_b.append(dt_b)
            matched_ws_b += 1

    def _percentile(arr, p):
        """计算分位数，p 为 0~100"""
        if not arr:
            return None
        s = sorted(arr)
        k = (len(s) - 1) * p / 100.0
        f = int(k)
        c = f + 1 if f + 1 < len(s) else f
        if f == c:
            return s[f]
        return s[f] * (c - k) + s[c] * (k - f)

    def _stat(arr):
        if not arr:
            return "-"
        return f"{sum(arr)/len(arr):.1f}/{min(arr):.1f}/{max(arr):.1f}"

    def _full_stat(arr):
        """输出完整统计：均值/中位数/P90/P95/P99/最小/最大"""
        if not arr:
            return "无数据"
        avg = sum(arr) / len(arr)
        med = _percentile(arr, 50)
        p90 = _percentile(arr, 90)
        p95 = _percentile(arr, 95)
        p99 = _percentile(arr, 99)
        return (f"  平均值 : {avg:.1f} ms\n"
                f"  中位数 : {med:.1f} ms\n"
                f"  P90    : {p90:.1f} ms (90% 的记录 <= 此值)\n"
                f"  P95    : {p95:.1f} ms (95% 的记录 <= 此值)\n"
                f"  P99    : {p99:.1f} ms (99% 的记录 <= 此值)\n"
                f"  最小   : {min(arr):.1f} ms\n"
                f"  最大   : {max(arr):.1f} ms")

    # 输出按 uid 汇总的表格
    header = (f"{'无人机ID':<26} {'记录数':>6} {'A-匹配':>6} {'B-匹配':>6} "
              f"{'上图-A(ms)':>22} {'上图-B(ms)':>22} {'差异(ms)':>10}")
    lines.append(header)
    lines.append("-" * 130)

    for uid, s in sorted(uid_stats.items()):
        diff_vals = []
        for i in range(min(len(s["dt_a"]), len(s["dt_b"]))):
            diff_vals.append(abs(s["dt_a"][i] - s["dt_b"][i]))
        diff_str = f"{sum(diff_vals)/len(diff_vals):.1f}" if diff_vals else "-"

        lines.append(
            f"{uid:<26} {s['count']:>6} {s['matched_ws_a']:>6} {s['matched_ws_b']:>6} "
            f"{_stat(s['dt_a']):>22} {_stat(s['dt_b']):>22} {diff_str:>10}"
        )

    lines.append("-" * 160)
    lines.append("")

    # ========== 首次上图时间统计（每个uid第一次发射到第一次WS收到的时间） ==========
    first_emit_by_uid: Dict[str, int] = {}
    for (uid, msg_ts), emit_t in emit_records.items():
        if uid not in first_emit_by_uid or emit_t < first_emit_by_uid[uid]:
            first_emit_by_uid[uid] = emit_t

    first_display_a: Dict[str, int] = {}  # uid -> 首次上图时间(ms)
    first_display_b: Dict[str, int] = {}
    for uid, emit_t in first_emit_by_uid.items():
        ws_a = find_ws_time_after_emit(ws_records_by_uid_a, uid, emit_t)
        if ws_a:
            first_display_a[uid] = ws_a - emit_t
        ws_b = find_ws_time_after_emit(ws_records_by_uid_b, uid, emit_t)
        if ws_b:
            first_display_b[uid] = ws_b - emit_t

    lines.append("【首次上图时间统计】（每个模拟器：首次发射 → 首次WS收到）")
    lines.append(f"  模拟器总数 : {len(first_emit_by_uid)}")
    lines.append(f"  A集群首次上图成功 : {len(first_display_a)}/{len(first_emit_by_uid)}")
    lines.append(f"  B集群首次上图成功 : {len(first_display_b)}/{len(first_emit_by_uid)}")

    if first_display_a:
        vals_a = list(first_display_a.values())
        lines.append(f"  A集群首次上图时间 : 平均={sum(vals_a)/len(vals_a):.1f}ms, 最小={min(vals_a):.1f}ms, 最大={max(vals_a):.1f}ms")
    if first_display_b:
        vals_b = list(first_display_b.values())
        lines.append(f"  B集群首次上图时间 : 平均={sum(vals_b)/len(vals_b):.1f}ms, 最小={min(vals_b):.1f}ms, 最大={max(vals_b):.1f}ms")

    # 按 uid 明细打印（前20个，避免日志过长）
    lines.append("")
    lines.append(f"{'无人机ID':<26} {'A首次上图(ms)':>14} {'B首次上图(ms)':>14}")
    lines.append("-" * 60)
    for uid in sorted(first_emit_by_uid.keys())[:20]:
        fa = first_display_a.get(uid)
        fb = first_display_b.get(uid)
        lines.append(f"{uid:<26} {fa if fa is not None else '-':>14} {fb if fb is not None else '-':>14}")
    if len(first_emit_by_uid) > 20:
        lines.append(f"... 共 {len(first_emit_by_uid)} 个模拟器，仅展示前20个")
    lines.append("")

    # A 集群汇总
    lines.append("【A 集群汇总】")
    lines.append(f"  总发射记录数 : {total}")
    lines.append(f"  Kafka 匹配数 : {sum(1 for k in emit_records if k in kafka_records_a)}")
    lines.append(f"  WS 匹配成功数 : {matched_ws_a}")
    if all_dt_a:
        lines.append("  上图时间分布 (WS收到 - 发射时间):")
        lines.append(_full_stat(all_dt_a))
    else:
        lines.append("  未匹配到数据")

    lines.append("")
    lines.append("【B 集群汇总】")
    lines.append(f"  总发射记录数 : {total}")
    lines.append(f"  Kafka 匹配数 : {sum(1 for k in emit_records if k in kafka_records_b)}")
    lines.append(f"  WS 匹配成功数 : {matched_ws_b}")
    if all_dt_b:
        lines.append("  上图时间分布 (WS收到 - 发射时间):")
        lines.append(_full_stat(all_dt_b))
    else:
        lines.append("  未匹配到数据")

    # 匹配方式统计（仅保留有意义的统计项）
    lines.append("")
    lines.append("【WS 匹配方式统计】")
    lines.append(f"  A集群: 列表查找匹配={match_list_a}, 未匹配={match_miss_a}")
    lines.append(f"  B集群: 列表查找匹配={match_list_b}, 未匹配={match_miss_b}")
    lines.append("  （列表查找匹配 = 在 uid 的时间列表中二分查找第一个 >= 发射时间的 WS 时间）")
    lines.append("  （用于区分已有 100 个模拟器的历史数据和本次新发射的数据）")

    if all_dt_a and all_dt_b:
        avg_a = sum(all_dt_a) / len(all_dt_a)
        avg_b = sum(all_dt_b) / len(all_dt_b)
        lines.append("")
        lines.append("【A/B 集群对比】")
        lines.append(f"  平均上图时间差异: {abs(avg_a - avg_b):.1f} ms")
        lines.append(f"  一致性判定: {'一致' if abs(avg_a - avg_b) < 100 else '差异较大'}")

    lines.append("=" * 160)

    report = "\n".join(lines)
    print("\n" + report)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[报告已保存] {report_path}")


# ========== 主流程 ==========
def main():
    print("=" * 70)
    print("上图时间指标获取")
    print("=" * 70)

    # 1. 检查并生成数据
    if not os.path.isfile(SCENE_FILE):
        print(f"[数据生成] 场景文件不存在: {SCENE_FILE}")
        if not os.path.isfile(GENERATOR_PY):
            print(f"[错误] 生成脚本不存在: {GENERATOR_PY}")
            sys.exit(1)
        print(f"[数据生成] 调用生成脚本: {GENERATOR_PY}")
        subprocess.run([sys.executable, GENERATOR_PY], cwd=ENGINE_DIR, check=True)
        if not os.path.isfile(SCENE_FILE):
            print("[错误] 生成后场景文件仍不存在")
            sys.exit(1)
        print("[数据生成] 完成")
    else:
        print(f"[数据生成] 场景文件已存在: {SCENE_FILE}")

    # 2. 先启动 WS 客户端（A/B 集群，防止遗漏数据）
    print("\n[启动] 启动 WebSocket 客户端（A/B 集群）...")
    ws_client_a = TimingWsClient(
        url=WS_URL_A,
        jwt_token="",  # 高可用模式根据 HAR 分析不需要 jwt-token
        destination=WS_DESTINATION,
        conn_name="上图时间指标-ws-A",
    )
    ws_client_b = TimingWsClient(
        url=WS_URL_B,
        jwt_token="",
        destination=WS_DESTINATION,
        conn_name="上图时间指标-ws-B",
    )
    ws_thread_a = threading.Thread(target=ws_client_a.start, daemon=True)
    ws_thread_b = threading.Thread(target=ws_client_b.start, daemon=True)
    ws_thread_a.start()
    ws_thread_b.start()

    # 等待 WS 建立连接
    for _ in range(20):
        if ws_client_a.connected and ws_client_b.connected:
            print("[WS] A/B 集群 SockJS 连接均已建立")
            break
        time.sleep(0.5)
    else:
        print("[警告] WS 连接超时，继续执行（可能错过前几秒数据）")

    # 3. 启动 Kafka/Trace 消费者线程（A/B 集群，使用 ready_event 确保就绪后再发射）
    kafka_stop = threading.Event()
    kafka_ready_a = threading.Event()
    kafka_ready_b = threading.Event()
    trace_ready_a = threading.Event()
    trace_ready_b = threading.Event()
    kafka_records_a: Dict[Tuple[str, int], bool] = {}
    kafka_records_b: Dict[Tuple[str, int], bool] = {}
    trace_records_a: Dict[Tuple[str, int], int] = {}
    trace_records_b: Dict[Tuple[str, int], int] = {}

    kafka_thread_a = threading.Thread(
        target=kafka_consume_loop,
        args=(kafka_stop, kafka_ready_a, ha_env.kafka_url_a, KAFKA_TOPIC, kafka_records_a, "A"),
        daemon=True,
    )
    kafka_thread_b = threading.Thread(
        target=kafka_consume_loop,
        args=(kafka_stop, kafka_ready_b, ha_env.kafka_url_b, KAFKA_TOPIC, kafka_records_b, "B"),
        daemon=True,
    )
    trace_thread_a = threading.Thread(
        target=trace_consume_loop,
        args=(kafka_stop, trace_ready_a, ha_env.kafka_url_a, trace_records_a, "A"),
        daemon=True,
    )
    trace_thread_b = threading.Thread(
        target=trace_consume_loop,
        args=(kafka_stop, trace_ready_b, ha_env.kafka_url_b, trace_records_b, "B"),
        daemon=True,
    )
    kafka_thread_a.start()
    kafka_thread_b.start()
    trace_thread_a.start()
    trace_thread_b.start()

    # 等待所有消费者就绪（subscribe + seek_to_end 完成）
    print("[等待] 等待消费者线程完全就绪（订阅+位点设置）...")
    for ev, name in [(kafka_ready_a, "Kafka-A"), (kafka_ready_b, "Kafka-B"),
                     (trace_ready_a, "Trace-A"), (trace_ready_b, "Trace-B")]:
        if not ev.wait(timeout=10):
            print(f"[警告] {name} 消费者就绪超时")
    print("[就绪] 所有消费者已就位")

    # 4. 写入 Redis 航线数据（触发下游 UTM 激活追踪）
    _write_redis_routes(SCENE_FILE)
    print("[等待] Redis 航线写入完成，等待 3 秒让后端加载航线计划...")
    time.sleep(3)

    # 5. 发射数据（通过 mirror 模式同时向 A/B 双集群写入，每批实时确认）
    producer = KafkaProducerClient(ha_env.kafka_url_a, bootstrap_servers_mirror=ha_env.kafka_url_b)
    print(f"[Kafka] 主集群: {ha_env.kafka_url_a} | 镜像集群: {ha_env.kafka_url_b}")
    try:
        emit_records = load_and_emit(producer, SCENE_FILE,
                                     kafka_records_a, kafka_records_b,
                                     trace_records_a, trace_records_b)
    finally:
        producer.close()

    # 6. 全部发射完成后，再统一等待几秒确保最后一批消费完毕
    print(f"\n[等待] 发射完成，额外等待 5 秒以确保最后一批 Kafka/WS/Trace 消费完毕...")
    time.sleep(5)

    # 7. 停止消费
    print("[停止] 正在停止消费者...")
    kafka_stop.set()
    ws_client_a.stop()
    ws_client_b.stop()

    kafka_thread_a.join(timeout=5)
    kafka_thread_b.join(timeout=5)
    trace_thread_a.join(timeout=5)
    trace_thread_b.join(timeout=5)
    ws_thread_a.join(timeout=5)
    ws_thread_b.join(timeout=5)

    # 8. 分析并输出（A/B 集群对比）
    # 使用 ws_records_by_uid 替代 ws_records，支持按发射时间精确匹配每条记录
    analyze_and_report(emit_records, kafka_records_a, kafka_records_b,
                       ws_client_a.ws_records_by_uid, ws_client_b.ws_records_by_uid,
                       trace_records_a, trace_records_b,
                       ws_client_a, ws_client_b)


if __name__ == "__main__":
    main()