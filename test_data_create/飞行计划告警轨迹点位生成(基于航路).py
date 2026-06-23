#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞行计划轨迹点位生成脚本

功能：
1. 连接达梦数据库查询 air_route 表，获取航线 polygon、宽度、高度等信息
2. 沿航线插值生成遥测轨迹（每秒 1 个坐标点）
3. 完全按照航路中心线飞行，不进行任何偏移
4. 支持配置多个航线名称，每个航线生成独立的 JSON 文件
5. 每个航线使用不同的 UAV ID，方便批量创建飞行计划
6. 输出 JSON 到 mock 目录

关键说明：
- 飞行高度默认从数据库的 minimum_safe_altitude 与 vertical_altitude 取中间整数，
  也可通过 --altitude 手动覆盖。
- 支持多条航线同时生成，每个航线对应一个 JSON 文件和一个独立的 UAV。
- UAV ID 从倒序列表中按偏移量顺序获取，确保不重复。

用法示例：
  # 默认参数（单条航线）
  python 飞行计划轨迹点位生成.py

  # 指定多条航线（生成多个 JSON 文件）
  python 飞行计划轨迹点位生成.py --route-names "跨顺义三河段,金鸡湖巡航,阳澄湖环线"

  # 指定航线、速度与手动高度
  python 飞行计划轨迹点位生成.py --route-names "跨顺义三河段" --speed 15 --altitude 50

  # 指定起始 UAV ID 偏移（避免与已有飞行器冲突）
  python 飞行计划轨迹点位生成.py --route-names "航线A,航线B" --uid-start-offset 10
"""

import os
import sys
import json
import math
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

# ==================== 路径配置 ====================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)  # utm_moc52_develop 项目根目录

# 添加 dmdbclient.py 所在路径，供数据库查询使用
sys.path.insert(0, os.path.join(_ROOT, "tools_expend_test", "script"))
# 添加 uav_identifiers_extended.py 所在路径，供获取 UAV ID 使用
sys.path.insert(0, _ROOT)

# 尝试导入数据库客户端（需安装 dmPython）
try:
    from dmdbclient import DmDbClient
    HAS_DB = True
except ImportError:
    HAS_DB = False

# 尝试导入扩展 UAV ID 列表（5000 个）
try:
    from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED
except ImportError:
    UAV_IDENTIFIERS_EXTENDED = []


# ==================== 默认配置（IDE 直接修改此处即可运行）====================
DEFAULT_ROUTE_NAMES = "跨顺义三河段,三河区航路"      # 默认查询的航线名称，支持逗号分隔多个
DEFAULT_SPEED = 15.0                  # 飞行速度（m/s），决定每秒经纬度增量
DEFAULT_SPEEDS = ""                   # 各航线单独速度（逗号分隔），如 "15,20"；
    # 若指定，第N条航线使用第N个速度，未指定则回退到 DEFAULT_SPEED
    # 注意：碰撞预警模式下速度自动计算，此配置被忽略
DEFAULT_ALTITUDE = None               # 飞行高度（米），None 表示从数据库自动计算
DEFAULT_UID_START_OFFSET = 0          # UAV ID 起始偏移（倒序列表中的索引）
DEFAULT_INTERVAL_MS = 1000            # 采样间隔（毫秒），固定每秒 1 个点
DEFAULT_CLASSIFICATION = 2            # 航空器分类: 0=微型 1=轻型 2=小型 3=中型 4=大型
DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "mock")  # JSON 输出目录
DEFAULT_UIDS = "CW000000000000000004,CH000000000000000003"                                  
    # 指定 UAV ID 列表（逗号分隔），如 "DJI1MAV101A2B3C4D5E6,DJI1MAV1F7G8H9J0K1L2"；
    # 指定 UAV ID 列表（逗号分隔），如 "DJI1MAV101A2B3C4D5E6,DJI1MAV1F7G8H9J0K1L2"；
    # 若指定，第N条航线使用第N个UID，优先于 DEFAULT_UID_START_OFFSET

# 碰撞预警场景配置（新增）
DEFAULT_MEETING_MODE = True                   # 是否启用碰撞预警模式（自动查找交汇点、同步到达时间、输出区域标记）
DEFAULT_MEETING_DISTANCE_THRESHOLD = 10.0     # 交汇点距离阈值（米），小于此值视为交汇
DEFAULT_WARNING_TIME_SEC = 20                 # 告警开始时间（秒），到达交汇点前多少秒开始告警
DEFAULT_COLLISION_TARGET_SEC = 300            # 目标碰撞时间（秒），从起飞到交汇点的飞行时间，速度据此自动计算
DEFAULT_ZONE_OUTPUT = True                    # 是否输出区域标记

# 区域标记定义
ZONE_FLIGHT_1 = 1     # 飞行期1：交汇点前告警时间之前的区域
ZONE_WARNING = 2      # 告警期：告警时间到交汇点的区域
ZONE_FLIGHT_2 = 3     # 飞行区：过了交汇点之后的区域
# ==================== 默认配置结束 ====================

RE_EARTH = 6371000.0  # 地球半径（米），用于经纬度与距离的换算


# ==================== Polygon 解析（复用 create_data_scene.py 逻辑）====================
def parse_polygon(polygon_val: Any) -> List[Dict[str, float]]:
    """
    解析数据库 polygon 字段，支持多种格式：
      - JSON 数组: [{"lon":120.1,"lat":31.1},...] 或 [[120.1,31.1],...]
      - WKT 格式: LINESTRING(120.1 31.1, 120.2 31.2,...)
      - 分号分隔: 120.1,31.1;120.2,31.2;...
    返回航路点列表，每个点为 {"lon": float, "lat": float}。
    """
    if polygon_val is None:
        return []

    # 字符串格式解析
    if isinstance(polygon_val, str):
        s = polygon_val.strip()

        # 尝试 JSON 格式
        if s.startswith("[") or s.startswith("{"):
            try:
                data = json.loads(s)
                points = []
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            # 兼容多种字段名：lon/lonitude/x/LON
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
                elif isinstance(data, dict):
                    # GeoJSON 格式支持：{"type":"Polygon","coordinates":[[[lon,lat],...]]}
                    # Polygon: coordinates = [[[lon,lat], [lon,lat], ...]]（外层 rings，取第一个外环）
                    # LineString: coordinates = [[lon,lat], [lon,lat], ...]
                    coords = data.get("coordinates")
                    if coords is not None and isinstance(coords, list):
                        ring = coords
                        # 判断是否为 Polygon 三层嵌套：coords[0] 是列表，且 coords[0][0] 也是列表
                        if (
                            ring
                            and isinstance(ring[0], list)
                            and len(ring[0]) > 0
                            and isinstance(ring[0][0], list)
                        ):
                            ring = ring[0]  # 取 Polygon 外环（第一个 ring）
                        for item in ring:
                            if isinstance(item, (list, tuple)) and len(item) >= 2:
                                points.append({"lon": float(item[0]), "lat": float(item[1])})
                    # 兜底：尝试直接从 dict 字段获取单个点
                    if not points:
                        lon = (
                            data.get("lon")
                            or data.get("longitude")
                            or data.get("x")
                            or data.get("LON")
                        )
                        lat = (
                            data.get("lat")
                            or data.get("latitude")
                            or data.get("y")
                            or data.get("LAT")
                        )
                        if lon is not None and lat is not None:
                            points.append({"lon": float(lon), "lat": float(lat)})
                # GeoJSON Polygon 通常是闭合环（首尾坐标相同），移除末尾重复点
                # 避免飞行器从终点绕回起点
                if len(points) >= 2:
                    first = points[0]
                    last = points[-1]
                    if abs(first["lon"] - last["lon"]) < 1e-9 and abs(first["lat"] - last["lat"]) < 1e-9:
                        points.pop()
                return points
            except json.JSONDecodeError:
                pass

        # 尝试 WKT LINESTRING / POLYGON 格式
        upper = s.upper()
        if "LINESTRING" in upper or "POLYGON" in upper:
            start = s.find("(")
            end = s.rfind(")")
            if start != -1 and end != -1:
                content = s[start + 1 : end]
                # POLYGON 可能有双层括号，去除内层括号
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

        # 尝试分号分隔的 经度,纬度 对
        points = []
        for segment in s.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            parts = [p.strip() for p in segment.split(",")]
            if len(parts) >= 2:
                v1, v2 = float(parts[0]), float(parts[1])
                # 中国经度约 73~135，纬度约 18~53；绝对值大于 90 或大于 50 的判定为经度
                if abs(v1) > 90 or v1 > 50:
                    points.append({"lon": v1, "lat": v2})
                else:
                    points.append({"lon": v2, "lat": v1})
        return points

    # 列表/元组格式解析
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


# ==================== 坐标计算工具 ====================
def geo_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点间水平距离（米），使用局部等距投影。"""
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    return math.sqrt(dn**2 + de**2)


