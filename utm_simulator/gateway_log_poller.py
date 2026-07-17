# -*- coding: utf-8 -*-
"""
TCP 网关日志轮询客户端

定期从 la-atc-beidou-grid-backend 的 /api/tcp/logs 拉取通信日志，
注入到 LogStreamer，使仿真运行日志中能看到真实的 TCP 代理通信记录。

用法:
    from gateway_log_poller import GatewayLogPoller
    poller = GatewayLogPoller(streamer=...)
    poller.start()
    ...
    poller.stop()
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import requests


# 网关日志 API 地址（来自 docs/tcp连接信息.md）
GATEWAY_LOGS_URL = "https://dkkgsit-test.testdolphin.com/la-atc-beidou-grid-backend/api/tcp/logs"

# 轮询间隔（秒）
DEFAULT_POLL_INTERVAL = 5.0


class GatewayLogPoller:
    """TCP 网关通信日志轮询器。

    后台线程定期调用网关日志 API，将新增日志条目推送到 LogStreamer，
    使前端"系统日志"页能看到真实的代理通信记录。
    """

    def __init__(self, streamer=None, interval: float = DEFAULT_POLL_INTERVAL):
        """初始化轮询器。

        Args:
            streamer: LogStreamer 实例（通过 _get_streamer() 获取）
            interval: 轮询间隔（秒），默认 5s
        """
        self._streamer = streamer
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_fetch_time: float = 0.0  # 上次拉取的时间戳（用于增量）
        self._last_entry_count = 0  # 上次拉取的条目数

    def start(self) -> None:
        """启动后台轮询线程。"""
        if self._running:
            return
        self._running = True
        self._last_fetch_time = time.time()
        self._last_entry_count = 0
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gw-log-poller")
        self._thread.start()
        if self._streamer:
            self._streamer.push("tcp_gateway", "TCP 网关日志轮询已启动",
                                {"url": GATEWAY_LOGS_URL, "interval_sec": self._interval})

    def stop(self) -> None:
        """停止后台轮询线程。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        if self._streamer:
            self._streamer.push("tcp_gateway", "TCP 网关日志轮询已停止")

    def _loop(self) -> None:
        """后台循环：按间隔拉取网关日志。"""
        while self._running:
            try:
                self._fetch_and_push()
            except Exception as e:
                if self._streamer:
                    self._streamer.push("tcp_gateway",
                                        f"TCP 网关日志拉取异常: {e}")
            time.sleep(self._interval)

    def _fetch_and_push(self) -> None:
        """拉取网关日志并推送新增条目到 LogStreamer。"""
        try:
            resp = requests.get(GATEWAY_LOGS_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            # 网络错误不频繁刷屏，仅在首次或状态变化时推送
            pass
            return
        except ValueError:
            return  # JSON 解析失败，跳过

        # 解析日志条目（支持多种返回格式）
        entries = self._extract_entries(data)
        if not entries:
            return

        total = len(entries)
        new_count = total - self._last_entry_count

        if new_count > 0:
            # 只推送新增的条目
            new_entries = entries[self._last_entry_count:]
            for entry in new_entries:
                msg = self._format_entry(entry)
                if self._streamer:
                    self._streamer.push("tcp_gateway", msg,
                                        {"raw": entry})
            self._last_entry_count = total

    def _extract_entries(self, data) -> list:
        """从 API 返回中提取日志条目列表。

        兼容多种返回格式：
        - 直接数组: [...]
        - {data: {logs: [...]}}
        - {logs: [...]}
        - {data: [...]}
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # 尝试常见嵌套路径
            for key in ("logs", "data", "records", "entries"):
                val = data.get(key)
                if isinstance(val, list):
                    return val
            # {data: {logs: [...]}} 嵌套
            inner = data.get("data")
            if isinstance(inner, dict):
                for key in ("logs", "records", "entries"):
                    val = inner.get(key)
                    if isinstance(val, list):
                        return val
                # data 本身可能是列表
                val = inner.get("list")
                if isinstance(val, list):
                    return val
            elif isinstance(inner, list):
                return inner
        return []

    def _format_entry(self, entry) -> str:
        """将单条日志格式化为可读消息。"""
        if isinstance(entry, str):
            return entry[:200]  # 截断过长字符
        if isinstance(entry, dict):
            # 提取关键字段
            time_str = entry.get("time", entry.get("timestamp", ""))
            msg = entry.get("message", entry.get("msg", ""))
            level = entry.get("level", entry.get("type", ""))
            client = entry.get("client", entry.get("agent_ip", entry.get("ip", "")))
            parts = []
            if time_str:
                parts.append(f"[{time_str}]")
            if level:
                parts.append(f"[{level}]")
            if client:
                parts.append(f"[{client}]")
            if msg:
                parts.append(str(msg)[:180])
            if not parts:
                # 没有可识别字段，显示整个 JSON（截断）
                import json as _json
                return _json.dumps(entry, ensure_ascii=False)[:200]
            return " ".join(parts)
        return str(entry)[:200]
