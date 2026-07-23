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
class MysqlConfig:
    """MySQL 连接配置（本项目 utm_simulator 库，配置/JSON/日志持久化）。"""
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "utm_simulator"
    charset: str = "utf8mb4"
    use_ssl: bool = True  # 是否使用 SSL/TLS 连接（Docker 本地部署可设 UTM_MYSQL_SSL=false 关闭）
    configured: bool = False  # 是否通过环境变量或 env.py 显式配置（Docker 内未配时跳过连接）


@dataclass
class DamengConfig:
    """达梦数据库连接配置（只读，外部 ATC 系统）。"""
    host: str = "127.0.0.1"
    port: int = 5236
    user: str = "SYSDBA"
    password: str = ""
    schema: str = "ATC_DKWRJ"
    vip: str = ""

    @property
    def port_int(self) -> int:
        return int(self.port)


@dataclass
class AtcClusterConfig:
    """ATC 集群 + IOMP + DOPS + ES 配置。"""
    cluster_api: str = ""
    vip: str = ""
    node_a: str = ""
    node_b: str = ""
    iomp_a: str = ""
    iomp_b: str = ""
    access_key_a: str = ""
    access_key_b: str = ""
    dops_a: str = ""
    dops_b: str = ""
    es_hosts: str = ""


@dataclass
class AppConfig:
    """应用全局配置。"""
    env: str = "dev"
    log_level: str = "INFO"
    redis: RedisConfig = field(default_factory=RedisConfig)
    kafka: KafkaConfig = field(default_factory=KafkaConfig)
    mysql: MysqlConfig = field(default_factory=MysqlConfig)
    dameng: DamengConfig = field(default_factory=DamengConfig)
    atc_cluster: AtcClusterConfig = field(default_factory=AtcClusterConfig)
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
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "env.py"),
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
                        # MySQL
                        "mysql_host": getattr(mod, "MYSQL_HOST", None),
                        "mysql_port": getattr(mod, "MYSQL_PORT", 3306),
                        "mysql_user": getattr(mod, "MYSQL_USER", "root"),
                        "mysql_password": getattr(mod, "MYSQL_PASSWORD", ""),
                        "mysql_database": getattr(mod, "MYSQL_DATABASE", "utm_simulator"),
                        "mysql_charset": getattr(mod, "MYSQL_CHARSET", "utf8mb4"),
                        # 达梦数据库
                        "dm_vip": getattr(mod, "dm_vip", ""),
                        "dm_host": getattr(mod, "DB_HOST", getattr(mod, "dm_a_host", "")),
                        "dm_port": getattr(mod, "DB_PORT", getattr(mod, "dm_a_port", 5236)),
                        "dm_user": getattr(mod, "DB_USER", getattr(mod, "dm_a_user", "SYSDBA")),
                        "dm_password": getattr(mod, "DB_PASSWORD", getattr(mod, "dm_a_password", "")),
                        "dm_schema": getattr(mod, "DB_SCHEMA", getattr(mod, "dm_a_schema", "")),
                        "dm_a_host": getattr(mod, "dm_a_host", ""),
                        "dm_a_port": getattr(mod, "dm_a_port", 5236),
                        "dm_a_user": getattr(mod, "dm_a_user", "SYSDBA"),
                        "dm_a_password": getattr(mod, "dm_a_password", ""),
                        "dm_a_schema": getattr(mod, "dm_a_schema", ""),
                        "dm_b_host": getattr(mod, "dm_b_host", ""),
                        "dm_b_port": getattr(mod, "dm_b_port", 5236),
                        "dm_b_user": getattr(mod, "dm_b_user", "SYSDBA"),
                        "dm_b_password": getattr(mod, "dm_b_password", ""),
                        "dm_b_schema": getattr(mod, "dm_b_schema", ""),
                        # ATC 集群
                        "cluster_api": getattr(mod, "cluster_api", ""),
                        "atc_vip": getattr(mod, "atc_vip", ""),
                        "atc_a": getattr(mod, "atc_a", ""),
                        "atc_b": getattr(mod, "atc_b", ""),
                        # IOMP
                        "iomp_a": getattr(mod, "iomp_a", ""),
                        "iomp_b": getattr(mod, "iomp_b", ""),
                        "ACCESS_KEY_a": getattr(mod, "ACCESS_KEY_a", ""),
                        "ACCESS_KEY_b": getattr(mod, "ACCESS_KEY_b", ""),
                        # DOPS
                        "dops_a": getattr(mod, "dops_a", ""),
                        "dops_b": getattr(mod, "dops_b", ""),
                        # ES
                        "es_hosts": str(getattr(mod, "es_hosts", "")),
                        # Kafka A/B
                        "kafka_url_a": getattr(mod, "kafka_url_a", ""),
                        "kafka_url_b": getattr(mod, "kafka_url_b", ""),
                        # Redis A/B
                        "redis_ip_a": getattr(mod, "redis_ip_a", ""),
                        "redis_port_a": getattr(mod, "redis_port_a", "6379"),
                        "redis_password_a": getattr(mod, "redis_password_a", ""),
                        "redis_ip_b": getattr(mod, "redis_ip_b", ""),
                        "redis_port_b": getattr(mod, "redis_port_b", "6379"),
                        "redis_password_b": getattr(mod, "redis_password_b", ""),
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


