import pandas as pd
import numpy as np
from datetime import datetime

df = pd.read_excel('c:/Users/wdjlw/iCloudDrive/AI_Python2026/低空测试脚本2026/迭代1.4.0过程数据及缺陷/低空空管自动化系统_缺陷_20260507201556.xlsx')

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
print()

print('=== 12. 测试阶段分布 ===')
stage_counts = df['测试阶段'].value_counts()
print(stage_counts)
print()

print('=== 13. 缺陷发生阶段分布 ===')
occurrence_stage_counts = df['缺陷发生阶段'].value_counts()
print(occurrence_stage_counts)
print()

print('=== 14. 迭代分布 ===')
iteration_counts = df['迭代'].value_counts()
print(iteration_counts)
print()

print('=== 15. 出现频率分布 ===')
freq_counts = df['出现频率'].value_counts()
print(freq_counts)
print()

print('=== 16. 关闭时间范围 ===')
df['关闭日期'] = pd.to_datetime(df['关闭时间'], errors='coerce').dt.date
close_dates = df['关闭日期'].dropna()
if len(close_dates) > 0:
    print(f'最早关闭: {close_dates.min()}, 最晚关闭: {close_dates.max()}')
print()

print('=== 17. 严重缺陷按模块分布 ===')
severe_df = df[df['严重程度'].isin(['致命', '严重'])]
severe_module = severe_df['模块'].value_counts()
print(severe_module)
print()

print('=== 18. 未关闭缺陷列表 ===')
unclosed = df[df['状态'].isin(['新', '接受/处理', '挂起'])]
print(f'未关闭缺陷数: {len(unclosed)}')
print(unclosed[['ID', '标题', '状态', '严重程度', '模块', '优先级']].to_string())
