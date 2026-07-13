#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一场景数据生成脚本 (create_data_scenes.py)

整合所有数据生成与检查场景，采用子命令架构：
  create      基础仿真数据生成（redis_route + kafka_data）
  route       沿航线飞行数据（单UAV，支持偏离/状态变更）
  parallel    大规模平行飞行（六边形/直线布局，ID碰撞避让）
  deviate     偏离航路告警（水平/垂直/both，平滑渐变）
  collision   碰撞预警（交汇点检测、同步到达、区域标记）
  status      飞行器状态告警（紧急/丢失/紧急后丢失）
  scale       基于模板批量扩展（蜂窝网格分布）
  check-id    ID碰撞检测（Java hashCode模拟）
  check-uid   UID数据库存在性检查
  analyze     轨迹质量分析（跳变/heading突变/方向反转）
  batch       批量场景执行（读取BATCH_CONFIGS预设）

用法示例:
  python create_data_scenes.py create --count 10
  python create_data_scenes.py route --route-name "金鸡湖航线" --speed 15
  python create_data_scenes.py parallel --count 3000 --layout hex
  python create_data_scenes.py deviate --route-name "跨顺义三河段" --deviate-offset 600
  python create_data_scenes.py collision --route-names "航线A,航线B"
  python create_data_scenes.py status --scene3 --count 5
  python create_data_scenes.py check-id --files ../data/mock/新疆空域2_平行飞行.json
  python create_data_scenes.py batch
"""

import sys
import os
import json
import math
import argparse
import random
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any, Optional

# ==================== 路径配置 ====================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 添加 dmdbclient 路径（atc_api_autotest/api_tools/）
_DMDB_PATH = os.path.join(_ROOT, "..", "atc_api_autotest", "api_tools")
if _DMDB_PATH not in sys.path:
    sys.path.insert(0, _DMDB_PATH)

# ==================== 外部模块导入 ====================
# 注意: web_server.py 已 import env as _env，导致 sys.modules['env'] 被缓存为
# utm_simulator/env.py。dmdbclient.py 需要 atc_api_autotest/env.py（含 DB_HOST），
# 因此需临时清除缓存。
_cached_env_for_dm = sys.modules.pop("env", None)
try:
    from dmdbclient import DmDbClient
    HAS_DB = True
except ImportError:
    HAS_DB = False
finally:
    if _cached_env_for_dm is not None:
        sys.modules["env"] = _cached_env_for_dm

try:
    from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED
except ImportError:
    UAV_IDENTIFIERS_EXTENDED = []

try:
    from simulation_core import Simulator
    HAS_SIMULATOR = True
except ImportError:
    HAS_SIMULATOR = False

# ==================== 常量 ====================
RE_EARTH = 6371000.0  # 地球半径（米）

# ==================== 批量预设配置 ====================
# 用于 batch 子命令一键生成多场景
BATCH_CONFIGS = [
    {"subcommand": "parallel", "count": 100, "center_lng": 87.407734, "center_lat": 43.450822,
     "output": "../data/mock/新疆空域1_平行飞行.json", "label": "新疆空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 10, "altitude": 30}, {"count": 90, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 82.382178, "center_lat": 40.171273,
     "output": "../data/mock/新疆空域2_平行飞行.json", "label": "新疆空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 85.507436, "center_lat": 32.604875,
     "output": "../data/mock/西藏空域1_平行飞行.json", "label": "西藏空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 91.725056, "center_lat": 38.264847,
     "output": "../data/mock/青海空域1_平行飞行.json", "label": "青海空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 91.769785, "center_lat": 35.956547,
     "output": "../data/mock/青海空域2_平行飞行.json", "label": "青海空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 96.105003, "center_lat": 35.859452,
     "output": "../data/mock/青海空域3_平行飞行.json", "label": "青海空域3-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 99.344645, "center_lat": 35.914791,
     "output": "../data/mock/青海空域4_平行飞行.json", "label": "青海空域4-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 96.119904, "center_lat": 40.486873,
     "output": "../data/mock/甘肃空域1_平行飞行.json", "label": "甘肃空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 102.361720, "center_lat": 38.180031,
     "output": "../data/mock/甘肃空域2_平行飞行.json", "label": "甘肃空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 101.537149, "center_lat": 41.134612,
     "output": "../data/mock/内蒙空域1_平行飞行.json", "label": "内蒙空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
    {"subcommand": "parallel", "count": 300, "center_lng": 105.377261, "center_lat": 40.571124,
     "output": "../data/mock/内蒙空域2_平行飞行.json", "label": "内蒙空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": True, "altitude_groups": [{"count": 30, "altitude": 30}, {"count": 270, "altitude": 50}]},
]


# ==================== 公共基础层 ====================
def make_telemetry_point(
    uid: str,
    reg_sign: str,
    timestamp_ms: int,
    lon: float,
    lat: float,
    alt: float,
    speed: float,
    heading: float,
    classification: int = 2,
    status: int = 2,
    uas_operation_category: int = 1,
    vertical_speed: float = 0.0,
    relative_altitude: float = 0.0,
    pressure_altitude: float = 0.0,
    rps_lon: float = 0.0,
    rps_lat: float = 0.0,
    rps_alt: float = 0.0,
    source_type: int = 1,
    add_inf: Optional[Dict[str, Any]] = None,
    active: Optional[int] = None,
    zone: Optional[int] = None,
) -> Dict[str, Any]:
    """生成单条遥测数据字典，统一所有场景的字段标准。"""
    point = {
        "uniqueProductIdentificationCode": uid,
        "realNameRegistrationSign": reg_sign,
        "uasOperationCategory": uas_operation_category,
        "classification": classification,
        "rpsLocationType": 1,
        "rpsLongitude": rps_lon,
        "rpsLatitude": rps_lat,
        "rpsAltitude": rps_alt,
        "longitude": round(lon, 14),
        "latitude": round(lat, 14),
        "trackAngle": round(heading, 2),
        "speed": round(speed, 2),
        "geodeticAltitude": round(alt, 1),
        "verticalSpeed": round(vertical_speed, 2),
        "relativeAltitude": relative_altitude,
        "pressureAltitude": pressure_altitude,
        "operatingStatus": status,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1,
        "verticalAccuracy": 0,
        "speedAccuracy": 0,
        "timestamp": timestamp_ms,
        "timestampAccuracy": 0,
        "sourceType": source_type,
        "addInf": add_inf if add_inf is not None else {},
    }
    if active is not None:
        point["active"] = active
    if zone is not None:
        point["zone"] = zone
    return point


def geo_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点间水平距离（米），使用局部等距投影。"""
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    return math.sqrt(dn**2 + de**2)


