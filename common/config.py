# -*- coding: utf-8 -*-
"""
统一配置管理模块

优先级：环境变量 UTM_* > env.py 兼容回退 > 代码默认值
不删除 env.py，保持向后兼容；现有代码可继续 import env 使用。

用法:
    from config import load_config
    cfg = load_config()              # 自动从 env.py + 环境变量加载
    cfg = load_config("production")  # 指定环境名
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# ── 配置数据类 ──────────────────────────────────────────────────────

@dataclass
class RedisConfig:
    """Redis 连接配置。"""
    host: str = "127.0.0.1"
    port: int = 6379
    password: str = ""
    db: int = 0

    @property
    def port_int(self) -> int:
        return int(self.port)


@dataclass
class KafkaConfig:
    """Kafka 连接配置。"""
    bootstrap_servers: str = "127.0.0.1:9092"
    bootstrap_servers_mirror: Optional[str] = None
    flush_timeout_sec: float = 1.0


@dataclass
class SimulationConfig:
    """仿真参数配置。"""
    target_drones: int = 10
    sim_center_lat: float = 31.315
    sim_center_lon: float = 120.665
    sim_radius_m: float = 800.0
    cruise_speed: float = 30.0
    climb_rate: float = 15.0
    uid_start_offset: int = 0
    ids_index: int = 1


@dataclass
class AppConfig:
    """应用全局配置。"""
    env: str = "dev"
    log_level: str = "INFO"
    redis: RedisConfig = field(default_factory=RedisConfig)
    kafka: KafkaConfig = field(default_factory=KafkaConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)


# ── 加载逻辑 ────────────────────────────────────────────────────────

def _read_config_json() -> Optional[dict]:
    """尝试读取 config.json（前端保存的持久化配置）。返回字典或 None。"""
    try:
        import json as _json
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return _json.load(f)
    except Exception:
        pass
    return None


def _read_env_py() -> Optional[dict]:
    """尝试从 env.py 读取配置（兼容现有部署）。返回字典或 None。"""
    try:
        # 优先从调用方目录查找 env，也尝试当前目录
        import importlib.util
        env_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "env.py"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "utm_simulator", "env.py"),
            os.path.join(os.getcwd(), "env.py"),
        ]
        for env_path in env_paths:
            if os.path.exists(env_path):
                spec = importlib.util.spec_from_file_location("_env_loader", env_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return {
                        "redis_ip": getattr(mod, "redis_ip", None),
                        "redis_port": getattr(mod, "redis_port", "6379"),
                        "redis_password": getattr(mod, "redis_password", ""),
                        "kafka_url": getattr(mod, "kafka_url", "127.0.0.1:9092"),
                        "kafka_url2": getattr(mod, "kafka_url2", None),
                    }
    except Exception:
        pass
    return None


def _env_str(key: str, default: str = "") -> str:
    """读取 UTM_ 前缀环境变量。"""
    return os.environ.get(f"UTM_{key}", default)


def _env_int(key: str, default: int = 0) -> int:
    val = os.environ.get(f"UTM_{key}")
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _env_float(key: str, default: float = 0.0) -> float:
    val = os.environ.get(f"UTM_{key}")
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return default


def load_config(env_name: Optional[str] = None) -> AppConfig:
    """加载应用配置。

    优先级（高→低）：
    1. 函数参数 env_name（保留，未来扩展）
    2. 环境变量 UTM_* 前缀
    3. config.json（前端保存的持久化配置，仅覆盖 redis_ip/port/kafka_url）
    4. env.py 模块变量（向后兼容）
    5. 代码默认值

    Args:
        env_name: 环境名称（目前未使用，保留接口）

    Returns:
        AppConfig 实例
    """
    # 0. 先尝试读取 config.json（前端持久化的配置）
    config_json = _read_config_json()

    # 1. 从 env.py 读取现有配置作为基准
    env_py = _read_env_py() or {}
    # config.json 覆盖 env.py 的值
    if config_json:
        for k in ("redis_ip", "redis_port", "redis_password", "kafka_url", "kafka_url2"):
            if k in config_json and config_json[k]:
                env_py[k] = config_json[k]

    # 2. 构建 RedisConfig（环境变量优先，env.py 次之，默认值兜底）
    redis = RedisConfig(
        host=_env_str("REDIS_HOST", env_py.get("redis_ip", "127.0.0.1")),
        port=_env_int("REDIS_PORT", int(env_py.get("redis_port", 6379))),
        password=_env_str("REDIS_PASSWORD", env_py.get("redis_password", "")),
        db=_env_int("REDIS_DB", 0),
    )

    # 3. 构建 KafkaConfig
    kafka_url = _env_str("KAFKA_URL", env_py.get("kafka_url", "127.0.0.1:9092"))
    kafka_url2 = _env_str("KAFKA_URL2", env_py.get("kafka_url2") or "")
    kafka = KafkaConfig(
        bootstrap_servers=kafka_url,
        bootstrap_servers_mirror=kafka_url2 if kafka_url2 else None,
        flush_timeout_sec=_env_float("KAFKA_FLUSH_TIMEOUT", 1.0),
    )

    # 4. 构建 SimulationConfig
    simulation = SimulationConfig(
        target_drones=_env_int("SIM_TARGET_DRONES", 10),
        sim_center_lat=_env_float("SIM_CENTER_LAT", 31.315),
        sim_center_lon=_env_float("SIM_CENTER_LON", 120.665),
        sim_radius_m=_env_float("SIM_RADIUS_M", 800.0),
        cruise_speed=_env_float("SIM_CRUISE_SPEED", 30.0),
        climb_rate=_env_float("SIM_CLIMB_RATE", 15.0),
        uid_start_offset=_env_int("SIM_UID_OFFSET", 0),
        ids_index=_env_int("SIM_IDS_INDEX", 1),
    )

    # 5. 组装 AppConfig
    return AppConfig(
        env=_env_str("ENV", "dev"),
        log_level=_env_str("LOG_LEVEL", "INFO"),
        redis=redis,
        kafka=kafka,
        simulation=simulation,
    )


# ── 便捷函数 ────────────────────────────────────────────────────────

def get_config() -> AppConfig:
    """获取当前配置（单次加载，后续调用返回同一实例）。"""
    global _cached_config
    if _cached_config is None:
        _cached_config = load_config()
    return _cached_config


_cached_config: Optional[AppConfig] = None


def reload_config() -> AppConfig:
    """强制重新加载配置（清除缓存）。"""
    global _cached_config
    _cached_config = None
    return get_config()


# ── 项目路径常量 ────────────────────────────────────────────────────
# 统一管理项目目录路径，消除各处重复的 os.path.join(dirname, "..", "data", "mock")

from pathlib import Path as _Path

_PROJECT_ROOT = _Path(__file__).parent.parent.resolve()

DATA_DIR = str(_PROJECT_ROOT / "data")
MOCK_DIR = str(_PROJECT_ROOT / "data" / "mock")
TEMPLATES_DIR = str(_PROJECT_ROOT / "data" / "templates")
SCHEMAS_DIR = str(_PROJECT_ROOT / "data" / "schemas")
UPLOADS_DIR = str(_PROJECT_ROOT / "data" / "uploads")
DATABASE_DIR = str(_PROJECT_ROOT / "database")
UTM_SIMULATOR_DIR = str(_PROJECT_ROOT / "utm_simulator")
DOCS_DIR = str(_PROJECT_ROOT / "docs")
