# -*- coding: utf-8 -*-
"""
MySQL 数据库管理器 — 与 db_manager.py 接口一致的 MySQL CRUD 适配层

提供 query / query_one / query_all / insert / update / delete / init_tables
七组函数，底层通过 mysqldbclient.MysqlDbClient 操作 MySQL，
MySQL 不可用时自动 fallback 到 SQLite db_manager（优雅降级）。

用法: 将原先的 `from db_manager import query, insert, ...` 替换为
           `from mysql_db_manager import query, insert, ...`
     其余调用代码无需修改。
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any, Dict, List, Optional

# 确保 mysqldbclient 可导入
_atc_tools = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "atc_api_autotest", "api_tools",
)
if _atc_tools not in sys.path:
    sys.path.insert(0, _atc_tools)

# ── 尝试导入 MySQL 客户端 ──────────────────────────────────────────
try:
    from mysqldbclient import MysqlDbClient
    _HAS_MYSQL_IMPORT = True
except (ImportError, Exception):
    _HAS_MYSQL_IMPORT = False
    MysqlDbClient = None

# ── SQLite fallback ────────────────────────────────────────────────
import db_manager as _sqlite

_lock = threading.Lock()

# ── MySQL 连接单例 ─────────────────────────────────────────────────
_mysql_client: Optional[Any] = None
_mysql_available: Optional[bool] = None  # None=未检测, True=可用, False=不可用


def _get_client():
    """获取 MySQL 客户端（延迟初始化 + 连接检测 + 自动重连），不可用时返回 None。

    线程安全：通过 _lock 保护模块级单例的创建/销毁/重连，避免多线程并发
    访问导致 conn 状态不一致（如 "NoneType has no attribute settimeout"）。
    """
    global _mysql_client, _mysql_available
    # ── 无锁快速路径：已知不可用或未安装 ──
    if not _HAS_MYSQL_IMPORT:
        _mysql_available = False
        return None
    if _mysql_available is False:
        return None
    with _lock:
        # 双重检查：锁内再次确认状态未被其他线程改变
        if _mysql_available is False:
            return None
        # ── 首次连接 ──
        if _mysql_client is None and _mysql_available is None:
            try:
                _mysql_client = MysqlDbClient()
                if _mysql_client.connect():
                    _mysql_available = True
                    _ensure_mysql_tables(client=_mysql_client)
                    print("[mysql_db_manager] MySQL 连接成功，使用 MySQL 持久化")
                else:
                    print("[mysql_db_manager] MySQL 连接失败，降级到 SQLite")
                    _mysql_client = None
                    _mysql_available = False
            except Exception as e:
                print(f"[mysql_db_manager] MySQL 初始化异常: {e}，降级到 SQLite")
                _mysql_client = None
                _mysql_available = False
        # ── 连接保活检查（pymysql 连接可能被服务端/网络关闭） ──
        if _mysql_client is not None and _mysql_available is True:
            try:
                _mysql_client.conn.ping(reconnect=True)
            except Exception as e:
                print(f"[mysql_db_manager] MySQL ping 失败: {e}，尝试新建连接...")
                # 关闭旧连接，创建全新客户端实例（避免 SSL 状态残留导致 BAD_LENGTH）
                try:
                    _mysql_client.close()
                except Exception:
                    pass
                _mysql_client = None
                try:
                    _mysql_client = MysqlDbClient()
                    if _mysql_client.connect():
                        _ensure_mysql_tables(client=_mysql_client)
                        print("[mysql_db_manager] MySQL 重连成功")
                    else:
                        print("[mysql_db_manager] MySQL 重连失败，降级到 SQLite")
                        _mysql_client = None
                        _mysql_available = False
                except Exception as e2:
                    print(f"[mysql_db_manager] MySQL 重连异常: {e2}，降级到 SQLite")
                    _mysql_client = None
                    _mysql_available = False
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
            `id`          INT AUTO_INCREMENT PRIMARY KEY,
            `name`        VARCHAR(256) NOT NULL,
            `category`    VARCHAR(64) DEFAULT 'route',
            `content`     LONGTEXT,
            `size_bytes`  INT DEFAULT 0,
            `description` TEXT,
            `tags`        VARCHAR(512) DEFAULT '',
            `created_by`  VARCHAR(64) DEFAULT 'manual',
            `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
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
}


def _ensure_mysql_tables(client=None):
    """在 MySQL 中创建所有表（如不存在），创建后验证表确实存在。

    Args:
        client: 可选，已连接的 MysqlDbClient 实例。由 _get_client() 持锁调用时
                传入以避免锁内递归调用 _get_client() 导致死锁。
    """
    if client is None:
        client = _get_client()
    if not client:
        return
    for name, ddl in _MYSQL_TABLE_DDL.items():
        try:
            client.execute(ddl)
            # DDL 返回 None（非查询语句），需额外验证表确实存在
            client.cursor.execute(f"SELECT 1 FROM `{name}` LIMIT 0")
            print(f"[mysql_db_manager] MySQL 表已就绪: {name}")
        except Exception as e:
            print(f"[mysql_db_manager] 建表失败 {name}: {e}")


# ── 检测当前使用的后端 ─────────────────────────────────────────────

def _use_mysql() -> bool:
    """当前是否使用 MySQL（连接可用则优先）。"""
    return _get_client() is not None


# ── 通用 CRUD（与 db_manager.py 接口一致） ─────────────────────────

def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_tables() -> None:
    """初始化所有表（MySQL 可用则建 MySQL 表，否则建 SQLite 表）。"""
    if _use_mysql():
        _ensure_mysql_tables()
    else:
        _sqlite.init_tables()


def query_all(table: str, order_by: str = "id DESC") -> List[Dict[str, Any]]:
    """查询表中所有记录。"""
    client = _get_client()
    if client:
        try:
            # MySQL: 用反引号包裹表名和列名
            safe_order = order_by.replace("id", "`id`") if "id" in order_by and "`id`" not in order_by else order_by
            sql = f"SELECT * FROM `{table}` ORDER BY {safe_order}"
            client.cursor.execute(sql)
            return client.cursor.fetchall()
        except Exception as e:
            print(f"[mysql_db_manager] query_all 失败: {e}，降级到 SQLite")
    return _sqlite.query_all(table, order_by)


def query_one(table: str, record_id: int) -> Optional[Dict[str, Any]]:
    """按 ID 查询单条记录。"""
    client = _get_client()
    if client:
        try:
            sql = f"SELECT * FROM `{table}` WHERE `id` = %s"
            client.cursor.execute(sql, (record_id,))
            return client.cursor.fetchone()
        except Exception as e:
            print(f"[mysql_db_manager] query_one 失败: {e}，降级到 SQLite")
    return _sqlite.query_one(table, record_id)


def query(table: str, where: str = "", params: tuple = (),
          order_by: str = "id DESC") -> List[Dict[str, Any]]:
    """条件查询。where 参数使用 SQLite 风格的 ? 占位符，自动转换为 MySQL %s。"""
    client = _get_client()
    if client:
        try:
            sql = f"SELECT * FROM `{table}`"
            if where:
                # 将 ? 占位符转为 %s（MySQL 风格）
                mysql_where = where.replace("?", "%s")
                sql += f" WHERE {mysql_where}"
            # 排序字段加反引号
            safe_order = order_by.replace("id", "`id`") if "id" in order_by else order_by
            sql += f" ORDER BY {safe_order}"
            client.cursor.execute(sql, params if params else ())
            return client.cursor.fetchall()
        except Exception as e:
            print(f"[mysql_db_manager] query 失败: {e}，降级到 SQLite")
    return _sqlite.query(table, where, params, order_by)


def insert(table: str, data: Dict[str, Any]) -> int:
    """插入一条记录，返回新 ID。"""
    now = _now()
    data["created_at"] = data.get("created_at", now)
    data["updated_at"] = data.get("updated_at", now)
    client = _get_client()
    if client:
        try:
            columns = ", ".join(f"`{k}`" for k in data.keys())
            placeholders = ", ".join("%s" for _ in data)
            values = list(data.values())
            sql = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
            client.cursor.execute(sql, values)
            client.conn.commit()
            return client.cursor.lastrowid
        except Exception as e:
            print(f"[mysql_db_manager] insert 失败: {e}，降级到 SQLite")
            try:
                client.conn.rollback()
            except Exception:
                pass
    return _sqlite.insert(table, data)


def update(table: str, record_id: int, data: Dict[str, Any]) -> bool:
    """按 ID 更新一条记录。"""
    data["updated_at"] = _now()
    client = _get_client()
    if client:
        try:
            sets = ", ".join(f"`{k}` = %s" for k in data)
            values = list(data.values()) + [record_id]
            sql = f"UPDATE `{table}` SET {sets} WHERE `id` = %s"
            client.cursor.execute(sql, values)
            client.conn.commit()
            return True
        except Exception as e:
            print(f"[mysql_db_manager] update 失败: {e}，降级到 SQLite")
            try:
                client.conn.rollback()
            except Exception:
                pass
    return _sqlite.update(table, record_id, data)


def delete(table: str, record_id: int) -> bool:
    """按 ID 删除一条记录。"""
    client = _get_client()
    if client:
        try:
            sql = f"DELETE FROM `{table}` WHERE `id` = %s"
            client.cursor.execute(sql, (record_id,))
            client.conn.commit()
            return True
        except Exception as e:
            print(f"[mysql_db_manager] delete 失败: {e}，降级到 SQLite")
            try:
                client.conn.rollback()
            except Exception:
                pass
    return _sqlite.delete(table, record_id)


def execute_raw(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """执行原始 SQL 查询（只读）。"""
    client = _get_client()
    if client:
        try:
            client.cursor.execute(sql, params)
            return client.cursor.fetchall()
        except Exception as e:
            print(f"[mysql_db_manager] execute_raw 失败: {e}，降级到 SQLite")
    return _sqlite.execute_raw(sql, params)


# ── 批量写入（用于 set_default 等操作） ─────────────────────────────

def execute_many_raw(sql: str, params_list: List[tuple]) -> bool:
    """批量执行 SQL（非查询）。返回是否成功。"""
    client = _get_client()
    if client:
        try:
            for params in params_list:
                client.cursor.execute(sql, params)
            client.conn.commit()
            return True
        except Exception as e:
            print(f"[mysql_db_manager] execute_many_raw 失败: {e}")
            try:
                client.conn.rollback()
            except Exception:
                pass
    return False


# ── 便捷入口：测试脚本 ──────────────────────────────────────────────

def _test():
    """独立测试 MySQL 连接 + CRUD。"""
    print("=== mysql_db_manager 自检 ===")
    init_tables()
    client = _get_client()
    if client:
        print(f"MySQL 连接: OK ({client.host}:{client.port}/{client.database})")
        tables = client.show_tables()
        print(f"现有表: {tables}")
    else:
        print("MySQL: 不可用，使用 SQLite fallback")
        print("SQLite 路径:", _sqlite.DB_PATH)


if __name__ == "__main__":
    _test()
