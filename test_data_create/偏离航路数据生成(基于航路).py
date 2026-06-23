#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
偏离航路数据生成脚本

功能：
1. 连接达梦数据库查询 air_route 表，获取航线 polygon、宽度、高度等信息
2. 沿航线插值生成遥测轨迹（每秒 1 个坐标点）
3. 支持三种偏离模式：
   - horizontal: 仅水平偏移（向右偏离中心线）
   - vertical: 仅高度偏移（上升或下降）
   - both: 综合偏移（水平+高度同时偏移）
4. 偏离过程平滑渐变，坐标连续无跳变
5. 输出 JSON 到 mock 目录

关键说明：
- 飞行高度默认从数据库的 minimum_safe_altitude 与 vertical_altitude 取中间整数，
  也可通过 --altitude 手动覆盖。
- 偏离距离指偏离航线中心线的垂直距离（米）。
  例如：航路宽度 1000 米，想偏离边界 100 米 → 偏离中心线 500+100=600 米。
- 偏航开始后，偏移量在 --deviate-transition 秒内从 0 平滑渐变到目标值，
  保证坐标连续性，不出现跳变。
- 航线转弯处每段按各自航向的垂直方向偏移，整体始终向"右侧"偏移。

用法示例：
  # 默认参数（水平偏移 600 米，第 20 秒开始偏航）
  python 偏离航路数据生成(基于航路).py

  # 指定航线与偏离参数
  python 偏离航路数据生成(基于航路).py --route-name "跨顺义三河段" --deviate-offset 600 --deviate-start 30

  # 仅沿中心线飞行（不偏航，用于对比基线数据）
  python 偏离航路数据生成(基于航路).py --deviate-offset 0

  # 指定 UAV ID、速度与手动高度
  python 偏离航路数据生成(基于航路).py --uid-offset 0 --speed 15 --altitude 50

  # 高度偏移模式（仅上升）
  python 偏离航路数据生成(基于航路).py --deviate-mode vertical --deviate-altitude-offset 20

  # 综合偏移模式（水平偏移 + 高度同时偏移）
  python 偏离航路数据生成(基于航路).py --deviate-mode both --deviate-offset 600 --deviate-altitude-offset 15
"""

import os
import sys
import json
import math
import argparse
from datetime import datetime
from tkinter import N
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
DEFAULT_ROUTE_NAME = "跨顺义三河段"      # 默认查询的航线名称
DEFAULT_DEVIATE_OFFSET = 0.0        # 偏离航道数值（米），实际偏离中心线 = 航路宽度/2 + 此值；为0时沿中心线飞行
DEFAULT_DEVIATE_START = 0            # 第几秒开始偏离（从 0 开始计数）
DEFAULT_SPEED = 15.0                  # 飞行速度（m/s），决定每秒经纬度增量
DEFAULT_ALTITUDE = 40.0               # 飞行高度（米），None 表示从数据库自动计算
DEFAULT_UID_OFFSET = 10                # UAV ID 起始偏移（倒序列表中的索引）
DEFAULT_INTERVAL_MS = 1000            # 采样间隔（毫秒），固定每秒 1 个点
DEFAULT_CLASSIFICATION = 3            # 航空器分类: 0=微型 1=轻型 2=小型 3=中型 4=大型
DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "mock")  # JSON 输出目录
DEFAULT_DEVIATE_TRANSITION = None      # 偏离渐变时间（秒），None 表示根据偏离距离和飞行速度自动计算
DEFAULT_DEVIATE_ALTITUDE_OFFSET = 0.0   # 高度偏离数值（米），正值=上升，负值=下降。最终高度 = 基础高度 + 此值，基础高度 = (minimum_safe_altitude + vertical_altitude) / 2
DEFAULT_DEVIATE_MODE = "horizontal"     # 偏离模式: horizontal=仅水平偏移, vertical=仅高度偏移, both=水平+高度综合偏移
DEFAULT_FILENAME = "跨顺义三河段航路最低安全高度数据_0.1.json"                 # 默认输出JSON文件名，None=自动生成（如：跨顺义三河段航路偏航数据_0.1.json）；可改为固定名称如 "test.json"
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
    用于确定飞行方向，垂直方向 = heading + 90°（右侧）。
    """
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    heading = math.degrees(math.atan2(de, dn))
    if heading < 0:
        heading += 360.0
    return heading


