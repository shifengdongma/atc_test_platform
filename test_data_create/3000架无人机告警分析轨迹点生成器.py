import json
import random
import math
import os
import sys

# ==================== 可配置参数 ====================
# 中心点坐标（度）——修改此处即可改变分布中心
CENTER_LNG = 89.2306   # 中心点经度
CENTER_LAT = 38.19424  # 中心点纬度

# 无人机之间的最小间隔（米）
SPACING_METERS = 300
# ===================================================

# 路径计算：获取项目根目录（脚本的上级目录，与原始脚本一致）
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

# 读取原始数据
MOCK_DIR = os.path.join(_root, "mock")
KAFKA_DATA_JSON_PATH = os.path.join(MOCK_DIR, "kafka_data_yfk.json")
with open(KAFKA_DATA_JSON_PATH, 'r', encoding='utf-8') as f:
    original_data = json.load(f)

# 原始数据中的轨迹点数
original_points = len(original_data)
print(f"原始数据包含 {original_points} 个轨迹点")

# 提取原始轨迹点（按无人机分组）
uav_trajectories = {}
for point in original_data:
    uav_id = point['uniqueProductIdentificationCode']
    if uav_id not in uav_trajectories:
        uav_trajectories[uav_id] = []
    uav_trajectories[uav_id].append(point)

print(f"原始无人机数量: {len(uav_trajectories)}")
for uav_id, trajectory in uav_trajectories.items():
    print(f"  {uav_id}: {len(trajectory)} 个轨迹点")

# 计算当前纬度下经纬度与米的转换系数
METERS_PER_DEGREE_LAT = 111320.0
METERS_PER_DEGREE_LNG = 111320.0 * math.cos(math.radians(CENTER_LAT))

# 300米对应的经纬度偏移量
SPACING_DEG_LNG = SPACING_METERS / METERS_PER_DEGREE_LNG
SPACING_DEG_LAT = SPACING_METERS / METERS_PER_DEGREE_LAT


def generate_hex_grid_offsets(n):
    """
    生成 n 个六边形蜂窝网格的经纬度偏移量（相对于中心点）。
    采用立方体坐标 (x, y, z) 满足 x + y + z = 0，从中心向外逐环扩展。
    相邻无人机之间的实际地理距离严格等于 SPACING_METERS（约300米）。
    """
    if n <= 0:
        return []

    offsets = [(0.0, 0.0)]  # 第1架在中心点

    if n == 1:
        return offsets

    # 六边形的6个方向向量
    directions = [(1, 0, -1), (0, 1, -1), (-1, 1, 0),
                  (-1, 0, 1), (0, -1, 1), (1, -1, 0)]

    ring = 1
    while len(offsets) < n:
        # 每环起点: (0, -ring, ring)
        x, y, z = 0, -ring, ring
        for dx, dy, dz in directions:
            for _ in range(ring):
                # 将立方体坐标转换为轴向坐标 (q=x, r=z)，再转经纬度偏移
                # 六边形网格平面坐标公式：
                #   x_cart = spacing * (q + r/2)
                #   y_cart = spacing * r * sqrt(3)/2
                lng_offset = (x + z * 0.5) * SPACING_DEG_LNG
                lat_offset = z * (SPACING_DEG_LAT * math.sqrt(3) / 2)

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


def generate_uav_data(base_uav_id, base_trajectory, offset_x, offset_y, time_shift):
    """生成一架无人机的轨迹数据"""
    new_trajectory = []
    for point in base_trajectory:
        new_point = point.copy()
        new_point['uniqueProductIdentificationCode'] = base_uav_id
        new_point['realNameRegistrationSign'] = base_uav_id

        # 经纬度偏移：中心点 + 相对偏移
        new_lng = CENTER_LNG + offset_x
        new_lat = CENTER_LAT + offset_y

        new_point['longitude'] = round(new_lng, 6)
        new_point['latitude'] = round(new_lat, 6)

        # 时间戳偏移：保留原始逻辑 + 按序号累加，避免重复
        new_point['timestamp'] = point['timestamp'] + int(offset_x * 1000) + int(offset_y * 1000) + time_shift

        new_trajectory.append(new_point)
    return new_trajectory