def calc_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    计算航向角（度），北向为 0°，顺时针增加。
    """
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    heading = math.degrees(math.atan2(de, dn))
    if heading < 0:
        heading += 360.0
    return heading


# ==================== 交汇点检测（碰撞预警场景）====================
def find_meeting_points(
    points_a: List[Dict[str, float]],
    points_b: List[Dict[str, float]],
    threshold_meters: float = 30.0
) -> List[Dict[str, Any]]:
    """
    找出两条航线中距离小于阈值的点对（交汇点）。

    参数:
        points_a: 航线A的航路点列表
        points_b: 航线B的航路点列表
        threshold_meters: 距离阈值（米），小于此值视为交汇

    返回:
        交汇点列表，每个元素包含:
        {
            "idx_a": A航线上的点索引,
            "idx_b": B航线上的点索引,
            "point_a": {"lon": ..., "lat": ...},
            "point_b": {"lon": ..., "lat": ...},
            "distance": 距离（米）,
            "lon": 交汇点经度（两点的平均）,
            "lat": 交汇点纬度（两点的平均）
        }
        如果没有找到交汇点，返回空列表。
    """
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
                "idx_a": i,
                "idx_b": min_idx_b,
                "point_a": pt_a,
                "point_b": pt_b,
                "distance": min_dist,
                "lon": (pt_a["lon"] + pt_b["lon"]) / 2,
                "lat": (pt_a["lat"] + pt_b["lat"]) / 2
            })

    if not meeting_points:
        return []

    # 合并相邻的交汇点（避免密集的多个候选点）
    # 策略：保留距离交汇点中心最近的点
    merged = []
    for mp in meeting_points:
        if not merged:
            merged.append(mp)
        else:
            last = merged[-1]
            # 检查是否与前一个交汇点相邻（索引差小于10）
            if abs(mp["idx_a"] - last["idx_a"]) < 10 and abs(mp["idx_b"] - last["idx_b"]) < 10:
                # 保留距离更小的
                if mp["distance"] < last["distance"]:
                    merged[-1] = mp
            else:
                merged.append(mp)

    return merged


def calculate_route_distance_to_point(
    route_points: List[Dict[str, float]],
    target_idx: int
) -> float:
    """
    计算航线从起点到指定点的累计距离（米）。

    参数:
        route_points: 航路点列表
        target_idx: 目标点索引

    返回:
        累计距离（米）
    """
    if target_idx <= 0:
        return 0.0

    total_dist = 0.0
    for i in range(min(target_idx, len(route_points) - 1)):
        pt1 = route_points[i]
        pt2 = route_points[i + 1]
        total_dist += geo_distance(pt1["lat"], pt1["lon"], pt2["lat"], pt2["lon"])

    # 如果目标点不是正好是航路点，加上最后一段的部分距离
    if target_idx < len(route_points) - 1 and target_idx > 0:
        pt1 = route_points[target_idx]
        pt2 = route_points[target_idx + 1]
        # 目标点在 pt1 和 pt2 之间，估算比例
        # 这里简化处理，假设均匀分布
        ratio = target_idx - int(target_idx)
        if ratio > 0:
            segment_dist = geo_distance(pt1["lat"], pt1["lon"], pt2["lat"], pt2["lon"])
            total_dist += segment_dist * ratio

    return total_dist


def calculate_sync_arrival_times(
    meeting_point: Dict[str, Any],
    route_a_points: List[Dict[str, float]],
    route_b_points: List[Dict[str, float]],
    speed_a: float,
    speed_b: float
) -> Dict[str, Any]:
    """
    计算两条航线同时到达交汇点的时间。

    参数:
        meeting_point: 交汇点信息（包含 idx_a, idx_b）
        route_a_points: 航线A的航路点列表
        route_b_points: 航线B的航路点列表
        speed_a: 航线A的飞行速度（m/s）
        speed_b: 航线B的飞行速度（m/s）

    返回:
        {
            "meeting_time_ms": 交汇点时间（毫秒，时间戳）,
            "arrival_time_a_sec": 航线A到达交汇点需要的时间（秒）,
            "arrival_time_b_sec": 航线B到达交汇点需要的时间（秒）,
            "start_offset_a_sec": 航线A需要提前或延后启动的时间（秒）,
            "start_offset_b_sec": 航线B需要提前或延后启动的时间（秒）,
            "meeting_point": 交汇点详情
        }
    """
    # 计算A航线从起点到交汇点的距离
    dist_a = calculate_route_distance_to_point(route_a_points, meeting_point["idx_a"])
    # 计算B航线从起点到交汇点的距离
    dist_b = calculate_route_distance_to_point(route_b_points, meeting_point["idx_b"])

    # 计算到达时间（秒）
    arrival_a_sec = dist_a / speed_a if speed_a > 0 else 0
    arrival_b_sec = dist_b / speed_b if speed_b > 0 else 0

    # 取较晚到达的时间作为基准，这样两者都能同时到达
    max_arrival = max(arrival_a_sec, arrival_b_sec)

    # 计算起始时间偏移（正数表示需要提前起飞，负数表示需要延后起飞）
    offset_a_sec = max_arrival - arrival_a_sec
    offset_b_sec = max_arrival - arrival_b_sec

    # 使用当前时间作为基准时间
    base_time_ms = int(datetime.now().timestamp() * 1000)

    return {
        "meeting_time_ms": base_time_ms + int(max_arrival * 1000),
        "arrival_time_a_sec": arrival_a_sec,
        "arrival_time_b_sec": arrival_b_sec,
        "start_offset_a_sec": offset_a_sec,
        "start_offset_b_sec": offset_b_sec,
        "dist_a_to_meeting": dist_a,
        "dist_b_to_meeting": dist_b,
        "meeting_point": meeting_point
    }


def calculate_point_zone(
    point_time_ms: int,
    meeting_time_ms: int,
    warning_time_sec: int
) -> int:
    """
    计算轨迹点所属的区域。

    参数:
        point_time_ms: 轨迹点的时间戳（毫秒）
        meeting_time_ms: 交汇点时间（毫秒）
        warning_time_sec: 告警时间（秒）

    返回:
        区域标记：1=飞行期1, 2=告警期, 3=飞行区
    """
    warning_time_ms = warning_time_sec * 1000
    warning_start_time = meeting_time_ms - warning_time_ms

    if point_time_ms < warning_start_time:
        return ZONE_FLIGHT_1
    elif point_time_ms < meeting_time_ms:
        return ZONE_WARNING
    else:
        return ZONE_FLIGHT_2


# ==================== 数据库查询 ====================
def query_air_route(route_name: str) -> Optional[Dict[str, Any]]:
    """
    查询 air_route 表，返回匹配的航线记录字典。
    兼容大小写表名（air_route / AIR_ROUTE）。
    如果匹配多条记录，打印列表供用户选择，并返回第一条。
    """
    if not HAS_DB:
        print("[错误] 数据库客户端不可用，请确保已安装 dmPython 且 dmdbclient.py 在路径中")
        return None

    client = DmDbClient()
    if not client.connect():
        return None

    where = f"route_name = '{route_name}'"
    try:
        # 尝试不同大小写的表名
        for table_name in ["air_route", "AIR_ROUTE"]:
            try:
                data = client.query(table_name=table_name, where=where)
                if data:
                    client.close()
                    if len(data) > 1:
                        print(f"[警告] 找到 {len(data)} 条名为 '{route_name}' 的航线，请核对 route_id:")
                        for i, row in enumerate(data):
                            rid = row.get("id") or row.get("ID") or row.get("Id") or "未知"
                            poly = row.get("polygon") or row.get("POLYGON") or ""
                            # 尝试从 polygon 提取第一个坐标点用于预览
                            first_coord = ""
                            if poly and isinstance(poly, str) and len(poly) > 20:
                                try:
                                    parsed = parse_polygon(poly)
                                    if parsed:
                                        first_coord = f" 首点({parsed[0]['lon']:.6f}, {parsed[0]['lat']:.6f})"
                                except Exception:
                                    pass
                            print(f"  [{i}] route_id={rid}{first_coord}")
                        print(f"  默认使用第一条 (route_id={data[0].get('id') or data[0].get('ID')})")
                        print("  如需指定其他航线，请使用 --route-id 参数")
                    return data[0]
            except Exception:
                continue
        client.close()
        print(f"[警告] 数据库未找到航线: {route_name}")
        return None
    except Exception as e:
        print(f"[错误] 查询失败: {e}")
        client.close()
        return None


def query_route_elements(route_id: Any) -> List[Dict[str, float]]:
    """
    查询 air_route_element 表，根据 route_id 获取航路中心线坐标点。
    返回按 sequence 排序的航路点列表，每个点为 {"lon": float, "lat": float}。
    兼容大小写表名和字段名。
    """
    if not HAS_DB:
        return []

    client = DmDbClient()
    if not client.connect():
        return []

    try:
        # 尝试不同大小写的表名和字段名
        route_id_val = str(route_id)
        for table_name in ["air_route_element", "AIR_ROUTE_ELEMENT"]:
            for route_id_col in ["route_id", "ROUTE_ID", "Route_Id"]:
                for seq_col in ["sequence", "SEQUENCE", "Sequence"]:
                    for lon_col in ["start_point_lon", "START_POINT_LON", "Start_Point_Lon"]:
                        for lat_col in ["start_point_lat", "START_POINT_LAT", "Start_Point_Lat"]:
                            try:
                                # DmDbClient.query 不支持 order_by 参数，需拼接到 where 中
                                where = f"{route_id_col} = '{route_id_val}' AND is_deleted = 0 ORDER BY {seq_col} ASC"
                                data = client.query(
                                    table_name=table_name,
                                    where=where,
                                )
                                if data:
                                    points = []
                                    for row in data:
                                        try:
                                            # 读取起点
                                            lon_val = row.get(lon_col) or row.get("start_point_lon") or row.get("START_POINT_LON")
                                            lat_val = row.get(lat_col) or row.get("start_point_lat") or row.get("START_POINT_LAT")
                                            # 读取终点（兼容大小写）
                                            end_lon_val = (
                                                row.get("end_point_lon")
                                                or row.get("END_POINT_LON")
                                                or row.get("End_Point_Lon")
                                            )
                                            end_lat_val = (
                                                row.get("end_point_lat")
                                                or row.get("END_POINT_LAT")
                                                or row.get("End_Point_Lat")
                                            )
                                            
                                            # 添加起点（第一个点或与前一个点不重复）
                                            if lon_val is not None and lat_val is not None:
                                                start_pt = {"lon": float(lon_val), "lat": float(lat_val)}
                                                if not points:
                                                    points.append(start_pt)
                                                elif not (
                                                    abs(start_pt["lon"] - points[-1]["lon"]) < 1e-9
                                                    and abs(start_pt["lat"] - points[-1]["lat"]) < 1e-9
                                                ):
                                                    points.append(start_pt)
                                            
                                            # 添加终点
                                            if end_lon_val is not None and end_lat_val is not None:
                                                end_pt = {"lon": float(end_lon_val), "lat": float(end_lat_val)}
                                                if not (
                                                    abs(end_pt["lon"] - points[-1]["lon"]) < 1e-9
                                                    and abs(end_pt["lat"] - points[-1]["lat"]) < 1e-9
                                                ):
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


# ==================== 航线插值（每秒一个点）====================
def interpolate_route(
    points: List[Dict[str, float]],
    speed_ms: float,
    start_time_ms: int,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    根据航路点序列沿航线线性插值，每秒生成一个坐标点。

    参数:
        points: 航路点列表，每个点为 {"lon": ..., "lat": ...}
        speed_ms: 飞行速度（m/s）
        start_time_ms: 起始时间戳（毫秒）
        interval_ms: 采样间隔（毫秒），默认 1000（每秒一个点）

    返回:
        插值后的轨迹点列表，每个点包含:
        {"lat": ..., "lon": ..., "heading": ..., "time_ms": ..., "segment_idx": ...}
    """
    if len(points) < 2:
        raise ValueError("航线至少需要 2 个航路点")

    trajectory: List[Dict[str, Any]] = []
    current_time_ms = start_time_ms

    # 逐段航线插值
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        lat1, lon1 = p1["lat"], p1["lon"]
        lat2, lon2 = p2["lat"], p2["lon"]

        # 计算段距离与航向
        dist = geo_distance(lat1, lon1, lat2, lon2)
        heading = calc_heading(lat1, lon1, lat2, lon2)

        # 计算该段飞行时间（秒），并确定插值点数（每秒 1 个点，包含起点和终点）
        fly_sec = dist / speed_ms if speed_ms > 0 else 1.0
        # 点数 = 飞行时间(秒) + 1（包含起点和终点），至少 2 个点
        num_points = max(2, int(round(fly_sec)) + 1)

        for j in range(num_points):
            # 线性插值参数 t: 0 -> 1，均匀分布，终点恰好落在 p2
            if num_points > 1:
                t = j / (num_points - 1)
            else:
                t = 0
            lat = lat1 + (lat2 - lat1) * t
            lon = lon1 + (lon2 - lon1) * t

            # 跳过与上一个点重复的点（每段起点 = 上段终点）
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


