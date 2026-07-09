# -*- coding: utf-8 -*-
"""
语义异常层次模块

将原来无处不在的 `except Exception` 裸捕获替换为语义化异常类型，
AI 工具和上层调用方可根据异常类型做出针对性处理。

用法:
    from exceptions import RedisConnectionError, ValidationError

    if not redis_client.is_connected():
        raise RedisConnectionError("无法连接到 Redis: %s:%d", host, port)

    is_valid, errors = validate_telemetry(data)
    if not is_valid:
        raise ValidationError("遥测数据校验失败", errors=errors)
"""

from __future__ import annotations

from typing import Any, List, Optional


# ── 异常层次 ────────────────────────────────────────────────────────

class UTMSimulationError(Exception):
    """UTM 仿真系统所有异常的基类。

    Attributes:
        message: 错误描述信息
        details: 可选的附加详情字典
    """

    def __init__(self, message: str = "", *args: Any, details: Optional[dict] = None, **kwargs: Any) -> None:
        super().__init__(message, *args, **kwargs)
        self.message = message
        self.details = details or {}


# ── 配置类异常 ──────────────────────────────────────────────────────

class ConfigError(UTMSimulationError):
    """配置相关错误（缺少必需配置项、格式错误等）。"""
    pass


# ── 连接类异常 ──────────────────────────────────────────────────────

class ConnectionError(UTMSimulationError):
    """连接相关错误基类。"""
    pass


class RedisConnectionError(ConnectionError):
    """Redis 连接失败。"""
    pass


class KafkaConnectionError(ConnectionError):
    """Kafka 连接失败。"""
    pass


class KafkaPublishError(ConnectionError):
    """Kafka 消息发送失败。"""
    pass


# ── 数据类异常 ──────────────────────────────────────────────────────

class DataError(UTMSimulationError):
    """数据处理错误基类。"""
    pass


class ValidationError(DataError):
    """数据校验失败。

    Attributes:
        errors: 校验错误信息列表
    """

    def __init__(self, message: str = "数据校验失败", errors: Optional[List[str]] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.errors = errors or []

    def __str__(self) -> str:
        base = self.message
        if self.errors:
            detail = "; ".join(self.errors[:5])
            if len(self.errors) > 5:
                detail += f" ... 及其他 {len(self.errors) - 5} 项"
            base = f"{base}: {detail}"
        return base


class SchemaError(DataError):
    """数据结构不符合预期 Schema。"""
    pass


# ── 仿真类异常 ──────────────────────────────────────────────────────

class SimulationError(UTMSimulationError):
    """仿真运行时错误基类。"""
    pass


class StateError(SimulationError):
    """仿真状态错误（如在未运行时调用停止、重复启动等）。"""
    pass


class StepError(SimulationError):
    """仿真步进失败。"""
    pass
