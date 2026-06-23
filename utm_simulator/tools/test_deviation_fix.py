#!/usr/bin/env python3
"""验证偏离航路修复后的轨迹平滑性"""
import json, math, sys
sys.path.insert(0, '.')

# 从目标脚本导入函数（读取到 main 函数之前）
with open('偏离航路数据生成(基于航路).py', 'r', encoding='utf-8') as f:
    source = f.read()
code = source.split('def main(')[0]
exec(code)

# 模拟一个90度转弯航线：向北1km，然后向东1km
route_points = [
    {'lon': 116.0, 'lat': 40.0},
    {'lon': 116.0, 'lat': 40.009},
    {'lon': 116.012, 'lat': 40.009},
]

# 生成中心线轨迹
traj_center = interpolate_route(route_points, speed_ms=15, start_time_ms=0, interval_ms=1000)
print(f'中心线轨迹点数: {len(traj_center)}')

# 平滑 heading
raw_headings = [p['heading'] for p in traj_center]
smooth_headings = _smooth_angles(raw_headings, window=5)

# 模拟新逻辑：偏航后使用 offset_point + smooth_headings
deviate_offset_m = 600.0
trajectory_new = []
for i, center_pt in enumerate(traj_center):
    t_sec = center_pt['time_ms'] / 1000.0
    if t_sec < 20:
        pt = dict(center_pt)
        pt['heading'] = smooth_headings[i]
        trajectory_new.append(pt)
    else:
        new_lat, new_lon = offset_point(
            center_pt['lat'], center_pt['lon'], smooth_headings[i], deviate_offset_m
        )
        trajectory_new.append({
            'lat': new_lat, 'lon': new_lon,
            'heading': smooth_headings[i],
            'time_ms': center_pt['time_ms'],
            'segment_idx': center_pt.get('segment_idx', -1),
        })

# 分析转弯处（第60-80点）的轨迹连续性
print('\n=== 新逻辑：转弯处轨迹分析 ===')
print('点号\t时间\theading\t平滑heading\t偏移距离(m)\t纬度\t\t经度')
print('-' * 100)
for i in range(55, min(85, len(traj_center))):
    dist = geo_distance(traj_center[i]['lat'], traj_center[i]['lon'],
                        trajectory_new[i]['lat'], trajectory_new[i]['lon'])
    marker = ''
    if dist > deviate_offset_m + 10:
        marker = '  << 超标!'
    print(f'{i}\t{i}s\t{traj_center[i]["heading"]:.1f}\t{smooth_headings[i]:.1f}\t\t{dist:.1f}{marker}')

# 计算相邻偏移点之间的距离和方向（判断轨迹是否有"羊角"/"勾回"）
print('\n=== 偏移轨迹相邻点分析（航段交界处）===')
print('点号\t到下一点的距离(m)\t方向变化(°)\t备注')
print('-' * 70)
for i in range(60, min(80, len(trajectory_new)-1)):
    p1 = trajectory_new[i]
    p2 = trajectory_new[i+1]
    dist = geo_distance(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
    h1 = calc_heading(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
    h2 = calc_heading(p2['lat'], p2['lon'], 
                      trajectory_new[i+2]['lat'], trajectory_new[i+2]['lon']) if i+2 < len(trajectory_new) else h1
    dh = (h2 - h1 + 180) % 360 - 180
    marker = ''
    if abs(dh) > 15:
        marker = '  << 方向突变!'
    elif dist > 20 or dist < 5:
        marker = '  << 间距异常!'
    print(f'{i}\t{dist:.1f}\t\t{dh:+.1f}\t\t{marker}')

# 可视化：计算偏移轨迹相对于中心线的方向
print('\n=== 偏移方向连续性（判断是否有"羊角"）===')
for i in range(60, min(78, len(traj_center))):
    # 从中心线到偏移点的向量方向
    dx = trajectory_new[i]['lon'] - traj_center[i]['lon']
    dy = trajectory_new[i]['lat'] - traj_center[i]['lat']
    offset_dir = math.degrees(math.atan2(dx, dy)) % 360
    
    dx2 = trajectory_new[i+1]['lon'] - traj_center[i+1]['lon']
    dy2 = trajectory_new[i+1]['lat'] - traj_center[i+1]['lat']
    offset_dir2 = math.degrees(math.atan2(dx2, dy2)) % 360
    
    dd = (offset_dir2 - offset_dir + 180) % 360 - 180
    marker = '  << 偏移方向突变!' if abs(dd) > 15 else ''
    if marker:
        print(f'点{i}->{i+1}: 偏移方向变化 {dd:+.1f}°{marker}')

# 统计最大偏移距离
max_dist = 0.0
exceed_count = 0
for i in range(len(traj_center)):
    dist = geo_distance(traj_center[i]['lat'], traj_center[i]['lon'],
                        trajectory_new[i]['lat'], trajectory_new[i]['lon'])
    max_dist = max(max_dist, dist)
    if dist > deviate_offset_m + 1:
        exceed_count += 1

print(f'\n最大偏移距离: {max_dist:.1f}m (目标: {deviate_offset_m}m)')
print(f'超标点数(>目标+1m): {exceed_count} / {len(traj_center)}')
