# -*- coding: utf-8 -*-
"""
统一仿真编排层 — SimulationManager

消除 main.py / run_kafka_alive.py / run_plan.py / web_server.py 中
重复的 DataSource/DataFlow 模式，统一管理三种仿真运行模式：

- "dynamic": Simulator 引擎实时生成飞行计划（原 main.py 逻辑）
- "replay":  预生成 JSON 数据回放（原 run_kafka_alive.py 逻辑）
- "plan":    Redis 飞行计划插值（原 run_plan.py 逻辑）

**关键约束**：
- 不改变 Redis key / Kafka topic / 消息格式
- 保持与旧版独立运行脚本的兼容（旧脚本仍可直接执行）
- 线程模型与现有一致（1 仿真线程 + 1 trace 消费线程）

用法:
    from config import load_config
    from sim_manager import SimulationManager

    cfg = load_config()
    mgr = SimulationManager(cfg)
    mgr.start(mode="dynamic", target_drones=100)
    ...
    mgr.stop()
"""

from __future__ import annotations

import copy
import traceback
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# 公共模块路径（database/ common/ 已从 utm_simulator/ 移出到项目根目录）
_database_path = os.path.join(_root, '..', 'database')
_common_path = os.path.join(_root, '..', 'common')
for _p in (_database_path, _common_path):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from redis_client import RedisClient
from kafka_proc import KafkaProducerClient, KafkaConsumerClient
from simulation_core import Simulator, UAV_IDENTIFIERS
from config import AppConfig, load_config
from log_setup import get_logger
from exceptions import SimulationError, StateError, StepError

logger = get_logger(__name__)

# ── 常量 ────────────────────────────────────────────────────────────
REDIS_FLIGHT_PLAN_KEY = "BIZ_DATA:UAV_ROUTE"
REDIS_AIRSPACE_KEY = "BIZ_DATA:AIRSPACE"
KAFKA_UAV_DATA_TOPIC = "uav_runtime_data"
KAFKA_TRACE_TOPIC = "uav_runtime_trace"

# ── 遥测字段默认值（与现有 main.py / run_plan.py 一致） ─────────────
TELEMETRY_DEFAULTS = {
    "uasOperationCategory": 1,
    "classification": 1,
    "rpsLocationType": 1,
    "rpsLongitude": 0.0,
    "rpsLatitude": 0.0,
    "rpsAltitude": 0.0,
    "coordinateSystemType": 0,
    "timestampAccuracy": 0,
    "horizontalAccuracy": 1.0,
    "verticalAccuracy": 1.0,
    "speedAccuracy": 1.0,
    "sourceType": 1,
    "active": 1,
    "addInf": {},
}


# =====================================================================
# SimulationManager
# =====================================================================