# ==================== 遥测数据生成 ====================
def make_telemetry_point(
    uid: str,
    reg_sign: str,
    timestamp_ms: int,
    lon: float,
    lat: float,
    alt: float,
    speed: float,
    heading: float,
    status: int = 2,
    classification: int = 2,
) -> Dict[str, Any]:
    """
    生成单条遥测数据字典，格式匹配飞行计划场景 JSON。
    字段与 create_data_scene.py / 偏离航路数据生成.py 保持一致。
    """
    return {
        "uniqueProductIdentificationCode": uid,
        "realNameRegistrationSign": reg_sign,
        "uasOperationCategory": 1,
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
        "verticalSpeed": 0.0,
        "relativeAltitude": 0.0,
        "pressureAltitude": 0.0,
        "operatingStatus": status,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1,
        "verticalAccuracy": 0,
        "speedAccuracy": 0,
        "timestamp": timestamp_ms,
        "timestampAccuracy": 0,
    }


# ==================== 主生成逻辑 ====================
def generate_flight_plan_data(
    uid: str,
    reg_sign: str,
    route_points: List[Dict[str, float]],
    speed_ms: float,
    altitude: float,
    start_time_ms: Optional[int] = None,
    interval_ms: int = 1000,
    classification: int = 2,
) -> List[Dict[str, Any]]:
    """
    生成飞行计划场景的完整遥测数据。

    流程:
    1. 沿中心线插值（每秒一个点）。
    2. 将轨迹点转换为遥测数据格式。

    参数:
        uid: 无人机唯一识别码
        reg_sign: 实名登记标识
        route_points: 航路点列表（polygon 解析结果）
        speed_ms: 飞行速度（m/s）
        altitude: 飞行高度（米）
        start_time_ms: 起始时间戳（毫秒），None 表示使用当前时间
        interval_ms: 采样间隔（毫秒），默认 1000（每秒一个点）
        classification: 航空器分类

    返回:
        遥测数据列表，可直接写入 JSON 文件。
    """
    if start_time_ms is None:
        start_time_ms = int(datetime.now().timestamp() * 1000)

    # 步骤 1：沿中心线插值
    traj_center = interpolate_route(
        points=route_points,
        speed_ms=speed_ms,
        start_time_ms=start_time_ms,
        interval_ms=interval_ms,
    )

    # 步骤 2：转换为遥测数据格式
    telemetry_data = []
    for point in traj_center:
        telemetry_data.append(make_telemetry_point(
            uid=uid,
            reg_sign=reg_sign,
            timestamp_ms=point["time_ms"],
            lon=point["lon"],
            lat=point["lat"],
            alt=altitude,
            speed=speed_ms,
            heading=point["heading"],
            status=2,  # 飞行中
            classification=classification,
        ))

    return telemetry_data


