# -*- coding: utf-8 -*-
"""
utm_moc52 Web 可视化后端服务

提供 REST API + WebSocket，统一管理三种仿真运行模式的启停、状态查询、
配置管理和飞行计划数据查询。

不修改 simulation_core.py / redis_client.py / kafka_proc.py 核心逻辑，
通过导入现有模块驱动仿真。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import atexit
import signal
from typing import Any, Dict, List, Optional

# 确保项目根目录及各模块在 sys.path 中
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_root,
           os.path.join(_root, 'database'),
           os.path.join(_root, 'services'),
           os.path.join(_root, 'tools')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

from core.redis_client import RedisClient
from core.kafka_proc import KafkaConsumerClient, KafkaProducerClient
from common.config import load_config, AppConfig
from core.sim_manager import SimulationManager
import env as _env

# ── 环境管理器（惰性导入，避免 SQLite 初始化阻塞） ───────────────────
_env_mgr = None

def _get_env_mgr():
    global _env_mgr
    if _env_mgr is None:
        import env_manager as em
        _env_mgr = em
    return _env_mgr

# ── 桥接层导入（异步，避免阻塞启动时加载 tools 脚本） ────────────────
_data_gen_bridge = None

def _get_bridge():
    """延迟导入 web_data_gen_bridge（tools 脚本导入较重）。"""
    global _data_gen_bridge
    if _data_gen_bridge is None:
        import web_data_gen_bridge as bridge
        _data_gen_bridge = bridge
    return _data_gen_bridge

# ── 常量 ──────────────────────────────────────────────────────────
# 项目根目录（用于 send_from_directory 绝对路径，避免 CWD 依赖）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB_PAGES_DIR = os.path.join(_PROJECT_ROOT, "web", "pages")
REDIS_FLIGHT_PLAN_KEY = "BIZ_DATA:UAV_ROUTE"
REDIS_AIRSPACE_KEY = "BIZ_DATA:AIRSPACE"
KAFKA_UAV_DATA_TOPIC = "uav_runtime_data"
KAFKA_TRACE_TOPIC = "uav_runtime_trace"
DEFAULT_TARGET_DRONES = 1

# ── Flask 应用初始化 ───────────────────────────────────────────────
app = Flask(__name__, static_folder=os.path.join(_PROJECT_ROOT, "web", "static"), static_url_path="/static")
app.config["SECRET_KEY"] = "utm_moc52_web_secret"
# WebSocket 异步模式选择：
# - Windows: threading 模式 + simple-websocket（eventlet monkey_patch 会破坏 C++ Simulator 线程）
# - Linux/Docker: eventlet 模式（werkzeug 开发服务器对 WebSocket 支持不完整，threading 模式会 500）
_socket_async_mode = "eventlet" if os.name == "posix" else "threading"
print(f"[web_server] async_mode={_socket_async_mode} (os={os.name})", flush=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=_socket_async_mode)


# ── 全局异常处理：捕获所有未处理异常并返回 JSON ──────────────────────
#   避免 Werkzeug "write() before start_response" 错误
@app.errorhandler(Exception)
def _handle_all_errors(e):
    """全局异常处理器：确保所有错误都返回 JSON 格式，不暴露 HTML 500 页面。"""
    import traceback
    tb = traceback.format_exc()
    # 只打印前 200 字符避免日志刷屏
    print(f"[web_server] 未处理异常: {e}\n{tb[:500]}", flush=True)
    return jsonify({"success": False, "message": f"服务器内部错误: {e}"}), 500


@app.errorhandler(404)
def _handle_404(e):
    return jsonify({"success": False, "message": "路由不存在"}), 404


@app.errorhandler(405)
def _handle_405(e):
    return jsonify({"success": False, "message": "方法不允许"}), 405


# ── 全局状态（线程安全通过 _lock 保护） ────────────────────────────
_lock = threading.Lock()

def _get_default_config() -> Dict[str, Any]:
    """惰性获取默认配置，使用 load_config() 的完整优先级体系
    (env vars > config.json > env.py > 代码默认值)，避免 getattr 回退到 127.0.0.1。"""
    cfg = load_config()
    return {
        "mode": "dynamic",
        "target_drones": DEFAULT_TARGET_DRONES,
        "nfz_enabled": True,
        "nfz_count": 3,
        "redis_ip": cfg.redis.host,
        "redis_port": str(cfg.redis.port_int),
        "kafka_url": cfg.kafka.bootstrap_servers,
        "api_mode": False,
        "api_base_url": "https://dkkgsit-test.testdolphin.com",
        "scene_files": [],
        "scene_dir": None,
        "scene_interval": 1000,
        "timestamp_mode": "replace",
        "scene_loop": False,
        "plan_selected_uids": None,
        "plan_route_file": "redis_route.json",
        "data_file": "kafka_data.json",
        "route_file": "redis_route.json",
    }

_current_config: Dict[str, Any] = _get_default_config()

_runtime_state: Dict[str, Any] = {
    "running": False,
    "mode": "",
    "active_drones": 0,
    "kafka_msg_per_sec": 0,
    "uptime_sec": 0,
    "errors": 0,
    "redis_connected": False,
    "kafka_connected": False,
    "logs": [],  # 最近 50 条日志
}

# ── 仿真运行时对象（由 SimulationRunner 持有） ─────────────────────
_sim_runner: Optional["SimulationRunner"] = None


# ── 进程退出时清理桥接子进程 ──────────────────────────────────────
def _kill_telemetry_bridge() -> None:
    """终止遥测桥接子进程（atexit / signal handler）。"""
    try:
        if _sim_runner is not None:
            bridge = getattr(_sim_runner, "_telemetry_bridge", None)
            if bridge is not None and bridge.poll() is None:
                bridge.terminate()
                try:
                    bridge.wait(timeout=3)
                except Exception:
                    try:
                        bridge.kill()
                    except Exception:
                        pass
                print("[web_server] 已清理遥测桥接子进程", flush=True)
    except Exception:
        pass


def _graceful_shutdown():
    """优雅关闭：并行停止后台服务后退出。"""
    global _orchestrator
    print("[web_server] 优雅关闭中...", flush=True)

    # 0. 先停止所有活跃的场景执行（必须串行，确保场景线程收到停止信号）
    if _orchestrator is not None:
        try:
            stopped = _orchestrator.stop_all_scenes()
            if stopped:
                print(f"[web_server] 已发送 {stopped} 个场景停止信号", flush=True)
                time.sleep(1)  # 短暂等待场景线程响应停止信号
        except Exception as e:
            print(f"[web_server] 停止场景执行异常: {e}", flush=True)

    # 1+2. 并行停止编排器调度线程和仿真运行器（两者操作独立对象）
    def _stop_orch():
        if _orchestrator is not None:
            try:
                _orchestrator.stop()
            except Exception as e:
                print(f"[web_server] 停止编排器异常: {e}", flush=True)

    def _stop_runner():
        if _sim_runner is not None:
            try:
                _sim_runner.stop()
            except Exception as e:
                print(f"[web_server] 停止仿真异常: {e}", flush=True)

    threads = []
    for target in (_stop_orch, _stop_runner):
        t = threading.Thread(target=target, daemon=True)
        t.start()
        threads.append(t)

    # 等待所有停止操作完成，总超时 8 秒
    deadline = time.time() + 8.0
    for t in threads:
        remaining = max(0.0, deadline - time.time())
        t.join(timeout=remaining)

    # 3. 清理桥接进程（快速，不阻塞）
    _kill_telemetry_bridge()

    # 4. 关闭 MySQL 连接（快速）
    try:
        from mysql_db_manager import _mysql_client, _lock as _mdb_lock
        with _mdb_lock:
            if _mysql_client is not None:
                try:
                    _mysql_client.close()
                    print("[web_server] MySQL 连接已归还连接池", flush=True)
                except Exception:
                    pass
    except Exception:
        pass

    print("[web_server] 退出", flush=True)


def _on_exit_signal(signum, frame):
    """SIGINT/SIGTERM 处理：优雅关闭后强制退出。

    Windows 上信号处理器运行在独立线程中，sys.exit() 只退出该线程，
    必须用 os._exit() 强制终止整个进程。
    """
    print(f"\n[web_server] 收到信号 {signum}，清理资源...", flush=True)
    _graceful_shutdown()
    os._exit(0)


atexit.register(_kill_telemetry_bridge)
signal.signal(signal.SIGINT, _on_exit_signal)
signal.signal(signal.SIGTERM, _on_exit_signal)


_situation_monitor = None


def _get_situation_monitor():
    """惰性导入态势监控采集器，在仿真启动时开始采集下游 ATC 态势数据。"""
    global _situation_monitor
    if _situation_monitor is None:
        from situation_monitor import SituationMonitor
        _situation_monitor = SituationMonitor(
            base_url="wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp",
            streamer=_get_streamer(),
        )
    return _situation_monitor


_gateway_log_poller = None


def _get_gateway_log_poller():
    """惰性导入 TCP 网关日志轮询器，启动仿真后同步拉取通信日志。"""
    global _gateway_log_poller
    if _gateway_log_poller is None:
        from gateway_log_poller import GatewayLogPoller
        _gateway_log_poller = GatewayLogPoller(streamer=_get_streamer())
    return _gateway_log_poller


# ── 日志辅助 ──────────────────────────────────────────────────────
def _add_log(msg: str) -> None:
    """添加日志到运行时状态，保留最近 50 条。"""
    with _lock:
        entry = f"[{time.strftime('%H:%M:%S')}] {msg}"
        _runtime_state["logs"].append(entry)
        if len(_runtime_state["logs"]) > 50:
            _runtime_state["logs"] = _runtime_state["logs"][-50:]
    socketio.emit("log", {"message": msg})
    # 同步推送到日志采集器
    try:
        _get_streamer().push_sim_log(msg)
    except Exception as e:
        print(f"[web_server] 推送日志到 streamer 失败: {e}")


def _push_replay_once_trace(ds) -> None:
    """从 replay_once 模式的 DataSource 消费 trace 数据推送到前端 Layer 2。"""
    try:
        if hasattr(ds, 'kafka_consumer') and ds.kafka_consumer:
            trace_msgs = ds.kafka_consumer.poll(timeout_ms=100)
            if trace_msgs:
                socketio.emit("trace_data", {
                    "count": len(trace_msgs),
                    "data": list(trace_msgs.values()),
                    "key": "replay_once"
                })
    except Exception:
        pass  # trace 桥接失败不影响主循环


def _get_streamer():
    """惰性导入 log_streamer 单例，绑定 WebSocket 推送。"""
    import log_streamer as _ls
    s = _ls.get_streamer()
    if s._callback is None:
        def _ws_push(entry):
            socketio.emit("log_entry", entry)
            # 同时桥接 ws_captured_data 到 run.html 的 Layer 4（ATC WebSocket 前端数据）
            if entry.get("type") == "ws_captured_data":
                socketio.emit("ws_captured", {
                    "raw_type": entry.get("type_name", ""),
                    "message": entry.get("message", ""),
                    "detail": entry.get("detail"),
                })
        s._callback = _ws_push
        s.push("sim_status", "日志采集服务已就绪")
    return s


# ── Kafka 冲突告警消费者 ──────────────────────────────────────────
_collision_consumer = None
_collision_consumer_thread = None


def _start_collision_alarm_consumer():
    """消费 uav_collision_alarm topic 并推送到 LogStreamer + SocketIO。
    初始化在后台线程完成，避免 subscribe() 阻塞请求线程。"""
    global _collision_consumer, _collision_consumer_thread
    if _collision_consumer is not None:
        return

    def _init_and_poll():
        global _collision_consumer
        try:
            kafka_url = _current_config["kafka_url"]
            _collision_consumer = KafkaConsumerClient(
                bootstrap_servers=kafka_url,
                group_id=f"utm_web_collision_{os.getpid()}",
                consume_from_latest_on_start=True,
            )
            _collision_consumer.subscribe(["uav_collision_alarm"])
            print(f"[web_server] Kafka 冲突告警消费者已启动 (topic=uav_collision_alarm)")

            while _collision_consumer is not None:
                try:
                    messages = _collision_consumer.poll(timeout_ms=500)
                    for msg in messages:
                        # 告警消息可能是单个对象或数组（算法文档：数组，可同时包含多个告警）
                        items = msg if isinstance(msg, list) else [msg]
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            # 提取告警类型和无人机列表
                            # 算法文档格式: {"collisionShortAlert": {"uavList": [...], "status": ..., "alarmId": ...}}
                            alert_types = []
                            total_uavs = 0
                            for key in item:
                                alert_obj = item[key]
                                if isinstance(alert_obj, dict):
                                    alert_types.append(key)
                                    uav_list = alert_obj.get("uavList", [])
                                    total_uavs += len(uav_list) if isinstance(uav_list, list) else 0
                            if alert_types:
                                alert_type_str = ", ".join(alert_types)
                                try:
                                    _get_streamer().push(
                                        "kafka_collision_alarm",
                                        f"冲突告警: {alert_type_str} 涉及 {total_uavs} 架无人机",
                                        detail={"alert_types": alert_types, "uav_count": total_uavs, "raw": item}
                                    )
                                except Exception:
                                    pass
                                try:
                                    socketio.emit("collision_alarm", item)
                                except Exception:
                                    pass
                except Exception:
                    pass
                time.sleep(0.1)
        except Exception as e:
            print(f"[web_server] 冲突告警消费者启动失败: {e}")
            _collision_consumer = None

    _collision_consumer_thread = threading.Thread(
        target=_init_and_poll, daemon=True, name="collision-consumer"
    )
    _collision_consumer_thread.start()


# ==================== SimulationRunner ============================
class SimulationRunner:
    """仿真运行管理器：在后台线程中运行仿真，并推送状态到 WebSocket。

    通过 SimulationManager 统一编排 dynamic/replay/plan 三种模式。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.mode = config["mode"]
        self.target_drones = config["target_drones"]
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_count = 0  # 用于遥测桥接健康检查

        # 构建 AppConfig 供 SimulationManager 使用
        # 从 load_config() 加载基础配置（env.py + config.json + UTM_* 环境变量），
        # 再用前端配置覆盖 Redis/Kafka 连接参数，确保与 web 界面一致
        self._app_cfg = load_config()
        self._app_cfg.simulation.target_drones = self.target_drones
        # 覆盖为前端当前选择的连接参数（用户可能通过环境管理切换过）
        self._app_cfg.redis.host = config.get("redis_ip", self._app_cfg.redis.host)
        self._app_cfg.redis.port = int(config.get("redis_port", self._app_cfg.redis.port))
        self._app_cfg.redis.password = getattr(_env, "redis_password", self._app_cfg.redis.password)
        self._app_cfg.kafka.bootstrap_servers = config.get("kafka_url", self._app_cfg.kafka.bootstrap_servers)
        self._app_cfg.kafka.bootstrap_servers_mirror = getattr(_env, "kafka_url2", self._app_cfg.kafka.bootstrap_servers_mirror)

        # SimulationManager 实例（dynamic/replay 模式）
        self._sim_mgr: Optional[SimulationManager] = None
        # PlanRunner 实例（plan 模式，复用 run_plan.py 的独立线程模型）
        self._plan_runner = None
        # plan 模式：用户选择的航线 UID 白名单
        self._plan_selected_uids: Optional[set] = None
        # 遥测桥接子进程（dynamic 模式，Redis → Kafka 进程外转发）
        self._telemetry_bridge = None
        # replay_once / scene 模式资源引用（供 _cleanup() 访问）
        self._ds: Any = None           # replay_once 模式 DataSource
        self._emitter: Any = None      # scene 模式 SceneEmitter

        # 检查连接状态 + 设置日志监控
        try:
            test_redis = RedisClient(
                config["redis_ip"], config["redis_port"],
                getattr(_env, "redis_password", ""),
            )
            with _lock:
                _runtime_state["redis_connected"] = test_redis.client is not None
            # 将 Redis 客户端传给日志采集器用于航线/空域变更监控
            try:
                _get_streamer().set_redis_client(test_redis)
            except Exception:
                pass
        except Exception:
            with _lock:
                _runtime_state["redis_connected"] = False

        try:
            test_kafka = KafkaProducerClient(bootstrap_servers=config["kafka_url"])
            with _lock:
                _runtime_state["kafka_connected"] = test_kafka.is_connected()
            test_kafka.close()
        except Exception:
            with _lock:
                _runtime_state["kafka_connected"] = False

    def _init_plan_mode(self) -> None:
        """初始化 Redis 计划插值模式（复用 run_plan.py 的 PlanRunner 逻辑）。

        先从指定的航线文件加载飞行计划写入 Redis，再启动 PlanRunner 进行插值遥测。
        """
        from tools.run_plan import PlanRunner as _PlanRunner

        # 先加载航线文件写入 Redis（PlanRunner 依赖 Redis 中已有飞行计划）
        route_file = self.config.get("plan_route_file", "redis_route.json")
        mock_dir = os.path.join(_root, "..", "data", "mock")
        route_path = os.path.join(mock_dir, route_file) if not os.path.isabs(route_file) else route_file

        if os.path.exists(route_path):
            try:
                import json as _json
                import copy
                with open(route_path, "r", encoding="utf-8") as f:
                    route_list = _json.load(f)
                now = time.time()
                written = 0
                for item in route_list:
                    key = item.get("key")
                    value = item.get("value")
                    if key is None or value is None:
                        continue
                    val = copy.deepcopy(value)
                    # 平移起降时间到当前时刻
                    for plan in val.get("flightPlanList") or []:
                        try:
                            takeoff = plan.get("planTakeoffTime")
                            land = plan.get("planLandTime")
                            if takeoff is not None and land is not None:
                                diff = now - takeoff
                                plan["planTakeoffTime"] = now
                                plan["planLandTime"] = land + diff
                        except (TypeError, ValueError):
                            pass
                    client = RedisClient(
                        self.config["redis_ip"], self.config["redis_port"],
                        getattr(_env, "redis_password", ""),
                    )
                    client.hset(REDIS_FLIGHT_PLAN_KEY, key, _json.dumps(val, ensure_ascii=False))
                    written += 1
                _add_log(f"plan 模式: 已从 {os.path.basename(route_path)} 写入 {written} 条航线到 Redis")
            except Exception as e:
                _add_log(f"plan 模式: 加载航线文件失败: {e}")
        else:
            _add_log(f"plan 模式: 航线文件不存在 {route_path}，尝试从 Redis 读取已有数据")

        self._plan_runner = _PlanRunner(
            log_callback=_add_log,
            trace_callback=lambda d: socketio.emit("trace_data", d),
            telemetry_callback=lambda d: socketio.emit("telemetry_data", d),
        )
        # 读取用户选择的航线 UID 列表
        # None = 未做选择（全部航线），[] = 明确取消全选（不执行任何航线），[...] = 指定航线
        uids = self.config.get("plan_selected_uids", None)
        if uids is not None and len(uids) == 0:
            selected = set()   # 用户明确取消全选 → 空集合，不注入任何航线
        elif uids is not None and len(uids) > 0:
            selected = set(uids)
        else:
            selected = None    # uids is None → 全部航线
        self._plan_runner.start_background(selected_uids=selected)
        if selected is not None and len(selected) > 0:
            _add_log(f"Redis 计划插值模式已启动（已选 {len(selected)} 条航线），后台线程运行中")
        elif selected is not None and len(selected) == 0:
            _add_log("Redis 计划插值模式已启动（未选择任何航线），后台线程运行中")
        else:
            _add_log("Redis 计划插值模式已启动（全部航线），后台线程运行中")

    def _sim_loop(self) -> None:
        """仿真主循环（后台线程），通过 SimulationManager 或 PlanRunner 驱动。"""
        self._running = True
        self._start_time = time.time()

        if self.mode == "dynamic":
            # 使用 SimulationManager 统一编排（桥接日志到前端）
            self._sim_mgr = SimulationManager(self._app_cfg, log_callback=_add_log,
                                              trace_callback=lambda d: socketio.emit("trace_data", d),
                                              telemetry_callback=lambda d: socketio.emit("telemetry_data", d))
            self._sim_mgr.start(mode=self.mode, target_drones=self.target_drones)

            # dynamic 模式下 trace/conflict 消费者因 ctypes 兼容性限制被跳过，明确告知用户
            _add_log("ℹ️ 动态仿真模式：轨迹预测(trace)和冲突告警(collision)不可用，"
                     "因 kafka-python 与 ctypes 引擎线程安全限制。"
                     "如需查看完整日志，请使用 replay 或 plan 模式。")

            with _lock:
                _runtime_state["redis_connected"] = self._sim_mgr.redis.client is not None
                _runtime_state["kafka_connected"] = (self._sim_mgr.kafka_producer.is_connected() if self._sim_mgr.kafka_producer else False)

            while self._running and self._sim_mgr._running:
                try:
                    status = self._sim_mgr.get_status()
                    with _lock:
                        _runtime_state.update({
                            "active_drones": status["active_drones"],
                            "kafka_msg_per_sec": status["kafka_msg_per_sec"],
                            "uptime_sec": status["uptime_sec"],
                            "errors": status["errors"],
                        })
                        # 合并日志
                        for log_entry in status.get("logs", []):
                            if log_entry not in _runtime_state["logs"]:
                                _runtime_state["logs"].append(log_entry)
                                if len(_runtime_state["logs"]) > 50:
                                    _runtime_state["logs"] = _runtime_state["logs"][-50:]
                    # 每 30 秒检查遥测桥接子进程健康
                    self._tick_count += 1
                    if self._tick_count % 30 == 0:
                        self._check_telemetry_bridge()
                    self._push_status()
                except Exception as e:
                    _add_log(f"状态查询错误: {e}")
                time.sleep(1.0)

            # 停止 SimulationManager
            if self._sim_mgr:
                self._sim_mgr.stop()

        elif self.mode == "replay":
            # 使用 SimulationManager 统一编排，传入用户选择的文件参数
            self._sim_mgr = SimulationManager(self._app_cfg, log_callback=_add_log,
                                              trace_callback=lambda d: socketio.emit("trace_data", d),
                                              telemetry_callback=lambda d: socketio.emit("telemetry_data", d))
            self._sim_mgr.start(
                mode=self.mode,
                target_drones=self.target_drones,
                replay_data_file=self.config.get("data_file"),
                replay_route_file=self.config.get("route_file"),
            )

            with _lock:
                _runtime_state["redis_connected"] = self._sim_mgr.redis.client is not None
                _runtime_state["kafka_connected"] = (self._sim_mgr.kafka_producer.is_connected() if self._sim_mgr.kafka_producer else False)

            while self._running and self._sim_mgr._running:
                try:
                    status = self._sim_mgr.get_status()
                    with _lock:
                        _runtime_state.update({
                            "active_drones": status["active_drones"],
                            "kafka_msg_per_sec": status["kafka_msg_per_sec"],
                            "uptime_sec": status["uptime_sec"],
                            "errors": status["errors"],
                        })
                        # 合并日志
                        for log_entry in status.get("logs", []):
                            if log_entry not in _runtime_state["logs"]:
                                _runtime_state["logs"].append(log_entry)
                                if len(_runtime_state["logs"]) > 50:
                                    _runtime_state["logs"] = _runtime_state["logs"][-50:]
                    self._push_status()
                except Exception as e:
                    _add_log(f"状态查询错误: {e}")
                time.sleep(1.0)

            # 停止 SimulationManager
            if self._sim_mgr:
                self._sim_mgr.stop()

        elif self.mode == "replay_once":
            # 预生成回放(单次)：使用 run_kafka.py 的 DataSource，数据耗尽自动停止
            _add_log("启动预生成回放(单次)模式，加载数据中...")
            from tools import run_kafka as _rk
            # 使用前端选择的文件覆盖默认路径
            data_file = self.config.get("data_file", "kafka_data.json")
            route_file = self.config.get("route_file", "redis_route.json")
            try:
                mock_dir = os.path.join(_root, "..", "data", "mock")
                _rk.KAFKA_DATA_JSON_PATH = os.path.join(mock_dir, data_file)
                _rk.REDIS_ROUTE_JSON_PATH = os.path.join(mock_dir, route_file)
                ds = _rk.DataSource(kafka_url=self.config.get("kafka_url"))
                self._ds = ds  # 保存引用供 _cleanup() 使用
                with _lock:
                    _runtime_state["redis_connected"] = ds.redis_client.client is not None
                    _runtime_state["kafka_connected"] = ds.kafka_producer.is_connected()
                    _runtime_state["active_drones"] = len(ds.allowed_uav_uids)

                _add_log(f"数据加载完成: {len(ds.allowed_uav_uids)} 架无人机, {len(ds.kafka_data_list)} 条遥测记录")

                while self._running and not ds.data_exhausted:
                    batch = ds.get_next_batch()
                    if batch:
                        try:
                            ds.kafka_producer.send_bulk(batch, KAFKA_UAV_DATA_TOPIC)
                            # 桥接遥测数据到前端运行日志面板
                            socketio.emit("telemetry_data", {"records": batch, "count": len(batch)})
                        except Exception as e:
                            _add_log(f"Kafka 发送失败: {e}")
                        with _lock:
                            _runtime_state["active_drones"] = len(ds.allowed_uav_uids)
                            _runtime_state["kafka_msg_per_sec"] = len(batch)
                            if self._start_time:
                                _runtime_state["uptime_sec"] = int(time.time() - self._start_time)
                    # 桥接触发数据到前端 Layer 2（运行日志-轨迹预测）
                    _push_replay_once_trace(ds)
                    self._push_status()
                    time.sleep(1.0)

                _add_log("数据回放完成（数据耗尽）")
                ds._save_kafka_data()
                try:
                    ds.kafka_producer.close()
                    ds.kafka_consumer.close()
                except Exception:
                    pass
            except Exception as e:
                _add_log(f"replay_once 模式异常: {e}")
                traceback.print_exc()

        elif self.mode == "scene":
            # 场景文件注入：使用 run_kafka_scene.py 的 SceneEmitter
            mock_dir = os.path.join(_root, "..", "data", "mock")
            scene_files = [os.path.join(mock_dir, f) for f in self.config.get("scene_files", []) if f]
            scene_dir = self.config.get("scene_dir", None)
            scene_interval = self.config.get("scene_interval", 1000)
            scene_timestamp_mode = self.config.get("timestamp_mode", "replace")
            scene_loop = self.config.get("scene_loop", False)

            if not scene_files and not scene_dir:
                _add_log("scene 模式需要指定场景文件或目录，请先选择文件")
                self._running = False
            else:
                _add_log(f"启动场景文件注入模式: {len(scene_files)} 个文件, 间隔={scene_interval}ms, 时间戳={scene_timestamp_mode}")
                from tools.run_kafka_scene import SceneEmitter
                try:
                    emitter = SceneEmitter(
                        files=scene_files,
                        scene_dir=scene_dir,
                        kafka_url=self.config.get("kafka_url"),
                        topic=KAFKA_UAV_DATA_TOPIC,
                        interval_ms=scene_interval,
                        timestamp_mode=scene_timestamp_mode,
                        loop=scene_loop,
                        consume_trace=True,
                    )
                    self._emitter = emitter  # 保存引用供 _cleanup() 使用
                    emitter.start()
                    with _lock:
                        _runtime_state["active_drones"] = len(emitter.uav_data_list)

                    _prev_scene_sent = 0
                    _prev_scene_trace = 0
                    while self._running and emitter.running:
                        try:
                            # 桥接场景遥测计数到前端 Layer 1（运行日志-遥测）
                            current_sent = emitter.stats.get('sent', 0)
                            if current_sent > _prev_scene_sent:
                                count = current_sent - _prev_scene_sent
                                _prev_scene_sent = current_sent
                                _get_streamer().report_kafka_telemetry(count)
                                socketio.emit("telemetry_data", {
                                    "records": [], "count": count,
                                    "mode": "scene",
                                    "message": f"场景注入 {count} 条遥测记录"
                                })
                            # 桥接场景 trace 数据到前端 Layer 2（运行日志-轨迹预测）
                            if emitter.consume_trace and emitter.trace_stats:
                                current_trace = emitter.trace_stats.get('received', 0)
                                if current_trace > _prev_scene_trace and current_trace > 0:
                                    _prev_scene_trace = current_trace
                                    socketio.emit("trace_data", {
                                        "count": current_trace,
                                        "data": list(emitter.trace_records[-50:]),
                                        "key": "scene",
                                    })
                            with _lock:
                                if self._start_time:
                                    _runtime_state["uptime_sec"] = int(time.time() - self._start_time)
                        except Exception:
                            pass
                        self._push_status()
                        time.sleep(1.0)

                    emitter.stop()
                    _add_log("场景文件注入完成")
                except Exception as e:
                    _add_log(f"scene 模式异常: {e}")
                    traceback.print_exc()

        elif self.mode == "plan":
            # Plan 模式：PlanRunner 有自己的独立线程
            self._init_plan_mode()
            while self._running:
                try:
                    plan_count = len(self._plan_runner._plans) if self._plan_runner else 0
                    with _lock:
                        _runtime_state["active_drones"] = plan_count
                        _runtime_state["kafka_msg_per_sec"] = plan_count
                        if self._start_time:
                            _runtime_state["uptime_sec"] = int(time.time() - self._start_time)
                except Exception:
                    pass
                self._push_status()
                time.sleep(1.0)

        self._cleanup()

    _last_reported_kafka = 0

    def _push_status(self) -> None:
        """推送运行时状态到所有 WebSocket 客户端。"""
        with _lock:
            if self._start_time:
                _runtime_state["uptime_sec"] = int(time.time() - self._start_time)
            status = dict(_runtime_state)
            kafka_tp = status.get("kafka_msg_per_sec", 0)
        socketio.emit("status", status)
        # 每 5 秒报告一次 Kafka 遥测吞吐量
        if kafka_tp > 0 and kafka_tp != self._last_reported_kafka:
            try:
                _get_streamer().report_kafka_telemetry(kafka_tp)
            except Exception:
                pass
            self._last_reported_kafka = kafka_tp

    def _cleanup(self) -> None:
        """清理资源。"""
        _add_log("仿真运行结束，清理资源...")
        # 停止 TCP 网关日志轮询
        try:
            if _gateway_log_poller:
                _gateway_log_poller.stop()
        except Exception:
            pass
        if self.mode == "plan" and getattr(self, "_plan_runner", None):
            try:
                self._plan_runner.stop()
            except Exception:
                pass
            self._plan_runner = None
        if self._sim_mgr:
            try:
                self._sim_mgr.stop()
            except Exception:
                pass
            self._sim_mgr = None
        # 清理 replay_once 模式 DataSource
        if self._ds:
            try:
                self._ds.kafka_producer.close()
            except Exception:
                pass
            try:
                self._ds.kafka_consumer.close()
            except Exception:
                pass
            self._ds = None
        # 清理 scene 模式 SceneEmitter
        if self._emitter:
            try:
                self._emitter.stop()
            except Exception:
                pass
            self._emitter = None
        # 终止遥测桥接子进程
        if getattr(self, "_telemetry_bridge", None) and self._telemetry_bridge.poll() is None:
            try:
                self._telemetry_bridge.terminate()
                self._telemetry_bridge.wait(timeout=3)
            except Exception:
                try:
                    self._telemetry_bridge.kill()
                except Exception:
                    pass
            self._telemetry_bridge = None
            _add_log("遥测桥接子进程已终止")
        with _lock:
            _runtime_state["running"] = False

    def start(self) -> None:
        """启动仿真后台线程。"""
        if self._running:
            _add_log("仿真已在运行中")
            return

        with _lock:
            _runtime_state["running"] = True
            _runtime_state["mode"] = self.mode
            _runtime_state["active_drones"] = 0
            _runtime_state["kafka_msg_per_sec"] = 0
            _runtime_state["uptime_sec"] = 0
            _runtime_state["errors"] = 0
            _runtime_state["logs"] = []

        socketio.emit("status_change", {"event": "starting", "message": f"仿真启动中 (模式: {self.mode})"})
        _add_log(f"仿真启动: 模式={self.mode}, 目标架数={self.target_drones}")

        # 启动态势监控采集（连接 ATC WebSocket，采集监视目标/飞行计划/告警数据）
        try:
            _get_situation_monitor().start()
        except Exception as e:
            print(f"[web_server] 态势监控启动失败: {e}")

        # 启动 TCP 网关日志轮询（拉取代理通信实时日志）
        try:
            _get_gateway_log_poller().start()
        except Exception as e:
            print(f"[web_server] 网关日志轮询启动失败: {e}")

        # 启动 Kafka 冲突告警消费者
        # dynamic 模式下跳过：kafka-python 后台 I/O 线程与 Simulator ctypes
        # 并发操作在 Windows 上会导致 C-level 堆损坏崩溃（已实际验证）
        # 告警消费者与 Simulator 在同一进程内，kafka-python(librdkafka) 的后台线程
        # 与 Simulator ctypes 操作并发时会触发 C-level 崩溃
        if self.mode != "dynamic":
            try:
                _start_collision_alarm_consumer()
            except Exception as e:
                print(f"[web_server] 冲突告警消费者启动失败: {e}")
        else:
            print("[web_server] dynamic 模式，跳过 Kafka 冲突告警消费者（避免 ctypes 并发崩溃）")
            _add_log("dynamic 模式：冲突告警消费者已跳过（ctypes 兼容性限制，不影响核心功能）")

        # dynamic 模式：启动遥测桥接子进程（Redis → Kafka）
        if self.mode == "dynamic":
            self._start_telemetry_bridge()
            # 验证桥接进程是否成功启动
            time.sleep(0.5)
            bridge = getattr(self, "_telemetry_bridge", None)
            if bridge is None or bridge.poll() is not None:
                _add_log("⚠️ 遥测桥接子进程启动失败，dynamic 模式将无 Kafka 数据，请检查 telemetry_bridge.py")
            else:
                # 5 秒后验证桥接是否在正常转发数据
                def _verify_bridge_forwarding():
                    time.sleep(5)
                    b = getattr(self, "_telemetry_bridge", None)
                    if b is None or b.poll() is not None:
                        _add_log("⚠️ 遥测桥接已退出，dynamic 模式 Kafka 数据中断")
                    else:
                        try:
                            from redis_client import RedisClient as _RC
                            from env import redis_ip as _rip, redis_port as _rpt, redis_password as _rpw
                            test_redis = _RC(_rip, _rpt, _rpw)
                            if test_redis.client and not test_redis.client.exists("BIZ_DATA:UAV_TELEMETRY"):
                                _add_log("遥测桥接运行中但 Redis 遥测 key 为空，检查 dynamic 模式是否正在产生遥测数据")
                        except Exception:
                            pass
                threading.Thread(target=_verify_bridge_forwarding, daemon=True).start()

        self._thread = threading.Thread(target=self._sim_loop, daemon=True)
        self._thread.start()

        socketio.emit("status_change", {"event": "started", "message": "仿真已启动"})

    def _check_telemetry_bridge(self) -> None:
        """检查遥测桥接子进程是否存活，异常退出时自动重启。"""
        bridge = getattr(self, "_telemetry_bridge", None)
        if bridge is None:
            return
        retcode = bridge.poll()
        if retcode is not None:
            _add_log(f"⚠️ 遥测桥接子进程已退出 (code={retcode})，正在重启...")
            try:
                self._start_telemetry_bridge()
                _add_log("遥测桥接子进程已重启")
            except Exception as e:
                _add_log(f"遥测桥接重启失败: {e}")

    def _start_telemetry_bridge(self) -> None:
        """启动遥测桥接子进程：将 Redis BIZ_DATA:UAV_TELEMETRY 转发到 Kafka。

        运行在独立子进程中，与 Simulator (ctypes) 主进程完全隔离，
        避免 Windows 上 kafka-python (librdkafka) 与 ctypes 堆污染导致的 C-level 崩溃。
        """
        import sys as _sys, subprocess as _sp
        bridge_script = os.path.join(_root, "tools", "telemetry_bridge.py")
        cfg = self._app_cfg
        cmd = [
            _sys.executable, bridge_script,
            "--redis-host", cfg.redis.host,
            "--redis-port", str(cfg.redis.port_int),
            "--redis-password", cfg.redis.password,
            "--kafka-url", cfg.kafka.bootstrap_servers,
        ]
        if cfg.kafka.bootstrap_servers_mirror:
            cmd += ["--kafka-mirror-url", cfg.kafka.bootstrap_servers_mirror]
        try:
            self._telemetry_bridge = _sp.Popen(cmd, close_fds=True)
            _add_log("遥测桥接子进程已启动")
        except Exception as e:
            print(f"[web_server] 遥测桥接启动失败: {e}")
            self._telemetry_bridge = None

    def stop(self) -> None:
        """停止仿真。"""
        if not self._running:
            _add_log("仿真未在运行")
            return

        _add_log("正在停止仿真...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._cleanup()
        socketio.emit("status_change", {"event": "stopped", "message": "仿真已停止"})
        _add_log("仿真已停止")


# ==================== REST API 路由 ================================

@app.route("/")
def index():
    """首页重定向到仿真执行页。"""
    from flask import redirect as _redirect
    return _redirect("/run")


@app.route("/config")
def page_config():
    """仿真配置页 — 已合并到 /run，重定向。"""
    from flask import redirect as _redirect
    return _redirect("/run")


@app.route("/run")
def page_run():
    """仿真执行页（合并配置+监控+地图）。"""
    return send_from_directory(_WEB_PAGES_DIR, "run.html")


@app.route("/scene")
def page_scene():
    """场景编排管理页。"""
    return send_from_directory(_WEB_PAGES_DIR, "scene.html")


@app.route("/schedule")
def page_schedule():
    """定时任务管理页（重定向到场景编排）。"""
    from flask import redirect
    return redirect("/scene")


@app.route("/generate")
def page_generate():
    """模拟数据生成页。"""
    return send_from_directory(_WEB_PAGES_DIR, "generate.html")


@app.route("/data")
def page_data():
    """JSON 数据管理页。"""
    return send_from_directory(_WEB_PAGES_DIR, "data.html")


@app.route("/env")
def page_env():
    """环境变量管理页。"""
    return send_from_directory(_WEB_PAGES_DIR, "env.html")


@app.route("/logs")
def page_logs():
    """系统日志页。"""
    return send_from_directory(_WEB_PAGES_DIR, "logs.html")


@app.route("/performance")
def page_performance():
    """性能监控页（占位）。"""
    return send_from_directory(_WEB_PAGES_DIR, "performance.html")


@app.route("/ha")
def page_ha():
    """高可用管理页（占位）。"""
    return send_from_directory(_WEB_PAGES_DIR, "ha.html")


@app.route("/basicdata")
def page_basicdata():
    """基础数据管理页（占位）。"""
    return send_from_directory(_WEB_PAGES_DIR, "basicdata.html")


@app.route("/api/sim/status", methods=["GET"])
def api_get_status():
    """获取仿真运行状态。"""
    with _lock:
        status = dict(_runtime_state)
    return jsonify(status)


@app.route("/api/sim/config", methods=["GET"])
def api_get_config():
    """获取当前配置。"""
    with _lock:
        config = dict(_current_config)
    return jsonify(config)


@app.route("/api/sim/config", methods=["PUT"])
def api_update_config():
    """更新配置（仅未运行时允许）。"""
    global _current_config
    with _lock:
        if _runtime_state["running"]:
            return jsonify({"success": False, "message": "仿真运行中，无法修改配置"}), 409

    data = request.get_json(silent=True) or {}
    with _lock:
        for key in ("mode", "target_drones", "nfz_enabled", "nfz_count",
                     "api_mode", "api_base_url",
                     "scene_interval", "timestamp_mode", "scene_loop",
                     "data_file", "route_file", "plan_selected_uids", "plan_route_file"):
            if key in data:
                _current_config[key] = data[key]
    return jsonify({"success": True, "config": _current_config})


@app.route("/api/sim/start", methods=["POST"])
def api_start_sim():
    """启动仿真。"""
    global _sim_runner

    with _lock:
        if _runtime_state["running"]:
            return jsonify({"success": False, "message": "仿真已在运行中"}), 409

    data = request.get_json(silent=True) or {}
    # 合并请求参数到配置
    config = dict(_current_config)
    for key in ("mode", "target_drones", "nfz_enabled", "nfz_count",
                "scene_files", "scene_interval", "timestamp_mode", "scene_loop",
                "data_file", "route_file", "plan_selected_uids", "plan_route_file"):
        if key in data:
            config[key] = data[key]

    try:
        _sim_runner = SimulationRunner(config)
        _sim_runner.start()
        return jsonify({"success": True, "message": "仿真已启动", "config": config})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"启动失败: {e}"}), 500


