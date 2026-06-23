#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汇总 mock 目录下所有 trajectory_accuracy_report_*.html 航迹预测误差报告，
提取关键指标并生成汇总 HTML 报告。

运行示例:
  python tools/trajectory_accuracy_report_analysis.py
  python tools/trajectory_accuracy_report_analysis.py --mock-dir mock/
"""

from __future__ import annotations

import re
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# mock 数据文件夹路径（指向 utm_moc52_develop/mock）
DEFAULT_MOCK_DIR = Path(__file__).resolve().parent.parent.parent / "utm_moc52_develop" / "mock"


def _escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def parse_html_report(html_path: Path) -> Optional[Dict[str, Any]]:
    """从单个 HTML 报告中提取关键指标。"""
    text = html_path.read_text(encoding="utf-8")

    # 目标飞行器 ID
    uav_match = re.search(r'目标飞行器[：:]\s*([^|]+?)\s*\|', text)
    uav_id = uav_match.group(1).strip() if uav_match else html_path.stem.replace("trajectory_accuracy_report_", "")

    # ADE / FDE（兼容 value 中可能存在 class，如 grade-pass 等）
    ade_match = re.search(
        r'ADE（平均位移误差）</span>\s*<br/>\s*<span\s+class="value[^"]*">\s*([\d.]+)\s*m',
        text, re.IGNORECASE,
    )
    fde_match = re.search(
        r'FDE（终点位移误差）</span>\s*<br/>\s*<span\s+class="value[^"]*">\s*([\d.]+)\s*m',
        text, re.IGNORECASE,
    )
    ade = float(ade_match.group(1)) if ade_match else None
    fde = float(fde_match.group(1)) if fde_match else None

    # 误差指标表（水平 / 垂直 / 3D）——使用 DOTALL 忽略换行差异
    h_match = re.search(
        r'<td>\s*水平误差\s*\(Horizontal\)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>',
        text, re.DOTALL,
    )
    v_match = re.search(
        r'<td>\s*垂直误差\s*\(Vertical\)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>',
        text, re.DOTALL,
    )
    d3_match = re.search(
        r'<td>\s*3D\s*位置误差\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>\s*'
        r'<td>\s*([\d.]+)\s*</td>',
        text, re.DOTALL,
    )

    def to_vals(m: Optional[re.Match]) -> List[Optional[float]]:
        return [float(m.group(i)) for i in range(1, 4)] if m else [None, None, None]

    h_mae, h_rmse, h_max = to_vals(h_match)
    v_mae, v_rmse, v_max = to_vals(v_match)
    d3_mae, d3_rmse, d3_max = to_vals(d3_match)

    return {
        "uav_id": uav_id,
        "ade": ade,
        "fde": fde,
        "horizontal": {"mae": h_mae, "rmse": h_rmse, "max": h_max},
        "vertical": {"mae": v_mae, "rmse": v_rmse, "max": v_max},
        "3d": {"mae": d3_mae, "rmse": d3_rmse, "max": d3_max},
    }


def grade_class_ade(value: float) -> str:
    """ADE 等级颜色（低空无人机通用标准）。"""
    if value < 5:
        return "grade-excellent"
    elif value < 15:
        return "grade-good"
    elif value < 30:
        return "grade-pass"
    else:
        return "grade-fail"


def grade_class_fde(value: float) -> str:
    """FDE 等级颜色（低空无人机通用标准，更严格）。"""
    if value < 3:
        return "grade-excellent"
    elif value < 10:
        return "grade-good"
    elif value < 20:
        return "grade-pass"
    else:
        return "grade-fail"


def grade_label(value: float, ade: bool = True) -> str:
    """返回等级文字标签。"""
    if ade:
        if value < 5:
            return "优秀"
        elif value < 15:
            return "良好"
        elif value < 30:
            return "及格"
        else:
            return "不合格"
    else:
        if value < 3:
            return "优秀"
        elif value < 10:
            return "良好"
        elif value < 20:
            return "及格"
        else:
            return "不合格"


def _fmt(val: Optional[float], digits: int = 3) -> str:
    return f"{val:.{digits}f}" if val is not None else "-"


def build_summary_html(reports: List[Dict[str, Any]], title: str) -> str:
    """生成汇总 HTML 报告。"""
    n = len(reports)

    # 汇总数据行
    rows_html = []
    for idx, r in enumerate(reports, 1):
        ade = r["ade"]
        fde = r["fde"]
        ade_cls = grade_class_ade(ade) if ade is not None else ""
        fde_cls = grade_class_fde(fde) if fde is not None else ""

        rows_html.append(
            f"""      <tr>
        <td>{idx}</td>
        <td>{_escape(r['uav_id'])}</td>
        <td class="{ade_cls}">{_fmt(ade)}</td>
        <td class="{fde_cls}">{_fmt(fde)}</td>
        <td>{_fmt(r['horizontal']['mae'])}</td>
        <td>{_fmt(r['horizontal']['rmse'])}</td>
        <td>{_fmt(r['horizontal']['max'])}</td>
        <td>{_fmt(r['vertical']['mae'])}</td>
        <td>{_fmt(r['vertical']['rmse'])}</td>
        <td>{_fmt(r['vertical']['max'])}</td>
        <td>{_fmt(r['3d']['mae'])}</td>
        <td>{_fmt(r['3d']['rmse'])}</td>
        <td>{_fmt(r['3d']['max'])}</td>
      </tr>"""
        )
    rows_str = "\n".join(rows_html)

    # 统计概览
    valid_ade = [r["ade"] for r in reports if r["ade"] is not None]
    valid_fde = [r["fde"] for r in reports if r["fde"] is not None]
    avg_ade = sum(valid_ade) / len(valid_ade) if valid_ade else None
    avg_fde = sum(valid_fde) / len(valid_fde) if valid_fde else None
    min_ade = min(valid_ade) if valid_ade else None
    max_ade = max(valid_ade) if valid_ade else None
    min_fde = min(valid_fde) if valid_fde else None
    max_fde = max(valid_fde) if valid_fde else None

    avg_ade_cls = grade_class_ade(avg_ade) if avg_ade is not None else ""
    avg_fde_cls = grade_class_fde(avg_fde) if avg_fde is not None else ""

    # 各等级数量统计
    ade_grades = {"优秀": 0, "良好": 0, "及格": 0, "不合格": 0}
    fde_grades = {"优秀": 0, "良好": 0, "及格": 0, "不合格": 0}
    for r in reports:
        if r["ade"] is not None:
            ade_grades[grade_label(r["ade"], ade=True)] += 1
        if r["fde"] is not None:
            fde_grades[grade_label(r["fde"], ade=False)] += 1

    def stat_card(label: str, value: str, cls: str = "") -> str:
        return f'<div class="metric-card"><span class="label">{_escape(label)}</span><br/><span class="value {cls}">{value}</span></div>'

    # 优秀率
    ade_excellent_rate = (ade_grades['优秀'] / n * 100) if n else 0
    fde_excellent_rate = (fde_grades['优秀'] / n * 100) if n else 0
    # 合格率（优秀+良好）
    ade_pass_rate = ((ade_grades['优秀'] + ade_grades['良好']) / n * 100) if n else 0
    fde_pass_rate = ((fde_grades['优秀'] + fde_grades['良好']) / n * 100) if n else 0

    overview_cards = (
        stat_card("总架次", f"{n} 架")
        + stat_card("平均 ADE", f"{_fmt(avg_ade)} m", avg_ade_cls)
        + stat_card("平均 FDE", f"{_fmt(avg_fde)} m", avg_fde_cls)
        + stat_card("ADE 最优", f"{_fmt(min_ade)} m", grade_class_ade(min_ade) if min_ade else "")
        + stat_card("ADE 最差", f"{_fmt(max_ade)} m", grade_class_ade(max_ade) if max_ade else "")
        + stat_card("FDE 最优", f"{_fmt(min_fde)} m", grade_class_fde(min_fde) if min_fde else "")
        + stat_card("FDE 最差", f"{_fmt(max_fde)} m", grade_class_fde(max_fde) if max_fde else "")
        + stat_card("ADE 优秀率", f"{ade_excellent_rate:.1f}%", "grade-excellent" if ade_excellent_rate > 0 else "")
        + stat_card("FDE 优秀率", f"{fde_excellent_rate:.1f}%", "grade-excellent" if fde_excellent_rate > 0 else "")
        + stat_card("ADE 合格率", f"{ade_pass_rate:.1f}%", "grade-good" if ade_pass_rate >= 50 else "grade-pass")
        + stat_card("FDE 合格率", f"{fde_pass_rate:.1f}%", "grade-good" if fde_pass_rate >= 50 else "grade-pass")
    )

    def pct(cnt: int) -> str:
        return f"{cnt / n * 100:.1f}%" if n else "-"

    grade_dist_html = f"""
    <div style="margin-top: 12px;">
      <table class="grade-ref">
        <thead>
          <tr><th>等级</th><th>ADE 数量</th><th>ADE 占比</th><th>FDE 数量</th><th>FDE 占比</th></tr>
        </thead>
        <tbody>
          <tr><td class="grade-excellent">优秀</td><td>{ade_grades['优秀']}</td><td class="grade-excellent">{pct(ade_grades['优秀'])}</td><td>{fde_grades['优秀']}</td><td class="grade-excellent">{pct(fde_grades['优秀'])}</td></tr>
          <tr><td class="grade-good">良好</td><td>{ade_grades['良好']}</td><td class="grade-good">{pct(ade_grades['良好'])}</td><td>{fde_grades['良好']}</td><td class="grade-good">{pct(fde_grades['良好'])}</td></tr>
          <tr><td class="grade-pass">及格</td><td>{ade_grades['及格']}</td><td class="grade-pass">{pct(ade_grades['及格'])}</td><td>{fde_grades['及格']}</td><td class="grade-pass">{pct(fde_grades['及格'])}</td></tr>
          <tr><td class="grade-fail">不合格</td><td>{ade_grades['不合格']}</td><td class="grade-fail">{pct(ade_grades['不合格'])}</td><td>{fde_grades['不合格']}</td><td class="grade-fail">{pct(fde_grades['不合格'])}</td></tr>
        </tbody>
      </table>
      <div class="grade-desc">
        <p><span class="grade-excellent">优秀</span>：满足绝大多数低空精细管控需求</p>
        <p><span class="grade-good">良好</span>：可满足常规空管监视，但精细避让场景可能不足</p>
        <p><span class="grade-pass">及格</span>：仅能满足粗粒度监控，需结合其他手段</p>
        <p><span class="grade-fail">不合格</span>：存在较大安全隐患，需优化算法</p>
      </div>
    </div>
    """


    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_escape(title)}</title>
  <style>
    :root {{ font-family: system-ui, "Segoe UI", sans-serif; background: #0f1419; color: #e6edf3; }}
    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-track {{ background: #161b22; }}
    ::-webkit-scrollbar-thumb {{ background: #30363d; border-radius: 6px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #484f58; }}
    body {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 8px; color: #58a6ff; }}
    .meta {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 24px; }}
    section {{ margin-bottom: 32px; }}
    section h2 {{ font-size: 1.1rem; color: #79c0ff; margin-bottom: 12px; border-bottom: 1px solid #30363d; padding-bottom: 6px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
    th, td {{ border: 1px solid #30363d; padding: 8px 10px; text-align: center; white-space: nowrap; }}
    th {{ background: #161b22; color: #58a6ff; }}
    tr:nth-child(even) {{ background: #161b22; }}
    tr:hover {{ background: #1f2933; }}
    td:first-child, td:nth-child(2) {{ text-align: left; }}
    .metric-card {{ display: inline-block; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px 18px; margin: 0 12px 12px 0; min-width: 100px; text-align: center; }}
    .metric-card .value {{ font-size: 1.4rem; font-weight: 600; color: #58a6ff; }}
    .metric-card .label {{ font-size: 0.8rem; color: #8b949e; }}
    .tbl-wrap {{ overflow-x: auto; max-height: 520px; overflow-y: auto; border: 1px solid #30363d; border-radius: 8px; }}
    .tbl-wrap::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    .grade-ref {{ margin-top: 16px; font-size: 0.75rem; width: 100%; }}
    .grade-ref th {{ color: #c9d1d9; }}
    .grade-excellent {{ color: #3fb950; font-weight: 600; }}
    .grade-good {{ color: #58a6ff; font-weight: 600; }}
    .grade-pass {{ color: #d29922; font-weight: 600; }}
    .grade-fail {{ color: #f85149; font-weight: 600; }}
    .metric-card .value.grade-excellent {{ color: #3fb950; }}
    .metric-card .value.grade-good {{ color: #58a6ff; }}
    .metric-card .value.grade-pass {{ color: #d29922; }}
    .metric-card .value.grade-fail {{ color: #f85149; }}
    .grade-desc {{ margin-top: 10px; font-size: 0.75rem; color: #8b949e; line-height: 1.6; }}
    .grade-desc p {{ margin: 4px 0; }}
    .group-header {{ background: #1c2128; color: #79c0ff; font-weight: 600; }}
  </style>
</head>
<body>
  <h1>{_escape(title)}</h1>
  <p class="meta">生成时间：2026-05-14 | 参与汇总无人机：{n} 架 | 数据来源：mock 目录下单机航迹预测误差报告</p>

  <section>
    <h2>统计概览</h2>
    {overview_cards}
    {grade_dist_html}
  </section>

  <section>
    <h2>轨迹精度汇总表</h2>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th rowspan="2">序号</th>
            <th rowspan="2">目标飞行器</th>
            <th rowspan="2">ADE<br/>(m)</th>
            <th rowspan="2">FDE<br/>(m)</th>
            <th colspan="3" class="group-header">水平误差 (m)</th>
            <th colspan="3" class="group-header">垂直误差 (m)</th>
            <th colspan="3" class="group-header">3D 位置误差 (m)</th>
          </tr>
          <tr>
            <th>MAE</th><th>RMSE</th><th>Max</th>
            <th>MAE</th><th>RMSE</th><th>Max</th>
            <th>MAE</th><th>RMSE</th><th>Max</th>
          </tr>
        </thead>
        <tbody>
{rows_str}
        </tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>等级评判标准（参考）</h2>
    <table class="grade-ref">
      <thead>
        <tr><th>等级</th><th>ADE 标准（平均位移误差）</th><th>FDE 标准（终点位移误差）</th></tr>
      </thead>
      <tbody>
        <tr><td class="grade-excellent">优秀</td><td>&lt; 5 m</td><td>&lt; 3 m</td></tr>
        <tr><td class="grade-good">良好</td><td>5 ~ 15 m</td><td>3 ~ 10 m</td></tr>
        <tr><td class="grade-pass">及格</td><td>15 ~ 30 m</td><td>10 ~ 20 m</td></tr>
        <tr><td class="grade-fail">不合格</td><td>&gt; 30 m</td><td>&gt; 20 m</td></tr>
      </tbody>
    </table>
    <div class="grade-desc">
      <p><strong>标准说明</strong>：上述阈值参考低空无人机航迹预测通用行业标准设定。ADE 反映整条轨迹的整体预测精度；FDE 反映航迹终点的到达精度。在低空空管场景中，终点通常涉及降落、航线终点到达等关键操作，因此 <strong>FDE 的合格阈值比 ADE 更严格</strong>。</p>
    </div>
  </section>
</body>
</html>"""