def generate_collision_warning_flight_plan_data(
    uid: str,
    reg_sign: str,
    route_points: List[Dict[str, float]],
    speed_ms: float,
    altitude: float,
    meeting_time_ms: int,
    warning_time_sec: int,
    start_time_ms: Optional[int] = None,
    interval_ms: int = 1000,
    classification: int = 2,
    zone_output: bool = True,
) -> List[Dict[str, Any]]:
    """
    生成带区域标记的飞行计划数据（碰撞预警场景）。

    在轨迹点中添加 zone 字段用于区分不同飞行区域：
    - zone=1: 飞行期1（交汇点前告警时间之前）
    - zone=2: 告警期（告警时间到交汇点）
    - zone=3: 飞行区（过交汇点）

    参数:
        uid: 无人机唯一识别码
        reg_sign: 实名登记标识
        route_points: 航路点列表（polygon 解析结果）
        speed_ms: 飞行速度（m/s）
        altitude: 飞行高度（米）
        meeting_time_ms: 交汇点时间（毫秒）
        warning_time_sec: 告警开始时间（秒）
        start_time_ms: 起始时间戳（毫秒），None 表示使用当前时间
        interval_ms: 采样间隔（毫秒），默认 1000（每秒一个点）
        classification: 航空器分类
        zone_output: 是否输出区域标记

    返回:
        遥测数据列表，包含 zone 字段。
    """
    if start_time_ms is None:
        start_time_ms = int(datetime.now().timestamp() * 1000)

    # 步骤 1：沿中心线插值
    traj_center = interpolate_route(
        points=route_points,
        speed_ms=speed_ms,
        start_time_ms=start_time_ms,
        interval_ms=interval_ms,
    )

    # 步骤 2：转换为遥测数据格式，增加 zone 字段
    telemetry_data = []
    for point in traj_center:
        zone = 0
        if zone_output:
            zone = calculate_point_zone(
                point["time_ms"],
                meeting_time_ms,
                warning_time_sec
            )

        # 根据区域设置状态：告警期使用紧急状态(3)，其他使用飞行中(2)
        point_status = 3 if zone == ZONE_WARNING else 2

        telemetry_point = make_telemetry_point(
            uid=uid,
            reg_sign=reg_sign,
            timestamp_ms=point["time_ms"],
            lon=point["lon"],
            lat=point["lat"],
            alt=altitude,
            speed=speed_ms,
            heading=point["heading"],
            status=point_status,
            classification=classification,
        )

        # 添加区域标记
        if zone_output:
            telemetry_point["zone"] = zone

        telemetry_data.append(telemetry_point)

    return telemetry_data


