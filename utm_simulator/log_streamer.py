# -*- coding: utf-8 -*-
"""
实时日志流 — 统一采集 Redis/Kafka/DB/仿真状态日志

通过 WebSocket 实时推送到前端，支持按类型过滤、关键字搜索、导出。
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from db_manager import query, query_all, _now

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

    def start(self) -> None:
        """启动日志采集。"""
        if self._running:
            return
        self._running = True
        print("[LogStreamer] 日志采集已启动")

    def stop(self) -> None:
        """停止日志采集。"""
        self._running = False
        print("[LogStreamer] 日志采集已停止")

    def push(self, log_type: str, message: str) -> None:
        """推送一条日志。type 必须是 LOG_TYPES 中的 key。"""
        if log_type not in LOG_TYPES:
            log_type = "sim_status"

        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "type": log_type,
            "type_name": LOG_TYPES.get(log_type, log_type),
            "message": message,
        }

        with self._lock:
            self._buffer.append(entry)
            self._counts[log_type] += 1
            if len(self._buffer) > self._max_buffer:
                self._buffer = self._buffer[-self._max_buffer:]

        if self._callback:
            try:
                self._callback(entry)
            except Exception:
                pass

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
            lines = ["time,type,message"]
            for l in logs:
                msg = l.get("message", "").replace('"', '""')
                lines.append(f'{l.get("time","")},{l.get("type","")},"{msg}"')
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
