#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 kafka_data_parallel.json 中的UID是否在数据库 uav_info 表中存在"""
import json
import sys
import os

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DMDB_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), 'tools_expend_test', 'script')
if _DMDB_DIR not in sys.path:
    sys.path.insert(0, _DMDB_DIR)

from dmdbclient import DmDbClient

# 加载JSON中的UID
json_path = os.path.join(os.path.dirname(_SCRIPT_DIR), 'mock', 'kafka_data_parallel.json')
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
uids = sorted(set(d['uniqueProductIdentificationCode'] for d in data))
print(f'JSON中的UID数量: {len(uids)}')
print('前5个UID:', uids[:5])

# 连接数据库查询
client = DmDbClient()
if not client.connect():
    sys.exit(1)

# 尝试 identify_code 字段（试错法，绕过 USER_TAB_COLUMNS 权限问题）
id_col = None
for c in ['identify_code', 'unique_product_identification_code']:
    try:
        test_sql = f"SELECT {c} FROM uav_info WHERE ROWNUM = 0"
        client.execute(test_sql)
        id_col = c
        print(f'\n✅ 找到字段: {c}')
        break
    except Exception:
        continue

if not id_col:
    print('\n❌ 未找到航空器识别码字段（尝试: identify_code / unique_product_identification_code）')
    client.close()
    sys.exit(1)

# 构建IN查询（达梦IN最多1000个，30个没问题）
in_clause = ', '.join([f"'{u}'" for u in uids])
sql = f"SELECT {id_col} FROM uav_info WHERE {id_col} IN ({in_clause})"
result = client.execute(sql)
found = set(r[id_col] for r in result) if result else set()
print(f'\n数据库中存在: {len(found)} / {len(uids)}')

missing = [u for u in uids if u not in found]
if missing:
    print(f'\n❌ 不存在的UID ({len(missing)}个):')
    for u in missing:
        print(f'  {u}')
else:
    print('\n✅ 全部UID均已存在于数据库')

client.close()