def calc_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算航向角（度），北向为 0°，顺时针增加。"""
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    heading = math.degrees(math.atan2(de, dn))
    if heading < 0:
        heading += 360.0
    return heading


def meters_to_geo(lat: float, lon: float, dn: float, de: float) -> tuple[float, float]:
    """局部东北坐标（米）转经纬度增量。"""
    d_lat = dn / RE_EARTH
    d_lon = de / (RE_EARTH * math.cos(math.radians(lat)))
    return lat + math.degrees(d_lat), lon + math.degrees(d_lon)


def geo_to_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """两点的经纬度差转东北向位移（米）。"""
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    return dn, de


def lerp(a: float, b: float, t: float) -> float:
    """线性插值。"""
    return a + (b - a) * t


def calc_step_offsets(speed_ms: float, heading_deg: float, center_lat: float) -> tuple[float, float]:
    """计算每秒的经纬度增量。"""
    heading_rad = math.radians(heading_deg)
    dn = speed_ms * math.cos(heading_rad)
    de = speed_ms * math.sin(heading_rad)
    meters_per_deg_lat = 111320.0
    meters_per_deg_lng = 111320.0 * math.cos(math.radians(center_lat))
    return dn / meters_per_deg_lat, de / meters_per_deg_lng


# ==================== 航路点插值 ====================
def interpolate_route(
    points: List[Dict[str, float]],
    speed_ms: float,
    start_time_ms: int,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """根据航路点序列沿航线线性插值，每秒生成一个坐标点。"""
    if len(points) < 2:
        raise ValueError("航线至少需要 2 个航路点")

    trajectory: List[Dict[str, Any]] = []
    current_time_ms = start_time_ms

    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        lat1, lon1 = p1["lat"], p1["lon"]
        lat2, lon2 = p2["lat"], p2["lon"]

        dist = geo_distance(lat1, lon1, lat2, lon2)
        heading = calc_heading(lat1, lon1, lat2, lon2)

        fly_sec = dist / speed_ms if speed_ms > 0 else 1.0
        num_points = max(2, int(round(fly_sec)) + 1)

        for j in range(num_points):
            if num_points > 1:
                t = j / (num_points - 1)
            else:
                t = 0
            lat = lat1 + (lat2 - lat1) * t
            lon = lon1 + (lon2 - lon1) * t

            if trajectory and j == 0 and i > 0:
                prev = trajectory[-1]
                if abs(lat - prev["lat"]) < 1e-12 and abs(lon - prev["lon"]) < 1e-12:
                    continue

            trajectory.append({
                "lat": lat,
                "lon": lon,
                "heading": heading,
                "time_ms": current_time_ms,
                "segment_idx": i,
            })
            current_time_ms += interval_ms

    return trajectory


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
    """根据航路点序列生成完整遥测轨迹。waypoints: [{lon,lat,alt}, ...]"""
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

        fly_sec = dist / speed_ms if speed_ms > 0 else 1.0
        num_points = max(1, int(fly_sec * 1000 / interval_ms))
        v_speed = (alt2 - alt1) / fly_sec if fly_sec > 0 else 0.0

        for j in range(num_points):
            t = j / num_points
            lon = lerp(lon1, lon2, t)
            lat = lerp(lat1, lat2, t)
            alt = lerp(alt1, alt2, t)
            trajectory.append(make_telemetry_point(
                uid=uid, reg_sign=reg_sign or uid, timestamp_ms=current_time_ms,
                lon=lon, lat=lat, alt=alt, speed=speed_ms, heading=heading,
                classification=classification, status=operating_status,
                vertical_speed=v_speed,
            ))
            current_time_ms += interval_ms

    last = waypoints[-1]
    last_heading = calc_heading(waypoints[-2]["lat"], waypoints[-2]["lon"], last["lat"], last["lon"]) if len(waypoints) >= 2 else 0.0
    trajectory.append(make_telemetry_point(
        uid=uid, reg_sign=reg_sign or uid, timestamp_ms=current_time_ms,
        lon=last["lon"], lat=last["lat"], alt=last.get("alt", 30.0),
        speed=0.0, heading=last_heading, classification=classification,
        status=operating_status,
    ))
    return trajectory


# ==================== Polygon 解析 ====================
def parse_polygon(polygon_val: Any) -> List[Dict[str, float]]:
    """解析数据库 polygon 字段，支持 JSON/WKT/分号分隔/GeoJSON 等多种格式。"""
    if polygon_val is None:
        return []

    if isinstance(polygon_val, str):
        s = polygon_val.strip()

        if s.startswith("[") or s.startswith("{"):
            try:
                data = json.loads(s)
                points = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            lon = item.get("lon") or item.get("longitude") or item.get("x") or item.get("LON")
                            lat = item.get("lat") or item.get("latitude") or item.get("y") or item.get("LAT")
                            if lon is not None and lat is not None:
                                points.append({"lon": float(lon), "lat": float(lat)})
                        elif isinstance(item, (list, tuple)) and len(item) >= 2:
                            points.append({"lon": float(item[0]), "lat": float(item[1])})
                elif isinstance(data, dict):
                    coords = data.get("coordinates")
                    if coords is not None and isinstance(coords, list):
                        ring = coords
                        if ring and isinstance(ring[0], list) and len(ring[0]) > 0 and isinstance(ring[0][0], list):
                            ring = ring[0]
                        for item in ring:
                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                points.append({"lon": float(item[0]), "lat": float(item[1])})
                    if not points:
                        lon = data.get("lon") or data.get("longitude") or data.get("x") or data.get("LON")
                        lat = data.get("lat") or data.get("latitude") or data.get("y") or data.get("LAT")
                        if lon is not None and lat is not None:
                            points.append({"lon": float(lon), "lat": float(lat)})
                if len(points) >= 2:
                    first = points[0]
                    last = points[-1]
                    if abs(first["lon"] - last["lon"]) < 1e-9 and abs(first["lat"] - last["lat"]) < 1e-9:
                        points.pop()
                return points
            except json.JSONDecodeError:
                pass

        upper = s.upper()
        if "LINESTRING" in upper or "POLYGON" in upper:
            start = s.find("(")
            end = s.rfind(")")
            if start != -1 and end != -1:
                content = s[start + 1:end]
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

        points = []
        for segment in s.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            parts = [p.strip() for p in segment.split(",")]
            if len(parts) >= 2:
                v1, v2 = float(parts[0]), float(parts[1])
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


# ==================== 数据库查询 ====================
def query_air_route(route_name: Optional[str] = None, route_id: Optional[Any] = None) -> List[Dict[str, Any]]:
    """查询 air_route 表（下游 ATC_DKWRJ_TEST 数据库），兼容 NAME/route_name 字段名。"""
    if not HAS_DB:
        print("[错误] 数据库客户端不可用，请确保已安装 dmPython 且 dmdbclient.py 在路径中")
        return []

    client = DmDbClient()
    if not client.connect():
        return []

    conditions = []
    if route_name:
        # 实际列名为 route_name（无 NAME 列）
        conditions.append(f"route_name = '{route_name}'")
    if route_id is not None:
        conditions.append(f"ID = {route_id}")
    where = " AND ".join(conditions) if conditions else None

    try:
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


def query_air_route_single(route_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """查询 air_route 表单条记录，多匹配时打印列表并返回第一条。"""
    data = query_air_route(route_name=route_name)
    if not data:
        return None
    if len(data) > 1:
        print(f"[警告] 找到 {len(data)} 条名为 '{route_name}' 的航线，默认使用第一条")
    return data[0]


def query_route_elements(route_id: Any) -> List[Dict[str, float]]:
    """查询 air_route_element 表获取航路中心线坐标点（下游 ATC_DKWRJ_TEST 数据库）。

    按 sequence 排序，从每段的 start_point_lon/lat 和 end_point_lon/lat 构建连续航路点列表。
    """
    if not HAS_DB:
        return []

    client = DmDbClient()
    if not client.connect():
        return []

    route_id_val = str(route_id)
    try:
        # 下游数据库表名: air_route_element / AIR_ROUTE_ELEMENT
        # 字段: route_id, sequence, start_point_lon/lat, end_point_lon/lat
        for table_name in ["air_route_element", "AIR_ROUTE_ELEMENT"]:
            try:
                where = f"route_id = '{route_id_val}' ORDER BY sequence ASC"
                data = client.query(table_name=table_name, where=where)
                if data:
                    points = []
                    for row in data:
                        try:
                            # 起点坐标（兼容大小写）
                            s_lon = (row.get("START_POINT_LON") or row.get("start_point_lon")
                                     or row.get("Start_Point_Lon"))
                            s_lat = (row.get("START_POINT_LAT") or row.get("start_point_lat")
                                     or row.get("Start_Point_Lat"))
                            # 终点坐标（兼容大小写）
                            e_lon = (row.get("END_POINT_LON") or row.get("end_point_lon")
                                     or row.get("End_Point_Lon"))
                            e_lat = (row.get("END_POINT_LAT") or row.get("end_point_lat")
                                     or row.get("End_Point_Lat"))

                            if s_lon is not None and s_lat is not None:
                                start_pt = {"lon": float(s_lon), "lat": float(s_lat)}
                                if not points:
                                    points.append(start_pt)
                                elif not (abs(start_pt["lon"] - points[-1]["lon"]) < 1e-9
                                          and abs(start_pt["lat"] - points[-1]["lat"]) < 1e-9):
                                    points.append(start_pt)

                            if e_lon is not None and e_lat is not None:
                                end_pt = {"lon": float(e_lon), "lat": float(e_lat)}
                                if not (abs(end_pt["lon"] - points[-1]["lon"]) < 1e-9
                                        and abs(end_pt["lat"] - points[-1]["lat"]) < 1e-9):
                                    points.append(end_pt)
                        except (ValueError, TypeError):
                            continue
                    client.close()
                    return points
            except Exception:
                continue
        client.close()
        return []
    except Exception as e:
        print(f"[错误] 查询航路点失败: {e}")
        client.close()
        return []


# ==================== 坐标系转换 ====================
def _transformlat(lng: float, lat: float) -> float:
    ret = (-100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat
           + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng)))
    ret += ((20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0)
    ret += ((20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0)
    ret += ((160.0 * math.sin(lat / 12.0 * math.pi) + 320.0 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0)
    return ret


def _transformlng(lng: float, lat: float) -> float:
    ret = (300.0 + lng + 2.0 * lat + 0.1 * lng * lng
           + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng)))
    ret += ((20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0)
    ret += ((20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0)
    ret += ((150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi)) * 2.0 / 3.0)
    return ret


def _out_of_china(lng: float, lat: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transformlat(lng - 105.0, lat - 35.0)
    dlng = _transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transformlat(lng - 105.0, lat - 35.0)
    dlng = _transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    return lng - dlng, lat - dlat


def gcj02_to_bd09(lng: float, lat: float) -> tuple[float, float]:
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * math.pi * 3000.0 / 180.0)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * math.pi * 3000.0 / 180.0)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    return z * math.cos(theta), z * math.sin(theta)


def convert_coordinate(lng: float, lat: float, from_sys: str, to_sys: str) -> tuple[float, float]:
    """通用坐标转换入口。支持: wgs84, gcj02, bd09。"""
    from_sys = from_sys.lower().strip()
    to_sys = to_sys.lower().strip()
    if from_sys == to_sys:
        return lng, lat
    if from_sys == "wgs84" and to_sys == "gcj02":
        return wgs84_to_gcj02(lng, lat)
    elif from_sys == "gcj02" and to_sys == "wgs84":
        return gcj02_to_wgs84(lng, lat)
    elif from_sys == "gcj02" and to_sys == "bd09":
        return gcj02_to_bd09(lng, lat)
    elif from_sys == "bd09" and to_sys == "gcj02":
        return bd09_to_gcj02(lng, lat)
    elif from_sys == "wgs84" and to_sys == "bd09":
        lng, lat = wgs84_to_gcj02(lng, lat)
        return gcj02_to_bd09(lng, lat)
    elif from_sys == "bd09" and to_sys == "wgs84":
        lng, lat = bd09_to_gcj02(lng, lat)
        return gcj02_to_wgs84(lng, lat)
    return lng, lat


# ==================== UAV ID 管理 ====================
def get_uav_id_pool() -> List[tuple[str, str]]:
    """获取 UAV ID 池（倒序）。"""
    return UAV_IDENTIFIERS_EXTENDED[::-1] if UAV_IDENTIFIERS_EXTENDED else []


def get_uav_ids(offset: int, count: int) -> List[tuple[str, str]]:
    """从扩展ID池中获取指定范围和数量的 UAV ID。"""
    pool = get_uav_id_pool()
    if not pool:
        return []
    offset = offset % len(pool)
    result = []
    for i in range(count):
        result.append(pool[(offset + i) % len(pool)])
    return result


def compute_java_hash_code(s: str) -> int:
    """模拟 Java String.hashCode() + Math.abs() 行为。"""
    h = 0
    for ch in s:
        h = (31 * h + ord(ch)) & 0xFFFFFFFF
    if h > 0x7FFFFFFF:
        h -= 0x100000000
    if h == -0x80000000:
        return -0x80000000
    return abs(h)


def compute_id_collision_free_offsets(uids: List[str], points: int, interval: int, s_by_mod: Optional[Dict[int, List[int]]] = None) -> tuple[List[int], Dict[int, List[int]]]:
    """
    为 UAV ID 列表计算无碰撞的起始时间偏移。
    返回: (offsets列表, 更新后的s_by_mod)
    """
    MIN_GAP = points * interval + interval
    if s_by_mod is None:
        s_by_mod = {}
    offsets = []
    for uid in uids:
        uhash = compute_java_hash_code(uid)
        mod = uhash % 1000
        if mod not in s_by_mod:
            s_by_mod[mod] = []
        if not s_by_mod[mod]:
            s = uhash
        else:
            s = s_by_mod[mod][-1] + MIN_GAP
        s_by_mod[mod].append(s)
        offsets.append(s - uhash)
    return offsets, s_by_mod


# ==================== 布局生成 ====================
def generate_hex_grid_offsets(n: int, spacing_meters: float, center_lat: float) -> List[tuple[float, float]]:
    """生成 n 个六边形蜂窝网格的经纬度偏移量。"""
    if n <= 0:
        return []

    meters_per_deg_lat = 111320.0
    meters_per_deg_lng = 111320.0 * math.cos(math.radians(center_lat))
    spacing_deg_lng = spacing_meters / meters_per_deg_lng
    spacing_deg_lat = spacing_meters / meters_per_deg_lat

    offsets = [(0.0, 0.0)]
    if n == 1:
        return offsets

    directions = [(1, 0, -1), (0, 1, -1), (-1, 1, 0),
                  (-1, 0, 1), (0, -1, 1), (1, -1, 0)]
    ring = 1
    while len(offsets) < n:
        x, y, z = 0, -ring, ring
        for dx, dy, dz in directions:
            for _ in range(ring):
                lng_offset = (x + z * 0.5) * spacing_deg_lng
                lat_offset = z * (spacing_deg_lat * math.sqrt(3) / 2)
                offsets.append((lng_offset, lat_offset))
                if len(offsets) >= n:
                    return offsets
                x += dx
                y += dy
                z += dz
            if len(offsets) >= n:
                return offsets
        ring += 1
    return offsets[:n]


def generate_line_offsets(n: int, spacing_meters: float, center_lat: float, heading: float, spacing_along: float = 0) -> List[tuple[float, float]]:
    """生成 n 个直线排列的经纬度偏移量，垂直于航向展开。"""
    if n <= 0:
        return []

    meters_per_deg_lat = 111320.0
    meters_per_deg_lng = 111320.0 * math.cos(math.radians(center_lat))
    heading_rad = math.radians(heading)
    perp_heading_rad = heading_rad + math.pi / 2

    offsets = []
    half_n = (n - 1) / 2 if n % 2 == 1 else n / 2

    for i in range(n):
        if n % 2 == 1:
            lateral_idx = i - half_n
        else:
            lateral_idx = i - half_n + 0.5

        lateral_offset = lateral_idx * spacing_meters
        forward_offset = i * spacing_along

        lng_offset = lateral_offset * math.sin(perp_heading_rad) / meters_per_deg_lng
        lat_offset = lateral_offset * math.cos(perp_heading_rad) / meters_per_deg_lat
        lng_offset += forward_offset * math.sin(heading_rad) / meters_per_deg_lng
        lat_offset += forward_offset * math.cos(heading_rad) / meters_per_deg_lat
        offsets.append((lng_offset, lat_offset))

    return offsets


# ==================== 输出与工具 ====================
def save_json(data: List[Dict[str, Any]], path: str) -> None:
    """保存数据为 JSON 文件。"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def print_stats(data: List[Dict[str, Any]]) -> None:
    """打印遥测数据集的统计信息。"""
    if not data:
        print("  数据为空")
        return
    duration_sec = (data[-1]["timestamp"] - data[0]["timestamp"]) / 1000.0
    uav_ids = set(p["uniqueProductIdentificationCode"] for p in data)
    lons = [p["longitude"] for p in data]
    lats = [p["latitude"] for p in data]
    alts = [p["geodeticAltitude"] for p in data]
    print(f"  无人机数量: {len(uav_ids)}")
    print(f"  总轨迹点数: {len(data)}")
    print(f"  时间跨度: {duration_sec:.1f} 秒")
    print(f"  经度范围: {min(lons):.6f} ~ {max(lons):.6f}")
    print(f"  纬度范围: {min(lats):.6f} ~ {max(lats):.6f}")
    if alts:
        print(f"  高度范围: {min(alts):.1f} ~ {max(alts):.1f} 米")


