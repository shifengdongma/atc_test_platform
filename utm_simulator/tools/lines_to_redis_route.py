#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 mock/lines.json（任务/航线 API 响应）转为与 mock/redis_route.json 相同的结构，
写入 mock/redis_route_custom.json；随后调用 create_data 生成 mock/redis_route.json 与 mock/kafka_data.json。

仅转换 lineSegments 中 type==2 的航路段；type==3 等区域段跳过（与仿真 routeList 用法一致）。
每条 flightLine 在航路段前增加起始线（departurePointLon/Lat → 首段起点）、
航路段后增加降落线（末段终点 → arrivalPointLon/Lat）；起降点高度按 0m，与航路衔接处取相邻段高度。

可选：--conflict（默认开启）对每条含航路段的 flightLine 各生成一条冲突航线，
与对应基准航线在前半段路径上共用一个枢轴点，绕该点水平旋转一定角度得到。

冲突机 uniqueProductIdentificationCode 由 CONFLICT_UNIQUE_PRODUCT_UID 数组按序取用，
用尽后对每条剩余冲突航线随机生成 ID。
"""

from __future__ import annotations

import argparse
import json
import math
import random
import string
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# 与 tools 下其它脚本一致，保证可 import 同目录的 create_data
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

# 冲突航线机身份：按航线顺序依次使用；与 simulation_core.UAV_IDENTIFIERS 中实名登记对应
# 条数不足时由 _conflict_uid_at 随机生成
CONFLICT_UNIQUE_PRODUCT_UID = [
    "ZKJXVT05F5G6H7J8K990",  # UAS10ZKJXVT0530
    "ZKJXVT05F5G6H7J8K991",  # UAS097H9FSEC401
]


def _random_product_uid() -> str:
    """预置冲突 ID 用尽时生成与业务风格相近的 20 位 product id。"""
    return "ZKJXVT05" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))


def _conflict_uid_at(index: int) -> str:
    """第 index 条冲突航线使用的 Redis key / uniqueProductIdentificationCode。"""
    pool = CONFLICT_UNIQUE_PRODUCT_UID
    if index < len(pool):
        return str(pool[index])
    return _random_product_uid()


def _ms_to_sec(ms: Any) -> float:
    if ms is None:
        return 0.0
    try:
        return float(ms) / 1000.0
    except (TypeError, ValueError):
        return 0.0


def _route_segment(
    sequence: int,
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    start_h: float,
    end_h: float,
    width: float,
    protect_height: float,
) -> Dict[str, Any]:
    """单段航线（type==2）。"""
    return {
        "sequence": sequence,
        "type": 2,
        "segmentStartLon": start_lon,
        "segmentStartLat": start_lat,
        "segmentEndLon": end_lon,
        "segmentEndLat": end_lat,
        "segmentStartHeight": start_h,
        "segmentEndHeight": end_h,
        "segmentProtectHeight": protect_height,
        "segmentProtectHeightType": 1,
        "segmentWidth": width,
    }


def _line_segment_to_route(seg: Dict[str, Any], sequence: int) -> Dict[str, Any]:
    """type==2 航路段 -> redis_route 单段。"""
    return _route_segment(
        sequence,
        float(seg["startPointLon"]),
        float(seg["startPointLat"]),
        float(seg["endPointLon"]),
        float(seg["endPointLat"]),
        float(seg["startPointHeight"]),
        float(seg["endPointHeight"]),
        float(seg.get("width", 100.0)),
        float(seg.get("protectHeight", 50.0)),
    )


def _route_list_from_flight_line(fl: Dict[str, Any]) -> List[Dict[str, Any]]:
    """单条 flightLine：起始线 + type==2 段 + 降落线；无端点航路段则返回 []。"""
    cruise: List[Dict[str, Any]] = []
    for seg in fl.get("lineSegments") or []:
        if seg.get("type") == 2:
            cruise.append(seg)
    if not cruise:
        return []

    first, last = cruise[0], cruise[-1]
    w_first = float(first.get("width", 100.0))
    ph_first = float(first.get("protectHeight", 50.0))
    w_last = float(last.get("width", 100.0))
    ph_last = float(last.get("protectHeight", 50.0))

    dep_lat = fl.get("departurePointLat")
    dep_lon = fl.get("departurePointLon")
    arr_lat = fl.get("arrivalPointLat")
    arr_lon = fl.get("arrivalPointLon")

    block: List[Dict[str, Any]] = []
    if dep_lat is not None and dep_lon is not None:
        block.append(
            _route_segment(
                0,
                float(dep_lon),
                float(dep_lat),
                float(first["startPointLon"]),
                float(first["startPointLat"]),
                0.0,
                float(first["startPointHeight"]),
                w_first,
                ph_first,
            )
        )
    for seg in cruise:
        block.append(_line_segment_to_route(seg, 0))
    if arr_lat is not None and arr_lon is not None:
        block.append(
            _route_segment(
                0,
                float(last["endPointLon"]),
                float(last["endPointLat"]),
                float(arr_lon),
                float(arr_lat),
                float(last["endPointHeight"]),
                0.0,
                w_last,
                ph_last,
            )
        )

    route_list: List[Dict[str, Any]] = []
    for seq, seg in enumerate(block):
        seg["sequence"] = seq
        route_list.append(seg)
    return route_list


def _rotate_lonlat_around_pivot(
    lon: float,
    lat: float,
    pivot_lon: float,
    pivot_lat: float,
    angle_rad: float,
) -> Tuple[float, float]:
    """绕 pivot 在水平面旋转 angle_rad（弧度），局部平面近似。"""
    r_e = 6371000.0
    lat_p = math.radians(pivot_lat)
    dx = r_e * math.cos(lat_p) * math.radians(lon - pivot_lon)
    dy = r_e * math.radians(lat - pivot_lat)
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    dx_r = c * dx - s * dy
    dy_r = s * dx + c * dy
    lat_n = pivot_lat + math.degrees(dy_r / r_e)
    lon_n = pivot_lon + math.degrees(dx_r / (r_e * math.cos(lat_p)))
    return lon_n, lat_n


def _pivot_index_first_half(num_vertices: int) -> int:
    """在前半段路径上取枢轴顶点索引（避免落在首尾端点）。"""
    m = num_vertices
    if m <= 2:
        return 0
    # 约在前 1/4～1/2 路径处，保证落在「前半段」
    hi = max(1, (m - 1) // 2)
    cand = max(1, min(m - 2, m // 3))
    return min(cand, hi)


def _rotate_route_list(route_list: List[Dict[str, Any]], angle_deg: float) -> List[Dict[str, Any]]:
    """
    将整条航线绕「前半段」某一顶点水平旋转，生成冲突航线；与基准线在枢轴处相交。
    """
    n = len(route_list)
    if n == 0:
        return []
    if n < 2:
        return [dict(s) for s in route_list]

    seg0 = route_list[0]
    wps_lonlat: List[Tuple[float, float]] = [
        (float(seg0["segmentStartLon"]), float(seg0["segmentStartLat"]))
    ]
    wps_h: List[float] = [float(seg0["segmentStartHeight"])]
    for seg in route_list:
        wps_lonlat.append((float(seg["segmentEndLon"]), float(seg["segmentEndLat"])))
        wps_h.append(float(seg["segmentEndHeight"]))

    m = len(wps_lonlat)
    pivot_idx = _pivot_index_first_half(m)
    plon, plat = wps_lonlat[pivot_idx]
    angle_rad = math.radians(angle_deg)

    new_lonlat: List[Tuple[float, float]] = []
    for i, (lo, la) in enumerate(wps_lonlat):
        if i == pivot_idx:
            new_lonlat.append((plon, plat))
        else:
            new_lonlat.append(_rotate_lonlat_around_pivot(lo, la, plon, plat, angle_rad))

    out: List[Dict[str, Any]] = []
    for i, seg in enumerate(route_list):
        s = dict(seg)
        s["segmentStartLon"] = new_lonlat[i][0]
        s["segmentStartLat"] = new_lonlat[i][1]
        s["segmentEndLon"] = new_lonlat[i + 1][0]
        s["segmentEndLat"] = new_lonlat[i + 1][1]
        s["segmentStartHeight"] = wps_h[i]
        s["segmentEndHeight"] = wps_h[i + 1]
        s["sequence"] = i
        out.append(s)
    return out


def _period_bounds(result: Dict[str, Any]) -> Tuple[float, float]:
    periods = result.get("periods") or []
    if not periods:
        return 0.0, 0.0
    p0 = periods[0]
    return _ms_to_sec(p0.get("startTime")), _ms_to_sec(p0.get("endTime"))


def _task_id_int(result: Dict[str, Any]) -> int:
    tid = result.get("id")
    if tid is None:
        return 1
    try:
        return int(tid)
    except (TypeError, ValueError):
        return 1


def lines_payload_to_redis_entries(
    lines_root: Dict[str, Any],
    conflict: bool = True,
    conflict_angle_deg: float = 35.0,
) -> List[Dict[str, Any]]:
    """
    解析 lines.json 根对象，返回 [{ \"key\", \"value\" }, ...]。

    每条含 type==2 航路段的 flightLine 生成一条独立航线；与 uavInfos 按下标一一对应
    （第 i 条线对应 uavInfos[i]）。若某条无对应 uav，则该条使用随机 product id。

    conflict 为 True 时，对每条基准航线再追加一条绕枢轴旋转的冲突航线；
    冲突机 ID 依次取 CONFLICT_UNIQUE_PRODUCT_UID，用尽后每条剩余冲突航线随机生成。
    """
    result = lines_root.get("result")
    if not isinstance(result, dict):
        raise ValueError("lines.json 缺少 result 对象")

    per_line_routes: List[List[Dict[str, Any]]] = []
    for fl in result.get("flightLines") or []:
        rl = _route_list_from_flight_line(fl)
        if rl:
            per_line_routes.append(rl)

    if not per_line_routes:
        raise ValueError("未找到任何 type==2 航路段，无法生成 routeList")

    start_s, end_s = _period_bounds(result)
    task_id = _task_id_int(result)
    task_name = str(result.get("taskName") or "")

    uav_infos = result.get("uavInfos") or []

    out: List[Dict[str, Any]] = []
    for i, route_list in enumerate(per_line_routes):
        uid = None
        if i < len(uav_infos):
            u = uav_infos[i]
            uid = u.get("uavIdentifyCode") or u.get("uavId")
        if not uid:
            uid = _random_product_uid()
        uid_str = str(uid)
        flight_plan = {
            "flightPlanId": task_id,
            "planTakeoffTime": start_s,
            "planLandTime": end_s,
            "flightTaskId": task_id,
            "flightTaskName": task_name,
            "routeList": route_list,
        }
        out.append(
            {
                "key": uid_str,
                "value": {
                    "uniqueProductIdentificationCode": uid_str,
                    "flightPlanList": [flight_plan],
                },
            }
        )

    if conflict:
        conflict_idx = 0
        for route_list in per_line_routes:
            if len(route_list) < 2:
                continue
            cuid = _conflict_uid_at(conflict_idx)
            conflict_idx += 1
            conflict_plan = {
                "flightPlanId": task_id,
                "planTakeoffTime": start_s,
                "planLandTime": end_s,
                "flightTaskId": task_id,
                "flightTaskName": task_name,
                "routeList": _rotate_route_list(route_list, conflict_angle_deg),
            }
            out.append(
                {
                    "key": cuid,
                    "value": {
                        "uniqueProductIdentificationCode": cuid,
                        "flightPlanList": [conflict_plan],
                    },
                }
            )
    return out


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="lines.json -> redis_route 格式")
    ap.add_argument(
        "--input",
        type=Path,
        default=base / "lines.json",
        help="输入 lines.json 路径",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=base / "mock" / "redis_route_custom.json",
        help="输出路径",
    )
    ap.add_argument(
        "--count",
        type=int,
        default=None,
        help="传给 create_data：随机生成的基础航线数量，默认与 env.py 中 TARGET_DRONES 或 count 一致",
    )
    ap.add_argument(
        "--skip-create-data",
        action="store_true",
        help="仅写出 redis_route_custom.json，不调用 create_data",
    )
    ap.add_argument(
        "--conflict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否对每条基准航线各追加一条绕枢轴旋转得到的冲突航线（默认：生成）",
    )
    ap.add_argument(
        "--conflict-angle",
        type=float,
        default=5.0,
        help="冲突航线相对基准航线的水平旋转角（度），默认 5",
    )
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        lines_root = json.load(f)

    payload = lines_payload_to_redis_entries(
        lines_root,
        conflict=args.conflict,
        conflict_angle_deg=args.conflict_angle,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    res = lines_root.get("result") or {}
    n_base = sum(
        1 for fl in res.get("flightLines") or [] if _route_list_from_flight_line(fl)
    )
    if args.conflict and n_base and len(payload) > n_base:
        print(
            f"已写入 {args.output}，共 {len(payload)} 条（{n_base} 条基准航线 + {len(payload) - n_base} 条冲突航线）"
        )
    else:
        print(f"已写入 {args.output}，共 {len(payload)} 条")

    if args.skip_create_data:
        sys.exit(0)

    import create_data  # noqa: E402

    create_data.main(target_drones=args.count)
    sys.exit(0)


if __name__ == "__main__":
    main()
