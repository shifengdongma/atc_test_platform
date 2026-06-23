#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
达梦数据库 A/B 双集群数据一致性检查脚本
支持单表时间范围查询与多表总量对比
配置源统一从 ha_env.py 获取
"""

import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dm_ha_client import DmDbClient, DB_CONFIG_A, DB_CONFIG_B


class TeeLogger:
    """同时输出到控制台和日志文件"""

    def __init__(self, filepath, encoding="utf-8"):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding=encoding, buffering=1)

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


# ==================== 场景开关与参数配置区域 ====================
# 场景开关（True 开启，False 关闭）
SCENE_SINGLE = True   # 场景1：单表查询（按时间范围）
SCENE_MULTI = True    # 场景2：多表查询（总量对比）

# --- 场景1：单表查询配置 ---
SINGLE_TABLE = "uav_info"           # 单表查询的表名
TIME_FIELD = "CREATED_TIME"          # 时间字段名（根据实际表结构调整，如 GMT_CREATE、UPDATE_TIME 等）
TIME_MODE = "range"                 # 时间模式："today"=当天，"range"=指定时间范围
# TIME_MODE = "range" 时生效：
START_TIME = "2026-06-01 00:00:00"  # 起始时间（格式：YYYY-MM-DD HH:MM:SS）
END_TIME = "2026-06-10 23:59:59"    # 结束时间（格式：YYYY-MM-DD HH:MM:SS）

# --- 场景1增强：逐条创建时间精细比对（按唯一字段逐条比对 CREATED_TIME，计算毫秒差值）---
DETAIL_TIME_CHECK = True            # 是否开启逐条精细比对
UNIQUE_FIELD = "IDENTIFY_CODE"       # 唯一标识字段名
BATCH_SIZE = 1000                   # 分页批次大小，控制单次查询数据量，减轻数据库压力
DETAIL_TIME_SLEEP = 0.5             # 每批查询间隔（秒），降低对业务数据库的连续冲击

# --- 场景2：多表查询配置 ---
MULTI_TABLES = [
    "uav_info",
    "flight_task",
    "air_route",
    "alert",
    "flight_plan",
    "flight_task",
    "seat", #坐席
    "users",    #用户
    "sector",   #扇区
    "operation_organization",     #运营组织
    "operation_people",   #运营人
    # 按需添加更多表名
]

# 场景2时间范围配置（与场景1独立，设为 None 表示不限制时间）
MULTI_TIME_FIELD = "CREATED_TIME"       # 多表查询共用的时间字段，None 表示不按时间过滤
MULTI_TIME_MODE = "range"               # "today"=当天，"range"=指定范围，None=全量
MULTI_START_TIME = "2026-06-11 00:00:00"
MULTI_END_TIME = "2026-06-11 23:59:59"
# =============================================================


def get_count_sql(table_name, schema, time_field=None, time_mode="today", start_time=None, end_time=None):
    """构建带时间条件的 COUNT 查询 SQL

    Args:
        table_name (str): 表名
        schema (str): 模式名
        time_field (str, optional): 时间字段名
        time_mode (str): "today" 或 "range"
        start_time (str): 范围起始时间
        end_time (str): 范围结束时间

    Returns:
        str: SQL 语句
    """
    sql = f"SELECT COUNT(*) AS TOTAL FROM {schema}.{table_name}"
    if time_field:
        if time_mode == "today":
            # 达梦：当天数据（TRUNC 截断到日期）
            where = (
                f"{time_field} >= TRUNC(SYSDATE) "
                f"AND {time_field} < TRUNC(SYSDATE) + 1"
            )
        elif time_mode == "range":
            # 达梦：指定时间范围（字符串转日期比较）
            where = (
                f"{time_field} >= TO_DATE('{start_time}', 'YYYY-MM-DD HH24:MI:SS') "
                f"AND {time_field} <= TO_DATE('{end_time}', 'YYYY-MM-DD HH24:MI:SS')"
            )
        else:
            where = None
        if where:
            sql += f" WHERE {where}"
    return sql


def fetch_count(client, sql):
    """执行 COUNT 查询并返回数值

    Args:
        client (DmDbClient): 数据库客户端
        sql (str): COUNT 查询 SQL

    Returns:
        int: 数据总量，查询失败返回 -1
    """
    result = client.execute(sql, silent=True)
    if result and len(result) > 0:
        total = result[0].get("TOTAL", 0)
        return int(total) if total is not None else 0
    return -1


def fetch_min_max_time(client, table_name, schema, time_field, time_mode="today", start_time=None, end_time=None):
    """查询指定时间范围内的最早和最晚创建时间

    Returns:
        tuple: (最早时间str, 最晚时间str)，查询失败返回 (None, None)
    """
    where_clauses = []
    if time_mode == "today":
        where_clauses.append(
            f"{time_field} >= TRUNC(SYSDATE) AND {time_field} < TRUNC(SYSDATE) + 1"
        )
    elif time_mode == "range":
        where_clauses.append(
            f"{time_field} >= TO_DATE('{start_time}', 'YYYY-MM-DD HH24:MI:SS')"
        )
        where_clauses.append(
            f"{time_field} <= TO_DATE('{end_time}', 'YYYY-MM-DD HH24:MI:SS')"
        )

    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = (
        f"SELECT MIN({time_field}) AS MIN_TIME, MAX({time_field}) AS MAX_TIME "
        f"FROM {schema}.{table_name} {where_str}"
    )
    result = client.execute(sql, silent=True)
    if result and len(result) > 0:
        min_time = result[0].get("MIN_TIME")
        max_time = result[0].get("MAX_TIME")
        # 达梦返回的日期对象转字符串
        if min_time is not None:
            min_time = str(min_time)
        if max_time is not None:
            max_time = str(max_time)
        return min_time, max_time
    return None, None


def check_consistency(count_a, count_b):
    """判断两库数据数量是否一致

    Returns:
        str: "一致" / "不一致" / "查询异常"
    """
    if count_a == -1 or count_b == -1:
        return "查询异常"
    return "一致" if count_a == count_b else "不一致"


def check_time_consistency(min_a, max_a, min_b, max_b):
    """判断两库创建时间范围是否一致

    Returns:
        str: "一致" / "不一致" / "查询异常" / "无数据"
    """
    if min_a is None or min_b is None:
        if min_a is None and min_b is None:
            return "无数据"
        return "不一致"
    return "一致" if (str(min_a) == str(min_b) and str(max_a) == str(max_b)) else "不一致"


def _build_where_time(time_field, time_mode, start_time, end_time):
    """构建时间范围 WHERE 子句（用于分页查询）"""
    clauses = []
    if time_mode == "today":
        clauses.append(f"{time_field} >= TRUNC(SYSDATE)")
        clauses.append(f"{time_field} < TRUNC(SYSDATE) + 1")
    elif time_mode == "range":
        clauses.append(f"{time_field} >= TO_DATE('{start_time}', 'YYYY-MM-DD HH24:MI:SS')")
        clauses.append(f"{time_field} <= TO_DATE('{end_time}', 'YYYY-MM-DD HH24:MI:SS')")
    return " AND ".join(clauses) if clauses else ""


def _to_datetime(value):
    """将达梦返回的日期值统一转为 datetime 对象"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # 尝试解析字符串格式
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def fetch_batch_data(client, table_name, schema, unique_field, time_field,
                     time_mode, start_time, end_time, batch_size, offset):
    """分页查询指定范围内的唯一字段和时间字段

    Returns:
        list[dict]: 每条记录包含 unique_field 和 time_field
    """
    where_str = _build_where_time(time_field, time_mode, start_time, end_time)
    where_clause = f"WHERE {where_str}" if where_str else ""

    # 达梦分页：使用 ROWNUM 经典三层嵌套
    sql = (
        f"SELECT * FROM ("
        f"  SELECT t.*, ROWNUM rn FROM ("
        f"    SELECT {unique_field}, {time_field} FROM {schema}.{table_name} "
        f"    {where_clause} ORDER BY {unique_field}"
        f"  ) t WHERE ROWNUM <= {offset + batch_size}"
        f") WHERE rn > {offset}"
    )
    result = client.execute(sql, silent=True)
    return result if result else []


