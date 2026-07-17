#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性数据迁移脚本：将 SQLite 中 sim_env_config 和 sim_json_files 的全部记录
迁移到 MySQL 对应表。

用法:
    conda run -n utm python database/migrate_to_mysql.py

安全设计:
    - 不会删除 SQLite 数据（只读迁移）
    - 重复运行幂等（按 name 去重，同名记录跳过）
"""

import os
import sys

# 确保 database/ 在 sys.path
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import db_manager as _sqlite
from mysql_db_manager import _get_client, _ensure_mysql_tables, _mysql_conn_target


def migrate_env_config():
    """迁移 sim_env_config 表。"""
    client = _get_client()
    if not client:
        print("❌ MySQL 不可用，迁移中止")
        return False

    _sqlite.init_tables()
    rows = _sqlite.query_all("sim_env_config")
    if not rows:
        print("  sim_env_config: SQLite 中无数据，跳过")
        return True

    print(f"  sim_env_config: SQLite 有 {len(rows)} 条记录，开始迁移...")

    # 获取 MySQL 中已有的 name 列表（用于幂等）
    try:
        cur = client.cursor()
        cur.execute("SELECT `name` FROM `sim_env_config`")
        existing_names = {r["name"] for r in cur.fetchall()}
    except Exception:
        existing_names = set()

    migrated = 0
    skipped = 0
    for row in rows:
        name = row.get("name", "")
        if name in existing_names:
            skipped += 1
            continue

        data = {
            "name": name,
            "redis_ip": row.get("redis_ip", ""),
            "redis_port": str(row.get("redis_port", "6379")),
            "redis_pwd": row.get("redis_pwd", ""),
            "kafka_url": row.get("kafka_url", ""),
            "kafka_url2": row.get("kafka_url2", ""),
            "is_default": int(row.get("is_default", 0)),
        }
        try:
            columns = ", ".join(f"`{k}`" for k in data)
            placeholders = ", ".join("%s" for _ in data)
            sql = f"INSERT INTO `sim_env_config` ({columns}) VALUES ({placeholders})"
            cur = client.cursor()
            cur.execute(sql, list(data.values()))
            client.commit()
            migrated += 1
        except Exception as e:
            print(f"    ⚠️ 写入失败 [{name}]: {e}")
            client.rollback()

    print(f"  sim_env_config: 迁移 {migrated} 条, 跳过 {skipped} 条 (已存在)")
    return True


def migrate_json_files():
    """迁移 sim_json_files 表。"""
    client = _get_client()
    if not client:
        return False

    _sqlite.init_tables()
    rows = _sqlite.query_all("sim_json_files")
    if not rows:
        print("  sim_json_files: SQLite 中无数据，跳过")
        return True

    print(f"  sim_json_files: SQLite 有 {len(rows)} 条记录，开始迁移...")

    try:
        cur = client.cursor()
        cur.execute("SELECT `name` FROM `sim_json_files`")
        existing_names = {r["name"] for r in cur.fetchall()}
    except Exception:
        existing_names = set()

    migrated = 0
    skipped = 0
    for row in rows:
        name = row.get("name", "")
        if name in existing_names:
            skipped += 1
            continue

        data = {
            "name": name,
            "category": row.get("category", "route"),
            "content": row.get("content", ""),
            "size_bytes": row.get("size_bytes", 0),
            "description": row.get("description", ""),
            "tags": row.get("tags", ""),
            "created_by": row.get("created_by", "migration"),
        }
        try:
            columns = ", ".join(f"`{k}`" for k in data)
            placeholders = ", ".join("%s" for _ in data)
            sql = f"INSERT INTO `sim_json_files` ({columns}) VALUES ({placeholders})"
            cur = client.cursor()
            cur.execute(sql, list(data.values()))
            client.commit()
            migrated += 1
        except Exception as e:
            print(f"    ⚠️ 写入失败 [{name}]: {e}")
            client.rollback()

    print(f"  sim_json_files: 迁移 {migrated} 条, 跳过 {skipped} 条 (已存在)")
    return True


def main():
    print("=== SQLite → MySQL 数据迁移 ===\n")

    # 确保 MySQL 表存在
    _ensure_mysql_tables()

    # 检查 MySQL 连接
    client = _get_client()
    if not client:
        print("❌ MySQL 不可用，请检查连接配置和网络")
        print("   SQLite 数据未受影响，可稍后重试")
        return

    print(f"✅ MySQL 已连接: {_mysql_conn_target}\n")
    print("SQLite 路径:", _sqlite.DB_PATH, "\n")

    # 执行迁移
    migrate_env_config()
    print()
    migrate_json_files()

    print("\n=== 迁移完成 ===")


if __name__ == "__main__":
    main()