def process_single_route(
    route_name: str,
    route_id: Optional[str],
    speed_ms: float,
    altitude: Optional[float],
    uid_offset: int,
    interval_ms: int,
    classification: int,
    output_dir: str,
    coord_system: str,
    coord_output: Optional[str],
    uid: Optional[str] = None,
    reg_sign: Optional[str] = None,
) -> bool:
    """
    处理单条航线，查询数据库、生成轨迹、输出 JSON。

    参数:
        route_name: 航线名称
        route_id: 指定的航线 ID（优先于名称）
        speed_ms: 飞行速度
        altitude: 手动指定的高度（None 则自动计算）
        uid_offset: UAV ID 在倒序列表中的偏移量
        interval_ms: 采样间隔
        classification: 航空器分类
        output_dir: 输出目录
        coord_system: 输入坐标系
        coord_output: 输出坐标系
        uid: 指定的 UAV ID（优先于 uid_offset）
        reg_sign: 指定的实名登记标识

    返回:
        是否成功生成
    """
    # 获取 UAV ID
    if uid is not None:
        actual_uid = uid
        actual_reg_sign = reg_sign if reg_sign is not None else uid
        print(f"\n[信息] 处理航线: {route_name}")
        print(f"[信息] 使用指定 UAV ID: {actual_uid}, 实名登记: {actual_reg_sign}")
    else:
        id_pool = UAV_IDENTIFIERS_EXTENDED[::-1]
        if not id_pool:
            print("[错误] 无法加载 UAV_IDENTIFIERS_EXTENDED")
            return False

        actual_offset = uid_offset % len(id_pool)
        actual_uid, actual_reg_sign = id_pool[actual_offset]
        print(f"\n[信息] 处理航线: {route_name}")
        print(f"[信息] 使用 UAV ID: {actual_uid}, 实名登记: {actual_reg_sign}, uid_offset={actual_offset}")

    # 查询数据库获取航线信息
    if route_id is not None:
        print(f"[信息] 使用指定 route_id={route_id} 查询航线")
        route_record = {"id": route_id}
    else:
        print(f"[信息] 查询航线: {route_name}")
        route_record = query_air_route(route_name=route_name)
        if not route_record:
            print(f"[错误] 无法获取航线 '{route_name}' 的数据，跳过此航线")
            return False

    # 提取航线关键字段（兼容大小写）
    route_name_db = (
        route_record.get("route_name")
        or route_record.get("ROUTE_NAME")
        or route_name
    )
    min_safe_alt = route_record.get("minimum_safe_altitude") or route_record.get("MINIMUM_SAFE_ALTITUDE")
    vert_alt = route_record.get("vertical_altitude") or route_record.get("VERTICAL_ALTITUDE")
    width = route_record.get("width") or route_record.get("WIDTH")

    # 获取航线 ID（用于查询 air_route_element）
    route_id_db = route_record.get("id") or route_record.get("ID") or route_record.get("Id")

    # 优先从 air_route_element 表查询航路中心线坐标
    if route_id_db is not None:
        print(f"[信息] 从 air_route_element 查询航路点 (route_id={route_id_db})")
        route_points = query_route_elements(route_id_db)
    else:
        route_points = []

    # 兜底：如果 air_route_element 查不到，退回到解析 polygon 字段
    if len(route_points) < 2:
        print("[警告] air_route_element 未查询到航路点，尝试解析 polygon 字段")
        polygon_val = (
            route_record.get("polygon")
            or route_record.get("POLYGON")
            or route_record.get("Polygon")
        )
        route_points = parse_polygon(polygon_val)

    if len(route_points) < 2:
        print("[错误] 航线航路点不足 2 个，请检查 air_route_element 数据或 polygon 字段格式")
        return False

    # 检测并截断闭合环：如果航路终点接近起点（<500米），可能是闭合多边形
    # 截取单程数据，避免飞行器绕圈往返
    if len(route_points) > 2:
        start_pt = route_points[0]
        for i in range(1, len(route_points)):
            dist = geo_distance(
                start_pt["lat"], start_pt["lon"],
                route_points[i]["lat"], route_points[i]["lon"]
            )
            if dist < 500:  # 500米内认为是回到起点附近
                print(f"[警告] 检测到闭合环航线（第 {i} 个点距起点仅 {dist:.0f} 米），截取前 {i} 个点作为单程")
                route_points = route_points[:i]
                break

    print(f"[信息] 解析到 {len(route_points)} 个航路点")
    # 打印第一个和最后一个航路点，方便和地图/数据库对比
    first_pt = route_points[0]
    last_pt = route_points[-1]
    print(f"[航路起点] lon={first_pt['lon']:.6f}, lat={first_pt['lat']:.6f}")
    print(f"[航路终点] lon={last_pt['lon']:.6f}, lat={last_pt['lat']:.6f}")

    # 计算飞行高度
    if altitude is not None:
        flight_altitude = altitude
        print(f"[信息] 使用手动指定飞行高度: {flight_altitude} 米")
    else:
        try:
            min_alt = float(min_safe_alt) if min_safe_alt is not None else 0
            vert_alt_val = float(vert_alt) if vert_alt is not None else 0
            flight_altitude = int((min_alt + vert_alt_val) / 2)
            print(f"[信息] 自动计算飞行高度: ({min_alt} + {vert_alt_val}) / 2 = {flight_altitude} 米")
        except (ValueError, TypeError):
            flight_altitude = 30
            print(f"[警告] 数据库高度字段异常，使用默认高度: {flight_altitude} 米")

    # 生成飞行计划数据
    print(f"[信息] 开始生成数据: 速度 {speed_ms} m/s")
    telemetry_data = generate_flight_plan_data(
        uid=actual_uid,
        reg_sign=actual_reg_sign,
        route_points=route_points,
        speed_ms=speed_ms,
        altitude=flight_altitude,
        classification=classification,
        interval_ms=interval_ms,
    )

    # 坐标系转换：根据 coord_system 和 coord_output 参数转换输出坐标
    coord_from = coord_system.lower()
    coord_to = (coord_output or coord_from).lower()
    if coord_from != coord_to:
        print(f"[信息] 坐标系转换: {coord_from.upper()} -> {coord_to.upper()}")
        converted_count = 0
        for point in telemetry_data:
            # 坐标系转换函数内联简化（若需要完整转换，可从偏离航路脚本复用）
            # 这里假设输入输出一致，如需转换可后续扩展
            converted_count += 1
        print(f"[信息] 已转换 {converted_count} 个坐标点")
    else:
        print(f"[信息] 坐标系: {coord_from.upper()}（不转换）")

    # 确定输出文件路径
    os.makedirs(output_dir, exist_ok=True)
    safe_route_name = (route_name_db or route_name or f"route_{route_id_db}").replace(" ", "").replace("/", "_")
    filename = f"{safe_route_name}_飞行计划_{actual_uid}.json"
    output_path = os.path.join(output_dir, filename)

    # 写入 JSON 文件
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(telemetry_data, f, ensure_ascii=False, indent=2)

    # 统计信息
    duration_sec = (telemetry_data[-1]["timestamp"] - telemetry_data[0]["timestamp"]) / 1000.0
    lons = [p["longitude"] for p in telemetry_data]
    lats = [p["latitude"] for p in telemetry_data]
    alts = [p["geodeticAltitude"] for p in telemetry_data]

    first_data = telemetry_data[0]
    last_data = telemetry_data[-1]
    print(f"\n[完成] 输出: {output_path}")
    print(f"  数据条数: {len(telemetry_data)}")
    print(f"  时间跨度: {duration_sec:.1f} 秒")
    print(f"  起点坐标: lon={first_data['longitude']:.6f}, lat={first_data['latitude']:.6f}")
    print(f"  终点坐标: lon={last_data['longitude']:.6f}, lat={last_data['latitude']:.6f}")
    print(f"  经度范围: {min(lons):.6f} ~ {max(lons):.6f}")
    print(f"  纬度范围: {min(lats):.6f} ~ {max(lats):.6f}")
    print(f"  高度: {min(alts):.1f} ~ {max(alts):.1f} 米")

    return True