class SimulationManager:
    """统一仿真编排器。

    支持三种运行模式，统一管理 Redis/Kafka 客户端、仿真引擎、
    后台线程和运行状态。
    """

    def __init__(self, config: Optional[AppConfig] = None, log_callback=None) -> None:
        """
        Args:
            config: 应用配置。为 None 时自动从 env.py + 环境变量加载。
            log_callback: 可选，日志回调函数 func(msg: str)，用于桥接到 web 前端。
        """
        self.config = config or load_config()
        self._log_callback = log_callback

        # ── Redis / Kafka 客户端 ────────────────────────────────────
        self.redis = RedisClient(
            self.config.redis.host,
            str(self.config.redis.port_int),
            self.config.redis.password,
        )
        self.kafka_producer = KafkaProducerClient(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            bootstrap_servers_mirror=self.config.kafka.bootstrap_servers_mirror,
        )
        self.kafka_consumer = KafkaConsumerClient(
            bootstrap_servers=self.config.kafka.bootstrap_servers,
            group_id=f"utm_sim_mgr_{os.getpid()}",
            consume_from_latest_on_start=True,
        )
        self.kafka_consumer.subscribe([KAFKA_TRACE_TOPIC])

        # ── 运行状态 ────────────────────────────────────────────────
        self.mode: str = ""
        self._running = False
        self._lock = threading.Lock()
        self._start_time: float = 0.0
        self._tick_count: int = 0
        self._kafka_sent_total: int = 0
        self._errors: int = 0
        self._logs: List[str] = []
        self._trace_msg_count: int = 0

        # ── 后台线程 ────────────────────────────────────────────────
        self._sim_thread: Optional[threading.Thread] = None
        self._trace_thread: Optional[threading.Thread] = None

        # ── 模式特定数据 ────────────────────────────────────────────
        self.simulator: Optional[Simulator] = None           # dynamic 模式
        self._replay_index: Dict[str, List[dict]] = {}       # replay 模式
        self._replay_cursors: Dict[str, int] = {}            # replay 模式
        self._route_cache: List[Dict[str, Any]] = []         # replay 模式 Redis 航线缓存
        self._plans: Dict[str, Any] = {}                     # plan 模式: uid → RoutePlanSim
        self._plan_runner = None                             # plan 模式 PlanRunner 引用

        self._add_log("SimulationManager 初始化完成")
        logger.info(
            "SimulationManager init: redis=%s:%s kafka=%s mirror=%s",
            self.config.redis.host, self.config.redis.port_int,
            self.config.kafka.bootstrap_servers,
            self.config.kafka.bootstrap_servers_mirror or "(none)",
        )

    # ── 日志辅助 ────────────────────────────────────────────────────

    def _add_log(self, msg: str) -> None:
        """线程安全地添加运行日志，同时回调到 web 前端（若设置）。"""
        with self._lock:
            ts = time.strftime("%H:%M:%S")
            self._logs.append(f"[{ts}] {msg}")
            if len(self._logs) > 50:
                self._logs = self._logs[-50:]
        if self._log_callback:
            try:
                self._log_callback(msg)
            except Exception:
                pass

    # ── 生命周期 ────────────────────────────────────────────────────

    def start(
        self,
        mode: str = "dynamic",
        target_drones: Optional[int] = None,
        replay_data_file: Optional[str] = None,
        replay_route_file: Optional[str] = None,
    ) -> None:
        """启动仿真。

        Args:
            mode: 运行模式 ("dynamic" / "replay" / "plan")
            target_drones: 目标无人机架数（dynamic 模式，覆盖配置）
            replay_data_file: pre-generated kafka_data.json 路径（replay 模式）
            replay_route_file: pre-generated redis_route.json 路径（replay 模式）

        Raises:
            StateError: 仿真已在运行中
        """
        if self._running:
            raise StateError("仿真已在运行中，请先调用 stop()")

        self.mode = mode
        if target_drones is not None:
            self.config.simulation.target_drones = target_drones

        # 重置状态
        self._running = True
        self._start_time = time.time()
        self._tick_count = 0
        self._kafka_sent_total = 0
        self._errors = 0
        self._logs = []
        self._plans = {}

        # 模式特定初始化
        if mode == "dynamic":
            self._init_dynamic_mode()
        elif mode == "replay":
            self._init_replay_mode(replay_data_file, replay_route_file)
        elif mode == "plan":
            self._init_plan_mode()
        else:
            raise ValueError(f"未知运行模式: {mode}，有效值: dynamic / replay / plan")

        # 启动线程
        self._sim_thread = threading.Thread(target=self._sim_loop, daemon=True, name="sim-loop")
        self._sim_thread.start()
        self._trace_thread = threading.Thread(target=self._consume_trace, daemon=True, name="trace-cons")
        self._trace_thread.start()

        self._add_log(f"仿真已启动: 模式={mode}, 目标架数={self.config.simulation.target_drones}")
        logger.info("仿真启动 mode=%s drones=%d", mode, self.config.simulation.target_drones)

    def stop(self, timeout: float = 5.0) -> None:
        """停止仿真并清理资源。

        Args:
            timeout: 等待线程结束的超时时间（秒）
        """
        if not self._running:
            return

        self._add_log("正在停止仿真...")
        self._running = False

        # 等待线程结束
        for t in (self._sim_thread, self._trace_thread):
            if t and t.is_alive():
                t.join(timeout=timeout)

        # 清理 plan 模式资源
        if self.mode == "plan" and self._plan_runner:
            try:
                self._plan_runner.stop()
            except Exception:
                pass
            self._plan_runner = None

        # 关闭 Kafka
        try:
            self.kafka_consumer.close()
        except Exception:
            pass
        try:
            self.kafka_producer.close()
        except Exception:
            pass

        self._add_log("仿真已停止")
        logger.info("仿真停止 mode=%s ticks=%d sent=%d", self.mode, self._tick_count, self._kafka_sent_total)

    def get_status(self) -> Dict[str, Any]:
        """获取当前运行状态快照（线程安全）。

        Returns:
            状态字典（与 web_server API 格式一致）
        """
        with self._lock:
            active_drones = 0
            if self.mode == "dynamic" and self.simulator:
                active_drones = self.simulator.active_count
            elif self.mode == "replay":
                active_drones = len(self._replay_index)
            elif self.mode == "plan":
                active_drones = len(self._plans)

            kafka_ps = self._kafka_sent_total // max(self._tick_count, 1)

            return {
                "running": self._running,
                "mode": self.mode,
                "active_drones": active_drones,
                "kafka_msg_per_sec": kafka_ps,
                "uptime_sec": int(time.time() - self._start_time) if self._start_time else 0,
                "errors": self._errors,
                "redis_connected": self.redis.client is not None,
                "kafka_connected": self.kafka_producer.is_connected(),
                "logs": list(self._logs[-10:]),
            }

    def get_flight_plans(self) -> List[Dict[str, Any]]:
        """获取当前 Redis 中的飞行计划列表（供前端地图渲染）。

        Returns:
            飞行计划字典列表
        """
        plans = []
        try:
            all_data = self.redis.hgetall(REDIS_FLIGHT_PLAN_KEY)
        except Exception as e:
            logger.warning("读取 Redis 飞行计划失败: %s", e)
            return plans

        if not all_data:
            return plans

        for uid, raw in all_data.items():
            try:
                obj = json.loads(raw) if isinstance(raw, str) else raw
                plans.append(obj)
            except (json.JSONDecodeError, TypeError):
                continue

        return plans

    # ── 模式初始化 ──────────────────────────────────────────────────

    def _init_dynamic_mode(self) -> None:
        """动态仿真模式初始化：创建 Simulator，生成初始飞行计划，写入 Redis。"""
        sim_cfg = self.config.simulation
        self.simulator = Simulator(
            origin_lat=sim_cfg.sim_center_lat,
            origin_lon=sim_cfg.sim_center_lon,
            sim_radius_m=sim_cfg.sim_radius_m,
            uid_start_offset=sim_cfg.uid_start_offset,
        )

        # 循环生成初始批次飞行计划（generate_plan 每次只生成一个 FlightPlan）
        generated = 0
        for _ in range(sim_cfg.target_drones):
            plan = self.simulator.generate_plan()
            uid = plan.aircraft.uid.decode("utf-8")
            route_json = self._plan_to_route_json(plan)
            self.redis.hset(REDIS_FLIGHT_PLAN_KEY, uid, route_json)
            generated += 1

        self._add_log(f"动态仿真: 已生成 {generated} 架无人机飞行计划并写入 Redis")

        # 禁飞区（可选）
        self._nfz_list: List[Any] = []
        try:
            nfz_count = 3
            self._nfz_list = self.simulator.generate_nfzs(nfz_count)
            for nfz in self._nfz_list:
                nfz_json = self._nfz_to_json(nfz)
                nfz_id = nfz.uid.decode("utf-8") if isinstance(nfz.uid, bytes) else str(nfz.uid)
                self.redis.hset(REDIS_AIRSPACE_KEY, nfz_id, nfz_json)
            self._add_log(f"已生成 {len(self._nfz_list)} 个禁飞区")
        except Exception as e:
            logger.warning("禁飞区生成失败（非致命）: %s", e)

    def _init_replay_mode(
        self,
        data_file: Optional[str] = None,
        route_file: Optional[str] = None,
    ) -> None:
        """预生成注入模式初始化：加载 JSON 数据文件，写入 Redis 航线。"""
        mock_dir = os.path.join(_root, "..", "data", "mock")
        # 拼接完整路径：若传入的是纯文件名则拼接 mock_dir，绝对路径则直接使用
        if data_file:
            data_path = data_file if os.path.isabs(data_file) else os.path.join(mock_dir, data_file)
        else:
            data_path = os.path.join(mock_dir, "kafka_data.json")
        if route_file:
            route_path = route_file if os.path.isabs(route_file) else os.path.join(mock_dir, route_file)
        else:
            route_path = os.path.join(mock_dir, "redis_route.json")

        # 加载并写 Redis 航线
        if os.path.exists(route_path):
            with open(route_path, "r", encoding="utf-8") as f:
                route_list = json.load(f)
            self._route_cache = copy.deepcopy(route_list)
            for item in route_list:
                key = item.get("key")
                value = item.get("value")
                if key and value:
                    val = copy.deepcopy(value)
                    self._shift_plan_times(val)
                    self.redis.hset(REDIS_FLIGHT_PLAN_KEY, key, json.dumps(val, ensure_ascii=False))
            self._add_log(f"已从 {os.path.basename(route_path)} 写入 {len(route_list)} 条航线到 Redis")
        else:
            self._add_log(f"航线数据文件不存在: {route_path} — 请先生成或上传数据文件")

        # 加载遥测数据并按 UID 建索引
        self._replay_index = {}
        self._replay_cursors = {}
        if os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                kafka_data = json.load(f)
            for msg in kafka_data:
                uid = msg.get("uniqueProductIdentificationCode", "unknown")
                self._replay_index.setdefault(uid, []).append(msg)
            self._replay_cursors = {uid: 0 for uid in self._replay_index}
            self._add_log(f"已从 {os.path.basename(data_path)} 加载 {len(kafka_data)} 条遥测 ({len(self._replay_index)} 架无人机)")
        else:
            self._add_log(f"遥测数据文件不存在: {data_path} — 请先生成或上传数据文件")

    def _init_plan_mode(self) -> None:
        """Redis 计划插值模式：先加载航线文件写入 Redis，再通过 PlanRunner 后台线程插值。

        PlanRunner 依赖 Redis 中已有飞行计划，因此需要先播种数据。
        """
        # 先尝试加载默认航线文件写入 Redis
        mock_dir = os.path.join(_root, "..", "data", "mock")
        default_route = os.path.join(mock_dir, "redis_route.json")
        if os.path.exists(default_route):
            try:
                with open(default_route, "r", encoding="utf-8") as f:
                    route_list = json.load(f)
                now = time.time()
                written = 0
                for item in route_list:
                    key = item.get("key")
                    value = item.get("value")
                    if key is None or value is None:
                        continue
                    val = copy.deepcopy(value)
                    self._shift_plan_times(val)
                    self.redis.hset(REDIS_FLIGHT_PLAN_KEY, key, json.dumps(val, ensure_ascii=False))
                    written += 1
                self._add_log(f"plan 模式: 已从 redis_route.json 写入 {written} 条航线到 Redis")
            except Exception as e:
                self._add_log(f"plan 模式: 加载航线文件失败: {e}")
        else:
            self._add_log("plan 模式: 默认航线文件不存在，尝试从 Redis 读取已有数据")

        try:
            from tools.run_plan import PlanRunner
        except ImportError as e:
            raise SimulationError(f"无法导入 run_plan.PlanRunner: {e}")

        self._plan_runner = PlanRunner(log_callback=self._add_log)
        self._plan_runner.start_background()
        self._add_log("Redis 计划插值模式已初始化，后台线程已启动")

    # ── 主循环 ──────────────────────────────────────────────────────

    def _sim_loop(self) -> None:
        """仿真主循环（后台线程）。严格每秒执行一次 tick。"""
        logger.info("仿真主循环启动 mode=%s", self.mode)
        while self._running:
            t0 = time.perf_counter()
            try:
                self._tick_count += 1
                if self.mode == "dynamic":
                    self._tick_dynamic()
                elif self.mode == "replay":
                    self._tick_replay()
                elif self.mode == "plan":
                    self._tick_plan()
            except Exception as e:
                self._errors += 1
                tb = traceback.format_exc()
                logger.error("仿真 tick 异常: %s", e, exc_info=True)
                self._add_log(f"仿真步进错误: {e}")

            elapsed = time.perf_counter() - t0
            sleep_for = max(0.0, 1.0 - elapsed)
            if sleep_for < 0.001 and self._tick_count % 60 == 0:
                logger.warning("仿真 tick 耗时过长: %.3fs，可能超出 1s 周期", elapsed)
            time.sleep(sleep_for)

        logger.info("仿真主循环退出 mode=%s ticks=%d", self.mode, self._tick_count)

    # ── Dynamic 模式 tick ───────────────────────────────────────────

    def _tick_dynamic(self) -> None:
        """动态仿真模式每秒推进（原 main.py DataSource 逻辑）。"""
        if not self.simulator:
            return

        # 步进仿真（step() 内部自动清理 state==5 的 agent 到 last_finished_uids）
        telemetry_list = self.simulator.step(1.0)

        # 打印已降落的无人机
        for uid in self.simulator.last_finished_uids:
            self._add_log(f"无人机 {uid} 已降落，从仿真移除")

        # 补充新无人机维持目标架数
        sim_cfg = self.config.simulation
        active_count = len(self.simulator.agents)
        if active_count < sim_cfg.target_drones:
            need = sim_cfg.target_drones - active_count
            for _ in range(need):
                plan = self.simulator.generate_plan()
                uid = plan.aircraft.uid.decode("utf-8")
                route_json = self._plan_to_route_json(plan)
                self.redis.hset(REDIS_FLIGHT_PLAN_KEY, uid, route_json)
                self._add_log(f"新无人机 {uid} 加入仿真")

        # 发送遥测到 Kafka
        kafka_msgs = self._telemetry_list_to_kafka(telemetry_list)
        if kafka_msgs:
            self.kafka_producer.send_bulk(kafka_msgs, KAFKA_UAV_DATA_TOPIC)
            self._kafka_sent_total += len(kafka_msgs)
            if self._tick_count % 30 == 0:
                self._add_log(f"动态仿真: {len(kafka_msgs)} 条遥测, 累计 {self._kafka_sent_total} 条")
            # 连接健康检查（每 30 tick）
            if self._tick_count % 30 == 0:
                r_ok = self.redis.client is not None
                k_ok = self.kafka_producer.is_connected()
                if not r_ok or not k_ok:
                    self._add_log(f"连接异常: Redis={'OK' if r_ok else 'DOWN'} Kafka={'OK' if k_ok else 'DOWN'}")

    # ── Replay 模式 tick ────────────────────────────────────────────

    def _tick_replay(self) -> None:
        """预生成注入模式每秒回放（原 run_kafka_alive.py 逻辑）。"""
        if not self._replay_index:
            return

        records = []
        now_ms = int(time.time() * 1000)

        for uid, msgs in self._replay_index.items():
            cursor = self._replay_cursors.get(uid, 0)
            if cursor >= len(msgs):
                # 一轮结束 → 重置游标并刷新 Redis 航线
                self._replay_cursors[uid] = 0
                cursor = 0
                self._refresh_single_redis_route(uid)

            msg = dict(msgs[cursor])
            msg["timestamp"] = now_ms
            records.append(msg)
            self._replay_cursors[uid] = cursor + 1

        if records:
            self.kafka_producer.send_bulk(records, KAFKA_UAV_DATA_TOPIC)
            self._kafka_sent_total += len(records)
            if self._tick_count % 30 == 0:
                self._add_log(f"Replay: {len(records)} 条/{len(self._replay_index)} 架, 累计 {self._kafka_sent_total} 条")

    def _refresh_single_redis_route(self, uid: str) -> None:
        """某架机遥测跑完一轮后，按缓存刷新该机 Redis 航线（时间平移）。"""
        for item in self._route_cache:
            if item.get("key") != uid:
                continue
            value = item.get("value")
            if value is None:
                return
            val = copy.deepcopy(value)
            self._shift_plan_times(val)
            self.redis.hset(REDIS_FLIGHT_PLAN_KEY, uid, json.dumps(val, ensure_ascii=False))
            self._add_log(f"无人机 {uid} 航线已刷新（新起飞时间），开始新一轮飞行")
            return

    # ── Plan 模式 tick ──────────────────────────────────────────────

    def _tick_plan(self) -> None:
        """Redis 计划插值模式（原 run_plan.py PlanRunner 逻辑）。

        PlanRunner 有自己的独立时间循环，本方法桥接状态。
        """
        if self._plan_runner:
            # 从 PlanRunner 读取当前计划数量作为活跃无人机数
            try:
                plans = getattr(self._plan_runner, "_plans", {})
                self._plans = plans
                if self._tick_count % 30 == 0:
                    self._add_log(f"Plan模式: {len(plans)} 个活跃计划")
            except Exception:
                pass

    # ── Trace 消费（共享）────────────────────────────────────────────

    def _consume_trace(self) -> None:
        """消费 uav_runtime_trace topic（共享逻辑，三种模式通用）。

        从 Kafka 读取 trace 消息 → 按 redisKey 查 Redis → 过滤打印。
        """
        while self._running:
            try:
                messages = self.kafka_consumer.poll(timeout_ms=500)
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue
                    redis_key = msg.get("redisKey") or msg.get("redis_key")
                    if not redis_key:
                        continue

                    value = self.redis.get_value_by_key(redis_key)
                    if value is None:
                        continue

                    # 获取当前活跃 UID 集合用于过滤
                    allowed: Set[str] = set()
                    if self.mode == "dynamic" and self.simulator:
                        allowed = set(self.simulator.agents.keys())
                    elif self.mode == "replay":
                        allowed = set(self._replay_index.keys())
                    elif self.mode == "plan" and self._plan_runner:
                        try:
                            allowed = self._plan_runner._allowed_uids_set()
                        except Exception:
                            pass

                    # 过滤并打印
                    if isinstance(value, list):
                        filtered = [
                            p for p in value
                            if p.get("uniqueProductIdentificationCode") in allowed
                        ] if allowed else value
                        if filtered:
                            self._trace_msg_count += 1
                            if self._trace_msg_count % 50 == 0:
                                self._add_log(f"Trace消费: 累计 {self._trace_msg_count} 条, 最近 {len(filtered)} 条")
            except Exception as e:
                pass  # 非致命
            time.sleep(0.05)

    # ── 数据转换辅助（与现有格式一致）────────────────────────────────

    def _plan_to_route_json(self, plan) -> str:
        """将 FlightPlan 转为 Redis 航线 JSON 字符串（与 simulation_core 一致）。"""
        route_list = []
        wps_count = getattr(plan.data.traj, "count", 0)
        for i in range(wps_count - 1):
            w0 = plan.data.traj.wps[i]
            w1 = plan.data.traj.wps[i + 1]
            route_list.append({
                "sequence": i,
                "type": 2,
                "segmentStartLon": w0.point.lon,
                "segmentStartLat": w0.point.lat,
                "segmentEndLon": w1.point.lon,
                "segmentEndLat": w1.point.lat,
                "segmentStartHeight": w0.point.alt,
                "segmentEndHeight": w1.point.alt,
                "segmentProtectHeight": getattr(w1, "segmentVerticalleight", 50.0),
                "segmentProtectHeightType": getattr(w1, "segmentProtectHeightType", 1),
                "segmentWidth": getattr(w1, "segmentWidth", 100.0),
            })

        flight_plan = {
            "flightPlanId": 1,
            "planTakeoffTime": plan.start_time,
            "planLandTime": plan.end_time,
            "flightTaskId": 1,
            "flightTaskName": "test",
            "routeList": route_list,
        }
        obj = {
            "uniqueProductIdentificationCode": plan.aircraft.uid.decode("utf-8"),
            "flightPlanList": [flight_plan],
        }
        return json.dumps(obj, ensure_ascii=False)

    def _nfz_to_json(self, nfz) -> str:
        """将禁飞区对象转为标准空域 JSON 字符串。"""
        nfz_uid = nfz.uid.decode("utf-8").rstrip("\x00") if isinstance(nfz.uid, bytes) else str(nfz.uid)
        obj = {
            "airspaceId": nfz_uid,
            "spcNo": getattr(nfz, "spcNo", nfz_uid),
            "name": getattr(nfz, "name", f"动态禁飞区_{nfz_uid}"),
            "typeCode": getattr(nfz, "type", 1),
            "status": getattr(nfz, "status", 1),
            "times": [
                {"startTime": getattr(nfz, "start_time", 0), "endTime": getattr(nfz, "end_time", 0)}
            ],
            "usagePurpose": getattr(nfz, "usagePurpose", ""),
            "lowestHeight": nfz.geometry.min_alt if hasattr(nfz, "geometry") else 0.0,
            "highestHeight": nfz.geometry.max_alt if hasattr(nfz, "geometry") else 500.0,
            "capacity": getattr(nfz, "capacity", 0),
            "monitorAbility": getattr(nfz, "monitorAbility", 1),
            "polygon": getattr(nfz, "polygon", {}),
        }
        return json.dumps(obj, ensure_ascii=False)

    def _telemetry_list_to_kafka(self, telemetry_list: list) -> List[Dict[str, Any]]:
        """将 Simulator 遥测列表转为 Kafka 消息格式（与 main.py 一致）。

        simulator.step() 返回格式: [{"current": TelemetryData, "history": [...]}, ...]
        需要从 item["current"] 提取 TelemetryData 对象。
        """
        msgs = []
        now_ms = int(time.time() * 1000)
        for item in telemetry_list:
            t = item["current"]  # 从包装字典中提取 TelemetryData
            uid_str = t.uid.decode("utf-8").rstrip("\x00") if isinstance(t.uid, bytes) else str(t.uid)
            msg = dict(TELEMETRY_DEFAULTS)
            msg.update({
                "uniqueProductIdentificationCode": uid_str,
                "realNameRegistrationSign": getattr(t, "realNameRegistrationSign", uid_str),
                "longitude": t.location.lon,
                "latitude": t.location.lat,
                "trackAngle": t.heading,
                "speed": t.speed,
                "geodeticAltitude": t.location.alt,
                "verticalSpeed": t.verticalSpeed,
                "relativeAltitude": t.relativeAltitude,
                "ressureAltitude": t.ressureAltitude,
                "operatingStatus": t.operatingStatus,
                "timestamp": now_ms,
                "sourceType": getattr(t, "sourceType", 1),
            })
            msgs.append(msg)
        return msgs

    def _shift_plan_times(self, value: dict) -> float:
        """将飞行计划的起降时间平移到当前时刻（保持飞行时长不变）。

        Args:
            value: flightPlanList 条目的父级 value 字典

        Returns:
            当前时间戳，供日志使用
        """
        now = time.time()
        for plan in value.get("flightPlanList", []):
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


