import pandas as pd
import numpy as np
from datetime import datetime

df = pd.read_excel('c:/Users/wdjlw/iCloudDrive/AI_Python2026/低空测试脚本2026/迭代1.4.0过程数据及缺陷/低空空管自动化系统_迭代1.4.0缺陷_20260506140841.xls')

print('=== 1. 严重程度分布 ===')
severity_counts = df['严重程度'].value_counts()
print(severity_counts)
print()

print('=== 2. 状态分布 ===')
status_counts = df['状态'].value_counts()
print(status_counts)
print()

print('=== 3. 优先级分布 ===')
priority_counts = df['优先级'].value_counts()
print(priority_counts)
print()

print('=== 4. 问题大类分布 ===')
category_counts = df['问题大类'].value_counts()
print(category_counts)
print()

print('=== 5. 缺陷原因分类分布 ===')
reason_counts = df['缺陷原因分类'].value_counts()
print(reason_counts)
print()

print('=== 6. 模块分布TOP15 ===')
module_counts = df['模块'].value_counts().head(15)
print(module_counts)
print()

print('=== 7. 创建人分布TOP10 ===')
creator_counts = df['创建人'].value_counts().head(10)
print(creator_counts)
print()

print('=== 8. 问题责任人分布TOP10 ===')
responsibility_counts = df['问题责任人'].value_counts().head(10)
print(responsibility_counts)
print()

print('=== 9. 按天统计缺陷创建趋势 ===')
df['创建日期'] = pd.to_datetime(df['创建时间']).dt.date
daily_counts = df['创建日期'].value_counts().sort_index()
print(daily_counts)
print()

print('=== 10. 严重 & 状态交叉分析 ===')
severity_status = pd.crosstab(df['严重程度'], df['状态'])
print(severity_status)
print()

print('=== 11. 重新打开次数统计 ===')
reopen_count = df['重新打开时间'].notna().sum()
print(f'重新打开的缺陷数: {reopen_count}')
