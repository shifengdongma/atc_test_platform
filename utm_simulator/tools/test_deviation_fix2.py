#!/usr/bin/env python3
"""验证混合方案的轨迹平滑性：稳定期用traj_offset，渐变期用offset_point+smooth_headings"""
import json, math, sys
sys.path.insert(0, '.')

with open('偏离航路数据生成(基于航路).py', 'r', encoding='utf-8') as f:
    source = f.read()
code = source.split('def main(')[0]
exec(code)

# 模拟90度转弯航线
route_points = [
    {'lon': 116.0, 'lat': 40.0},
    {'lon': 116.0, 'lat': 40.009},
    {'lon': 116.012, 'lat': 40.009},
]

traj_center = interpolate_route(route_points, speed_ms=15, start_time_ms=0, interval_ms=1000)
raw_headings = [p['heading'] for p in traj_center]
smooth_headings = _smooth_angles(raw_headings, window=5)

deviate_offset_m = 600.0

# 生成偏移航线（稳定期使用）
offset_points = offset_route_points_list(route_points, deviate_offset_m)
traj_offset = interpolate_route(offset_points, speed_ms=15, start_time_ms=0, interval_ms=1000)

# 混合方案
trajectory_mixed = []
for i, center_pt in enumerate(traj_center):
    t_sec = center_pt['time_ms'] / 1000.0
    if t_sec < 20:
        pt = dict(center_pt)
        pt['heading'] = smooth_headings[i]
        trajectory_mixed.append(pt)
    elif t_sec >= 25:
        if i < len(traj_offset):
            trajectory_mixed.append(traj_offset[i])
        elif traj_offset:
            trajectory_mixed.append(traj_offset[-1])
        else:
            pt = dict(center_pt)
            pt['heading'] = smooth_headings[i]
            trajectory_mixed.append(pt)
    else:
        ratio = (t_sec - 20) / 5.0
        current_offset = deviate_offset_m * ratio
        new_lat, new_lon = offset_point(
            center_pt['lat'], center_pt['lon'], smooth_headings[i], current_offset
        )
        trajectory_mixed.append({
            'lat': new_lat, 'lon': new_lon,
            'heading': smooth_headings[i],
            'time_ms': center_pt['time_ms'],
            'segment_idx': center_pt.get('segment_idx', -1),
        })

print(f'中心线轨迹点数: {len(traj_center)}, 偏移航线点数: {len(traj_offset)}')

print('\n=== 混合方案：转弯处轨迹分析 ===')
print('点号\t时间\t偏移距离(m)\t备注')
print('-' * 50)
for i in range(55, min(85, len(traj_center))):
    dist = geo_distance(traj_center[i]['lat'], traj_center[i]['lon'],
                        trajectory_mixed[i]['lat'], trajectory_mixed[i]['lon'])
    marker = ''
    if dist > deviate_offset_m + 10:
        marker = '  << 超标!'
    print(f'{i}\t{i}s\t{dist:.1f}\t\t{marker}')

print('\n=== 偏移轨迹相邻点分析 ===')
print('点号\t到下一点的距离(m)\t方向变化(°)\t备注')
print('-' * 60)
for i in range(60, min(80, len(trajectory_mixed)-1)):
    p1 = trajectory_mixed[i]
    p2 = trajectory_mixed[i+1]
    dist = geo_distance(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
    if i+2 < len(trajectory_mixed):
        h1 = calc_heading(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
        h2 = calc_heading(p2['lat'], p2['lon'], trajectory_mixed[i+2]['lat'], trajectory_mixed[i+2]['lon'])
        dh = (h2 - h1 + 180) % 360 - 180
    else:
        dh = 0
    marker = ''
    if abs(dh) > 15:
        marker = '  << 方向突变!'
    elif dist > 20 or dist < 5:
        marker = '  << 间距异常!'
    if marker:
        print(f'{i}\t{dist:.1f}\t\t{dh:+.1f}\t\t{marker}')

max_dist = 0.0
exceed_count = 0
for i in range(len(traj_center)):
    dist = geo_distance(traj_center[i]['lat'], traj_center[i]['lon'],
                        trajectory_mixed[i]['lat'], trajectory_mixed[i]['lon'])
    max_dist = max(max_dist, dist)
    if dist > deviate_offset_m + 1:
        exceed_count += 1

print(f'\n最大偏移距离: {max_dist:.1f}m (目标: {deviate_offset_m}m)')
print(f'超标点数(>目标+1m): {exceed_count} / {len(traj_center)}')
