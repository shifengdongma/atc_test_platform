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
from typing import Any, Dict, List, Optional

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

from redis_client import RedisClient
from kafka_proc import KafkaProducerClient
from config import load_config, AppConfig
from sim_manager import SimulationManager
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
REDIS_FLIGHT_PLAN_KEY = "BIZ_DATA:UAV_ROUTE"
REDIS_AIRSPACE_KEY = "BIZ_DATA:AIRSPACE"
KAFKA_UAV_DATA_TOPIC = "uav_runtime_data"
KAFKA_TRACE_TOPIC = "uav_runtime_trace"
DEFAULT_TARGET_DRONES = 1

# ── Flask 应用初始化 ───────────────────────────────────────────────
app = Flask(__name__, static_folder="web/static", static_url_path="/static")
app.config["SECRET_KEY"] = "utm_moc52_web_secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── 全局状态（线程安全通过 _lock 保护） ────────────────────────────
_lock = threading.Lock()

_current_config: Dict[str, Any] = {
    "mode": "dynamic",  # dynamic / replay / replay_once / scene / plan
    "target_drones": DEFAULT_TARGET_DRONES,
    "nfz_enabled": True,
    "nfz_count": 3,
    "redis_ip": getattr(_env, "redis_ip", "127.0.0.1"),
    "redis_port": getattr(_env, "redis_port", "6379"),
    "kafka_url": getattr(_env, "kafka_url", "127.0.0.1:9092"),
    "api_mode": False,          # 是否通过 ATC API 创建飞行任务
    "api_base_url": "https://dkkgsit-test.testdolphin.com",
    # scene 模式参数
    "scene_files": [],
    "scene_dir": None,
    "scene_interval": 1000,
    "timestamp_mode": "replace",  # replace / align / preserve
    "scene_loop": False,
    # plan 模式参数
    "plan_selected_uids": [],  # 用户选择的航线 UID 列表，空表示全部
    # replay_once 模式参数
    "data_file": "kafka_data.json",
    "route_file": "redis_route.json",
}

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
    except Exception:
        pass


