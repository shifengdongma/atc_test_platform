#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
无人机航迹预测点位准确度计算脚本

根据《航迹预测误差计算方法》：
- 模拟点位：kafka_data.json（真值，含 longitude, latitude, geodeticAltitude, timestamp）
- 预测点位：redis_trace.json（卡尔曼滤波预测，key=uav_runtime_trace_<ts>, value[0] 含 longitude, latitude, altitude, timestamp）
- 按时间戳对齐后，在 ENU 局部坐标系下计算水平/垂直/3D 误差及 ADE、FDE 等指标。

依赖: pip install numpy

运行示例:
  python tools/trajectory_accuracy.py
  python tools/trajectory_accuracy.py --simulated json/kafka_data.json --predicted json/redis_trace.json --output report.json
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path  
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple

try:
    import numpy as np
except ImportError:
    np = None

# mcok 数据文件夹路径，可改为 "json" 等
DEFAULT_JSON_DIR = Path(__file__).resolve().parent.parent / "mock"

# 终端颜色（ANSI，支持 PowerShell / 现代终端）
class _C:
    R = "\033[0m"      # reset
    T = "\033[1;36m"   # 标题 bold cyan
    S = "\033[33m"     # 小节 yellow
    V = "\033[32m"     # 数值 green
    G = "\033[1;32m"   # 成功/写入 bold green
    I = "\033[36m"     # 信息 cyan


@dataclass
class TrajectoryPoint:
    """轨迹点：纬度(度)、经度(度)、高度(米)、时间戳(毫秒)。"""
    lat: float
    lon: float
    alt: float
    timestamp: float = 0.0


# ---- 坐标转换（参考文档）----

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点水平距离（米），Haversine 公式。"""
    R = 6371000  # 地球半径（米）
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return float(R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))


def to_enu(ref: TrajectoryPoint, point: TrajectoryPoint) -> np.ndarray:
    """
    将经纬高转换为以 ref 为原点的 ENU 局部坐标（米）。
    East-North-Up 坐标系，适合小范围（<100km）轨迹。
    """
    R = 6371000
    dlat = np.radians(point.lat - ref.lat)
    dlon = np.radians(point.lon - ref.lon)
    north = R * dlat
    east = R * np.cos(np.radians(ref.lat)) * dlon
    up = point.alt - ref.alt
    return np.array([east, north, up], dtype=float)


# ---- 误差计算（参考文档）----

def compute_errors(
    simulated: List[TrajectoryPoint],
    predicted: List[TrajectoryPoint],
) -> Dict[str, Any]:
    """
    计算模拟点位与预测点位之间的误差。

    Args:
        simulated: 模拟（真值）轨迹点列表
        predicted: 卡尔曼滤波预测轨迹点列表

    Returns:
        包含各项误差指标的字典
    """
    if len(simulated) != len(predicted):
        raise ValueError(f"点位数量必须一致: simulated={len(simulated)}, predicted={len(predicted)}")

    ref = simulated[0]
    sim_enu = np.array([to_enu(ref, p) for p in simulated])   # (N, 3)
    pred_enu = np.array([to_enu(ref, p) for p in predicted])  # (N, 3)
    diff = pred_enu - sim_enu  # (N, 3): [east_err, north_err, up_err]

    horizontal_errors = np.sqrt(diff[:, 0] ** 2 + diff[:, 1] ** 2)
    vertical_errors = np.abs(diff[:, 2])
    errors_3d = np.linalg.norm(diff, axis=1)

    return {
        "horizontal_mae": float(np.mean(horizontal_errors)),
        "horizontal_rmse": float(np.sqrt(np.mean(horizontal_errors ** 2))),
        "horizontal_max": float(np.max(horizontal_errors)),
        "vertical_mae": float(np.mean(vertical_errors)),
        "vertical_rmse": float(np.sqrt(np.mean(vertical_errors ** 2))),
        "vertical_max": float(np.max(vertical_errors)),
        "error_3d_mae": float(np.mean(errors_3d)),
        "error_3d_rmse": float(np.sqrt(np.mean(errors_3d ** 2))),
        "error_3d_max": float(np.max(errors_3d)),
        "ADE": float(np.mean(errors_3d)),
        "FDE": float(errors_3d[-1]),
        "per_point_3d": [float(x) for x in errors_3d],
        "per_point_horizontal": [float(x) for x in horizontal_errors],
        "per_point_vertical": [float(x) for x in vertical_errors],
        "aligned_timestamps_simulated": [float(p.timestamp) for p in simulated],
        "aligned_timestamps_predicted": [float(p.timestamp) for p in predicted],
        "num_points": len(simulated),
    }


# ---- 数据加载与对齐 ----

def load_simulated_raw(path: Path) -> List[Dict[str, Any]]:
    """从 kafka_data.json 加载原始数据（只读一次文件）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        raise ValueError("kafka_data.json 为空")
    return data


