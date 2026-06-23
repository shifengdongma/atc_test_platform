#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景化飞行数据生成器

功能：
- 根据起始坐标、轨迹类型、速度、无人机ID 生成标准格式的 JSON 飞行数据
- 支持直线、折线、圆形、盘旋、爬升下降、8字形、螺旋等多种轨迹
- 可通过命令行参数、配置文件或交互式输入运行

用法示例：
    # 交互式模式
    python scene_generator.py

    # 命令行模式 - 直线飞行
    python scene_generator.py --type straight_line --uid UAV_001 --start-lon 120.7 --start-lat 31.3 --start-alt 100 --speed 15 --duration 300 --heading 90 --output straight.json

    # 命令行模式 - 圆形飞行
    python scene_generator.py --type circle --uid UAV_002 --start-lon 120.7 --start-lat 31.3 --start-alt 200 --speed 15 --duration 600 --radius 500 --output circle.json

    # 配置文件模式
    python scene_generator.py --config scene_generator_config.yaml
"""

import json
import math
import time
import uuid
import argparse
import os
import sys
import random
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# 将上级目录加入路径，以便导入 core 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config_manager import ConfigManager


# ==================== 常量 ====================
RE_EARTH = 6371000.0  # 地球半径（米）


def meters_to_degrees_lat(meters: float) -> float:
    """米转纬度度数"""
    return math.degrees(meters / RE_EARTH)


def meters_to_degrees_lon(meters: float, lat: float) -> float:
    """米转经度度数（需参考纬度）"""
    return math.degrees(meters / (RE_EARTH * math.cos(math.radians(lat))))


def degrees_lat_to_meters(deg: float) -> float:
    """纬度度数转米"""
    return math.radians(deg) * RE_EARTH


def degrees_lon_to_meters(deg: float, lat: float) -> float:
    """经度度数转米（需参考纬度）"""
    return math.radians(deg) * RE_EARTH * math.cos(math.radians(lat))


def calculate_heading(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> float:
    """
    计算从起点到终点的航向角（度）
    0=正北, 90=正东, 180=正南, 270=正西
    """
    dlat = math.radians(to_lat - from_lat)
    dlon = math.radians(to_lon - from_lon)
    lat1 = math.radians(from_lat)
    lat2 = math.radians(to_lat)

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    heading = math.degrees(math.atan2(y, x))
    return (heading + 360) % 360


# ==================== 轨迹生成器 ====================

@dataclass
class FlightPoint:
    """飞行数据点"""
    longitude: float
    latitude: float
    altitude: float
    speed: float
    track_angle: float
    vertical_speed: float
    timestamp: int


def create_base_record(
    uid: str,
    lon: float,
    lat: float,
    alt: float,
    speed: float,
    track_angle: float,
    vertical_speed: float,
    timestamp_ms: int,
) -> Dict[str, Any]:
    """生成标准格式的单条飞行记录"""
    return {
        "uniqueProductIdentificationCode": uid,
        "realNameRegistrationSign": uid,
        "uasOperationCategory": 1,
        "classification": 1,
        "rpsLocationType": 1,
        "rpsLongitude": 0,
        "rpsLatitude": 0,
        "rpsAltitude": 0,
        "longitude": round(lon, 10),
        "latitude": round(lat, 10),
        "trackAngle": round(track_angle, 2),
        "speed": round(speed, 2),
        "geodeticAltitude": round(alt, 2),
        "verticalSpeed": round(vertical_speed, 2),
        "relativeAltitude": 0.0,
        "pressureAltitude": 0.0,
        "operatingStatus": 2,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1,
        "verticalAccuracy": 0,
        "speedAccuracy": 0,
        "timestamp": timestamp_ms,
        "timestampAccuracy": 0,
    }


def generate_straight_line(
    uid: str,
    start_lon: float,
    start_lat: float,
    start_alt: float,
    speed: float,
    duration_sec: int,
    heading_deg: float,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    生成直线飞行数据

    Args:
        heading_deg: 航向角（0=正北, 90=正东）
    """
    records = []
    num_points = int(duration_sec * 1000 / interval_ms)
    heading_rad = math.radians(heading_deg)

    # 每步移动距离（米）
    step_distance = speed * (interval_ms / 1000.0)

    # 每步经纬度增量
    dlat = meters_to_degrees_lat(step_distance * math.cos(heading_rad))
    dlon = meters_to_degrees_lon(step_distance * math.sin(heading_rad), start_lat)

    base_timestamp = int(time.time() * 1000)

    for i in range(num_points):
        lon = start_lon + dlon * i
        lat = start_lat + dlat * i
        timestamp = base_timestamp + i * interval_ms
        records.append(create_base_record(
            uid, lon, lat, start_alt, speed, heading_deg, 0.0, timestamp
        ))

    return records


