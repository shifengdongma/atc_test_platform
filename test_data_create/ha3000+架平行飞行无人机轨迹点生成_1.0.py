#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高可用测试环境3000~5000架平行飞行无人机轨迹点生成，10%告警率场景生成，17个扇区（空域坐标），每个扇区只能容纳300无人机

特性：
- 使用 uav_identifiers_extended.py 扩展ID（支持最多5000架）
- 六边形蜂窝网格水平分布，相邻间距可配置
- 所有无人机沿同一航向、同一速度平行飞行
- 支持命令行参数化：中心坐标、高度、间距、数量、航向、速度等
- 支持批量场景配置：简化输入、默认参数继承、自动生成文件名
- 支持扇区选择开关：可控制生成全部/前N个/指定索引的场景
- 支持UAV ID正序/倒序取用，支持起始偏移量配置
- 输出标准 Kafka 遥测 JSON 格式

用法示例：
  python ha3000+架平行飞行无人机轨迹点生成_1.0.py --count 3000 --spacing 300 --altitude 100 --heading 90
  python ha3000+架平行飞行无人机轨迹点生成_1.0.py --center-lng 120.5 --center-lat 31.2 --count 1000 --speed 20

IDE快速运行：
  直接运行脚本，无需命令行参数，按 SCENE_INPUTS 配置批量生成