def get_next_version_path(mock_dir: Path, date_str: str, count: int) -> Path:
    """自动迭代版本号 001 → 002 …"""
    for ver in range(1, 1000):
        name = f"{date_str}_{count}架模拟器轨迹精度报告汇总_{ver:03d}.html"
        path = mock_dir / name
        if not path.exists():
            return path
    raise RuntimeError("版本号超过 999，请清理旧汇总报告")


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总航迹预测误差 HTML 报告")
    parser.add_argument(
        "--mock-dir",
        type=Path,
        default=DEFAULT_MOCK_DIR,
        help="存放单机 HTML 报告的目录（默认: mock/）",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="20260514",
        help="报告日期前缀（默认: 20260514）",
    )
    args = parser.parse_args()

    mock_dir: Path = args.mock_dir
    if not mock_dir.exists():
        raise SystemExit(f"目录不存在: {mock_dir}")

    # 查找所有单机报告（排除已生成的汇总报告）
    report_files: List[Path] = sorted(
        p for p in mock_dir.glob("trajectory_accuracy_report_*.html")
        if "汇总" not in p.name
    )

    if not report_files:
        raise SystemExit(f"在 {mock_dir} 中未找到 trajectory_accuracy_report_*.html 报告文件")

    reports: List[Dict[str, Any]] = []
    for f in report_files:
        data = parse_html_report(f)
        if data is not None:
            reports.append(data)
            print(f"  ✔ 已解析: {f.name} → {data['uav_id']}")
        else:
            print(f"  ✗ 解析失败: {f.name}")

    if not reports:
        raise SystemExit("未能从任何报告中提取到有效数据")

    count = len(reports)
    out_path = get_next_version_path(mock_dir, args.date, count)
    html_content = build_summary_html(reports, out_path.stem)
    out_path.write_text(html_content, encoding="utf-8")
    print(f"\n汇总报告已生成: {out_path}")


if __name__ == "__main__":
    main()