@app.route("/api/sim/stop", methods=["POST"])
def api_stop_sim():
    """停止仿真。先停止场景编排执行，再停止全局仿真运行器。"""
    global _sim_runner

    # 1. 先停止所有活跃的场景编排执行（不依赖 _sim_runner）
    scene_stopped = 0
    try:
        och = _get_orchestrator()
        scene_stopped = och.stop_all_scenes()
        if scene_stopped:
            _add_log(f"[场景编排] 已发送 {scene_stopped} 个场景停止信号")
            # 等待场景 runner 退出（最多 5 秒）
            for _ in range(50):
                if not och.list_active_executions():
                    break
                time.sleep(0.1)
    except Exception as e:
        print(f"[web_server] 停止场景执行异常: {e}", flush=True)

    # 2. 停止全局 _sim_runner（如果有）
    if not _sim_runner:
        if scene_stopped > 0:
            _add_log("场景执行已停止")
            with _lock:
                _runtime_state["running"] = False
            socketio.emit("status_change", {"event": "stopped", "message": "场景执行已停止"})
            return jsonify({"success": True, "message": "场景执行已停止"})
        return jsonify({"success": False, "message": "无运行中的仿真"}), 404

    _sim_runner.stop()
    _sim_runner = None

    # 3. 重启进程 — Simulator(ctypes) 与 kafka-python(librdkafka)
    # 在同一进程中先后运行会导致 C-level 堆损坏，重启获得干净环境
    import sys as _sys, subprocess as _sp
    env = os.environ.copy()
    env["UTM_RESTART"] = "1"
    _sp.Popen([_sys.executable] + _sys.argv, env=env, close_fds=True)
    print("[web_server] 正在重启进程以清理堆状态...", flush=True)
    _graceful_shutdown()
    os._exit(0)


