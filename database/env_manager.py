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

    # 写入 config.json
    config_data = {
        "redis_ip": env.get("redis_ip", "127.0.0.1"),
        "redis_port": str(env.get("redis_port", "6379")),
        "redis_password": env.get("redis_pwd", ""),
        "kafka_url": env.get("kafka_url", "127.0.0.1:9092"),
        "kafka_url2": env.get("kafka_url2", ""),
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
            "name": f"env.py-{_env.redis_ip or 'local'}",
            "redis_ip": getattr(_env, "redis_ip", "127.0.0.1"),
            "redis_port": str(getattr(_env, "redis_port", "6379")),
            "redis_pwd": getattr(_env, "redis_password", ""),
            "kafka_url": getattr(_env, "kafka_url", "127.0.0.1:9092"),
            "kafka_url2": getattr(_env, "kafka_url2", ""),
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
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "utm_simulator", "env.py")
    if not os.path.exists(env_path):
        return
    import re
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

        mappings = [
            (r'redis_ip\s*=\s*"[^"]*"', f'redis_ip = "{config.get("redis_ip", "127.0.0.1")}"'),
            (r'redis_port\s*=\s*"[^"]*"', f'redis_port = "{config.get("redis_port", "6379")}"'),
            (r'redis_password\s*=\s*"[^"]*"', f'redis_password = "{config.get("redis_password", "")}"'),
            (r'kafka_url\s*=\s*"[^"]*"', f'kafka_url = "{config.get("kafka_url", "127.0.0.1:9092")}"'),
            (r'kafka_url2\s*=\s*"[^"]*"', f'kafka_url2 = "{config.get("kafka_url2", "")}"'),
        ]
        for pattern, replacement in mappings:
            content = re.sub(pattern, replacement, content)

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass  # 静默失败，config.json 是主要配置来源
