#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_kafka_scene.py - 场景化 Kafka 数据发射器（核心发射器）

存储位置：utm_moc52_develop/tools/

支持两种使用方式：
1. 命令行直接指定 JSON 文件发射
2. 被 testcases 场景脚本 import 调用

用法示例：
    # 命令行：发射指定 JSON
    python run_kafka_scene.py --file scenes/scene1/uav_001.json --topic uav_runtime_data

    # 命令行：发射整个场景目录
    python run_kafka_scene.py --scene scenes/scene1

    # 命令行：发射多个文件
    python run_kafka_scene.py -f scenes/s1/uav1.json -f scenes/s1/uav2.json --interval 500

    # Python 调用（供 testcases 场景脚本使用）
    from run_kafka_scene import SceneEmitter
    emitter = SceneEmitter(files=['scenes/scene1/uav_001.json'])
    emitter.start()
    emitter.wait_until_done()
    emitter.stop()
"""

import sys
import os
import time
import json
import threading
import argparse
from typing import List, Dict, Any, Optional

# 将项目根目录加入 path，便于从 tools 下直接运行
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from core.kafka_proc import KafkaProducerClient, KafkaConsumerClient
import env as _env

try:
    from common.log_setup import debug_print
except ImportError:
    def debug_print(prefix, message): pass

# 尝试导入 redis（写入航线用）
try:
    import redis as _redis
except ImportError:
    _redis = None


class UAVData:
    """单个 UAV 的数据管理"""

    def __init__(self, uid: str, records: List[Dict[str, Any]], delay_ms: int = 0):
        self.uid = uid
        self.records = records
        self.delay_ms = delay_ms
        self.cursor = 0
        self.enabled = True

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def progress(self) -> float:
        return self.cursor / self.total if self.total > 0 else 1.0

    def has_next(self) -> bool:
        return self.cursor < self.total

    def next(self) -> Optional[Dict[str, Any]]:
        if not self.has_next():
            return None
        record = self.records[self.cursor].copy()
        self.cursor += 1
        return record

    def reset(self):
        self.cursor = 0


class SceneEmitter:
    """场景 Kafka 发射器"""

    def __init__(
        self,
        files: Optional[List[str]] = None,
        scene_dir: Optional[str] = None,
        kafka_url: Optional[str] = None,
        topic: str = 'uav_runtime_data',
        interval_ms: int = 1000,
        timestamp_mode: str = 'replace',
        loop: bool = False,
        debug_print_uav_ids: bool = False,
        consume_trace: bool = False,
        trace_group_id: Optional[str] = None,
        quiet: bool = False,
    ):
        """
        Args:
            files: 直接指定 JSON 文件路径列表
            scene_dir: 场景目录路径（目录下所有 .json 文件）
            kafka_url: Kafka 地址，默认从 env 读取
            topic: Kafka topic
            interval_ms: 发射间隔（毫秒）
            timestamp_mode: 时间戳模式（replace/align/preserve）
            loop: 数据耗尽后是否循环
            debug_print_uav_ids: 是否打印每次发射的无人机ID列表，默认False
            consume_trace: 是否消费 uav_runtime_trace topic，默认False
            trace_group_id: trace消费组ID，默认使用进程ID区分（多进程共享同一ID可避免重复消费）
            quiet: 是否静默模式（不打印发送日志），默认False
        """
        self.topic = topic
        self.interval_ms = interval_ms
        self.timestamp_mode = timestamp_mode
        self.loop = loop
        self.debug_print_uav_ids = debug_print_uav_ids
        self.consume_trace = consume_trace
        self.trace_group_id = trace_group_id or f"scene_emitter_trace_{os.getpid()}"
        self.quiet = quiet
        self.running = False

        # Kafka 配置
        _kafka_url = kafka_url or getattr(_env, 'kafka_url', 'localhost:9092')
        print(f"[Kafka] 连接地址: {_kafka_url}")
        self.kafka = KafkaProducerClient(_kafka_url)

        # 加载 UAV 数据
        self.uav_data_list: List[UAVData] = []
        if files:
            self._load_from_files(files)
        if scene_dir:
            self._load_from_scene_dir(scene_dir)

        self._thread = None
        self._first_emit_time = None
        self._first_record_time = None

        # Redis 客户端（用于写入 BIZ_DATA:UAV_ROUTE）
        self.redis_client = None
        if _redis is not None:
            try:
                self.redis_client = _redis.Redis(
                    host=_env.redis_ip,
                    port=int(_env.redis_port),
                    password=_env.redis_password,
                    db=0,
                    decode_responses=True,
                )
                self.redis_client.ping()
                print(f"[Redis] 连接成功 ({_env.redis_ip}:{_env.redis_port})")
            except Exception as e:
                print(f"[Redis] 连接失败: {e}")

        # uav_runtime_trace 消费者
        self.trace_consumer = None
        self.trace_thread = None
        self.trace_stats = {'received': 0}
        self.trace_records = []  # 保存回查 Redis 的完整 trace 数据
        if self.consume_trace:
            try:
                self.trace_consumer = KafkaConsumerClient(
                    bootstrap_servers=_kafka_url,
                    group_id=self.trace_group_id,
                    consume_from_latest_on_start=True,
                )
                self.trace_consumer.subscribe(['uav_runtime_trace'])
                print(f"[Trace] uav_runtime_trace 消费者已初始化 (group={self.trace_group_id})")
            except Exception as e:
                print(f"[Trace] 消费者初始化失败: {e}")

        self.stats = {
            'sent': 0,
            'start_time': None,
            'end_time': None
        }

    def _load_from_files(self, files: List[str]):
        """从指定文件列表加载"""
        for path in files:
            if not os.path.exists(path):
                print(f"⚠️  文件不存在: {path}")
                continue
            self._load_json_file(path)

    def _load_from_scene_dir(self, scene_dir: str):
        """从场景目录加载所有 JSON 文件"""
        if not os.path.exists(scene_dir):
            print(f"⚠️  场景目录不存在: {scene_dir}")
            return

        for fname in sorted(os.listdir(scene_dir)):
            if not fname.endswith('.json'):
                continue
            path = os.path.join(scene_dir, fname)
            self._load_json_file(path)

    def _load_json_file(self, path: str):
        """加载单个 JSON 文件，按 uid 分组。

        支持三种 JSON 格式：
        1. 列表: [{telemetry}, ...] — ATC 遥测记录数组
        2. dict + records 键: {"records": [{telemetry}, ...]}
        3. dict + data 键: {"data": [{flight_data_point}, ...]} — flight_data 格式，
           每个元素是坐标点(uav_id/lat/lon/alt/timestamp)，自动转为 ATC 遥测格式
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                records = data
            elif isinstance(data, dict) and 'records' in data:
                records = data['records']
            elif isinstance(data, dict) and 'data' in data:
                # flight_data 格式：{"data": [{uav_id, position:{lat,lon,alt}, ...}]}
                records = [self._normalize_flight_data(r) for r in data['data']]
                print(f"  📋 flight_data 格式: {len(records)} 个坐标点 ({os.path.basename(path)})")
            else:
                records = [data]

            # 按 uid 分组
            groups: Dict[str, List[Dict]] = {}
            for record in records:
                uid = record.get('uniqueProductIdentificationCode', 'UNKNOWN')
                groups.setdefault(uid, []).append(record)

            for uid, uid_records in groups.items():
                self.uav_data_list.append(UAVData(uid, uid_records))
                print(f"  ✅ {uid}: {len(uid_records)} 条记录 ({os.path.basename(path)})")

        except Exception as e:
            print(f"  ❌ 加载失败 {path}: {e}")

    @staticmethod
    def _normalize_flight_data(pt: Dict) -> Dict:
        """将 flight_data 格式坐标点转为 ATC 遥测格式。

        flight_data:                   → ATC telemetry:
          uav_id                       → uniqueProductIdentificationCode
          position.lat                 → latitude
          position.lon                 → longitude
          position.alt                 → geodeticAltitude
          position.alt_relative        → relativeAltitude
          timestamp                    → timestamp
          track_angle                  → trackAngle
          vertical_speed               → verticalSpeed
          status.ground_speed          → speed
          classification / mav_type    保持
        """
        pos = pt.get("position", {}) or {}
        status = pt.get("status", {}) or {}
        return {
            "uniqueProductIdentificationCode": pt.get("uav_id", "UNKNOWN"),
            "realNameRegistrationSign": pt.get("realNameRegistrationSign", pt.get("uav_id", "")),
            "longitude": pos.get("lon", 0),
            "latitude": pos.get("lat", 0),
            "geodeticAltitude": pos.get("alt", 0),
            "relativeAltitude": pos.get("alt_relative", 0),
            "timestamp": pt.get("timestamp", 0),
            "trackAngle": pt.get("track_angle", 0),
            "verticalSpeed": pt.get("vertical_speed", 0),
            "speed": status.get("ground_speed", 0),
            "operatingStatus": 2,
            "classification": pt.get("classification", 3),
            "uasOperationCategory": pt.get("mav_type", 1),
            "coordinateSystemType": 0,
            "horizontalAccuracy": 1,
            "verticalAccuracy": 0,
            "speedAccuracy": 0,
            "timestampAccuracy": 0,
            "sourceType": 1,
            "rpsLocationType": 1,
            "rpsLongitude": 0.0,
            "rpsLatitude": 0.0,
            "rpsAltitude": 0.0,
            "pressureAltitude": 0.0,
            "addInf": {},
        }

    def _process_timestamp(self, record: Dict, now_ms: int) -> int:
        """处理时间戳"""
        original_ts = record.get('timestamp', 0)
        now_ms = now_ms - 1000  # 减 1 秒，可以慢不能快

        if self.timestamp_mode == 'preserve':
            return original_ts
        elif self.timestamp_mode == 'align':
            if self._first_emit_time is None:
                self._first_emit_time = now_ms
                self._first_record_time = original_ts
                return now_ms
            offset = original_ts - self._first_record_time
            return self._first_emit_time + offset
        else:
            return now_ms

    def start(self):
        """开始发射"""
        if self.running:
            print("⚠️  发射器已在运行")
            return

        if not self.uav_data_list:
            print("❌ 没有加载到任何 UAV 数据")
            return

        self.running = True
        self.stats['start_time'] = time.time()

        # ① 先将航线写入 Redis（必须在发射线程之前，确保下游 UTM 先有飞行计划）
        if self.redis_client:
            print("\n[Redis] 正在写入 UAV 航线数据...")
            self._write_redis_route_batch()
            print(f"[Redis] 航线写入完成: {len(self.uav_data_list)} 架")

        # ② 再启动遥测发射线程（此时 Redis 中已有飞行计划，下游可正常关联）
        self._thread = threading.Thread(target=self._emit_loop)
        self._thread.daemon = True
        self._thread.start()

        # ③ 最后启动 trace 消费线程
        if self.trace_consumer:
            self.trace_thread = threading.Thread(target=self._consume_trace_loop)
            self.trace_thread.daemon = True
            self.trace_thread.start()
            print("[Trace] 开始消费 uav_runtime_trace")

        print(f"\n🚀 发射器启动")
        print(f"   UAV 数量: {len(self.uav_data_list)}")
        print(f"   Topic: {self.topic}")
        print(f"   间隔: {self.interval_ms}ms")
        print(f"   时间戳模式: {self.timestamp_mode}")
        if self.consume_trace:
            print(f"   Trace消费: 已启用")

    def stop(self):
        """停止发射"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self.trace_thread:
            self.trace_thread.join(timeout=3)
        if self.trace_consumer:
            try:
                self.trace_consumer.close()
            except Exception:
                pass
        self.kafka.close()
        self.stats['end_time'] = time.time()

        # 保存 trace 数据到文件
        if self.consume_trace and self.trace_records:
            try:
                trace_path = os.path.join(_root, "mock", "redis_trace.json")
                os.makedirs(os.path.dirname(trace_path), exist_ok=True)
                with open(trace_path, 'w', encoding='utf-8') as f:
                    json.dump(self.trace_records, f, ensure_ascii=False, indent=2)
                print(f"[Trace] 已保存 trace 数据到: {trace_path} ({len(self.trace_records)} 条)")
            except Exception as e:
                print(f"[Trace] 保存失败: {e}")
        elif self.redis_client and not self.consume_trace:
            # 未消费模式：直接扫描 Redis 查询 trace 数据
            try:
                trace_records = self._query_trace_from_redis()
                if trace_records:
                    trace_path = os.path.join(_root, "mock", "redis_trace.json")
                    os.makedirs(os.path.dirname(trace_path), exist_ok=True)
                    with open(trace_path, 'w', encoding='utf-8') as f:
                        json.dump(trace_records, f, ensure_ascii=False, indent=2)
                    print(f"[Trace] 已查询并保存 Redis trace 数据: {trace_path} ({len(trace_records)} 条)")
                else:
                    print("[Trace] Redis 中未找到 trace 数据")
            except Exception as e:
                print(f"[Trace] 查询保存失败: {e}")

        print("🛑 发射器已停止")
        print(f"   共发送: {self.stats['sent']} 条")
        if self.consume_trace:
            print(f"   共接收trace: {self.trace_stats['received']} 条")

    def _emit_loop(self):
        """发射循环"""
        last_redis_refresh = 0.0
        redis_refresh_interval = 30.0  # 每 30 秒刷新 Redis 航线时间戳，保持下游 ATC 活跃追踪
        while self.running:
            t0 = time.perf_counter()

            # 周期性刷新 Redis 航线时间戳，确保下游 ATC 不因时间过期而取消追踪
            now = time.time()
            if self.redis_client and now - last_redis_refresh >= redis_refresh_interval:
                try:
                    self._write_redis_route_batch()
                    last_redis_refresh = now
                except Exception as e:
                    print(f"[Redis] 周期性航线刷新失败: {e}")

            if self._is_all_completed():
                if self.loop:
                    self._reset_all()
                else:
                    print("\n🏁 所有 UAV 数据已耗尽")
                    self.running = False
                    break

            self._emit_once()

            elapsed = (time.perf_counter() - t0) * 1000
            sleep_ms = max(0, self.interval_ms - elapsed)
            time.sleep(sleep_ms / 1000)

    def _emit_once(self):
        """单次发射"""
        records = []
        now_ms = int(time.time() * 1000)

        for uav in self.uav_data_list:
            if not uav.has_next():
                continue

            record = uav.next()
            record['timestamp'] = self._process_timestamp(record, now_ms)
            record['active'] = 1  # 标记激活状态，与 PlanRunner 输出一致
            # 强制 operatingStatus=2（飞行中），下游 ATC 依赖此字段识别活跃监视目标
            record['operatingStatus'] = 2
            records.append(record)

        if records:
            try:
                self.kafka.send_bulk(records, self.topic)
                self.stats['sent'] += len(records)

                progress = self._get_progress()
                ts = int(time.time())
                if not self.quiet:
                    if self.debug_print_uav_ids:
                        uids = [r.get('uniqueProductIdentificationCode') for r in records]
                        debug_print("uav_runtime_data", f"{ts} 发送 {len(records)} 条 | {progress} | UAVs: {uids}")
                    else:
                        debug_print("uav_runtime_data", f"{ts} 发送 {len(records)} 条 | {progress}")
            except Exception as e:
                print(f"❌ 发送失败: {e}")

    def _is_all_completed(self) -> bool:
        return all(not u.has_next() for u in self.uav_data_list)

    def _reset_all(self):
        for uav in self.uav_data_list:
            uav.reset()
        self._first_emit_time = None
        self._first_record_time = None
        print("🔄 循环模式: 重新开始")

    def _get_progress(self) -> str:
        total = sum(u.total for u in self.uav_data_list)
        sent = sum(u.cursor for u in self.uav_data_list)
        return f"进度: {sent}/{total} ({sent / total * 100:.1f}%)"

    def _redis_get(self, key):
        """从 Redis 读取指定 key 的值，自动判断类型（string/hash/list/set/zset）"""
        if not self.redis_client:
            return None
        try:
            key_type = self.redis_client.type(key)
            if key_type == "string":
                raw = self.redis_client.get(key)
                if raw is None:
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
            elif key_type == "hash":
                data = self.redis_client.hgetall(key)
                if not data:
                    return None
                parsed = {}
                for k, v in data.items():
                    try:
                        parsed[k] = json.loads(v)
                    except json.JSONDecodeError:
                        parsed[k] = v
                return parsed
            elif key_type == "list":
                data = self.redis_client.lrange(key, 0, -1)
                if not data:
                    return None
                parsed = []
                for item in data:
                    try:
                        parsed.append(json.loads(item))
                    except json.JSONDecodeError:
                        parsed.append(item)
                return parsed
            elif key_type == "set":
                data = list(self.redis_client.smembers(key))
                parsed = []
                for item in data:
                    try:
                        parsed.append(json.loads(item))
                    except json.JSONDecodeError:
                        parsed.append(item)
                return parsed
            elif key_type == "zset":
                data = self.redis_client.zrange(key, 0, -1, withscores=False)
                parsed = []
                for item in data:
                    try:
                        parsed.append(json.loads(item))
                    except json.JSONDecodeError:
                        parsed.append(item)
                return parsed
            else:
                return None
        except Exception as e:
            print(f"[Redis] 读取失败 {key}: {e}")
            return None

    def _query_trace_from_redis(self):
        """直接扫描 Redis 查询 trace 数据（非消费模式），匹配 uav_runtime_trace* 和 BIZ_DATA:UAV_ROUTE 相关 key"""
        if not self.redis_client:
            return []
        records = []
        # 扫描 uav_runtime_trace* 模式的 key
        try:
            keys = list(self.redis_client.scan_iter(match="uav_runtime_trace*", count=1000))
            for key in sorted(keys):
                value = self._redis_get(key)
                if value is not None:
                    records.append({"redisKey": key, "data": value})
        except Exception as e:
            print(f"[Trace] 扫描 uav_runtime_trace* 失败: {e}")
        return records

    def _consume_trace_loop(self):
        """消费 uav_runtime_trace topic，支持两种消息格式：
        1) 含 redisKey：回查 Redis 获取完整数据
        2) 无 redisKey：消息 value 本身就是 trace 数据
        """
        while self.running:
            try:
                messages = self.trace_consumer.poll(timeout_ms=500)
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue

                    ts = msg.get('timestamp', 0)
                    redis_key = msg.get("redisKey") or msg.get("redis_key")
                    self.trace_stats['received'] += 1

                    trace_data = None
                    data_count = 0

                    if redis_key and self.redis_client:
                        # 格式1：回查 Redis
                        try:
                            trace_data = self._redis_get(redis_key)
                            if trace_data is None:
                                # 诊断：打印 Redis key 信息
                                key_exists = self.redis_client.exists(redis_key)
                                key_type = self.redis_client.type(redis_key)
                                print(f"[Trace] Redis回查为空: key={redis_key}, exists={key_exists}, type={key_type}")
                        except Exception as e:
                            print(f"[Trace] Redis回查失败: {e}")
                        data_count = len(trace_data) if isinstance(trace_data, list) else (1 if trace_data else 0)
                    else:
                        # 格式2：消息本身就是 trace 数据
                        # 排除空值和纯时间戳包装
                        msg_copy = dict(msg)
                        msg_copy.pop('timestamp', None)
                        if msg_copy:
                            trace_data = msg_copy
                            data_count = 1

                    if trace_data:
                        self.trace_records.append({
                            "timestamp": ts,
                            "redisKey": redis_key,
                            "data": trace_data,
                        })

                    debug_print("uav_runtime_trace", f"{int(ts)} 收到 {data_count} 条")
            except Exception as e:
                print(f"[Trace] 消费异常: {e}")
            time.sleep(0.05)

    def _build_redis_route(self, uav):
        """根据 UAV 遥测数据生成航线字典，返回 None 表示无数据。
        起降时间平移到当前时刻（保持原始飞行时长），以触发下游 ATC 激活追踪。"""
        if not uav.records:
            return None
        records = uav.records

        # 注册号：优先用 realNameRegistrationSign，否则用 UID
        reg_code = records[0].get("realNameRegistrationSign", uav.uid)

        def _make_segment(seq, p0, p1):
            return {
                "sequence": seq,
                "type": 2,
                "segmentStartLon": p0.get("longitude", 0),
                "segmentStartLat": p0.get("latitude", 0),
                "segmentEndLon": p1.get("longitude", 0),
                "segmentEndLat": p1.get("latitude", 0),
                "segmentStartHeight": p0.get("geodeticAltitude", 0),
                "segmentEndHeight": p1.get("geodeticAltitude", 0),
                "segmentProtectHeight": 50.0,
                "segmentProtectHeightType": 1,
                "segmentWidth": 100.0,
            }

        # 单记录场景：构造一个悬停点航线
        if len(records) == 1:
            p = records[0]
            now = time.time()
            route_list = [_make_segment(0, p, p)]
            return {
                "uniqueProductIdentificationCode": uav.uid,
                "realNameRegistrationSign": reg_code,
                "flightPlanList": [{
                    "flightPlanId": 1,
                    "planTakeoffTime": now,
                    "planLandTime": now + 60,
                    "flightTaskId": 1,
                    "flightTaskName": "test",
                    "routeList": route_list,
                }],
            }

        # 多记录场景：降采样构建折线（最多 200 段，避免下游因过多航段拒绝）
        _MAX_SEGMENTS = 200
        _step = max(1, (len(records) - 1) // _MAX_SEGMENTS)
        route_list = []
        seq = 0
        for i in range(0, len(records) - 1, _step):
            p0 = records[i]
            p1 = records[min(i + _step, len(records) - 1)]
            route_list.append(_make_segment(seq, p0, p1))
            seq += 1
        # 确保末点被覆盖
        if len(records) > 1:
            last = records[-1]
            prev = records[-2]
            if len(route_list) > 0:
                route_list[-1]["segmentEndLon"] = last.get("longitude", 0)
                route_list[-1]["segmentEndLat"] = last.get("latitude", 0)
                route_list[-1]["segmentEndHeight"] = last.get("geodeticAltitude", 0)

        # 计算原始飞行时长，再将起降时间平移到当前时刻
        start_ts = records[0].get("timestamp", int(time.time()))
        end_ts = records[-1].get("timestamp", start_ts + 600)
        if start_ts > 1e10:
            start_ts = start_ts / 1000.0
        if end_ts > 1e10:
            end_ts = end_ts / 1000.0
        duration = max(end_ts - start_ts, 60)
        now = time.time()
        return {
            "uniqueProductIdentificationCode": uav.uid,
            "realNameRegistrationSign": reg_code,
            "flightPlanList": [
                {
                    "flightPlanId": 1,
                    "planTakeoffTime": now,
                    "planLandTime": now + duration,
                    "flightTaskId": 1,
                    "flightTaskName": "test",
                    "routeList": route_list,
                }
            ],
        }

    def _write_redis_route_batch(self, batch_size=200, max_retries=3):
        """使用 Pipeline 批量写入 Redis 航线，支持重试"""
        if not self.redis_client:
            return
        failed = []
        for retry in range(max_retries):
            if retry > 0:
                print(f"[Redis] 第 {retry + 1} 次重试，待写入 {len(failed)} 架...")
            pipeline = self.redis_client.pipeline(transaction=False)
            current_batch = []
            uavs_to_write = failed if retry > 0 else self.uav_data_list
            failed = []
            for uav in uavs_to_write:
                route_data = self._build_redis_route(uav)
                if route_data is None:
                    continue
                pipeline.hset(
                    "BIZ_DATA:UAV_ROUTE",
                    uav.uid,
                    json.dumps(route_data, ensure_ascii=False),
                )
                current_batch.append(uav.uid)
                if len(current_batch) >= batch_size:
                    try:
                        pipeline.execute()
                    except Exception as e:
                        print(f"[Redis] 批量写入失败: {e}")
                        failed.extend(current_batch)
                    pipeline = self.redis_client.pipeline(transaction=False)
                    current_batch = []
            if current_batch:
                try:
                    pipeline.execute()
                except Exception as e:
                    print(f"[Redis] 批量写入失败: {e}")
                    failed.extend(current_batch)
            if not failed:
                break
        if failed:
            print(f"[Redis] ⚠️ 最终仍有 {len(failed)} 架写入失败")
        else:
            print(f"[Redis] ✅ 全部 {len(self.uav_data_list)} 架航线写入成功")

    def is_running(self) -> bool:
        return self.running

    def wait_until_done(self):
        """阻塞等待直到数据发送完毕或停止"""
        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass


def main():
    parser = argparse.ArgumentParser(description='场景化 Kafka 数据发射器')
    parser.add_argument('-f', '--file', action='append', help='指定 JSON 文件路径（可多次使用）')
    parser.add_argument('-s', '--scene', help='指定场景目录（加载目录下所有 JSON 文件）')
    parser.add_argument('--url', help='Kafka URL（默认从 env 读取）')
    parser.add_argument('--topic', default='uav_runtime_data', help='Kafka topic')
    parser.add_argument('--interval', type=int, default=1000, help='发射间隔（毫秒）')
    parser.add_argument('--timestamp-mode', default='replace', choices=['replace', 'align', 'preserve'],
                        help='时间戳处理模式')
    parser.add_argument('--loop', action='store_true', help='数据耗尽后循环发射')
    parser.add_argument('--debug-print-uav-ids', action='store_true', help='打印每次发射的无人机ID列表，默认关闭')
    parser.add_argument('--consume-trace', action='store_true', help='消费 uav_runtime_trace topic，默认关闭')

    args = parser.parse_args()

    if not args.file and not args.scene:
        parser.print_help()
        sys.exit(1)

    emitter = SceneEmitter(
        files=args.file,
        scene_dir=args.scene,
        kafka_url=args.url,
        topic=args.topic,
        interval_ms=args.interval,
        timestamp_mode=args.timestamp_mode,
        loop=args.loop,
        debug_print_uav_ids=args.debug_print_uav_ids,
        consume_trace=args.consume_trace,
    )

    emitter.start()

    try:
        emitter.wait_until_done()
    finally:
        if emitter.is_running():
            emitter.stop()

    print("\n✨ 程序结束")


if __name__ == '__main__':
    main()