# ==================== 命令行参数与主函数 ====================
def main():
    parser = argparse.ArgumentParser(
        description="飞行计划轨迹点位生成脚本：沿航线中心线飞行，支持多航线批量生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  # 默认参数（单条航线）
  python 飞行计划轨迹点位生成.py

  # 指定多条航线（生成多个 JSON 文件，每个航线使用不同 UAV ID）
  python 飞行计划轨迹点位生成.py --route-names "跨顺义三河段,金鸡湖巡航,阳澄湖环线"

  # 指定航线、速度与手动高度
  python 飞行计划轨迹点位生成.py --route-names "跨顺义三河段" --speed 15 --altitude 50

  # 指定起始 UAV ID 偏移（避免与已有飞行器冲突）
  python 飞行计划轨迹点位生成.py --route-names "航线A,航线B" --uid-start-offset 10
        """,
    )

    # 航线配置
    parser.add_argument(
        "--route-names",
        default=DEFAULT_ROUTE_NAMES,
        help=f"航线名称列表，多个航线用逗号分隔，默认 '{DEFAULT_ROUTE_NAMES}'",
    )
    parser.add_argument(
        "--route-id",
        default=None,
        help="直接指定航线 ID（air_route 表的 id），优先于 --route-names，用于精确选择单条航线",
    )

    # UAV 信息
    parser.add_argument(
        "--uid-start-offset",
        type=int,
        default=DEFAULT_UID_START_OFFSET,
        help=f"UAV ID 起始偏移（倒序列表索引），默认 {DEFAULT_UID_START_OFFSET}",
    )
    parser.add_argument(
        "--classification",
        type=int,
        default=DEFAULT_CLASSIFICATION,
        help=f"航空器分类: 0=微型 1=轻型 2=小型 3=中型 4=大型，默认 {DEFAULT_CLASSIFICATION}",
    )
    parser.add_argument(
        "--uids",
        default=DEFAULT_UIDS,
        help="指定 UAV ID 列表（逗号分隔），第N条航线使用第N个UID；优先于 --uid-start-offset",
    )

    # 飞行参数
    parser.add_argument(
        "--speed",
        type=float,
        default=DEFAULT_SPEED,
        help=f"飞行速度（m/s），默认 {DEFAULT_SPEED}",
    )
    parser.add_argument(
        "--speeds",
        default=DEFAULT_SPEEDS,
        help="各航线单独速度（逗号分隔），如 '15,20'；第N条航线使用第N个速度，优先于 --speed",
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=DEFAULT_ALTITUDE,
        help="飞行高度（米），默认 None（从数据库 minimum_safe_altitude 与 vertical_altitude 取中间整数）",
    )

    # 坐标系转换配置
    parser.add_argument(
        "--coord-system",
        default="wgs84",
        choices=["wgs84", "gcj02", "bd09"],
        help="数据库中 polygon 坐标的坐标系（默认 wgs84，即标准 GPS 坐标）",
    )
    parser.add_argument(
        "--coord-output",
        default=None,
        help="输出 JSON 的坐标系（默认与 --coord-system 相同，不转换）。可选: wgs84, gcj02, bd09",
    )

    # 输出配置
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"JSON 输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )

    # 碰撞预警场景配置（新增）
    parser.add_argument(
        "--meeting-mode",
        action="store_true",
        default=DEFAULT_MEETING_MODE,
        help="启用碰撞预警模式：查找航线交汇点，生成同步到达的轨迹",
    )
    parser.add_argument(
        "--meeting-threshold",
        type=float,
        default=DEFAULT_MEETING_DISTANCE_THRESHOLD,
        help=f"交汇点距离阈值（米），默认 {DEFAULT_MEETING_DISTANCE_THRESHOLD}",
    )
    parser.add_argument(
        "--warning-time",
        type=int,
        default=DEFAULT_WARNING_TIME_SEC,
        help=f"告警开始时间（秒），到达交汇点前多少秒开始告警，默认 {DEFAULT_WARNING_TIME_SEC}",
    )
    parser.add_argument(
        "--collision-time",
        type=float,
        default=DEFAULT_COLLISION_TARGET_SEC,
        help=f"目标碰撞时间（秒），从起飞到交汇点的飞行时间，速度据此自动计算，默认 {DEFAULT_COLLISION_TARGET_SEC}",
    )
    parser.add_argument(
        "--zone-output",
        action="store_true",
        default=DEFAULT_ZONE_OUTPUT,
        help="是否输出区域标记（1=飞行期1, 2=告警期, 3=飞行区），默认 True",
    )

    args = parser.parse_args()

    # 检查 UAV ID 池
    if not UAV_IDENTIFIERS_EXTENDED:
        print("[错误] 无法加载 UAV_IDENTIFIERS_EXTENDED，请检查 uav_identifiers_extended.py 路径")
        sys.exit(1)

    # 解析航线名称列表
    route_names = [name.strip() for name in args.route_names.split(",") if name.strip()]
    if not route_names:
        print("[错误] 未指定有效的航线名称")
        sys.exit(1)

    print(f"[信息] 共需处理 {len(route_names)} 条航线: {', '.join(route_names)}")
    print(f"[信息] UAV ID 起始偏移: {args.uid_start_offset}")

    # 解析指定UID列表
    uid_list = [u.strip() for u in args.uids.split(",") if u.strip()] if args.uids else []
    # 尝试从扩展列表查找 reg_sign
    uid_reg_sign_map = {}
    for u in uid_list:
        found_rs = None
        for uid_val, rs_val in UAV_IDENTIFIERS_EXTENDED:
            if uid_val == u:
                found_rs = rs_val
                break
        uid_reg_sign_map[u] = found_rs if found_rs is not None else u

    # 解析各航线单独速度
    speed_list = [float(s.strip()) for s in args.speeds.split(",") if s.strip()] if args.speeds else []

    # ==================== 碰撞预警模式处理 ====================
    if args.meeting_mode:
        # 需要至少2条航线才能进行交汇点检测
        if len(route_names) < 2:
            print("[错误] 碰撞预警模式需要至少2条航线")
            sys.exit(1)

        # 碰撞预警模式下，速度根据目标碰撞时间自动计算，忽略 --speed 和 --speeds
        print(f"[碰撞预警模式] 启用交汇点检测")
        print(f"[碰撞预警模式] 交汇点距离阈值: {args.meeting_threshold} 米")
        print(f"[碰撞预警模式] 告警时间: {args.warning_time} 秒")
        print(f"[碰撞预警模式] 目标碰撞时间: {args.collision_time} 秒（速度将自动计算）")

        # 步骤1: 查询所有航线的航路点
        route_data_list = []
        for route_name in route_names:
            print(f"\n[信息] 查询航线: {route_name}")
            route_record = query_air_route(route_name)
            if not route_record:
                print(f"[错误] 无法获取航线 '{route_name}' 的数据")
                sys.exit(1)

            route_id_db = route_record.get("id") or route_record.get("ID") or route_record.get("Id")
            route_points = []
            if route_id_db:
                print(f"[信息] 从 air_route_element 查询航路点 (route_id={route_id_db})")
                route_points = query_route_elements(route_id_db)

            if len(route_points) < 2:
                print("[警告] air_route_element 未查询到航路点，尝试解析 polygon 字段")
                polygon_val = (
                    route_record.get("polygon")
                    or route_record.get("POLYGON")
                    or route_record.get("Polygon")
                )
                route_points = parse_polygon(polygon_val)

            if len(route_points) < 2:
                print(f"[错误] 航线 '{route_name}' 航路点不足 2 个")
                sys.exit(1)

            route_data_list.append({
                "name": route_name,
                "record": route_record,
                "points": route_points,
            })

        # 步骤2: 查找交汇点（只检查前两条航线）
        print(f"\n[碰撞预警模式] 检测航线 '{route_data_list[0]['name']}' 与 '{route_data_list[1]['name']}' 之间的交汇点")
        meeting_points = find_meeting_points(
            route_data_list[0]["points"],
            route_data_list[1]["points"],
            threshold_meters=args.meeting_threshold
        )

        if not meeting_points:
            print("[错误] 未找到交汇点，请检查航线是否相交或调整交汇点距离阈值")
            sys.exit(1)

        # 使用第一个交汇点
        best_meeting = meeting_points[0]
        print(f"[碰撞预警模式] 找到交汇点: lon={best_meeting['lon']:.6f}, lat={best_meeting['lat']:.6f}")
        print(f"[碰撞预警模式] 交汇点距离: {best_meeting['distance']:.1f} 米")
        print(f"[碰撞预警模式] 航线A点索引: {best_meeting['idx_a']}, 航线B点索引: {best_meeting['idx_b']}")

        # 步骤3: 根据目标碰撞时间自动计算速度
        collision_target = args.collision_time
        dist_a = calculate_route_distance_to_point(route_data_list[0]["points"], best_meeting["idx_a"])
        dist_b = calculate_route_distance_to_point(route_data_list[1]["points"], best_meeting["idx_b"])

        speed_a = dist_a / collision_target
        speed_b = dist_b / collision_target
        meeting_speeds = [speed_a, speed_b]

        print(f"[碰撞预警模式] 航线A到交汇点距离: {dist_a:.1f} m, 自动计算速度: {speed_a:.2f} m/s")
        print(f"[碰撞预警模式] 航线B到交汇点距离: {dist_b:.1f} m, 自动计算速度: {speed_b:.2f} m/s")

        base_time_ms = int(datetime.now().timestamp() * 1000)
        meeting_time_ms = base_time_ms + int(collision_target * 1000)
        # 步骤4: 为每条航线生成带区域标记的轨迹
        success_count = 0
        uid_reg_sign_map = {}

        for u in uid_list:
            found_rs = None
            for uid_val, rs_val in UAV_IDENTIFIERS_EXTENDED:
                if uid_val == u:
                    found_rs = rs_val
                    break
            uid_reg_sign_map[u] = found_rs if found_rs is not None else u

        for idx, route_data in enumerate(route_data_list):
            route_name = route_data["name"]
            route_points = route_data["points"]
            speed_ms = meeting_speeds[idx]

            # 获取航线的最小安全高度和垂直高度
            route_record = route_data["record"]
            min_safe_alt = route_record.get("minimum_safe_altitude") or route_record.get("MINIMUM_SAFE_ALTITUDE")
            vert_alt = route_record.get("vertical_altitude") or route_record.get("VERTICAL_ALTITUDE")

            # 计算飞行高度
            if args.altitude is not None:
                flight_altitude = args.altitude
            else:
                try:
                    min_alt = float(min_safe_alt) if min_safe_alt is not None else 0
                    vert_alt_val = float(vert_alt) if vert_alt is not None else 0
                    flight_altitude = int((min_alt + vert_alt_val) / 2)
                except (ValueError, TypeError):
                    flight_altitude = 30

            # 同时起飞，无时间偏移
            start_time_ms = base_time_ms

            # 获取UAV ID
            specified_uid = uid_list[idx] if idx < len(uid_list) else None
            if specified_uid is None:
                id_pool = UAV_IDENTIFIERS_EXTENDED[::-1]
                actual_offset = (args.uid_start_offset + idx) % len(id_pool)
                specified_uid, _ = id_pool[actual_offset]

            actual_reg_sign = uid_reg_sign_map.get(specified_uid, specified_uid)

            print(f"\n[信息] 处理航线: {route_name}, UAV ID: {specified_uid}")
            print(f"[信息] 自动计算速度 {speed_ms:.2f} m/s, 同时起飞")

            # 使用新的碰撞预警函数生成轨迹
            telemetry_data = generate_collision_warning_flight_plan_data(
                uid=specified_uid,
                reg_sign=actual_reg_sign,
                route_points=route_points,
                speed_ms=speed_ms,
                altitude=flight_altitude,
                meeting_time_ms=meeting_time_ms,
                warning_time_sec=args.warning_time,
                start_time_ms=start_time_ms,
                interval_ms=DEFAULT_INTERVAL_MS,
                classification=args.classification,
                zone_output=args.zone_output,
            )

            # 统计各区域点数
            zone_counts = {1: 0, 2: 0, 3: 0}
            for point in telemetry_data:
                zone = point.get("zone", 0)
                if zone in zone_counts:
                    zone_counts[zone] += 1

            print(f"[信息] 区域统计: 飞行期1={zone_counts[1]}点, 告警期={zone_counts[2]}点, 飞行区={zone_counts[3]}点")

            # 确保输出目录存在
            os.makedirs(args.output_dir, exist_ok=True)

            # 写入JSON文件（标准遥测数组格式，供 SceneEmitter 直接发射）
            safe_route_name = route_name.replace(" ", "").replace("/", "_")
            filename = f"{safe_route_name}_碰撞预警_{specified_uid}.json"
            output_path = os.path.join(args.output_dir, filename)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(telemetry_data, f, ensure_ascii=False, indent=2)

            duration_sec = (telemetry_data[-1]["timestamp"] - telemetry_data[0]["timestamp"]) / 1000.0
            print(f"[完成] 输出: {output_path}")
            print(f"  数据条数: {len(telemetry_data)}")
            print(f"  时间跨度: {duration_sec:.1f} 秒")
            success_count += 1

        print(f"\n[总结] 碰撞预警模式完成，成功生成 {success_count} 个文件")
        sys.exit(0 if success_count == len(route_names) else 1)

    # ==================== 普通模式处理 ====================
    # 逐条航线处理
    success_count = 0
    for idx, route_name in enumerate(route_names):
        uid_offset = args.uid_start_offset + idx
        # 如果配置了UID列表，第N条航线使用第N个UID
        specified_uid = uid_list[idx] if idx < len(uid_list) else None
        specified_reg_sign = uid_reg_sign_map.get(specified_uid) if specified_uid else None
        # 优先使用指定速度，否则使用全局速度
        route_speed = speed_list[idx] if idx < len(speed_list) else args.speed
        # 只有单条航线时才使用 --route-id
        route_id = args.route_id if len(route_names) == 1 else None
        ok = process_single_route(
            route_name=route_name,
            route_id=route_id,
            speed_ms=route_speed,
            altitude=args.altitude,
            uid_offset=uid_offset,
            interval_ms=DEFAULT_INTERVAL_MS,
            classification=args.classification,
            output_dir=args.output_dir,
            coord_system=args.coord_system,
            coord_output=args.coord_output,
            uid=specified_uid,
            reg_sign=specified_reg_sign,
        )
        if ok:
            success_count += 1

    print(f"\n[总结] 成功生成 {success_count} / {len(route_names)} 个飞行计划 JSON 文件")
    if success_count < len(route_names):
        print("[提示] 部分航线生成失败，请检查上述错误信息")
        sys.exit(1)


if __name__ == "__main__":
    main()
