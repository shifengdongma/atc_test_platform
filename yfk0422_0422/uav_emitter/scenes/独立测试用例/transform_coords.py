import json
import re

# 新的起点和终点
new_start_lon = 120.7418790425605
new_start_lat = 31.368951664705985
new_end_lon = 120.66053648948652
new_end_lat = 31.368319878931356

# 读取JSON文件
with open('3.json', 'r', encoding='utf-8') as f:
    content = f.read()
    data = json.loads(content)

# 提取原文件中的所有经纬度
orig_lons = []
orig_lats = []
for item in data:
    orig_lons.append(item['longitude'])
    orig_lats.append(item['latitude'])

orig_start_lon = orig_lons[0]
orig_start_lat = orig_lats[0]
orig_end_lon = orig_lons[-1]
orig_end_lat = orig_lats[-1]

print(f'原起点: {orig_start_lon}, {orig_start_lat}')
print(f'原终点: {orig_end_lon}, {orig_end_lat}')
print(f'新起点: {new_start_lon}, {new_start_lat}')
print(f'新终点: {new_end_lon}, {new_end_lat}')
print(f'共 {len(orig_lons)} 个坐标点')

# 计算新坐标（保持相对偏移比例）
new_lons = []
new_lats = []

for i in range(len(orig_lons)):
    # 计算在原轨迹中的比例位置（基于索引）
    ratio = i / (len(orig_lons) - 1) if len(orig_lons) > 1 else 0
    
    # 线性插值计算新坐标
    new_lon = new_start_lon + (new_end_lon - new_start_lon) * ratio
    new_lat = new_start_lat + (new_end_lat - new_start_lat) * ratio
    
    new_lons.append(new_lon)
    new_lats.append(new_lat)

# 生成替换映射
replacements = []
for i in range(len(orig_lons)):
    replacements.append({
        'old_lon': orig_lons[i],
        'old_lat': orig_lats[i],
        'new_lon': new_lons[i],
        'new_lat': new_lats[i]
    })

# 保存替换映射
with open('coord_replacements.json', 'w', encoding='utf-8') as f:
    json.dump(replacements, f, indent=2)

print('坐标替换映射已保存到 coord_replacements.json')
print(f'示例: {orig_lons[0]} -> {new_lons[0]}')
print(f'示例: {orig_lats[0]} -> {new_lats[0]}')
