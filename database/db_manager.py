# -*- coding: utf-8 -*-
"""
SQLite 数据库管理器 — 本地持久化存储

使用 Python 标准库 sqlite3，数据库文件: utm_simulator/data.db
管理 8 张表：sim_env_config / sim_json_files / sim_scenes / sim_scene_tasks / sim_scene_task_files / sim_task_logs / sim_alarm_types / sim_system_logs
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
            dm_host     TEXT DEFAULT '',
            dm_port     INTEGER DEFAULT 5236,
            dm_user     TEXT DEFAULT 'SYSDBA',
            dm_password TEXT DEFAULT '',
            dm_schema   TEXT DEFAULT '',
            mysql_host     TEXT DEFAULT '',
            mysql_port     INTEGER DEFAULT 3306,
            mysql_user     TEXT DEFAULT '',
            mysql_password TEXT DEFAULT '',
            mysql_database TEXT DEFAULT '',
            atc_cluster_api TEXT DEFAULT '',
            atc_vip      TEXT DEFAULT '',
            atc_node_a   TEXT DEFAULT '',
            atc_node_b   TEXT DEFAULT '',
            es_hosts     TEXT DEFAULT '',
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
    "sim_scenes": """
        CREATE TABLE IF NOT EXISTS sim_scenes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            env_id      INTEGER DEFAULT 0,
            scene_type  TEXT DEFAULT 'single',
            cron_expr   TEXT DEFAULT '',
            sim_mode    TEXT DEFAULT 'scene',
            enabled     INTEGER DEFAULT 1,
            last_run_at TEXT DEFAULT '',
            next_run_at TEXT DEFAULT '',
            created_at  TEXT DEFAULT '',
            updated_at  TEXT DEFAULT ''
        )
    """,
    "sim_scene_tasks": """
        CREATE TABLE IF NOT EXISTS sim_scene_tasks (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id              INTEGER NOT NULL,
            name                  TEXT NOT NULL,
            task_type             TEXT DEFAULT 'sequential',
            cycle_interval_sec    INTEGER DEFAULT 0,
            repeat_count          INTEGER DEFAULT 1,
            execution_timeout_sec INTEGER DEFAULT 300,
            sort_order            INTEGER DEFAULT 0,
            created_at            TEXT DEFAULT '',
            updated_at            TEXT DEFAULT ''
        )
    """,
    "sim_scene_task_files": """
        CREATE TABLE IF NOT EXISTS sim_scene_task_files (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id      INTEGER NOT NULL,
            file_id      INTEGER NOT NULL,
            interval_sec INTEGER DEFAULT 0,
            sort_order   INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT '',
            updated_at   TEXT DEFAULT ''
        )
    """,
    "sim_task_logs": """
        CREATE TABLE IF NOT EXISTS sim_task_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id         INTEGER DEFAULT 0,
            scene_id        INTEGER DEFAULT 0,
            scene_task_name TEXT DEFAULT '',
            task_type       TEXT DEFAULT '',
            status          TEXT DEFAULT 'running',
            message         TEXT DEFAULT '',
            started_at      TEXT DEFAULT '',
            finished_at     TEXT DEFAULT '',
            created_at      TEXT DEFAULT '',
            updated_at      TEXT DEFAULT ''
        )
    """,
    "sim_alarm_types": """
        CREATE TABLE IF NOT EXISTS sim_alarm_types (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            color       TEXT DEFAULT '#64748b',
            description TEXT DEFAULT '',
            is_builtin  INTEGER DEFAULT 0,
            sort_order  INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT '',
            updated_at  TEXT DEFAULT ''
        )
    """,
    "sim_system_logs": """
        CREATE TABLE IF NOT EXISTS sim_system_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            time       TEXT NOT NULL,
            type       TEXT NOT NULL,
            type_name  TEXT DEFAULT '',
            message    TEXT DEFAULT '',
            detail     TEXT DEFAULT '',
            task_id    TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
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
    """创建所有表（如不存在），并执行必要迁移。"""
    with _lock:
        conn = _get_conn()
        try:
            for name, ddl in _TABLE_DDL.items():
                conn.execute(ddl)
                print(f"[DB] 表已就绪: {name}")
            # 迁移：为已存在的 sim_alarm_types 表补加 updated_at 列
            _migrate_add_column(conn, "sim_alarm_types", "updated_at",
                                "TEXT DEFAULT ''")
            # 迁移：为已存在的 sim_env_config 表补加新配置列
            _migrate_add_column(conn, "sim_env_config", "dm_host", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "dm_port", "INTEGER DEFAULT 5236")
            _migrate_add_column(conn, "sim_env_config", "dm_user", "TEXT DEFAULT 'SYSDBA'")
            _migrate_add_column(conn, "sim_env_config", "dm_password", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "dm_schema", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "mysql_host", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "mysql_port", "INTEGER DEFAULT 3306")
            _migrate_add_column(conn, "sim_env_config", "mysql_user", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "mysql_password", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "mysql_database", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "atc_cluster_api", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "atc_vip", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "atc_node_a", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "atc_node_b", "TEXT DEFAULT ''")
            _migrate_add_column(conn, "sim_env_config", "es_hosts", "TEXT DEFAULT ''")
            conn.commit()
        finally:
            conn.close()


def _migrate_add_column(conn, table: str, column: str, col_def: str) -> None:
    """安全添加列（如不存在）。SQLite 不支持 IF NOT EXISTS for ALTER TABLE。"""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        print(f"[DB] 迁移: {table}.{column} 列已添加")
    except Exception:
        pass  # 列已存在，忽略


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


def query(table: str, where: str = "", params: tuple = (), order_by: str = "id DESC",
          limit: int = 0, offset: int = 0) -> List[Dict[str, Any]]:
    """条件查询（支持分页）。"""
    with _lock:
        conn = _get_conn()
        try:
            sql = f"SELECT * FROM {table}"
            if where:
                sql += f" WHERE {where}"
            sql += f" ORDER BY {order_by}"
            if limit > 0:
                sql += f" LIMIT {int(limit)}"
            if offset > 0:
                sql += f" OFFSET {int(offset)}"
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()


def query_count(table: str, where: str = "", params: tuple = ()) -> int:
    """查询符合条件的记录总数。"""
    with _lock:
        conn = _get_conn()
        try:
            sql = f"SELECT COUNT(*) as cnt FROM {table}"
            if where:
                sql += f" WHERE {where}"
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row).get("cnt", 0) if row else 0
        finally:
            conn.close()


def query_distinct(table: str, column: str) -> List[str]:
    """查询某列的 DISTINCT 值。"""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} != ''")
            return [row[column] for row in cur.fetchall()]
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