@app.route("/api/sim/plans", methods=["GET"])
def api_get_plans():
    """获取当前 Redis 中的飞行计划（供地图渲染）。"""
    limit = request.args.get("limit", 100, type=int)

    # 从 Redis 读取飞行计划
    client = RedisClient(
        _current_config["redis_ip"],
        _current_config["redis_port"],
        getattr(_env, "redis_password", ""),
    )

    try:
        all_data = client.hgetall(REDIS_FLIGHT_PLAN_KEY)
    except Exception as e:
        return jsonify({"plans": [], "total": 0, "error": str(e)})

    if not all_data:
        return jsonify({"plans": [], "total": 0})

    plans = []
    for uid, raw in all_data.items():
        if len(plans) >= limit:
            break
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
            fp_list = obj.get("flightPlanList", []) if isinstance(obj, dict) else []
            plan_entry = dict(obj) if isinstance(obj, dict) else {}
            plan_entry["_uid"] = uid  # Redis Hash field = 无人机 UID
            plan_entry["_fpCount"] = len(fp_list)
            plans.append(plan_entry)
        except (json.JSONDecodeError, TypeError):
            continue

    return jsonify({"plans": plans, "total": len(all_data)})


@app.route("/api/sim/nfzs", methods=["GET"])
def api_get_nfzs():
    """获取当前 Redis 中的空域/禁飞区数据（供地图渲染）。"""
    client = RedisClient(
        _current_config["redis_ip"],
        _current_config["redis_port"],
        getattr(_env, "redis_password", ""),
    )

    try:
        all_data = client.hgetall(REDIS_AIRSPACE_KEY)
    except Exception as e:
        return jsonify({"nfzs": [], "total": 0, "error": str(e)})

    if not all_data:
        return jsonify({"nfzs": [], "total": 0})

    nfzs = []
    for key, raw in all_data.items():
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
            nfzs.append(obj)
        except (json.JSONDecodeError, TypeError):
            continue

    return jsonify({"nfzs": nfzs, "total": len(nfzs)})


