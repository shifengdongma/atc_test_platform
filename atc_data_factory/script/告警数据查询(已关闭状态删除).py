#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警数据查询脚本

查询 alert 表每日数据量及状态分布，输出格式：
    日期  当天总量  已解除关闭  关闭  删除数量

结果保存至 ../test_data/告警数量_YYYYMMDD_HHMMSS.txt，
并与历史文件比对，输出删除统计。
"""

import sys
import os
import glob
from datetime import datetime

# 将当前目录加入路径，确保能导入 dmdbclient
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dmdbclient import DmDbClient

# ── 路径常量 ──────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DATA_DIR = os.path.join(SCRIPT_DIR, "..", "test_data")


def _display_width(s):
    """计算字符串在等宽终端中的显示宽度（ASCII 占 1，中文等 CJK 占 2）。"""
    w = 0
    for ch in str(s):
        if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' or '\uff00' <= ch <= '\uffef':
            w += 2
        else:
            w += 1
    return w


def _ljust_width(s, width):
    """左对齐到指定显示宽度。"""
    pad = width - _display_width(s)
    return str(s) + ' ' * max(pad, 0)


def _rjust_width(s, width):
    """右对齐到指定显示宽度。"""
    pad = width - _display_width(s)
    return ' ' * max(pad, 0) + str(s)


def query_alert_daily_stats():
    """按日期统计告警数据总量与删除数量。"""
    client = DmDbClient()

    if not client.connect():
        print("[错误] 数据库连接失败")
        return

    try:
        # 达梦 SQL：按 create_date 日期分组统计
        sql = """
        SELECT
            TO_CHAR(create_date, 'YYYY-MM-DD') AS stat_date,
            COUNT(*) AS total_count,
            SUM(CASE WHEN is_deleted = 1 THEN 1 ELSE 0 END) AS deleted_count,
            SUM(CASE WHEN status = '5' THEN 1 ELSE 0 END) AS resolved_count,
            SUM(CASE WHEN status = '6' THEN 1 ELSE 0 END) AS closed_count
        FROM ATC_DKWRJ_TEST.alert
        WHERE create_date IS NOT NULL
        GROUP BY TO_CHAR(create_date, 'YYYY-MM-DD')
        ORDER BY stat_date
        """

        result = client.execute(sql)

        if not result:
            print("[提示] 未查询到数据")
            return

        # 列显示宽度配置（按终端实际显示宽度计算）
        # 顺序：日期 | 当天总量 | 已解除关闭 | 关闭 | 删除数量（最后一列）
        col_specs = [
            ("日期", 12, _ljust_width),      # 左对齐
            ("当天总量", 10, _rjust_width),
            ("已解除关闭", 10, _rjust_width),
            ("关闭", 8, _rjust_width),
            ("删除数量", 10, _rjust_width),
        ]
        sep = "  "  # 列间间隔

        # 组装输出内容
        lines = []
        header_line = sep.join(fmt(title, width) for title, width, fmt in col_specs)
        lines.append(header_line)
        sep_width = _display_width(header_line)
        lines.append("-" * sep_width)

        # 用于保存的原始数据
        raw_rows = []

        # 输出数据行
        current_data = {}   # 用于历史比对
        sum_total = sum_resolved = sum_closed = sum_deleted = 0
        for row in result:
            stat_date = row.get("STAT_DATE") or row.get("stat_date") or "-"
            total = row.get("TOTAL_COUNT") or row.get("total_count") or 0
            deleted = row.get("DELETED_COUNT") or row.get("deleted_count") or 0
            resolved = row.get("RESOLVED_COUNT") or row.get("resolved_count") or 0
            closed = row.get("CLOSED_COUNT") or row.get("closed_count") or 0

            values = [stat_date, total, resolved, closed, deleted]
            line = sep.join(fmt(str(v), width) for (_, width, fmt), v in zip(col_specs, values))
            lines.append(line)

            raw_rows.append(f"{stat_date},{total},{resolved},{closed},{deleted}")
            current_data[stat_date] = int(total)

            # 累加汇总
            sum_total += int(total)
            sum_resolved += int(resolved)
            sum_closed += int(closed)
            sum_deleted += int(deleted)

        lines.append("-" * sep_width)

        # 汇总行
        summary_values = ["合计", sum_total, sum_resolved, sum_closed, sum_deleted]
        summary_line = sep.join(fmt(str(v), width) for (_, width, fmt), v in zip(col_specs, summary_values))
        lines.append(summary_line)

        lines.append(f"共 {len(result)} 天数据")

        # ── 控制台输出 ─────────────────────────────────────
        for line in lines:
            print(line)

        # ── 保存到文件 ─────────────────────────────────────
        os.makedirs(TEST_DATA_DIR, exist_ok=True)
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"告警数量_{now_str}.txt"
        filepath = os.path.join(TEST_DATA_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n\n[RAW_DATA]\n")
            f.write("\n".join(raw_rows))
        print(f"\n[保存] 结果已写入: {filepath}")

        # ── 历史比对：删除统计 ─────────────────────────────
        _print_delete_stat(current_data)

    except Exception as e:
        print(f"[错误] 查询执行失败: {e}")
    finally:
        client.close()


def _print_delete_stat(current_data):
    """读取 test_data 最新的历史文件，比对并输出删除统计。"""
    pattern = os.path.join(TEST_DATA_DIR, "告警数量_*.txt")
    files = glob.glob(pattern)
    if not files:
        print("[删除统计] 无历史文件，跳过比对")
        return

    # 排除当前刚生成的文件（按修改时间取倒数第二个最新的）
    files.sort(key=os.path.getmtime, reverse=True)
    latest_file = files[0] if len(files) == 1 else files[1]

    # 解析历史 RAW_DATA
    historical = {}
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            content = f.read()
        raw_section = content.split("[RAW_DATA]")[-1]
        for line in raw_section.strip().splitlines():
            if not line.strip():
                continue
            parts = line.strip().split(",")
            if len(parts) >= 2:
                historical[parts[0]] = int(parts[1])
    except Exception as e:
        print(f"[删除统计] 解析历史文件失败: {e}")
        return

    # 比对：历史存在但当前减少或消失的视为删除
    delete_stats = []
    for date, hist_total in historical.items():
        curr_total = current_data.get(date, 0)
        if hist_total > curr_total:
            delete_stats.append((date, hist_total, curr_total, hist_total - curr_total))

    if not delete_stats:
        print("[删除统计] 与上次比对，无新增删除数据")
        return

    print("\n[删除统计] 与历史文件比对结果:")
    print(f"{'日期':<12} {'历史总量':>10} {'当前总量':>10} {'删除数量':>10}")
    print("-" * 46)
    total_deleted = 0
    for date, hist, curr, diff in delete_stats:
        print(f"{date:<12} {hist:>10} {curr:>10} {diff:>10}")
        total_deleted += diff
    print("-" * 46)
    print(f"合计删除: {total_deleted} 条")


if __name__ == "__main__":
    query_alert_daily_stats()