def run_detail_time_check(client_a, client_b):
    """逐条 IDENTIFY_CODE 的 CREATED_TIME 精细比对（含毫秒差值统计）"""
    import time

    print("\n" + "=" * 100)
    print(
        f"【场景1-增强】逐条创建时间精细比对 — 表: {SINGLE_TABLE} | "
        f"唯一字段: {UNIQUE_FIELD} | 时间字段: {TIME_FIELD} | 批次: {BATCH_SIZE}"
    )
    print("=" * 100)

    # 1. 查询总数
    count_sql_a = get_count_sql(SINGLE_TABLE, client_a.schema, TIME_FIELD, TIME_MODE, START_TIME, END_TIME)
    count_sql_b = get_count_sql(SINGLE_TABLE, client_b.schema, TIME_FIELD, TIME_MODE, START_TIME, END_TIME)
    total_a = fetch_count(client_a, count_sql_a)
    total_b = fetch_count(client_b, count_sql_b)

    print(f"[INFO] A库符合条件的记录数: {total_a}")
    print(f"[INFO] B库符合条件的记录数: {total_b}")

    if total_a == -1 or total_b == -1:
        print("[ERROR] 查询总数失败，跳过精细比对")
        return

    max_total = max(total_a, total_b)
    if max_total == 0:
        print("[INFO] 两库均无数据，无需比对")
        return

    # 2. 分页拉取并比对
    all_diffs = []          # 所有匹配记录的毫秒差值（绝对值）
    match_count = 0         # A/B 均存在且时间可解析的记录数
    only_in_a = 0           # 仅 A 库存在
    only_in_b = 0           # 仅 B 库存在
    parse_error = 0         # 时间解析失败数

    offset = 0
    processed = 0

    print(f"[INFO] 开始分页拉取比对，每批 {BATCH_SIZE} 条，间隔 {DETAIL_TIME_SLEEP}s...")

    while processed < max_total:
        # 拉取 A 库本批数据
        rows_a = fetch_batch_data(
            client_a, SINGLE_TABLE, client_a.schema,
            UNIQUE_FIELD, TIME_FIELD, TIME_MODE, START_TIME, END_TIME,
            BATCH_SIZE, offset
        )
        # 拉取 B 库本批数据
        rows_b = fetch_batch_data(
            client_b, SINGLE_TABLE, client_b.schema,
            UNIQUE_FIELD, TIME_FIELD, TIME_MODE, START_TIME, END_TIME,
            BATCH_SIZE, offset
        )

        if not rows_a and not rows_b:
            break

        # B 库数据建索引字典
        dict_b = {}
        for row in rows_b:
            key = row.get(UNIQUE_FIELD)
            if key is not None:
                dict_b[key] = row.get(TIME_FIELD)

        # 遍历 A 库数据，与 B 库匹配
        for row in rows_a:
            key = row.get(UNIQUE_FIELD)
            time_a_val = row.get(TIME_FIELD)
            time_b_val = dict_b.pop(key, None)

            if time_b_val is None:
                only_in_a += 1
                continue

            dt_a = _to_datetime(time_a_val)
            dt_b = _to_datetime(time_b_val)

            if dt_a is None or dt_b is None:
                parse_error += 1
                continue

            diff_ms = abs(int((dt_a - dt_b).total_seconds() * 1000))
            all_diffs.append(diff_ms)
            match_count += 1

        # dict_b 中剩余即为仅 B 库存在
        only_in_b += len(dict_b)

        processed += max(len(rows_a), len(rows_b))
        offset += BATCH_SIZE
        print(f"[PROGRESS] 已处理约 {min(processed, max_total)} / {max_total} 条...")

        if DETAIL_TIME_SLEEP > 0:
            time.sleep(DETAIL_TIME_SLEEP)

    # 3. 输出统计结果
    print("\n" + "-" * 80)
    print("【逐条创建时间比对结果】")
    print("-" * 80)
    print(f"  匹配记录数（A/B均存在）    : {match_count}")
    print(f"  仅 A 库存在                : {only_in_a}")
    print(f"  仅 B 库存在                : {only_in_b}")
    print(f"  时间解析失败数             : {parse_error}")

    if all_diffs:
        min_diff = min(all_diffs)
        max_diff = max(all_diffs)
        avg_diff = sum(all_diffs) / len(all_diffs)
        # 中位数
        sorted_diffs = sorted(all_diffs)
        mid = len(sorted_diffs) // 2
        median_diff = sorted_diffs[mid] if len(sorted_diffs) % 2 == 1 else (sorted_diffs[mid - 1] + sorted_diffs[mid]) / 2

        print(f"  毫秒差值范围               : {min_diff} ms ~ {max_diff} ms")
        print(f"  平均差值                   : {avg_diff:.2f} ms")
        print(f"  中位数差值                 : {median_diff:.2f} ms")

        # 分布统计
        ranges = [
            (0, 50, "0~50ms"),
            (50, 100, "50~100ms"),
            (100, 500, "100~500ms"),
            (500, 1000, "500ms~1s"),
            (1000, 5000, "1s~5s"),
            (5000, float('inf'), ">5s"),
        ]
        print("  差值分布:")
        for low, high, label in ranges:
            cnt = sum(1 for d in all_diffs if low <= d < high)
            pct = cnt / len(all_diffs) * 100
            bar = "█" * int(pct / 2)
            print(f"    {label:<12} : {cnt:>5} 条 ({pct:>5.1f}%) {bar}")
    else:
        print("  [WARN] 无有效匹配记录，无法计算差值统计")

    print("-" * 80)