@app.route("/api/sim/test-connection", methods=["GET"])
def api_test_connection():
    """测试 Redis/Kafka 连接状态。"""
    result = {"redis": False, "kafka": False}

    # 测试 Redis
    try:
        client = RedisClient(
            _current_config["redis_ip"],
            _current_config["redis_port"],
            getattr(_env, "redis_password", ""),
        )
        result["redis"] = client.client is not None
    except Exception:
        pass

    # 测试 Kafka
    try:
        producer = KafkaProducerClient(
            bootstrap_servers=_current_config["kafka_url"],
        )
        result["kafka"] = producer.is_connected()
        producer.close()
    except Exception:
        pass

    return jsonify(result)


@app.route("/api/sim/config/save", methods=["POST"])
def api_save_config():
    """保存连接配置到 config.json（持久化）。"""
    global _current_config
    data = request.get_json(silent=True) or {}
    changes = {}
    for key in ("redis_ip", "redis_port", "kafka_url"):
        if key in data:
            changes[key] = data[key]
            _current_config[key] = data[key]

    if not changes:
        return jsonify({"success": False, "message": "无有效配置项"}), 400

    # 写入 config.json
    try:
        cfg_path = os.path.join(_root, "..", "common", "config.json")
        cfg_data = {
            "redis_ip": _current_config["redis_ip"],
            "redis_port": _current_config["redis_port"],
            "kafka_url": _current_config["kafka_url"],
        }
        # 保留已有的 kafka_url2（从 _current_config 或 env 读取）
        cfg_data["kafka_url2"] = _current_config.get("kafka_url2", getattr(_env, "kafka_url2", ""))

        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg_data, f, ensure_ascii=False, indent=2)
        _add_log(f"连接配置已保存到 config.json (Redis={cfg_data['redis_ip']}:{cfg_data['redis_port']}, Kafka={cfg_data['kafka_url']})")
        return jsonify({"success": True, "message": "配置已保存到 config.json", "changes": changes})
    except Exception as e:
        return jsonify({"success": False, "message": f"写入文件失败: {e}"}), 500


# ── 数据文件格式检测（Task: 数据管理显示适用模式） ─────────────

def _detect_file_format(content_str: str) -> Dict[str, Any]:
    """分析 JSON 文件内容，返回格式类型和兼容的仿真模式。

    Returns:
        {"format": "telemetry"|"flight_plan"|"redis_route"|"unknown",
         "format_label": 中文格式名,
         "compatible_modes": ["scene","replay","replay_once","plan"...]}
    """
    result = {"format": "unknown", "format_label": "未知格式", "compatible_modes": []}
    if not content_str or not content_str.strip():
        return result

    try:
        data = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        return result

    # 检测1: redis_route 格式 [{"key": "...", "value": {...}}]
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        first = data[0]
        if "key" in first and "value" in first:
            result["format"] = "redis_route"
            result["format_label"] = "Redis航线"
            result["compatible_modes"] = ["plan", "replay"]
            return result

        # 检测2: telemetry 格式 (有 longitude + latitude)
        if "longitude" in first and "latitude" in first:
            # 同时检查是否有 flightPlanList
            has_plan = "flightPlanList" in first
            result["format"] = "telemetry"
            result["format_label"] = "遥测轨迹" + (" + 飞行计划" if has_plan else "")
            result["compatible_modes"] = ["scene", "replay", "replay_once"]
            if has_plan:
                result["compatible_modes"].append("plan")
            return result

        # 检测3: flight_plan 格式 (有 flightPlanList 但无 longitude)
        if "flightPlanList" in first:
            result["format"] = "flight_plan"
            result["format_label"] = "飞行计划"
            result["compatible_modes"] = ["plan", "replay"]
            return result

    # 检测4: dict 格式的 redis_route
    if isinstance(data, dict):
        # 可能是单个 flight plan
        if "flightPlanList" in data:
            result["format"] = "flight_plan"
            result["format_label"] = "飞行计划(单条)"
            result["compatible_modes"] = ["plan", "replay"]
            return result

    # 未知格式 — 允许用户尝试所有模式
    result["compatible_modes"] = ["scene", "replay", "replay_once", "plan"]
    return result


# ── 数据文件管理 API（Task 1: 前端数据可视化增强） ─────────────

@app.route("/api/data/files", methods=["GET"])
def api_list_data_files():
    """列出 mock/ 目录下可用的 JSON 数据文件。"""
    mock_dir = os.path.join(_root, "..", "data", "mock")
    if not os.path.exists(mock_dir):
        return jsonify({"files": [], "error": "mock/ 目录不存在"})

    files = []
    for name in os.listdir(mock_dir):
        if name.endswith(".json"):
            path = os.path.join(mock_dir, name)
            size = os.path.getsize(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    # 先读取前 64KB 用于快速解析和格式检测
                    content = f.read(65536)
                    try:
                        data = json.loads(content)
                    except (json.JSONDecodeError, ValueError):
                        # 大文件截断导致解析失败 → 回退读取完整文件
                        f.seek(0)
                        content = f.read()
                        data = json.loads(content)
                if isinstance(data, list):
                    records = len(data)
                    sample_keys = list(data[0].keys())[:5] if data else []
                elif isinstance(data, dict):
                    records = len(data)
                    sample_keys = list(data.keys())[:5]
                else:
                    records = 0
                    sample_keys = []
                # 格式检测（使用前 64KB 样本即可，避免大文件全文分析）
                fmt_info = _detect_file_format(content[:65536])
            except Exception:
                records = -1
                sample_keys = []
                fmt_info = {"format": "unknown", "format_label": "解析失败", "compatible_modes": []}

            files.append({
                "name": name,
                "size": size,
                "size_kb": round(size / 1024, 1),
                "records": records,
                "sample_keys": sample_keys,
                "format": fmt_info["format"],
                "format_label": fmt_info["format_label"],
                "compatible_modes": fmt_info["compatible_modes"],
            })

    return jsonify({"files": sorted(files, key=lambda f: f["name"])})


@app.route("/api/data/files/<filename>", methods=["GET"])
def api_get_data_file(filename: str):
    """查看 JSON 文件内容（分页）。"""
    mock_dir = os.path.join(_root, "..", "data", "mock")
    path = os.path.join(mock_dir, filename)

    # 安全检查：禁止路径穿越
    real_path = os.path.realpath(path)
    if not real_path.startswith(os.path.realpath(mock_dir)):
        return jsonify({"error": "非法的文件路径"}), 403

    if not os.path.exists(path):
        return jsonify({"error": f"文件不存在: {filename}"}), 404

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return jsonify({"error": f"读取失败: {e}"}), 500

    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 50, type=int)

    if isinstance(data, list):
        page = data[offset:offset + limit]
        total = len(data)
        result = {
            "filename": filename,
            "type": "list",
            "total": total,
            "offset": offset,
            "limit": limit,
            "data": page,
        }
    elif isinstance(data, dict):
        result = {
            "filename": filename,
            "type": "dict",
            "total_keys": len(data),
            "keys": list(data.keys()),
            "data": data,
        }
    else:
        result = {"filename": filename, "type": "unknown", "data": str(data)[:1000]}

    return jsonify(result)