def _get_streamer():
    """惰性导入 log_streamer 单例，绑定 WebSocket 推送。"""
    import log_streamer as _ls
    s = _ls.get_streamer()
    if s._callback is None:
        def _ws_push(entry):
            socketio.emit("log_entry", entry)
        s._callback = _ws_push
        s.push("sim_status", "日志采集服务已就绪")
    return s


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

        # 构建 AppConfig 供 SimulationManager 使用
        self._app_cfg = AppConfig()
        self._app_cfg.simulation.target_drones = self.target_drones

        # SimulationManager 实例（dynamic/replay 模式）
        self._sim_mgr: Optional[SimulationManager] = None
        # PlanRunner 实例（plan 模式，复用 run_plan.py 的独立线程模型）
        self._plan_runner = None
        # plan 模式：用户选择的航线 UID 白名单
        self._plan_selected_uids: Optional[set] = None

        # 检查连接状态
        try:
            test_redis = RedisClient(
                config["redis_ip"], config["redis_port"],
                getattr(_env, "redis_password", ""),
            )
            with _lock:
                _runtime_state["redis_connected"] = test_redis.client is not None
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
        """初始化 Redis 计划插值模式（复用 run_plan.py 的 PlanRunner 逻辑）。"""
        from tools.run_plan import PlanRunner as _PlanRunner
        self._plan_runner = _PlanRunner(log_callback=_add_log)
        # 读取用户选择的航线 UID 列表
        uids = self.config.get("plan_selected_uids", [])
        selected = set(uids) if uids else None
        self._plan_runner.start_background(selected_uids=selected)
        if selected:
            _add_log(f"Redis 计划插值模式已启动（已选 {len(selected)} 条航线），后台线程运行中")
        else:
            _add_log("Redis 计划插值模式已启动（全部航线），后台线程运行中")

    def _sim_loop(self) -> None:
        """仿真主循环（后台线程），通过 SimulationManager 或 PlanRunner 驱动。"""
        self._running = True
        self._start_time = time.time()

        if self.mode in ("dynamic", "replay"):
            # 使用 SimulationManager 统一编排（桥接日志到前端）
            self._sim_mgr = SimulationManager(self._app_cfg, log_callback=_add_log)
            self._sim_mgr.start(mode=self.mode, target_drones=self.target_drones)

            with _lock:
                _runtime_state["redis_connected"] = self._sim_mgr.redis.client is not None
                _runtime_state["kafka_connected"] = self._sim_mgr.kafka_producer.is_connected()

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
                mock_dir = os.path.join(_root, "mock")
                _rk.KAFKA_DATA_JSON_PATH = os.path.join(mock_dir, data_file)
                _rk.REDIS_ROUTE_JSON_PATH = os.path.join(mock_dir, route_file)
                ds = _rk.DataSource()
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
                        except Exception as e:
                            _add_log(f"Kafka 发送失败: {e}")
                        with _lock:
                            _runtime_state["active_drones"] = len(ds.allowed_uav_uids)
                            _runtime_state["kafka_msg_per_sec"] = len(batch)
                            if self._start_time:
                                _runtime_state["uptime_sec"] = int(time.time() - self._start_time)
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
            scene_files = [os.path.join(_root, "mock", f) for f in self.config.get("scene_files", []) if f]
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
                    )
                    emitter.start()
                    with _lock:
                        _runtime_state["active_drones"] = len(emitter.uav_data_list)

                    while self._running and emitter.running:
                        try:
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

    def _push_status(self) -> None:
        """推送运行时状态到所有 WebSocket 客户端。"""
        with _lock:
            if self._start_time:
                _runtime_state["uptime_sec"] = int(time.time() - self._start_time)
            status = dict(_runtime_state)
        socketio.emit("status", status)

    def _cleanup(self) -> None:
        """清理资源。"""
        _add_log("仿真运行结束，清理资源...")
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

        self._thread = threading.Thread(target=self._sim_loop, daemon=True)
        self._thread.start()

        socketio.emit("status_change", {"event": "started", "message": "仿真已启动"})

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
    """首页重定向到仿真配置页。"""
    from flask import redirect as _redirect
    return _redirect("/config")


@app.route("/config")
def page_config():
    """仿真配置页。"""
    return send_from_directory("web/pages", "config.html")


@app.route("/run")
def page_run():
    """仿真执行页。"""
    return send_from_directory("web/pages", "run.html")


@app.route("/generate")
def page_generate():
    """模拟数据生成页。"""
    return send_from_directory("web/pages", "generate.html")


@app.route("/data")
def page_data():
    """JSON 数据管理页。"""
    return send_from_directory("web/pages", "data.html")


@app.route("/env")
def page_env():
    """环境变量管理页。"""
    return send_from_directory("web/pages", "env.html")


@app.route("/logs")
def page_logs():
    """系统日志页。"""
    return send_from_directory("web/pages", "logs.html")


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
                     "data_file", "route_file", "plan_selected_uids"):
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
                "data_file", "route_file", "plan_selected_uids"):
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
    """停止仿真。"""
    global _sim_runner
    if not _sim_runner:
        return jsonify({"success": False, "message": "无运行中的仿真"}), 404

    _sim_runner.stop()
    _sim_runner = None
    return jsonify({"success": True, "message": "仿真已停止"})


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
        cfg_path = os.path.join(_root, "config.json")
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


# ── 数据文件管理 API（Task 1: 前端数据可视化增强） ─────────────