def run_single_table_check(client_a, client_b):
    """场景1：单表时间范围数据一致性检查（含数量 + 创建时间比对）"""
    print("\n" + "=" * 120)
    print(f"【场景1】单表查询 — 表名: {SINGLE_TABLE} | 时间字段: {TIME_FIELD} | 模式: {TIME_MODE}")
    print("=" * 120)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 数量查询
    sql_a = get_count_sql(
        SINGLE_TABLE, client_a.schema, TIME_FIELD, TIME_MODE, START_TIME, END_TIME
    )
    sql_b = get_count_sql(
        SINGLE_TABLE, client_b.schema, TIME_FIELD, TIME_MODE, START_TIME, END_TIME
    )

    count_a = fetch_count(client_a, sql_a)
    count_b = fetch_count(client_b, sql_b)
    count_status = check_consistency(count_a, count_b)

    # 创建时间范围查询
    min_a, max_a = fetch_min_max_time(
        client_a, SINGLE_TABLE, client_a.schema, TIME_FIELD, TIME_MODE, START_TIME, END_TIME
    )
    min_b, max_b = fetch_min_max_time(
        client_b, SINGLE_TABLE, client_b.schema, TIME_FIELD, TIME_MODE, START_TIME, END_TIME
    )
    time_status = check_time_consistency(min_a, max_a, min_b, max_b)

    # 表头
    header = (
        f"{'日期时分秒':<22} {'数据库A地址':<16} {'A总量':<8} {'B总量':<8} "
        f"{'数量一致性':<10} {'A最早创建时间':<22} {'A最晚创建时间':<22} "
        f"{'B最早创建时间':<22} {'B最晚创建时间':<22} {'创建时间一致性'}"
    )
    print(header)
    print("-" * 170)
    print(
        f"{now_str:<22} {client_a.host:<16} {count_a:<8} {count_b:<8} "
        f"{count_status:<10} {str(min_a):<22} {str(max_a):<22} "
        f"{str(min_b):<22} {str(max_b):<22} {time_status}"
    )
    print("-" * 170)

    return count_a, count_b, count_status, time_status


