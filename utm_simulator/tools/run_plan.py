# -*- coding: utf-8 -*-
"""
每分钟从 Redis 读取 BIZ_DATA:UAV_ROUTE，将 flightPlanList 中 planLandTime 大于当前时间的计划并入 planList；
按航线插值生成遥测，每秒批量发送到 Kafka。
当前时间超过某条计划的 planLandTime 时结束该计划并从 planList 移除；Redis 刷新时发现新计划则自动加入。
同时消费 uav_runtime_trace，按 redisKey 回查 Redis 并记录（与 run_kafka_alive 日志风格一致）。
"""
from __future__ import annotations

import copy
import json
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from kafka_proc import KafkaConsumerClient, KafkaProducerClient
from redis_client import RedisClient
from env import redis_ip, redis_port, redis_password, kafka_url
import env as _env

REDIS_FLIGHT_PLAN_KEY = "BIZ_DATA:UAV_ROUTE"
REDIS_TELEMETRY_KEY = "BIZ_DATA:UAV_TELEMETRY"  # dynamic 模式遥测桥接
KAFKA_UAV_DATA_TOPIC = "uav_runtime_data"
KAFKA_TRACE_TOPIC = "uav_runtime_trace"
FETCH_INTERVAL_SEC = 60.0
TICK_INTERVAL_SEC = 1.0


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _horiz_dist_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """两点间水平距离近似（米）。"""
    mx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) * 0.5)) * 111320.0
    my = (lat2 - lat1) * 110540.0
    return math.hypot(mx, my)