@app.route("/api/data/files/generate", methods=["POST"])
def api_generate_data():
    """参数化生成模拟数据。

    Body: {
        "count": 100,              // 无人机数量
        "center_lat": 31.315,      // 中心纬度
        "center_lon": 120.665,     // 中心经度
        "radius": 800.0,           // 半径（米）
        "pattern": "random",       // 路径模式: random/grid/radial
        "duration_min": 10         // 飞行时长（分钟）
    }
    """
    data = request.get_json(silent=True) or {}
    count = data.get("count", 10)
    center_lat = data.get("center_lat", 31.315)
    center_lon = data.get("center_lon", 120.665)
    radius = data.get("radius", 800.0)
    pattern = data.get("pattern", "random")
    duration_min = data.get("duration_min", 10)

    try:
        import random as _random
        import math as _math
        from datetime import datetime as _dt

        generated = []
        now_ts = time.time()
        duration_sec = duration_min * 60

        for i in range(count):
            uid = f"UAV_{i + 1:05d}"

            # 根据模式生成航点
            waypoints = []
            if pattern == "grid":
                cols = int(_math.ceil(_math.sqrt(count)))
                row, col = divmod(i, cols)
                d = radius / max(cols, 1)
                base_lat = center_lat + (row - cols // 2) * d / 111320.0
                base_lon = center_lon + (col - cols // 2) * d / (111320.0 * _math.cos(_math.radians(center_lat)))
                waypoints = [
                    (base_lon, base_lat),
                    (base_lon + d / 111320.0, base_lat + d / 111320.0),
                ]
            elif pattern == "radial":
                angle = 2 * _math.pi * i / max(count, 1)
                dist = radius * (0.3 + 0.7 * (i % 3) / 2)
                waypoints = [
                    (center_lon, center_lat),
                    (center_lon + dist * _math.cos(angle) / 111320.0,
                     center_lat + dist * _math.sin(angle) / 110540.0),
                ]
            else:  # random
                for _ in range(3):
                    angle = _random.uniform(0, 2 * _math.pi)
                    dist = _random.uniform(0.2 * radius, radius)
                    waypoints.append((
                        center_lon + dist * _math.cos(angle) / 111320.0,
                        center_lat + dist * _math.sin(angle) / 110540.0,
                    ))

            # ── 沿航点插值生成遥测轨迹点（Kafka 格式 + Redis 航线格式） ──
            route_list = []
            telemetry_records = []
            # 每个航点分配高度递进
            wp_with_alt = []
            for j, (lon, lat) in enumerate(waypoints):
                alt = 100.0 + j * 50  # 逐段升高 50m
                wp_with_alt.append((lon, lat, alt))

            # 构建 routeList（Redis 航线格式）
            for j in range(len(wp_with_alt) - 1):
                s_lon, s_lat, s_alt = wp_with_alt[j]
                e_lon, e_lat, e_alt = wp_with_alt[j + 1]
                route_list.append({
                    "sequence": j,
                    "type": 2,
                    "segmentStartLon": round(s_lon, 6),
                    "segmentStartLat": round(s_lat, 6),
                    "segmentEndLon": round(e_lon, 6),
                    "segmentEndLat": round(e_lat, 6),
                    "segmentStartHeight": s_alt,
                    "segmentEndHeight": e_alt,
                    "segmentProtectHeight": 50.0,
                    "segmentProtectHeightType": 1,
                    "segmentWidth": 100.0,
                })

            # 沿航点路径插值生成遥测轨迹点（Kafka 场景模式/回放模式可用）
            interval_sec = 1.0  # 每秒一个轨迹点
            cruise_speed = 15.0  # m/s
            total_flight_time = 0.0

            for j in range(len(wp_with_alt) - 1):
                s_lon, s_lat, s_alt = wp_with_alt[j]
                e_lon, e_lat, e_alt = wp_with_alt[j + 1]

                # 计算航段距离和方位角
                d_lon = (e_lon - s_lon) * _math.cos(_math.radians((s_lat + e_lat) / 2)) * 111320.0
                d_lat = (e_lat - s_lat) * 110540.0
                seg_dist = _math.hypot(d_lon, d_lat)
                seg_time = seg_dist / cruise_speed if cruise_speed > 0 else 1.0
                steps = max(1, int(seg_time / interval_sec))

                heading = (_math.degrees(_math.atan2(d_lon, d_lat)) + 360) % 360

                for step in range(steps):
                    frac = step / steps
                    lon = s_lon + (e_lon - s_lon) * frac
                    lat = s_lat + (e_lat - s_lat) * frac
                    alt = s_alt + (e_alt - s_alt) * frac
                    ts = int((now_ts + total_flight_time + frac * seg_time) * 1000)

                    telemetry_records.append({
                        "uniqueProductIdentificationCode": uid,
                        "realNameRegistrationSign": f"GEN_{uid}",
                        "longitude": round(lon, 6),
                        "latitude": round(lat, 6),
                        "geodeticAltitude": round(alt, 1),
                        "speed": cruise_speed,
                        "trackAngle": round(heading, 1),
                        "verticalSpeed": 0.0,
                        "relativeAltitude": 0.0,
                        "ressureAltitude": 0.0,
                        "operatingStatus": 2,
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
                        "timestamp": ts,
                        "addInf": {},
                    })
                total_flight_time += seg_time

            # 构建飞行计划（Redis 航线格式）
            flight_plan = {
                "flightPlanId": 1,
                "planTakeoffTime": now_ts + i * 10,
                "planLandTime": now_ts + duration_sec + i * 10,
                "flightTaskId": 1,
                "flightTaskName": f"auto_gen_{pattern}",
                "routeList": route_list,
            }

            generated.append({
                "uniqueProductIdentificationCode": uid,
                "realNameRegistrationSign": f"GEN_{uid}",
                "flightPlanList": [flight_plan],
            })

        # 保存遥测轨迹文件（Kafka 格式，用于 scene/replay 模式）
        mock_dir = os.path.join(_root, "..", "data", "mock")
        os.makedirs(mock_dir, exist_ok=True)
        ts = int(time.time())

        # 1) Kafka 遥测轨迹文件（场景模式 / 回放模式的 kafka_data）
        kafka_file = os.path.join(mock_dir, f"kafka_data_gen_{ts}.json")
        with open(kafka_file, "w", encoding="utf-8") as f:
            json.dump(telemetry_records, f, ensure_ascii=False, indent=2)

        # 2) Redis 航线文件（replay / plan 模式的 redis_route）
        route_file = os.path.join(mock_dir, f"redis_route_gen_{ts}.json")
        route_data = []
        for item in generated:
            uid = item["uniqueProductIdentificationCode"]
            route_data.append({
                "key": uid,
                "value": item,
            })
        with open(route_file, "w", encoding="utf-8") as f:
            json.dump(route_data, f, ensure_ascii=False, indent=2)

        _add_log(f"已生成 {count} 架无人机数据 (遥测 {len(telemetry_records)} 点) → {os.path.basename(kafka_file)} + {os.path.basename(route_file)}")

        return jsonify({
            "success": True,
            "message": f"已生成 {count} 架无人机, {len(telemetry_records)} 个轨迹点",
            "file": os.path.basename(kafka_file),
            "route_file": os.path.basename(route_file),
            "path": kafka_file,
            "count": count,
            "pattern": pattern,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/data/files/upload", methods=["POST"])
def api_upload_data():
    """上传自定义 JSON 数据文件到 mock/ 目录。"""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未上传文件"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".json"):
        return jsonify({"success": False, "error": "仅支持 .json 文件"}), 400

    try:
        mock_dir = os.path.join(_root, "..", "data", "mock")
        os.makedirs(mock_dir, exist_ok=True)
        save_path = os.path.join(mock_dir, file.filename)
        file.save(save_path)

        _add_log(f"已上传数据文件: {file.filename} ({os.path.getsize(save_path)} bytes)")
        return jsonify({
            "success": True,
            "message": f"已保存: {file.filename}",
            "path": save_path,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/data/launch-replay", methods=["POST"])
def api_launch_replay():
    """从指定的 JSON 文件启动 replay 模式仿真。"""
    global _sim_runner

    with _lock:
        if _runtime_state["running"]:
            return jsonify({"success": False, "message": "仿真已在运行中"}), 409

    data = request.get_json(silent=True) or {}
    data_file = data.get("data_file", "kafka_data.json")
    route_file = data.get("route_file", "redis_route.json")
    target_drones = data.get("target_drones", None)

    mock_dir = os.path.join(_root, "..", "data", "mock")
    data_path = os.path.join(mock_dir, data_file)
    route_path = os.path.join(mock_dir, route_file)

    if not os.path.exists(data_path):
        return jsonify({"success": False, "message": f"数据文件不存在: {data_file}"}), 404

    # 使用 SimulationManager 启动 replay
    config = dict(_current_config)
    config["mode"] = "replay"
    if target_drones:
        config["target_drones"] = target_drones

    try:
        _sim_runner = SimulationRunner(config)
        # 读取 JSON 文件获取记录数
        with open(data_path, "r", encoding="utf-8") as f:
            kd = json.load(f)
        drone_count = len(set(
            m.get("uniqueProductIdentificationCode") for m in kd
            if isinstance(m, dict)
        ))
        _add_log(f"从 {data_file} ({drone_count} 架无人机, {len(kd)} 条记录) 启动 replay")
        _sim_runner.start()
        return jsonify({
            "success": True,
            "message": f"已启动 replay 模式 ({data_file}, {drone_count} 架无人机)",
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": f"启动失败: {e}"}), 500


# ── 场景数据生成 API（集成 tools/ 脚本能力） ────────────────────────

@app.route("/api/data/scene/single", methods=["POST"])
def api_scene_single():
    """单机航线飞行数据生成（create_data_scene.py）。"""
    data = request.get_json(silent=True) or {}
    bridge = _get_bridge()
    result = bridge.gen_single_route(
        uid=data.get("uid", "UAV_TEST_001"),
        reg_sign=data.get("reg_sign"),
        classification=data.get("classification", 2),
        route_name=data.get("route_name"),
        route_id=data.get("route_id"),
        points=data.get("points"),
        start_lon=data.get("start_lon"),
        start_lat=data.get("start_lat"),
        end_lon=data.get("end_lon"),
        end_lat=data.get("end_lat"),
        altitude=data.get("altitude", 30.0),
        start_alt=data.get("start_alt"),
        end_alt=data.get("end_alt"),
        speed=data.get("speed", 15.0),
        start_time=data.get("start_time"),
        interval=data.get("interval", 1000),
        operating_status=data.get("operating_status", 2),
        filename=data.get("filename"),
    )
    if result.get("success"):
        _add_log(f"单机航线已生成: {os.path.basename(result.get('file', ''))} ({result.get('points', 0)} 轨迹点)")
    return jsonify(result)


@app.route("/api/data/scene/deviate", methods=["POST"])
def api_scene_deviate():
    """单机偏离航路数据生成（create_data_scene.py + apply_deviation）。"""
    data = request.get_json(silent=True) or {}
    bridge = _get_bridge()
    result = bridge.gen_single_deviate(
        uid=data.get("uid", "UAV_TEST_001"),
        reg_sign=data.get("reg_sign"),
        classification=data.get("classification", 2),
        route_name=data.get("route_name"),
        points=data.get("points"),
        start_lon=data.get("start_lon"),
        start_lat=data.get("start_lat"),
        end_lon=data.get("end_lon"),
        end_lat=data.get("end_lat"),
        altitude=data.get("altitude", 30.0),
        speed=data.get("speed", 15.0),
        interval=data.get("interval", 1000),
        deviate=data.get("deviate", True),
        deviate_offset=data.get("deviate_offset", 0.001),
        deviate_start_index=data.get("deviate_start_index", 5),
        operating_status=data.get("operating_status", 2),
        filename=data.get("filename"),
    )
    if result.get("success"):
        _add_log(f"偏离航路数据已生成: {os.path.basename(result.get('file', ''))} ({result.get('points', 0)} 轨迹点)")
    return jsonify(result)


@app.route("/api/data/scene/parallel", methods=["POST"])
def api_scene_parallel():
    """多机平行飞行数据生成（create_data_scenes.py parallel）。"""
    data = request.get_json(silent=True) or {}
    bridge = _get_bridge()
    result = bridge.gen_parallel(
        count=data.get("count", 30),
        center_lng=data.get("center_lng", 85.070136),
        center_lat=data.get("center_lat", 40.818724),
        altitude=data.get("altitude", 50.0),
        speed=data.get("speed", 15.0),
        heading=data.get("heading", 90.0),
        spacing=data.get("spacing", 2000.0),
        spacing_along=data.get("spacing_along", 0.0),
        layout=data.get("layout", "hex"),
        points=data.get("points", 1200),
        interval=data.get("interval", 1000),
        uid_offset=data.get("uid_offset", 0),
        classification=data.get("classification", 2),
        output=data.get("output"),
        multi=data.get("multi", False),
        start_time=data.get("start_time"),
    )
    if result.get("success"):
        _add_log(f"平行飞行数据已生成: {os.path.basename(result.get('file', ''))} ({result.get('count', 0)} 架无人机)")
    return jsonify(result)


@app.route("/api/data/scene/deviate-adv", methods=["POST"])
def api_scene_deviate_adv():
    """高级偏离航路数据生成（create_data_scenes.py deviate，平滑过渡）。"""
    data = request.get_json(silent=True) or {}
    bridge = _get_bridge()
    result = bridge.gen_deviate_adv(
        route_name=data.get("route_name", "铁门关至吐鲁番"),
        route_id=data.get("route_id"),
        uid_offset=data.get("uid_offset", 1),
        classification=data.get("classification", 3),
        speed=data.get("speed", 15.0),
        altitude=data.get("altitude"),
        deviate_offset=data.get("deviate_offset", 3000.0),
        deviate_start=data.get("deviate_start", 20),
        deviate_transition=data.get("deviate_transition"),
        deviate_altitude_offset=data.get("deviate_altitude_offset", 0.0),
        deviate_mode=data.get("deviate_mode", "horizontal"),
        coord_system=data.get("coord_system", "wgs84"),
        coord_output=data.get("coord_output"),
        filename=data.get("filename"),
    )
    if result.get("success"):
        _add_log(f"高级偏离数据已生成: {os.path.basename(result.get('file', ''))}")
    return jsonify(result)


@app.route("/api/data/scene/collision", methods=["POST"])
def api_scene_collision():
    """碰撞预警场景生成（create_data_scenes.py collision）。"""
    data = request.get_json(silent=True) or {}
    bridge = _get_bridge()
    result = bridge.gen_collision(
        route_names=data.get("route_names", "跨顺义三河段,三河区航路"),
        route_id=data.get("route_id"),
        uids=data.get("uids", "CW000000000000000004,CH000000000000000003"),
        uid_start_offset=data.get("uid_start_offset", 0),
        classification=data.get("classification", 2),
        altitude=data.get("altitude"),
        meeting_threshold=data.get("meeting_threshold", 10.0),
        warning_time=data.get("warning_time", 20),
        collision_time=data.get("collision_time", 300.0),
        zone_output=data.get("zone_output", True),
        interval=data.get("interval", 1000),
        output_dir=data.get("output_dir"),
    )
    if result.get("success"):
        _add_log(f"碰撞预警场景已生成 → {result.get('output_dir', 'mock/')}")
    return jsonify(result)


@app.route("/api/data/scene/status", methods=["POST"])
def api_scene_status():
    """状态告警场景生成（create_data_scenes.py status）。"""
    data = request.get_json(silent=True) or {}
    bridge = _get_bridge()
    result = bridge.gen_status(
        count=data.get("count", 1),
        center_lng=data.get("center_lng", 120.7418),
        center_lat=data.get("center_lat", 31.3689),
        altitude=data.get("altitude", 50.0),
        speed=data.get("speed", 15.0),
        heading=data.get("heading", 90.0),
        flight_minutes=data.get("flight_minutes", 1),
        emergency_count=data.get("emergency_count", 5),
        ground_seconds=data.get("ground_seconds", 0),
        climb_seconds=data.get("climb_seconds", 0),
        spacing=data.get("spacing", 2000.0),
        classification=data.get("classification", 2),
        scene3=data.get("scene3", False),
        scene5=data.get("scene5", False),
        scene3_5=data.get("scene3-5", False),
        id_offset=data.get("id_offset"),
        output_dir=data.get("output_dir"),
    )
    if result.get("success"):
        _add_log(f"状态告警场景已生成 → {result.get('output_dir', 'mock/')}")
    return jsonify(result)


@app.route("/api/data/scene/scale", methods=["POST"])
def api_scene_scale():
    """模板扩展数据生成（create_data_scenes.py scale）。"""
    data = request.get_json(silent=True) or {}
    bridge = _get_bridge()
    result = bridge.gen_scale(
        source=data.get("source", "mock/kafka_data_yfk.json"),
        count=data.get("count", 100),
        center_lng=data.get("center_lng", 89.2306),
        center_lat=data.get("center_lat", 38.19424),
        spacing=data.get("spacing", 300.0),
        output=data.get("output"),
    )
    if result.get("success"):
        _add_log(f"模板扩展数据已生成: {os.path.basename(result.get('file', ''))} ({result.get('count', 0)} 架)")
    return jsonify(result)


@app.route("/api/data/batch", methods=["POST"])
def api_data_batch():
    """批量预设生成（create_data_scenes.py batch）。"""
    data = request.get_json(silent=True) or {}
    config_index = data.get("config_index")
    bridge = _get_bridge()
    result = bridge.gen_batch(config_index=config_index)
    return jsonify(result)


@app.route("/api/data/batch/presets", methods=["GET"])
def api_batch_presets():
    """获取批量预设列表（供前端展示按钮）。"""
    bridge = _get_bridge()
    return jsonify({"presets": bridge.BATCH_PRESETS})


# ==================== 辅助装饰器 =====================================


def _safe_json(fn):
    """装饰器：为 API 添加 JSON 格式异常处理。"""
    from functools import wraps as _wraps
    @_wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            # 用 print 而非 traceback.print_exc，避免在 response 写入阶段触发
            # Werkzeug "write() before start_response" 断言错误
            print(f"[web_server] API 异常 ({fn.__name__}): {e}", flush=True)
            return jsonify({"success": False, "message": f"操作失败: {e}"}), 500
    return wrapper


# ==================== 环境管理 API ==================================

@app.route("/api/env/list", methods=["GET"])
def api_env_list():
    """列出所有环境配置。"""
    mgr = _get_env_mgr()
    envs = mgr.list_envs()
    current = mgr.get_current_config()
    return jsonify({"envs": envs, "current": current})


@app.route("/api/env/<int:env_id>", methods=["GET"])
def api_env_get(env_id):
    """获取单个环境配置。"""
    mgr = _get_env_mgr()
    env = mgr.get_env(env_id)
    if not env:
        return jsonify({"success": False, "message": "环境不存在"}), 404
    return jsonify({"success": True, "env": env})


@app.route("/api/env/save", methods=["POST"])
def api_env_save():
    """新增或更新环境配置。"""
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"success": False, "message": "环境名称不能为空"}), 400
    mgr = _get_env_mgr()
    env_id = mgr.save_env(data)
    return jsonify({"success": True, "id": env_id, "message": "已保存"})


@app.route("/api/env/<int:env_id>", methods=["DELETE"])
@_safe_json
def api_env_delete(env_id):
    """删除环境配置。"""
    mgr = _get_env_mgr()
    mgr.delete_env(env_id)
    return jsonify({"success": True, "message": "已删除"})


@app.route("/api/env/<int:env_id>/activate", methods=["POST"])
def api_env_activate(env_id):
    """激活指定环境配置。"""
    mgr = _get_env_mgr()
    result = mgr.activate_env(env_id)
    if result["success"]:
        # 同步更新运行时配置
        cfg = result.get("config", {})
        with _lock:
            _current_config["redis_ip"] = cfg.get("redis_ip", _current_config["redis_ip"])
            _current_config["redis_port"] = cfg.get("redis_port", _current_config["redis_port"])
            _current_config["kafka_url"] = cfg.get("kafka_url", _current_config["kafka_url"])
            # 同步达梦配置
            _current_config["dm_host"] = cfg.get("dm_host", "")
            _current_config["dm_port"] = cfg.get("dm_port", 5236)
            _current_config["dm_user"] = cfg.get("dm_user", "SYSDBA")
            _current_config["dm_password"] = cfg.get("dm_password", "")
            _current_config["dm_schema"] = cfg.get("dm_schema", "")
            # 同步 MySQL 配置（环境切换时生效）
            _current_config["mysql_host"] = cfg.get("mysql_host", "")
            _current_config["mysql_port"] = cfg.get("mysql_port", 3306)
            _current_config["mysql_user"] = cfg.get("mysql_user", "")
            _current_config["mysql_password"] = cfg.get("mysql_password", "")
            _current_config["mysql_database"] = cfg.get("mysql_database", "")
        # 仅当新环境配置了有效 MySQL 地址时才重置连接池
        if cfg.get("mysql_host"):
            try:
                from database.mysql_db_manager import reset_mysql_connection
                reset_mysql_connection()
            except Exception as e:
                print(f"[web_server] MySQL 连接重置失败: {e}", flush=True)
        mysql_info = f"{cfg.get('mysql_host')}/{cfg.get('mysql_database')}" if cfg.get("mysql_host") else "未配置(保持现有连接)"
        _add_log(f"已切换环境配置: Redis={cfg.get('redis_ip')}:{cfg.get('redis_port')}, Kafka={cfg.get('kafka_url')}, 达梦={cfg.get('dm_host')}, MySQL={mysql_info}")
    return jsonify(result)


@app.route("/api/env/import", methods=["POST"])
def api_env_import():
    """从 env.py 导入当前配置。"""
    mgr = _get_env_mgr()
    result = mgr.import_from_env_py()
    return jsonify(result)


# ==================== JSON 数据管理 API ==============================

_json_mgr = None

def _get_json_mgr():
    global _json_mgr
    if _json_mgr is None:
        import json_data_manager as jdm
        _json_mgr = jdm
    return _json_mgr


@app.route("/api/data/db/files", methods=["GET"])
def api_db_list_files():
    """分页查询数据库中的 JSON 文件（v2: 文件路径存储，不含 content）。"""
    mgr = _get_json_mgr()
    category = request.args.get("category", "")
    alarm_type = request.args.get("alarm_type", "")
    keyword = request.args.get("keyword", "")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    result = mgr.list_files(
        category=category, alarm_type=alarm_type,
        keyword=keyword, page=page, page_size=page_size,
    )
    # 为每个文件附加格式检测信息（从磁盘读取首 64KB）
    for f in result.get("files", []):
        fpath = mgr._resolve_path(f)
        sample = ""
        if fpath and os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    sample = fh.read(65536)
            except Exception:
                pass
        fmt = _detect_file_format(sample) if sample else {"format": "unknown", "format_label": "未知格式", "compatible_modes": []}
        f["format"] = fmt["format"]
        f["format_label"] = fmt["format_label"]
        f["compatible_modes"] = fmt["compatible_modes"]
        # 移除内部字段，不暴露给前端
        f.pop("file_path", None)
    return jsonify(result)


@app.route("/api/data/db/files/<int:file_id>", methods=["GET"])
def api_db_get_file(file_id):
    """获取文件详情（默认不含完整内容，大文件用 /preview 端点）。"""
    mgr = _get_json_mgr()
    include_content = request.args.get("include_content", "").lower() == "true"
    if include_content:
        # 仅返回前 100KB，避免大文件 OOM
        result = mgr.read_file_content_partial(file_id, max_chars=102400)
        record = mgr.get_file(file_id)
        if record:
            record["content"] = result.get("content", "")
            record["content_truncated"] = result.get("truncated", False)
            record["content_message"] = result.get("message", "")
            return jsonify(record)
        return jsonify({"error": "文件不存在"}), 404
    record = mgr.get_file(file_id)
    if not record:
        return jsonify({"error": "文件不存在"}), 404
    # 移除内部路径
    record.pop("file_path", None)
    return jsonify(record)


@app.route("/api/data/db/files/<int:file_id>/preview", methods=["GET"])
def api_db_preview_file(file_id):
    """分页预览文件内容（按行读取，避免大文件 OOM）。"""
    mgr = _get_json_mgr()
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 500, type=int)
    result = mgr.preview_file(file_id, offset=offset, limit=limit)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/data/db/routes", methods=["GET"])
def api_db_routes_list():
    """查询达梦数据库中可用航线列表（供数据生成航线下拉选择）。"""
    mgr = _get_json_mgr()
    keyword = request.args.get("keyword", "")
    routes = mgr.query_available_routes(keyword=keyword)
    return jsonify({"routes": routes})


@app.route("/api/data/db/files/<int:file_id>/validate-route", methods=["GET"])
def api_db_validate_route(file_id):
    """校验文件关联的航线是否在数据库中存在。"""
    mgr = _get_json_mgr()
    record = mgr.get_file(file_id)
    if not record:
        return jsonify({"error": "文件不存在"}), 404
    linked_route = record.get("linked_route", "")
    result = mgr.validate_route_correlation(linked_route)
    return jsonify(result)


@app.route("/api/data/db/files", methods=["POST"])
def api_db_save_file():
    """新增或更新文件（JSON 内容或元数据）。

    支持 content 字段（写入磁盘），同时接受 alarm_type/simulator_id/linked_route/source。
    """
    mgr = _get_json_mgr()
    # 支持 JSON body 和 multipart form（文件上传）
    if request.content_type and "multipart" in request.content_type:
        # 文件上传
        uploaded = request.files.get("file")
        if not uploaded:
            return jsonify({"success": False, "message": "未选择文件"}), 400
        name = uploaded.filename or f"upload_{int(time.time())}.json"
        content = uploaded.read().decode("utf-8")
        data = {
            "name": name,
            "content": content,
            "source": "upload",
            "description": f"上传: {name}",
        }
    else:
        data = request.get_json(silent=True) or {}
        if not data.get("name") and not data.get("content") and not data.get("file_path"):
            return jsonify({"success": False, "message": "文件名和内容不能同时为空"}), 400
    try:
        fid = mgr.save_file(data)
        return jsonify({"success": True, "id": fid, "message": "已保存"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/data/db/files/<int:file_id>", methods=["PUT"])
def api_db_update_file(file_id):
    """重命名/编辑文件。"""
    mgr = _get_json_mgr()
    data = request.get_json(silent=True) or {}
    try:
        mgr.update_file(file_id, data)
        return jsonify({"success": True, "message": "已更新"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/data/db/files/<int:file_id>", methods=["DELETE"])
@_safe_json
def api_db_delete_file(file_id):
    """删除文件。"""
    mgr = _get_json_mgr()
    mgr.delete_file(file_id)
    return jsonify({"success": True, "message": "已删除"})


@app.route("/api/data/db/files/<int:file_id>/download", methods=["GET"])
def api_db_download_file(file_id):
    """下载文件内容为 JSON（从磁盘流式传输）。"""
    from flask import send_file
    mgr = _get_json_mgr()
    record = mgr.get_file(file_id)
    if not record:
        return jsonify({"error": "文件不存在"}), 404
    fpath = mgr._resolve_path(record)
    if not fpath or not os.path.exists(fpath):
        return jsonify({"error": "文件内容不可用"}), 404
    return send_file(
        fpath,
        mimetype="application/json",
        as_attachment=True,
        download_name=record.get("name", "file.json"),
    )


@app.route("/api/data/db/import", methods=["POST"])
def api_db_import_mock():
    """从 mock/ 目录批量导入到数据库。"""
    mgr = _get_json_mgr()
    result = mgr.import_from_mock()
    _add_log(f"已从 mock/ 导入: {result.get('imported',0)} 新增, {result.get('updated',0)} 更新, {result.get('skipped',0)} 跳过")
    return jsonify(result)


@app.route("/api/data/db/export/<int:file_id>", methods=["POST"])
def api_db_export_mock(file_id):
    """从数据库导出到 mock/ 目录。"""
    mgr = _get_json_mgr()
    result = mgr.export_to_mock(file_id)
    return jsonify(result)


@app.route("/api/data/db/export-batch", methods=["POST"])
def api_db_export_batch():
    """批量从数据库导出到 mock/ 目录。"""
    data = request.get_json(silent=True) or {}
    file_ids = data.get("file_ids", [])
    if not file_ids:
        return jsonify({"success": 0, "total": 0, "results": []})
    mgr = _get_json_mgr()
    result = mgr.export_to_mock_batch(file_ids)
    return jsonify(result)


@app.route("/api/data/db/export-all", methods=["POST"])
@_safe_json
def api_db_export_all():
    """从数据库导出所有文件到 mock/ 目录（Docker 重建后恢复用）。"""
    mgr = _get_json_mgr()
    result = mgr.export_all_to_mock()
    _add_log(f"全部导出: {result.get('message', '')}")
    return jsonify(result)


@app.route("/api/data/db/categories", methods=["GET"])
def api_db_categories():
    """获取所有分类和告警类型。"""
    mgr = _get_json_mgr()
    return jsonify({
        "categories": mgr.get_categories(),
        "alarm_types": mgr.get_alarm_types(),
    })


@app.route("/api/data/db/categories", methods=["PUT"])
def api_db_rename_category():
    """重命名分类。"""
    data = request.get_json(silent=True) or {}
    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()
    mgr = _get_json_mgr()
    result = mgr.rename_category(old_name, new_name)
    return jsonify(result)


@app.route("/api/data/db/categories/<name>", methods=["DELETE"])
@_safe_json
def api_db_delete_category(name):
    """删除分类（清空关联文件的分类字段）。"""
    mgr = _get_json_mgr()
    result = mgr.delete_category(name)
    return jsonify(result)


# ── 告警类型自定义管理 API ─────────────────────────────────────────

@app.route("/api/data/db/alarm-types", methods=["GET"])
def api_db_alarm_types_list():
    """获取所有告警类型（含自定义颜色、描述等）。"""
    mgr = _get_json_mgr()
    types = mgr.list_alarm_types_full()
    return jsonify({"alarm_types": types})


@app.route("/api/data/db/alarm-types", methods=["POST"])
def api_db_alarm_types_add():
    """新增自定义告警类型。"""
    mgr = _get_json_mgr()
    data = request.get_json(silent=True) or {}
    result = mgr.add_alarm_type(
        name=data.get("name", ""),
        color=data.get("color", "#64748b"),
        description=data.get("description", ""),
    )
    return jsonify(result)


@app.route("/api/data/db/alarm-types/<int:type_id>", methods=["PUT"])
def api_db_alarm_types_update(type_id):
    """更新告警类型（名称/颜色/描述）。"""
    mgr = _get_json_mgr()
    data = request.get_json(silent=True) or {}
    result = mgr.update_alarm_type(type_id, data)
    return jsonify(result)


@app.route("/api/data/db/alarm-types/<int:type_id>", methods=["DELETE"])
@_safe_json
def api_db_alarm_types_delete(type_id):
    """删除告警类型（内置类型不可删除）。"""
    mgr = _get_json_mgr()
    result = mgr.delete_alarm_type(type_id)
    return jsonify(result)


# ==================== AI 数据生成 API ================================

_ai_gen = None

def _get_ai_gen():
    global _ai_gen
    if _ai_gen is None:
        from ai import ai_data_gen as aig
        _ai_gen = aig
    return _ai_gen


@app.route("/api/ai/templates", methods=["GET"])
def api_ai_templates():
    """获取所有 Prompt 模板列表。"""
    mgr = _get_ai_gen()
    return jsonify({"templates": mgr.list_templates()})


@app.route("/api/ai/generate", methods=["POST"])
def api_ai_generate():
    """调用大模型生成 JSON 数据。"""
    data = request.get_json(silent=True) or {}
    api_url = data.get("api_url", "").strip()
    api_key = data.get("api_key", "").strip()
    model = data.get("model", "").strip()
    template_name = data.get("template_name", "")
    params = data.get("params", {})
    save_to_db = data.get("save_to_db", True)
    save_name = data.get("save_name", "").strip()

    if not api_url:
        return jsonify({"success": False, "error": "API URL 不能为空"}), 400
    if not api_key:
        return jsonify({"success": False, "error": "API Key 不能为空"}), 400
    if not template_name:
        return jsonify({"success": False, "error": "请选择 Prompt 模板"}), 400

    mgr = _get_ai_gen()
    result = mgr.generate_and_save(
        api_url=api_url,
        api_key=api_key,
        model=model,
        template_name=template_name,
        params=params,
        save_to_db=save_to_db,
        save_name=save_name,
    )

    if result.get("success"):
        _add_log(f"AI 生成成功: {template_name} ({len(str(result.get('data',''))) if result.get('data') else 0} chars)")
    else:
        _add_log(f"AI 生成失败: {template_name} — {result.get('error','')}")

    return jsonify(result)


# ==================== 场景编排 API ===================================

_orchestrator = None


def _wait_with_stop(duration_sec: float, stop_event) -> None:
    """等待指定秒数，期间检查停止信号（0.5s 粒度）。"""
    if stop_event is None:
        time.sleep(duration_sec)
        return
    deadline = time.time() + duration_sec
    while time.time() < deadline:
        if stop_event.is_set():
            return
        time.sleep(0.5)


def _get_orchestrator():
    """获取场景编排调度器单例。首次调用时初始化并启动 cron 调度线程。"""
    global _orchestrator
    if _orchestrator is None:
        from orchestrator import get_orchestrator

        def _run_scene(scene, stop_event=None):
            """编排回调：执行场景中的所有任务（支持通过 stop_event 取消）。"""
            from orchestrator import get_orchestrator as _get_och
            och = _get_och()
            scene_id = scene["id"]
            scene_name = scene.get("name", f"scene-{scene_id}")
            tasks = och.list_tasks(scene_id)

            _add_log(f"[场景编排] {scene_name} 开始执行 ({len(tasks)} 个任务)")

            for task in tasks:
                # 每个任务前检查停止信号
                if stop_event and stop_event.is_set():
                    _add_log(f"[场景编排] {scene_name} 收到停止信号，终止执行")
                    return f"场景已停止: {scene_name}"

                task_id = task["id"]
                task_name = task.get("name", f"task-{task_id}")
                task_type = task.get("task_type", "sequential")
                cycle_interval = task.get("cycle_interval_sec", 0)
                repeat_count = task.get("repeat_count", 1)
                timeout_sec = task.get("execution_timeout_sec", 300)
                files = och.list_task_files(task_id)

                if not files:
                    _add_log(f"[场景编排] 任务 '{task_name}' 无关联文件，跳过")
                    continue

                _add_log(f"[场景编排] 任务 '{task_name}' ({task_type}, {len(files)} 个文件, 重复{repeat_count}次)")

                for rep in range(repeat_count):
                    if stop_event and stop_event.is_set():
                        _add_log(f"[场景编排] {scene_name} 收到停止信号，终止执行")
                        return f"场景已停止: {scene_name}"

                    if task_type == "sequential":
                        # 顺序执行：按文件列表顺序逐个执行
                        for fi, tf in enumerate(files):
                            if stop_event and stop_event.is_set():
                                break
                            _execute_scene_file(tf, scene, task, rep + 1, stop_event)
                            if stop_event and stop_event.is_set():
                                break
                            interval = tf.get("interval_sec", 0)
                            if interval > 0 and fi < len(files) - 1:
                                _add_log(f"[场景编排] 文件间隔等待 {interval}s")
                                _wait_with_stop(interval, stop_event)
                                if stop_event and stop_event.is_set():
                                    break
                    elif task_type == "parallel":
                        # 并行执行：多线程同时执行所有文件
                        from concurrent.futures import ThreadPoolExecutor, wait as _futures_wait, FIRST_COMPLETED
                        max_workers = min(len(files), 5)  # 最多5个并发
                        with ThreadPoolExecutor(max_workers=max_workers) as executor:
                            futures = [
                                executor.submit(_execute_scene_file, tf, scene, task, rep + 1, stop_event)
                                for tf in files
                            ]
                            # 使用 wait 循环检查停止信号（而非阻塞的 result）
                            remaining = list(futures)
                            while remaining:
                                if stop_event and stop_event.is_set():
                                    _add_log(f"[场景编排] 收到停止信号，等待并行任务退出...")
                                    for f in remaining:
                                        try:
                                            f.result(timeout=timeout_sec)
                                        except Exception:
                                            pass
                                    break
                                done, remaining = _futures_wait(
                                    remaining, timeout=1.0,
                                    return_when=FIRST_COMPLETED
                                )
                                for f in done:
                                    try:
                                        f.result(timeout=0)
                                    except Exception as exc:
                                        _add_log(f"[场景编排] 并行执行异常: {exc}")

                    # 循环间隔等待
                    if cycle_interval > 0 and rep < repeat_count - 1:
                        if stop_event and stop_event.is_set():
                            break
                        _add_log(f"[场景编排] 循环间隔等待 {cycle_interval}s")
                        _wait_with_stop(cycle_interval, stop_event)

                if stop_event and stop_event.is_set():
                    _add_log(f"[场景编排] {scene_name} 收到停止信号，终止执行")
                    return f"场景已停止: {scene_name}"

            _add_log(f"[场景编排] {scene_name} 执行完成")
            return f"场景完成: {scene_name}"

        def _execute_scene_file(tf, scene, task, rep_num, stop_event=None):
            """执行单个场景文件（支持通过 stop_event 取消）。"""
            try:
                import json_data_manager as jdm
                file_id = tf.get("file_id", 0)
                record = jdm.get_file(int(file_id))
                if not record:
                    _add_log(f"[场景编排] 文件 ID={file_id} 不存在")
                    return

                # 复制文件到 mock/ 目录
                mock_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mock")
                os.makedirs(mock_dir, exist_ok=True)
                src_path = jdm._resolve_path(record)
                dest_path = os.path.join(mock_dir, record.get("name", ""))
                if src_path and os.path.exists(src_path):
                    if os.path.abspath(src_path) != os.path.abspath(dest_path):
                        import shutil
                        shutil.copy2(src_path, dest_path)

                mode = scene.get("sim_mode", "scene")
                params = {
                    "mode": mode,
                    "target_drones": 10,
                    "duration_min": 5,
                }
                if mode in ("replay", "replay_once"):
                    params["data_file"] = record.get("name", "")
                elif mode == "scene":
                    params["scene_files"] = [record.get("name", "")]

                task_name = task.get("name", "")
                _add_log(f"[场景编排] 执行: {task_name} #{rep_num} → {record.get('name', '')}")

                runner = SimulationRunner(params)
                runner.start()
                wait = params.get("duration_min", 5) * 60
                deadline = time.time() + min(wait, 3600)
                while runner._running and time.time() < deadline:
                    if stop_event and stop_event.is_set():
                        _add_log(f"[场景编排] 收到停止信号，正在停止仿真...")
                        runner.stop()
                        break
                    time.sleep(1)
                else:
                    # 正常运行结束或超时
                    if runner._running:
                        runner.stop()

            except Exception as e:
                _add_log(f"[场景编排] 文件执行异常: {e}")

        _orchestrator = get_orchestrator(execute_callback=_run_scene)
    return _orchestrator


# 在后台线程中延迟初始化编排器，避免 MySQL 连接阻塞 Flask 服务启动
# （启动后台线程 2 秒后初始化，确保 Flask 先绑定端口响应 HTTP 请求）
_init_orch_done = False


def _init_orchestrator_deferred() -> None:
    """后台线程：延迟初始化场景编排调度器。"""
    global _init_orch_done
    import time as _time
    _time.sleep(2.0)  # 等待 Flask 端口绑定后再连接数据库
    try:
        _get_orchestrator()
        _init_orch_done = True
        print("[web_server] 场景编排调度器已在后台初始化", flush=True)
    except Exception as _orch_init_err:
        print(f"[web_server] 场景编排调度器初始化失败（DB 可能未就绪）: {_orch_init_err}", flush=True)


_init_orch_thread = threading.Thread(
    target=_init_orchestrator_deferred,
    daemon=True,
    name="orch-deferred-init",
)
_init_orch_thread.start()


# ── 场景 CRUD ───────────────────────────────────────────────────────

@app.route("/api/scenes", methods=["GET"])
@_safe_json
def api_scene_list():
    """列出所有场景。"""
    och = _get_orchestrator()
    scenes = och.list_scenes()
    return jsonify({"scenes": scenes})


@app.route("/api/scenes", methods=["POST"])
@_safe_json
def api_scene_create():
    """创建场景。"""
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"success": False, "message": "场景名称不能为空"}), 400
    och = _get_orchestrator()
    scene_id = och.create_scene(data)
    _add_log(f"场景已创建: {data.get('name', '')}")
    return jsonify({"success": True, "id": scene_id, "message": "已创建"})


@app.route("/api/scenes/<int:scene_id>", methods=["PUT"])
@_safe_json
def api_scene_update(scene_id):
    """更新场景。"""
    data = request.get_json(silent=True) or {}
    och = _get_orchestrator()
    och.update_scene(scene_id, data)
    return jsonify({"success": True, "message": "已更新"})


@app.route("/api/scenes/<int:scene_id>", methods=["DELETE"])
@_safe_json
def api_scene_delete(scene_id):
    """删除场景。"""
    och = _get_orchestrator()
    och.delete_scene(scene_id)
    return jsonify({"success": True, "message": "已删除"})


@app.route("/api/scenes/<int:scene_id>/toggle", methods=["POST"])
@_safe_json
def api_scene_toggle(scene_id):
    """启用/禁用场景。"""
    och = _get_orchestrator()
    updated = och.toggle_scene(scene_id)
    if updated is None:
        return jsonify({"success": False, "message": "场景不存在"}), 404
    return jsonify({"success": True, "enabled": updated.get("enabled"), "message": "已切换"})


@app.route("/api/scenes/<int:scene_id>/run-now", methods=["POST"])
@_safe_json
def api_scene_run_now(scene_id):
    """立即执行场景。"""
    och = _get_orchestrator()
    result = och.run_scene_now(scene_id)
    return jsonify(result)


@app.route("/api/scenes/<int:scene_id>/stop", methods=["POST"])
@_safe_json
def api_scene_stop(scene_id):
    """停止正在执行的场景。"""
    och = _get_orchestrator()
    if och.stop_scene(scene_id):
        _add_log(f"[场景编排] 收到停止请求: scene_id={scene_id}")
        return jsonify({"success": True, "message": "场景执行已停止"})
    return jsonify({"success": False, "message": "场景未在运行"}), 404


@app.route("/api/scenes/<int:scene_id>/history", methods=["GET"])
@_safe_json
def api_scene_history(scene_id):
    """获取场景执行历史。"""
    och = _get_orchestrator()
    history = och.get_scene_history(scene_id)
    return jsonify({"history": history})


@app.route("/api/scenes/health", methods=["GET"])
@_safe_json
def api_scene_health():
    """获取场景编排调度器健康状态。"""
    och = _get_orchestrator()
    health = och.get_health()
    return jsonify(health)


# ── 任务 CRUD（场景内）──────────────────────────────────────────────

@app.route("/api/scenes/<int:scene_id>/tasks", methods=["GET"])
@_safe_json
def api_scene_tasks_list(scene_id):
    """列出场景下的所有任务。"""
    och = _get_orchestrator()
    tasks = och.list_tasks(scene_id)
    return jsonify({"tasks": tasks})


@app.route("/api/scenes/<int:scene_id>/tasks", methods=["POST"])
@_safe_json
def api_scene_task_create(scene_id):
    """创建任务。"""
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"success": False, "message": "任务名称不能为空"}), 400
    data["scene_id"] = scene_id
    och = _get_orchestrator()
    task_id = och.create_task(data)
    return jsonify({"success": True, "id": task_id, "message": "已创建"})


@app.route("/api/scenes/<int:scene_id>/tasks/<int:task_id>", methods=["PUT"])
@_safe_json
def api_scene_task_update(scene_id, task_id):
    """更新任务（含名称修改）。"""
    data = request.get_json(silent=True) or {}
    och = _get_orchestrator()
    och.update_task(task_id, data)
    return jsonify({"success": True, "message": "已更新"})


@app.route("/api/scenes/<int:scene_id>/tasks/<int:task_id>", methods=["DELETE"])
@_safe_json
def api_scene_task_delete(scene_id, task_id):
    """删除任务。"""
    och = _get_orchestrator()
    och.delete_task(task_id)
    return jsonify({"success": True, "message": "已删除"})


@app.route("/api/scenes/<int:scene_id>/tasks/reorder", methods=["POST"])
@_safe_json
def api_scene_tasks_reorder(scene_id):
    """重新排序任务。"""
    data = request.get_json(silent=True) or {}
    task_ids = data.get("task_ids", [])
    och = _get_orchestrator()
    och.reorder_tasks(scene_id, task_ids)
    return jsonify({"success": True, "message": "已排序"})


# ── 任务文件 CRUD ───────────────────────────────────────────────────

@app.route("/api/scenes/<int:scene_id>/tasks/<int:task_id>/files", methods=["GET"])
@_safe_json
def api_task_files_list(scene_id, task_id):
    """列出任务下的所有文件关联。"""
    och = _get_orchestrator()
    files = och.list_task_files(task_id)
    return jsonify({"files": files})


@app.route("/api/scenes/<int:scene_id>/tasks/<int:task_id>/files", methods=["POST"])
@_safe_json
def api_task_file_add(scene_id, task_id):
    """为任务添加文件。"""
    data = request.get_json(silent=True) or {}
    if not data.get("file_id"):
        return jsonify({"success": False, "message": "file_id 不能为空"}), 400
    data["task_id"] = task_id
    och = _get_orchestrator()
    rel_id = och.add_task_file(data)
    return jsonify({"success": True, "id": rel_id, "message": "已添加"})


@app.route("/api/scenes/<int:scene_id>/tasks/<int:task_id>/files/<int:file_rel_id>", methods=["PUT"])
@_safe_json
def api_task_file_update(scene_id, task_id, file_rel_id):
    """更新文件关联（修改间隔等）。"""
    data = request.get_json(silent=True) or {}
    och = _get_orchestrator()
    och.update_task_file(file_rel_id, data)
    return jsonify({"success": True, "message": "已更新"})


@app.route("/api/scenes/<int:scene_id>/tasks/<int:task_id>/files/<int:file_rel_id>", methods=["DELETE"])
@_safe_json
def api_task_file_remove(scene_id, task_id, file_rel_id):
    """移除文件关联。"""
    och = _get_orchestrator()
    och.remove_task_file(file_rel_id)
    return jsonify({"success": True, "message": "已移除"})



# ==================== 日志流 API =====================================

@app.route("/api/logs", methods=["GET"])
def api_logs_query():
    """查询历史日志。"""
    types_str = request.args.get("types", "")
    types = [t.strip() for t in types_str.split(",") if t.strip()] if types_str else None
    keyword = request.args.get("keyword", "")
    limit = request.args.get("limit", 200, type=int)
    since = request.args.get("since", "")

    streamer = _get_streamer()
    logs = streamer.get_logs(types=types, keyword=keyword, limit=limit, since=since)
    counts = streamer.get_counts()
    return jsonify({"logs": logs, "counts": counts})


@app.route("/api/logs/export", methods=["POST"])
def api_logs_export():
    """导出日志。"""
    data = request.get_json(silent=True) or {}
    types_str = data.get("types", "")
    types = [t.strip() for t in types_str.split(",") if t.strip()] if types_str else None
    fmt = data.get("format", "json")
    keyword = data.get("keyword", "")

    from flask import Response as _Response
    streamer = _get_streamer()
    result = streamer.export_logs(types=types, fmt=fmt, keyword=keyword)

    mime_map = {"json": "application/json", "csv": "text/csv", "txt": "text/plain"}
    ts = time.strftime("%Y%m%d_%H%M%S")
    return _Response(
        result.get("content", ""),
        mimetype=mime_map.get(fmt, "text/plain"),
        headers={"Content-Disposition": f"attachment; filename=sim-logs-{ts}.{fmt}"},
    )


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    """清空日志缓冲区。"""
    streamer = _get_streamer()
    streamer.clear()
    return jsonify({"success": True, "message": "日志已清空"})


@app.route("/api/logs/export/db", methods=["POST"])
def api_logs_export_db():
    """从 MySQL 导出持久化日志（支持日期范围、类型过滤、关键字搜索）。"""
    data = request.get_json(silent=True) or {}
    start_date = data.get("start_date", "")
    end_date = data.get("end_date", "")
    types_str = data.get("types", "")
    types = [t.strip() for t in types_str.split(",") if t.strip()] if types_str else None
    keyword = data.get("keyword", "")
    fmt = data.get("format", "json")

    from flask import Response as _Response
    streamer = _get_streamer()
    logs = streamer.export_logs_from_db(
        start_date=start_date,
        end_date=end_date,
        types=types,
        keyword=keyword,
    )

    if fmt == "csv":
        lines = ["time,type,type_name,message,detail"]
        for l in logs:
            msg = (l.get("message", "") or "").replace('"', '""')
            tn = (l.get("type_name", "") or "").replace('"', '""')
            detail_str = ""
            if l.get("detail"):
                detail_str = json.dumps(l["detail"], ensure_ascii=False).replace('"', '""')
            lines.append(f'{l.get("time","")},{l.get("type","")},"{tn}","{msg}","{detail_str}"')
        content = "\n".join(lines)
        mime = "text/csv;charset=utf-8"
    else:
        content = json.dumps(logs, ensure_ascii=False, indent=2)
        mime = "application/json;charset=utf-8"

    ts = time.strftime("%Y%m%d_%H%M%S")
    return _Response(
        content,
        mimetype=mime,
        headers={"Content-Disposition": f"attachment; filename=sim-logs-db-{ts}.{fmt}"},
    )


@app.route("/api/sim/retry-alarm-details", methods=["POST"])
def api_retry_alarm_details():
    """触发态势监控器重新获取告警详情。"""
    monitor = _get_situation_monitor()
    if monitor:
        monitor._alert_retry_count = 0
        monitor._pending_alarm_fallback = False
        _get_streamer().push("sim_status", "告警详情重试已触发")
        return jsonify({"success": True, "message": "已触发告警详情重试"})
    return jsonify({"success": False, "message": "态势监控未启动"}), 503


@app.route("/api/logs/types", methods=["GET"])
def api_logs_types():
    """获取日志类型列表。"""
    from log_streamer import LOG_TYPES
    return jsonify({"types": LOG_TYPES})


# ── WebSocket 事件 ────────────────────────────────────────────────

@socketio.on("connect")
def handle_connect():
    """WebSocket 客户端连接时推送当前状态。"""
    with _lock:
        emit("status", dict(_runtime_state))
        emit("status_change", {
            "event": "connected",
            "message": f"WebSocket 已连接，当前运行状态: {_runtime_state['running']}"
        })


@socketio.on("disconnect")
def handle_disconnect():
    pass


# ==================== 入口 ========================================
if __name__ == "__main__":
    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_PORT", "5000"))
    print(f"utm_moc52 Web 服务启动: http://{host}:{port}")
    print(f"  - 配置: Redis={_current_config['redis_ip']}:{_current_config['redis_port']}")
    print(f"  - 配置: Kafka={_current_config['kafka_url']}")
    print("  按 Ctrl+C 停止服务")
    # 重启后等待端口释放（Windows TIME_WAIT 约 120 秒，但通常 2 秒内释放）
    if os.environ.get("UTM_RESTART") == "1":
        import time as _t
        print("[web_server] 等待端口释放...", flush=True)
        _t.sleep(2.0)
    # ── 启动预热：提前建表，避免首次 API 请求承受全部延迟 ──
    # 注意：init_tables() 内部已通过 _get_client() 连接 MySQL 并验证建表，
    # 返回后连接就绪，无需再次调用 _get_client()（可能导致锁竞争）。
    # 整个预热放在后台线程中执行，确保 Flask 端口优先绑定。
    def _warmup_db() -> None:
        try:
            import mysql_db_manager as _warmup_mdb
            print("[web_server] 预热数据库...", flush=True)
            _warmup_mdb.init_tables()
            print("[web_server] 数据库预热完成", flush=True)
        except Exception as e:
            print(f"[web_server] 数据库预热跳过: {e}", flush=True)

    _warmup_thread = threading.Thread(
        target=_warmup_db, daemon=True, name="db-warmup"
    )
    _warmup_thread.start()
    # 达梦连接在首次 generate 页面使用航线选择时惰性加载，无需预热
    try:
        print(f"[web_server] 正在启动 HTTP 服务 {host}:{port} ...", flush=True)
        socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)
    except Exception as e:
        import traceback
        print(f"[web_server] 启动失败: {e}", flush=True)
        traceback.print_exc()
        raise