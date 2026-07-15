# -*- coding: utf-8 -*-
"""
MySQL 数据库管理器 — 测试平台主数据库 CRUD 层

提供 query / query_one / query_all / insert / update / delete / init_tables
底层通过 mysqldbclient.MysqlDbClient 操作 MySQL。

用法: from mysql_db_manager import query, insert, ...
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

# 确保 mysqldbclient 可导入
_atc_tools = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "atc_api_autotest", "api_tools",
)
if _atc_tools not in sys.path:
    sys.path.insert(0, _atc_tools)

# ── 导入 MySQL 客户端 ──────────────────────────────────────────────
from mysqldbclient import MysqlDbClient

_lock = threading.Lock()

# ── MySQL 连接单例 ─────────────────────────────────────────────────
_mysql_client: Optional[Any] = None
_mysql_available: Optional[bool] = None  # None=未检测, True=可用, False=不可用
_mysql_last_fail_time: float = 0.0
_MYSQL_RETRY_COOLDOWN: float = 60.0
_mysql_conn_target: str = ""


def _create_mysql_client(read_timeout=120, write_timeout=120):
    """使用 common/config.py 统一配置创建 MysqlDbClient 实例。"""
    global _mysql_conn_target
    try:
        _common_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common")
        if _common_path not in sys.path:
            sys.path.insert(0, _common_path)
        from config import load_mysql_config
        cfg = load_mysql_config()
        _mysql_conn_target = f"{cfg.host}:{cfg.port}/{cfg.database}"
        print(f"[mysql_db_manager] MySQL 配置: host={cfg.host}, port={cfg.port}, database={cfg.database}")
        if not cfg.configured:
            print("[mysql_db_manager] MySQL 未配置 (UTM_MYSQL_HOST 未设置)")
            _mysql_conn_target = ""
            return None
        return MysqlDbClient(
            host=cfg.host, port=cfg.port, user=cfg.user,
            password=cfg.password, database=cfg.database,
            charset=cfg.charset,
            read_timeout=read_timeout, write_timeout=write_timeout,
        )
    except Exception as e:
        print(f"[mysql_db_manager] 加载 MySQL 配置失败: {e}")
        _mysql_conn_target = ""
        return None


def _get_client():
    """获取 MySQL 客户端（延迟初始化 + 连接保活 + 自动重连）。

    线程安全；连接失败后有冷却期避免刷屏。
    """
    global _mysql_client, _mysql_available, _mysql_last_fail_time

    if _mysql_available is False:
        if time.time() - _mysql_last_fail_time < _MYSQL_RETRY_COOLDOWN:
            return None
        with _lock:
            if _mysql_available is False:
                if time.time() - _mysql_last_fail_time < _MYSQL_RETRY_COOLDOWN:
                    return None
                _mysql_available = None
                _mysql_client = None

    with _lock:
        if _mysql_available is False:
            return None

        # 首次连接
        if _mysql_client is None and _mysql_available is None:
            try:
                _mysql_client = _create_mysql_client()
                if _mysql_client is None:
                    _mysql_available = False
                    _mysql_last_fail_time = time.time()
                    return None
                if _mysql_client.connect():
                    _c = _mysql_client.conn.cursor()
                    _c.execute("SELECT 1")
                    _c.fetchone()
                    _mysql_available = True
                    _ensure_mysql_tables(client=_mysql_client)
                    print("[mysql_db_manager] MySQL 连接成功")
                else:
                    print(f"[mysql_db_manager] MySQL 连接失败 ({_mysql_conn_target})")
                    _mysql_client = None
                    _mysql_available = False
                    _mysql_last_fail_time = time.time()
            except Exception as e:
                print(f"[mysql_db_manager] MySQL 初始化异常: {e}")
                _mysql_client = None
                _mysql_available = False
                _mysql_last_fail_time = time.time()

        # 连接保活
        if _mysql_client is not None and _mysql_available is True:
            try:
                _mysql_client.conn.ping(reconnect=True)
                _c = _mysql_client.conn.cursor()
                _c.execute("SELECT 1")
                _c.fetchone()
            except Exception as e:
                print(f"[mysql_db_manager] MySQL 连接已断开 ({e})，尝试重连...")
                try:
                    _mysql_client.close()
                except Exception:
                    pass
                _mysql_client = None
                try:
                    _mysql_client = _create_mysql_client()
                    if _mysql_client and _mysql_client.connect():
                        _c = _mysql_client.conn.cursor()
                        _c.execute("SELECT 1")
                        _c.fetchone()
                        _ensure_mysql_tables(client=_mysql_client)
                        print("[mysql_db_manager] MySQL 重连成功")
                    else:
                        print(f"[mysql_db_manager] MySQL 重连失败 ({_mysql_conn_target})")
                        _mysql_client = None
                        _mysql_available = False
                        _mysql_last_fail_time = time.time()
                except Exception as e2:
                    print(f"[mysql_db_manager] MySQL 重连异常: {e2}")
                    _mysql_client = None
                    _mysql_available = False
                    _mysql_last_fail_time = time.time()

        return _mysql_client


# ── MySQL DDL ──────────────────────────────────────────────────────

_MYSQL_TABLE_DDL = {
    "sim_env_config": """
        CREATE TABLE IF NOT EXISTS `sim_env_config` (
            `id`          INT AUTO_INCREMENT PRIMARY KEY,
            `name`        VARCHAR(128) NOT NULL,
            `redis_ip`    VARCHAR(128) DEFAULT '',
            `redis_port`  VARCHAR(16) DEFAULT '6379',
            `redis_pwd`   VARCHAR(128) DEFAULT '',
            `kafka_url`   VARCHAR(256) DEFAULT '',
            `kafka_url2`  VARCHAR(256) DEFAULT '',
            `is_default`  TINYINT DEFAULT 0,
            `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仿真环境配置表'
    """,
    "sim_json_files": """
        CREATE TABLE IF NOT EXISTS `sim_json_files` (
            `id`           INT AUTO_INCREMENT PRIMARY KEY,
            `name`         VARCHAR(256) NOT NULL,
            `category`     VARCHAR(64) DEFAULT 'route',
            `alarm_type`   VARCHAR(64) DEFAULT '' COMMENT '告警类型',
            `file_path`    VARCHAR(1024) DEFAULT '' COMMENT '本地文件路径',
            `simulator_id` VARCHAR(2048) DEFAULT '' COMMENT '模拟器ID',
            `linked_route` VARCHAR(256) DEFAULT '' COMMENT '关联航线名称',
            `size_bytes`   INT DEFAULT 0,
            `source`       VARCHAR(32) DEFAULT 'manual',
            `description`  TEXT,
            `tags`         VARCHAR(512) DEFAULT '',
            `created_at`   DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='JSON数据文件表'
    """,
    "sim_scheduled_tasks": """
        CREATE TABLE IF NOT EXISTS `sim_scheduled_tasks` (
            `id`          INT AUTO_INCREMENT PRIMARY KEY,
            `name`        VARCHAR(256) NOT NULL,
            `cron_expr`   VARCHAR(64) DEFAULT '',
            `sim_mode`    VARCHAR(32) DEFAULT 'replay',
            `json_file_ids` VARCHAR(512) DEFAULT '',
            `sim_params`  TEXT,
            `enabled`     TINYINT DEFAULT 1,
            `last_run_at` DATETIME,
            `next_run_at` DATETIME,
            `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务表'
    """,
    "sim_task_logs": """
        CREATE TABLE IF NOT EXISTS `sim_task_logs` (
            `id`          INT AUTO_INCREMENT PRIMARY KEY,
            `task_id`     INT DEFAULT 0,
            `task_type`   VARCHAR(64) DEFAULT '',
            `status`      VARCHAR(32) DEFAULT 'running',
            `message`     TEXT,
            `started_at`  DATETIME,
            `finished_at` DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务执行日志表'
    """,
    "sim_alarm_types": """
        CREATE TABLE IF NOT EXISTS `sim_alarm_types` (
            `id`          INT AUTO_INCREMENT PRIMARY KEY,
            `name`        VARCHAR(128) NOT NULL UNIQUE,
            `color`       VARCHAR(16) DEFAULT '#64748b',
            `description` VARCHAR(256) DEFAULT '',
            `is_builtin`  TINYINT DEFAULT 0,
            `sort_order`  INT DEFAULT 0,
            `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='告警类型自定义表'
    """,
}


def _ensure_mysql_tables(client=None):
    """在 MySQL 中创建所有表（如不存在）。"""
    if client is None:
        client = _get_client()
    if not client:
        return
    for name, ddl in _MYSQL_TABLE_DDL.items():
        try:
            client.execute(ddl)
            cur = _cursor(client)
            cur.execute(f"SELECT 1 FROM `{name}` LIMIT 0")
            print(f"[mysql_db_manager] 表已就绪: {name}")
        except Exception as e:
            print(f"[mysql_db_manager] 建表失败 {name}: {e}")


def _cursor(client):
    """每次查询创建独立 cursor，避免多线程共享同一 cursor 导致 Protocol error。"""
    return client.conn.cursor()


# ── CRUD ───────────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_tables() -> None:
    """初始化所有表。"""
    _ensure_mysql_tables()


def query_all(table: str, order_by: str = "id DESC") -> List[Dict[str, Any]]:
    client = _get_client()
    if not client:
        return []
    safe_order = order_by.replace("id", "`id`") if "id" in order_by and "`id`" not in order_by else order_by
    sql = f"SELECT * FROM `{table}` ORDER BY {safe_order}"
    cur = _cursor(client)
    cur.execute(sql)
    return cur.fetchall()


def query_one(table: str, record_id: int) -> Optional[Dict[str, Any]]:
    client = _get_client()
    if not client:
        return None
    sql = f"SELECT * FROM `{table}` WHERE `id` = %s"
    cur = _cursor(client)
    cur.execute(sql, (record_id,))
    return cur.fetchone()


def query(table: str, where: str = "", params: tuple = (),
          order_by: str = "id DESC") -> List[Dict[str, Any]]:
    client = _get_client()
    if not client:
        return []
    sql = f"SELECT * FROM `{table}`"
    if where:
        sql += f" WHERE {where.replace('?', '%s')}"
    safe_order = order_by.replace("id", "`id`") if "id" in order_by else order_by
    sql += f" ORDER BY {safe_order}"
    cur = _cursor(client)
    cur.execute(sql, params if params else ())
    return cur.fetchall()


def insert(table: str, data: Dict[str, Any]) -> int:
    now = _now()
    data["created_at"] = data.get("created_at", now)
    data["updated_at"] = data.get("updated_at", now)
    client = _get_client()
    if not client:
        raise RuntimeError("MySQL 不可用，无法写入数据")
    columns = ", ".join(f"`{k}`" for k in data.keys())
    placeholders = ", ".join("%s" for _ in data)
    sql = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
    cur = _cursor(client)
    cur.execute(sql, list(data.values()))
    client.conn.commit()
    return cur.lastrowid


def update(table: str, record_id: int, data: Dict[str, Any]) -> bool:
    data["updated_at"] = _now()
    client = _get_client()
    if not client:
        return False
    sets = ", ".join(f"`{k}` = %s" for k in data)
    sql = f"UPDATE `{table}` SET {sets} WHERE `id` = %s"
    cur = _cursor(client)
    cur.execute(sql, list(data.values()) + [record_id])
    client.conn.commit()
    return True


def delete(table: str, record_id: int) -> bool:
    client = _get_client()
    if not client:
        return False
    sql = f"DELETE FROM `{table}` WHERE `id` = %s"
    cur = _cursor(client)
    cur.execute(sql, (record_id,))
    client.conn.commit()
    return True


def execute_raw(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    client = _get_client()
    if not client:
        return []
    cur = _cursor(client)
    cur.execute(sql, params)
    return cur.fetchall()


def execute_many_raw(sql: str, params_list: List[tuple]) -> bool:
    client = _get_client()
    if not client:
        return False
    for params in params_list:
        cur = _cursor(client)
        cur.execute(sql, params)
    client.conn.commit()
    return True


# ── 自检 ───────────────────────────────────────────────────────────

def _test():
    print("=== mysql_db_manager 自检 ===")
    init_tables()
    client = _get_client()
    if client:
        print(f"MySQL 连接: OK ({client.host}:{client.port}/{client.database})")
        tables = client.show_tables()
        print(f"现有表: {tables}")
    else:
        print("MySQL: 不可用")


if __name__ == "__main__":
    _test()