def apply_coord_conversion(data: List[Dict[str, Any]], from_sys: str, to_sys: str) -> None:
    """原地转换数据中的坐标系。"""
    if from_sys.lower() == to_sys.lower():
        return
    for point in data:
        new_lon, new_lat = convert_coordinate(point["longitude"], point["latitude"], from_sys, to_sys)
        point["longitude"] = round(new_lon, 14)
        point["latitude"] = round(new_lat, 14)


# ==================== create 子命令 ====================
def setup_create_parser(subparsers):
    p = subparsers.add_parser("create", help="基础仿真数据生成（redis_route + kafka_data）")
    p.add_argument("--count", type=int, default=10, help="维持活跃无人机数量，默认 10")
    p.add_argument("--origin-lat", type=float, default=None, help="仿真中心纬度")
    p.add_argument("--origin-lon", type=float, default=None, help="仿真中心经度")
    p.add_argument("--sim-radius-m", type=float, default=None, help="仿真有效半径（米）")
    p.add_argument("--output-dir", default=os.path.join(_ROOT, "mock"), help="输出目录")
    return p


def run_create(args):
    if not HAS_SIMULATOR:
        print("[错误] simulation_core 不可用，请确保 simulation_core.py 在路径中")
        sys.exit(1)

    mock_dir = args.output_dir
    os.makedirs(mock_dir, exist_ok=True)
    redis_route_path = os.path.join(mock_dir, "redis_route.json")
    kafka_data_path = os.path.join(mock_dir, "kafka_data.json")

    simulator = Simulator(
        origin_lat=args.origin_lat,
        origin_lon=args.origin_lon,
        sim_radius_m=args.sim_radius_m,
    )
    plans = []
    for _ in range(args.count):
        plans.append(simulator.generate_plan())

    # 加载自定义航线
    custom_route_path = os.path.join(mock_dir, "redis_route_custom.json")
    if os.path.exists(custom_route_path):
        with open(custom_route_path, encoding="utf-8") as f:
            custom_params = json.load(f)
        added = simulator.add_plans(custom_params)
        custom_uids = {item.get("key") or item.get("value", {}).get("uniqueProductIdentificationCode") for item in custom_params}
        plans.extend(agent.plan for uid, agent in simulator.agents.items() if uid in custom_uids)
        print(f"已加载自定义航线: {custom_route_path} (追加 {added} 架)")

    # redis_route
    def plan_to_redis_route(plan):
        route_data = {}
        route_data["uniqueProductIdentificationCode"] = plan.aircraft.uid.decode("utf-8")
        fp = {
            "flightPlanId": 1,
            "planTakeoffTime": plan.start_time,
            "planLandTime": plan.end_time,
            "flightTaskId": 1,
            "flightTaskName": "test",
            "routeList": [],
        }
        if plan.type == 0 and plan.data.traj.count > 0:
            for i in range(0, plan.data.traj.count - 1):
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
        route_data["flightPlanList"] = [fp]
        return {"key": plan.aircraft.uid.decode("utf-8"), "value": route_data}

    redis_route_list = [plan_to_redis_route(p) for p in plans]
    with open(redis_route_path, "w", encoding="utf-8") as f:
        json.dump(redis_route_list, f, ensure_ascii=False, indent=2)
    print(f"已生成: {redis_route_path} (共 {len(redis_route_list)} 条)")

    # kafka_data
    def telemetry_to_kafka_item(t):
        uav_vid = t.uid.decode("utf-8")
        return {
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
            "pressureAltitude": getattr(t, "ressureAltitude", 0.0),
            "operatingStatus": t.operatingStatus,
            "coordinateSystemType": t.coordinateSystemType,
            "horizontalAccuracy": t.horizontalAccuracy,
            "verticalAccuracy": t.verticalAccuracy,
            "speedAccuracy": t.speedAccuracy,
            "timestamp": t.timestamp * 1000,
            "timestampAccuracy": 0,
            "sourceType": t.sourceType if hasattr(t, "sourceType") else 1,
            "addInf": t.addInf if hasattr(t, "addInf") else {},
            "active": 1,
        }

    kafka_data_list = []
    sim_time = min(p.start_time for p in plans) if plans else 0
    step_sec = 1.0
    max_end = max(p.end_time for p in plans) if plans else 0
    max_steps = int(max_end - sim_time) + 600
    steps = 0
    while simulator.agents and steps < max_steps:
        payloads = simulator.step(step_sec, sim_time=sim_time)
        for item in payloads:
            t = item["current"]
            kafka_data_list.append(telemetry_to_kafka_item(t))
        sim_time += step_sec
        steps += 1

    with open(kafka_data_path, "w", encoding="utf-8") as f:
        json.dump(kafka_data_list, f, ensure_ascii=False, indent=2)
    print(f"已生成: {kafka_data_path} (共 {len(kafka_data_list)} 条)")


# ==================== route 子命令 ====================
def setup_route_parser(subparsers):
    p = subparsers.add_parser("route", help="沿航线飞行数据（单UAV，支持偏离/状态变更）")
    p.add_argument("--output-dir", "-o", default=None, help="JSON输出目录")
    p.add_argument("--filename", "-f", default=None, help="输出文件名")
    p.add_argument("--uid", default="DJY20260422001002031", help="无人机唯一识别码")
    p.add_argument("--reg-sign", default=None, help="实名登记标识")
    p.add_argument("--classification", type=int, default=2, help="航空器分类")
    p.add_argument("--route-name", default=None, help="air_route 表航线名称")
    p.add_argument("--route-id", type=int, default=None, help="air_route 表航线ID")
    p.add_argument("--points", default=None, help="关键点序列 lon,lat,alt;...")
    p.add_argument("--start-lon", type=float, default=None)
    p.add_argument("--start-lat", type=float, default=None)
    p.add_argument("--end-lon", type=float, default=None)
    p.add_argument("--end-lat", type=float, default=None)
    p.add_argument("--altitude", "-a", type=float, default=30.0, help="默认飞行高度")
    p.add_argument("--start-alt", type=float, default=None)
    p.add_argument("--end-alt", type=float, default=None)
    p.add_argument("--speed", "-s", type=float, default=15.0)
    p.add_argument("--start-time", type=int, default=None)
    p.add_argument("--interval", type=int, default=1000)
    p.add_argument("--deviate", action="store_true", help="生成偏离航路的轨迹")
    p.add_argument("--deviate-offset", type=float, default=0.001, help="偏离偏移量（度）")
    p.add_argument("--deviate-start-index", type=int, default=5)
    p.add_argument("--operating-status", type=int, default=2)
    p.add_argument("--operating-status-change-time", type=int, default=None)
    p.add_argument("--operating-status-change-index", type=int, default=None)
    p.add_argument("--operating-status-changed", type=int, default=2)
    return p