def generate_polyline(
    uid: str,
    start_lon: float,
    start_lat: float,
    start_alt: float,
    speed: float,
    waypoints: List[Dict[str, float]],
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    生成折线飞行数据

    Args:
        waypoints: 航点列表，每个航点包含 lon, lat, alt（相对高度变化可选）
    """
    records = []
    base_timestamp = int(time.time() * 1000)
    current_time = 0

    # 添加起始点作为第一个航点
    all_points = [{"lon": start_lon, "lat": start_lat, "alt": start_alt}] + waypoints

    for seg_idx in range(len(all_points) - 1):
        p0 = all_points[seg_idx]
        p1 = all_points[seg_idx + 1]

        # 计算段距离
        dlat_m = degrees_lat_to_meters(p1["lat"] - p0["lat"])
        dlon_m = degrees_lon_to_meters(p1["lon"] - p0["lon"], p0["lat"])
        seg_distance = math.sqrt(dlat_m**2 + dlon_m**2)

        if seg_distance < 0.1:
            continue

        # 段内点数
        seg_duration = seg_distance / speed
        seg_points = max(1, int(seg_duration * 1000 / interval_ms))

        # 航向角
        heading = calculate_heading(p0["lat"], p0["lon"], p1["lat"], p1["lon"])

        # 高度变化
        alt_step = (p1.get("alt", p0["alt"]) - p0["alt"]) / seg_points if seg_points > 0 else 0

        for j in range(seg_points):
            ratio = j / seg_points if seg_points > 0 else 0
            lon = p0["lon"] + (p1["lon"] - p0["lon"]) * ratio
            lat = p0["lat"] + (p1["lat"] - p0["lat"]) * ratio
            alt = p0["alt"] + alt_step * j
            timestamp = base_timestamp + current_time * interval_ms
            vertical_speed = alt_step * 1000 / interval_ms if interval_ms > 0 else 0

            records.append(create_base_record(
                uid, lon, lat, alt, speed, heading, vertical_speed, timestamp
            ))
            current_time += 1

    return records


def generate_circle(
    uid: str,
    center_lon: float,
    center_lat: float,
    center_alt: float,
    speed: float,
    duration_sec: int,
    radius_m: float,
    clockwise: bool = True,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    生成圆形飞行数据

    Args:
        center_lon, center_lat: 圆心经度、纬度
        radius_m: 圆半径（米）
        clockwise: 是否顺时针飞行
    """
    records = []
    num_points = int(duration_sec * 1000 / interval_ms)

    # 圆周长
    circumference = 2 * math.pi * radius_m
    # 每步角度增量
    angular_speed = speed / radius_m  # 弧度/秒
    angle_step = angular_speed * (interval_ms / 1000.0)
    if not clockwise:
        angle_step = -angle_step

    # 将半径转换为度
    radius_lat_deg = meters_to_degrees_lat(radius_m)
    radius_lon_deg = meters_to_degrees_lon(radius_m, center_lat)

    base_timestamp = int(time.time() * 1000)

    for i in range(num_points):
        angle = angle_step * i
        # 圆心偏移：cos对应北向，sin对应东向
        lat = center_lat + radius_lat_deg * math.cos(angle)
        lon = center_lon + radius_lon_deg * math.sin(angle)

        # 航向角 = 切线方向（角度 + 90度）
        track_angle = (math.degrees(angle) + 90) % 360
        if not clockwise:
            track_angle = (track_angle + 180) % 360

        timestamp = base_timestamp + i * interval_ms
        records.append(create_base_record(
            uid, lon, lat, center_alt, speed, track_angle, 0.0, timestamp
        ))

    return records


def generate_hover(
    uid: str,
    lon: float,
    lat: float,
    alt: float,
    duration_sec: int,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    生成定点盘旋（悬停）飞行数据
    """
    records = []
    num_points = int(duration_sec * 1000 / interval_ms)
    base_timestamp = int(time.time() * 1000)

    for i in range(num_points):
        timestamp = base_timestamp + i * interval_ms
        # 添加微小扰动模拟GPS抖动
        jitter_lat = meters_to_degrees_lat(random.uniform(-0.5, 0.5))
        jitter_lon = meters_to_degrees_lon(random.uniform(-0.5, 0.5), lat)
        records.append(create_base_record(
            uid, lon + jitter_lon, lat + jitter_lat, alt, 0.0, 0.0, 0.0, timestamp
        ))

    return records


def generate_ascent_descent(
    uid: str,
    start_lon: float,
    start_lat: float,
    start_alt: float,
    speed: float,
    duration_sec: int,
    target_alt: float,
    heading_deg: float = 0,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    生成爬升后下降飞行数据
    - 前半段：爬升到目标高度
    - 后半段：下降回起始高度
    """
    records = []
    num_points = int(duration_sec * 1000 / interval_ms)
    half_points = num_points // 2

    heading_rad = math.radians(heading_deg)
    step_distance = speed * (interval_ms / 1000.0)
    dlat = meters_to_degrees_lat(step_distance * math.cos(heading_rad))
    dlon = meters_to_degrees_lon(step_distance * math.sin(heading_rad), start_lat)

    base_timestamp = int(time.time() * 1000)

    for i in range(num_points):
        lon = start_lon + dlon * i
        lat = start_lat + dlat * i

        if i < half_points:
            # 爬升阶段
            ratio = i / half_points if half_points > 0 else 0
            alt = start_alt + (target_alt - start_alt) * ratio
            vertical_speed = (target_alt - start_alt) / (half_points * interval_ms / 1000.0)
        else:
            # 下降阶段
            ratio = (i - half_points) / (num_points - half_points) if (num_points - half_points) > 0 else 0
            alt = target_alt - (target_alt - start_alt) * ratio
            vertical_speed = -(target_alt - start_alt) / ((num_points - half_points) * interval_ms / 1000.0)

        timestamp = base_timestamp + i * interval_ms
        records.append(create_base_record(
            uid, lon, lat, alt, speed, heading_deg, round(vertical_speed, 2), timestamp
        ))

    return records


def generate_figure8(
    uid: str,
    center_lon: float,
    center_lat: float,
    center_alt: float,
    speed: float,
    duration_sec: int,
    radius_m: float,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    生成8字形飞行数据（利萨茹曲线）
    """
    records = []
    num_points = int(duration_sec * 1000 / interval_ms)

    # 8字周期 = 走完两个圆的时间
    circumference = 2 * math.pi * radius_m * 2
    angular_speed = speed / radius_m

    radius_lat_deg = meters_to_degrees_lat(radius_m)
    radius_lon_deg = meters_to_degrees_lon(radius_m, center_lat)

    base_timestamp = int(time.time() * 1000)

    for i in range(num_points):
        t = i * (interval_ms / 1000.0)
        angle = angular_speed * t

        # 8字参数方程
        lat = center_lat + radius_lat_deg * math.sin(angle)
        lon = center_lon + radius_lon_deg * math.sin(angle) * math.cos(angle)

        # 计算航向角（通过前后点差分）
        if i > 0:
            prev = records[i - 1]
            heading = calculate_heading(prev["latitude"], prev["longitude"], lat, lon)
        else:
            # 估算初始航向
            lat_next = center_lat + radius_lat_deg * math.sin(angle + 0.01)
            lon_next = center_lon + radius_lon_deg * math.sin(angle + 0.01) * math.cos(angle + 0.01)
            heading = calculate_heading(lat, lon, lat_next, lon_next)

        timestamp = base_timestamp + i * interval_ms
        records.append(create_base_record(
            uid, lon, lat, center_alt, speed, round(heading, 2), 0.0, timestamp
        ))

    return records


def generate_spiral(
    uid: str,
    center_lon: float,
    center_lat: float,
    start_alt: float,
    speed: float,
    duration_sec: int,
    start_radius_m: float,
    end_radius_m: float,
    turns: float = 3.0,
    climb: bool = True,
    interval_ms: int = 1000,
) -> List[Dict[str, Any]]:
    """
    生成螺旋飞行数据

    Args:
        start_radius_m: 起始半径（米）
        end_radius_m: 结束半径（米）
        turns: 旋转圈数
        climb: True=爬升, False=下降
    """
    records = []
    num_points = int(duration_sec * 1000 / interval_ms)

    total_angle = turns * 2 * math.pi
    angular_speed = total_angle / duration_sec

    base_timestamp = int(time.time() * 1000)

    # 目标高度（每圈变化）
    target_alt = start_alt + (200.0 if climb else -200.0)

    for i in range(num_points):
        t = i * (interval_ms / 1000.0)
        angle = angular_speed * t

        # 半径线性变化
        radius_ratio = i / num_points if num_points > 0 else 0
        radius = start_radius_m + (end_radius_m - start_radius_m) * radius_ratio

        radius_lat = meters_to_degrees_lat(radius)
        radius_lon = meters_to_degrees_lon(radius, center_lat)

        lat = center_lat + radius_lat * math.cos(angle)
        lon = center_lon + radius_lon * math.sin(angle)

        alt = start_alt + (target_alt - start_alt) * radius_ratio
        vertical_speed = (target_alt - start_alt) / duration_sec

        # 航向角
        if i > 0:
            prev = records[i - 1]
            heading = calculate_heading(prev["latitude"], prev["longitude"], lat, lon)
        else:
            lat_next = center_lat + radius_lat * math.cos(angle + 0.01)
            lon_next = center_lon + radius_lon * math.sin(angle + 0.01)
            heading = calculate_heading(lat, lon, lat_next, lon_next)

        timestamp = base_timestamp + i * interval_ms
        records.append(create_base_record(
            uid, lon, lat, alt, speed, round(heading, 2), round(vertical_speed, 2), timestamp
        ))

    return records


# ==================== 批量生成场景 ====================

def generate_scene_batch(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """根据配置批量生成多个无人机的场景数据"""
    all_records = []

    scenes = config.get('scenes', [])
    for scene in scenes:
        scene_type = scene.get('type', 'straight_line')
        uid = scene.get('uid', f"UAV_{uuid.uuid4().hex[:8].upper()}")

        if scene_type == 'straight_line':
            records = generate_straight_line(
                uid=uid,
                start_lon=scene.get('start_lon', 120.7),
                start_lat=scene.get('start_lat', 31.3),
                start_alt=scene.get('start_alt', 100),
                speed=scene.get('speed', 15),
                duration_sec=scene.get('duration', 300),
                heading_deg=scene.get('heading', 90),
                interval_ms=scene.get('interval_ms', 1000),
            )
        elif scene_type == 'polyline':
            records = generate_polyline(
                uid=uid,
                start_lon=scene.get('start_lon', 120.7),
                start_lat=scene.get('start_lat', 31.3),
                start_alt=scene.get('start_alt', 100),
                speed=scene.get('speed', 15),
                waypoints=scene.get('waypoints', []),
                interval_ms=scene.get('interval_ms', 1000),
            )
        elif scene_type == 'circle':
            records = generate_circle(
                uid=uid,
                center_lon=scene.get('center_lon', 120.7),
                center_lat=scene.get('center_lat', 31.3),
                center_alt=scene.get('center_alt', 200),
                speed=scene.get('speed', 15),
                duration_sec=scene.get('duration', 600),
                radius_m=scene.get('radius', 500),
                clockwise=scene.get('clockwise', True),
                interval_ms=scene.get('interval_ms', 1000),
            )
        elif scene_type == 'hover':
            records = generate_hover(
                uid=uid,
                lon=scene.get('lon', 120.7),
                lat=scene.get('lat', 31.3),
                alt=scene.get('alt', 100),
                duration_sec=scene.get('duration', 300),
                interval_ms=scene.get('interval_ms', 1000),
            )
        elif scene_type == 'ascent_descent':
            records = generate_ascent_descent(
                uid=uid,
                start_lon=scene.get('start_lon', 120.7),
                start_lat=scene.get('start_lat', 31.3),
                start_alt=scene.get('start_alt', 50),
                speed=scene.get('speed', 15),
                duration_sec=scene.get('duration', 600),
                target_alt=scene.get('target_alt', 500),
                heading_deg=scene.get('heading', 90),
                interval_ms=scene.get('interval_ms', 1000),
            )
        elif scene_type == 'figure8':
            records = generate_figure8(
                uid=uid,
                center_lon=scene.get('center_lon', 120.7),
                center_lat=scene.get('center_lat', 31.3),
                center_alt=scene.get('center_alt', 200),
                speed=scene.get('speed', 15),
                duration_sec=scene.get('duration', 600),
                radius_m=scene.get('radius', 500),
                interval_ms=scene.get('interval_ms', 1000),
            )
        elif scene_type == 'spiral':
            records = generate_spiral(
                uid=uid,
                center_lon=scene.get('center_lon', 120.7),
                center_lat=scene.get('center_lat', 31.3),
                start_alt=scene.get('start_alt', 100),
                speed=scene.get('speed', 15),
                duration_sec=scene.get('duration', 600),
                start_radius_m=scene.get('start_radius', 100),
                end_radius_m=scene.get('end_radius', 1000),
                turns=scene.get('turns', 3.0),
                climb=scene.get('climb', True),
                interval_ms=scene.get('interval_ms', 1000),
            )
        else:
            print(f"未知场景类型: {scene_type}")
            continue

        all_records.extend(records)
        print(f"生成场景: {scene_type}, UAV: {uid}, 点数: {len(records)}")

    return all_records


# ==================== 交互式模式 ====================

def interactive_mode():
    """交互式输入模式"""
    print("=" * 60)
    print("场景化飞行数据生成器 - 交互式模式")
    print("=" * 60)

    print("\n支持的轨迹类型:")
    print("  1. straight_line  - 直线飞行")
    print("  2. polyline       - 折线飞行")
    print("  3. circle         - 圆形飞行")
    print("  4. hover          - 定点盘旋")
    print("  5. ascent_descent - 爬升后下降")
    print("  6. figure8        - 8字形飞行")
    print("  7. spiral         - 螺旋飞行")

    track_type = input("\n请选择轨迹类型 (输入编号或名称): ").strip().lower()
    type_map = {
        '1': 'straight_line', '2': 'polyline', '3': 'circle',
        '4': 'hover', '5': 'ascent_descent', '6': 'figure8', '7': 'spiral'
    }
    track_type = type_map.get(track_type, track_type)

    uid = input("无人机ID (回车自动生成): ").strip()
    if not uid:
        uid = f"UAV_{uuid.uuid4().hex[:8].upper()}"

    def get_float(prompt, default):
        val = input(f"{prompt} (默认 {default}): ").strip()
        return float(val) if val else default

    def get_int(prompt, default):
        val = input(f"{prompt} (默认 {default}): ").strip()
        return int(val) if val else default

    start_lon = get_float("起始经度", 120.7)
    start_lat = get_float("起始纬度", 31.3)
    start_alt = get_float("起始高度(米)", 100)
    speed = get_float("飞行速度(m/s)", 15)
    duration = get_int("飞行时长(秒)", 300)
    interval_ms = get_int("数据间隔(毫秒)", 1000)

    if track_type == 'straight_line':
        heading = get_float("航向角(0=北, 90=东)", 90)
        records = generate_straight_line(uid, start_lon, start_lat, start_alt, speed, duration, heading, interval_ms)

    elif track_type == 'polyline':
        print("\n请输入航点（格式: 经度,纬度,高度），空行结束:")
        waypoints = []
        while True:
            line = input("航点: ").strip()
            if not line:
                break
            parts = line.split(',')
            if len(parts) >= 2:
                waypoints.append({
                    "lon": float(parts[0]),
                    "lat": float(parts[1]),
                    "alt": float(parts[2]) if len(parts) > 2 else start_alt
                })
        records = generate_polyline(uid, start_lon, start_lat, start_alt, speed, waypoints, interval_ms)

    elif track_type == 'circle':
        radius = get_float("圆半径(米)", 500)
        clockwise = input("是否顺时针 (y/n, 默认y): ").strip().lower() != 'n'
        records = generate_circle(uid, start_lon, start_lat, start_alt, speed, duration, radius, clockwise, interval_ms)

    elif track_type == 'hover':
        records = generate_hover(uid, start_lon, start_lat, start_alt, duration, interval_ms)

    elif track_type == 'ascent_descent':
        target_alt = get_float("目标高度(米)", 500)
        heading = get_float("航向角", 90)
        records = generate_ascent_descent(uid, start_lon, start_lat, start_alt, speed, duration, target_alt, heading, interval_ms)

    elif track_type == 'figure8':
        radius = get_float("8字半径(米)", 500)
        records = generate_figure8(uid, start_lon, start_lat, start_alt, speed, duration, radius, interval_ms)

    elif track_type == 'spiral':
        start_radius = get_float("起始半径(米)", 100)
        end_radius = get_float("结束半径(米)", 1000)
        turns = get_float("旋转圈数", 3.0)
        climb = input("是否爬升 (y/n, 默认y): ").strip().lower() != 'n'
        records = generate_spiral(uid, start_lon, start_lat, start_alt, speed, duration, start_radius, end_radius, turns, climb, interval_ms)

    else:
        print(f"不支持的轨迹类型: {track_type}")
        return

    output = input(f"\n输出文件名 (默认 {track_type}_{uid}.json): ").strip()
    if not output:
        output = f"{track_type}_{uid}.json"

    save_records(records, output)


def save_records(records: List[Dict[str, Any]], output_path: str):
    """保存记录到 JSON 文件"""
    # 确保输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) if os.path.dirname(output_path) else '.', exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"\n已生成 {len(records)} 条飞行数据")
    print(f"保存到: {os.path.abspath(output_path)}")

    # 打印数据摘要
    if records:
        first = records[0]
        last = records[-1]
        print(f"\n数据摘要:")
        print(f"  UAV ID: {first['uniqueProductIdentificationCode']}")
        print(f"  起始坐标: ({first['longitude']}, {first['latitude']}, {first['geodeticAltitude']}m)")
        print(f"  结束坐标: ({last['longitude']}, {last['latitude']}, {last['geodeticAltitude']}m)")
        print(f"  时间跨度: {(last['timestamp'] - first['timestamp']) / 1000:.1f} 秒")
        print(f"  平均速度: {sum(r['speed'] for r in records) / len(records):.2f} m/s")


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(description='场景化飞行数据生成器')
    parser.add_argument('--config', '-c', type=str, help='配置文件路径（YAML格式，批量生成）')
    parser.add_argument('--interactive', '-i', action='store_true', help='交互式模式')

    # 单个场景参数
    parser.add_argument('--type', '-t', type=str, choices=['straight_line', 'polyline', 'circle', 'hover', 'ascent_descent', 'figure8', 'spiral'], help='轨迹类型')
    parser.add_argument('--uid', '-u', type=str, help='无人机唯一标识')
    parser.add_argument('--start-lon', type=float, default=120.7, help='起始经度')
    parser.add_argument('--start-lat', type=float, default=31.3, help='起始纬度')
    parser.add_argument('--start-alt', type=float, default=100, help='起始高度（米）')
    parser.add_argument('--speed', '-s', type=float, default=15, help='飞行速度（m/s）')
    parser.add_argument('--duration', '-d', type=int, default=300, help='飞行时长（秒）')
    parser.add_argument('--interval', type=int, default=1000, help='数据点间隔（毫秒）')
    parser.add_argument('--output', '-o', type=str, help='输出文件路径')

    # 特定类型参数
    parser.add_argument('--heading', type=float, default=90, help='航向角（0=北, 90=东）')
    parser.add_argument('--radius', '-r', type=float, help='圆半径/8字半径（米）')
    parser.add_argument('--center-lon', type=float, help='圆心经度')
    parser.add_argument('--center-lat', type=float, help='圆心纬度')
    parser.add_argument('--center-alt', type=float, help='圆心高度')
    parser.add_argument('--target-alt', type=float, help='目标高度（米）')
    parser.add_argument('--clockwise', action='store_true', default=True, help='顺时针')
    parser.add_argument('--counter-clockwise', dest='clockwise', action='store_false', help='逆时针')
    parser.add_argument('--start-radius', type=float, default=100, help='螺旋起始半径')
    parser.add_argument('--end-radius', type=float, default=1000, help='螺旋结束半径')
    parser.add_argument('--turns', type=float, default=3.0, help='螺旋圈数')
    parser.add_argument('--climb', action='store_true', default=True, help='爬升')
    parser.add_argument('--descend', dest='climb', action='store_false', help='下降')

    args = parser.parse_args()

    # 交互式模式
    if args.interactive or (not args.config and not args.type):
        interactive_mode()
        return

    # 配置文件模式
    if args.config:
        if not os.path.exists(args.config):
            print(f"配置文件不存在: {args.config}")
            return
        config_manager = ConfigManager(args.config)
        config = config_manager.get_full_config()
        records = generate_scene_batch(config)
        output = config.get('output', 'scene_batch.json')
        save_records(records, output)
        return

    # 命令行单场景模式
    uid = args.uid or f"UAV_{uuid.uuid4().hex[:8].upper()}"
    center_lon = args.center_lon if args.center_lon is not None else args.start_lon
    center_lat = args.center_lat if args.center_lat is not None else args.start_lat
    center_alt = args.center_alt if args.center_alt is not None else args.start_alt

    if args.type == 'straight_line':
        records = generate_straight_line(uid, args.start_lon, args.start_lat, args.start_alt,
                                         args.speed, args.duration, args.heading, args.interval)
    elif args.type == 'circle':
        radius = args.radius or 500
        records = generate_circle(uid, center_lon, center_lat, center_alt,
                                  args.speed, args.duration, radius, args.clockwise, args.interval)
    elif args.type == 'hover':
        records = generate_hover(uid, args.start_lon, args.start_lat, args.start_alt,
                                 args.duration, args.interval)
    elif args.type == 'ascent_descent':
        target_alt = args.target_alt or 500
        records = generate_ascent_descent(uid, args.start_lon, args.start_lat, args.start_alt,
                                          args.speed, args.duration, target_alt, args.heading, args.interval)
    elif args.type == 'figure8':
        radius = args.radius or 500
        records = generate_figure8(uid, center_lon, center_lat, center_alt,
                                   args.speed, args.duration, radius, args.interval)
    elif args.type == 'spiral':
        records = generate_spiral(uid, center_lon, center_lat, args.start_alt,
                                  args.speed, args.duration, args.start_radius, args.end_radius,
                                  args.turns, args.climb, args.interval)
    else:
        print(f"暂不支持通过命令行直接生成该类型，请使用交互式模式: --interactive")
        return

    output = args.output or f"{args.type}_{uid}.json"
    save_records(records, output)


if __name__ == '__main__':
    main()