def run_multi_table_check(client_a, client_b):
    """场景2：多表总量数据一致性检查"""
    print("\n" + "=" * 80)
    print(f"【场景2】多表查询 — 表列表: {MULTI_TABLES}")
    print("=" * 80)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 时间过滤提示
    if MULTI_TIME_FIELD and MULTI_TIME_MODE:
        print(f"[INFO] 时间过滤启用 — 字段: {MULTI_TIME_FIELD} | 模式: {MULTI_TIME_MODE}")
        if MULTI_TIME_MODE == "range":
            print(f"[INFO] 时间范围: {MULTI_START_TIME} ~ {MULTI_END_TIME}")
    else:
        print("[INFO] 时间过滤未启用 — 全表总量比对")

    print(f"{'日期':<22} {'表名':<20} {'数据库A地址':<18} {'A数据总量':<12} {'数据库B地址':<18} {'B数据总量':<12} {'是否一致'}")
    print("-" * 110)

    total_a = 0
    total_b = 0
    all_consistent = True

    for table in MULTI_TABLES:
        # 根据是否配置时间字段，决定 SQL 构建方式
        if MULTI_TIME_FIELD and MULTI_TIME_MODE:
            sql_a = get_count_sql(
                table, client_a.schema, MULTI_TIME_FIELD,
                MULTI_TIME_MODE, MULTI_START_TIME, MULTI_END_TIME
            )
            sql_b = get_count_sql(
                table, client_b.schema, MULTI_TIME_FIELD,
                MULTI_TIME_MODE, MULTI_START_TIME, MULTI_END_TIME
            )
        else:
            sql_a = f"SELECT COUNT(*) AS TOTAL FROM {client_a.schema}.{table}"
            sql_b = f"SELECT COUNT(*) AS TOTAL FROM {client_b.schema}.{table}"

        count_a = fetch_count(client_a, sql_a)
        count_b = fetch_count(client_b, sql_b)
        status = check_consistency(count_a, count_b)

        if status != "一致":
            all_consistent = False

        total_a += count_a if count_a != -1 else 0
        total_b += count_b if count_b != -1 else 0

        print(
            f"{now_str:<22} {table:<20} {client_a.host:<18} {count_a:<12} "
            f"{client_b.host:<18} {count_b:<12} {status}"
        )

    # 汇总行
    summary_status = "一致" if all_consistent and total_a == total_b else "不一致"
    print("-" * 110)
    print(
        f"{'汇总':<22} {'':<20} {client_a.host:<18} {total_a:<12} "
        f"{client_b.host:<18} {total_b:<12} {summary_status}"
    )
    print("-" * 110)

    return total_a, total_b, summary_status


