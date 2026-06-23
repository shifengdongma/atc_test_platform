#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析生成的轨迹 JSON，检查跳变、回头等问题"""

import json
import math
import sys

RE_EARTH = 6371000.0


def geo_distance(lat1, lon1, lat2, lon2):
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    return math.sqrt(dn**2 + de**2)


def calc_heading(lat1, lon1, lat2, lon2):
    dn = (lat2 - lat1) * RE_EARTH * math.pi / 180.0
    de = (lon2 - lon1) * RE_EARTH * math.cos(math.radians(lat1)) * math.pi / 180.0
    heading = math.degrees(math.atan2(de, dn))
    if heading < 0:
        heading += 360.0
    return heading


def analyze(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    n = len(data)
    print(f"总点数: {n}")
    print(f"起点: lon={data[0]['longitude']:.6f}, lat={data[0]['latitude']:.6f}, heading={data[0]['trackAngle']}")
    print(f"终点: lon={data[-1]['longitude']:.6f}, lat={data[-1]['latitude']:.6f}, heading={data[-1]['trackAngle']}")

    # 计算每段距离和 heading 变化
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

    # 统计
    print(f"\n距离统计:")
    print(f"  平均: {sum(distances)/len(distances):.2f} 米")
    print(f"  最小: {min(distances):.2f} 米")
    print(f"  最大: {max(distances):.2f} 米")

    print(f"\nHeading 变化统计:")
    print(f"  平均: {sum(heading_changes)/len(heading_changes):.2f}°")
    print(f"  最小: {min(heading_changes):.2f}°")
    print(f"  最大: {max(heading_changes):.2f}°")

    # 查找异常点
    print(f"\n--- 距离跳变 (>50米) ---")
    jump_count = 0
    for i, dist in enumerate(distances):
        if dist > 50:
            jump_count += 1
            if jump_count <= 5:
                lon1, lat1 = data[i]['longitude'], data[i]['latitude']
                lon2, lat2 = data[i + 1]['longitude'], data[i + 1]['latitude']
                print(f"  [{i}] {dist:.2f}米 ({lon1:.6f},{lat1:.6f}) -> ({lon2:.6f},{lat2:.6f})")
    if jump_count > 5:
        print(f"  ... 共 {jump_count} 处跳变")

    print(f"\n--- Heading 突变 (>30°) ---")
    sudden_count = 0
    for i, h_diff in enumerate(heading_changes):
        if h_diff > 30:
            sudden_count += 1
            if sudden_count <= 5:
                h1 = data[i]['trackAngle']
                h2 = data[i + 1]['trackAngle']
                lon1, lat1 = data[i]['longitude'], data[i]['latitude']
                lon2, lat2 = data[i + 1]['longitude'], data[i + 1]['latitude']
                print(f"  [{i}] {h1:.1f}° -> {h2:.1f}° (差值 {h_diff:.1f}°) ({lon1:.6f},{lat1:.6f}) -> ({lon2:.6f},{lat2:.6f})")
    if sudden_count > 5:
        print(f"  ... 共 {sudden_count} 处突变")

    # 查找"回头"：相邻点方向反转（heading 变化接近 180°）
    print(f"\n--- 方向反转 (heading 变化 >150°) ---")
    reverse_count = 0
    for i, h_diff in enumerate(heading_changes):
        if h_diff > 150:
            reverse_count += 1
            if reverse_count <= 5:
                h1 = data[i]['trackAngle']
                h2 = data[i + 1]['trackAngle']
                lon1, lat1 = data[i]['longitude'], data[i]['latitude']
                lon2, lat2 = data[i + 1]['longitude'], data[i + 1]['latitude']
                print(f"  [{i}] {h1:.1f}° -> {h2:.1f}° (差值 {h_diff:.1f}°) ({lon1:.6f},{lat1:.6f}) -> ({lon2:.6f},{lat2:.6f})")
    if reverse_count > 5:
        print(f"  ... 共 {reverse_count} 处反转")
    elif reverse_count == 0:
        print("  无方向反转")

    # 检查经纬度范围
    lons = [d['longitude'] for d in data]
    lats = [d['latitude'] for d in data]
    print(f"\n经纬度范围:")
    print(f"  经度: {min(lons):.6f} ~ {max(lons):.6f} (跨度 {(max(lons)-min(lons)):.6f})")
    print(f"  纬度: {min(lats):.6f} ~ {max(lats):.6f} (跨度 {(max(lats)-min(lats)):.6f})")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        analyze(sys.argv[1])
    else:
        import os
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_path = os.path.join(_root, "mock", "跨顺义三河段航路偏航数据_0.1.json")
        analyze(default_path)
