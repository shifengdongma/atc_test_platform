# -*- coding: utf-8 -*-
"""
SQLite 数据库管理器 — 本地持久化存储

使用 Python 标准库 sqlite3，数据库文件: utm_simulator/data.db
管理 4 张表：sim_env_config / sim_json_files / sim_scheduled_tasks / sim_task_logs
"""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

# 数据库文件路径（与 db_manager.py 同目录）
_DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_DB_DIR, "data.db")

_lock = threading.Lock()

# ── DDL ──────────────────────────────────────────────────────────────

_TABLE_DDL = {
    "sim_env_config": """
        CREATE TABLE IF NOT EXISTS sim_env_config (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            redis_ip    TEXT DEFAULT '',
            redis_port  TEXT DEFAULT '6379',
            redis_pwd   TEXT DEFAULT '',
            kafka_url   TEXT DEFAULT '',
            kafka_url2  TEXT DEFAULT '',
            is_default  INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT '',
            updated_at  TEXT DEFAULT ''
        )
    """,
    "sim_json_files": """
        CREATE TABLE IF NOT EXISTS sim_json_files (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            category     TEXT DEFAULT 'route',
            alarm_type   TEXT DEFAULT '',
            file_path    TEXT DEFAULT '',
            simulator_id TEXT DEFAULT '',
            linked_route TEXT DEFAULT '',
            size_bytes   INTEGER DEFAULT 0,
            source       TEXT DEFAULT 'manual',
            description  TEXT DEFAULT '',
            tags         TEXT DEFAULT '',
            created_at   TEXT DEFAULT '',
            updated_at   TEXT DEFAULT ''
        )
    """,
    "sim_scheduled_tasks": """
        CREATE TABLE IF NOT EXISTS sim_scheduled_tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            cron_expr   TEXT DEFAULT '',
            sim_mode    TEXT DEFAULT 'replay',
            json_file_ids TEXT DEFAULT '',
            sim_params  TEXT DEFAULT '{}',
            enabled     INTEGER DEFAULT 1,
            last_run_at TEXT DEFAULT '',
            next_run_at TEXT DEFAULT '',
            created_at  TEXT DEFAULT ''
        )
    """,
    "sim_task_logs": """
        CREATE TABLE IF NOT EXISTS sim_task_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     INTEGER,
            task_type   TEXT DEFAULT '',
            status      TEXT DEFAULT 'running',
            message     TEXT DEFAULT '',
            started_at  TEXT DEFAULT '',
            finished_at TEXT DEFAULT ''
        )
    """,
}


def _now() -> str:
    """返回当前时间字符串。"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（自动创建目录和文件）。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── 初始化 ──────────────────────────────────────────────────────────

def init_tables() -> None:
    """创建所有表（如不存在）。"""
    with _lock:
        conn = _get_conn()
        try:
            for name, ddl in _TABLE_DDL.items():
                conn.execute(ddl)
                print(f"[DB] 表已就绪: {name}")
            conn.commit()
        finally:
            conn.close()


# ── 通用 CRUD ───────────────────────────────────────────────────────

def query_all(table: str, order_by: str = "id DESC") -> List[Dict[str, Any]]:
    """查询表中所有记录。"""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()


def query_one(table: str, record_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 查询单条记录。"""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def query(table: str, where: str = "", params: tuple = (), order_by: str = "id DESC") -> List[Dict[str, Any]]:
    """条件查询。"""
    with _lock:
        conn = _get_conn()
        try:
            sql = f"SELECT * FROM {table}"
            if where:
                sql += f" WHERE {where}"
            sql += f" ORDER BY {order_by}"
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()


def insert(table: str, data: Dict[str, Any]) -> int:
    """插入一条记录，返回新 ID。"""
    now = _now()
    data["created_at"] = data.get("created_at", now)
    data["updated_at"] = data.get("updated_at", now)
    columns = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                tuple(data.values()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def update(table: str, record_id: int, data: Dict[str, Any]) -> bool:
    """按 ID 更新一条记录。"""
    data["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [record_id]
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", values)
            conn.commit()
            return True
        finally:
            conn.close()


def delete(table: str, record_id: int) -> bool:
    """按 ID 删除一条记录。"""
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
            conn.commit()
            return True
        finally:
            conn.close()


def execute_raw(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """执行原始 SQL 查询（只读）。"""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