def main():
    """主入口：根据场景开关执行对应检查，输出同时写入日志文件"""
    # 准备日志目录与文件
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
    os.makedirs(log_dir, exist_ok=True)
    log_filename = f"达梦数据库查询比对_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    log_path = os.path.join(log_dir, log_filename)

    # 重定向 stdout 到 TeeLogger（控制台 + 文件）
    tee = TeeLogger(log_path)
    sys.stdout = tee

    start_time = datetime.now()
    print(f"[执行开始时间] {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print("达梦数据库 A/B 双集群数据一致性检查")
    print(f"A集群: {DB_CONFIG_A['host']}:{DB_CONFIG_A['port']}  模式: {DB_CONFIG_A['schema']}")
    print(f"B集群: {DB_CONFIG_B['host']}:{DB_CONFIG_B['port']}  模式: {DB_CONFIG_B['schema']}")
    print("=" * 80)

    client_a = DmDbClient(**DB_CONFIG_A)
    client_b = DmDbClient(**DB_CONFIG_B)

    connected = True
    if not client_a.connect():
        print(f"[ERROR] A集群数据库连接失败: {DB_CONFIG_A['host']}")
        connected = False
    if not client_b.connect():
        print(f"[ERROR] B集群数据库连接失败: {DB_CONFIG_B['host']}")
        connected = False

    if not connected:
        print("[ERROR] 数据库连接异常，退出检查")
        client_a.close()
        client_b.close()
    else:
        try:
            if SCENE_SINGLE:
                run_single_table_check(client_a, client_b)
                if DETAIL_TIME_CHECK:
                    run_detail_time_check(client_a, client_b)
            else:
                print("\n【场景1】单表查询 — 已关闭（SCENE_SINGLE = False）")

            if SCENE_MULTI:
                run_multi_table_check(client_a, client_b)
            else:
                print("\n【场景2】多表查询 — 已关闭（SCENE_MULTI = False）")
        finally:
            client_a.close()
            client_b.close()
            print("\n[INFO] 数据库连接已全部关闭")

    end_time = datetime.now()
    duration = end_time - start_time
    print(f"\n[执行结束时间] {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[执行耗时] {duration}")
    print(f"[日志文件] {log_path}")

    # 恢复 stdout 并关闭文件
    sys.stdout = tee.terminal
    tee.close()


if __name__ == "__main__":
    main()