def _load_mysql_config() -> MysqlConfig:
    """加载本项目 MySQL 配置。

    优先级：
    1. 环境变量 UTM_MYSQL_*
    2. 根目录 env.py（本项目专用 MySQL）
    4. 默认值（configured=False，调用方应跳过 MySQL 连接）

    返回值中 configured 字段指示 MySQL 是否被显式配置：
    - True:  通过环境变量或 env.py 提供了 MySQL host
    - False: 所有配置源均未提供，使用默认值，调用方应优雅降级
    """
    host = "127.0.0.1"
    port = 3306
    user = "root"
    password = ""
    database = "utm_simulator"
    charset = "utf8mb4"
    configured = False  # 是否显式配置
    source = "默认值（MySQL 未配置，将跳过连接）"  # 配置来源追踪

    # 尝试从根目录 env.py 导入
    try:
        import importlib.util
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_paths = [
            os.path.join(_root, "env.py"),
        ]
        for env_path in env_paths:
            if not os.path.exists(env_path):
                print(f"[config] _load_mysql_config: env.py 不存在，跳过: {env_path}")
                continue
            spec = importlib.util.spec_from_file_location("_mysql_env_loader", env_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                env_host = getattr(mod, "MYSQL_HOST", None)
                if env_host:  # env.py 中有 MYSQL_HOST 才认为已配置
                    host = env_host
                    configured = True
                    source = f"env.py ({env_path})"
                    print(f"[config] _load_mysql_config: 从 env.py 加载 MySQL 配置 host={host}, path={env_path}")
                else:
                    print(f"[config] _load_mysql_config: env.py 中未找到 MYSQL_HOST, path={env_path}")
                port = getattr(mod, "MYSQL_PORT", port)
                user = getattr(mod, "MYSQL_USER", user)
                password = getattr(mod, "MYSQL_PASSWORD", password)
                database = getattr(mod, "MYSQL_DATABASE", database)
                charset = getattr(mod, "MYSQL_CHARSET", charset)
                break
    except Exception as e:
        print(f"[config] _load_mysql_config: 读取 env.py 异常: {e}")

    # 环境变量覆盖（最高优先级）
    env_overrides = []
    if os.environ.get("UTM_MYSQL_HOST"):
        old_host = host
        host = os.environ["UTM_MYSQL_HOST"]
        configured = True
        source = "环境变量 UTM_MYSQL_HOST"
        env_overrides.append(f"host: {old_host} -> {host}")
    if os.environ.get("UTM_MYSQL_PORT"):
        port = int(os.environ["UTM_MYSQL_PORT"])
        env_overrides.append(f"port={port}")
    if os.environ.get("UTM_MYSQL_USER"):
        user = os.environ["UTM_MYSQL_USER"]
        env_overrides.append(f"user={user}")
    if os.environ.get("UTM_MYSQL_PASSWORD"):
        password = os.environ["UTM_MYSQL_PASSWORD"]
        env_overrides.append("password=***")
    if os.environ.get("UTM_MYSQL_DB"):
        database = os.environ["UTM_MYSQL_DB"]
        env_overrides.append(f"database={database}")
    if os.environ.get("UTM_MYSQL_CHARSET"):
        charset = os.environ["UTM_MYSQL_CHARSET"]
        env_overrides.append(f"charset={charset}")

    # SSL 配置：可通过 UTM_MYSQL_SSL=false/0/no 关闭 TLS（Docker 本地部署加速连接）
    use_ssl = True
    if os.environ.get("UTM_MYSQL_SSL") is not None:
        use_ssl = os.environ["UTM_MYSQL_SSL"].lower() in ("1", "true", "yes")
        env_overrides.append(f"use_ssl={use_ssl}")
    if env_overrides:
        print(f"[config] _load_mysql_config: 环境变量覆盖 — {', '.join(env_overrides)}")

    # ── 最终配置摘要 ──────────────────────────────────────────────
    print(f"[config] _load_mysql_config: 最终 — host={host}, port={port}, "
          f"user={user}, database={database}, configured={configured}")
    print(f"[config] _load_mysql_config: 配置来源 — {source}")

    return MysqlConfig(
        host=host, port=port, user=user,
        password=password, database=database, charset=charset,
        use_ssl=use_ssl,
        configured=configured,
    )


def load_mysql_config() -> MysqlConfig:
    """获取本项目 MySQL 配置（带缓存）。

    供数据库模块独立调用，无需加载完整 AppConfig。

    Returns:
        MysqlConfig 实例
    """
    global _cached_mysql_config
    if _cached_mysql_config is None:
        _cached_mysql_config = _load_mysql_config()
    return _cached_mysql_config


_cached_mysql_config: Optional[MysqlConfig] = None


def clear_mysql_config_cache() -> None:
    """清除 MySQL 配置缓存。

    环境切换时调用，强制 load_mysql_config() 下次重新读取 env.py，
    确保新环境的 MySQL 地址/库名生效。
    """
    global _cached_mysql_config
    if _cached_mysql_config is not None:
        print("[config] MySQL 配置缓存已清除")
    _cached_mysql_config = None


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

    # 5. 构建 MysqlConfig（从根目录 env.py 读取）
    mysql = _load_mysql_config()

    # 6. 构建 DamengConfig
    dameng = DamengConfig(
        host=env_py.get("dm_host", "127.0.0.1"),
        port=int(env_py.get("dm_port", 5236)),
        user=env_py.get("dm_user", "SYSDBA"),
        password=env_py.get("dm_password", ""),
        schema=env_py.get("dm_schema", "ATC_DKWRJ"),
        vip=env_py.get("dm_vip", ""),
    )

    # 7. 构建 AtcClusterConfig
    atc_cluster = AtcClusterConfig(
        cluster_api=env_py.get("cluster_api", ""),
        vip=env_py.get("atc_vip", ""),
        node_a=env_py.get("atc_a", ""),
        node_b=env_py.get("atc_b", ""),
        iomp_a=env_py.get("iomp_a", ""),
        iomp_b=env_py.get("iomp_b", ""),
        access_key_a=env_py.get("ACCESS_KEY_a", ""),
        access_key_b=env_py.get("ACCESS_KEY_b", ""),
        dops_a=env_py.get("dops_a", ""),
        dops_b=env_py.get("dops_b", ""),
        es_hosts=env_py.get("es_hosts", ""),
    )

    # 8. 组装 AppConfig
    return AppConfig(
        env=_env_str("ENV", "dev"),
        log_level=_env_str("LOG_LEVEL", "INFO"),
        redis=redis,
        kafka=kafka,
        mysql=mysql,
        dameng=dameng,
        atc_cluster=atc_cluster,
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

DOCS_DIR = str(_PROJECT_ROOT / "docs")
