import json
import re

# 读取替换映射
with open('coord_replacements.json', 'r', encoding='utf-8') as f:
    replacements = json.load(f)

# 读取原文件
with open('3.json', 'r', encoding='utf-8') as f:
    content = f.read()

# 按顺序替换经纬度
# 使用正则表达式找到所有 longitude 和 latitude 值

# 替换 longitude
lon_pattern = r'"longitude":\s*([\d.]+)'
lon_matches = list(re.finditer(lon_pattern, content))

new_content = content
offset = 0
for i, match in enumerate(lon_matches):
    if i < len(replacements):
        old_val = match.group(1)
        new_val = replacements[i]['new_lon']
        # 格式化新值，保留足够精度
        new_val_str = f'{new_val:.13f}'
        
        start = match.start(1) + offset
        end = match.end(1) + offset
        new_content = new_content[:start] + new_val_str + new_content[end:]
        offset += len(new_val_str) - len(old_val)

# 替换 latitude
content = new_content
lat_pattern = r'"latitude":\s*([\d.]+)'
lat_matches = list(re.finditer(lat_pattern, content))

new_content = content
offset = 0
for i, match in enumerate(lat_matches):
    if i < len(replacements):
        old_val = match.group(1)
        new_val = replacements[i]['new_lat']
        # 格式化新值，保留足够精度
        new_val_str = f'{new_val:.15f}'
        
        start = match.start(1) + offset
        end = match.end(1) + offset
        new_content = new_content[:start] + new_val_str + new_content[end:]
        offset += len(new_val_str) - len(old_val)

# 保存新文件
with open('3.json', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('坐标替换完成！')
print(f'共替换 {len(replacements)} 个坐标点')
print(f'起点: {replacements[0]["new_lon"]}, {replacements[0]["new_lat"]}')
print(f'终点: {replacements[-1]["new_lon"]}, {replacements[-1]["new_lat"]}')
