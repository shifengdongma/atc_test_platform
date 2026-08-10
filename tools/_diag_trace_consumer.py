# -*- coding: utf-8 -*-
"""诊断脚本：直接测试 Kafka trace 消费 (用后即删)"""
import json, sys, os, time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from core.kafka_proc import KafkaConsumerClient, KafkaProducerClient

KAFKA_URL = "10.165.19.213:30011"
TOPIC = "uav_runtime_trace"

print(f"=== Kafka trace 消费诊断 ===")
print(f"Bootstrap: {KAFKA_URL}")
print(f"Topic: {TOPIC}")

# 1. 测试生产者（确认 Kafka 可达）
print("\n1. 测试生产者连接...")
try:
    p = KafkaProducerClient(KAFKA_URL)
    print(f"   生产者: OK (connected={p.is_connected()})")
    p.close()
except Exception as e:
    print(f"   生产者: FAIL - {e}")

# 2. 测试消费者 — 不使用 consume_from_latest_on_start
print("\n2. 测试消费者 (auto_offset_reset='latest', 无 seek_to_end)...")
group_id = f"diag_trace_{os.getpid()}"
print(f"   Group: {group_id}")
try:
    c = KafkaConsumerClient(
        bootstrap_servers=KAFKA_URL,
        group_id=group_id,
        consume_from_latest_on_start=False,
    )
    c.subscribe([TOPIC])
    print(f"   订阅成功: {TOPIC}")

    # 轮询收集消息，最多等 30 秒
    total = 0
    deadline = time.time() + 30
    while time.time() < deadline:
        msgs = c.poll(timeout_ms=2000)
        if msgs:
            total += len(msgs)
            print(f"   收到 {len(msgs)} 条 (累计 {total})")
            for m in msgs[:2]:
                print(f"      sample: keys={list(m.keys())[:5]}")
        else:
            elapsed = int(30 - (deadline - time.time()))
            print(f"   等待中... ({elapsed}s 超时)")

    if total == 0:
        print(f"\n   ❌ 30秒内未收到任何消息！")
        print(f"   可能原因:")
        print(f"   1. topic '{TOPIC}' 在此 Kafka 集群上无新消息")
        print(f"   2. 网络防火墙阻止消费")
        print(f"   3. broker 返回的内部 IP 不可达")
    else:
        print(f"\n   ✅ 共收到 {total} 条消息 — 消费正常")

    c.close()
except Exception as e:
    print(f"   消费者: FAIL - {e}")
    import traceback
    traceback.print_exc()

# 3. 发送一条测试消息到 uav_runtime_data，触发 UTM 产生 trace
print("\n3. 发送测试遥测，触发 UTM 产生 trace...")
try:
    p2 = KafkaProducerClient(KAFKA_URL)
    test_msg = {
        "uniqueProductIdentificationCode": "DIAG_TEST_001",
        "longitude": 120.665, "latitude": 31.315,
        "geodeticAltitude": 100, "speed": 15,
        "trackAngle": 90, "operatingStatus": 2,
        "timestamp": int(time.time() * 1000),
    }
    p2.send_message(TOPIC.replace("trace", "data"), test_msg)
    p2.close()
    print("   测试遥测已发送，等待 UTM 产生 trace (5秒)...")
    time.sleep(5)
except Exception as e:
    print(f"   发送失败: {e}")

# 4. 再次尝试消费 trace
print("\n4. 再次消费 trace...")
group_id2 = f"diag_trace2_{os.getpid()}"
try:
    c2 = KafkaConsumerClient(
        bootstrap_servers=KAFKA_URL,
        group_id=group_id2,
        consume_from_latest_on_start=False,
    )
    c2.subscribe([TOPIC])
    total2 = 0
    deadline2 = time.time() + 15
    while time.time() < deadline2:
        msgs = c2.poll(timeout_ms=2000)
        if msgs:
            total2 += len(msgs)
            print(f"   收到 {len(msgs)} 条 (累计 {total2})")
        else:
            print(f"   等待中...")

    print(f"\n   结果: 收到 {total2} 条 trace 消息")
    c2.close()
except Exception as e:
    print(f"   失败: {e}")