def get_unique_product_ids(data: List[Dict[str, Any]]) -> List[str]:
    """从 data 中取出所有不重复的 uniqueProductIdentificationCode，保持首次出现顺序。"""
    seen = set()
    result = []
    for item in data:
        code = item.get("uniqueProductIdentificationCode")
        if code and code not in seen:
            seen.add(code)
            result.append(code)
    if not result:
        raise ValueError("data 中无任何记录包含 uniqueProductIdentificationCode")
    return result


def filter_simulated_points(data: List[Dict[str, Any]], uav_id: str) -> List[TrajectoryPoint]:
    """按 uniqueProductIdentificationCode 过滤 data，转为 TrajectoryPoint 列表。
    若该 uav_id 下首条 timestamp 在 JSON 中为整数（末尾无 .0），则过滤掉所有 timestamp 为浮点数（带 .0）的记录。"""
    # 先筛出该 uav_id 的项，再按首条决定是否丢弃 float 时间戳
    items = [item for item in data if item.get("uniqueProductIdentificationCode") == uav_id]
    if not items:
        return []
    first_ts = items[0].get("timestamp", 0)
    drop_float_ts = isinstance(first_ts, int)
    points = []
    for item in items:
        ts_raw = item.get("timestamp", 0)
        if drop_float_ts and isinstance(ts_raw, float):
            continue
        points.append(TrajectoryPoint(
            lat=float(item["latitude"]),
            lon=float(item["longitude"]),
            alt=float(item.get("geodeticAltitude", 0)),
            timestamp=float(ts_raw),
        ))
    return points