def offset_point(lat: float, lon: float, heading_deg: float, offset_m: float) -> tuple[float, float]:
    """
    将坐标沿垂直于航向的方向（右侧，即 heading_deg + 90°）偏移指定米数。
    返回 (new_lat, new_lon)。
    """
    perp_heading = math.radians(heading_deg + 90)  # 右侧垂直方向
    dn = offset_m * math.cos(perp_heading)          # 北向位移（米）
    de = offset_m * math.sin(perp_heading)          # 东向位移（米）
    d_lat = dn / RE_EARTH                           # 纬度增量（弧度）
    d_lon = de / (RE_EARTH * math.cos(math.radians(lat)))  # 经度增量（弧度）
    return lat + math.degrees(d_lat), lon + math.degrees(d_lon)


def offset_route_points_list(
    points: List[Dict[str, float]], offset_m: float
) -> List[Dict[str, float]]:
    """
    将整条航线的航路点整体向右侧偏移 offset_m 米。
    对每条线段做平行偏移，相邻偏移线段在交界处取中点连接，
    保证偏移后的航线严格平行于中心线。
    """
    if not points or offset_m == 0:
        return [dict(p) for p in points]

    n = len(points)
    if n < 2:
        return [dict(p) for p in points]

    # 步骤 1：对每条线段做平行偏移
    offset_segments = []
    for i in range(n - 1):
        heading = calc_heading(
            points[i]["lat"], points[i]["lon"],
            points[i + 1]["lat"], points[i + 1]["lon"]
        )
        p1_lat, p1_lon = offset_point(
            points[i]["lat"], points[i]["lon"], heading, offset_m
        )
        p2_lat, p2_lon = offset_point(
            points[i + 1]["lat"], points[i + 1]["lon"], heading, offset_m
        )
        offset_segments.append({
            "p1": {"lat": p1_lat, "lon": p1_lon},
            "p2": {"lat": p2_lat, "lon": p2_lon},
        })

    # 步骤 2：从偏移线段构建航路点列表
    # 第1个点 = 第1条偏移线段的起点
    result = [dict(offset_segments[0]["p1"])]

    # 中间点 = 相邻偏移线段交界处的两个端点的中点
    for i in range(len(offset_segments) - 1):
        end_current = offset_segments[i]["p2"]
        start_next = offset_segments[i + 1]["p1"]
        mid_lat = (end_current["lat"] + start_next["lat"]) / 2
        mid_lon = (end_current["lon"] + start_next["lon"]) / 2
        result.append({"lat": mid_lat, "lon": mid_lon})

    # 最后1个点 = 最后一条偏移线段的终点
    result.append(dict(offset_segments[-1]["p2"]))

    return result


# ==================== 坐标系转换 ====================
# WGS-84: 国际 GPS 标准坐标系（数据库通常存储此坐标）
# GCJ-02: 火星坐标系（国测局加密坐标），高德/腾讯/谷歌中国地图使用
# BD-09: 百度坐标系（在 GCJ-02 基础上二次加密）
#
# 转换关系: WGS-84 <-> GCJ-02 <-> BD-09
# 中国境内 WGS-84 与 GCJ-02 偏移约 50~100 米，GCJ-02 与 BD-09 偏移约 20~50 米


def _transformlat(lng: float, lat: float) -> float:
    """GCJ-02 加密辅助函数：纬度偏移计算"""
    ret = (
        -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat
        + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
    )
    ret += (
        (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi))
        * 2.0 / 3.0
    )
    ret += (
        (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi))
        * 2.0 / 3.0
    )
    ret += (
        (160.0 * math.sin(lat / 12.0 * math.pi) + 320.0 * math.sin(lat * math.pi / 30.0))
        * 2.0 / 3.0
    )
    return ret


def _transformlng(lng: float, lat: float) -> float:
    """GCJ-02 加密辅助函数：经度偏移计算"""
    ret = (
        300.0 + lng + 2.0 * lat + 0.1 * lng * lng
        + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
    )
    ret += (
        (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi))
        * 2.0 / 3.0
    )
    ret += (
        (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi))
        * 2.0 / 3.0
    )
    ret += (
        (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng / 30.0 * math.pi))
        * 2.0 / 3.0
    )
    return ret


