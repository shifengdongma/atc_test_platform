#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 _source/plans.json 提取飞行计划，按 mock/redis_route.json 的格式
整理成标准飞行计划并保存为 mock/redis_route.json；
再按 uid 从 _source/telemetries.json 取对应遥测数据，按 json/kafka_data.json
的格式整理成标准飞行轨迹，按 timestamp 排序后保存为 mock/kafka_data.json。

若存在 telemetries.json：仅保留能产出飞行模拟数据（有对应遥测）的飞行计划，
无遥测或轨迹点不足无法生成航段的计划将不写入 redis_route.json。
"""

import json
from pathlib import Path

# 提取范围：EXTRACT_START、EXTRACT_END 均为 0 表示取全部；否则取 items[EXTRACT_START:EXTRACT_END]
EXTRACT_START: int = 0
EXTRACT_END: int = 5
# 若非空，则按此 UAV ID 列表提取飞行计划，不再使用 EXTRACT_START/EXTRACT_END
# EXTRACT_UAV_IDS: list[str] = ["UAV_00007","UAV_00077","UAV_00211","UAV_00241","UAV_00375","UAV_00475"] # 例如 ["UAV_00081", "UAV_00082"]
EXTRACT_UAV_IDS: list[str] = ["UAV_00001"]


def load_plans(plans_path: Path) -> dict:
    """加载 plans.json，返回根对象（key 为 UAV_xxx 的字典）。"""
    with open(plans_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_plans(
    plans_data: dict,
    start: int = 0,
    end: int = 0,
    uav_ids: list[str] | None = None,
) -> list[tuple[str, dict]]:
    """
    获取飞行计划列表：[(uav_id, plan_obj), ...]。
    uav_ids 非空时按该列表提取（忽略 start/end）；否则 start、end 均为 0 表示全部，否则取 items[start:end]。
    """
    if not plans_data:
        raise ValueError("plans.json 为空，无飞行计划")
    items = list(plans_data.items())
    if uav_ids:
        id_set = set(uav_ids)
        return [(uid, plan) for uid, plan in items if uid in id_set]
    if start == 0 and end == 0:
        return items
    return items[start:end]


def traj_to_route_list(traj: list) -> list:
    """
    将 plans 中的 traj（点序列）转为 redis_route 的 routeList（段序列）。
    每相邻两点构成一段：segment i = 从 traj[i] 到 traj[i+1]。
    """
    route_list = []
    for i in range(len(traj) - 1):
        a, b = traj[i], traj[i + 1]
        pa, pb = a["point"], b["point"]
        segment = {
            "sequence": i,
            "type": 2,
            "segmentStartLon": pa["lon"],
            "segmentStartLat": pa["lat"],
            "segmentEndLon": pb["lon"],
            "segmentEndLat": pb["lat"],
            "segmentStartHeight": pa["alt"],
            "segmentEndHeight": pb["alt"],
            "segmentProtectHeight": a.get("seg_h", 50.0),
            "segmentProtectHeightType": 1,
            "segmentWidth": a.get("seg_w", 100.0),
        }
        route_list.append(segment)
    return route_list


def plan_to_redis_route_value(uav_id: str, plan: dict) -> dict:
    """将 plans 中单个 plan 转为 redis_route 的 value 结构。"""
    traj = plan.get("traj", [])
    if len(traj) < 2:
        raise ValueError(f"飞行计划轨迹点不足 2 个，无法生成航段 (uav_id={uav_id})")

    route_list = traj_to_route_list(traj)
    flight_plan = {
        "flightPlanId": plan.get("plan_id", 1),
        "planTakeoffTime": plan.get("start_time", 0.0),
        "planLandTime": plan.get("end_time", 0.0),
        "flightTaskId": plan.get("task_id", 0),
        "flightTaskName": plan.get("task_name", ""),
        "routeList": route_list,
    }
    return {
        "uniqueProductIdentificationCode": uav_id,
        "flightPlanList": [flight_plan],
    }


def transform_and_save(
    plans_path: Path,
    output_path: Path,
    start: int = 0,
    end: int = 0,
    extract_uav_ids: list[str] | None = None,
    allowed_uav_ids: set[str] | None = None,
) -> list[tuple[str, dict]]:
    """
    从 plans 取计划，转为 redis_route 格式并写入 output_path。
    extract_uav_ids 非空时按该列表提取；否则 start、end 均为 0 表示全部，否则取 start:end 范围。
    若提供 allowed_uav_ids，仅保留能对应出飞行模拟数据（遥测）的飞行计划，其余不写入。
    返回 [(uav_id, plan), ...] 供后续遥测转换使用。
    """
    plans_data = load_plans(plans_path)
    items = get_plans(
        plans_data,
        start=start,
        end=end,
        uav_ids=extract_uav_ids if extract_uav_ids else None,
    )
    if allowed_uav_ids is not None:
        before = len(items)
        items = [(uav_id, plan) for uav_id, plan in items if uav_id in allowed_uav_ids]
        dropped = before - len(items)
        if dropped > 0:
            print(f"已剔除 {dropped} 个无遥测数据的飞行计划，仅保留 {len(items)} 个")
    payload = []
    kept_items: list[tuple[str, dict]] = []
    for uav_id, plan in items:
        try:
            value = plan_to_redis_route_value(uav_id, plan)
            payload.append({"key": uav_id, "value": value})
            kept_items.append((uav_id, plan))
        except ValueError:
            # 轨迹点不足等无法生成航段时，不写入该计划（视为“出不了飞行模拟数据”）
            print(f"  警告: 飞行计划无法生成航段 (uid={uav_id})，已跳过")
            continue
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    n = len(payload)
    uav_ids = [p["key"] for p in payload]
    print(f"已从 {plans_path} 提取 {n} 个飞行计划 ({', '.join(uav_ids)})，保存到 {output_path}")
    return kept_items


def telemetry_to_kafka_record(uid: str, point: dict) -> dict:
    """将 telemetries 单条遥测点转为 kafka_data 标准飞行轨迹记录。"""
    loc = point.get("loc", {})
    acc = point.get("acc", [1, 1, 1])
    return {
        "uniqueProductIdentificationCode": uid,
        "realNameRegistrationSign": uid,
        "uasOperationCategory": 1,
        "classification": point.get("cls", 1),
        "rpsLocationType": 1,
        "rpsLongitude": 0,
        "rpsLatitude": 0,
        "rpsAltitude": 0,
        "longitude": loc.get("lon", 0),
        "latitude": loc.get("lat", 0),
        "trackAngle": point.get("hdg", 0.0),
        "speed": point.get("spd", 0.0),
        "geodeticAltitude": loc.get("alt", 0.0),
        "verticalSpeed": point.get("v_spd", 0.0),
        "relativeAltitude": 0.0,
        "pressureAltitude": 0.0,
        "operatingStatus": point.get("status", 0),
        "coordinateSystemType": 0,
        "horizontalAccuracy": acc[0] if len(acc) > 0 else 1,
        "verticalAccuracy": acc[1] if len(acc) > 1 else 1,
        "speedAccuracy": acc[2] if len(acc) > 2 else 1,
        "timestamp": point.get("ts", 0) * 1000.0,
        "timestampAccuracy": 0,
    }


def build_kafka_data_from_telemetries(
    telemetries_path: Path,
    uav_ids: list[str],
    output_path: Path,
) -> None:
    """
    按 uid 从 telemetries 中取出对应遥测数组，转为 kafka_data 格式，
    合并后按 timestamp 排序，保存到 output_path。
    """
    with open(telemetries_path, "r", encoding="utf-8") as f:
        telemetries = json.load(f)
    records: list[dict] = []
    for uid in uav_ids:
        points = telemetries.get(uid)
        if not points:
            print(f"  警告: telemetries 中未找到 uid={uid}，跳过")
            continue
        for point in points:
            records.append(telemetry_to_kafka_record(uid, point))
    records.sort(key=lambda r: r["timestamp"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"已从 {telemetries_path} 按 {len(uav_ids)} 个 uid 提取遥测，共 {len(records)} 条，按 timestamp 排序后保存到 {output_path}")


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    plans_path = base / "_source" / "plans.json"
    telemetries_path = base / "_source" / "telemetries.json"
    redis_route_path = base / "mock" / "redis_route.json"
    kafka_data_path = base / "mock" / "kafka_data.json"
    if not plans_path.exists():
        raise FileNotFoundError(f"未找到 {plans_path}")
    # 若有遥测文件，仅保留能产出飞行模拟数据的飞行计划（有对应遥测的 uid）
    allowed_uav_ids: set[str] | None = None
    if telemetries_path.exists():
        with open(telemetries_path, "r", encoding="utf-8") as f:
            telemetries = json.load(f)
        allowed_uav_ids = {uid for uid, points in telemetries.items() if points}
    items = transform_and_save(
        plans_path,
        redis_route_path,
        start=EXTRACT_START,
        end=EXTRACT_END,
        extract_uav_ids=EXTRACT_UAV_IDS if EXTRACT_UAV_IDS else None,
        allowed_uav_ids=allowed_uav_ids,
    )
    uav_ids = [uid for uid, _ in items]
    if not telemetries_path.exists():
        print(f"未找到 {telemetries_path}，跳过 kafka_data 生成")
        return
    build_kafka_data_from_telemetries(telemetries_path, uav_ids, kafka_data_path)


if __name__ == "__main__":
    main()