def _build_waypoints(args) -> List[Dict[str, Any]]:
    """根据参数构建航路点列表。"""
    waypoints: List[Dict[str, Any]] = []

    if args.route_name or args.route_id is not None:
        if not HAS_DB:
            print("[警告] 未安装 dmPython，无法查询数据库航线")
        else:
            routes = query_air_route(route_name=args.route_name, route_id=args.route_id)
            if routes:
                route = routes[0]
                route_id_db = route.get("ID") or route.get("id") or route.get("Id")
                # 优先从 air_route_element 表获取高精度航路坐标点
                if route_id_db is not None:
                    db_points = query_route_elements(route_id_db)
                else:
                    db_points = []
                # 兜底：segment 查不到时，回退到解析 polygon 字段
                if len(db_points) < 2:
                    polygon = route.get("polygon") or route.get("POLYGON") or route.get("Polygon")
                    db_points = parse_polygon(polygon)
                if db_points:
                    base_alt = args.altitude if args.altitude is not None else 30.0
                    for p in db_points:
                        waypoints.append({"lon": p["lon"], "lat": p["lat"], "alt": base_alt})

    if args.points:
        for segment in args.points.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            parts = [float(x.strip()) for x in segment.split(",")]
            if len(parts) >= 2:
                wp = {"lon": parts[0], "lat": parts[1]}
                wp["alt"] = parts[2] if len(parts) >= 3 else (args.altitude if args.altitude is not None else 30.0)
                waypoints.append(wp)

    has_start = args.start_lon is not None and args.start_lat is not None
    has_end = args.end_lon is not None and args.end_lat is not None

    if has_start:
        wp_start = {"lon": args.start_lon, "lat": args.start_lat,
                    "alt": args.start_alt if args.start_alt is not None else (args.altitude if args.altitude is not None else 30.0)}
        if not waypoints:
            waypoints = [wp_start]
            if has_end:
                wp_end = {"lon": args.end_lon, "lat": args.end_lat,
                          "alt": args.end_alt if args.end_alt is not None else (args.altitude if args.altitude is not None else 30.0)}
                waypoints.append(wp_end)
        else:
            first_is_start = abs(waypoints[0]["lon"] - wp_start["lon"]) < 1e-9 and abs(waypoints[0]["lat"] - wp_start["lat"]) < 1e-9
            if not first_is_start:
                waypoints.insert(0, wp_start)
            if has_end:
                wp_end = {"lon": args.end_lon, "lat": args.end_lat,
                          "alt": args.end_alt if args.end_alt is not None else (args.altitude if args.altitude is not None else 30.0)}
                last_is_end = abs(waypoints[-1]["lon"] - wp_end["lon"]) < 1e-9 and abs(waypoints[-1]["lat"] - wp_end["lat"]) < 1e-9
                if not last_is_end:
                    waypoints.append(wp_end)
    return waypoints


def run_route(args):
    output_dir = args.output_dir if args.output_dir else os.path.join(_ROOT, "utm_test_cases", "scenes")
    os.makedirs(output_dir, exist_ok=True)

    waypoints = _build_waypoints(args)
    if len(waypoints) < 2:
        print("[错误] 无法构建有效航路点，至少需要2个点")
        sys.exit(1)

    trajectory = generate_trajectory(
        waypoints=waypoints, uid=args.uid, speed_ms=args.speed,
        start_time_ms=args.start_time, interval_ms=args.interval,
        reg_sign=args.reg_sign, classification=args.classification,
        operating_status=args.operating_status,
    )

    if args.deviate:
        print(f"[信息] 生成偏离轨迹，偏移 {args.deviate_offset}°，从索引 {args.deviate_start_index} 开始")
        for i in range(args.deviate_start_index, len(trajectory)):
            trajectory[i]["longitude"] += args.deviate_offset
            trajectory[i]["latitude"] += args.deviate_offset

    if args.operating_status_change_time is not None and trajectory:
        change_at = trajectory[0]["timestamp"] + args.operating_status_change_time
        for p in trajectory:
            if p["timestamp"] >= change_at:
                p["operatingStatus"] = args.operating_status_changed

    if args.operating_status_change_index is not None and trajectory:
        idx = min(args.operating_status_change_index, len(trajectory))
        for i in range(idx, len(trajectory)):
            trajectory[i]["operatingStatus"] = args.operating_status_changed

    if args.filename:
        filename = args.filename if args.filename.endswith(".json") else args.filename + ".json"
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dev_tag = "_deviate" if args.deviate else ""
        filename = f"UAV_scene_{args.uid}{dev_tag}_{ts}.json"

    output_path = os.path.join(output_dir, filename)
    save_json(trajectory, output_path)
    print(f"\n[完成] 输出: {output_path}")
    print_stats(trajectory)


# ==================== deviate 子命令 ====================
def setup_deviate_parser(subparsers):
    p = subparsers.add_parser("deviate", help="偏离航路告警（水平/垂直/both，平滑渐变）")
    p.add_argument("--route-name", default="铁门关至吐鲁番", help="航线名称")
    p.add_argument("--route-id", default=None, help="直接指定航线ID")
    p.add_argument("--uid-offset", type=int, default=1, help="UAV ID起始偏移")
    p.add_argument("--classification", type=int, default=3)
    p.add_argument("--speed", type=float, default=15.0)
    p.add_argument("--altitude", type=float, default=None)
    p.add_argument("--deviate-offset", type=float, default=3000.0, help="偏离航道数值（米）")
    p.add_argument("--deviate-start", type=int, default=20, help="第几秒开始偏离")
    p.add_argument("--deviate-transition", type=int, default=None, help="偏离渐变时间（秒）")
    p.add_argument("--deviate-altitude-offset", type=float, default=0.0, help="高度偏离（米）")
    p.add_argument("--deviate-mode", type=str, default="horizontal", choices=["horizontal", "vertical", "both"])
    p.add_argument("--coord-system", default="wgs84", choices=["wgs84", "gcj02", "bd09"])
    p.add_argument("--coord-output", default=None)
    p.add_argument("--output-dir", default=os.path.join(_ROOT, "mock"))
    p.add_argument("--filename", default=None)
    return p


def _smooth_angles(angles: List[float], window: int = 5) -> List[float]:
    n = len(angles)
    if n <= 1:
        return angles[:]
    result = []
    half = window // 2
    for i in range(n):
        window_angles = []
        for j in range(max(0, i - half), min(n, i + half + 1)):
            h = angles[j]
            while h - angles[i] > 180:
                h -= 360
            while h - angles[i] < -180:
                h += 360
            window_angles.append(h)
        avg = sum(window_angles) / len(window_angles)
        result.append(avg % 360)
    return result


def _offset_point(lat: float, lon: float, heading_deg: float, offset_m: float) -> tuple[float, float]:
    perp_heading = math.radians(heading_deg + 90)
    dn = offset_m * math.cos(perp_heading)
    de = offset_m * math.sin(perp_heading)
    d_lat = dn / RE_EARTH
    d_lon = de / (RE_EARTH * math.cos(math.radians(lat)))
    return lat + math.degrees(d_lat), lon + math.degrees(d_lon)