def _out_of_china(lng: float, lat: float) -> bool:
    """判断坐标是否在中国境外（境外不做 GCJ-02 加密偏移）"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """WGS-84 转 GCJ-02（火星坐标系）"""
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transformlat(lng - 105.0, lat - 35.0)
    dlng = _transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / (
        (6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi
    )
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    return lng + dlng, lat + dlat


def gcj02_to_wgs84(lng: float, lat: float) -> tuple[float, float]:
    """GCJ-02 转 WGS-84（使用近似反向迭代算法）"""
    if _out_of_china(lng, lat):
        return lng, lat
    # 迭代逼近：用 GCJ-02 减去 WGS84->GCJ02 的偏移量
    dlat = _transformlat(lng - 105.0, lat - 35.0)
    dlng = _transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - 0.00669342162296594323 * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / (
        (6378245.0 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * math.pi
    )
    dlng = (dlng * 180.0) / (6378245.0 / sqrtmagic * math.cos(radlat) * math.pi)
    return lng - dlng, lat - dlat


def gcj02_to_bd09(lng: float, lat: float) -> tuple[float, float]:
    """GCJ-02 转 BD-09（百度坐标系）"""
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * math.pi * 3000.0 / 180.0)
    theta = math.atan2(lat, lng) + 0.000003 * math.cos(lng * math.pi * 3000.0 / 180.0)
    return z * math.cos(theta) + 0.0065, z * math.sin(theta) + 0.006


def bd09_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """BD-09 转 GCJ-02"""
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)
    return z * math.cos(theta), z * math.sin(theta)


def convert_coordinate(lng: float, lat: float, from_sys: str, to_sys: str) -> tuple[float, float]:
    """
    通用坐标转换入口。
    支持: wgs84, gcj02, bd09
    转换路径: wgs84 <-> gcj02 <-> bd09
    """
    from_sys = from_sys.lower().strip()
    to_sys = to_sys.lower().strip()
    if from_sys == to_sys:
        return lng, lat

    # WGS-84 -> GCJ-02
    if from_sys == "wgs84" and to_sys == "gcj02":
        return wgs84_to_gcj02(lng, lat)
    # GCJ-02 -> WGS-84
    elif from_sys == "gcj02" and to_sys == "wgs84":
        return gcj02_to_wgs84(lng, lat)
    # GCJ-02 -> BD-09
    elif from_sys == "gcj02" and to_sys == "bd09":
        return gcj02_to_bd09(lng, lat)
    # BD-09 -> GCJ-02
    elif from_sys == "bd09" and to_sys == "gcj02":
        return bd09_to_gcj02(lng, lat)
    # WGS-84 -> BD-09（经 GCJ-02 中转）
    elif from_sys == "wgs84" and to_sys == "bd09":
        lng, lat = wgs84_to_gcj02(lng, lat)
        return gcj02_to_bd09(lng, lat)
    # BD-09 -> WGS-84（经 GCJ-02 中转）
    elif from_sys == "bd09" and to_sys == "wgs84":
        lng, lat = bd09_to_gcj02(lng, lat)
        return gcj02_to_wgs84(lng, lat)
    else:
        # 不支持的转换组合，保持原样
        return lng, lat


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


# ==================== 偏离计算（平滑渐变，坐标连续）====================
def _smooth_angles(angles: List[float], window: int = 5) -> List[float]:
    """对角度列表进行滑动平均平滑，正确处理 360° 环绕。"""
    n = len(angles)
    if n <= 1:
        return angles[:]
    result = []
    half = window // 2
    for i in range(n):
        window_angles = []
        for j in range(max(0, i - half), min(n, i + half + 1)):
            h = angles[j]
            # 统一角度范围，避免 359° 和 1° 的平均问题
            while h - angles[i] > 180:
                h -= 360
            while h - angles[i] < -180:
                h += 360
            window_angles.append(h)
        avg = sum(window_angles) / len(window_angles)
        avg = avg % 360
        result.append(avg)
    return result


def _smooth_interpolate_heading(h1: float, h2: float, ratio: float) -> float:
    """
    平滑插值两个航向角，正确处理 360° 环绕。
    ratio: 0.0 时返回 h1，1.0 时返回 h2。
    """
    diff = h2 - h1
    while diff > 180:
        diff -= 360
    while diff < -180:
        diff += 360
    h = h1 + diff * ratio
    return h % 360


def apply_deviation(
    trajectory: List[Dict[str, Any]],
    offset_m: float,
    start_second: int,
    transition_sec: int = 5,
) -> None:
    """
    在轨迹上应用偏离偏移，原地修改每个点的 lat/lon。

    偏离规则:
    1. 偏航前（elapsed_sec < start_second）：沿中心线飞行，不偏移。
    2. 渐变期（start_second <= elapsed_sec < start_second + transition_sec）：
       偏移量从 0 线性渐变到 offset_m，保证坐标连续性，无跳变。
    3. 稳定期（elapsed_sec >= start_second + transition_sec）：
       固定偏移 offset_m。
    4. 偏移方向：沿平滑后的航向右侧偏移，避免航段交界处 heading 突变导致的跳变/回头。

    参数:
        trajectory: 插值后的轨迹点列表（会被原地修改）
        offset_m: 目标偏移距离（米），正值向右侧
        start_second: 第几秒开始偏航
        transition_sec: 渐变过渡时间（秒）
    """
    if not trajectory or offset_m == 0:
        return

    # 平滑 heading，消除航段交界处的方向突变
    raw_headings = [p["heading"] for p in trajectory]
    smooth_headings = _smooth_angles(raw_headings, window=5)

    base_time_ms = trajectory[0]["time_ms"]

    for i, point in enumerate(trajectory):
        # 计算该点从起飞开始的经过时间（秒）
        elapsed_sec = (point["time_ms"] - base_time_ms) / 1000.0

        if elapsed_sec < start_second:
            # 偏航前：无偏移
            continue

        # 计算当前时刻的偏移量（平滑渐变）
        if elapsed_sec < start_second + transition_sec and transition_sec > 0:
            # 渐变期：线性插值偏移量
            ratio = (elapsed_sec - start_second) / transition_sec
            current_offset = offset_m * ratio
        else:
            # 稳定期：达到目标偏移量
            current_offset = offset_m

        # 沿平滑后的航向垂直方向（右侧）偏移
        new_lat, new_lon = offset_point(
            point["lat"], point["lon"], smooth_headings[i], current_offset
        )
        point["lat"] = new_lat
        point["lon"] = new_lon


def _print_deviation_stats(
    traj_center: List[Dict[str, Any]],
    trajectory: List[Dict[str, Any]],
    deviate_start_sec: int,
    transition_sec: int,
    start_time_ms: int,
    target_horizontal_offset: float,
    target_vertical_offset: float = 0.0,
    deviate_mode: str = "horizontal",
) -> None:
    """
    打印偏离距离统计信息，帮助用户了解过渡期和平行飞行阶段的偏移情况。
    """
    deviate_start_ms = start_time_ms + deviate_start_sec * 1000
    transition_end_ms = deviate_start_ms + transition_sec * 1000

    # 找过渡期起点、中点、终点的偏离距离
    start_dist = None
    mid_dist = None
    end_dist = None
    max_dist = 0.0
    exceed_500_count = 0

    # 高度相关统计
    has_vertical = deviate_mode in ("vertical", "both") and target_vertical_offset != 0
    start_alt = None
    mid_alt = None
    end_alt = None
    max_alt_offset = 0.0

    for i, pt in enumerate(trajectory):
        if i >= len(traj_center):
            break
        t = pt["time_ms"]

        # 水平距离统计
        dist = geo_distance(
            traj_center[i]["lat"], traj_center[i]["lon"],
            pt["lat"], pt["lon"]
        )
        if dist > max_dist:
            max_dist = dist
        if dist > 500:
            exceed_500_count += 1

        # 过渡期起点 (t == deviate_start_ms)
        if start_dist is None and t >= deviate_start_ms:
            start_dist = dist
            if has_vertical:
                start_alt = pt.get("altitude_offset", 0.0)
        # 过渡期中点
        if mid_dist is None and t >= deviate_start_ms + transition_sec * 500:
            mid_dist = dist
            if has_vertical:
                mid_alt = pt.get("altitude_offset", 0.0)
        # 过渡期终点
        if end_dist is None and t >= transition_end_ms:
            end_dist = dist
            if has_vertical:
                end_alt = pt.get("altitude_offset", 0.0)

        # 高度偏移统计
        if has_vertical:
            alt_offset = abs(pt.get("altitude_offset", 0.0))
            if alt_offset > max_alt_offset:
                max_alt_offset = alt_offset

    print(f"\n[偏离统计]")
    print(f"  偏离模式: {deviate_mode}")

    if deviate_mode in ("horizontal", "both"):
        print(f"  目标水平偏移量: {target_horizontal_offset:.1f} 米")
        print(f"  过渡期 ({deviate_start_sec}s ~ {deviate_start_sec + transition_sec}s):")
        if start_dist is not None:
            print(f"    起点偏离: {start_dist:.1f} 米")
        if mid_dist is not None:
            print(f"    中点偏离: {mid_dist:.1f} 米")
        if end_dist is not None:
            print(f"    终点偏离: {end_dist:.1f} 米")
        print(f"  平行飞行最大偏离: {max_dist:.1f} 米")
        if deviate_mode == "horizontal":
            print(f"  偏离超过500米的点数: {exceed_500_count} / {len(trajectory)}")

    if deviate_mode in ("vertical", "both"):
        print(f"  目标高度偏移量: {target_vertical_offset:.1f} 米")
        print(f"  过渡期 ({deviate_start_sec}s ~ {deviate_start_sec + transition_sec}s):")
        if start_alt is not None:
            print(f"    起点偏移: {start_alt:.1f} 米")
        if mid_alt is not None:
            print(f"    中点偏移: {mid_alt:.1f} 米")
        if end_alt is not None:
            print(f"    终点偏移: {end_alt:.1f} 米")
        print(f"  最大高度偏移: {max_alt_offset:.1f} 米")


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
    生成单条遥测数据字典，格式匹配偏离航路告警场景 JSON。
    字段与 create_data_scene.py / 飞行器状态告警数据点位生成.py 保持一致。
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
def generate_deviation_data(
    uid: str,
    reg_sign: str,
    route_points: List[Dict[str, float]],
    speed_ms: float,
    altitude: float,
    deviate_offset_m: float,
    deviate_start_sec: int,
    transition_sec: int,
    start_time_ms: Optional[int] = None,
    interval_ms: int = 1000,
    classification: int = 2,
    deviate_altitude_offset: float = 0.0,
    deviate_mode: str = "horizontal",
) -> List[Dict[str, Any]]:
    """
    生成偏离航路场景的完整遥测数据。

    流程:
    1. 沿中心线插值（每秒一个点）。
    2. 对中心线 heading 做滑动平均平滑，消除航段交界处的方向突变。
    3. 按时间生成轨迹（根据 deviate_mode 支持三种模式）：
       - horizontal: 仅水平偏移（向右偏离）
       - vertical: 仅高度偏移（上升/下降）
       - both: 综合偏移（水平+高度同时偏移）
       每种模式均支持三阶段：偏移前、过渡期、稳定期
    4. 将轨迹点转换为遥测数据格式。

    此方式保证飞行器始终沿一条连续的航线飞行，不会在航段交界处
    因 heading 突变或索引错位而导致偏移方向跳变、轨迹回头或超出目标偏移距离。

    参数:
        uid: 无人机唯一识别码
        reg_sign: 实名登记标识
        route_points: 航路点列表（polygon 解析结果）
        speed_ms: 飞行速度（m/s）
        altitude: 基础飞行高度（米），由数据库 minimum_safe_altitude 与 vertical_altitude 取中间值
        deviate_offset_m: 水平偏离距离（米），向航线右侧偏移
        deviate_start_sec: 第几秒开始偏离
        transition_sec: 渐变过渡时间（秒）
        start_time_ms: 起始时间戳（毫秒），None 表示使用当前时间
        interval_ms: 采样间隔（毫秒），默认 1000（每秒一个点）
        classification: 航空器分类
        deviate_altitude_offset: 高度偏离数值（米），正=上升，负=下降。
            计算方式: 最终高度 = 基础高度 + deviate_altitude_offset
            基础高度 = (minimum_safe_altitude + vertical_altitude) / 2
        deviate_mode: 偏离模式，horizontal=仅水平偏移；vertical=仅高度偏移；both=综合偏移
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

    # 对中心线 heading 做滑动平均平滑，消除航段交界处的方向突变
    # 避免渐变期因 heading 跳变导致偏移方向突变，形成"羊角"轨迹
    raw_headings = [p["heading"] for p in traj_center]
    smooth_headings = _smooth_angles(raw_headings, window=5)

    # 判断是否需要进行偏移（水平或高度）
    need_horizontal = deviate_mode in ("horizontal", "both") and deviate_offset_m != 0
    need_vertical = deviate_mode in ("vertical", "both") and deviate_altitude_offset != 0

    if not need_horizontal and not need_vertical:
        # 无需偏移，直接使用中心线
        trajectory = traj_center
    else:
        # 步骤 2：按时间生成轨迹，根据模式分别计算水平和高度偏移
        deviate_start_ms = start_time_ms + deviate_start_sec * 1000
        transition_end_ms = deviate_start_ms + transition_sec * 1000

        trajectory: List[Dict[str, Any]] = []
        for i, center_pt in enumerate(traj_center):
            t = center_pt["time_ms"]

            if t < deviate_start_ms:
                # 偏移前：沿中心线飞行
                pt = dict(center_pt)
                pt["heading"] = smooth_headings[i]
                pt["altitude_offset"] = 0.0
                trajectory.append(pt)
            elif t >= transition_end_ms:
                # 稳定期：达到目标偏移量
                new_lat = center_pt["lat"]
                new_lon = center_pt["lon"]

                # 水平偏移：沿平滑航向的右侧偏移（与渐变期保持一致）
                if need_horizontal:
                    new_lat, new_lon = offset_point(
                        new_lat, new_lon, smooth_headings[i], deviate_offset_m
                    )

                # 高度偏移：基础高度 + 偏离值
                altitude_offset = deviate_altitude_offset if need_vertical else 0.0

                trajectory.append({
                    "lat": new_lat,
                    "lon": new_lon,
                    "heading": smooth_headings[i],
                    "time_ms": t,
                    "segment_idx": center_pt.get("segment_idx", -1),
                    "altitude_offset": altitude_offset,
                })
            else:
                # 过渡期：偏移量从0线性渐变到目标值
                if transition_sec > 0:
                    ratio = (t - deviate_start_ms) / (transition_sec * 1000.0)
                else:
                    ratio = 1.0

                new_lat = center_pt["lat"]
                new_lon = center_pt["lon"]

                # 水平偏移：按比例渐变
                if need_horizontal:
                    current_horizontal_offset = deviate_offset_m * ratio
                    new_lat, new_lon = offset_point(
                        new_lat, new_lon, smooth_headings[i], current_horizontal_offset
                    )

                # 高度偏移：按比例渐变
                if need_vertical:
                    current_altitude_offset = deviate_altitude_offset * ratio
                else:
                    current_altitude_offset = 0.0

                trajectory.append({
                    "lat": new_lat,
                    "lon": new_lon,
                    "heading": smooth_headings[i],
                    "time_ms": t,
                    "segment_idx": center_pt.get("segment_idx", -1),
                    "altitude_offset": current_altitude_offset,
                })

    # 步骤 4：转换为遥测数据格式
    telemetry_data = []
    for point in trajectory:
        # 应用高度偏移：基础高度 + 偏移量
        point_altitude = altitude + point.get("altitude_offset", 0.0)

        telemetry_data.append(make_telemetry_point(
            uid=uid,
            reg_sign=reg_sign,
            timestamp_ms=point["time_ms"],
            lon=point["lon"],
            lat=point["lat"],
            alt=point_altitude,
            speed=speed_ms,
            heading=point["heading"],
            status=2,  # 飞行中
            classification=classification,
        ))

    # 偏离距离统计（仅偏移模式）
    if deviate_offset_m > 0 or deviate_altitude_offset != 0:
        _print_deviation_stats(
            traj_center, trajectory,
            deviate_start_sec, transition_sec,
            start_time_ms, deviate_offset_m, deviate_altitude_offset, deviate_mode
        )

    return telemetry_data


