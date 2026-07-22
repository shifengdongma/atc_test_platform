# -*- coding: utf-8 -*-
"""
环境配置管理器 — 管理 Redis/Kafka 连接地址

功能：
- 保存多组连接配置（名称 + Redis IP/端口/密码 + Kafka 地址）
- 激活切换：将选中配置写入 config.json 并更新运行时配置
- 从 env.py 导入现有连接信息
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from mysql_db_manager import (
    query_all, query_one, insert, update, delete, init_tables, _now,
)

TABLE = "sim_env_config"

# config.json 路径
_CONFIG_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common", "config.json")


def _ensure_tables() -> None:
    """确保表存在（惰性初始化）。"""
    init_tables()


def list_envs() -> List[Dict[str, Any]]:
    """列出所有环境配置。"""
    _ensure_tables()
    return query_all(TABLE)


def get_env(env_id: int) -> Optional[Dict[str, Any]]:
    """获取单个环境配置。"""
    _ensure_tables()
    return query_one(TABLE, env_id)


def save_env(data: Dict[str, Any]) -> int:
    """新增或更新环境配置。如果有 id 且存在则更新，否则新增。"""
    _ensure_tables()
    env_id = data.pop("id", None)
    if env_id:
        existing = query_one(TABLE, int(env_id))
        if existing:
            update(TABLE, int(env_id), data)
            return int(env_id)
    # 如果 name 已存在，更新而不是新增
    name = data.get("name", "")
    if name:
        existing = query_one(TABLE, name) if False else None  # keep simple: always insert
    return insert(TABLE, data)


def delete_env(env_id: int) -> bool:
    """删除环境配置。"""
    _ensure_tables()
    return delete(TABLE, int(env_id))


def set_default(env_id: int) -> bool:
    """设为默认环境（MySQL/SQLite 自适应）。"""
    _ensure_tables()
    try:
        # 先清零所有环境，再将目标设为 1
        all_envs = query_all(TABLE)
        for env in all_envs:
            if env.get("is_default"):
                update(TABLE, env["id"], {"is_default": 0})
        update(TABLE, int(env_id), {"is_default": 1})
        return True
    except Exception as e:
        print(f"[env_manager] set_default 失败: {e}")
        return False


def activate_env(env_id: int) -> Dict[str, Any]:
    """激活指定环境：将配置写入 config.json 并返回配置数据。
    返回 {success, config, message}。
    """
    _ensure_tables()
    env = query_one(TABLE, int(env_id))
    if not env:
        return {"success": False, "message": f"环境配置 {env_id} 不存在"}

    # 标记为默认
    set_default(int(env_id))

    # 写入 config.json（包含全部配置字段）
    config_data = {
        "redis_ip": env.get("redis_ip", "127.0.0.1"),
        "redis_port": str(env.get("redis_port", "6379")),
        "redis_password": env.get("redis_pwd", ""),
        "kafka_url": env.get("kafka_url", "127.0.0.1:9092"),
        "kafka_url2": env.get("kafka_url2", ""),
        "dm_host": env.get("dm_host", ""),
        "dm_port": env.get("dm_port", 5236),
        "dm_user": env.get("dm_user", "SYSDBA"),
        "dm_password": env.get("dm_password", ""),
        "dm_schema": env.get("dm_schema", ""),
        "mysql_host": env.get("mysql_host", ""),
        "mysql_port": env.get("mysql_port", 3306),
        "mysql_user": env.get("mysql_user", ""),
        "mysql_password": env.get("mysql_password", ""),
        "mysql_database": env.get("mysql_database", ""),
        "atc_cluster_api": env.get("atc_cluster_api", ""),
        "atc_vip": env.get("atc_vip", ""),
        "atc_node_a": env.get("atc_node_a", ""),
        "atc_node_b": env.get("atc_node_b", ""),
        "es_hosts": env.get("es_hosts", ""),
    }
    try:
        with open(_CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"success": False, "message": f"写入 config.json 失败: {e}"}

    # 同时更新 env.py（如果存在且内容匹配模板）
    _update_env_py(config_data)

    return {"success": True, "message": f"已切换到环境: {env.get('name','')}", "config": config_data}


def get_current_config() -> Dict[str, Any]:
    """获取当前激活的配置（从 config.json 读取）。"""
    config = {
        "redis_ip": "127.0.0.1",
        "redis_port": "6379",
        "redis_password": "",
        "kafka_url": "127.0.0.1:9092",
        "kafka_url2": "",
        "dm_host": "", "dm_port": 5236, "dm_user": "SYSDBA",
        "dm_password": "", "dm_schema": "",
        "mysql_host": "", "mysql_port": 3306, "mysql_user": "",
        "mysql_password": "", "mysql_database": "",
        "atc_cluster_api": "", "atc_vip": "", "atc_node_a": "", "atc_node_b": "",
        "es_hosts": "",
    }
    try:
        if os.path.exists(_CONFIG_JSON):
            with open(_CONFIG_JSON, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config.update(saved)
    except Exception:
        pass
    return config


def import_from_env_py() -> Dict[str, Any]:
    """从 env.py 文件导入当前连接配置，保存到数据库并返回。"""
    _ensure_tables()
    try:
        import env as _env
        data = {
            "name": f"env.py-{getattr(_env, 'redis_ip', 'local')}",
            "redis_ip": getattr(_env, "redis_ip", "127.0.0.1"),
            "redis_port": str(getattr(_env, "redis_port", "6379")),
            "redis_pwd": getattr(_env, "redis_password", ""),
            "kafka_url": getattr(_env, "kafka_url", "127.0.0.1:9092"),
            "kafka_url2": getattr(_env, "kafka_url2", ""),
            # 达梦数据库
            "dm_host": getattr(_env, "DB_HOST", getattr(_env, "dm_a_host", "")),
            "dm_port": getattr(_env, "DB_PORT", getattr(_env, "dm_a_port", 5236)),
            "dm_user": getattr(_env, "DB_USER", getattr(_env, "dm_a_user", "SYSDBA")),
            "dm_password": getattr(_env, "DB_PASSWORD", getattr(_env, "dm_a_password", "")),
            "dm_schema": getattr(_env, "DB_SCHEMA", getattr(_env, "dm_a_schema", "")),
            # MySQL
            "mysql_host": getattr(_env, "MYSQL_HOST", ""),
            "mysql_port": getattr(_env, "MYSQL_PORT", 3306),
            "mysql_user": getattr(_env, "MYSQL_USER", ""),
            "mysql_password": getattr(_env, "MYSQL_PASSWORD", ""),
            "mysql_database": getattr(_env, "MYSQL_DATABASE", ""),
            # ATC 集群
            "atc_cluster_api": getattr(_env, "cluster_api", ""),
            "atc_vip": getattr(_env, "atc_vip", ""),
            "atc_node_a": getattr(_env, "atc_a", ""),
            "atc_node_b": getattr(_env, "atc_b", ""),
            # ES
            "es_hosts": str(getattr(_env, "es_hosts", "")),
        }
        env_id = save_env(data)
        data["id"] = env_id
        return {"success": True, "message": f"已导入 env.py 配置: {data['name']}", "config": data}
    except ImportError:
        return {"success": False, "message": "env.py 文件不存在，无法导入"}
    except Exception as e:
        return {"success": False, "message": f"导入失败: {e}"}


def _update_env_py(config: Dict[str, Any]) -> None:
    """尝试更新 env.py 文件中的连接地址（简单正则替换，仅更新主流配置行）。"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "env.py")
    if not os.path.exists(env_path):
        return
    import re
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 字符串值字段 (key = "...")
        _str_fields = [
            ("redis_ip", "127.0.0.1"),
            ("redis_port", "6379"),
            ("redis_password", ""),
            ("kafka_url", "127.0.0.1:9092"),
            ("kafka_url2", ""),
            ("dm_a_host", ""), ("dm_a_user", "SYSDBA"), ("dm_a_password", ""), ("dm_a_schema", ""),
            ("dm_b_host", ""), ("dm_b_user", "SYSDBA"), ("dm_b_password", ""), ("dm_b_schema", ""),
            ("dm_vip", ""),
            ("DB_HOST", ""), ("DB_USER", "SYSDBA"), ("DB_PASSWORD", ""), ("DB_SCHEMA", ""),
            ("MYSQL_HOST", ""), ("MYSQL_USER", ""), ("MYSQL_PASSWORD", ""), ("MYSQL_DATABASE", ""),
            ("cluster_api", ""), ("atc_vip", ""), ("atc_a", ""), ("atc_b", ""),
            ("ACCESS_KEY_a", ""), ("ACCESS_KEY_b", ""),
            ("dops_a", ""), ("dops_b", ""),
            ("kafka_url_a", ""), ("kafka_url_b", ""),
            ("redis_ip_a", ""), ("redis_port_a", "6379"), ("redis_password_a", ""),
            ("redis_ip_b", ""), ("redis_port_b", "6379"), ("redis_password_b", ""),
        ]
        # 整数值字段 (key = 1234)
        _int_fields = [
            ("MYSQL_PORT", 3306),
            ("dm_a_port", 5236), ("dm_b_port", 5236),
            ("DB_PORT", 5236),
            ("iomp_port_a", 8801), ("iomp_port_b", 8801),
        ]
        # 列表值字段 (key = [...])
        _list_fields = [
            ("es_hosts", '["10.165.26.119:29200", "10.165.26.139:29200"]'),
        ]

        # 从数据库字段映射到 env.py 字段名
        _db_to_env = {
            "redis_password": "redis_password",
            "dm_host": "DB_HOST",
            "dm_port": "DB_PORT",
            "dm_user": "DB_USER",
            "dm_password": "DB_PASSWORD",
            "dm_schema": "DB_SCHEMA",
            "mysql_host": "MYSQL_HOST",
            "mysql_port": "MYSQL_PORT",
            "mysql_user": "MYSQL_USER",
            "mysql_password": "MYSQL_PASSWORD",
            "mysql_database": "MYSQL_DATABASE",
            "atc_cluster_api": "cluster_api",
            "atc_node_a": "atc_a",
            "atc_node_b": "atc_b",
        }

        for field, default in _str_fields:
            env_field = _db_to_env.get(field, field)
            val = config.get(field, default)
            # 同时尝试 db 列名（如 redis_password → redis_pwd）
            if field in ("redis_password",) and config.get("redis_pwd"):
                val = config.get("redis_pwd", default)
            content = re.sub(
                rf'{env_field}\s*=\s*"[^"]*"',
                f'{env_field} = "{val}"',
                content,
            )

        for field, default in _int_fields:
            env_field = _db_to_env.get(field, field)
            val = config.get(field, default)
            content = re.sub(
                rf'{env_field}\s*=\s*\d+',
                f'{env_field} = {val}',
                content,
            )

        for field, default_str in _list_fields:
            val = config.get(field, None)
            if val:
                content = re.sub(
                    rf'{field}\s*=\s*\[[^\]]*\]',
                    f'{field} = {val}',
                    content,
                )

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass  # 静默失败，config.json 是主要配置来源