def load_predicted_points(path: Path, uav_id: str) -> List[TrajectoryPoint]:
    """
    从 redis_trace.json 加载预测点位，仅保留指定飞行器（uniqueProductIdentificationCode）的数据。
    redis 中 value 可能包含多架飞行器，按 uav_id 过滤后取匹配项。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    points = []
    for item in data:
        val = item.get("value") or []
        for p in val:
            if p.get("uniqueProductIdentificationCode") != uav_id:
                continue
            ts = float(p.get("timestamp", 0))
            points.append(TrajectoryPoint(
                lat=float(p["latitude"]),
                lon=float(p["longitude"]),
                alt=float(p.get("altitude", 0)),
                timestamp=ts,
            ))
    # 按时间戳排序，与 kafka 对齐时一致
    points.sort(key=lambda x: x.timestamp)
    return points


def align_by_timestamp(
    simulated: List[TrajectoryPoint],
    predicted: List[TrajectoryPoint],
    tolerance_ms: float = 500.0,
) -> Tuple[List[TrajectoryPoint], List[TrajectoryPoint]]:
    """
    按时间戳单调对齐：两边按时间排序后，按顺序配对，保证不出现「早 sim 配晚 pred」的错位。
    对每个模拟点，只在「尚未使用的、且时间不早于上一对」的预测点中找时间差最小的；
    仅当时间差 <= tolerance_ms 时才接受该配对，否则跳过该模拟点。
    这样避免如 1772511407284 -> 1772511423000 这种相差十几秒的错配。
    """
    sim_sorted = sorted(simulated, key=lambda p: p.timestamp)
    pred_sorted = sorted(predicted, key=lambda p: p.timestamp)
    sim_aligned, pred_aligned = [], []
    j_min = 0  # 当前可用的预测点起始下标，保证单调

    for s in sim_sorted:
        best_j, best_dt = None, float("inf")
        for j in range(j_min, len(pred_sorted)):
            dt = abs(pred_sorted[j].timestamp - s.timestamp)
            if dt < best_dt:
                best_dt, best_j = dt, j
        if best_j is not None and best_dt <= tolerance_ms:
            sim_aligned.append(s)
            pred_aligned.append(pred_sorted[best_j])
            j_min = best_j + 1
    return sim_aligned, pred_aligned


# ---- HTML 报告 ----

def _escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html_report(
    errors: Dict[str, Any],
    title: str = "航迹预测误差报告",
    uav_id: str | None = None,
) -> str:
    """根据误差字典生成完整 HTML 报告（含逐点误差表格与 3D 误差曲线图）。"""
    n = errors.get("num_points", 0)
    per_3d = errors.get("per_point_3d") or []
    per_h = errors.get("per_point_horizontal") or []
    per_v = errors.get("per_point_vertical") or []
    ts_sim = errors.get("aligned_timestamps_simulated") or []
    ts_pred = errors.get("aligned_timestamps_predicted") or []

    def row(name: str, mae: float, rmse: float, max_val: float) -> str:
        return f"""
        <tr>
          <td>{_escape(name)}</td>
          <td>{mae:.3f}</td>
          <td>{rmse:.3f}</td>
          <td>{max_val:.3f}</td>
        </tr>"""

    metrics_rows = (
        row("水平误差 (Horizontal)", errors["horizontal_mae"], errors["horizontal_rmse"], errors["horizontal_max"])
        + row("垂直误差 (Vertical)", errors["vertical_mae"], errors["vertical_rmse"], errors["vertical_max"])
        + row("3D 位置误差", errors["error_3d_mae"], errors["error_3d_rmse"], errors["error_3d_max"])
    )

    # 逐点表格：全部展示（序号、时间戳 kafka->redis、3D/水平/垂直误差）
    table_rows = []
    for i in range(len(per_3d)):
        s = ts_sim[i] if i < len(ts_sim) else ""
        p = ts_pred[i] if i < len(ts_pred) else ""
        s_str = f"{s:.0f}" if isinstance(s, (int, float)) else str(s)
        p_str = f"{p:.0f}" if isinstance(p, (int, float)) else str(p)
        ts_str = f"{s_str} -> {p_str}"
        table_rows.append(
            f"<tr><td>{i + 1}</td><td>{_escape(ts_str)}</td><td>{per_3d[i]:.4f}</td><td>{per_h[i]:.4f}</td><td>{per_v[i]:.4f}</td></tr>"
        )
    table_body = "\n".join(table_rows)

    # 简单 SVG 折线图：3D 误差随点序变化（最多 300 个点采样）
    chart_points = 300
    if per_3d:
        step = max(1, len(per_3d) // chart_points)
        sampled = [per_3d[i] for i in range(0, len(per_3d), step)]
        max_err = max(sampled) or 1
        w, h = 800, 220
        pad = 40
        xs = [pad + (w - 2 * pad) * i / (len(sampled) - 1) if len(sampled) > 1 else pad + (w - 2 * pad) / 2 for i in range(len(sampled))]
        ys = [h - pad - (h - 2 * pad) * (v / max_err) for v in sampled]
        path_d = " ".join(f"{'L' if i else 'M'} {x:.1f} {y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
        chart_svg = f"""
        <svg class="chart" viewBox="0 0 {w} {h}" width="100%" height="220">
          <text x="{pad}" y="20" class="chart-title">逐点 3D 误差 (m)</text>
          <line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" class="chart-axis"/>
          <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" class="chart-axis"/>
          <path d="{path_d}" class="chart-line" fill="none"/>
        </svg>"""
    else:
        chart_svg = '<p class="no-data">无逐点数据</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_escape(title)}</title>
  <style>
    :root {{ font-family: system-ui, "Segoe UI", sans-serif; background: #0f1419; color: #e6edf3; }}
    /* 全局滚动条（与深色主题一致，圆角需配合 background-clip + border 生效）*/
    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-track {{ background: #161b22;}}
    ::-webkit-scrollbar-thumb {{
      background: #30363d;
      border-radius: 6px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #484f58;
    }}
    body {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 8px; color: #58a6ff; }}
    .meta {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 24px; }}
    section {{ margin-bottom: 32px; }}
    section h2 {{ font-size: 1.1rem; color: #79c0ff; margin-bottom: 12px; border-bottom: 1px solid #30363d; padding-bottom: 6px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #30363d; padding: 10px 14px; text-align: left; }}
    th {{ background: #161b22; color: #58a6ff; }}
    tr:nth-child(even) {{ background: #161b22; }}
    .metric-card {{ display: inline-block; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px 20px; margin: 0 16px 16px 0; }}
    .metric-card .value {{ font-size: 1.5rem; font-weight: 600; color: #58a6ff; }}
    .metric-card .label {{ font-size: 0.85rem; color: #8b949e; }}
    .chart {{ background: #161b22; border-radius: 8px; border: 1px solid #30363d; }}
    .chart-title {{ font-size: 12px; fill: #8b949e; }}
    .chart-axis {{ stroke: #30363d; stroke-width: 1; }}
    .chart-line {{ stroke: #58a6ff; stroke-width: 2; }}
    .tbl-wrap {{ overflow-x: auto; max-height: 360px; overflow-y: auto; }}
    .tbl-wrap::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    .tbl-wrap table {{ font-size: 0.85rem; }}
    .more {{ color: #8b949e; text-align: center; }}
    .no-data {{ color: #8b949e; }}
  </style>
</head>
<body>
  <h1>{_escape(title)}</h1>
  <p class="meta">目标飞行器：{_escape(uav_id or '-')} | 参与计算点数：{n}（按时间戳对齐后的模拟点与预测点对）</p>

  <section>
    <h2>汇总指标</h2>
    <div class="metric-card"><span class="label">ADE（平均位移误差）</span><br/><span class="value">{errors["ADE"]:.3f} m</span></div>
    <div class="metric-card"><span class="label">FDE（终点位移误差）</span><br/><span class="value">{errors["FDE"]:.3f} m</span></div>
  </section>

  <section>
    <h2>误差指标表</h2>
    <table>
      <thead><tr><th>指标</th><th>MAE (m)</th><th>RMSE (m)</th><th>Max (m)</th></tr></thead>
      <tbody>{metrics_rows}
      </tbody>
    </table>
  </section>

  <section>
    <h2>逐点 3D 误差曲线</h2>
    {chart_svg}
  </section>

  <section>
    <h2>逐点误差明细</h2>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>序号</th><th>时间戳 (kafka_data → redis_trace)</th><th>3D 误差 (m)</th><th>水平误差 (m)</th><th>垂直误差 (m)</th></tr></thead>
        <tbody>
{table_body}
        </tbody>
      </table>
    </div>
  </section>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="无人机航迹预测点位准确度计算")
    parser.add_argument(
        "--simulated",
        type=Path,
        default=DEFAULT_JSON_DIR / "kafka_data.json",
        help="模拟点位 JSON（kafka_data.json）",
    )
    parser.add_argument(
        "--predicted",
        type=Path,
        default=DEFAULT_JSON_DIR / "redis_trace.json",
        help="预测点位 JSON（redis_trace.json）",
    )
    parser.add_argument(
        "--tolerance-ms",
        type=float,
        default=500.0,
        help="时间戳对齐允许误差（毫秒），仅保留时间差不超过该值的配对，避免错位（默认 1000，即 1 秒）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="将完整误差结果写入 JSON 文件（含逐点误差）",
    )
    parser.add_argument(
        "--no-print",
        action="store_true",
        help="不打印报告，仅写文件",
    )
    default_html = DEFAULT_JSON_DIR / "trajectory_accuracy_report.html"
    parser.add_argument(
        "--html",
        type=Path,
        default=default_html,
        help=f"将报告输出为 HTML 文件（默认: {default_html}），传 '' 可禁用",
    )
    args = parser.parse_args()

    if np is None:
        raise SystemExit("请安装 numpy: pip install numpy")

    # 只读一次 kafka 文件，取出所有 uniqueProductIdentificationCode，按每个 code 过滤并生成报告
    simulated_raw = load_simulated_raw(args.simulated)
    unique_ids = get_unique_product_ids(simulated_raw)
    print(f"{_C.I}检测到 {len(unique_ids)} 个飞行器: {unique_ids}{_C.R}")

    for uav_id in unique_ids:
        simulated = filter_simulated_points(simulated_raw, uav_id)
        print(f"{_C.I}目标飞行器: {uav_id} | 模拟点 {len(simulated)} 个{_C.R}")
        predicted = load_predicted_points(args.predicted, uav_id=uav_id)
        print(f"{_C.I}已加载: 预测点 {len(predicted)} 个（已过滤）{_C.R}")

        sim_aligned, pred_aligned = align_by_timestamp(
            simulated, predicted, tolerance_ms=args.tolerance_ms
        )
        if not sim_aligned:
            print(f"{_C.I}  {uav_id}: 按时间戳对齐后无共同点位，跳过报告{_C.R}")
            continue
        print(f"{_C.I}按时间戳对齐后: {len(sim_aligned)} 对点位{_C.R}")

        errors = compute_errors(sim_aligned, pred_aligned)

        if not args.no_print:
            print(f"\n{_C.T}=== 航迹预测误差报告 [{uav_id}] ==={_C.R}")
            print(f"  点数: {_C.V}{errors['num_points']}{_C.R}")
            print(f"  {_C.S}水平误差 (Horizontal){_C.R}")
            print(f"    MAE:   {_C.V}{errors['horizontal_mae']:.3f} m{_C.R}")
            print(f"    RMSE:  {_C.V}{errors['horizontal_rmse']:.3f} m{_C.R}")
            print(f"    Max:   {_C.V}{errors['horizontal_max']:.3f} m{_C.R}")
            print(f"  {_C.S}垂直误差 (Vertical){_C.R}")
            print(f"    MAE:   {_C.V}{errors['vertical_mae']:.3f} m{_C.R}")
            print(f"    RMSE:  {_C.V}{errors['vertical_rmse']:.3f} m{_C.R}")
            print(f"    Max:   {_C.V}{errors['vertical_max']:.3f} m{_C.R}")
            print(f"  {_C.S}3D 位置误差{_C.R}")
            print(f"    MAE:   {_C.V}{errors['error_3d_mae']:.3f} m{_C.R}")
            print(f"    RMSE:  {_C.V}{errors['error_3d_rmse']:.3f} m{_C.R}")
            print(f"    Max:   {_C.V}{errors['error_3d_max']:.3f} m{_C.R}")
            print(f"  {_C.S}轨迹级指标{_C.R}")
            print(f"    ADE (平均位移误差): {_C.V}{errors['ADE']:.3f} m{_C.R}")
            print(f"    FDE (终点位移误差): {_C.V}{errors['FDE']:.3f} m{_C.R}")

        # 多飞行器时输出文件名带 _<uav_id>，单飞行器时保持原文件名
        suffix_json = "_" + uav_id + ".json" if len(unique_ids) > 1 else ""
        suffix_html = "_" + uav_id + ".html" if len(unique_ids) > 1 else ""

        out_path = args.output
        if out_path is not None:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if suffix_json:
                out_path = out_path.parent / (out_path.stem + suffix_json)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(errors, f, ensure_ascii=False, indent=2)
            print(f"\n{_C.G}完整结果已写入: {out_path}{_C.R}")

        html_path = args.html
        if html_path is not None and str(html_path).strip():
            html_path = Path(html_path)
            html_path.parent.mkdir(parents=True, exist_ok=True)
            if suffix_html:
                html_path = html_path.parent / (html_path.stem + suffix_html)
            html_content = build_html_report(errors, uav_id=uav_id)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"{_C.G}HTML 报告已写入: {html_path}{_C.R}")


if __name__ == "__main__":
    main()