# ==================== 命令行参数与主函数 ====================
def main():
    parser = argparse.ArgumentParser(
        description="偏离航路数据生成脚本：沿航线飞行并在指定时间后偏离",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  # 默认参数（跨顺义三河段，航路宽1000米时偏离边界100米 = 中心线+600米，第60秒开始偏航）
  python 偏离航路数据生成(基于航路).py

  # 指定航线与偏离参数（航路宽1000米时，100表示超出边界100米，实际偏离中心线600米）
  python 偏离航路数据生成(基于航路).py --route-name "跨顺义三河段" --deviate-offset 100 --deviate-start 60

  # 仅沿中心线飞行（不偏航，验证用）
  python 偏离航路数据生成(基于航路).py --deviate-offset 0

  # 指定 UAV ID、速度、手动高度
  python 偏离航路数据生成(基于航路).py --uid-offset 0 --speed 15 --altitude 50
        """,

    )

    # 航线配置
    parser.add_argument(
        "--route-name",
        default=DEFAULT_ROUTE_NAME,
        help=f"航线名称（air_route 表的 route_name），默认 '{DEFAULT_ROUTE_NAME}'",
    )
    parser.add_argument(
        "--route-id",
        default=None,
        help="直接指定航线 ID（air_route 表的 id），优先于 --route-name，用于同名航线精确选择",
    )

    # UAV 信息
    parser.add_argument(
        "--uid-offset",
        type=int,
        default=DEFAULT_UID_OFFSET,
        help=f"UAV ID 起始偏移（倒序列表索引），默认 {DEFAULT_UID_OFFSET}",
    )
    parser.add_argument(
        "--classification",
        type=int,
        default=DEFAULT_CLASSIFICATION,
        help=f"航空器分类: 0=微型 1=轻型 2=小型 3=中型 4=大型，默认 {DEFAULT_CLASSIFICATION}",
    )

    # 飞行参数
    parser.add_argument(
        "--speed",
        type=float,
        default=DEFAULT_SPEED,
        help=f"飞行速度（m/s），默认 {DEFAULT_SPEED}",
    )
    parser.add_argument(
        "--altitude",
        type=float,
        default=DEFAULT_ALTITUDE,
        help="飞行高度（米），默认 None（从数据库 minimum_safe_altitude 与 vertical_altitude 取中间整数）",
    )

    # 偏离参数
    parser.add_argument(
        "--deviate-offset",
        type=float,
        default=DEFAULT_DEVIATE_OFFSET,
        help=f"偏离航道数值（米），实际偏离中心线 = 航路宽度/2 + 此值；为0时沿中心线飞行，默认 {DEFAULT_DEVIATE_OFFSET}",
    )
    parser.add_argument(
        "--deviate-start",
        type=int,
        default=DEFAULT_DEVIATE_START,
        help=f"第几秒开始偏离（从 0 开始），默认 {DEFAULT_DEVIATE_START}",
    )
    parser.add_argument(
        "--deviate-transition",
        type=int,
        default=DEFAULT_DEVIATE_TRANSITION,
        help="偏离渐变时间（秒），偏移量从 0 平滑过渡到目标值，默认自动计算（偏离距离/飞行速度）",
    )
    parser.add_argument(
        "--deviate-altitude-offset",
        type=float,
        default=DEFAULT_DEVIATE_ALTITUDE_OFFSET,
        help=f"高度偏离数值（米），正值为上升，负值为下降。"
             f"最终高度 = 基础高度 + 此值，基础高度 = (minimum_safe_altitude + vertical_altitude) / 2",
    )
    parser.add_argument(
        "--deviate-mode",
        type=str,
        default=DEFAULT_DEVIATE_MODE,
        choices=["horizontal", "vertical", "both"],
        help=f"偏离模式: horizontal=仅水平偏移, vertical=仅高度偏移, both=水平+高度综合偏移，默认 {DEFAULT_DEVIATE_MODE}",
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
    parser.add_argument(
        "--filename",
        default=DEFAULT_FILENAME,
        help="输出文件名，默认自动命名（如：金鸡湖巡航航路偏航数据_0.1.json）。也可通过 DEFAULT_FILENAME 变量在脚本内固定配置。",
    )

    args = parser.parse_args()

    # 检查 UAV ID 池
    if not UAV_IDENTIFIERS_EXTENDED:
        print("[错误] 无法加载 UAV_IDENTIFIERS_EXTENDED，请检查 uav_identifiers_extended.py 路径")
        sys.exit(1)

    # 获取 UAV ID（倒序列表）
    id_pool = UAV_IDENTIFIERS_EXTENDED[::-1]
    uid_offset = args.uid_offset % len(id_pool)
    uid, reg_sign = id_pool[uid_offset]
    print(f"[信息] 使用 UAV ID: {uid}, 实名登记: {reg_sign}")

    # 查询数据库获取航线信息
    if args.route_id is not None:
        print(f"[信息] 使用指定 route_id={args.route_id} 查询航线")
        # 构造一个极简的 route_record，只包含 id
        route_record = {"id": args.route_id}
    else:
        print(f"[信息] 查询航线: {args.route_name}")
        route_record = query_air_route(route_name=args.route_name)
        if not route_record:
            print(f"[错误] 无法获取航线 '{args.route_name}' 的数据，请确认航线名称正确且数据库可连接")
            sys.exit(1)

    # 提取航线关键字段（兼容大小写）
    route_name = (
        route_record.get("route_name")
        or route_record.get("ROUTE_NAME")
        or args.route_name
    )
    min_safe_alt = route_record.get("minimum_safe_altitude") or route_record.get("MINIMUM_SAFE_ALTITUDE")
    vert_alt = route_record.get("vertical_altitude") or route_record.get("VERTICAL_ALTITUDE")
    width = route_record.get("width") or route_record.get("WIDTH")

    # 获取航线 ID（用于查询 air_route_element）
    route_id = route_record.get("id") or route_record.get("ID") or route_record.get("Id")

    # 优先从 air_route_element 表查询航路中心线坐标
    if route_id is not None:
        print(f"[信息] 从 air_route_element 查询航路点 (route_id={route_id})")
        route_points = query_route_elements(route_id)
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
        sys.exit(1)
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
    if args.altitude is not None:
        altitude = args.altitude
        print(f"[信息] 使用手动指定飞行高度: {altitude} 米")
    else:
        try:
            min_alt = float(min_safe_alt) if min_safe_alt is not None else 0
            vert_alt_val = float(vert_alt) if vert_alt is not None else 0
            altitude = int((min_alt + vert_alt_val) / 2)
            print(f"[信息] 自动计算飞行高度: ({min_alt} + {vert_alt_val}) / 2 = {altitude} 米")
        except (ValueError, TypeError):
            altitude = 30
            print(f"[警告] 数据库高度字段异常，使用默认高度: {altitude} 米")

    # 计算实际偏离量：根据航路宽度和用户输入的偏离航道数值
    try:
        width_val = float(width) if width is not None else 0
        if args.deviate_offset == 0:
            actual_offset = 0.0
            print(f"[信息] 航路宽度: {width_val} 米，偏离航道数值: {args.deviate_offset} 米 → 沿中心线飞行")
        else:
            actual_offset = width_val / 2 + args.deviate_offset
            print(f"[信息] 航路宽度: {width_val} 米，偏离航道数值: {args.deviate_offset} 米")
            print(f"[信息] 实际偏离中心线: {width_val}/2 + {args.deviate_offset} = {actual_offset} 米")
            if width_val > 0 and abs(actual_offset) > width_val / 2:
                print(f"[提示] 当前偏离量已超出航路边界（边界在中心线 ±{width_val/2} 米处）")
    except (ValueError, TypeError):
        width_val = 0
        actual_offset = args.deviate_offset
        print(f"[警告] 航路宽度信息不可用，直接使用偏离数值: {actual_offset} 米")

    # 计算渐变时间：若未手动指定，则根据偏离距离和飞行速度自动计算
    if args.deviate_transition is not None and args.deviate_transition > 0:
        transition_sec = args.deviate_transition
        print(f"[信息] 使用手动指定渐变时间: {transition_sec} 秒")
    else:
        # 自动计算：渐变期间飞行距离 ≈ 偏离距离，保证平滑过渡
        # 公式: transition_sec = deviate_offset_m / speed_ms，限制在 [5, 60] 秒
        transition_sec = max(5, min(60, int(actual_offset / args.speed)))
        print(f"[信息] 自动计算渐变时间: 偏离 {actual_offset:.0f}m / 速度 {args.speed}m/s ≈ {transition_sec} 秒")

    # 生成偏离航路数据
    print(f"[信息] 开始生成数据: 速度 {args.speed} m/s, 偏航起点 {args.deviate_start} 秒")
    print(f"[信息] 偏离模式: {args.deviate_mode}, 水平偏移: {actual_offset} 米, 高度偏移: {args.deviate_altitude_offset} 米")
    telemetry_data = generate_deviation_data(
        uid=uid,
        reg_sign=reg_sign,
        route_points=route_points,
        speed_ms=args.speed,
        altitude=altitude,
        deviate_offset_m=actual_offset,
        deviate_start_sec=args.deviate_start,
        transition_sec=transition_sec,
        classification=args.classification,
        deviate_altitude_offset=args.deviate_altitude_offset,
        deviate_mode=args.deviate_mode,
    )

    # 坐标系转换：根据 --coord-system 和 --coord-output 参数转换输出坐标
    coord_from = args.coord_system.lower()
    coord_to = (args.coord_output or coord_from).lower()
    if coord_from != coord_to:
        print(f"[信息] 坐标系转换: {coord_from.upper()} -> {coord_to.upper()}")
        converted_count = 0
        for point in telemetry_data:
            new_lon, new_lat = convert_coordinate(
                point["longitude"], point["latitude"], coord_from, coord_to
            )
            point["longitude"] = round(new_lon, 14)
            point["latitude"] = round(new_lat, 14)
            converted_count += 1
        print(f"[信息] 已转换 {converted_count} 个坐标点")
    else:
        print(f"[信息] 坐标系: {coord_from.upper()}（不转换）")

    # 确定输出文件路径
    os.makedirs(args.output_dir, exist_ok=True)
    if args.filename:
        filename = args.filename if args.filename.endswith(".json") else args.filename + ".json"
    else:
        # 命名格式: {航路名}航路偏航数据_0.1.json
        safe_route_name = (route_name or args.route_name or f"route_{args.route_id}").replace(" ", "").replace("/", "_")
        filename = f"{safe_route_name}航路偏航数据_0.1.json"

    output_path = os.path.join(args.output_dir, filename)

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
    print(f"  偏航开始: 第 {args.deviate_start} 秒，偏移量: {args.deviate_offset} 米")


if __name__ == "__main__":
    main()
