# -*- coding: utf-8 -*-
"""
生成 mock/redis_route.json 与 mock/kafka_data.json（参考 main.py 逻辑，一次性跑完仿真）。
支持通过命令行 --count 指定无人机数量，默认 10。
"""
import sys
import os
import json
import argparse

# 项目根目录加入 path，便于导入
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from simulation_core import Simulator

MOCK_DIR = os.path.join(_ROOT, "mock")
REDIS_ROUTE_PATH = os.path.join(MOCK_DIR, "redis_route.json")
KAFKA_DATA_PATH = os.path.join(MOCK_DIR, "kafka_data.json")


def plan_to_redis_route(plan):
    """将 FlightPlan 转为 redis_route 一条记录（与 main.add_redis_plan 一致）。"""
    route_data = {}
    route_data["uniqueProductIdentificationCode"] = plan.aircraft.uid.decode("utf-8")
    flight_plan_list = []
    fp = {
        "flightPlanId": 1,
        "planTakeoffTime": plan.start_time,
        "planLandTime": plan.end_time,
        "flightTaskId": 1,
        "flightTaskName": "test",
        "routeList": [],
    }
    if plan.type == 0 and plan.data.traj.count > 0:
        wps_count = plan.data.traj.count
        for i in range(0, wps_count - 1):
            route = {
                "sequence": i,
                "type": 2,
                "segmentStartLon": plan.data.traj.wps[i].point.lon,
                "segmentStartLat": plan.data.traj.wps[i].point.lat,
                "segmentEndLon": plan.data.traj.wps[i + 1].point.lon,
                "segmentEndLat": plan.data.traj.wps[i + 1].point.lat,
                "segmentStartHeight": plan.data.traj.wps[i].point.alt,
                "segmentEndHeight": plan.data.traj.wps[i + 1].point.alt,
                "segmentProtectHeight": plan.data.traj.wps[i + 1].segmentVerticalleight,
                "segmentProtectHeightType": plan.data.traj.wps[i + 1].segmentProtectHeightType,
                "segmentWidth": plan.data.traj.wps[i + 1].segmentWidth,
            }
            fp["routeList"].append(route)
    flight_plan_list.append(fp)
    route_data["flightPlanList"] = flight_plan_list
    return {"key": plan.aircraft.uid.decode("utf-8"), "value": route_data}


def telemetry_to_kafka_item(t):
    """将遥测 current 转为一条 kafka_data（与 main.get_flight_plans_simulator 一致），并加 active: 1。"""
    uav_vid = t.uid.decode("utf-8")
    kafka_data = {
        "uniqueProductIdentificationCode": uav_vid,
        "realNameRegistrationSign": t.realNameRegistrationSign,
        "uasOperationCategory": 1,
        "classification": 1,
        "rpsLocationType": 1,
        "rpsLongitude": 0,
        "rpsLatitude": 0,
        "rpsAltitude": 0,
        "longitude": t.location.lon,
        "latitude": t.location.lat,
        "trackAngle": t.heading,
        "speed": t.speed,
        "geodeticAltitude": t.location.alt,
        "verticalSpeed": t.verticalSpeed,
        "relativeAltitude": getattr(t, "relativeAltitude", 0.0),
        "ressureAltitude": getattr(t, "ressureAltitude", 0.0),
        "operatingStatus": t.operatingStatus,
        "coordinateSystemType": t.coordinateSystemType,
        "horizontalAccuracy": t.horizontalAccuracy,
        "verticalAccuracy": t.verticalAccuracy,
        "speedAccuracy": t.speedAccuracy,
        "timestamp": t.timestamp * 1000,
        "timestampAccuracy": 0,
        "sourceType": t.sourceType if hasattr(t, "sourceType") else 1,    
        "addInf": t.addInf if hasattr(t, "addInf") else {},
        "active": 1
    }
    return kafka_data


def main(target_drones=None, origin_lat=None, origin_lon=None, sim_radius_m=None):
    """target_drones: 维持活跃无人机数量，默认 10。"""
    if target_drones is None or target_drones == 0:
        target_drones = 10
    os.makedirs(MOCK_DIR, exist_ok=True)

    simulator = Simulator(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        sim_radius_m=sim_radius_m,
    )
    plans = []
    for _ in range(target_drones):
        plan = simulator.generate_plan()
        plans.append(plan)

    # 若存在自定义航线文件，追加其中的飞行计划
    custom_route_path = os.path.join(MOCK_DIR, "redis_route_custom.json")
    if os.path.exists(custom_route_path):
        with open(custom_route_path, encoding="utf-8") as f:
            custom_params = json.load(f)
        added = simulator.add_plans(custom_params)
        # 将新追加的 DroneAgent 对应的 FlightPlan 也纳入 plans
        custom_uids = {item.get("key") or item.get("value", {}).get("uniqueProductIdentificationCode") for item in custom_params}
        plans.extend(agent.plan for uid, agent in simulator.agents.items() if uid in custom_uids)
        print(f"已加载自定义航线: {custom_route_path} (追加 {added} 架无人机)")

    # 1. 生成 mock/redis_route.json（与 main.py _maintain_traffic + add_redis_plan 一致）
    redis_route_list = [plan_to_redis_route(p) for p in plans]
    with open(REDIS_ROUTE_PATH, "w", encoding="utf-8") as f:
        json.dump(redis_route_list, f, ensure_ascii=False, indent=2)
    print(f"已生成: {REDIS_ROUTE_PATH} (共 {len(redis_route_list)} 条, drone_count={target_drones})")

    # 2. 用仿真时间一次性跑完，收集全部 kafka_data（带 active: 1）
    kafka_data_list = []
    sim_time = min(p.start_time for p in plans) if plans else 0
    step_sec = 1.0
    max_end = max(p.end_time for p in plans) if plans else 0
    max_steps = int(max_end - sim_time) + 600  # 防止死循环
    steps = 0
    while simulator.agents and steps < max_steps:
        payloads = simulator.step(step_sec, sim_time=sim_time)
        for item in payloads:
            t = item["current"]
            kafka_data_list.append(telemetry_to_kafka_item(t))
        sim_time += step_sec
        steps += 1

    with open(KAFKA_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(kafka_data_list, f, ensure_ascii=False, indent=2)
    print(f"已生成: {KAFKA_DATA_PATH} (共 {len(kafka_data_list)} 条)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成 mock 航线与 Kafka 数据，支持配置无人机数量")
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="维持活跃无人机数量，默认 10",
    )
    parser.add_argument(
        "--origin-lat",
        type=float,
        default=None,
        help="仿真中心纬度（度），默认使用 simulation_core 默认值",
    )
    parser.add_argument(
        "--origin-lon",
        type=float,
        default=None,
        help="仿真中心经度（度），默认使用 simulation_core 默认值",
    )
    parser.add_argument(
        "--sim-radius-m",
        type=float,
        default=None,
        help="仿真有效半径（米），默认使用 simulation_core 默认值",
    )
    args = parser.parse_args()
    main(
        target_drones=args.count,
        origin_lat=args.origin_lat,
        origin_lon=args.origin_lon,
        sim_radius_m=args.sim_radius_m,
    )
    sys.exit(0)