def run_deviate(args):
    pool = get_uav_id_pool()
    if not pool:
        print("[错误] 无法加载 UAV_IDENTIFIERS_EXTENDED")
        sys.exit(1)
    uid_offset = args.uid_offset % len(pool)
    uid, reg_sign = pool[uid_offset]
    print(f"[信息] 使用 UAV ID: {uid}, 实名登记: {reg_sign}")

    if args.route_id is not None:
        route_record = {"id": args.route_id}
    else:
        route_record = query_air_route_single(route_name=args.route_name)
        if not route_record:
            print(f"[错误] 无法获取航线 '{args.route_name}' 的数据")
            sys.exit(1)

    route_name_db = (route_record.get("route_name") or route_record.get("ROUTE_NAME")
                     or route_record.get("NAME") or args.route_name)
    min_safe_alt = (route_record.get("minimum_safe_altitude") or route_record.get("MINIMUM_SAFE_ALTITUDE")
                    or route_record.get("Minimum_Safe_Altitude"))
    vert_alt = route_record.get("vertical_altitude") or route_record.get("VERTICAL_ALTITUDE")
    width = route_record.get("width") or route_record.get("WIDTH")
    route_id_db = route_record.get("ID") or route_record.get("id") or route_record.get("Id")

    route_points = []
    if route_id_db is not None:
        route_points = query_route_elements(route_id_db)
    if len(route_points) < 2:
        polygon_val = route_record.get("polygon") or route_record.get("POLYGON") or route_record.get("Polygon")
        route_points = parse_polygon(polygon_val)

    if len(route_points) < 2:
        print("[错误] 航线航路点不足 2 个")
        sys.exit(1)

    if len(route_points) > 2:
        start_pt = route_points[0]
        for i in range(1, len(route_points)):
            dist = geo_distance(start_pt["lat"], start_pt["lon"], route_points[i]["lat"], route_points[i]["lon"])
            if dist < 500:
                route_points = route_points[:i]
                break

    print(f"[信息] 解析到 {len(route_points)} 个航路点")

    if args.altitude is not None:
        altitude = args.altitude
    else:
        try:
            min_alt = float(min_safe_alt) if min_safe_alt is not None else 0
            vert_alt_val = float(vert_alt) if vert_alt is not None else 0
            altitude = int((min_alt + vert_alt_val) / 2)
        except (ValueError, TypeError):
            altitude = 30

    try:
        width_val = float(width) if width is not None else 0
        if args.deviate_offset == 0:
            actual_offset = 0.0
        else:
            actual_offset = width_val / 2 + args.deviate_offset
    except (ValueError, TypeError):
        actual_offset = args.deviate_offset

    if args.deviate_transition is not None and args.deviate_transition > 0:
        transition_sec = args.deviate_transition
    else:
        transition_sec = max(5, min(60, int(actual_offset / args.speed)))

    start_time_ms = int(datetime.now().timestamp() * 1000)
    traj_center = interpolate_route(route_points, args.speed, start_time_ms)
    raw_headings = [p["heading"] for p in traj_center]
    smooth_headings = _smooth_angles(raw_headings, window=5)

    need_horizontal = args.deviate_mode in ("horizontal", "both") and actual_offset != 0
    need_vertical = args.deviate_mode in ("vertical", "both") and args.deviate_altitude_offset != 0
    deviate_start_ms = start_time_ms + args.deviate_start * 1000
    transition_end_ms = deviate_start_ms + transition_sec * 1000

    trajectory = []
    for i, center_pt in enumerate(traj_center):
        t = center_pt["time_ms"]
        if t < deviate_start_ms:
            trajectory.append(dict(center_pt))
            trajectory[-1]["heading"] = smooth_headings[i]
            trajectory[-1]["altitude_offset"] = 0.0
        elif t >= transition_end_ms:
            new_lat, new_lon = center_pt["lat"], center_pt["lon"]
            if need_horizontal:
                new_lat, new_lon = _offset_point(new_lat, new_lon, smooth_headings[i], actual_offset)
            alt_offset = args.deviate_altitude_offset if need_vertical else 0.0
            trajectory.append({
                "lat": new_lat, "lon": new_lon, "heading": smooth_headings[i],
                "time_ms": t, "segment_idx": center_pt.get("segment_idx", -1),
                "altitude_offset": alt_offset,
            })
        else:
            ratio = (t - deviate_start_ms) / (transition_sec * 1000.0) if transition_sec > 0 else 1.0
            new_lat, new_lon = center_pt["lat"], center_pt["lon"]
            if need_horizontal:
                new_lat, new_lon = _offset_point(new_lat, new_lon, smooth_headings[i], actual_offset * ratio)
            alt_offset = args.deviate_altitude_offset * ratio if need_vertical else 0.0
            trajectory.append({
                "lat": new_lat, "lon": new_lon, "heading": smooth_headings[i],
                "time_ms": t, "segment_idx": center_pt.get("segment_idx", -1),
                "altitude_offset": alt_offset,
            })

    telemetry_data = []
    for point in trajectory:
        point_altitude = altitude + point.get("altitude_offset", 0.0)
        telemetry_data.append(make_telemetry_point(
            uid=uid, reg_sign=reg_sign, timestamp_ms=point["time_ms"],
            lon=point["lon"], lat=point["lat"], alt=point_altitude,
            speed=args.speed, heading=point["heading"], status=2,
            classification=args.classification,
        ))

    coord_from = args.coord_system.lower()
    coord_to = (args.coord_output or coord_from).lower()
    apply_coord_conversion(telemetry_data, coord_from, coord_to)

    os.makedirs(args.output_dir, exist_ok=True)
    if args.filename:
        filename = args.filename if args.filename.endswith(".json") else args.filename + ".json"
    else:
        safe_name = (route_name_db or args.route_name or f"route_{args.route_id}").replace(" ", "").replace("/", "_")
        filename = f"{safe_name}航路偏航数据_0.1.json"

    output_path = os.path.join(args.output_dir, filename)
    save_json(telemetry_data, output_path)
    print(f"\n[完成] 输出: {output_path}")
    print_stats(telemetry_data)


# ==================== parallel 子命令 ====================
def setup_parallel_parser(subparsers):
    p = subparsers.add_parser("parallel", help="大规模平行飞行（六边形/直线布局，ID碰撞避让）")
    p.add_argument("--center-lng", type=float, default=85.070136, help="中心点经度")
    p.add_argument("--center-lat", type=float, default=40.818724, help="中心点纬度")
    p.add_argument("--altitude", "-a", type=float, default=50.0, help="飞行高度")
    p.add_argument("--speed", "-s", type=float, default=15.0)
    p.add_argument("--heading", type=float, default=90.0, help="航向角: 0=北,90=东")
    p.add_argument("--count", "-n", type=int, default=30, help="无人机数量")
    p.add_argument("--spacing", type=float, default=2000, help="横向间距(米)")
    p.add_argument("--spacing-along", type=float, default=0, help="前后间距(米)")
    p.add_argument("--layout", type=str, default="hex", choices=["hex", "line"])
    p.add_argument("--sim-radius", type=float, default=100000.0, help="仿真有效半径")
    p.add_argument("--classification", type=int, default=2)
    p.add_argument("--points", "-p", type=int, default=1200, help="每架无人机轨迹点数")
    p.add_argument("--interval", type=int, default=1000, help="采样间隔(毫秒)")
    p.add_argument("--start-time", type=int, default=None, help="起始时间戳(毫秒)")
    p.add_argument("--output", "-o", default="../data/mock/kafka_data_parallel.json", help="输出文件路径")
    p.add_argument("--uid-offset", type=int, default=0, help="UAV ID起始偏移")
    p.add_argument("--multi", action="store_true", help="分3区域生成3个JSON")
    return p


