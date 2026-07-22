# -*- coding: utf-8 -*-
"""
结构化日志配置模块

提供 AI 友好的 JSON 结构化日志输出，同时保留控制台可读格式。
新模块使用 `logger = get_logger(__name__)`；旧 print() 暂不替换。

用法:
    from log_setup import get_logger, setup_logging
    setup_logging(log_level="INFO")
    logger = get_logger(__name__)
    logger.info("仿真已启动，目标架数=%d", target_drones)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional


# ── JSON 格式化器 ───────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """AI 友好的 JSON 结构化日志格式。

    输出字段: ts(ISO 8601+Z), level, module, line, func, msg, thread, exc
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "line": record.lineno,
            "func": record.funcName,
            "msg": record.getMessage(),
            "thread": record.threadName,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exc"] = str(record.exc_info[1])

        return json.dumps(log_entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """控制台可读格式：时间 级别 模块:行号 - 消息"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-5s %(module)s:%(lineno)d - %(message)s",
            datefmt="%H:%M:%S",
        )


# ── 日志器缓存 ──────────────────────────────────────────────────────

_loggers: dict[str, logging.Logger] = {}
_setup_done: bool = False


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    json_output: bool = True,
) -> logging.Logger:
    """配置全局日志系统（幂等，多次调用只有首次生效）。

    Args:
        log_level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 可选，JSON 日志输出文件路径
        json_output: 是否启用 JSON 格式输出到 stderr

    Returns:
        根 logger 实例
    """
    global _setup_done
    if _setup_done:
        return logging.getLogger()

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 根据 UTM_LOG_FORMAT 环境变量选择日志格式:
    #   "json"   = 仅 JSON（适合生产环境日志采集）
    #   "simple" = 仅可读文本（适合开发）
    #   未设置   = 双输出（兼容旧行为）
    _log_fmt = os.environ.get("UTM_LOG_FORMAT", "").lower()

    if not root.handlers:
        if _log_fmt in ("", "simple", "console"):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(ConsoleFormatter())
            console_handler.setLevel(logging.DEBUG)
            root.addHandler(console_handler)

        if _log_fmt in ("", "json"):
            json_handler = logging.StreamHandler(sys.stderr)
            json_handler.setFormatter(JsonFormatter())
            json_handler.setLevel(logging.INFO)
            root.addHandler(json_handler)

    # 文件输出（可选）
    if log_file:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(JsonFormatter())
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)

    _setup_done = True

    # 降低第三方库日志噪音
    for noisy in ("kafka", "urllib3", "engineio", "socketio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # HTTP 请求日志：默认 WARNING 抑制刷屏，设 UTM_HTTP_LOG_LEVEL=INFO 可恢复
    _http_log_level = os.environ.get("UTM_HTTP_LOG_LEVEL", "WARNING")
    logging.getLogger("werkzeug").setLevel(getattr(logging, _http_log_level.upper(), logging.WARNING))
    logging.getLogger("_internal").setLevel(getattr(logging, _http_log_level.upper(), logging.WARNING))

    return root


def get_logger(name: str) -> logging.Logger:
    """获取指定模块的 logger 实例（自动确保日志系统已初始化）。

    Args:
        name: 通常传入 __name__

    Returns:
        logging.Logger 实例
    """
    if not _setup_done:
        setup_logging()

    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)

    return _loggers[name]


# ── 便捷函数 ────────────────────────────────────────────────────────

def reset_logging() -> None:
    """重置日志配置（主要用于测试）。"""
    global _setup_done, _loggers
    _setup_done = False
    _loggers.clear()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)


# ── 限频打印工具（抑制重复刷屏日志）────────────────────────────────

# 环境变量 UTM_VERBOSE=1 可恢复所有详细日志
_VERBOSE = os.environ.get("UTM_VERBOSE", "").lower() in ("1", "true", "yes")


class RateLimitedPrinter:
    """限频打印器：相同前缀的消息在冷却时间内最多打印一次。

    用法:
        _rlp = RateLimitedPrinter("mysql_db_manager", cooldown=60)
        _rlp.print("MySQL 不可用，query 返回空")  # 60s 内只打印一次
    """

    def __init__(self, prefix: str, cooldown: float = 60.0) -> None:
        self._prefix = prefix
        self._cooldown = cooldown
        self._last_printed: dict[str, float] = {}
        self._last_time: float = 0.0

    def print(self, message: str, tag: str = "") -> None:
        """限频打印消息。相同 tag 在冷却时间内只打印一次。"""
        import time as _time
        now = _time.time()
        key = tag or message
        last = self._last_printed.get(key, 0.0)
        if now - last >= self._cooldown:
            self._last_printed[key] = now
            # 如果冷却期内被抑制过，打印抑制次数
            print(f"[{self._prefix}] {message}", flush=True)


def debug_print(prefix: str, message: str) -> None:
    """DEBUG 级别打印：仅在 UTM_VERBOSE=1 时输出。

    用法:
        from log_setup import debug_print
        debug_print("DmDbClient", f"查询表: {table}, 返回 {len(rows)} 条记录")
    """
    if _VERBOSE:
        print(f"[{prefix}] {message}", flush=True)


def info_print(prefix: str, message: str) -> None:
    """INFO 级别打印：常规信息（始终输出）。"""
    print(f"[{prefix}] {message}", flush=True)


def warn_print(prefix: str, message: str) -> None:
    """WARNING 级别打印（始终输出）。"""
    print(f"[{prefix}] ⚠ {message}", flush=True)


def error_print(prefix: str, message: str) -> None:
    """ERROR 级别打印（始终输出）。"""
    print(f"[{prefix}] ❌ {message}", flush=True)
