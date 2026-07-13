#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景模拟数据生成脚本 (create_data_scene.py)

功能：
1. 连接达梦数据库，查询 air_route 表获取航线 polygon、route_name 等信息
2. 根据航线关键点或命令行指定的起止坐标，生成完整的无人机遥测轨迹 JSON
3. 支持指定飞行速度、高度、无人机ID、时间戳等参数
4. 支持生成"偏离航路"的偏航数据（用于偏航告警测试）

参考：
- simulation_core.py: 坐标转换与航迹插值逻辑
- create_data.py: 遥测数据结构
- 偏离航路.json: 输出数据格式规范

用法示例：
  # 从数据库查询航线生成
  python create_data_scene.py --route-name "金鸡湖航线" --uid DJY001 --speed 15

  # 直接指定起止坐标生成
  python create_data_scene.py --start-lon 120.7418 --start-lat 31.3689 --end-lon 120.7300 --end-lat 31.3600 --speed 15 --altitude 30

  # 指定多个关键点
  python create_data_scene.py --points "120.7418,31.3689,30;120.7380,31.3650,35;120.7300,31.3600,30"

  # 生成偏航数据（偏离航路告警场景）
  python create_data_scene.py --points "120.7418,31.3689;120.7300,31.3600" --deviate --deviate-offset 0.001 --output-dir ../utm_test_cases/scenes/偏离航路告警
"""

import sys
import os
import json
import math
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime

# ==================== 路径配置 ====================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)  # utm_moc52_develop
_PROJECT_ROOT = os.path.dirname(_ROOT)  # Atc_Test2026

# 添加 dmdbclient 路径（atc_api_autotest/api_tools/）
_DMDB_PATH = os.path.join(_ROOT, "..", "atc_api_autotest", "api_tools")
if _DMDB_PATH not in sys.path:
    sys.path.insert(0, _DMDB_PATH)

# 尝试导入数据库客户端
# 注意: web_server.py 已 import env as _env，sys.modules['env'] 可能已缓存，
# 需临时清除让 dmdbclient.py 能正确导入 atc_api_autotest/env.py
_cached_env_for_dm = sys.modules.pop("env", None)
try:
    from dmdbclient import DmDbClient
    HAS_DB = True
except ImportError:
    HAS_DB = False
finally:
    if _cached_env_for_dm is not None:
        sys.modules["env"] = _cached_env_for_dm

# ==================== 常量 ====================
RE_EARTH = 6371000.0  # 地球半径（米）


# ==================== 用户配置区域（IDE 中直接修改此处即可运行）====================
# 说明：
#   以下参数为脚本默认配置，直接修改后点击运行即可生效。
#   命令行传入的参数会覆盖此处的默认值。
#   航线来源三选一：数据库查询 / 直接指定关键点 / 起止点

# ---- 输出配置 ----
OUTPUT_DIR = None          # JSON 输出目录，None 表示默认 ../../utm_test_cases/scenes
FILENAME = None            # 输出文件名，None 表示自动命名

# ---- 无人机信息 ----
UID = "DJY20260422001002031"   # 无人机唯一识别码
REG_SIGN = None                # 实名登记标识，None 表示与 UID 相同
CLASSIFICATION = 2             # 航空器分类 (UAVClassification): 0=微型(MICRO) 1=轻型(LIGHT) 2=小型(SMALL) 3=中型(MEDIUM) 4=大型(LARGE)

# ---- 航线来源配置（三选一） ----
# 方式1：数据库查询（需要安装 dmPython）
ROUTE_NAME = None          # air_route 表航线名称，例如 "金鸡湖航线"
ROUTE_ID = None            # air_route 表航线 ID

# 方式2：直接指定关键点序列
# 格式: "lon,lat,alt;lon,lat,alt;..."  高度(alt)可选，省略时使用默认高度
POINTS = None
# POINTS = "120.7418,31.3689,30;120.7380,31.3650,35;120.7300,31.3600,30"

# 方式3：起止坐标（当 ROUTE_NAME/ROUTE_ID/POINTS 均未设置时使用）
START_LON = None           # 起点经度
START_LAT = None           # 起点纬度
END_LON = None             # 终点经度
END_LAT = None             # 终点纬度

# ---- 高度配置（米） ----
ALTITUDE = 30.0            # 默认飞行高度
START_ALT = None           # 起点高度，None 表示使用 ALTITUDE
END_ALT = None             # 终点高度，None 表示使用 ALTITUDE

# ---- 速度与时间 ----
SPEED = 15.0               # 飞行速度（m/s）
START_TIME = None          # 起始时间戳（毫秒），None 表示使用当前时间
INTERVAL = 1000            # 采样间隔（毫秒）

# ---- 偏离航路（偏航告警场景） ----
DEVIATE = False            # True=生成偏离航路的轨迹，False=正常航线
DEVIATE_OFFSET = 0.001     # 偏离偏移量（度），0.001° 约 100 米
DEVIATE_START_INDEX = 5    # 从第几个点开始偏离

# ---- 运行状态 (operatingStatus) ----
# 状态值说明（参考 simulation_core.py）：
#   1 = 已落地 (FINISHED)   2 = 飞行中 (ACTIVE)
#   如需扩展业务状态（如 3=悬停 5=任务完成），直接填写对应数字即可
OPERATING_STATUS = 2                    # 默认运行状态
OPERATING_STATUS_CHANGE_TIME = None     # 运行多少毫秒后改变状态，None 表示按时间不变更
OPERATING_STATUS_CHANGE_INDEX = None    # 从第几个轨迹点开始改变状态，None 表示按索引不变更
OPERATING_STATUS_CHANGED = 2            # 变更后的状态值（配合上面两个条件使用）
# ==================== 用户配置区域结束 ====================


# ==================== 坐标计算工具（参考 simulation_core.py） ====================
def meters_to_geo(lat: float, lon: float, dn: float, de: float) -> tuple[float, float]:
    """局部东北坐标（米）转经纬度增量"""
    d_lat = dn / RE_EARTH
    d_lon = de / (RE_EARTH * math.cos(math.radians(lat)))
    return lat + math.degrees(d_lat), lon + math.degrees(d_lon)


def geo_to_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """两点的经纬度差转东北向位移（米）"""
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    return dn, de


def geo_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点间水平距离（米）"""
    dn, de = geo_to_meters(lat1, lon1, lat2, lon2)
    return math.sqrt(dn**2 + de**2)


