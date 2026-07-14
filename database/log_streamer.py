# -*- coding: utf-8 -*-
"""
实时日志流 — 统一采集 Redis/Kafka/DB/仿真状态日志

通过 WebSocket 实时推送到前端，支持按类型过滤、关键字搜索、导出。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

try:
    import pymysql
    _HAS_PYMYSQL = True
except ImportError:
    pymysql = None  # type: ignore
    _HAS_PYMYSQL = False

from mysql_db_manager import query, query_all, _now, init_tables

# ── MySQL 持久化（可选，优雅降级） ─────────────────────────────────
try:
    _atc_tools = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "atc_api_autotest", "api_tools",
    )
    if _atc_tools not in sys.path:
        sys.path.insert(0, _atc_tools)
    from mysqldbclient import MysqlDbClient
    _HAS_MYSQL = True
except (ImportError, Exception):
    _HAS_MYSQL = False
    MysqlDbClient = None

# 从统一配置加载 MySQL 连接参数
try:
    _common_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common")
    if _common_path not in sys.path:
        sys.path.insert(0, _common_path)
    from config import load_mysql_config as _load_mysql_cfg
    _mysql_cfg = _load_mysql_cfg()
except Exception:
    _mysql_cfg = None
    _load_mysql_cfg = None

def _create_mysql_client():
    """使用统一配置创建 MysqlDbClient。

    MySQL 未显式配置时返回 None，调用方应跳过 MySQL 持久化。
    """
    if _mysql_cfg and _mysql_cfg.configured:
        return MysqlDbClient(
            host=_mysql_cfg.host, port=_mysql_cfg.port, user=_mysql_cfg.user,
            password=_mysql_cfg.password, database=_mysql_cfg.database,
            charset=_mysql_cfg.charset,
        )
    return None


LOG_TABLE = "sim_task_logs"

# 日志类型
LOG_TYPES = {
    "redis_route": "Redis 航线变更",
    "redis_airspace": "Redis 空域变更",
    "kafka_telemetry": "Kafka 遥测",
    "kafka_trace": "Kafka 轨迹预测",
    "db_run_data": "数据库运行日志",
    "db_traffic": "数据库流量日志",
    "db_alarm": "数据库告警日志",
    "sim_status": "仿真状态",
    "situation_uav": "态势-监视目标",
    "situation_plan": "态势-飞行计划",
    "situation_alarm": "态势-实时告警",
    "kafka_collision_alarm": "Kafka 冲突告警",
    "ws_captured_data": "WebSocket 前端数据",
}


class LogStreamer:
    """实时日志采集与推送。"""

    def __init__(self, push_callback: Optional[Callable] = None):
        self._callback = push_callback  # push_callback(log_type, message)
        self._running = False
        self._buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._max_buffer = 1000
        self._redis_thread: Optional[threading.Thread] = None
        self._counts: Dict[str, int] = {k: 0 for k in LOG_TYPES}
        # MySQL 持久化（延迟初始化）
        self._mysql_enabled = _HAS_MYSQL
        self._mysql_client: Any = None
        self._cleanup_counter = 0
        self._mysql_fail_count = 0
        self._mysql_last_fail_time = 0.0
        _MYSQL_COOLDOWN_SEC = 60.0

    def start(self) -> None:
        """启动日志采集。"""
        if self._running:
            return
        self._running = True
        print("[LogStreamer] 日志采集已启动")
        # 启动后台数据源监控线程
        self._start_redis_monitor()
        self._start_db_monitor()

    def stop(self) -> None:
        """停止日志采集。"""
        self._running = False
        print("[LogStreamer] 日志采集已停止")

    # ── Redis 监控 ──────────────────────────────────────────────────

    _redis_client = None
    _last_route_count = 0
    _last_airspace_count = 0

    def set_redis_client(self, client) -> None:
        """设置 Redis 客户端用于监控。"""
        self._redis_client = client

    def _start_redis_monitor(self) -> None:
        """后台轮询 Redis 数据变更。"""
        def _poll():
            self.push("sim_status", "Redis/Kafka 监控线程已启动")
            while self._running:
                try:
                    if self._redis_client:
                        try:
                            routes = self._redis_client.hgetall("BIZ_DATA:UAV_ROUTE")
                            airspaces = self._redis_client.hgetall("BIZ_DATA:AIRSPACE")
                            route_count = len(routes) if routes else 0
                            air_count = len(airspaces) if airspaces else 0
                            if route_count != self._last_route_count:
                                self.push("redis_route",
                                    f"飞行计划数量变更: {self._last_route_count} → {route_count} (BIZ_DATA:UAV_ROUTE)")
                                self._last_route_count = route_count
                            if air_count != self._last_airspace_count:
                                self.push("redis_airspace",
                                    f"空域数据数量变更: {self._last_airspace_count} → {air_count} (BIZ_DATA:AIRSPACE)")
                                self._last_airspace_count = air_count
                        except Exception:
                            pass
                except Exception as e:
                    self.push("sim_status", f"Redis 监控异常: {e}")
                time.sleep(10)  # 每 10 秒检查一次
        threading.Thread(target=_poll, daemon=True, name="redis-monitor").start()

    # ── 数据库任务日志监控 ──────────────────────────────────────────

    _last_log_id = 0

    def _start_db_monitor(self) -> None:
        """后台轮询数据库 sim_task_logs 表。"""
        # 确保数据库表已创建
        try:
            init_tables()
        except Exception as e:
            print(f"[LogStreamer] 数据库表初始化失败: {e}")
            return
        def _poll():
            time.sleep(5)  # 初始延迟
            while self._running:
                try:
                    rows = query(LOG_TABLE, where=f"id > {self._last_log_id}", order_by="id ASC")
                    for row in rows:
                        self.push("db_run_data",
                            f"[{row.get('task_type','')}] {row.get('message','')} [{row.get('status','')}]")
                        if row.get("id", 0) > self._last_log_id:
                            self._last_log_id = row["id"]
                except Exception as e:
                    print(f"[LogStreamer] DB 监控查询异常: {e}")
                time.sleep(5)
        threading.Thread(target=_poll, daemon=True, name="db-monitor").start()

    # ── Kafka 遥测计数 ──────────────────────────────────────────────

    def report_kafka_telemetry(self, count: int, topic: str = "uav_runtime_data") -> None:
        """报告 Kafka 消息发送计数（由 SimulationManager 回调）。"""
        if count > 0:
            self.push("kafka_telemetry", f"发送 {count} 条遥测到 {topic}")

    def report_kafka_trace(self, count: int) -> None:
        """报告 Kafka trace 消费计数。"""
        if count > 0:
            self.push("kafka_trace", f"收到 {count} 条轨迹预测 (uav_runtime_trace)")

    # ── MySQL 持久化 ───────────────────────────────────────────────

    def _get_mysql_client(self):
        """延迟初始化 MySQL 连接（含保活检查 + 自动重连 + 冷却期，失败则禁用后续写入）。"""
        if not self._mysql_enabled:
            # 冷却期内跳过重试
            if self._mysql_last_fail_time > 0 and time.time() - self._mysql_last_fail_time < self._MYSQL_COOLDOWN_SEC:
                return None
            # 冷却期过后允许重试一次
            if self._mysql_last_fail_time > 0:
                self._mysql_enabled = True
                self._mysql_fail_count = 0
            else:
                return None
        if self._mysql_client is None:
            try:
                self._mysql_client = _create_mysql_client()
                if self._mysql_client is None:
                    # MySQL 未配置，跳过持久化
                    self._mysql_enabled = False
                    self._mysql_last_fail_time = time.time()
                    return None
                if self._mysql_client.connect():
                    # 验证连接：执行 SELECT 1 确保连接真正可用
                    try:
                        self._mysql_client.cursor.execute("SELECT 1")
                        self._mysql_client.cursor.fetchone()
                    except Exception:
                        print("[LogStreamer] MySQL 连接验证失败 (SELECT 1)")
                        try:
                            self._mysql_client.close()
                        except Exception:
                            pass
                        self._mysql_client = None
                        self._mysql_enabled = False
                        self._mysql_last_fail_time = time.time()
                        return None
                    self._ensure_mysql_table()
                else:
                    print("[LogStreamer] MySQL 连接失败，日志将仅保存在内存中")
                    self._mysql_client = None
                    self._mysql_enabled = False
                    self._mysql_last_fail_time = time.time()
            except Exception as e:
                print(f"[LogStreamer] MySQL 初始化异常: {e}")
                self._mysql_enabled = False
                self._mysql_last_fail_time = time.time()
        # ── 连接保活检查 ──
        if self._mysql_client is not None:
            try:
                self._mysql_client.conn.ping(reconnect=True)
            except Exception:
                print("[LogStreamer] MySQL 连接已断开，尝试重连...")
                try:
                    if self._mysql_client.connect():
                        # 验证新连接
                        try:
                            self._mysql_client.cursor.execute("SELECT 1")
                            self._mysql_client.cursor.fetchone()
                        except Exception:
                            print("[LogStreamer] MySQL 重连后验证失败")
                            self._mysql_client.close()
                            self._mysql_client = None
                            self._mysql_enabled = False
                            self._mysql_last_fail_time = time.time()
                            return None
                        print("[LogStreamer] MySQL 重连成功")
                    else:
                        print("[LogStreamer] MySQL 重连失败，禁用持久化")
                        self._mysql_client = None
                        self._mysql_enabled = False
                        self._mysql_last_fail_time = time.time()
                except Exception as e:
                    print(f"[LogStreamer] MySQL 重连异常: {e}")
                    self._mysql_client = None
                    self._mysql_enabled = False
                    self._mysql_last_fail_time = time.time()
        return self._mysql_client

    def _ensure_mysql_table(self):
        """创建 sim_system_logs 表（如不存在）。"""
        ddl = """
        CREATE TABLE IF NOT EXISTS `sim_system_logs` (
            `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
            `time` VARCHAR(20) NOT NULL COMMENT '日志时间 HH:mm:ss',
            `type` VARCHAR(32) NOT NULL COMMENT '日志类型 key',
            `type_name` VARCHAR(64) DEFAULT '' COMMENT '日志类型中文名',
            `message` TEXT COMMENT '日志消息',
            `detail` TEXT COMMENT '结构化详情 JSON',
            `task_id` VARCHAR(64) DEFAULT '' COMMENT '关联任务 ID',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统日志持久化表'
        """
        try:
            self._mysql_client.execute(ddl)
            print("[LogStreamer] 系统日志表已就绪: sim_system_logs")
        except Exception as e:
            print(f"[LogStreamer] 建表失败: {e}")
            self._mysql_enabled = False

    def export_logs_from_db(
        self,
        start_date: str = "",
        end_date: str = "",
        types: Optional[List[str]] = None,
        keyword: str = "",
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """从 MySQL 导出日志（支持日期范围过滤）。"""
        client = self._get_mysql_client()
        if not client:
            return []

        where_parts = []
        params = []

        if start_date:
            where_parts.append("created_at >= %s")
            params.append(start_date)
        if end_date:
            where_parts.append("created_at <= %s")
            params.append(end_date + " 23:59:59")
        if types:
            placeholders = ", ".join(["%s"] * len(types))
            where_parts.append(f"type IN ({placeholders})")
            params.extend(types)
        if keyword:
            where_parts.append("message LIKE %s")
            params.append(f"%{keyword}%")

        where_sql = " AND ".join(where_parts) if where_parts else "1=1"
        sql = f"SELECT * FROM `sim_system_logs` WHERE {where_sql} ORDER BY id ASC LIMIT {limit}"

        try:
            client.cursor.execute(sql, tuple(params))
            rows = client.cursor.fetchall()
            result = []
            for row in rows:
                entry = {
                    "time": row.get("time", ""),
                    "type": row.get("type", ""),
                    "type_name": row.get("type_name", ""),
                    "message": row.get("message", ""),
                }
                detail_raw = row.get("detail", "")
                if detail_raw:
                    try:
                        entry["detail"] = json.loads(detail_raw)
                    except json.JSONDecodeError:
                        pass
                result.append(entry)
            return result
        except Exception as e:
            print(f"[LogStreamer] MySQL 导出失败: {e}")
            return []

    def _cleanup_old_logs(self, days: int = 7):
        """清理超过指定天数的旧日志。"""
        client = self._get_mysql_client()
        if not client:
            return
        try:
            sql = f"DELETE FROM `sim_system_logs` WHERE created_at < NOW() - INTERVAL {days} DAY"
            client.execute(sql)
            print(f"[LogStreamer] 已清理 {days} 天前的日志")
        except Exception as e:
            print(f"[LogStreamer] 日志清理失败: {e}")

    # ── 推送 ─────────────────────────────────────────────────────

    def push(self, log_type: str, message: str, detail: Optional[Dict] = None) -> None:
        """推送一条日志。type 必须是 LOG_TYPES 中的 key。

        Args:
            log_type: 日志类型（LOG_TYPES 的 key）
            message: 摘要文本
            detail: 可选的结构化详情字典（如 UAV 列表、告警列表等）
        """
        if log_type not in LOG_TYPES:
            log_type = "sim_status"

        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": log_type,
            "type_name": LOG_TYPES.get(log_type, log_type),
            "message": message,
        }
        if detail is not None:
            entry["detail"] = detail

        with self._lock:
            self._buffer.append(entry)
            self._counts[log_type] += 1
            if len(self._buffer) > self._max_buffer:
                self._buffer = self._buffer[-self._max_buffer:]

        if self._callback:
            try:
                self._callback(entry)
            except Exception as e:
                print(f"[LogStreamer] 推送回调失败: {e}")

        # ── MySQL 持久化（异步写，忽略失败不影响主流程） ──────────
        if self._mysql_enabled:
            try:
                client = self._get_mysql_client()
                if client:
                    detail_json = json.dumps(detail, ensure_ascii=False) if detail is not None else ""
                    result = client.insert("sim_system_logs", {
                        "time": entry["time"],
                        "type": entry["type"],
                        "type_name": entry["type_name"],
                        "message": entry["message"],
                        "detail": detail_json,
                        "task_id": "",
                    })
                    if result is None:
                        # insert 返回 None = 写入失败，累计失败次数
                        self._mysql_fail_count += 1
                        self._mysql_last_fail_time = time.time()
                        if self._mysql_fail_count >= 5:
                            print("[LogStreamer] MySQL 连续写入失败超过5次，禁用持久化")
                            self._mysql_enabled = False
                    else:
                        # 写入成功，重置失败计数
                        self._mysql_fail_count = 0
                        # 每约 3600 条日志触发一次旧日志清理（约每小时）
                        self._cleanup_counter += 1
                        if self._cleanup_counter >= 3600:
                            self._cleanup_counter = 0
                            self._cleanup_old_logs()
            except Exception as e:
                # 区分 pymysql 特定错误（如连接断开）和通用异常
                if _HAS_PYMYSQL and isinstance(e, pymysql.Error):
                    print(f"[LogStreamer] MySQL pymysql 错误: {e}")
                else:
                    print(f"[LogStreamer] MySQL 写入异常: {e}")
                self._mysql_fail_count += 1
                self._mysql_last_fail_time = time.time()
                if self._mysql_fail_count >= 5:
                    print("[LogStreamer] MySQL 连续写入失败超过5次，禁用持久化")
                    self._mysql_enabled = False

    def push_sim_log(self, message: str) -> None:
        """推送仿真运行日志（兼容 _add_log）。"""
        self.push("sim_status", message)

    # ── 查询 ───────────────────────────────────────────────────────

    def get_logs(
        self,
        types: Optional[List[str]] = None,
        keyword: str = "",
        limit: int = 200,
        since: str = "",
    ) -> List[Dict[str, Any]]:
        """按条件查询历史日志。"""
        with self._lock:
            logs = list(self._buffer)

        # 包含数据库中的任务执行日志
        try:
            db_logs = query(LOG_TABLE, order_by="id DESC")
            for row in db_logs[:50]:
                logs.append({
                    "time": (row.get("started_at") or "")[-8:] or "--",
                    "type": "db_run_data",
                    "type_name": "任务日志",
                    "message": f"[{row.get('task_type','')}] {row.get('message','')} [{row.get('status','')}]",
                })
        except Exception:
            pass

        # 按时间排序（最新的在前）
        logs.sort(key=lambda x: x.get("time", ""), reverse=True)

        # 过滤
        if types:
            logs = [l for l in logs if l.get("type") in types]
        if keyword:
            kw = keyword.lower()
            logs = [l for l in logs if kw in l.get("message", "").lower()]
        if since:
            logs = [l for l in logs if l.get("time", "") >= since]

        return logs[:limit]

    def export_logs(self, types: Optional[List[str]] = None,
                    fmt: str = "json", keyword: str = "") -> Dict[str, Any]:
        """导出日志为指定格式。"""
        logs = self.get_logs(types=types, keyword=keyword, limit=5000)

        if fmt == "json":
            content = json.dumps(logs, ensure_ascii=False, indent=2)
            return {"format": "json", "content": content, "count": len(logs)}
        elif fmt == "csv":
            lines = ["time,type,type_name,message,detail"]
            for l in logs:
                msg = l.get("message", "").replace('"', '""')
                type_name = l.get("type_name", "").replace('"', '""')
                detail_str = ""
                if l.get("detail"):
                    detail_str = json.dumps(l["detail"], ensure_ascii=False).replace('"', '""')
                lines.append(f'{l.get("time","")},{l.get("type","")},"{type_name}","{msg}","{detail_str}"')
            return {"format": "csv", "content": "\n".join(lines), "count": len(logs)}
        elif fmt == "txt":
            lines = []
            for l in logs:
                lines.append(f'[{l.get("time","")}] [{l.get("type_name","")}] {l.get("message","")}')
            return {"format": "txt", "content": "\n".join(lines), "count": len(logs)}
        else:
            return {"format": fmt, "content": "", "count": 0, "error": f"不支持的格式: {fmt}"}

    def get_counts(self) -> Dict[str, int]:
        """获取各类型日志计数。"""
        with self._lock:
            return dict(self._counts)

    def clear(self) -> None:
        """清空缓冲区。"""
        with self._lock:
            self._buffer.clear()
            for k in self._counts:
                self._counts[k] = 0


# ── 全局单例 ────────────────────────────────────────────────────────

_log_streamer: Optional[LogStreamer] = None


def get_streamer() -> LogStreamer:
    """获取日志采集器单例。"""
    global _log_streamer
    if _log_streamer is None:
        _log_streamer = LogStreamer()
        _log_streamer.start()
    return _log_streamer