@app.route("/api/data/files", methods=["GET"])
def api_list_data_files():
    """列出 mock/ 目录下可用的 JSON 数据文件。"""
    mock_dir = os.path.join(_root, "mock")
    if not os.path.exists(mock_dir):
        return jsonify({"files": [], "error": "mock/ 目录不存在"})

    files = []
    for name in os.listdir(mock_dir):
        if name.endswith(".json"):
            path = os.path.join(mock_dir, name)
            size = os.path.getsize(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    records = len(data)
                    sample_keys = list(data[0].keys())[:5] if data else []
                elif isinstance(data, dict):
                    # redis_route.json 之类的是 dict
                    records = len(data)
                    sample_keys = list(data.keys())[:5]
                else:
                    records = 0
                    sample_keys = []
            except Exception:
                records = -1
                sample_keys = []

            files.append({
                "name": name,
                "size": size,
                "size_kb": round(size / 1024, 1),
                "records": records,
                "sample_keys": sample_keys,
            })

    return jsonify({"files": sorted(files, key=lambda f: f["name"])})


@app.route("/api/data/files/<filename>", methods=["GET"])
def api_get_data_file(filename: str):
    """查看 JSON 文件内容（分页）。"""
    mock_dir = os.path.join(_root, "mock")
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

            # 构建 routeList
            route_list = []
            for j in range(len(waypoints) - 1):
                route_list.append({
                    "sequence": j,
                    "type": 2,
                    "segmentStartLon": round(waypoints[j][0], 6),
                    "segmentStartLat": round(waypoints[j][1], 6),
                    "segmentEndLon": round(waypoints[j + 1][0], 6),
                    "segmentEndLat": round(waypoints[j + 1][1], 6),
                    "segmentStartHeight": 100.0 + j * 50,
                    "segmentEndHeight": 100.0 + (j + 1) * 50,
                    "segmentProtectHeight": 50.0,
                    "segmentProtectHeightType": 1,
                    "segmentWidth": 100.0,
                })

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

        # 保存到 mock/ 目录
        mock_dir = os.path.join(_root, "mock")
        os.makedirs(mock_dir, exist_ok=True)
        ts = int(time.time())
        kafka_file = os.path.join(mock_dir, f"kafka_data_gen_{ts}.json")
        with open(kafka_file, "w", encoding="utf-8") as f:
            json.dump(generated, f, ensure_ascii=False, indent=2)

        _add_log(f"已生成 {count} 架无人机数据 → {os.path.basename(kafka_file)} (模式: {pattern})")

        return jsonify({
            "success": True,
            "message": f"已生成 {count} 条数据记录",
            "file": os.path.basename(kafka_file),
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
        mock_dir = os.path.join(_root, "mock")
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

    mock_dir = os.path.join(_root, "mock")
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
        _add_log(f"已切换环境配置: Redis={cfg.get('redis_ip')}:{cfg.get('redis_port')}, Kafka={cfg.get('kafka_url')}")
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
    """分页查询数据库中的 JSON 文件。"""
    mgr = _get_json_mgr()
    category = request.args.get("category", "")
    keyword = request.args.get("keyword", "")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    result = mgr.list_files(category=category, keyword=keyword, page=page, page_size=page_size)
    return jsonify(result)


@app.route("/api/data/db/files/<int:file_id>", methods=["GET"])
def api_db_get_file(file_id):
    """获取文件详情。"""
    mgr = _get_json_mgr()
    record = mgr.get_file(file_id)
    if not record:
        return jsonify({"error": "文件不存在"}), 404
    return jsonify(record)


@app.route("/api/data/db/files", methods=["POST"])
def api_db_save_file():
    """新增或更新文件（JSON 内容或文件上传）。"""
    mgr = _get_json_mgr()
    data = request.get_json(silent=True) or {}
    if not data.get("name") and not data.get("content"):
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
def api_db_delete_file(file_id):
    """删除文件。"""
    mgr = _get_json_mgr()
    mgr.delete_file(file_id)
    return jsonify({"success": True, "message": "已删除"})


@app.route("/api/data/db/files/<int:file_id>/download", methods=["GET"])
def api_db_download_file(file_id):
    """下载文件内容为 JSON。"""
    from flask import Response as _Response
    mgr = _get_json_mgr()
    record = mgr.download_file(file_id)
    if not record:
        return jsonify({"error": "文件不存在"}), 404
    return _Response(
        record["content"],
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={record['name']}"},
    )


@app.route("/api/data/db/import", methods=["POST"])
def api_db_import_mock():
    """从 mock/ 目录批量导入到数据库。"""
    mgr = _get_json_mgr()
    result = mgr.import_from_mock()
    _add_log(f"已从 mock/ 导入 {result['imported']} 个文件到数据库")
    return jsonify(result)


@app.route("/api/data/db/export/<int:file_id>", methods=["POST"])
def api_db_export_mock(file_id):
    """从数据库导出到 mock/ 目录。"""
    mgr = _get_json_mgr()
    result = mgr.export_to_mock(file_id)
    return jsonify(result)


@app.route("/api/data/db/categories", methods=["GET"])
def api_db_categories():
    """获取所有分类。"""
    mgr = _get_json_mgr()
    return jsonify({"categories": mgr.get_categories()})


# ==================== AI 数据生成 API ================================

_ai_gen = None

def _get_ai_gen():
    global _ai_gen
    if _ai_gen is None:
        import ai_data_gen as aig
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


# ==================== 定时任务调度 API ===============================

_scheduler = None

def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        from scheduler import get_scheduler

        def _run_task(task):
            """调度器回调：执行仿真任务。"""
            mode = task.get("sim_mode", "replay")
            params = {}
            try:
                sim_params = task.get("sim_params", "{}")
                if isinstance(sim_params, str):
                    params = json.loads(sim_params)
                else:
                    params = sim_params or {}
            except (json.JSONDecodeError, TypeError):
                pass

            params["mode"] = mode
            params["target_drones"] = params.get("target_drones", 10)

            _add_log(f"[定时任务] {task.get('name','')} 开始执行 (模式={mode})")
            try:
                runner = SimulationRunner(params)
                runner.start()
                # 等待仿真运行（最多1小时）
                wait = params.get("duration_min", 10) * 60
                deadline = time.time() + min(wait, 3600)
                while runner._running and time.time() < deadline:
                    time.sleep(1)
                runner.stop()
                return f"任务完成: {task.get('name','')} (模式={mode}, 运行{params.get('duration_min',10)}分钟)"
            except Exception as e:
                return f"任务异常: {e}"

        _scheduler = get_scheduler(execute_callback=_run_task)
    return _scheduler


@app.route("/api/schedule/tasks", methods=["GET"])
def api_schedule_list():
    """列出所有定时任务。"""
    sch = _get_scheduler()
    tasks = sch.list_tasks()
    return jsonify({"tasks": tasks})


@app.route("/api/schedule/tasks", methods=["POST"])
def api_schedule_create():
    """创建定时任务。"""
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"success": False, "message": "任务名称不能为空"}), 400
    sch = _get_scheduler()
    tid = sch.add_task(data)
    _add_log(f"定时任务已创建: {data.get('name','')}")
    return jsonify({"success": True, "id": tid, "message": "已创建"})


@app.route("/api/schedule/tasks/<int:task_id>", methods=["PUT"])
def api_schedule_update(task_id):
    """更新定时任务。"""
    data = request.get_json(silent=True) or {}
    sch = _get_scheduler()
    sch.update_task(task_id, data)
    return jsonify({"success": True, "message": "已更新"})


@app.route("/api/schedule/tasks/<int:task_id>", methods=["DELETE"])
def api_schedule_delete(task_id):
    """删除定时任务。"""
    sch = _get_scheduler()
    sch.delete_task(task_id)
    return jsonify({"success": True, "message": "已删除"})


@app.route("/api/schedule/tasks/<int:task_id>/pause", methods=["POST"])
def api_schedule_pause(task_id):
    sch = _get_scheduler()
    sch.pause_task(task_id)
    return jsonify({"success": True, "message": "已暂停"})


@app.route("/api/schedule/tasks/<int:task_id>/resume", methods=["POST"])
def api_schedule_resume(task_id):
    sch = _get_scheduler()
    sch.resume_task(task_id)
    return jsonify({"success": True, "message": "已恢复"})


@app.route("/api/schedule/tasks/<int:task_id>/run-now", methods=["POST"])
def api_schedule_run_now(task_id):
    """立即执行一次。"""
    sch = _get_scheduler()
    result = sch.run_now(task_id)
    return jsonify(result)


@app.route("/api/schedule/tasks/<int:task_id>/history", methods=["GET"])
def api_schedule_history(task_id):
    """获取任务执行历史。"""
    sch = _get_scheduler()
    history = sch.get_history(task_id)
    return jsonify({"history": history})


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
    socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)