def _bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """方位角（度），北为 0，顺时针。"""
    d_lon = math.radians(lon2 - lon1)
    r1 = math.radians(lat1)
    r2 = math.radians(lat2)
    x = math.sin(d_lon) * math.cos(r2)
    y = math.cos(r1) * math.sin(r2) - math.sin(r1) * math.cos(r2) * math.cos(d_lon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


class RoutePlanSim:
    """单条飞行计划：按 routeList 折线插值，时间与路径长度成比例。"""

    def __init__(self, uid: str, registered_code: str, plan: Dict[str, Any]) -> None:
        self.uid = uid
        self.registered_code = registered_code or uid
        self.flight_plan_id = plan.get("flightPlanId")
        t0 = _to_float(plan.get("planTakeoffTime"))
        t1 = _to_float(plan.get("planLandTime"))
        self.takeoff = t0 if t0 is not None else 0.0
        self.land = t1 if t1 is not None else self.takeoff
        raw_routes = plan.get("routeList") or []
        self._segments: List[Dict[str, Any]] = sorted(raw_routes, key=lambda s: s.get("sequence", 0))
        self._seg_hlen: List[float] = []
        self._seg_start: List[Tuple[float, float, float]] = []
        self._seg_end: List[Tuple[float, float, float]] = []
        self._total_h = 0.0
        self._build_segments()

    def _build_segments(self) -> None:
        for seg in self._segments:
            slon = float(seg.get("segmentStartLon", 0))
            slat = float(seg.get("segmentStartLat", 0))
            elon = float(seg.get("segmentEndLon", 0))
            elat = float(seg.get("segmentEndLat", 0))
            sa = float(seg.get("segmentStartHeight", 0))
            ea = float(seg.get("segmentEndHeight", 0))
            h = _horiz_dist_m(slon, slat, elon, elat)
            self._seg_hlen.append(h)
            self._seg_start.append((slon, slat, sa))
            self._seg_end.append((elon, elat, ea))
            self._total_h += h
        if self._total_h <= 0 and self._segments:
            self._total_h = float(len(self._segments))

    def sample(self, t: float) -> Dict[str, Any]:
        """在给定时刻采样：经纬高、航迹角、地速、垂直速度、运行状态。"""
        duration = max(self.land - self.takeoff, 1e-6)
        if t < self.takeoff:
            s0 = self._segments[0] if self._segments else {}
            return {
                "lon": float(s0.get("segmentStartLon", 0)),
                "lat": float(s0.get("segmentStartLat", 0)),
                "alt": float(s0.get("segmentStartHeight", 0)),
                "heading": 0.0,
                "speed": 0.0,
                "v_speed": 0.0,
                "operating_status": 1,
            }
        if t >= self.land:
            last = self._segments[-1] if self._segments else {}
            lon = float(last.get("segmentEndLon", 0))
            lat = float(last.get("segmentEndLat", 0))
            return {
                "lon": lon,
                "lat": lat,
                "alt": float(last.get("segmentEndHeight", 0)),
                "heading": _bearing_deg(
                    float(last.get("segmentStartLon", 0)),
                    float(last.get("segmentStartLat", 0)),
                    lon, lat,
                ),
                "speed": 0.0,
                "v_speed": 0.0,
                "operating_status": 0,
            }

        u = max(0.0, min(1.0, (t - self.takeoff) / duration))
        dist_target = u * self._total_h
        acc = 0.0
        seg_idx = 0
        local = 0.0
        for i, hlen in enumerate(self._seg_hlen):
            if hlen + acc < dist_target - 1e-12 and i < len(self._seg_hlen) - 1:
                acc += hlen
                continue
            seg_idx = i
            local = max(0.0, min(1.0, (dist_target - acc) / hlen if hlen > 1e-6 else 0.0))
            break

        s_lon, s_lat, s_a = self._seg_start[seg_idx]
        e_lon, e_lat, e_a = self._seg_end[seg_idx]
        lon = s_lon + local * (e_lon - s_lon)
        lat = s_lat + local * (e_lat - s_lat)
        alt = s_a + local * (e_a - s_a)
        seg_h = self._seg_hlen[seg_idx] if self._seg_hlen else 1.0
        seg_time = max(duration * (seg_h / self._total_h) if self._total_h > 1e-6 else duration / max(len(self._seg_hlen), 1), 1e-6)
        return {
            "lon": lon,
            "lat": lat,
            "alt": alt,
            "heading": _bearing_deg(s_lon, s_lat, e_lon, e_lat),
            "speed": seg_h / seg_time,
            "v_speed": (e_a - s_a) / seg_time,
            "operating_status": 2,
        }


def _telemetry_dict(uid: str, registered_code: str, samp: Dict[str, Any], now_ms: int) -> Dict[str, Any]:
    """与 mock/kafka_data.json、run_kafka_alive 字段风格一致。"""
    return {
        "uniqueProductIdentificationCode": uid,
        "realNameRegistrationSign": registered_code,
        "uasOperationCategory": 1,
        "classification": 1,
        "rpsLocationType": 1,
        "rpsLongitude": 0,
        "rpsLatitude": 0,
        "rpsAltitude": 0,
        "longitude": samp["lon"],
        "latitude": samp["lat"],
        "trackAngle": samp["heading"],
        "speed": samp["speed"],
        "geodeticAltitude": samp["alt"],
        "verticalSpeed": samp["v_speed"],
        "relativeAltitude": 0.0,
        "pressureAltitude": 0.0,
        "operatingStatus": samp["operating_status"],
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1,
        "verticalAccuracy": 0,
        "speedAccuracy": 0,
        "timestamp": now_ms,
        "timestampAccuracy": 0,
        "sourceType": 1,
        "addInf": {},
        "active": 1,
    }


class PlanRunner:
    """维护 planList，定时拉 Redis，每秒发送遥测，并消费 uav_runtime_trace。"""

    def __init__(self, log_callback=None) -> None:
        self.redis_client = RedisClient(redis_ip, redis_port, redis_password)
        self.kafka_producer = KafkaProducerClient(
            kafka_url, bootstrap_servers_mirror=getattr(_env, "kafka_url2", None)
        )
        self.kafka_consumer = KafkaConsumerClient(
            bootstrap_servers=kafka_url,
            group_id=f"utm_run_plan_trace_{os.getpid()}",
            consume_from_latest_on_start=True,
        )
        self.kafka_consumer.subscribe([KAFKA_TRACE_TOPIC])
        self._plans: Dict[str, RoutePlanSim] = {}
        self._lock = threading.Lock()
        self.running = True
        self._log_callback = log_callback
        self._threads: List[threading.Thread] = []
        self._selected_uids: Optional[Set[str]] = None  # 航线白名单过滤

    def _log(self, msg: str) -> None:
        """日志输出：优先回调到前端，否则打印到 stdout。"""
        if self._log_callback:
            try:
                self._log_callback(msg)
            except Exception:
                pass
        else:
            print(msg)

    def __del__(self) -> None:
        if getattr(self, "kafka_consumer", None):
            try:
                self.kafka_consumer.close()
            except Exception:
                pass

    def _allowed_uids_set(self) -> Set[str]:
        with self._lock:
            return {p.uid for p in self._plans.values()}

    def _shift_and_write_plan(self, uid: str, obj: Dict[str, Any]) -> None:
        """将 obj 中所有 flightPlan 的起降时间平移到当前时刻起飞（保持飞行时长），写回 Redis。
        下游 UTM 检测到 Redis 写入后才会激活追踪并响应遥测。"""
        now = time.time()
        for plan in obj.get("flightPlanList") or []:
            takeoff = _to_float(plan.get("planTakeoffTime"))
            land = _to_float(plan.get("planLandTime"))
            if takeoff is not None and land is not None:
                duration = land - takeoff
                plan["planTakeoffTime"] = now
                plan["planLandTime"] = now + duration
        try:
            self.redis_client.hset(
                REDIS_FLIGHT_PLAN_KEY, uid,
                json.dumps(obj, ensure_ascii=False)
            )
            print(f"已刷新 Redis 航线: {uid}，planTakeoffTime={now:.0f}")
        except Exception as e:
            print(f"写回 Redis 失败 uid={uid}: {e}")

    def merge_from_redis(self) -> None:
        """读取 Redis 中所有 UAV 航线，将未着陆计划加入 planList（已存在则跳过）。
        新计划加入时平移起降时间并写回 Redis，以触发下游 UTM 激活追踪。"""
        now = time.time()
        try:
            data = self.redis_client.hgetall(REDIS_FLIGHT_PLAN_KEY)
        except Exception as e:
            print(f"Redis HGETALL 失败: {e}")
            return
        if not data:
            print("Redis HGETALL 为空或键不存在")
            return
        added = 0
        with self._lock:
            for uid, raw in data.items():
                if not raw:
                    continue
                # 白名单过滤：若设置了 selected_uids，则仅处理列表中的 UID
                if self._selected_uids is not None and uid not in self._selected_uids:
                    continue
                try:
                    obj = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                reg = obj.get("uniqueProductIdentificationCode") or uid
                # 收集该 uid 下所有未加入且有效的 fp_id
                new_fp_ids: List[int] = []
                for idx, plan in enumerate(obj.get("flightPlanList") or []):
                    if not isinstance(plan, dict):
                        continue
                    land = _to_float(plan.get("planLandTime"))
                    if land is None or land <= now:
                        continue
                    fp_id = plan.get("flightPlanId", idx)
                    if f"{uid}:{fp_id}" in self._plans:
                        continue
                    if not plan.get("routeList"):
                        print(f"跳过无 routeList 的计划: {uid}:{fp_id}")
                        continue
                    new_fp_ids.append(fp_id)
                if not new_fp_ids:
                    continue
                # 平移起降时间写回 Redis，触发下游 UTM 激活追踪
                self._shift_and_write_plan(uid, obj)
                # obj 内 flightPlanList 已被 _shift_and_write_plan 原地更新
                fp_map = {p.get("flightPlanId"): p for p in obj.get("flightPlanList") or [] if isinstance(p, dict)}
                for fp_id in new_fp_ids:
                    plan_use = fp_map.get(fp_id)
                    if plan_use is None:
                        continue
                    plan_use.setdefault("flightPlanId", fp_id)
                    key = f"{uid}:{fp_id}"
                    self._plans[key] = RoutePlanSim(str(uid), str(reg), plan_use)
                    added += 1
        if added:
            print(f"本轮从 Redis 新加入 {added} 条计划，当前共 {len(self._plans)} 条")

    def _remove_expired(self) -> None:
        now = time.time()
        with self._lock:
            to_del = [k for k, p in self._plans.items() if now > p.land]
            for k in to_del:
                del self._plans[k]
                print(f"计划已结束并移除: {k}")

    def tick_send(self) -> None:
        """移除已到期计划后，为剩余计划各采样一条遥测并批量发送；
        同时转发 dynamic 模式写入 Redis 的遥测数据到 Kafka。
        """
        self._remove_expired()
        now = time.time()
        now_ms = int(now * 1000)
        with self._lock:
            plans = list(self._plans.values())
        batch: List[Dict[str, Any]] = [
            _telemetry_dict(sim.uid, sim.registered_code, sim.sample(now), now_ms)
            for sim in plans
        ]

        # ── 转发 dynamic 模式遥测（Redis → Kafka 桥接） ──────────────
        # dynamic 模式下 SimulationManager 不直接使用 kafka-python
        # （Windows 上其后台 I/O 线程与 Simulator ctypes 并发会 C-level 崩溃），
        # 改为写遥测到 Redis，由本 PlanRunner tick 统一转发。
        try:
            raw = self.redis_client.client.get(REDIS_TELEMETRY_KEY)
            if raw:
                dyn_batch = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                if isinstance(dyn_batch, list) and dyn_batch:
                    batch.extend(dyn_batch)
                self.redis_client.client.delete(REDIS_TELEMETRY_KEY)
        except Exception:
            pass

        if batch:
            self.kafka_producer.send_bulk(batch, KAFKA_UAV_DATA_TOPIC)

    def _watch_redis_loop(self) -> None:
        """监听 BIZ_DATA:UAV_ROUTE keyspace 变动，有写入立即合并计划；
        同时每分钟兜底轮询一次，防止服务端未开启通知时事件丢失。"""
        pubsub = None
        channel = f"__keyspace@{self.redis_client.db}__:{REDIS_FLIGHT_PLAN_KEY}"
        try:
            # 尝试开启 hash 相关 keyspace 通知（服务端禁止 CONFIG SET 时会抛异常）
            self.redis_client.client.config_set("notify-keyspace-events", "KEh")
        except Exception:
            pass
        try:
            pubsub = self.redis_client.client.pubsub()
            pubsub.subscribe(channel)
            print(f"已订阅 Redis keyspace 通知: {REDIS_FLIGHT_PLAN_KEY}")
        except Exception as e:
            print(f"订阅 Redis keyspace 通知失败，降级为轮询: {e}")
            pubsub = None

        last_poll = time.time()
        try:
            while self.running:
                if pubsub:
                    try:
                        msg = pubsub.get_message(timeout=1.0)
                        if msg and msg.get("type") == "message":
                            try:
                                self.merge_from_redis()
                            except Exception as e:
                                print(f"刷新计划失败: {e}")
                            last_poll = time.time()
                    except Exception as e:
                        print(f"Redis keyspace 监听异常: {e}")
                else:
                    time.sleep(1.0)
                # 兜底轮询：未开启通知或事件丢失时保底
                if time.time() - last_poll >= FETCH_INTERVAL_SEC:
                    try:
                        self.merge_from_redis()
                    except Exception as e:
                        print(f"兜底轮询失败: {e}")
                    last_poll = time.time()
        finally:
            if pubsub:
                try:
                    pubsub.unsubscribe()
                    pubsub.close()
                except Exception:
                    pass

    def _tick_loop(self) -> None:
        """严格每秒调用一次 tick_send。"""
        while self.running:
            t0 = time.perf_counter()
            try:
                self.tick_send()
            except Exception as e:
                print(f"发送遥测失败: {e}")
            time.sleep(max(0.0, TICK_INTERVAL_SEC - (time.perf_counter() - t0)))

    def _consume_uav_runtime_trace(self) -> None:
        """消费 uav_runtime_trace：按 redisKey 从 Redis 查出数据并打印（参考 run_kafka_alive）。"""
        while self.running:
            try:
                messages = self.kafka_consumer.poll(timeout_ms=500)
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    redis_key = msg.get("redisKey") or msg.get("redis_key")
                    if not redis_key:
                        continue
                    value = self.redis_client.get_value_by_key(redis_key)
                    if value is None:
                        continue
                    allowed = self._allowed_uids_set()
                    if not allowed:
                        continue
                    if isinstance(value, list):
                        filtered = [
                            copy.deepcopy(p)
                            for p in value
                            if p.get("uniqueProductIdentificationCode") in allowed
                        ]
                    else:
                        continue
                    if not filtered:
                        continue
                    print(
                        f"\033[32m[uav_runtime_trace] {int(msg.get('timestamp', 0))} "
                        f"收到 {len(filtered)} 条\033[0m"
                    )
                    # 推送 kafka_trace 日志到 LogStreamer（前端 /logs 面板可见）
                    try:
                        from database.log_streamer import get_streamer
                        get_streamer().report_kafka_trace(len(filtered))
                    except Exception:
                        pass
            except Exception as e:
                print(f"消费 uav_runtime_trace 异常: {e}")
            time.sleep(0.05)

    def start_background(self, selected_uids: Optional[Set[str]] = None) -> None:
        """非阻塞启动：首次拉取 Redis 计划，启动所有后台线程后立即返回。
        供 web_server / sim_manager 等外部编排器调用。

        Args:
            selected_uids: 可选的白名单 UID 集合，仅注入这些航线；None 表示全部注入。
        """
        self.running = True
        self._selected_uids = selected_uids
        self.merge_from_redis()

        # watch 线程：监听 Redis 变动 + 60s 兜底轮询
        watch_thread = threading.Thread(target=self._watch_redis_loop, daemon=True, name="plan-watch")
        watch_thread.start()
        self._threads.append(watch_thread)

        # trace 消费线程
        trace_thread = threading.Thread(target=self._consume_uav_runtime_trace, daemon=True, name="plan-trace")
        trace_thread.start()
        self._threads.append(trace_thread)

        # tick 线程：每秒插值发送遥测
        tick_thread = threading.Thread(target=self._tick_loop, daemon=True, name="plan-tick")
        tick_thread.start()
        self._threads.append(tick_thread)

        self._log(f"Redis 计划插值模式已启动，当前 {len(self._plans)} 条活跃计划" +
                  (f"（已选 {len(selected_uids)} 条航线）" if selected_uids else "（全部航线）"))

    def stop(self) -> None:
        """优雅停止所有后台线程并清理连接。"""
        self.running = False
        for t in self._threads:
            t.join(timeout=3.0)
        self._threads.clear()
        if getattr(self, "kafka_consumer", None):
            try:
                self.kafka_consumer.close()
            except Exception:
                pass
        if getattr(self, "kafka_producer", None):
            try:
                self.kafka_producer.close()
            except Exception:
                pass
        self._log("Redis 计划插值模式已停止")

    def run(self) -> None:
        """首次立即拉 Redis，之后每分钟拉一次；后台消费 trace；主线程每秒发送遥测。"""
        self.merge_from_redis()
        watch_thread = threading.Thread(target=self._watch_redis_loop, daemon=True)
        watch_thread.start()
        trace_thread = threading.Thread(target=self._consume_uav_runtime_trace, daemon=True)
        trace_thread.start()
        print("run_plan 已启动：监听 Redis 变动实时刷新计划，每秒发送遥测，监听 uav_runtime_trace（Ctrl+C 退出）")
        try:
            self._tick_loop()
        except KeyboardInterrupt:
            print("收到停止信号")
        finally:
            self.running = False
            trace_thread.join(timeout=5)
            if getattr(self, "kafka_consumer", None):
                try:
                    self.kafka_consumer.close()
                except Exception:
                    pass
            if getattr(self, "kafka_producer", None):
                self.kafka_producer.close()
            print("程序已停止")


if __name__ == "__main__":
    print("main begin (run_plan 模式：按 Redis 飞行计划生成遥测，Ctrl+C 退出)")
    PlanRunner().run()
    print("app run exit")