# =====================================================================
# 便捷入口：main.py 命令行启动
# =====================================================================

def run_main() -> None:
    """命令行入口：从配置加载并以 dynamic 模式启动。

    用法: python -m sim_manager [--mode dynamic|replay|plan] [--count 100]
    """
    import argparse

    parser = argparse.ArgumentParser(description="UTM 模拟器统一入口")
    parser.add_argument("--mode", choices=["dynamic", "replay", "plan"], default="dynamic")
    parser.add_argument("--count", type=int, default=None, help="目标无人机架数")
    parser.add_argument("--data-file", type=str, default=None, help="replay 模式数据文件")
    parser.add_argument("--route-file", type=str, default=None, help="replay 模式航线文件")
    args = parser.parse_args()

    cfg = load_config()
    if args.count is not None:
        cfg.simulation.target_drones = args.count

    mgr = SimulationManager(cfg)
    mgr.start(
        mode=args.mode,
        target_drones=args.count,
        replay_data_file=args.data_file,
        replay_route_file=args.route_file,
    )

    print(f"UTM 模拟器已启动: mode={args.mode} drones={cfg.simulation.target_drones}")
    print("按 Ctrl+C 停止...")

    try:
        while mgr._running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到停止信号")
    finally:
        mgr.stop()
        print("模拟器已退出")


if __name__ == "__main__":
    run_main()
