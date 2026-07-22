# -*- coding: utf-8 -*-
"""
MySQL 数据库管理器 — 测试平台主数据库 CRUD 层

提供 query / query_one / query_all / insert / update / delete / init_tables
底层通过 DBUtils.PooledDB 连接池 + pymysql 操作 MySQL。
MySQL 不可用时抛出异常，不再降级到 SQLite（避免数据分歧）。

用法: from mysql_db_manager import query, insert, ...
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional

# 确保 tools/ 可导入（mysqldbclient 在 tools/ 目录下）
_tools_dir = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "tools",
)
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

# ── 导入 MySQL 客户端 ──────────────────────────────────────────────
from mysqldbclient import MysqlDbClient
import pymysql

try:
    from dbutils.pooled_db import PooledDB
except ImportError:
    PooledDB = None

# ── 限频日志（抑制 MySQL 不可用时的重复刷屏）──────────────────────────
try:
    from common.log_setup import RateLimitedPrinter
except ImportError:
    # 兜底
    class RateLimitedPrinter:
        def __init__(self, prefix, cooldown=60):
            self._prefix = prefix
            self._cooldown = cooldown
            self._last = {}
        def print(self, message, tag=""):
            import time as _t
            now = _t.time()
            key = tag or message
            if now - self._last.get(key, 0) >= self._cooldown:
                self._last[key] = now
                print(f"[{self._prefix}] {message}", flush=True)

_rlp_unavailable = RateLimitedPrinter("mysql_db_manager", cooldown=60)

_lock = threading.RLock()

# ── MySQL 连接池 ────────────────────────────────────────────────────
_mysql_client: Optional[Any] = None          # 当前活跃连接（从池中借出）
_mysql_available: Optional[bool] = None      # None=未检测, True=可用, False=不可用
_mysql_last_fail_time: float = 0.0
_MYSQL_RETRY_COOLDOWN: float = 60.0
_mysql_conn_target: str = ""
_pool: Optional[Any] = None                  # PooledDB 实例


def _get_or_create_pool():
    """线程安全地惰性初始化连接池。"""
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = _create_pool()
    return _pool


def _create_pool():
    """使用 DBUtils.PooledDB 创建 MySQL 连接池。

    返回 PooledDB 实例，失败返回 None。
    ping=1 在每次借出连接时自动校验连接有效性，替代手动健康检查。
    """
    global _mysql_conn_target

    if PooledDB is None:
        print("[mysql_db_manager] DBUtils 未安装，请执行: pip install DBUtils>=3.0")
        return None

    try:
        _common_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common")
        if _common_path not in sys.path:
            sys.path.insert(0, _common_path)
        from config import load_mysql_config
        cfg = load_mysql_config()
        _mysql_conn_target = f"{cfg.host}:{cfg.port}/{cfg.database}"
        print(f"[mysql_db_manager] MySQL 配置: host={cfg.host}, port={cfg.port}, "
              f"database={cfg.database}, use_ssl={cfg.use_ssl}")
        if not cfg.configured:
            print("[mysql_db_manager] MySQL 未配置 (UTM_MYSQL_HOST 未设置)")
            _mysql_conn_target = ""
            return None

        ssl_args = {}
        if cfg.use_ssl:
            ssl_args = {'ssl': {}}

        pool_instance = PooledDB(
            creator=pymysql,
            mincached=1,           # 最少保持 1 个空闲连接
            maxcached=5,           # 最多缓存 5 个连接
            maxconnections=10,     # 最大连接数（含借出的）
            blocking=True,         # 连接耗尽时等待而非报错
            ping=1,                # 每次借出时 ping 验证连接有效性
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            charset=cfg.charset,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,     # 连接超时 5 秒（从 10 秒降低）
            **ssl_args,
        )
        # 验证池可以创建连接
        test_conn = pool_instance.connection()
        test_conn.close()
        print(f"[mysql_db_manager] 连接池创建成功 ({_mysql_conn_target})")
        return pool_instance
    except Exception as e:
        print(f"[mysql_db_manager] 创建连接池失败: {e}")
        _mysql_conn_target = ""
        return None


def _get_client():
    """从连接池获取 MySQL 连接（单例持有 + 自动恢复）。

    线程安全。连接池的 ping=1 确保每次借出时连接有效，
    不再需要手动健康检查。断线后下次调用自动从池中获取新连接。
    """
    global _mysql_client, _mysql_available, _mysql_last_fail_time

    # 冷却期内直接返回 None，避免频繁重试
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

        # 首次或恢复后获取连接
        if _mysql_client is None:
            try:
                pool = _get_or_create_pool()
                if pool is None:
                    _mysql_available = False
                    _mysql_last_fail_time = time.time()
                    return None
                _mysql_client = pool.connection()
                _mysql_available = True
                print(f"[mysql_db_manager] MySQL 连接成功 ({_mysql_conn_target})")
            except Exception as e:
                print(f"[mysql_db_manager] MySQL 初始化异常: {e}")
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
            `dm_host`     VARCHAR(128) DEFAULT '' COMMENT '达梦数据库地址',
            `dm_port`     INT DEFAULT 5236 COMMENT '达梦数据库端口',
            `dm_user`     VARCHAR(128) DEFAULT 'SYSDBA' COMMENT '达梦用户名',
            `dm_password` VARCHAR(128) DEFAULT '' COMMENT '达梦密码',
            `dm_schema`   VARCHAR(128) DEFAULT '' COMMENT '达梦模式名',
            `mysql_host`     VARCHAR(128) DEFAULT '' COMMENT 'MySQL地址',
            `mysql_port`     INT DEFAULT 3306 COMMENT 'MySQL端口',
            `mysql_user`     VARCHAR(128) DEFAULT '' COMMENT 'MySQL用户',
            `mysql_password` VARCHAR(128) DEFAULT '' COMMENT 'MySQL密码',
            `mysql_database` VARCHAR(128) DEFAULT '' COMMENT 'MySQL数据库名',
            `atc_cluster_api` VARCHAR(256) DEFAULT '' COMMENT '集群API地址',
            `atc_vip`      VARCHAR(128) DEFAULT '' COMMENT 'ATC VIP地址',
            `atc_node_a`   VARCHAR(128) DEFAULT '' COMMENT 'ATC A节点',
            `atc_node_b`   VARCHAR(128) DEFAULT '' COMMENT 'ATC B节点',
            `es_hosts`     VARCHAR(512) DEFAULT '' COMMENT 'ES地址(JSON)',
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
    "sim_scenes": """
        CREATE TABLE IF NOT EXISTS `sim_scenes` (
            `id`          INT AUTO_INCREMENT PRIMARY KEY,
            `name`        VARCHAR(256) NOT NULL COMMENT '场景名称',
            `env_id`      INT DEFAULT 0 COMMENT '关联环境配置ID (sim_env_config.id)',
            `scene_type`  VARCHAR(16) DEFAULT 'single' COMMENT '场景类型: single|multi',
            `cron_expr`   VARCHAR(64) DEFAULT '' COMMENT 'cron调度表达式',
            `sim_mode`    VARCHAR(32) DEFAULT 'scene' COMMENT '仿真模式',
            `enabled`     TINYINT DEFAULT 1 COMMENT '是否启用',
            `last_run_at` DATETIME COMMENT '上次执行时间',
            `next_run_at` DATETIME COMMENT '下次执行时间',
            `created_at`  DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景编排主表'
    """,
    "sim_scene_tasks": """
        CREATE TABLE IF NOT EXISTS `sim_scene_tasks` (
            `id`                    INT AUTO_INCREMENT PRIMARY KEY,
            `scene_id`              INT NOT NULL COMMENT '关联场景ID',
            `name`                  VARCHAR(256) NOT NULL COMMENT '任务名称',
            `task_type`             VARCHAR(16) DEFAULT 'sequential' COMMENT '执行类型: sequential|parallel',
            `cycle_interval_sec`    INT DEFAULT 0 COMMENT '循环间隔(秒)，0=不循环',
            `repeat_count`          INT DEFAULT 1 COMMENT '重复次数',
            `execution_timeout_sec` INT DEFAULT 300 COMMENT '执行超时(秒)',
            `sort_order`            INT DEFAULT 0 COMMENT '排序号',
            `created_at`            DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`            DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景任务表'
    """,
    "sim_scene_task_files": """
        CREATE TABLE IF NOT EXISTS `sim_scene_task_files` (
            `id`           INT AUTO_INCREMENT PRIMARY KEY,
            `task_id`      INT NOT NULL COMMENT '关联任务ID',
            `file_id`      INT NOT NULL COMMENT '关联文件ID (sim_json_files.id)',
            `interval_sec` INT DEFAULT 0 COMMENT '文件间等待间隔(秒)',
            `sort_order`   INT DEFAULT 0 COMMENT '文件执行顺序',
            `created_at`   DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景任务文件关联表'
    """,
    "sim_task_logs": """
        CREATE TABLE IF NOT EXISTS `sim_task_logs` (
            `id`              INT AUTO_INCREMENT PRIMARY KEY,
            `task_id`         INT DEFAULT 0 COMMENT '场景ID（兼容旧字段）',
            `scene_id`        INT DEFAULT 0 COMMENT '场景ID',
            `scene_task_name` VARCHAR(256) DEFAULT '' COMMENT '任务名称',
            `task_type`       VARCHAR(64) DEFAULT '' COMMENT '日志类型',
            `status`          VARCHAR(32) DEFAULT 'running',
            `message`         TEXT,
            `started_at`      DATETIME,
            `finished_at`     DATETIME,
            `created_at`      DATETIME DEFAULT CURRENT_TIMESTAMP,
            `updated_at`      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='场景任务执行日志表'
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
    "sim_system_logs": """
        CREATE TABLE IF NOT EXISTS `sim_system_logs` (
            `id`         BIGINT AUTO_INCREMENT PRIMARY KEY,
            `time`       VARCHAR(20) NOT NULL COMMENT '日志时间 HH:mm:ss',
            `type`       VARCHAR(32) NOT NULL COMMENT '日志类型 key',
            `type_name`  VARCHAR(64) DEFAULT '' COMMENT '日志类型中文名',
            `message`    TEXT COMMENT '日志消息',
            `detail`     TEXT COMMENT '结构化详情 JSON',
            `task_id`    VARCHAR(64) DEFAULT '' COMMENT '关联任务 ID',
            `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
            `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统日志持久化表'
    """,
}


def _ensure_mysql_tables(client=None):
    """在 MySQL 中创建所有表（如不存在）。

    先 SHOW TABLES 获取已有表，只对缺失的表执行 CREATE，避免
    对已存在的表重复执行 DDL 触发远程 MySQL 网络超时。
    """
    import sys as _sys
    _p = lambda msg: print(msg, file=_sys.stderr, flush=True)

    if client is None:
        client = _get_client()
    if not client:
        return

    # 1. 获取已存在的表名
    existing_tables = set()
    try:
        cur = client.cursor()
        cur.execute("SHOW TABLES")
        for row in cur.fetchall():
            existing_tables.add(list(row.values())[0])
        _p(f"[mysql_db_manager] 已有表: {existing_tables}")
    except Exception as e:
        _p(f"[mysql_db_manager] SHOW TABLES 失败: {e}, 将尝试全部建表")

    # 2. 只对缺失的表执行 CREATE
    for name, ddl in _MYSQL_TABLE_DDL.items():
        if name in existing_tables:
            _p(f"[mysql_db_manager] 表已存在 (跳过): {name}")
            continue

        _p(f"[mysql_db_manager] 创建表: {name} ...")
        try:
            cur = client.cursor()
            cur.execute(ddl)
            _p(f"[mysql_db_manager] 表已创建: {name}")
        except Exception as e:
            err_msg = str(e)
            _p(f"[mysql_db_manager] 建表失败 {name}: {err_msg}")
            # 连接错误 → 重置状态，下次查询时自动重连
            if "Lost connection" in err_msg or "timed out" in err_msg:
                _try_reset_broken_connection()

    # 3. 对已存在的表，检查并补全缺失列（ALTER TABLE ADD COLUMN）
    _ALTER_COLUMNS = {
        "sim_env_config": [
            ("dm_host",     "VARCHAR(128) DEFAULT '' COMMENT '达梦数据库地址'"),
            ("dm_port",     "INT DEFAULT 5236 COMMENT '达梦数据库端口'"),
            ("dm_user",     "VARCHAR(128) DEFAULT 'SYSDBA' COMMENT '达梦用户名'"),
            ("dm_password", "VARCHAR(128) DEFAULT '' COMMENT '达梦密码'"),
            ("dm_schema",   "VARCHAR(128) DEFAULT '' COMMENT '达梦模式名'"),
            ("mysql_host",     "VARCHAR(128) DEFAULT '' COMMENT 'MySQL地址'"),
            ("mysql_port",     "INT DEFAULT 3306 COMMENT 'MySQL端口'"),
            ("mysql_user",     "VARCHAR(128) DEFAULT '' COMMENT 'MySQL用户'"),
            ("mysql_password", "VARCHAR(128) DEFAULT '' COMMENT 'MySQL密码'"),
            ("mysql_database", "VARCHAR(128) DEFAULT '' COMMENT 'MySQL数据库名'"),
            ("atc_cluster_api", "VARCHAR(256) DEFAULT '' COMMENT '集群API'"),
            ("atc_vip",      "VARCHAR(128) DEFAULT '' COMMENT 'ATC VIP'"),
            ("atc_node_a",   "VARCHAR(128) DEFAULT '' COMMENT 'ATC A节点'"),
            ("atc_node_b",   "VARCHAR(128) DEFAULT '' COMMENT 'ATC B节点'"),
            ("es_hosts",     "VARCHAR(512) DEFAULT '' COMMENT 'ES地址(JSON)'"),
        ],
        "sim_scene_tasks": [
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ],
        "sim_scene_task_files": [
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ],
        "sim_task_logs": [
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ],
    }
    for table_name, columns in _ALTER_COLUMNS.items():
        if table_name not in existing_tables:
            continue
        try:
            cur = client.cursor()
            cur.execute(f"SHOW COLUMNS FROM `{table_name}`")
            existing_cols = set()
            for row in cur.fetchall():
                existing_cols.add(list(row.values())[0])
            for col_name, col_def in columns:
                if col_name in existing_cols:
                    continue
                try:
                    cur2 = client.cursor()
                    cur2.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{col_name}` {col_def}")
                    _p(f"[mysql_db_manager] ALTER {table_name} 已增加列: {col_name}")
                except Exception as e:
                    _p(f"[mysql_db_manager] ALTER {table_name}.{col_name} 跳过: {e}")
        except Exception as e:
            _p(f"[mysql_db_manager] 检查 {table_name} 列信息失败: {e}")


def _try_reset_broken_connection():
    """强制重置全局连接状态（DDL 超时导致连接损坏后调用）。"""
    global _mysql_client, _mysql_available, _mysql_last_fail_time
    _mysql_client = None
    _mysql_available = None
    _mysql_last_fail_time = 0.0


def _cursor(client):
    """每次查询创建独立 cursor。"""
    if client is None:
        return None
    return client.cursor()


# ── CRUD ───────────────────────────────────────────────────────────

def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_tables_initialized = False
_tables_init_lock = threading.RLock()


def init_tables() -> None:
    """初始化所有 MySQL 表（首次调用执行，后续跳过，线程安全）。

    MySQL 不可用时抛出异常，不再降级到 SQLite。
    """
    global _tables_initialized
    if _tables_initialized:
        return
    with _tables_init_lock:
        if _tables_initialized:
            return
        _ensure_mysql_tables()
        _tables_initialized = True


def query_all(table: str, order_by: str = "id DESC") -> List[Dict[str, Any]]:
    with _lock:
        client = _get_client()
        if not client:
            _rlp_unavailable.print(f"MySQL 不可用，query_all({table}) 返回空", tag="unavailable_query_all")
            return []
        try:
            safe_order = order_by.replace("id", "`id`") if "id" in order_by and "`id`" not in order_by else order_by
            sql = f"SELECT * FROM `{table}` ORDER BY {safe_order}"
            cur = client.cursor()
            cur.execute(sql)
            return cur.fetchall()
        except Exception as e:
            print(f"[mysql_db_manager] query_all 失败 ({table}): {e}")
            return []


def query_one(table: str, record_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        client = _get_client()
        if not client:
            _rlp_unavailable.print(f"MySQL 不可用，query_one({table}) 返回 None", tag="unavailable_query_one")
            return None
        try:
            sql = f"SELECT * FROM `{table}` WHERE `id` = %s"
            cur = client.cursor()
            cur.execute(sql, (record_id,))
            return cur.fetchone()
        except Exception as e:
            print(f"[mysql_db_manager] query_one 失败 ({table}#{record_id}): {e}")
            return None


def query(table: str, where: str = "", params: tuple = (),
          order_by: str = "id DESC",
          limit: int = 0, offset: int = 0) -> List[Dict[str, Any]]:
    with _lock:
        client = _get_client()
        if not client:
            _rlp_unavailable.print(f"MySQL 不可用，query({table}) 返回空", tag="unavailable_query")
            return []
        try:
            sql = f"SELECT * FROM `{table}`"
            if where:
                sql += f" WHERE {where.replace('?', '%s')}"
            safe_order = order_by.replace("id", "`id`") if "id" in order_by else order_by
            sql += f" ORDER BY {safe_order}"
            if limit > 0:
                sql += f" LIMIT {int(limit)}"
            if offset > 0:
                sql += f" OFFSET {int(offset)}"
            cur = client.cursor()
            cur.execute(sql, params if params else ())
            return cur.fetchall()
        except Exception as e:
            print(f"[mysql_db_manager] query 失败 ({table}): {e}")
            return []


def query_count(table: str, where: str = "", params: tuple = ()) -> int:
    """查询符合条件的记录总数。"""
    with _lock:
        client = _get_client()
        if not client:
            _rlp_unavailable.print(f"MySQL 不可用，query_count({table}) 返回 0", tag="unavailable_query_count")
            return 0
        try:
            sql = f"SELECT COUNT(*) as cnt FROM `{table}`"
            if where:
                sql += f" WHERE {where.replace('?', '%s')}"
            cur = client.cursor()
            cur.execute(sql, params if params else ())
            row = cur.fetchone()
            return row["cnt"] if row else 0
        except Exception as e:
            print(f"[mysql_db_manager] query_count 失败 ({table}): {e}")
            return 0


def insert(table: str, data: Dict[str, Any]) -> int:
    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        with _lock:
            now = _now()
            data["created_at"] = data.get("created_at", now)
            data["updated_at"] = data.get("updated_at", now)
            client = _get_client()
            if not client:
                raise RuntimeError(f"MySQL 不可用，无法写入 {table}")
            columns = ", ".join(f"`{k}`" for k in data.keys())
            placeholders = ", ".join("%s" for _ in data)
            sql = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
            cur = client.cursor()
            try:
                cur.execute(sql, list(data.values()))
                client.commit()
                return cur.lastrowid
            except pymysql.err.OperationalError as e:
                client.rollback()
                if e.args[0] == 1213 and attempt < max_retries - 1:
                    wait = 0.1 * (3 ** attempt)
                    print(f"[mysql_db_manager] INSERT 死锁 (1213)，{wait:.1f}s 后重试 #{attempt + 1}")
                    last_error = e
                    time.sleep(wait)
                else:
                    raise
            except Exception:
                client.rollback()
                raise
    raise last_error


def update(table: str, record_id: int, data: Dict[str, Any]) -> bool:
    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        with _lock:
            data["updated_at"] = _now()
            client = _get_client()
            if not client:
                raise RuntimeError(f"MySQL 不可用，无法更新 {table}")
            sets = ", ".join(f"`{k}` = %s" for k in data)
            sql = f"UPDATE `{table}` SET {sets} WHERE `id` = %s"
            cur = client.cursor()
            try:
                cur.execute(sql, list(data.values()) + [record_id])
                client.commit()
                return True
            except pymysql.err.OperationalError as e:
                client.rollback()
                if e.args[0] == 1213 and attempt < max_retries - 1:
                    wait = 0.1 * (3 ** attempt)
                    print(f"[mysql_db_manager] UPDATE 死锁 (1213)，{wait:.1f}s 后重试 #{attempt + 1}")
                    last_error = e
                    time.sleep(wait)
                else:
                    raise
            except Exception:
                client.rollback()
                raise
    raise last_error


def delete(table: str, record_id: int) -> bool:
    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        with _lock:
            client = _get_client()
            if not client:
                raise RuntimeError(f"MySQL 不可用，无法删除 {table}")
            sql = f"DELETE FROM `{table}` WHERE `id` = %s"
            cur = client.cursor()
            try:
                cur.execute(sql, (record_id,))
                client.commit()
                return True
            except pymysql.err.OperationalError as e:
                client.rollback()
                if e.args[0] == 1213 and attempt < max_retries - 1:
                    wait = 0.1 * (3 ** attempt)
                    print(f"[mysql_db_manager] DELETE 死锁 (1213)，{wait:.1f}s 后重试 #{attempt + 1}")
                    last_error = e
                    time.sleep(wait)
                else:
                    raise
            except Exception:
                client.rollback()
                raise
    raise last_error


def query_distinct(table: str, column: str) -> List[str]:
    """查询某列的 DISTINCT 值（避免 SELECT * 全表扫描）。"""
    with _lock:
        client = _get_client()
        if not client:
            _rlp_unavailable.print(f"MySQL 不可用，query_distinct({table}) 返回空", tag="unavailable_query_distinct")
            return []
        try:
            cur = client.cursor()
            cur.execute(f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` != ''")
            return [row[column] for row in cur.fetchall()]
        except Exception as e:
            print(f"[mysql_db_manager] query_distinct 失败 ({table}.{column}): {e}")
            return []


def execute_raw(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _lock:
        client = _get_client()
        if not client:
            _rlp_unavailable.print(f"MySQL 不可用，execute_raw 返回空", tag="unavailable_execute_raw")
            return []
        try:
            cur = client.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        except Exception as e:
            print(f"[mysql_db_manager] execute_raw 失败: {e}")
            return []


def execute_many_raw(sql: str, params_list: List[tuple]) -> bool:
    with _lock:
        client = _get_client()
        if not client:
            raise RuntimeError("MySQL 不可用，无法执行批量操作")
        for params in params_list:
            cur = client.cursor()
            cur.execute(sql, params)
        client.commit()
        return True


# ── 自检 ───────────────────────────────────────────────────────────

def _test():
    print("=== mysql_db_manager 自检 ===")
    init_tables()
    client = _get_client()
    if client:
        from config import load_mysql_config
        cfg = load_mysql_config()
        print(f"MySQL 连接: OK ({cfg.host}:{cfg.port}/{cfg.database})")
        # 查询表列表
        cur = client.cursor()
        cur.execute("SHOW TABLES")
        tables = [list(row.values())[0] for row in cur.fetchall()]
        print(f"现有表: {tables}")
    else:
        print("MySQL: 不可用")


if __name__ == "__main__":
    _test()
