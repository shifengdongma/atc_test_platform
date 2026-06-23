#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 N 架无人机平行飞行数据集

特性：
- 使用 uav_identifiers_extended.py 扩展ID（支持最多5000架）
- 六边形蜂窝网格水平分布，相邻间距可配置
- 所有无人机沿同一航向、同一速度平行飞行
- 支持命令行参数化：中心坐标、高度、间距、数量、航向、速度等
- 输出标准 Kafka 遥测 JSON 格式

用法示例：
  python 3000架平行飞行无人机.py --count 3000 --spacing 300 --altitude 100 --heading 90
  python 3000架平行飞行无人机.py --center-lng 120.5 --center-lat 31.2 --count 1000 --speed 20
"""

import json
import math
import os
import sys
import random
import argparse
from datetime import datetime

# ========== 路径配置 ==========
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED

# ========== 默认配置 ==========
DEFAULT_CENTER_LNG = 85.070136          # 分布中心经度（度）
DEFAULT_CENTER_LAT = 40.818724         # 分布中心纬度（度）
DEFAULT_ALTITUDE = 50.0              # 默认飞行高度（米）
DEFAULT_SPEED = 15.0                  # 默认飞行速度（米/秒）
DEFAULT_HEADING = 90.0                # 默认航向角（度）：0=正北, 90=正东, 180=正南, 270=正西
DEFAULT_COUNT = 30                  # 默认生成无人机数量
DEFAULT_SPACING = 2000                 # 相邻无人机横向间距（米），用于 line 布局
DEFAULT_SPACING_ALONG = 2000             # 相邻无人机前后间距（米），用于 line 布局
DEFAULT_INTERVAL_MS = 1000            # 轨迹采样间隔（毫秒）
DEFAULT_POINTS_PER_UAV = 1200          # 每架无人机生成的轨迹点数量（600点 × 1秒 = 约10分钟）
DEFAULT_SIM_RADIUS = 100000.0         # 仿真有效半径（米），与 simulation_core.py SIM_RADIUS_M 默认值一致
DEFAULT_CLASSIFICATION = 3            # 航空器分类（模拟器类型）：0=微型 1=轻型 2=小型 3=中型 4=大型
DEFAULT_OUTPUT = "mock/kafka_data_parallel.json"

# IDE 直接运行配置：设为 True 时，无需命令行参数直接生成多降维度数据
IDE_QUICK_RUN = True

# IDE 模式下是否强制覆盖已存在的文件（设为 True 时，即使文件存在也会重新生成）
IDE_FORCE_OVERWRITE = False

# IDE 模式下生成的数据集配置（可自由增减）
# 支持自定义坐标、数量、输出路径、是否分区域
# 未显式指定的参数（如 altitude、speed、spacing、sim_radius 等）均使用上方 DEFAULT_* 默认值
# multi=True  表示将该 count 分成 3 组生成（输出 _1.json / _2.json / _3.json），用于多线程发射
# multi=False 表示单文件输出，坐标中心即为所有无人机的分布中心
IDE_DATASETS = [
    {"count": 100, "center_lng": 116.411207, "center_lat": 39.897838,
     "output": "mock/kafka_data_scene_bj.json", "multi": False, "label": "北京扇区", "altitude": 50,
     "enable_altitude_groups": True,
     "altitude_groups": [
         {"count": 30, "altitude": 30},  # 前10架无人机飞行高度为 30米
         {"count": 70, "altitude": 50}   # 后90架无人机飞行高度为 50米
     ]},
    {"count": 100, "center_lng": 87.407734, "center_lat": 43.450822,
     "output": "mock/kafka_data_scene1.json", "multi": False, "label": "新疆空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 10, "altitude": 30},  # 前30架无人机飞行高度为 30米
         {"count": 90, "altitude": 50}   # 后70架无人机飞行高度为 30米
     ]},
    {"count": 300, "center_lng": 82.382178, "center_lat": 40.171273,
     "output": "mock/kafka_data_scene2.json", "multi": False, "label": "新疆空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 85.507436, "center_lat": 32.604875,
     "output": "mock/kafka_data_scene3.json", "multi": False, "label": "西藏空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 91.725056, "center_lat": 38.264847,
     "output": "mock/kafka_data_scene4.json", "multi": False, "label": "青海空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 91.769785, "center_lat": 35.956547,
     "output": "mock/kafka_data_scene5.json", "multi": False, "label": "青海空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 96.105003, "center_lat": 35.859452,
     "output": "mock/kafka_data_scene6.json", "multi": False, "label": "青海空域3-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 99.344645, "center_lat": 35.914791,
     "output": "mock/kafka_data_scene7.json", "multi": False, "label": "青海空域4-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 96.119904, "center_lat": 40.486873,
     "output": "mock/kafka_data_scene8.json", "multi": False, "label": "甘肃空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 102.361720, "center_lat": 38.180031,
     "output": "mock/kafka_data_scene9.json", "multi": False, "label": "甘肃空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 101.537149, "center_lat": 41.134612,
     "output": "mock/kafka_data_scene10.json", "multi": False, "label": "内蒙空域1-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
    {"count": 300, "center_lng": 105.377261, "center_lat": 40.571124,
     "output": "mock/kafka_data_scene11.json", "multi": False, "label": "内蒙空域2-平行飞行", "altitude": 50,
     "enable_altitude_groups": False,
     "altitude_groups": [
         {"count": 30, "altitude": 30},
         {"count": 270, "altitude": 50}
     ]},
]
# 新疆1 87.407734,43.450822   半径200000米
# 新疆2 82.382178,40.171273   半径200000米
# 西藏  85.507436,32.604875   半径300000米
# 青海1  91.725056,38.264847   半径50000米
# 青海2  91.769785,35.956547   半径50000米
# 青海3  96.105003,35.859452   半径140000米
# 青海4  99.344645,35.914791   半径110000米
# 甘肃1  96.119904,40.486873   半径100000米
# 甘肃2  102.361720,38.180031   半径60000米
# 内蒙1  101.537149,41.134612  半径90000米
# 内蒙2  105.377261,40.571124  半径100000米

def generate_hex_grid_offsets(n, spacing_meters, center_lat):
    """
    生成 n 个六边形蜂窝网格的经纬度偏移量。
    从中心向外逐环扩展，相邻无人机实际地理距离严格等于 spacing_meters。
    """
    if n <= 0:
        return []

    meters_per_degree_lat = 111320.0
    meters_per_degree_lng = 111320.0 * math.cos(math.radians(center_lat))
    spacing_deg_lng = spacing_meters / meters_per_degree_lng
    spacing_deg_lat = spacing_meters / meters_per_degree_lat

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


def generate_line_offsets(n, spacing_meters, center_lat, heading, spacing_along=0):
    """
    生成 n 个直线排列的经纬度偏移量。
    无人机排成一条线，与航向方向垂直展开。
    - spacing_meters: 横向间隔（垂直于航向方向）
    - spacing_along: 前后间隔（沿航向方向），默认为0表示齐头并进
    """
    if n <= 0:
        return []

    meters_per_degree_lat = 111320.0
    meters_per_degree_lng = 111320.0 * math.cos(math.radians(center_lat))

    # 航向方向：0=北(正向Y)，90=东(正向X)
    heading_rad = math.radians(heading)
    # 垂直于航向的方向（左侧）
    perp_heading_rad = heading_rad + math.pi / 2

    offsets = []
    # 计算每侧需要多少架无人机，使中心点在中间
    # 如果是奇数，中心点正好在中间；如果是偶数，中心点左右对称分布
    half_n = (n - 1) / 2 if n % 2 == 1 else n / 2

    for i in range(n):
        if n % 2 == 1:
            # 奇数：中心点在 i=0
            lateral_idx = i - half_n  # -half_n 到 +half_n
        else:
            # 偶数：中心点在 i=0 和 i=1 之间
            lateral_idx = i - half_n + 0.5  # -half_n+0.5 到 +half_n-0.5

        # 侧向偏移（垂直于航向）
        lateral_offset = lateral_idx * spacing_meters

        # 前后偏移（沿航向方向）
        # 从第一架开始，依次向后排列
        forward_offset = i * spacing_along

        # 转换为经纬度偏移
        # 侧向贡献
        lng_offset = lateral_offset * math.sin(perp_heading_rad) / meters_per_degree_lng
        lat_offset = lateral_offset * math.cos(perp_heading_rad) / meters_per_degree_lat
        # 前后贡献（沿航向方向）
        lng_offset += forward_offset * math.sin(heading_rad) / meters_per_degree_lng
        lat_offset += forward_offset * math.cos(heading_rad) / meters_per_degree_lat

        offsets.append((lng_offset, lat_offset))

    return offsets


def make_telemetry_point(uid, reg_sign, ts, lon, lat, alt, speed, heading, classification):
    """生成单条遥测数据（格式兼容 create_data_scene.py）"""
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
        "operatingStatus": 2,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1,
        "verticalAccuracy": 0,
        "speedAccuracy": 0,
        "timestamp": ts,
        "timestampAccuracy": 0,
    }


def generate_parallel_dataset(args, uid_offset=0, s_by_mod=None):
    """根据参数生成平行飞行数据集

    ID 碰撞避让策略：
        后端使用 Math.abs(identifyCode.hashCode()) + timestamp 生成内部 ID。
        按 hash % 1000 分组，组内 S = hash + offset 严格间隔 MIN_GAP，全局跨 scene
        共享 s_by_mod，确保任意两架 UAV 的任意轨迹点都不会产生相同 ID。

        注意：由于 Java hashCode 范围约为 ±21 亿，offset 范围不可避免地会覆盖
        较大区间（最大约数十天），这是在不修改后端 ID 生成策略的前提下，
        实现确定性零碰撞的必要代价。

    Args:
        s_by_mod: 跨 scene/跨批次共享的 ID 分配状态。
                  dict[mod_1000 -> list[S_value]]。
    """
    # 根据布局类型选择生成方式
    if args.layout == "line":
        offsets = generate_line_offsets(args.count, args.spacing, args.center_lat, args.heading, args.spacing_along)
    else:
        offsets = generate_hex_grid_offsets(args.count, args.spacing, args.center_lat)
    all_data = []
    # base_time 取 1000 的倍数，确保所有 timestamp 都是 1000 的整数倍，
    # 从而将碰撞条件限制为 "hash 差必须是 1000 的倍数"，大幅降低碰撞概率
    raw_base_time = args.start_time if args.start_time else int(datetime.now().timestamp() * 1000)
    base_time = (raw_base_time // 1000) * 1000

    # 计算每步的经纬度增量
    step_meters = args.speed * (args.interval / 1000.0)
    heading_rad = math.radians(args.heading)
    dn = step_meters * math.cos(heading_rad)
    de = step_meters * math.sin(heading_rad)

    meters_per_degree_lat = 111320.0
    meters_per_degree_lng = 111320.0 * math.cos(math.radians(args.center_lat))
    d_lat = dn / meters_per_degree_lat
    d_lng = de / meters_per_degree_lng

    # 估算分布范围
    if args.layout == "line":
        # 直线排列：横向跨度 + 纵向跨度（取较大者作为分布半径）
        lateral_span = (args.count - 1) * args.spacing if args.spacing > 0 else 0
        along_span = (args.count - 1) * args.spacing_along if args.spacing_along > 0 else 0
        estimated_radius = max(lateral_span, along_span)
    else:
        # 六边形网格最外层半径 ≈ ring * spacing
        ring = 1
        while 1 + 3 * ring * (ring + 1) < args.count:
            ring += 1
        estimated_radius = ring * args.spacing
    print(f"开始生成 {args.count} 架平行飞行数据...")
    print(f"  布局: {args.layout} ({'直线排列' if args.layout == 'line' else '六边形蜂窝网格'})")
    print(f"  中心: ({args.center_lng}, {args.center_lat})")
    print(f"  航向: {args.heading}°, 速度: {args.speed}m/s, 高度: {args.altitude}m")
    # 构建每架无人机的高度列表
    altitudes = []
    enable_groups = getattr(args, 'enable_altitude_groups', False)
    if enable_groups and hasattr(args, 'altitude_groups') and args.altitude_groups:
        for group in args.altitude_groups:
            group_count = group.get("count", 0)
            group_alt = group.get("altitude", args.altitude)
            altitudes.extend([group_alt] * group_count)
        print(f"  高度分组已启用: {args.altitude_groups}")
    if not altitudes:
        altitudes = [args.altitude] * args.count
    # 确保高度列表长度与无人机数量一致（超出截断，不足补齐）
    altitudes = altitudes[:args.count]
    while len(altitudes) < args.count:
        altitudes.append(args.altitude)

    if args.layout == "line":
        print(f"  横向间距: {args.spacing}m, 前后间距: {args.spacing_along}m")
    else:
        print(f"  间距: {args.spacing}m")
    print(f"  每架点数: {args.points}")
    print(f"  分类: {args.classification}, 仿真半径: {args.sim_radius}m")
    print(f"  ID偏移: {uid_offset}")
    if estimated_radius > args.sim_radius:
        print(f"  [警告] 警告: 预估分布半径 {estimated_radius:.0f}m 超过仿真有效半径 {args.sim_radius:.0f}m")
    else:
        print(f"  预估分布半径: {estimated_radius:.0f}m（在仿真半径内）")

    # ---------- ID 碰撞预检测与避让 ----------
    # 后端使用 Math.abs(identifyCode.hashCode()) + timestamp 生成内部 ID。
    # 碰撞条件: hash_i + ts_i = hash_j + ts_j
    #   => hash_i + base_time + offset_i + p_i*interval = hash_j + base_time + offset_j + p_j*interval
    #   => (hash_i + offset_i) - (hash_j + offset_j) = (p_j - p_i) * interval
    #
    # 若 hash_i % 1000 != hash_j % 1000：
    #   左边不是 1000 的倍数，右边一定是 1000 的倍数（interval=1000），
    #   等式不可能成立 → 不会碰撞。
    #
    # 若 hash_i % 1000 == hash_j % 1000：
    #   两边都是 1000 的倍数，可能碰撞。
    #   但只要保证同组内 S = hash + offset 的间隔大于任意两轨迹点的最大时间差，
    #   即 |S_i - S_j| > (points-1)*interval，则 (p_j-p_i)*interval 永远追不上 S 差，
    #   等式仍不可能成立。
    #
    # 策略：按 hash % 1000 分组，组内 S 严格递增间隔 MIN_GAP，全局跨 scene 共享。
    # 全局共享是确定性零碰撞的必要条件；若各 scene 独立管理，跨 scene UAV 之间
    # 的 hash+timestamp 精确抵消将导致大量碰撞。
    MIN_GAP = args.points * args.interval + args.interval  # 大于任意两轨迹点时间差的最大值

    def _compute_uav_hash(uid: str) -> int:
        """模拟 Java String.hashCode() + Math.abs()"""
        h = 0
        for ch in uid:
            h = (31 * h + ord(ch)) & 0xFFFFFFFF
        if h > 0x7FFFFFFF:
            h -= 0x100000000
        if h == -0x80000000:
            return -0x80000000
        return abs(h)

    if s_by_mod is None:
        s_by_mod = {}

    start_offsets = []
    max_offset_used = 0

    for idx in range(args.count):
        uid, _ = UAV_IDENTIFIERS_EXTENDED[idx + uid_offset]
        uhash = _compute_uav_hash(uid)
        mod = uhash % 1000

        if mod not in s_by_mod:
            s_by_mod[mod] = []

        if not s_by_mod[mod]:
            # 该 mod 组的第一个 UAV，S 直接取 hash 值本身，offset = 0
            s = uhash
        else:
            # 在该 mod 组最后一个 S 的基础上增加 MIN_GAP，确保组内间隔足够大
            s = s_by_mod[mod][-1] + MIN_GAP

        s_by_mod[mod].append(s)
        offset = s - uhash
        start_offsets.append(offset)
        max_offset_used = max(max_offset_used, offset)

    if max_offset_used > 0:
        print(f"  [信息] 最大起始时间偏移: {max_offset_used}ms ({max_offset_used/1000:.1f}秒)")
    print(f"  [成功] 碰撞预检测通过: {args.count} 架无人机无 ID 碰撞风险")
    # ----------------------------------------

    for i in range(args.count):
        uid, reg_sign = UAV_IDENTIFIERS_EXTENDED[i + uid_offset]
        offset_x, offset_y = offsets[i]

        start_lng = args.center_lng + offset_x
        start_lat = args.center_lat + offset_y

        for p in range(args.points):
            # timestamp = base_time + offset + p*interval
            # offset 已确保全局无碰撞，interval 固定为 1000ms
            ts = base_time + start_offsets[i] + p * args.interval
            lon = start_lng + p * d_lng
            lat = start_lat + p * d_lat
            point = make_telemetry_point(
                uid, reg_sign, ts, lon, lat, altitudes[i], args.speed, args.heading, args.classification
            )
            all_data.append(point)

        if (i + 1) % 500 == 0:
            print(f"  已生成 {i + 1} 架...")

    all_data.sort(key=lambda x: x["timestamp"])

    output_path = os.path.join(_ROOT, args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    # 统计
    uav_ids = set(p["uniqueProductIdentificationCode"] for p in all_data)
    lngs = [p["longitude"] for p in all_data]
    lats = [p["latitude"] for p in all_data]

    print(f"\n[成功] 生成完成: {output_path}")
    print(f"  无人机数量: {len(uav_ids)}")
    print(f"  总轨迹点数: {len(all_data)}")
    print(f"  预计文件大小: {len(all_data) * 350 / 1024 / 1024:.1f} MB")
    print(f"  经度范围: {min(lngs):.6f} ~ {max(lngs):.6f}")
    print(f"  纬度范围: {min(lats):.6f} ~ {max(lats):.6f}")


def main():
    parser = argparse.ArgumentParser(
        description="生成 N 架无人机平行飞行数据集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  python 3000架平行飞行无人机.py
  python 3000架平行飞行无人机.py --count 1000 --spacing 500 --altitude 150
  python 3000架平行飞行无人机.py --center-lng 120.5 --center-lat 31.2 --speed 20 --heading 0
  python 3000架平行飞行无人机.py --layout line --count 30 --spacing 100 --heading 90  # 直线排列
        """,
    )

    # 中心坐标
    parser.add_argument("--center-lng", type=float, default=DEFAULT_CENTER_LNG, help="中心点经度")
    parser.add_argument("--center-lat", type=float, default=DEFAULT_CENTER_LAT, help="中心点纬度")

    # 飞行参数
    parser.add_argument("--altitude", "-a", type=float, default=DEFAULT_ALTITUDE, help="飞行高度(米)")
    parser.add_argument("--speed", "-s", type=float, default=DEFAULT_SPEED, help="飞行速度(m/s)")
    parser.add_argument("--heading", type=float, default=DEFAULT_HEADING, help="航向角(度): 0=北, 90=东, 180=南, 270=西")

    # 分布与数量
    parser.add_argument("--count", "-n", type=int, default=DEFAULT_COUNT, help="无人机数量")
    parser.add_argument("--spacing", type=float, default=DEFAULT_SPACING, help="横向间距(米)，用于 line 布局")
    parser.add_argument("--spacing-along", type=float, default=DEFAULT_SPACING_ALONG,
                        help="前后间距(米)，用于 line 布局，0 表示齐头并进")
    parser.add_argument("--layout", type=str, default="hex", choices=["hex", "line"],
                        help="分布布局: hex=六边形蜂窝网格(默认), line=直线排列(齐头并进)")
    parser.add_argument("--sim-radius", type=float, default=DEFAULT_SIM_RADIUS, help="仿真有效半径(米)，默认100000")
    parser.add_argument("--classification", type=int, default=DEFAULT_CLASSIFICATION,
                        help="航空器分类/模拟器类型: 0=微型 1=轻型 2=小型 3=中型 4=大型，默认2")

    # 时间与点数
    parser.add_argument("--points", "-p", type=int, default=DEFAULT_POINTS_PER_UAV, help="每架无人机轨迹点数")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MS, help="采样间隔(毫秒)")
    parser.add_argument("--start-time", type=int, default=None, help="起始时间戳(毫秒)，默认当前时间")

    # 输出
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="输出文件路径，默认 mock/kafka_data_parallel.json")
    parser.add_argument("--multi", action="store_true", help="分3个区域生成3个JSON文件（用于多线程发射），默认关闭")

    if IDE_QUICK_RUN:
        # IDE 快速运行模式：循环生成多降维度数据
        print("[IDE模式] 开始生成多降维度数据...")
        total_needed = sum(cfg["count"] for cfg in IDE_DATASETS)
        if total_needed > len(UAV_IDENTIFIERS_EXTENDED):
            print(f"[错误] 错误: IDE_DATASETS 总需求 {total_needed} 架超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
            return

        uid_offset = 0
        global_s_by_mod = {}  # 跨 scene 全局共享的 ID 分配状态
        # 统一所有 scene 的 base_time，避免跨 scene 因 base_time 差异产生碰撞
        unified_base_time = int(datetime.now().timestamp() * 1000)
        for cfg in IDE_DATASETS:
            output_path = os.path.join(_ROOT, cfg["output"])
            if os.path.isfile(output_path) and not IDE_FORCE_OVERWRITE:
                print(f"[跳过] {cfg['label']}: 文件已存在 → {cfg['output']}")
                uid_offset += cfg["count"]
                continue
            if os.path.isfile(output_path) and IDE_FORCE_OVERWRITE:
                print(f"[覆盖] {cfg['label']}: 强制重新生成 → {cfg['output']}")
            print(f"\n{'=' * 60}")
            print(f"[批次] {cfg['label']}: {cfg['count']} 架 → {cfg['output']}")
            print(f"{'=' * 60}")

            args = parser.parse_args([])
            args.count = cfg["count"]
            args.output = cfg["output"]
            args.multi = cfg["multi"]
            args.center_lng = cfg.get("center_lng", DEFAULT_CENTER_LNG)
            args.center_lat = cfg.get("center_lat", DEFAULT_CENTER_LAT)
            args.altitude = cfg.get("altitude", DEFAULT_ALTITUDE)
            args.speed = cfg.get("speed", DEFAULT_SPEED)
            args.heading = cfg.get("heading", DEFAULT_HEADING)
            args.spacing = cfg.get("spacing", DEFAULT_SPACING)
            args.spacing_along = cfg.get("spacing_along", DEFAULT_SPACING_ALONG)
            # 支持分组高度配置：同一批次内不同无人机使用不同高度
            args.altitude_groups = cfg.get("altitude_groups", None)
            args.enable_altitude_groups = cfg.get("enable_altitude_groups", False)
            args.start_time = unified_base_time

            if args.count > len(UAV_IDENTIFIERS_EXTENDED):
                print(f"[错误] 错误: 请求数量 {args.count} 超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
                continue

            if args.multi:
                if args.count < 3:
                    print("[错误] 错误: --multi 模式下 count 至少为3")
                    continue
                group_count = args.count // 3
                base_lng = args.center_lng
                base_lat = args.center_lat
                print(f"\n[多区域] 多区域模式: 将 {args.count} 架无人机分成 3 组，每组约 {group_count} 架")
                print("=" * 60)
                for i in range(3):
                    region_args = argparse.Namespace(**vars(args))
                    region_args.count = group_count if i < 2 else args.count - group_count * 2
                    region_args.output = args.output.replace(".json", f"_{i+1}.json")
                    offset_meters = i * args.spacing * 5
                    offset_lng = offset_meters / (111320.0 * math.cos(math.radians(base_lat)))
                    region_args.center_lng = base_lng + offset_lng
                    region_args.center_lat = base_lat
                    uid_offset = i * group_count
                    print(f"\n[区域] 区域 {i+1}: 中心({region_args.center_lng:.6f}, {region_args.center_lat:.6f}), "
                          f"数量 {region_args.count}, 输出 {region_args.output}")
                    generate_parallel_dataset(region_args, uid_offset=uid_offset,
                                               s_by_mod=global_s_by_mod)
                print("\n" + "=" * 60)
                print(f"[成功] 多区域生成完成: {args.output.replace('.json', '_1.json')}, "
                      f"{args.output.replace('.json', '_2.json')}, {args.output.replace('.json', '_3.json')}")
            else:
                generate_parallel_dataset(args, uid_offset=uid_offset,
                                           s_by_mod=global_s_by_mod)
                uid_offset += args.count

        print("\n" + "=" * 60)
        print(f"[完成] 所有降维度数据生成完成，共使用 {uid_offset} 个唯一 UAV ID")
        print("=" * 60)
        return

    args = parser.parse_args()

    if args.count > len(UAV_IDENTIFIERS_EXTENDED):
        print(f"[错误] 错误: 请求数量 {args.count} 超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
        sys.exit(1)

    if args.multi:
        if args.count < 3:
            print("[错误] 错误: --multi 模式下 count 至少为3")
            sys.exit(1)
        group_count = args.count // 3
        base_lng = args.center_lng
        base_lat = args.center_lat
        print(f"\n[多区域] 多区域模式: 将 {args.count} 架无人机分成 3 组，每组约 {group_count} 架")
        print("=" * 60)
        for i in range(3):
            region_args = argparse.Namespace(**vars(args))
            region_args.count = group_count if i < 2 else args.count - group_count * 2
            region_args.output = args.output.replace(".json", f"_{i+1}.json")
            offset_meters = i * args.spacing * 5
            offset_lng = offset_meters / (111320.0 * math.cos(math.radians(base_lat)))
            region_args.center_lng = base_lng + offset_lng
            region_args.center_lat = base_lat
            uid_offset = i * group_count
            print(f"\n[区域] 区域 {i+1}: 中心({region_args.center_lng:.6f}, {region_args.center_lat:.6f}), "
                  f"数量 {region_args.count}, 输出 {region_args.output}")
            generate_parallel_dataset(region_args, uid_offset=uid_offset)
        print("\n" + "=" * 60)
        print(f"[成功] 多区域生成完成: {args.output.replace('.json', '_1.json')}, "
              f"{args.output.replace('.json', '_2.json')}, {args.output.replace('.json', '_3.json')}")
    else:
        generate_parallel_dataset(args)


if __name__ == "__main__":
    main()