"""

import json
import math
import os
import sys
import random
import argparse
import re
import logging
from datetime import datetime

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

# ========== 路径配置 ==========
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ========== 第一类：高频配置（每次测试按需调整） ==========

# IDE 快速运行模式开关
# True = IDE直接运行批量生成（使用 SCENE_INPUTS 配置）
# False = 命令行参数模式（手动指定 --count --center-lng 等）
IDE_QUICK_RUN = True

# 扇区选择: "all"=全部, 5=前5个, [0,2,4]=第1/3/5个(0-based索引)
SCENE_SELECT = "all"  # 所有扇区
#SCENE_SELECT = [1, 2] # 所有扇区

# UAV ID 起始偏移量: 从 UAV_IDENTIFIERS_EXTENDED 的第N个元素开始取
UAV_ID_START_OFFSET = 200

# UAV ID 取用顺序: False=正序(从索引0开始), True=倒序(从列表末尾开始)
UAV_ID_REVERSE = False

# IDE 模式下是否强制覆盖已存在的文件
IDE_FORCE_OVERWRITE = True

# 随机种子：用于复现相同的异常注入场景（设为 None 则每次随机）
RANDOM_SEED = None

# IDE 模式下异常注入比例（0.0=不注入, 0.1=10%无人机异常）
IDE_ANOMALY_RATE = 0.0


# ========== 第二类：场景参数模板（特殊场景通过 override 覆盖） ==========

# 以下参数为所有场景的默认模板，单个场景可在 SCENE_INPUTS 中通过第三个参数字典覆盖
DEFAULT_SCENE_CONFIG = {
    "count": 10,                      # 每场景（中心点坐标、扇区）无人机数量
    "center_lng": 116.461380,           # 分布中心经度（度）
    "center_lat": 40.021655,            # 分布中心纬度（度）
    "altitude": 50.0,                   # 默认飞行高度（米）
    "speed": 15.0,                      # 默认飞行速度（米/秒）
    "heading": 90.0,                    # 默认航向角（度）
    "spacing": 2000,                    # 横向间距（米）
    "spacing_along": 2000,              # 前后间距（米）
    "interval": 1000,                   # 采样间隔（毫秒）
    "points": 120,                    # 每架无人机轨迹点数（约20分钟数据）
    "sim_radius": 100000.0,             # 仿真有效半径（米）
    "classification": 3,                # 航空器分类
    "enable_altitude_groups": True,     # 是否启用高度分组
    "altitude_group_config": {           # 高度分组配置
        "first_count": 3,               # 第一组数量：整数=固定架数，字符串如"10%"=百分比
        "first_altitude": 30,            # 第一组飞行高度（米）
        "second_altitude": 50,           # 第二组飞行高度（米）
    },
    "multi": False,                     # 是否分3个区域输出
    "output": "mock/kafka_data_parallel.json",  # 默认输出路径（会被自动命名覆盖）
}


# ========== 第三类：系统底层常量（一般无需修改） ==========

# 场景输入列表：每个元素为 ([经度, 纬度], "编号+地名") 或带 override 字典
# 配置完成后通常不再变动，如需测试新空域可在此添加
SCENE_INPUTS = [
    # ([center_lng, center_lat], "编号+地名", {覆盖字段})
    ([116.461380, 40.021655],  "01北京"),
    ([117.826852, 39.073524], "02天津"),
    ([116.797942, 38.269612], "03沧州"),
    ([118.620119, 37.680876], "04东营"),
    ([116.933169, 36.453227], "05济南"),
    ([120.708629, 37.473974], "06烟台"),
    ([122.351890, 37.329510],  "07威海"),
    ([120.354408, 36.093086], "08青岛"),
    ([118.341695, 35.098066], "09临沂"),
    ([115.614067, 34.459829], "10商丘"),
    ([113.381888, 34.569984], "11郑州"),
    ([114.008407, 33.039381], "12驻马店"),
    ([117.369795, 32.925982], "13蚌埠"),
    ([120.149122, 33.368025], "14盐城"),
    ([118.796679, 31.974394], "15南京"),
    ([120.408145, 31.320259], "16苏州"),
    ([121.554483, 31.125277], "17上海"),
]

# 注：命令行模式默认值统一从 DEFAULT_SCENE_CONFIG 读取，不再单独定义常量


# 地名到拼音首字母映射表（用于自动生成输出文件名）
_PINYIN_MAP = {
    '北京': 'bj', '天津': 'tj', '上海': 'sh', '重庆': 'cq',
    '新疆': 'xj', '西藏': 'xz', '青海': 'qh', '甘肃': 'gs',
    '内蒙': 'nm', '四川': 'sc', '云南': 'yn', '贵州': 'gz',
    '广东': 'gd', '广西': 'gx', '海南': 'hn', '湖南': 'hn',
    '湖北': 'hb', '河南': 'hn', '河北': 'hb', '山东': 'sd',
    '山西': 'sx', '陕西': 'sx', '安徽': 'ah', '江西': 'jx',
    '江苏': 'js', '浙江': 'zj', '福建': 'fj', '台湾': 'tw',
    '辽宁': 'ln', '吉林': 'jl', '黑龙江': 'hlj',
    '沧州': 'cz', '东营': 'dy', '济南': 'jn', '烟台': 'yt',
    '威海': 'wh', '青岛': 'qd', '临沂': 'ly', '商丘': 'sq',
    '郑州': 'zz', '驻马店': 'zmd', '蚌埠': 'bb', '盐城': 'yc',
    '南京': 'nj', '苏州': 'sz',
}

from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED

# ========== 日志配置 ==========
# 日志文件存储在脚本所在目录，每次执行覆盖
LOG_FILE = os.path.join(_SCRIPT_DIR, "ha_模拟数据生成日志.txt")

_LOGGER = logging.getLogger("uav_data_gen")
_LOGGER.setLevel(logging.INFO)


def _setup_logging():
    """初始化日志：控制台 + 文件，每次执行覆盖（mode='w'）"""
    if _LOGGER.handlers:
        return
    formatter = logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    # 控制台输出
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    _LOGGER.addHandler(console)
    # 文件输出（覆盖模式）
    file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    _LOGGER.addHandler(file_handler)


def _log(*args, **kwargs):
    """通过 logging 输出，同时到控制台和日志文件"""
    message = " ".join(str(a) for a in args)
    _LOGGER.info(message)


def label_to_output_path(label: str) -> str:
    """根据标签自动生成输出路径。

    标签格式: "01北京扇区" -> mock/ha_data_scene_01bj.json
             "02新疆空域1" -> mock/ha_data_scene_02xj.json
    """
    m = re.match(r'^(\d+)(.+?)(?:扇区|空域.*)?$', label)
    if not m:
        return f"mock/ha_data_scene_{label}.json"
    num, name = m.group(1), m.group(2)
    py = _PINYIN_MAP.get(name, '')
    if not py:
        # 逐字fallback映射
        char_map = {
            '北': 'b', '京': 'j', '天': 't', '津': 'j',
            '新': 'x', '疆': 'j', '西': 'x', '藏': 'z',
            '青': 'q', '海': 'h', '甘': 'g', '肃': 's',
            '内': 'n', '蒙': 'm',
            '沧': 'c', '州': 'z', '东': 'd', '营': 'y',
            '济': 'j', '南': 'n', '烟': 'y', '台': 't',
            '威': 'w', '岛': 'd', '临': 'l', '沂': 'y',
            '商': 's', '丘': 'q', '郑': 'z', '驻': 'z',
            '马': 'm', '店': 'd', '蚌': 'b', '埠': 'b',
            '盐': 'y', '城': 'c', '苏': 's', '上': 's',
        }
        py = ''.join(char_map.get(c, '') for c in name)
    return f"mock/ha_data_scene_{num}{py}.json"


def expand_scene_inputs(inputs, select="all"):
    """将简化的场景输入展开为完整的配置字典列表。

    Args:
        inputs: 场景输入列表，每个元素为 ([lng, lat], label) 或 ([lng, lat], label, override_dict)
        select: 扇区选择器，"all"/int/list

    Returns:
        完整的配置字典列表
    """
    scenes = []
    for item in inputs:
        if isinstance(item, dict):
            # 兼容字典格式
            center = item.get("center")
            label = item.get("label", f"scene{len(scenes)}")
            override = {k: v for k, v in item.items() if k not in ("center", "label")}
        elif isinstance(item, (list, tuple)):
            center, label = item[0], item[1]
            override = item[2] if len(item) > 2 else {}
        else:
            continue

        cfg = {
            **DEFAULT_SCENE_CONFIG,
            "center_lng": center[0],
            "center_lat": center[1],
            "label": label,
            **override,
        }
        # 允许 override 中自定义 output，否则自动生成
        if "output" not in override:
            cfg["output"] = label_to_output_path(label)

        # 高度分组自适应：根据配置动态生成 altitude_groups
        if cfg.get("enable_altitude_groups"):
            group_cfg = cfg.get("altitude_group_config", {})
            first_count = group_cfg.get("first_count", 30)

            # 支持百分比格式，如 "10%"
            if isinstance(first_count, str) and first_count.endswith('%'):
                first_count = int(cfg["count"] * int(first_count.rstrip('%')) / 100)

            first_count = max(0, min(int(first_count), cfg["count"]))
            cfg["altitude_groups"] = [
                {"count": first_count, "altitude": group_cfg.get("first_altitude", 30)},
                {"count": cfg["count"] - first_count, "altitude": group_cfg.get("second_altitude", 50)}
            ]

        scenes.append(cfg)

    # 应用选择过滤器
    if select == "all":
        return scenes
    elif isinstance(select, int):
        return scenes[:select]
    elif isinstance(select, (list, tuple)):
        return [scenes[i] for i in select if 0 <= i < len(scenes)]
    return scenes


def get_uav_index(i, uid_offset, total, reverse=False):
    """获取无人机在 UAV_IDENTIFIERS_EXTENDED 中的实际索引。

    Args:
        i: 当前场景内的索引 (0-based)
        uid_offset: 跨场景累计偏移量
        total: UAV_IDENTIFIERS_EXTENDED 总长度
        reverse: True=倒序取ID, False=正序取ID

    Returns:
        实际索引
    """
    if reverse:
        return total - 1 - uid_offset - i
    return uid_offset + i


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
        "longitude": round(lon, 8),
        "latitude": round(lat, 8),
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


def generate_parallel_dataset(args, uid_offset=0, s_by_mod=None, uav_id_reverse=False):
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
    _log(f"开始生成 {args.count} 架平行飞行数据...")
    _log(f"  布局: {args.layout} ({'直线排列' if args.layout == 'line' else '六边形蜂窝网格'})")
    _log(f"  中心: ({args.center_lng}, {args.center_lat})")
    _log(f"  航向: {args.heading}°, 速度: {args.speed}m/s, 高度: {args.altitude}m")
    # 构建每架无人机的高度列表
    altitudes = []
    enable_groups = getattr(args, 'enable_altitude_groups', False)
    if enable_groups and hasattr(args, 'altitude_groups') and args.altitude_groups:
        for group in args.altitude_groups:
            group_count = group.get("count", 0)
            group_alt = group.get("altitude", args.altitude)
            altitudes.extend([group_alt] * group_count)
        _log(f"  高度分组已启用: {args.altitude_groups}")
    if not altitudes:
        altitudes = [args.altitude] * args.count
    # 确保高度列表长度与无人机数量一致（超出截断，不足补齐）
    altitudes = altitudes[:args.count]
    while len(altitudes) < args.count:
        altitudes.append(args.altitude)

    if args.layout == "line":
        _log(f"  横向间距: {args.spacing}m, 前后间距: {args.spacing_along}m")
    else:
        _log(f"  间距: {args.spacing}m")
    _log(f"  每架点数: {args.points}")
    _log(f"  分类: {args.classification}, 仿真半径: {args.sim_radius}m")
    order_str = "倒序" if uav_id_reverse else "正序"
    _log(f"  ID偏移: {uid_offset} ({order_str})")
    if estimated_radius > args.sim_radius:
        _log(f"  [警告] 警告: 预估分布半径 {estimated_radius:.0f}m 超过仿真有效半径 {args.sim_radius:.0f}m")
    else:
        _log(f"  预估分布半径: {estimated_radius:.0f}m（在仿真半径内）")

    # ---------- ID 碰撞预检测与避让 ----------
    legacy_avoidance = getattr(args, 'legacy_id_avoidance', True)
    if legacy_avoidance:
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
        used_uids = []
        max_offset_used = 0

        for idx in range(args.count):
            idx_actual = get_uav_index(idx, uid_offset, len(UAV_IDENTIFIERS_EXTENDED), uav_id_reverse)
            uid, _ = UAV_IDENTIFIERS_EXTENDED[idx_actual]
            used_uids.append(uid)
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
            _log(f"  [信息] 最大起始时间偏移: {max_offset_used}ms ({max_offset_used/1000:.1f}秒)")
        _log(f"  [成功] 碰撞预检测通过: {args.count} 架无人机无 ID 碰撞风险")
    else:
        # 关闭 ID 碰撞避让：统一使用 base_time，速度更快
        start_offsets = [0] * args.count
        used_uids = []
        for idx in range(args.count):
            idx_actual = get_uav_index(idx, uid_offset, len(UAV_IDENTIFIERS_EXTENDED), uav_id_reverse)
            uid, _ = UAV_IDENTIFIERS_EXTENDED[idx_actual]
            used_uids.append(uid)
        _log(f"  [信息] ID 碰撞避让已关闭，统一起始时间")

    # 打印实际使用的 UAV ID 列表
    if len(used_uids) <= 15:
        _log(f"  [信息] UAV ID 列表: {', '.join(used_uids)}")
    else:
        _log(f"  [信息] UAV ID 列表: {', '.join(used_uids[:5])} ... {', '.join(used_uids[-5:])} (共 {len(used_uids)} 架)")

        # 高度分组抽检确认
        if enable_groups and len(used_uids) >= 3:
            samples = [(used_uids[i], f"{altitudes[i]}m") for i in range(3)]
            _log(f"  [抽检] 前3架高度: {samples}")
            if len(used_uids) >= 7:
                samples_end = [(used_uids[i], f"{altitudes[i]}m") for i in range(len(used_uids)-3, len(used_uids))]
                _log(f"  [抽检] 后3架高度: {samples_end}")

    # ---------- 异常注入准备 ----------
    anomaly_rate = getattr(args, 'anomaly_rate', 0.0)
    anomaly_duration = getattr(args, 'anomaly_duration', 10)
    anomaly_uavs = {}
    if anomaly_rate > 0 and args.count > 0:
        anomaly_count = max(1, int(args.count * anomaly_rate))
        anomaly_count = min(anomaly_count, args.count)
        anomaly_indices = random.sample(range(args.count), anomaly_count)
        for aidx in anomaly_indices:
            start_p = random.randint(int(args.points * 0.2), int(args.points * 0.6))
            a_type = random.choice(['altitude', 'speed', 'heading'])
            if a_type == 'altitude':
                delta = random.choice([-1, 1]) * random.uniform(20, 50)
            elif a_type == 'speed':
                delta = random.choice([-1, 1]) * random.uniform(5, 10)
            else:
                delta = random.choice([-1, 1]) * random.uniform(30, 60)
            anomaly_uavs[aidx] = {'type': a_type, 'start': start_p, 'duration': anomaly_duration, 'delta': delta}
        _log(f"  [异常注入] {len(anomaly_indices)} 架无人机将触发飞行异常 ({anomaly_rate*100:.0f}%)")
    # -----------------------------------

    is_dry_run = getattr(args, 'dry_run', False)
    all_data = [] if not is_dry_run else None

    for i in range(args.count):
        idx_actual = get_uav_index(i, uid_offset, len(UAV_IDENTIFIERS_EXTENDED), uav_id_reverse)
        uid, reg_sign = UAV_IDENTIFIERS_EXTENDED[idx_actual]
        offset_x, offset_y = offsets[i]

        start_lng = args.center_lng + offset_x
        start_lat = args.center_lat + offset_y

        base_alt = altitudes[i]
        base_speed = args.speed
        base_heading = args.heading
        is_anomaly_uav = i in anomaly_uavs

        if not is_dry_run:
            for p in range(args.points):
                # timestamp = base_time + offset + p*interval
                # offset 已确保全局无碰撞，interval 固定为 1000ms
                ts = base_time + start_offsets[i] + p * args.interval
                lon = start_lng + p * d_lng
                lat = start_lat + p * d_lat

                # 异常注入：在指定时间段内修改飞行参数
                current_alt = base_alt
                current_speed = base_speed
                current_heading = base_heading
                if is_anomaly_uav:
                    a = anomaly_uavs[i]
                    if a['start'] <= p < a['start'] + a['duration']:
                        if a['type'] == 'altitude':
                            current_alt = base_alt + a['delta']
                        elif a['type'] == 'speed':
                            current_speed = base_speed + a['delta']
                        elif a['type'] == 'heading':
                            current_heading = (base_heading + a['delta']) % 360

                point = make_telemetry_point(
                    uid, reg_sign, ts, lon, lat, current_alt, current_speed, current_heading, args.classification
                )
                all_data.append(point)

        if (i + 1) % 100 == 0 or (i + 1) == args.count:
            _log(f"  已生成 {i + 1} 架...")

    output_path = os.path.join(_ROOT, args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    is_compact = getattr(args, 'compact', False)

    if not is_dry_run:
        if HAS_ORJSON:
            option = orjson.OPT_INDENT_2 if not is_compact else 0
            with open(output_path, "wb") as f:
                f.write(orjson.dumps(all_data, option=option))
        else:
            dump_kwargs = {"ensure_ascii": False}
            if is_compact:
                dump_kwargs["separators"] = (",", ":")
            else:
                dump_kwargs["indent"] = 2
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, **dump_kwargs)

    # 统计
    if is_dry_run:
        uav_ids = set(used_uids)
        total_points = args.count * args.points
        # 估算经纬度范围（首架起点 ~ 末架终点）
        if args.count > 0 and offsets:
            first_lon = args.center_lng + offsets[0][0]
            first_lat = args.center_lat + offsets[0][1]
            last_lon = args.center_lng + offsets[-1][0] + (args.points - 1) * d_lng
            last_lat = args.center_lat + offsets[-1][1] + (args.points - 1) * d_lat
            lngs = [min(first_lon, last_lon), max(first_lon, last_lon)]
            lats = [min(first_lat, last_lat), max(first_lat, last_lat)]
        else:
            lngs = [args.center_lng, args.center_lng]
            lats = [args.center_lat, args.center_lat]
    else:
        uav_ids = set(p["uniqueProductIdentificationCode"] for p in all_data)
        lngs = [p["longitude"] for p in all_data]
        lats = [p["latitude"] for p in all_data]
        total_points = len(all_data)

    abs_output = os.path.abspath(output_path)
    if is_dry_run:
        _log(f"\n[DryRun] 摘要: {abs_output}")
    else:
        _log(f"\n[成功] 生成完成: {abs_output}")
    _log(f"  无人机数量: {len(uav_ids)}")
    _log(f"  总轨迹点数: {total_points}")
    _log(f"  预计文件大小: {total_points * 350 / 1024 / 1024:.1f} MB")
    _log(f"  经度范围: {min(lngs):.6f} ~ {max(lngs):.6f}")
    _log(f"  纬度范围: {min(lats):.6f} ~ {max(lats):.6f}")
    if len(used_uids) <= 15:
        _log(f"  UAV ID: {', '.join(used_uids)}")
    else:
        _log(f"  UAV ID: {', '.join(used_uids[:5])} ... {', '.join(used_uids[-5:])}")


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="生成 N 架无人机平行飞行数据集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  python ha3000+架平行飞行无人机轨迹点生成_1.0.py
  python ha3000+架平行飞行无人机轨迹点生成_1.0.py --count 1000 --spacing 500 --altitude 150
  python ha3000+架平行飞行无人机轨迹点生成_1.0.py --center-lng 120.5 --center-lat 31.2 --speed 20 --heading 0
  python ha3000+架平行飞行无人机轨迹点生成_1.0.py --layout line --count 30 --spacing 100 --heading 90  # 直线排列
        """,
    )

    # 中心坐标
    parser.add_argument("--center-lng", type=float, default=DEFAULT_SCENE_CONFIG["center_lng"], help="中心点经度")
    parser.add_argument("--center-lat", type=float, default=DEFAULT_SCENE_CONFIG["center_lat"], help="中心点纬度")

    # 飞行参数
    parser.add_argument("--altitude", "-a", type=float, default=DEFAULT_SCENE_CONFIG["altitude"], help="飞行高度(米)")
    parser.add_argument("--speed", "-s", type=float, default=DEFAULT_SCENE_CONFIG["speed"], help="飞行速度(m/s)")
    parser.add_argument("--heading", type=float, default=DEFAULT_SCENE_CONFIG["heading"], help="航向角(度): 0=北, 90=东, 180=南, 270=西")

    # 分布与数量
    parser.add_argument("--count", "-n", type=int, default=DEFAULT_SCENE_CONFIG["count"], help="无人机数量")
    parser.add_argument("--spacing", type=float, default=DEFAULT_SCENE_CONFIG["spacing"], help="横向间距(米)，用于 line 布局")
    parser.add_argument("--spacing-along", type=float, default=DEFAULT_SCENE_CONFIG["spacing_along"],
                        help="前后间距(米)，用于 line 布局，0 表示齐头并进")
    parser.add_argument("--layout", type=str, default="hex", choices=["hex", "line"],
                        help="分布布局: hex=六边形蜂窝网格(默认), line=直线排列(齐头并进)")
    parser.add_argument("--sim-radius", type=float, default=DEFAULT_SCENE_CONFIG["sim_radius"], help="仿真有效半径(米)，默认100000")
    parser.add_argument("--classification", type=int, default=DEFAULT_SCENE_CONFIG["classification"],
                        help="航空器分类/模拟器类型: 0=微型 1=轻型 2=小型 3=中型 4=大型，默认3")

    # 时间与点数
    parser.add_argument("--points", "-p", type=int, default=DEFAULT_SCENE_CONFIG["points"], help="每架无人机轨迹点数")
    parser.add_argument("--interval", type=int, default=DEFAULT_SCENE_CONFIG["interval"], help="采样间隔(毫秒)")
    parser.add_argument("--start-time", type=int, default=None, help="起始时间戳(毫秒)，默认当前时间")

    # 输出与模式
    parser.add_argument("--output", "-o", default=DEFAULT_SCENE_CONFIG["output"], help="输出文件路径，默认 mock/kafka_data_parallel.json")
    parser.add_argument("--multi", action="store_true", help="分3个区域生成3个JSON文件（用于多线程发射），默认关闭")
    parser.add_argument("--multi-region-spacing-factor", type=float, default=5.0,
                        help="多区域模式下的区域间距倍数，默认5")
    parser.add_argument("--compact", action="store_true", help="使用紧凑JSON格式输出（无缩进），减小文件体积")
    parser.add_argument("--dry-run", action="store_true", help="只输出摘要信息，不生成JSON文件")
    parser.add_argument("--legacy-id-avoidance", action="store_true", default=True,
                        help="启用传统ID碰撞避让逻辑（默认开启）")
    parser.add_argument("--no-legacy-id-avoidance", dest="legacy_id_avoidance", action="store_false",
                        help="关闭传统ID碰撞避让逻辑，可提升生成速度")
    parser.add_argument("--anomaly-rate", type=float, default=0.0,
                        help="异常注入比例，如0.1表示10%%的无人机会触发飞行异常，默认0（不注入）")
    parser.add_argument("--anomaly-duration", type=int, default=10,
                        help="每次异常持续的轨迹点数，默认10")
    parser.add_argument("--random-seed", type=int, default=None,
                        help="随机种子，用于复现相同的异常注入场景")

    # 设置随机种子（IDE 配置优先，命令行参数可覆盖）
    seed = RANDOM_SEED
    if IDE_QUICK_RUN:
        if seed is not None:
            random.seed(seed)
            _log(f"[配置] 随机种子已设置: {seed}，异常注入场景可复现")
        # IDE 快速运行模式：根据 SCENE_INPUTS + SCENE_SELECT 批量生成场景数据
        _log("[IDE模式] 开始生成多场景数据...")
        # 展开场景配置（支持扇区选择、默认参数继承、自动命名）
        IDE_DATASETS = expand_scene_inputs(SCENE_INPUTS, SCENE_SELECT)
        total_needed = sum(cfg["count"] for cfg in IDE_DATASETS)
        if total_needed > len(UAV_IDENTIFIERS_EXTENDED):
            _log(f"[错误] 错误: IDE_DATASETS 总需求 {total_needed} 架超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
            return

        uid_offset = UAV_ID_START_OFFSET
        global_s_by_mod = {}  # 跨 scene 全局共享的 ID 分配状态
        # 统一所有 scene 的 base_time，避免跨 scene 因 base_time 差异产生碰撞
        unified_base_time = int(datetime.now().timestamp() * 1000)
        order_str = "倒序" if UAV_ID_REVERSE else "正序"

        _log("\n" + "=" * 60)
        _log("[总体概览]")
        _log(f"  场景数量: {len(IDE_DATASETS)}")
        _log(f"  总无人机数: {total_needed}")
        _log(f"  ID 起始偏移: {UAV_ID_START_OFFSET}")
        _log(f"  ID 取用顺序: {order_str}")
        _log(f"  统一 base_time: {unified_base_time}")
        _log("  场景列表:")
        total_ids = len(UAV_IDENTIFIERS_EXTENDED)
        for i, cfg in enumerate(IDE_DATASETS, 1):
            if UAV_ID_REVERSE:
                start_actual = total_ids - 1 - uid_offset
                end_actual = total_ids - uid_offset - cfg["count"]
            else:
                start_actual = uid_offset
                end_actual = uid_offset + cfg["count"] - 1
            _log(f"    {i}. {cfg['label']}: {cfg['count']} 架 (ID 索引 {start_actual}~{end_actual}) -> {cfg['output']}")
            uid_offset += cfg["count"]
        _log("=" * 60)
        uid_offset = UAV_ID_START_OFFSET  # 重置偏移量，供实际生成使用

        for cfg in IDE_DATASETS:
            output_path = os.path.join(_ROOT, cfg["output"])
            if os.path.isfile(output_path) and not IDE_FORCE_OVERWRITE:
                _log(f"[跳过] {cfg['label']}: 文件已存在 → {cfg['output']}")
                uid_offset += cfg["count"]
                continue
            if os.path.isfile(output_path) and IDE_FORCE_OVERWRITE:
                _log(f"[覆盖] {cfg['label']}: 强制重新生成 → {cfg['output']}")
            _log(f"\n{'=' * 60}")
            _log(f"[批次] {cfg['label']}: {cfg['count']} 架 → {cfg['output']}")
            _log(f"{'=' * 60}")

            args = parser.parse_args([])
            # 从展开后的场景配置中直接取值（expand_scene_inputs 已合并所有默认值）
            args.count = cfg["count"]
            args.output = cfg["output"]
            args.multi = cfg["multi"]
            args.center_lng = cfg["center_lng"]
            args.center_lat = cfg["center_lat"]
            args.altitude = cfg["altitude"]
            args.speed = cfg["speed"]
            args.heading = cfg["heading"]
            args.spacing = cfg["spacing"]
            args.spacing_along = cfg["spacing_along"]
            args.interval = cfg["interval"]
            args.points = cfg["points"]
            args.sim_radius = cfg["sim_radius"]
            args.classification = cfg["classification"]
            args.altitude_groups = cfg["altitude_groups"]
            args.enable_altitude_groups = cfg["enable_altitude_groups"]
            args.start_time = unified_base_time
            args.anomaly_rate = IDE_ANOMALY_RATE
            args.anomaly_duration = 10

            if args.count > len(UAV_IDENTIFIERS_EXTENDED):
                _log(f"[错误] 错误: 请求数量 {args.count} 超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
                continue

            if args.multi:
                if args.count < 3:
                    _log("[错误] 错误: --multi 模式下 count 至少为3")
                    continue
                group_count = args.count // 3
                base_lng = args.center_lng
                base_lat = args.center_lat
                _log(f"\n[多区域] 多区域模式: 将 {args.count} 架无人机分成 3 组，每组约 {group_count} 架")
                _log("=" * 60)
                for i in range(3):
                    region_args = argparse.Namespace(**vars(args))
                    region_args.count = group_count if i < 2 else args.count - group_count * 2
                    region_args.output = args.output.replace(".json", f"_{i+1}.json")
                    offset_meters = i * args.spacing * getattr(args, 'multi_region_spacing_factor', 5.0)
                    offset_lng = offset_meters / (111320.0 * math.cos(math.radians(base_lat)))
                    region_args.center_lng = base_lng + offset_lng
                    region_args.center_lat = base_lat
                    region_uid_offset = uid_offset + i * group_count
                    _log(f"\n[区域] 区域 {i+1}: 中心({region_args.center_lng:.6f}, {region_args.center_lat:.6f}), "
                          f"数量 {region_args.count}, 输出 {region_args.output}")
                    generate_parallel_dataset(region_args, uid_offset=region_uid_offset,
                                               s_by_mod=global_s_by_mod,
                                               uav_id_reverse=UAV_ID_REVERSE)
                _log("\n" + "=" * 60)
                _log(f"[成功] 多区域生成完成: {args.output.replace('.json', '_1.json')}, "
                      f"{args.output.replace('.json', '_2.json')}, {args.output.replace('.json', '_3.json')}")
                uid_offset += args.count
            else:
                generate_parallel_dataset(args, uid_offset=uid_offset,
                                           s_by_mod=global_s_by_mod,
                                           uav_id_reverse=UAV_ID_REVERSE)
                uid_offset += args.count

        # 总汇总表
        _log("\n" + "=" * 60)
        _log("[总汇总表]")
        _log(f"  {'扇区':<12} {'架数':>6} {'文件大小(MB)':>14} {'输出文件'}")
        total_size_all = 0
        total_count_all = 0
        for cfg in IDE_DATASETS:
            total_size = 0
            files = []
            base_path = os.path.join(_ROOT, cfg["output"])
            if cfg["multi"]:
                for suffix in ["_1.json", "_2.json", "_3.json"]:
                    fpath = base_path.replace(".json", suffix)
                    if os.path.isfile(fpath):
                        total_size += os.path.getsize(fpath)
                        files.append(os.path.basename(fpath))
            else:
                if os.path.isfile(base_path):
                    total_size = os.path.getsize(base_path)
                    files.append(cfg["output"])
            files_str = ", ".join(files) if files else "(文件不存在)"
            size_mb = total_size / 1024 / 1024
            _log(f"  {cfg['label']:<12} {cfg['count']:>6} {size_mb:>14.1f} {files_str}")
            total_size_all += size_mb
            total_count_all += cfg["count"]
        _log(f"  {'合计':<12} {total_count_all:>6} {total_size_all:>14.1f}")
        _log("=" * 60)

        _log(f"[完成] 所有场景数据生成完成，共使用 {uid_offset} 个唯一 UAV ID")
        return

    args = parser.parse_args()

    # 命令行模式下优先使用命令行传入的 random_seed
    if args.random_seed is not None:
        seed = args.random_seed
    if seed is not None:
        random.seed(seed)
        _log(f"[配置] 随机种子已设置: {seed}，异常注入场景可复现")

    if args.count > len(UAV_IDENTIFIERS_EXTENDED):
        _log(f"[错误] 错误: 请求数量 {args.count} 超过扩展ID上限 {len(UAV_IDENTIFIERS_EXTENDED)}")
        sys.exit(1)

    if args.multi:
        if args.count < 3:
            _log("[错误] 错误: --multi 模式下 count 至少为3")
            sys.exit(1)
        group_count = args.count // 3
        base_lng = args.center_lng
        base_lat = args.center_lat
        _log(f"\n[多区域] 多区域模式: 将 {args.count} 架无人机分成 3 组，每组约 {group_count} 架")
        _log("=" * 60)
        for i in range(3):
            region_args = argparse.Namespace(**vars(args))
            region_args.count = group_count if i < 2 else args.count - group_count * 2
            region_args.output = args.output.replace(".json", f"_{i+1}.json")
            offset_meters = i * args.spacing * getattr(args, 'multi_region_spacing_factor', 5.0)
            offset_lng = offset_meters / (111320.0 * math.cos(math.radians(base_lat)))
            region_args.center_lng = base_lng + offset_lng
            region_args.center_lat = base_lat
            region_uid_offset = i * group_count
            _log(f"\n[区域] 区域 {i+1}: 中心({region_args.center_lng:.6f}, {region_args.center_lat:.6f}), "
                  f"数量 {region_args.count}, 输出 {region_args.output}")
            generate_parallel_dataset(region_args, uid_offset=region_uid_offset,
                                       s_by_mod={})
        _log("\n" + "=" * 60)
        _log(f"[成功] 多区域生成完成: {args.output.replace('.json', '_1.json')}, "
              f"{args.output.replace('.json', '_2.json')}, {args.output.replace('.json', '_3.json')}")
    else:
        generate_parallel_dataset(args)


if __name__ == "__main__":
    main()