def run_parallel(args, uid_offset_override=None, s_by_mod_override=None, start_time_override=None):
    """支持外部调用来覆盖部分参数（用于batch模式）。"""
    count = args.count
    if count > len(UAV_IDENTIFIERS_EXTENDED):
        print(f"[错误] 请求数量 {count} 超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
        sys.exit(1)

    uid_offset = uid_offset_override if uid_offset_override is not None else args.uid_offset
    s_by_mod = s_by_mod_override if s_by_mod_override is not None else None
    base_time = start_time_override if start_time_override is not None else (args.start_time if args.start_time else int(datetime.now().timestamp() * 1000))
    base_time = (base_time // 1000) * 1000

    if args.layout == "line":
        offsets = generate_line_offsets(count, args.spacing, args.center_lat, args.heading, args.spacing_along)
    else:
        offsets = generate_hex_grid_offsets(count, args.spacing, args.center_lat)

    step_meters = args.speed * (args.interval / 1000.0)
    heading_rad = math.radians(args.heading)
    dn = step_meters * math.cos(heading_rad)
    de = step_meters * math.sin(heading_rad)
    meters_per_deg_lat = 111320.0
    meters_per_deg_lng = 111320.0 * math.cos(math.radians(args.center_lat))
    d_lat = dn / meters_per_deg_lat
    d_lng = de / meters_per_deg_lng

    altitudes = []
    enable_groups = getattr(args, 'enable_altitude_groups', False)
    if enable_groups and hasattr(args, 'altitude_groups') and args.altitude_groups:
        for group in args.altitude_groups:
            altitudes.extend([group.get("altitude", args.altitude)] * group.get("count", 0))
    if not altitudes:
        altitudes = [args.altitude] * count
    altitudes = altitudes[:count]
    while len(altitudes) < count:
        altitudes.append(args.altitude)

    uids = [UAV_IDENTIFIERS_EXTENDED[::-1][(uid_offset + i) % len(UAV_IDENTIFIERS_EXTENDED)][0] for i in range(count)]
    start_offsets, s_by_mod = compute_id_collision_free_offsets(uids, args.points, args.interval, s_by_mod)

    all_data = []
    for i in range(count):
        uid, reg_sign = UAV_IDENTIFIERS_EXTENDED[::-1][(uid_offset + i) % len(UAV_IDENTIFIERS_EXTENDED)]
        offset_x, offset_y = offsets[i]
        start_lng = args.center_lng + offset_x
        start_lat = args.center_lat + offset_y
        for p in range(args.points):
            ts = base_time + start_offsets[i] + p * args.interval
            lon = start_lng + p * d_lng
            lat = start_lat + p * d_lat
            all_data.append(make_telemetry_point(
                uid, reg_sign, ts, lon, lat, altitudes[i], args.speed, args.heading, args.classification
            ))
        if (i + 1) % 500 == 0:
            print(f"  已生成 {i + 1} 架...")

    all_data.sort(key=lambda x: x["timestamp"])
    output_path = os.path.join(_ROOT, args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    save_json(all_data, output_path)
    print(f"\n[完成] 输出: {output_path}")
    print_stats(all_data)
    return s_by_mod


# ==================== scale 子命令 ====================
def setup_scale_parser(subparsers):
    p = subparsers.add_parser("scale", help="基于模板批量扩展（蜂窝网格分布）")
    p.add_argument("--source", default="../data/mock/kafka_data_yfk.json", help="源JSON文件路径")
    p.add_argument("--count", type=int, default=100, help="目标无人机数量")
    p.add_argument("--center-lng", type=float, default=89.2306)
    p.add_argument("--center-lat", type=float, default=38.19424)
    p.add_argument("--spacing", type=float, default=300, help="相邻无人机间距(米)")
    p.add_argument("--output", "-o", default="../data/mock/kafka_data_alarm_100.json")
    return p


def run_scale(args):
    source_path = os.path.join(_ROOT, args.source)
    with open(source_path, 'r', encoding='utf-8') as f:
        original_data = json.load(f)

    uav_trajectories = {}
    for point in original_data:
        uav_id = point['uniqueProductIdentificationCode']
        uav_trajectories.setdefault(uav_id, []).append(point)

    print(f"原始数据: {len(original_data)} 个轨迹点, {len(uav_trajectories)} 架无人机")

    METERS_PER_DEGREE_LAT = 111320.0
    METERS_PER_DEGREE_LNG = 111320.0 * math.cos(math.radians(args.center_lat))
    SPACING_DEG_LNG = args.spacing / METERS_PER_DEGREE_LNG
    SPACING_DEG_LAT = args.spacing / METERS_PER_DEGREE_LAT

    offsets = generate_hex_grid_offsets(args.count, args.spacing, args.center_lat)
    base_uav_ids = list(uav_trajectories.keys())
    num_base = len(base_uav_ids)
    all_data = []

    for i in range(args.count):
        base_id = base_uav_ids[i % num_base]
        base_trajectory = uav_trajectories[base_id]
        new_uav_id = f"UAV_{i+1:06d}"
        offset_x, offset_y = offsets[i]

        for point in base_trajectory:
            new_point = point.copy()
            new_point['uniqueProductIdentificationCode'] = new_uav_id
            new_point['realNameRegistrationSign'] = new_uav_id
            new_point['longitude'] = round(args.center_lng + offset_x, 6)
            new_point['latitude'] = round(args.center_lat + offset_y, 6)
            new_point['timestamp'] = point['timestamp'] + int(offset_x * 1000) + int(offset_y * 1000) + i * 1000
            all_data.append(new_point)

        if (i + 1) % 500 == 0:
            print(f"  已生成 {i+1} 架...")

    all_data.sort(key=lambda x: x['timestamp'])
    output_path = os.path.join(_ROOT, args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    save_json(all_data, output_path)
    print(f"\n[完成] 输出: {output_path} ({len(all_data)} 个轨迹点)")


# ==================== collision 子命令 ====================
def setup_collision_parser(subparsers):
    p = subparsers.add_parser("collision", help="碰撞预警（交汇点检测、同步到达、区域标记）")
    p.add_argument("--route-names", default="跨顺义三河段,三河区航路", help="航线名称列表，逗号分隔")
    p.add_argument("--route-id", default=None, help="指定航线ID（单条航线时）")
    p.add_argument("--uids", default="CW000000000000000004,CH000000000000000003", help="指定UAV ID列表")
    p.add_argument("--uid-start-offset", type=int, default=0)
    p.add_argument("--classification", type=int, default=2)
    p.add_argument("--altitude", type=float, default=None)
    p.add_argument("--meeting-threshold", type=float, default=10.0, help="交汇点距离阈值(米)")
    p.add_argument("--warning-time", type=int, default=20, help="告警开始时间(秒)")
    p.add_argument("--collision-time", type=float, default=300, help="目标碰撞时间(秒)")
    p.add_argument("--zone-output", action="store_true", default=True, help="输出区域标记")
    p.add_argument("--output-dir", default=os.path.join(_ROOT, "mock"))
    p.add_argument("--interval", type=int, default=1000)
    return p


def _find_meeting_points(points_a, points_b, threshold_meters=30.0):
    meeting_points = []
    for i, pt_a in enumerate(points_a):
        min_dist = float('inf')
        min_idx_b = -1
        for j, pt_b in enumerate(points_b):
            dist = geo_distance(pt_a["lat"], pt_a["lon"], pt_b["lat"], pt_b["lon"])
            if dist < min_dist:
                min_dist = dist
                min_idx_b = j
        if min_dist <= threshold_meters and min_idx_b >= 0:
            pt_b = points_b[min_idx_b]
            meeting_points.append({
                "idx_a": i, "idx_b": min_idx_b,
                "point_a": pt_a, "point_b": pt_b,
                "distance": min_dist,
                "lon": (pt_a["lon"] + pt_b["lon"]) / 2,
                "lat": (pt_a["lat"] + pt_b["lat"]) / 2,
            })
    if not meeting_points:
        return []
    merged = [meeting_points[0]]
    for mp in meeting_points[1:]:
        last = merged[-1]
        if abs(mp["idx_a"] - last["idx_a"]) < 10 and abs(mp["idx_b"] - last["idx_b"]) < 10:
            if mp["distance"] < last["distance"]:
                merged[-1] = mp
        else:
            merged.append(mp)
    return merged


def _route_distance_to_point(route_points, target_idx):
    if target_idx <= 0:
        return 0.0
    total = 0.0
    for i in range(min(target_idx, len(route_points) - 1)):
        total += geo_distance(route_points[i]["lat"], route_points[i]["lon"], route_points[i+1]["lat"], route_points[i+1]["lon"])
    return total


def run_collision(args):
    route_names = [name.strip() for name in args.route_names.split(",") if name.strip()]
    if len(route_names) < 2:
        print("[错误] 碰撞预警模式需要至少2条航线")
        sys.exit(1)

    print(f"[碰撞预警模式] 共 {len(route_names)} 条航线")
    route_data_list = []
    for route_name in route_names:
        route_record = query_air_route_single(route_name)
        if not route_record:
            print(f"[错误] 无法获取航线 '{route_name}'")
            sys.exit(1)
        route_id_db = route_record.get("ID") or route_record.get("id") or route_record.get("Id")
        route_points = query_route_elements(route_id_db) if route_id_db else []
        if len(route_points) < 2:
            polygon_val = route_record.get("polygon") or route_record.get("POLYGON") or route_record.get("Polygon")
            route_points = parse_polygon(polygon_val)
        if len(route_points) < 2:
            print(f"[错误] 航线 '{route_name}' 航路点不足")
            sys.exit(1)
        route_data_list.append({"name": route_name, "record": route_record, "points": route_points})

    print(f"[碰撞预警模式] 检测航线 '{route_data_list[0]['name']}' 与 '{route_data_list[1]['name']}' 之间的交汇点")
    meeting_points = _find_meeting_points(route_data_list[0]["points"], route_data_list[1]["points"], args.meeting_threshold)
    if not meeting_points:
        print("[错误] 未找到交汇点")
        sys.exit(1)

    best_meeting = meeting_points[0]
    print(f"[碰撞预警模式] 交汇点: lon={best_meeting['lon']:.6f}, lat={best_meeting['lat']:.6f}, 距离={best_meeting['distance']:.1f}米")

    collision_target = args.collision_time
    dist_a = _route_distance_to_point(route_data_list[0]["points"], best_meeting["idx_a"])
    dist_b = _route_distance_to_point(route_data_list[1]["points"], best_meeting["idx_b"])
    speed_a = dist_a / collision_target
    speed_b = dist_b / collision_target
    meeting_speeds = [speed_a, speed_b]
    print(f"[碰撞预警模式] 航线A距离: {dist_a:.1f}m, 速度: {speed_a:.2f}m/s")
    print(f"[碰撞预警模式] 航线B距离: {dist_b:.1f}m, 速度: {speed_b:.2f}m/s")

    base_time_ms = int(datetime.now().timestamp() * 1000)
    meeting_time_ms = base_time_ms + int(collision_target * 1000)
    uid_list = [u.strip() for u in args.uids.split(",") if u.strip()] if args.uids else []
    pool = get_uav_id_pool()

    success_count = 0
    for idx, route_data in enumerate(route_data_list):
        route_name = route_data["name"]
        route_points = route_data["points"]
        speed_ms = meeting_speeds[idx]

        route_record = route_data["record"]
        min_safe_alt = (route_record.get("minimum_safe_altitude") or route_record.get("MINIMUM_SAFE_ALTITUDE")
                        or route_record.get("Minimum_Safe_Altitude"))
        vert_alt = route_record.get("vertical_altitude") or route_record.get("VERTICAL_ALTITUDE")
        if args.altitude is not None:
            flight_altitude = args.altitude
        else:
            try:
                min_alt = float(min_safe_alt) if min_safe_alt is not None else 0
                vert_alt_val = float(vert_alt) if vert_alt is not None else 0
                flight_altitude = int((min_alt + vert_alt_val) / 2)
            except (ValueError, TypeError):
                flight_altitude = 30

        specified_uid = uid_list[idx] if idx < len(uid_list) else None
        if specified_uid is None:
            actual_offset = (args.uid_start_offset + idx) % len(pool)
            specified_uid, _ = pool[actual_offset]

        actual_reg_sign = specified_uid
        for u, rs in UAV_IDENTIFIERS_EXTENDED:
            if u == specified_uid:
                actual_reg_sign = rs
                break

        print(f"\n[信息] 处理航线: {route_name}, UAV ID: {specified_uid}, 速度: {speed_ms:.2f}m/s")

        traj = interpolate_route(route_points, speed_ms, base_time_ms, args.interval)
        telemetry_data = []
        for point in traj:
            warning_start = meeting_time_ms - args.warning_time * 1000
            if point["time_ms"] < warning_start:
                zone = 1
            elif point["time_ms"] < meeting_time_ms:
                zone = 2
            else:
                zone = 3
            status = 3 if zone == 2 else 2
            tp = make_telemetry_point(
                uid=specified_uid, reg_sign=actual_reg_sign, timestamp_ms=point["time_ms"],
                lon=point["lon"], lat=point["lat"], alt=flight_altitude,
                speed=speed_ms, heading=point["heading"], status=status,
                classification=args.classification,
            )
            if args.zone_output:
                tp["zone"] = zone
            telemetry_data.append(tp)

        zone_counts = {1: 0, 2: 0, 3: 0}
        for point in telemetry_data:
            z = point.get("zone", 0)
            if z in zone_counts:
                zone_counts[z] += 1
        print(f"[信息] 区域统计: 飞行期1={zone_counts[1]}点, 告警期={zone_counts[2]}点, 飞行区={zone_counts[3]}点")

        os.makedirs(args.output_dir, exist_ok=True)
        safe_route_name = route_name.replace(" ", "").replace("/", "_")
        filename = f"{safe_route_name}_碰撞预警_{specified_uid}.json"
        output_path = os.path.join(args.output_dir, filename)
        save_json(telemetry_data, output_path)
        print(f"[完成] 输出: {output_path} ({len(telemetry_data)} 条)")
        success_count += 1

    print(f"\n[总结] 碰撞预警模式完成，成功生成 {success_count} 个文件")


# ==================== status 子命令 ====================
def setup_status_parser(subparsers):
    p = subparsers.add_parser("status", help="飞行器状态告警（紧急/丢失/紧急后丢失）")
    p.add_argument("--count", type=int, default=1, help="UAV数量")
    p.add_argument("--center-lng", type=float, default=120.7418)
    p.add_argument("--center-lat", type=float, default=31.3689)
    p.add_argument("--altitude", type=float, default=50.0)
    p.add_argument("--speed", type=float, default=15.0)
    p.add_argument("--heading", type=float, default=90.0)
    p.add_argument("--interval", type=int, default=1000)
    p.add_argument("--ground-seconds", type=int, default=0)
    p.add_argument("--climb-seconds", type=int, default=0)
    p.add_argument("--flight-minutes", type=int, default=1)
    p.add_argument("--emergency-count", type=int, default=5, help="紧急状态数据条数(1~10)")
    p.add_argument("--spacing", type=float, default=2000, help="多架UAV横向间距(米)")
    p.add_argument("--classification", type=int, default=2)
    p.add_argument("--sim-radius", type=float, default=100000.0)
    p.add_argument("--id-offset", type=int, default=None, help="ID起始偏移")
    p.add_argument("--scene3", action="store_true", help="状态3: 紧急后恢复")
    p.add_argument("--scene5", action="store_true", help="状态5: 丢失")
    p.add_argument("--scene3-5", action="store_true", help="状态3转5: 紧急后丢失")
    p.add_argument("--output-dir", default=os.path.join(_ROOT, "mock"))
    return p


_ID_OFFSET_RECORD = os.path.join(_SCRIPT_DIR, ".last_id_offset")


def _get_next_id_offset(total_needed, pool_size):
    offset = 0
    if os.path.exists(_ID_OFFSET_RECORD):
        try:
            with open(_ID_OFFSET_RECORD, "r", encoding="utf-8") as f:
                offset = int(f.read().strip())
        except (ValueError, IOError):
            offset = 0
    offset = offset % pool_size
    next_offset = (offset + total_needed) % pool_size
    try:
        with open(_ID_OFFSET_RECORD, "w", encoding="utf-8") as f:
            f.write(str(next_offset))
    except IOError:
        pass
    return offset


def _generate_status_scene_data(uid, reg_sign, start_lng, start_lat, altitude, speed, heading,
                                interval_ms, ground_s, climb_s, flight_min, emergency_cnt, scene_type, classification):
    trajectory = []
    base_time = int(datetime.now().timestamp() * 1000)
    d_lat, d_lon = calc_step_offsets(speed, heading, start_lat)

    # 阶段1: 地面 status=1
    for i in range(ground_s):
        ts = base_time + i * interval_ms
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, start_lng, start_lat, 0.0, 0.0, 0.0, 1, classification))

    # 阶段2: 爬升 status=2
    for i in range(climb_s):
        ts = base_time + (ground_s + i) * interval_ms
        p = (i + 1) / climb_s if climb_s > 0 else 1
        alt = altitude * p
        lon = start_lng + d_lon * i * 0.3
        lat = start_lat + d_lat * i * 0.3
        spd = speed * p
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, alt, spd, heading, 2, classification))

    # 阶段3: 巡航 status=2
    flight_s = int(flight_min * 60)
    base_idx = ground_s + climb_s
    for i in range(flight_s):
        ts = base_time + (base_idx + i) * interval_ms
        lon = start_lng + d_lon * (climb_s * 0.3 + i)
        lat = start_lat + d_lat * (climb_s * 0.3 + i)
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 2, classification))

    # 阶段4: 告警
    base_idx = ground_s + climb_s + flight_s
    if scene_type == 3:
        for i in range(emergency_cnt):
            ts = base_time + (base_idx + i) * interval_ms
            lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + i)
            lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + i)
            trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 3, classification))
        base_idx += emergency_cnt
        for i in range(60):
            ts = base_time + (base_idx + i) * interval_ms
            lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + emergency_cnt + i)
            lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + emergency_cnt + i)
            trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 2, classification))
    elif scene_type == 5:
        ts = base_time + base_idx * interval_ms
        lon = start_lng + d_lon * (climb_s * 0.3 + flight_s)
        lat = start_lat + d_lat * (climb_s * 0.3 + flight_s)
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 5, classification))
    elif scene_type == '3_5':
        for i in range(emergency_cnt):
            ts = base_time + (base_idx + i) * interval_ms
            lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + i)
            lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + i)
            trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 3, classification))
        base_idx += emergency_cnt
        ts = base_time + base_idx * interval_ms
        lon = start_lng + d_lon * (climb_s * 0.3 + flight_s + emergency_cnt)
        lat = start_lat + d_lat * (climb_s * 0.3 + flight_s + emergency_cnt)
        trajectory.append(make_telemetry_point(uid, reg_sign, ts, lon, lat, altitude, speed, heading, 5, classification))

    return trajectory