def generate_dataset(num_uavs, output_file):
    """生成指定数量无人机的数据集"""
    all_data = []

    # 获取基础轨迹模板
    base_uav_ids = list(uav_trajectories.keys())
    num_base_trajectories = len(base_uav_ids)
    points_per_uav = len(uav_trajectories[base_uav_ids[0]])  # 约200个点

    print(f"\n生成 {num_uavs} 架无人机数据，每架 {points_per_uav} 个轨迹点，总计 {num_uavs * points_per_uav} 个点")

    # 预计算所有偏移量（六边形蜂窝网格）
    offsets = generate_hex_grid_offsets(num_uavs)

    for i in range(num_uavs):
        # 选择基础轨迹模板（循环使用）
        base_id = base_uav_ids[i % num_base_trajectories]
        base_trajectory = uav_trajectories[base_id]

        # 生成新的无人机ID
        new_uav_id = f"UAV_{i+1:06d}"

        # 获取预计算的偏移量
        offset_x, offset_y = offsets[i]

        # 生成轨迹（time_shift = i * 1000 保证各机时间戳不重合）
        new_trajectory = generate_uav_data(new_uav_id, base_trajectory, offset_x, offset_y, time_shift=i * 1000)
        all_data.extend(new_trajectory)

        if (i + 1) % 500 == 0:
            print(f"  已生成 {i+1} 架无人机...")

    # 按时间戳排序
    all_data.sort(key=lambda x: x['timestamp'])

    # 保存文件
    output_path = os.path.join(_root, output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    print(f"  已保存到 {output_path}，共 {len(all_data)} 个轨迹点")
    return all_data


# 预计算并打印分布范围
print("=" * 50)
print(f"分布中心: ({CENTER_LNG}, {CENTER_LAT})")
print(f"最小间隔: {SPACING_METERS} 米")
for num in [1000, 2000, 3000]:
    test_offsets = generate_hex_grid_offsets(num)
    lngs = [CENTER_LNG + o[0] for o in test_offsets]
    lats = [CENTER_LAT + o[1] for o in test_offsets]
    print(f"{num}架无人机预计分布范围: 经度 {min(lngs):.4f}~{max(lngs):.4f}, 纬度 {min(lats):.4f}~{max(lats):.4f}")
print("=" * 50)

# 生成四个数据集
print("开始生成数据集...")

# 100架无人机
data_100 = generate_dataset(100, 'mock/kafka_data_alarm_100.json')

# 1000架无人机
# data_1000 = generate_dataset(1000, 'mock/kafka_data_alarm_1000.json')

# 2000架无人机
# data_2000 = generate_dataset(2000, 'mock/kafka_data_alarm_2000.json')

# 3000架无人机
# data_3000 = generate_dataset(3000, 'mock/kafka_data_alarm_3000.json')

print("\n" + "=" * 50)
print("生成完成！")
print(f"100架无人机文件: mock/kafka_data_alarm_100.json ({len(data_100)} 个轨迹点)")
# print(f"1000架无人机文件: mock/kafka_data_alarm_1000.json ({len(data_1000)} 个轨迹点)")
# print(f"2000架无人机文件: mock/kafka_data_alarm_2000.json ({len(data_2000)} 个轨迹点)")
# print(f"3000架无人机文件: mock/kafka_data_alarm_3000.json ({len(data_3000)} 个轨迹点)")

# 验证数据
print("\n数据验证:")
for file_name, num_uavs in [
    ('mock/kafka_data_alarm_100.json', 100)
    ,('mock/kafka_data_alarm_1000.json', 1000)
    ,('mock/kafka_data_alarm_2000.json', 2000)
    ,('mock/kafka_data_alarm_3000.json', 3000)
]:
    file_path = os.path.join(_root, file_name)
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 统计无人机数量
    uav_ids = set(p['uniqueProductIdentificationCode'] for p in data)
    points_per_uav = len(data) / len(uav_ids)

    # 统计经纬度范围
    lngs = [p['longitude'] for p in data]
    lats = [p['latitude'] for p in data]

    # 计算实际最小间距（取每架无人机的第一个轨迹点）
    uav_first_points = {}
    for p in data:
        uid = p['uniqueProductIdentificationCode']
        if uid not in uav_first_points:
            uav_first_points[uid] = (p['longitude'], p['latitude'])

    positions = list(uav_first_points.values())
    min_dist = float('inf')
    for a in range(len(positions)):
        for b in range(a + 1, len(positions)):
            dx = (positions[b][0] - positions[a][0]) * METERS_PER_DEGREE_LNG
            dy = (positions[b][1] - positions[a][1]) * METERS_PER_DEGREE_LAT
            d = math.sqrt(dx * dx + dy * dy)
            if d < min_dist:
                min_dist = d

    print(f"\n{file_name}:")
    print(f"  无人机数量: {len(uav_ids)}")
    print(f"  总轨迹点数: {len(data)}")
    print(f"  每架平均点数: {points_per_uav:.1f}")
    print(f"  经度范围: {min(lngs):.4f} ~ {max(lngs):.4f}")
    print(f"  纬度范围: {min(lats):.4f} ~ {max(lats):.4f}")
    print(f"  实际最小间距: {min_dist:.1f} 米")
