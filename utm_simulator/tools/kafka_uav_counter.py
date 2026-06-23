#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka UAV 数量统计器
消费 uav_runtime_data topic，统计实际接收到的不同 UAV 数量
"""
import json
import sys
import time
from kafka import KafkaConsumer

KAFKA_URL = "10.165.19.213:30011"
TOPIC = "uav_runtime_data"
TIMEOUT_SEC = 30  # 监听30秒

print(f"连接 Kafka: {KAFKA_URL}")
print(f"订阅 Topic: {TOPIC}")
print(f"监听时长: {TIMEOUT_SEC} 秒")
print("-" * 50)

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_URL,
    auto_offset_reset='latest',
    enable_auto_commit=True,
    consumer_timeout_ms=TIMEOUT_SEC * 1000,
    max_poll_records=500,
)

uids = set()
count = 0
start = time.time()

try:
    for msg in consumer:
        count += 1
        try:
            data = json.loads(msg.value.decode('utf-8'))
            uid = data.get('uniqueProductIdentificationCode', 'UNKNOWN')
            uids.add(uid)
        except Exception:
            pass

        if count % 100 == 0:
            elapsed = time.time() - start
            print(f"  已接收 {count} 条, 不同UID: {len(uids)}, 耗时: {elapsed:.1f}s")

except KeyboardInterrupt:
    pass
finally:
    consumer.close()

elapsed = time.time() - start
print("-" * 50)
print(f"统计结果:")
print(f"  总消息数: {count}")
print(f"  不同UID数: {len(uids)}")
print(f"  监听时长: {elapsed:.1f} 秒")
if uids:
    print(f"  UID列表 ({len(uids)}个):")
    for u in sorted(uids)[:20]:
        print(f"    {u}")
    if len(uids) > 20:
        print(f"    ... 等共 {len(uids)} 个")