def run_status(args):
    scenes = []
    if args.scene3:
        scenes.append(("飞行器丢失状态3.json", 3, "状态3(紧急后恢复)"))
    if args.scene5:
        scenes.append(("飞行器丢失状态5.json", 5, "状态5(丢失)"))
    if args.scene3_5:
        scenes.append(("飞行器丢失状态3-5.json", '3_5', "状态3转5(紧急后丢失)"))

    if not scenes:
        print("[警告] 没有启用的场景，请通过 --scene3 / --scene5 / --scene3-5 指定")
        return

    total_needed = args.count * len(scenes)
    pool = get_uav_id_pool()
    if not pool:
        print("[错误] UAV ID池为空")
        return

    if args.id_offset is not None:
        id_offset = args.id_offset % len(pool)
        print(f"[手动指定] ID偏移: {id_offset}")
    else:
        id_offset = _get_next_id_offset(total_needed, len(pool))
        print(f"[自动递增] ID偏移: {id_offset}")

    all_uav_ids = get_uav_ids(id_offset, total_needed)
    if total_needed > len(pool):
        print(f"[错误] 总需求 {total_needed} 超过扩展ID上限 {len(pool)}")
        return

    meters_per_deg_lat = 111320.0
    meters_per_deg_lng = 111320.0 * math.cos(math.radians(args.center_lat))
    spacing_deg_lng = args.spacing / meters_per_deg_lng
    spacing_deg_lat = args.spacing / meters_per_deg_lat
    heading_rad = math.radians(args.heading)
    perp_heading_rad = heading_rad + math.pi / 2

    for scene_idx, (filename, scene_type, label) in enumerate(scenes):
        all_data = []
        half_n = (args.count - 1) / 2 if args.count % 2 == 1 else args.count / 2
        scene_offset_meters = scene_idx * args.spacing * (args.count + 1)
        scene_offset_lng = scene_offset_meters * math.sin(perp_heading_rad) / meters_per_deg_lng
        scene_offset_lat = scene_offset_meters * math.cos(perp_heading_rad) / meters_per_deg_lat
        scene_center_lng = args.center_lng + scene_offset_lng
        scene_center_lat = args.center_lat + scene_offset_lat

        start_idx = scene_idx * args.count
        uav_list = all_uav_ids[start_idx:start_idx + args.count]
        print(f"  [{label}] 使用 UAV ID: {[u[0] for u in uav_list]}")

        for idx, (uid, reg_sign) in enumerate(uav_list):
            if args.count % 2 == 1:
                lateral_idx = idx - half_n
            else:
                lateral_idx = idx - half_n + 0.5
            offset_lng = lateral_idx * spacing_deg_lng * math.sin(perp_heading_rad)
            offset_lat = lateral_idx * spacing_deg_lat * math.cos(perp_heading_rad)
            data = _generate_status_scene_data(
                uid, reg_sign, scene_center_lng + offset_lng, scene_center_lat + offset_lat,
                args.altitude, args.speed, args.heading, args.interval,
                args.ground_seconds, args.climb_seconds, args.flight_minutes,
                args.emergency_count, scene_type, args.classification
            )
            all_data.extend(data)

        path = os.path.join(args.output_dir, filename)
        os.makedirs(args.output_dir, exist_ok=True)
        save_json(all_data, path)
        print(f"[{label}] {path} ({len(all_data)} 条)")


# ==================== check-id 子命令 ====================
def setup_check_id_parser(subparsers):
    p = subparsers.add_parser("check-id", help="ID碰撞检测（Java hashCode模拟）")
    p.add_argument("--files", nargs="+", default=None,
                   help="检测的文件路径列表，默认检测 mock/kafka_data_scene2.json ~ scene11.json")
    p.add_argument("--mock-dir", default=os.path.join(_ROOT, "mock"), help="mock数据目录")
    return p


def _java_hash_code(s: str) -> int:
    h = 0
    for ch in s:
        h = (31 * h + ord(ch)) & 0xFFFFFFFF
    if h > 0x7FFFFFFF:
        h -= 0x100000000
    return h


def _java_math_abs(n: int) -> int:
    if n == -0x80000000:
        return -0x80000000
    return abs(n)


def _generate_backend_id(identify_code: str, timestamp: int) -> str:
    h = _java_math_abs(_java_hash_code(identify_code))
    return str(h + timestamp)


def run_check_id(args):
    mock_dir = args.mock_dir
    if args.files:
        files = args.files
    else:
        # 从 BATCH_CONFIGS 获取输出文件名
        files = [os.path.join(mock_dir, os.path.basename(cfg['output'])) for cfg in BATCH_CONFIGS]

    all_records = []
    for fpath in files:
        if not os.path.exists(fpath):
            print(f"[警告] 文件不存在，已跳过: {fpath}")
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            all_records.extend(json.load(f))

    print(f"总记录数: {len(all_records)}")
    id_to_sources = defaultdict(list)
    for item in all_records:
        code = item.get('uniqueProductIdentificationCode', '')
        ts = item.get('timestamp', 0)
        gid = _generate_backend_id(code, ts)
        id_to_sources[gid].append((code, ts))

    duplicates = {k: v for k, v in id_to_sources.items() if len(v) > 1}
    dup_records_count = sum(len(v) for v in duplicates.values())

    print(f"生成 ID 数量: {len(all_records)}")
    print(f"唯一 ID 数量: {len(id_to_sources)}")
    print(f"重复生成的ID值数量: {len(duplicates)}")
    print(f"涉及重复的记录数: {dup_records_count}")

    same_code_same_ts = 0
    same_code_diff_ts = 0
    diff_code = 0
    for gid, sources in duplicates.items():
        codes = [s[0] for s in sources]
        tss = [s[1] for s in sources]
        if len(set(codes)) == 1 and len(set(tss)) == 1:
            same_code_same_ts += len(sources)
        elif len(set(codes)) == 1:
            same_code_diff_ts += len(sources)
        else:
            diff_code += len(sources)

    print(f"\n重复类型分布:")
    print(f"  同identifyCode + 同timestamp: {same_code_same_ts}条")
    print(f"  同identifyCode + 不同timestamp: {same_code_diff_ts}条")
    print(f"  不同identifyCode碰撞: {diff_code}条")

    print(f"\n不同identifyCode导致重复的示例:")
    count = 0
    for gid, sources in duplicates.items():
        codes = [s[0] for s in sources]
        if len(set(codes)) > 1:
            count += 1
            print(f"  生成ID={gid}")
            for code, ts in sources[:5]:
                print(f"    {code} @ {ts}")
            if count >= 5:
                break
    if count == 0:
        print("  无（所有重复均为同identifyCode同timestamp的重复记录）")


