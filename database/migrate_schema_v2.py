# -*- coding: utf-8 -*-
"""
Schema migration v1 → v2: 将 sim_json_files 表从 content 存储改为 file_path 存储。

迁移内容:
1. MySQL/SQLite 添加新列: alarm_type, file_path, simulator_id, linked_route, source
2. 将现有记录的 content 写入磁盘文件 data/mock/db_export/{id}_{name}
3. 自动检测并填充 alarm_type / simulator_id / linked_route
4. 将 created_by 映射为 source

用法:
    python database/migrate_schema_v2.py           # 查看状态
    python database/migrate_schema_v2.py --execute  # 执行迁移
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

# 添加项目根路径
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "database"))
sys.path.insert(0, os.path.join(_project_root, "common"))

from config import MOCK_DIR

# ── 检测函数 ────────────────────────────────────────────────────────

def _detect_alarm_type(fname: str, sample: str = "") -> str:
    if "碰撞预警" in fname:
        return "碰撞预警"
    if "偏航" in fname:
        return "偏航"
    if "航路最低安全高度" in fname or "最低安全高度" in fname:
        return "最低安全高度"
    if "nfz" in fname.lower() or "禁飞" in fname:
        return "禁飞区"
    if sample:
        try:
            data = json.loads(sample[:65536])
            if isinstance(data, list) and data and isinstance(data[0], dict):
                first = data[0]
                if "key" in first and "value" in first:
                    return "飞行计划"
                if "longitude" in first and "latitude" in first:
                    return "正常遥测"
        except Exception:
            pass
    return "正常遥测"


def _extract_simulator_id(content: str) -> str:
    if not content:
        return ""
    try:
        data = json.loads(content[:65536])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            first = data[0]
            if "uniqueProductIdentificationCode" in first:
                return str(first["uniqueProductIdentificationCode"])
            if "key" in first:
                return str(first["key"])
        elif isinstance(data, dict):
            if "uniqueProductIdentificationCode" in data:
                return str(data["uniqueProductIdentificationCode"])
            if "value" in data and isinstance(data["value"], dict):
                val = data["value"]
                if "uniqueProductIdentificationCode" in val:
                    return str(val["uniqueProductIdentificationCode"])
    except Exception:
        pass
    return ""


def _detect_linked_route(fname: str, sample: str = "") -> str:
    import re
    for pattern in [r"^(.+?)_碰撞预警_", r"^(.+?)航路偏航数据", r"^(.+?)航路最低安全高度"]:
        m = re.match(pattern, fname)
        if m:
            return m.group(1)
    if sample:
        try:
            data = json.loads(sample[:65536])
            if isinstance(data, list) and data and isinstance(data[0], dict):
                first = data[0]
                if "value" in first and isinstance(first["value"], dict):
                    val = first["value"]
                    if "flightPlanList" in val and val["flightPlanList"]:
                        fp = val["flightPlanList"][0]
                        if isinstance(fp, dict) and fp.get("flightTaskName"):
                            return str(fp["flightTaskName"])
        except Exception:
            pass
    return ""


# ── 迁移逻辑 ────────────────────────────────────────────────────────

def check_status():
    """检查当前状态。"""
    from mysql_db_manager import query_all as mq
    rows = mq("sim_json_files")
    print(f"sim_json_files 现有记录数: {len(rows)}")
    if rows:
        r = rows[0]
        has_new = all(k in r for k in ["alarm_type", "file_path", "simulator_id", "linked_route", "source"])
        has_old = "content" in r
        print(f"  新列存在: {has_new}")
        print(f"  旧 content 列存在: {has_old}")
        if has_new and not has_old:
            print("  ✓ 已迁移到 v2")
        elif has_new and has_old:
            print("  → 迁移进行中（新旧列并存）")
        else:
            print("  → 需要迁移（当前为 v1 schema）")
    else:
        print("  表为空，无需迁移")


def migrate():
    """执行迁移。"""
    from mysql_db_manager import (
        query_all as mq, update as mu,
        execute_raw, _ensure_mysql_tables, _use_mysql,
    )

    rows = mq("sim_json_files")
    if not rows:
        print("表为空，跳过数据迁移。")
        return

    # 检查是否已迁移
    r0 = rows[0]
    if all(k in r0 for k in ["alarm_type", "file_path", "simulator_id", "linked_route", "source"]):
        print("新列已存在，仅更新元数据...")
    else:
        print(f"添加新列到 {len(rows)} 条记录...")
        # MySQL ALTER TABLE 添加新列
        if _use_mysql():
            alter_sql = """
                ALTER TABLE `sim_json_files`
                ADD COLUMN IF NOT EXISTS `alarm_type` VARCHAR(64) DEFAULT '' COMMENT '告警类型',
                ADD COLUMN IF NOT EXISTS `file_path` VARCHAR(1024) DEFAULT '' COMMENT '本地文件路径',
                ADD COLUMN IF NOT EXISTS `simulator_id` VARCHAR(128) DEFAULT '' COMMENT '模拟器ID',
                ADD COLUMN IF NOT EXISTS `linked_route` VARCHAR(256) DEFAULT '' COMMENT '关联航线',
                ADD COLUMN IF NOT EXISTS `source` VARCHAR(32) DEFAULT 'manual' COMMENT '来源'
            """
            # MySQL doesn't support IF NOT EXISTS for columns, try one by one
            import time as _time
            for col_name, mysql_def, sqlite_def in [
                ("alarm_type", "VARCHAR(64) DEFAULT ''", "TEXT DEFAULT ''"),
                ("file_path", "VARCHAR(1024) DEFAULT ''", "TEXT DEFAULT ''"),
                ("simulator_id", "VARCHAR(128) DEFAULT ''", "TEXT DEFAULT ''"),
                ("linked_route", "VARCHAR(256) DEFAULT ''", "TEXT DEFAULT ''"),
                ("source", "VARCHAR(32) DEFAULT 'manual'", "TEXT DEFAULT 'manual'"),
            ]:
                try:
                    if _use_mysql():
                        sql = f"ALTER TABLE `sim_json_files` ADD COLUMN `{col_name}` {mysql_def}"
                    else:
                        sql = f"ALTER TABLE sim_json_files ADD COLUMN {col_name} {sqlite_def}"
                    execute_raw(sql)
                    print(f"  [OK] added column {col_name}")
                    _time.sleep(0.5)  # small delay between DDL statements
                except Exception as e:
                    err_msg = str(e)
                    if "Duplicate column" in err_msg or "already exists" in err_msg or "duplicate column" in err_msg.lower():
                        print(f"  [SKIP] column {col_name} already exists")
                    else:
                        print(f"  [FAIL] add column {col_name}: {err_msg[:100]}")

    # 2. 数据迁移：将 content 写入磁盘，填充新列
    export_dir = os.path.join(MOCK_DIR, "db_export")
    os.makedirs(export_dir, exist_ok=True)

    migrated = 0
    for row in rows:
        fid = row["id"]
        name = row.get("name", f"file_{fid}.json")
        content = row.get("content", "") or ""
        sample = content[:65536] if content else ""

        # 写入磁盘（仅当有内容且 file_path 为空时）
        fpath = row.get("file_path", "") or ""
        if content and not fpath:
            fpath = os.path.join(export_dir, f"{fid}_{name}")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)

        # 检测元数据
        alarm_type = row.get("alarm_type", "") or _detect_alarm_type(name, sample)
        simulator_id = row.get("simulator_id", "") or _extract_simulator_id(sample)
        linked_route = row.get("linked_route", "") or _detect_linked_route(name, sample)
        source_map = {"manual": "manual", "import": "import", "upload": "upload"}
        source = row.get("source", "") or source_map.get(row.get("created_by", "manual"), "manual")

        update_data = {
            "alarm_type": alarm_type,
            "file_path": fpath,
            "simulator_id": simulator_id,
            "linked_route": linked_route,
            "source": source,
        }

        try:
            mu("sim_json_files", fid, update_data)
            migrated += 1
        except Exception as e:
            print(f"  ✗ 更新记录 {fid} 失败: {e}")

    print(f"\n迁移完成: {migrated}/{len(rows)} 条记录已更新")
    print(f"文件导出目录: {export_dir}")
    print("注意: 旧 content 列保留未删除，确认无误后可手动清理。")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="sim_json_files v1→v2 迁移")
    p.add_argument("--execute", action="store_true", help="执行迁移（不指定则仅检查状态）")
    args = p.parse_args()

    if args.execute:
        migrate()
    else:
        check_status()
        print("\n运行 python database/migrate_schema_v2.py --execute 执行迁移")