def calc_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算航向角（度，北为0，顺时针）"""
    dn, de = geo_to_meters(lat1, lon1, lat2, lon2)
    heading = math.degrees(math.atan2(de, dn))
    if heading < 0:
        heading += 360.0
    return heading


def lerp(a: float, b: float, t: float) -> float:
    """线性插值"""
    return a + (b - a) * t


# ==================== 数据库与航线解析 ====================
def parse_polygon(polygon_val: Any) -> List[Dict[str, float]]:
    """
    解析数据库 polygon 字段，支持多种格式：
      - JSON: [{"lon":120.1,"lat":31.1},...] 或 [[120.1,31.1],...]
      - WKT: LINESTRING(120.1 31.1, 120.2 31.2,...)
      - 分号分隔: 120.1,31.1;120.2,31.2;...
    """
    if polygon_val is None:
        return []

    if isinstance(polygon_val, str):
        s = polygon_val.strip()
        # JSON
        if s.startswith("[") or s.startswith("{"):
            try:
                data = json.loads(s)
                points = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            lon = (
                                item.get("lon")
                                or item.get("longitude")
                                or item.get("x")
                                or item.get("LON")
                            )
                            lat = (
                                item.get("lat")
                                or item.get("latitude")
                                or item.get("y")
                                or item.get("LAT")
                            )
                            if lon is not None and lat is not None:
                                points.append({"lon": float(lon), "lat": float(lat)})
                        elif isinstance(item, (list, tuple)) and len(item) >= 2:
                            points.append({"lon": float(item[0]), "lat": float(item[1])})
                return points
            except json.JSONDecodeError:
                pass

        # WKT LINESTRING / POLYGON
        upper = s.upper()
        if "LINESTRING" in upper or "POLYGON" in upper:
            start = s.find("(")
            end = s.rfind(")")
            if start != -1 and end != -1:
                content = s[start + 1 : end]
                # POLYGON 可能有双层括号
                if content.startswith("("):
                    content = content[1:]
                if content.endswith(")"):
                    content = content[:-1]
                points = []
                for pair in content.split(","):
                    pair = pair.strip()
                    if not pair:
                        continue
                    coords = pair.split()
                    if len(coords) >= 2:
                        points.append({"lon": float(coords[0]), "lat": float(coords[1])})
                return points

        # 分号分隔的 经度,纬度 对
        points = []
        for segment in s.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            parts = [p.strip() for p in segment.split(",")]
            if len(parts) >= 2:
                v1, v2 = float(parts[0]), float(parts[1])
                # 中国经度约 73~135，纬度约 18~53；大于 90 的必为经度
                if abs(v1) > 90 or v1 > 50:
                    points.append({"lon": v1, "lat": v2})
                else:
                    points.append({"lon": v2, "lat": v1})
        return points

    elif isinstance(polygon_val, (list, tuple)):
        points = []
        for item in polygon_val:
            if isinstance(item, dict):
                lon = item.get("lon") or item.get("longitude") or item.get("x")
                lat = item.get("lat") or item.get("latitude") or item.get("y")
                if lon is not None and lat is not None:
                    points.append({"lon": float(lon), "lat": float(lat)})
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                points.append({"lon": float(item[0]), "lat": float(item[1])})
        return points

    return []


def query_air_route(route_name: Optional[str] = None, route_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """查询 air_route 表（下游 ATC_DKWRJ_TEST 数据库），兼容 NAME/route_name 字段名。"""
    if not HAS_DB:
        print("[错误] 数据库客户端不可用，请确保已安装 dmPython 且 dmdbclient.py 在路径中")
        return []

    client = DmDbClient()
    if not client.connect():
        return []

    conditions = []
    if route_name:
        conditions.append(f"route_name = '{route_name}'")
    if route_id is not None:
        conditions.append(f"ID = {route_id}")

    where = " AND ".join(conditions) if conditions else None

    try:
        # 兼容大小写表名
        for table_name in ["air_route", "AIR_ROUTE"]:
            try:
                data = client.query(table_name=table_name, where=where)
                if data:
                    client.close()
                    return data
            except Exception:
                continue
        client.close()
        return []
    except Exception as e:
        print(f"[错误] 查询失败: {e}")
        client.close()
        return []


# ==================== 遥测数据生成 ====================
def make_telemetry_point(
    uid: str,
    timestamp_ms: int,
    lon: float,
    lat: float,
    alt: float,
    speed: float,
    heading: float,
    vertical_speed: float = 0.0,
    reg_sign: Optional[str] = None,
    classification: int = 2,
    uas_operation_category: int = 1,
    operating_status: int = 2,
) -> Dict[str, Any]:
    """生成单条遥测数据，格式匹配 偏离航路.json"""
    if reg_sign is None:
        reg_sign = uid

    return {
        "uniqueProductIdentificationCode": uid,
        "realNameRegistrationSign": reg_sign,
        "uasOperationCategory": uas_operation_category,
        "classification": classification,
        "rpsLocationType": 1,
        "rpsLongitude": 0,
        "rpsLatitude": 0,
        "rpsAltitude": 0,
        "longitude": round(lon, 14),
        "latitude": round(lat, 14),
        "trackAngle": round(heading, 2),
        "speed": round(speed, 2),
        "geodeticAltitude": round(alt, 1),
        "verticalSpeed": round(vertical_speed, 2),
        "relativeAltitude": 0.0,
        "pressureAltitude": 0.0,
        "operatingStatus": operating_status,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1,
        "verticalAccuracy": 0,
        "speedAccuracy": 0,
        "timestamp": timestamp_ms,
        "timestampAccuracy": 0,
    }


def generate_trajectory(
    waypoints: List[Dict[str, Any]],
    uid: str,
    speed_ms: float,
    start_time_ms: Optional[int] = None,
    interval_ms: int = 1000,
    reg_sign: Optional[str] = None,
    classification: int = 2,
    operating_status: int = 2,
) -> List[Dict[str, Any]]:
    """
    根据航路点序列生成完整轨迹（线性插值）

    waypoints: [{"lon": ..., "lat": ..., "alt": ...}, ...]
    """
    if len(waypoints) < 2:
        raise ValueError("至少需要 2 个航路点")

    if start_time_ms is None:
        start_time_ms = int(datetime.now().timestamp() * 1000)

    trajectory: List[Dict[str, Any]] = []
    current_time_ms = start_time_ms

    for i in range(len(waypoints) - 1):
        p1 = waypoints[i]
        p2 = waypoints[i + 1]

        lon1, lat1 = p1["lon"], p1["lat"]
        lon2, lat2 = p2["lon"], p2["lat"]
        alt1 = p1.get("alt", 30.0)
        alt2 = p2.get("alt", 30.0)

        dist = geo_distance(lat1, lon1, lat2, lon2)
        heading = calc_heading(lat1, lon1, lat2, lon2)

        # 飞行时间（秒）
        fly_sec = dist / speed_ms if speed_ms > 0 else 1.0

        # 这段距离生成的点数
        num_points = max(1, int(fly_sec * 1000 / interval_ms))

        # 垂直速度
        v_speed = (alt2 - alt1) / fly_sec if fly_sec > 0 else 0.0

        for j in range(num_points):
            t = j / num_points
            lon = lerp(lon1, lon2, t)
            lat = lerp(lat1, lat2, t)
            alt = lerp(alt1, alt2, t)

            point = make_telemetry_point(
                uid=uid,
                timestamp_ms=current_time_ms,
                lon=lon,
                lat=lat,
                alt=alt,
                speed=speed_ms,
                heading=heading,
                vertical_speed=v_speed,
                reg_sign=reg_sign,
                classification=classification,
                operating_status=operating_status,
            )
            trajectory.append(point)
            current_time_ms += interval_ms

    # 终点
    last = waypoints[-1]
    last_heading = (
        calc_heading(waypoints[-2]["lat"], waypoints[-2]["lon"], last["lat"], last["lon"])
        if len(waypoints) >= 2
        else 0.0
    )

    trajectory.append(
        make_telemetry_point(
            uid=uid,
            timestamp_ms=current_time_ms,
            lon=last["lon"],
            lat=last["lat"],
            alt=last.get("alt", 30.0),
            speed=0.0,
            heading=last_heading,
            vertical_speed=0.0,
            reg_sign=reg_sign,
            classification=classification,
            operating_status=operating_status,
        )
    )

    return trajectory


def apply_deviation(trajectory: List[Dict[str, Any]], offset_deg: float, start_index: int = 0) -> None:
    """在原轨迹上叠加偏移，生成偏离航路数据（原地修改）"""
    for i in range(start_index, len(trajectory)):
        trajectory[i]["longitude"] += offset_deg
        trajectory[i]["latitude"] += offset_deg


# ==================== 参数构建 ====================
def build_waypoints(args) -> List[Dict[str, Any]]:
    """根据命令行参数构建航路点列表

    优先级：
      1. --route-name / --route-id  查询数据库
      2. --points                    直接指定关键点
      3. --start-lon/lat --end-lon/lat 起止点
    """
    waypoints: List[Dict[str, Any]] = []

    # 1. 数据库查询航线
    if args.route_name or args.route_id is not None:
        if not HAS_DB:
            print("[警告] 未安装 dmPython，无法查询数据库航线")
        else:
            print(f"[信息] 查询 air_route: route_name={args.route_name}, route_id={args.route_id}")
            routes = query_air_route(route_name=args.route_name, route_id=args.route_id)
            if routes:
                route = routes[0]
                polygon = (
                    route.get("polygon")
                    or route.get("POLYGON")
                    or route.get("Polygon")
                )
                name = (
                    route.get("route_name")
                    or route.get("ROUTE_NAME")
                    or route.get("Route_Name")
                    or "unknown"
                )
                print(f"[信息] 获取航线: {name}")

                db_points = parse_polygon(polygon)
                if db_points:
                    print(f"[信息] 解析到 {len(db_points)} 个航路点")
                    base_alt = args.altitude if args.altitude is not None else 30.0
                    for p in db_points:
                        waypoints.append({"lon": p["lon"], "lat": p["lat"], "alt": base_alt})
                else:
                    print("[警告] polygon 字段解析失败，请检查字段格式")
            else:
                print("[警告] 数据库未找到匹配航线")

    # 2. 命令行直接指定关键点
    if args.points:
        for segment in args.points.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            parts = [float(x.strip()) for x in segment.split(",")]
            if len(parts) >= 2:
                wp = {"lon": parts[0], "lat": parts[1]}
                wp["alt"] = (
                    parts[2]
                    if len(parts) >= 3
                    else (args.altitude if args.altitude is not None else 30.0)
                )
                waypoints.append(wp)

    # 3. 起止点模式
    has_start = args.start_lon is not None and args.start_lat is not None
    has_end = args.end_lon is not None and args.end_lat is not None

    if has_start:
        wp_start = {
            "lon": args.start_lon,
            "lat": args.start_lat,
            "alt": (
                args.start_alt
                if args.start_alt is not None
                else (args.altitude if args.altitude is not None else 30.0)
            ),
        }

        if not waypoints:
            waypoints = [wp_start]
            if has_end:
                wp_end = {
                    "lon": args.end_lon,
                    "lat": args.end_lat,
                    "alt": (
                        args.end_alt
                        if args.end_alt is not None
                        else (args.altitude if args.altitude is not None else 30.0)
                    ),
                }
                waypoints.append(wp_end)
        else:
            first_is_start = (
                abs(waypoints[0]["lon"] - wp_start["lon"]) < 1e-9
                and abs(waypoints[0]["lat"] - wp_start["lat"]) < 1e-9
            )
            if not first_is_start:
                waypoints.insert(0, wp_start)

            if has_end:
                wp_end = {
                    "lon": args.end_lon,
                    "lat": args.end_lat,
                    "alt": (
                        args.end_alt
                        if args.end_alt is not None
                        else (args.altitude if args.altitude is not None else 30.0)
                    ),
                }
                last_is_end = (
                    abs(waypoints[-1]["lon"] - wp_end["lon"]) < 1e-9
                    and abs(waypoints[-1]["lat"] - wp_end["lat"]) < 1e-9
                )
                if not last_is_end:
                    waypoints.append(wp_end)

    return waypoints


# ==================== 主函数 ====================
def main():
    parser = argparse.ArgumentParser(
        description="生成无人机场景模拟数据 JSON（支持数据库航线查询）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  # 从数据库查询航线
  python create_data_scene.py --route-name "金鸡湖航线" --uid DJY001

  # 直接指定起止坐标
  python create_data_scene.py --start-lon 120.7418 --start-lat 31.3689 --end-lon 120.7300 --end-lat 31.3600 --speed 15

  # 指定多个关键点（分号分隔）
  python create_data_scene.py --points "120.7418,31.3689,30;120.7380,31.3650,35;120.7300,31.3600,30"

  # 生成偏航告警场景（航线正常，但轨迹偏移）
  python create_data_scene.py --points "120.7418,31.3689;120.7300,31.3600" --deviate --deviate-offset 0.001
        """,
    )

    # 输出
    parser.add_argument(
        "--output-dir", "-o", default=OUTPUT_DIR, help="JSON输出目录，默认 ../../utm_test_cases/scenes"
    )
    parser.add_argument("--filename", "-f", default=FILENAME, help="输出文件名，默认自动命名")

    # 无人机信息
    parser.add_argument("--uid", default=UID, help="无人机唯一识别码")
    parser.add_argument("--reg-sign", default=REG_SIGN, help="实名登记标识，默认同uid")
    parser.add_argument("--classification", type=int, default=CLASSIFICATION, help="航空器分类，默认2")

    # 数据库航线查询
    parser.add_argument("--route-name", default=ROUTE_NAME, help="air_route 表航线名称")
    parser.add_argument("--route-id", type=int, default=ROUTE_ID, help="air_route 表航线ID")

    # 坐标点（多种输入方式）
    parser.add_argument(
        "--points",
        default=POINTS,
        help="关键点序列，格式: lon,lat,alt;lon,lat,alt;...（高度可选）",
    )
    parser.add_argument("--start-lon", type=float, default=START_LON, help="起点经度")
    parser.add_argument("--start-lat", type=float, default=START_LAT, help="起点纬度")
    parser.add_argument("--end-lon", type=float, default=END_LON, help="终点经度")
    parser.add_argument("--end-lat", type=float, default=END_LAT, help="终点纬度")

    # 高度
    parser.add_argument(
        "--altitude", "-a", type=float, default=ALTITUDE, help="默认飞行高度(米)，默认30.0"
    )
    parser.add_argument("--start-alt", type=float, default=START_ALT, help="起点高度(米)")
    parser.add_argument("--end-alt", type=float, default=END_ALT, help="终点高度(米)")

    # 速度与时间
    parser.add_argument(
        "--speed", "-s", type=float, default=SPEED, help="飞行速度(m/s)，默认15.0"
    )
    parser.add_argument(
        "--start-time", type=int, default=START_TIME, help="起始时间戳(毫秒)，默认当前时间"
    )
    parser.add_argument(
        "--interval", type=int, default=INTERVAL, help="采样间隔(毫秒)，默认1000"
    )

    # 偏离航路（偏航告警）
    parser.add_argument("--deviate", action="store_true", default=DEVIATE, help="生成偏离航路的轨迹")
    parser.add_argument(
        "--deviate-offset",
        type=float,
        default=DEVIATE_OFFSET,
        help="偏离偏移量(度)，默认0.001（约100米）",
    )
    parser.add_argument(
        "--deviate-start-index",
        type=int,
        default=DEVIATE_START_INDEX,
        help="从第几个点开始偏离，默认5",
    )

    # 运行状态 (operatingStatus)
    parser.add_argument(
        "--operating-status",
        type=int,
        default=OPERATING_STATUS,
        help="默认运行状态: 1=已落地 2=飞行中",
    )
    parser.add_argument(
        "--operating-status-change-time",
        type=int,
        default=OPERATING_STATUS_CHANGE_TIME,
        help="运行多少毫秒后改变状态，None 表示不变更",
    )
    parser.add_argument(
        "--operating-status-change-index",
        type=int,
        default=OPERATING_STATUS_CHANGE_INDEX,
        help="从第几个轨迹点开始改变状态，None 表示不变更",
    )
    parser.add_argument(
        "--operating-status-changed",
        type=int,
        default=OPERATING_STATUS_CHANGED,
        help="变更后的状态值",
    )

    args = parser.parse_args()

    # 确定输出目录
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = os.path.join(_ROOT, "utm_test_cases", "scenes")

    os.makedirs(output_dir, exist_ok=True)

    # 构建航路点
    waypoints = build_waypoints(args)
    if len(waypoints) < 2:
        print("[错误] 无法构建有效航路点，至少需要2个点")
        print("请通过以下任一方式指定：")
        print("  1. --route-name / --route-id  从数据库查询航线")
        print("  2. --points 'lon,lat,alt;...'  直接指定关键点")
        print("  3. --start-lon/lat --end-lon/lat  指定起止点")
        sys.exit(1)

    print(f"[信息] 航路点 ({len(waypoints)} 个):")
    for i, wp in enumerate(waypoints):
        print(f"  [{i}] lon={wp['lon']:.6f}, lat={wp['lat']:.6f}, alt={wp.get('alt', 30.0):.1f}")

    # 生成轨迹
    trajectory = generate_trajectory(
        waypoints=waypoints,
        uid=args.uid,
        speed_ms=args.speed,
        start_time_ms=args.start_time,
        interval_ms=args.interval,
        reg_sign=args.reg_sign,
        classification=args.classification,
        operating_status=args.operating_status,
    )

    # 应用偏离
    if args.deviate:
        print(
            f"[信息] 生成偏离轨迹，偏移 {args.deviate_offset}°，从索引 {args.deviate_start_index} 开始"
        )
        apply_deviation(trajectory, args.deviate_offset, args.deviate_start_index)

    # 应用运行状态变更（按时间或按索引）
    if args.operating_status_change_time is not None and trajectory:
        change_at = trajectory[0]["timestamp"] + args.operating_status_change_time
        changed_count = 0
        for p in trajectory:
            if p["timestamp"] >= change_at:
                p["operatingStatus"] = args.operating_status_changed
                changed_count += 1
        if changed_count > 0:
            print(
                f"[信息] 运行状态变更: {args.operating_status_change_time}ms 后"
                f" ({changed_count} 条数据) operatingStatus -> {args.operating_status_changed}"
            )

    if args.operating_status_change_index is not None and trajectory:
        idx = min(args.operating_status_change_index, len(trajectory))
        for i in range(idx, len(trajectory)):
            trajectory[i]["operatingStatus"] = args.operating_status_changed
        if idx < len(trajectory):
            print(
                f"[信息] 运行状态变更: 从索引 {idx} 开始"
                f" ({len(trajectory) - idx} 条数据) operatingStatus -> {args.operating_status_changed}"
            )

    # 文件名
    if args.filename:
        filename = args.filename if args.filename.endswith(".json") else args.filename + ".json"
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dev_tag = "_deviate" if args.deviate else ""
        filename = f"UAV_scene_{args.uid}{dev_tag}_{ts}.json"

    output_path = os.path.join(output_dir, filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(trajectory, f, ensure_ascii=False, indent=2)

    # 统计信息
    duration_sec = (trajectory[-1]["timestamp"] - trajectory[0]["timestamp"]) / 1000.0
    lons = [p["longitude"] for p in trajectory]
    lats = [p["latitude"] for p in trajectory]
    alts = [p["geodeticAltitude"] for p in trajectory]

    print(f"\n[完成] 输出: {output_path}")
    print(f"  数据条数: {len(trajectory)}")
    print(f"  时间跨度: {duration_sec:.1f} 秒")
    print(f"  经度范围: {min(lons):.6f} ~ {max(lons):.6f}")
    print(f"  纬度范围: {min(lats):.6f} ~ {max(lats):.6f}")
    print(f"  高度范围: {min(alts):.1f} ~ {max(alts):.1f} 米")


if __name__ == "__main__":
    main()