# ==================== check-uid 子命令 ====================
def setup_check_uid_parser(subparsers):
    p = subparsers.add_parser("check-uid", help="UID数据库存在性检查")
    p.add_argument("--file", default="../data/mock/kafka_data_parallel.json", help="JSON文件路径")
    return p


def run_check_uid(args):
    json_path = os.path.join(_ROOT, args.file)
    if not os.path.exists(json_path):
        print(f"[错误] 文件不存在: {json_path}")
        sys.exit(1)

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    uids = sorted(set(d['uniqueProductIdentificationCode'] for d in data))
    print(f"JSON中的UID数量: {len(uids)}")
    print('前5个UID:', uids[:5])

    if not HAS_DB:
        print("[错误] 数据库客户端不可用")
        sys.exit(1)

    client = DmDbClient()
    if not client.connect():
        sys.exit(1)

    id_col = None
    for c in ['identify_code', 'unique_product_identification_code']:
        try:
            test_sql = f"SELECT {c} FROM uav_info WHERE ROWNUM = 0"
            client.execute(test_sql)
            id_col = c
            print(f'\n找到字段: {c}')
            break
        except Exception:
            continue

    if not id_col:
        print('\n未找到航空器识别码字段')
        client.close()
        sys.exit(1)

    in_clause = ', '.join([f"'{u}'" for u in uids])
    sql = f"SELECT {id_col} FROM uav_info WHERE {id_col} IN ({in_clause})"
    result = client.execute(sql)
    found = set(r[id_col] for r in result) if result else set()
    print(f'\n数据库中存在: {len(found)} / {len(uids)}')

    missing = [u for u in uids if u not in found]
    if missing:
        print(f'\n不存在的UID ({len(missing)}个):')
        for u in missing:
            print(f'  {u}')
    else:
        print('\n全部UID均已存在于数据库')
    client.close()


# ==================== analyze 子命令 ====================
def setup_analyze_parser(subparsers):
    p = subparsers.add_parser("analyze", help="轨迹质量分析（跳变/heading突变/方向反转）")
    p.add_argument("--file", default=None, help="JSON文件路径")
    return p


def run_analyze(args):
    if args.file:
        filepath = args.file
    else:
        filepath = os.path.join(_ROOT, "mock", "跨顺义三河段航路偏航数据_0.1.json")
    if not os.path.exists(filepath):
        print(f"[错误] 文件不存在: {filepath}")
        sys.exit(1)

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    n = len(data)
    print(f"总点数: {n}")
    print(f"起点: lon={data[0]['longitude']:.6f}, lat={data[0]['latitude']:.6f}")
    print(f"终点: lon={data[-1]['longitude']:.6f}, lat={data[-1]['latitude']:.6f}")

    distances = []
    heading_changes = []
    for i in range(1, n):
        lon1, lat1 = data[i - 1]['longitude'], data[i - 1]['latitude']
        lon2, lat2 = data[i]['longitude'], data[i]['latitude']
        dist = geo_distance(lat1, lon1, lat2, lon2)
        distances.append(dist)
        h1 = data[i - 1]['trackAngle']
        h2 = data[i]['trackAngle']
        h_diff = abs(h2 - h1)
        if h_diff > 180:
            h_diff = 360 - h_diff
        heading_changes.append(h_diff)

    print(f"\n距离统计: 平均={sum(distances)/len(distances):.2f}m, 最小={min(distances):.2f}m, 最大={max(distances):.2f}m")
    print(f"Heading变化: 平均={sum(heading_changes)/len(heading_changes):.2f}°, 最小={min(heading_changes):.2f}°, 最大={max(heading_changes):.2f}°")

    jump_count = sum(1 for d in distances if d > 50)
    sudden_count = sum(1 for h in heading_changes if h > 30)
    reverse_count = sum(1 for h in heading_changes if h > 150)
    print(f"\n距离跳变(>50m): {jump_count} 处")
    print(f"Heading突变(>30°): {sudden_count} 处")
    print(f"方向反转(>150°): {reverse_count} 处")

    lons = [d['longitude'] for d in data]
    lats = [d['latitude'] for d in data]
    print(f"\n经纬度范围:")
    print(f"  经度: {min(lons):.6f} ~ {max(lons):.6f}")
    print(f"  纬度: {min(lats):.6f} ~ {max(lats):.6f}")


# ==================== batch 子命令 ====================
def setup_batch_parser(subparsers):
    p = subparsers.add_parser("batch", help="批量场景执行（读取BATCH_CONFIGS预设）")
    p.add_argument("--config-index", type=int, default=None, help="仅执行指定索引的配置")
    return p


def run_batch(args):
    if not BATCH_CONFIGS:
        print("[错误] BATCH_CONFIGS 为空")
        sys.exit(1)

    configs = [BATCH_CONFIGS[args.config_index]] if args.config_index is not None else BATCH_CONFIGS
    total_needed = sum(cfg.get("count", 0) for cfg in configs)
    if total_needed > len(UAV_IDENTIFIERS_EXTENDED):
        print(f"[错误] 总需求 {total_needed} 超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
        sys.exit(1)

    uid_offset = 0
    global_s_by_mod = {}
    unified_base_time = int(datetime.now().timestamp() * 1000)

    for cfg in configs:
        print(f"\n{'=' * 60}")
        print(f"[{cfg.get('label', '未命名')}] {cfg.get('count', 0)} 架 -> {cfg.get('output', '未知')}")
        print(f"{'=' * 60}")

        subcommand = cfg.get("subcommand", "parallel")
        if subcommand != "parallel":
            print(f"[跳过] 当前仅支持 parallel 子命令的批量执行，'{subcommand}' 暂不支持")
            continue

        if cfg.get("multi"):
            group_count = cfg["count"] // 3
            base_lng = cfg.get("center_lng", 85.070136)
            base_lat = cfg.get("center_lat", 40.818724)
            for i in range(3):
                region_count = group_count if i < 2 else cfg["count"] - group_count * 2
                region_output = cfg["output"].replace(".json", f"_{i+1}.json")
                offset_meters = i * cfg.get("spacing", 2000) * 5
                offset_lng = offset_meters / (111320.0 * math.cos(math.radians(base_lat)))
                region_lng = base_lng + offset_lng
                print(f"\n区域 {i+1}: 中心({region_lng:.6f}, {base_lat:.6f}), 数量 {region_count}, 输出 {region_output}")

                class FakeArgs:
                    def __init__(self, **kwargs):
                        for k, v in kwargs.items():
                            setattr(self, k, v)

                region_args = FakeArgs(
                    count=region_count, output=region_output,
                    center_lng=region_lng, center_lat=base_lat,
                    altitude=cfg.get("altitude", 50), speed=cfg.get("speed", 15),
                    heading=cfg.get("heading", 90), spacing=cfg.get("spacing", 2000),
                    spacing_along=cfg.get("spacing_along", 0), layout=cfg.get("layout", "hex"),
                    sim_radius=cfg.get("sim_radius", 100000), classification=cfg.get("classification", 2),
                    points=cfg.get("points", 1200), interval=cfg.get("interval", 1000),
                    start_time=unified_base_time, enable_altitude_groups=cfg.get("enable_altitude_groups", False),
                    altitude_groups=cfg.get("altitude_groups", None),
                )
                global_s_by_mod = run_parallel(region_args, uid_offset_override=i * group_count,
                                               s_by_mod_override=global_s_by_mod,
                                               start_time_override=unified_base_time)
        else:
            class FakeArgs:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)

            batch_args = FakeArgs(
                count=cfg.get("count", 30), output=cfg.get("output", "../data/mock/kafka_data_parallel.json"),
                center_lng=cfg.get("center_lng", 85.070136), center_lat=cfg.get("center_lat", 40.818724),
                altitude=cfg.get("altitude", 50), speed=cfg.get("speed", 15),
                heading=cfg.get("heading", 90), spacing=cfg.get("spacing", 2000),
                spacing_along=cfg.get("spacing_along", 0), layout=cfg.get("layout", "hex"),
                sim_radius=cfg.get("sim_radius", 100000), classification=cfg.get("classification", 2),
                points=cfg.get("points", 1200), interval=cfg.get("interval", 1000),
                start_time=unified_base_time, enable_altitude_groups=cfg.get("enable_altitude_groups", False),
                altitude_groups=cfg.get("altitude_groups", None),
            )
            global_s_by_mod = run_parallel(batch_args, uid_offset_override=uid_offset,
                                           s_by_mod_override=global_s_by_mod,
                                           start_time_override=unified_base_time)
            uid_offset += cfg.get("count", 0)

    print("\n" + "=" * 60)
    print(f"批量执行完成，共使用 {uid_offset} 个唯一 UAV ID")
    print("=" * 60)


# ==================== main ====================
def main():
    parser = argparse.ArgumentParser(
        description="统一场景数据生成脚本 (create_data_scenes.py)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  python create_data_scenes.py create --count 10
  python create_data_scenes.py route --route-name "金鸡湖航线" --speed 15
  python create_data_scenes.py parallel --count 3000 --layout hex
  python create_data_scenes.py deviate --route-name "跨顺义三河段" --deviate-offset 600
  python create_data_scenes.py collision --route-names "航线A,航线B"
  python create_data_scenes.py status --scene3 --count 5
  python create_data_scenes.py scale --source mock/kafka_data_yfk.json --count 1000
  python create_data_scenes.py check-id
  python create_data_scenes.py check-uid --file mock/kafka_data_parallel.json
  python create_data_scenes.py analyze --file mock/kafka_data_scene2.json
  python create_data_scenes.py batch
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    setup_create_parser(subparsers)
    setup_route_parser(subparsers)
    setup_deviate_parser(subparsers)
    setup_parallel_parser(subparsers)
    setup_scale_parser(subparsers)
    setup_collision_parser(subparsers)
    setup_status_parser(subparsers)
    setup_check_id_parser(subparsers)
    setup_check_uid_parser(subparsers)
    setup_analyze_parser(subparsers)
    setup_batch_parser(subparsers)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "create": run_create,
        "route": run_route,
        "deviate": run_deviate,
        "parallel": run_parallel,
        "scale": run_scale,
        "collision": run_collision,
        "status": run_status,
        "check-id": run_check_id,
        "check-uid": run_check_uid,
        "analyze": run_analyze,
        "batch": run_batch,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        print(f"[错误] 未知子命令: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()