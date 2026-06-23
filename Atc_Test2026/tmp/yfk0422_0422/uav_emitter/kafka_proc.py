#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 生产者客户端
基于 kafka-python 库

安装依赖:
    pip install kafka-python
"""

import json
from typing import List, Dict, Any
from kafka import KafkaProducer
from kafka.errors import KafkaError


class KafkaProducerClient:
    """Kafka 生产者客户端"""

    def __init__(self, bootstrap_servers: str):
        """
        初始化 Kafka 生产者

        Args:
            bootstrap_servers: Kafka 服务器地址，如 "10.165.19.227:30123"
        """
        self.bootstrap_servers = bootstrap_servers

        # 解析服务器地址
        servers = [s.strip() for s in bootstrap_servers.split(',')]

        try:
            self.producer = KafkaProducer(
                bootstrap_servers=servers,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                # 连接配置
                request_timeout_ms=30000,
                connections_max_idle_ms=540000,
                # 重试配置
                retries=3,
                retry_backoff_ms=1000,
                # 批量配置
                batch_size=16384,
                linger_ms=100,
                # 确认配置
                acks='all',
            )
            print(f"✅ Kafka 连接成功: {bootstrap_servers}")
        except Exception as e:
            print(f"❌ Kafka 连接失败: {e}")
            raise

    def send(self, topic: str, data: Dict[str, Any], key: str = None) -> bool:
        """
        发送单条消息

        Args:
            topic: Kafka Topic
            data: 消息数据（字典）
            key: 消息键（可选）

        Returns:
            是否发送成功
        """
        try:
            future = self.producer.send(topic, key=key, value=data)
            record_metadata = future.get(timeout=10)
            return True
        except KafkaError as e:
            print(f"❌ 发送失败: {e}")
            return False
        except Exception as e:
            print(f"❌ 发送异常: {e}")
            return False

    def send_bulk(self, records: List[Dict[str, Any]], topic: str) -> int:
        """
        批量发送消息

        Args:
            records: 消息列表
            topic: Kafka Topic

        Returns:
            成功发送的数量
        """
        if not records:
            return 0

        success_count = 0

        try:
            # 批量发送
            futures = []
            for record in records:
                key = record.get('uniqueProductIdentificationCode')
                future = self.producer.send(topic, key=key, value=record)
                futures.append(future)

            # 等待所有发送完成
            for future in futures:
                try:
                    record_metadata = future.get(timeout=10)
                    success_count += 1
                except Exception as e:
                    print(f"❌ 单条发送失败: {e}")

            return success_count

        except Exception as e:
            print(f"❌ 批量发送异常: {e}")
            return success_count

    def flush(self):
        """刷新缓冲区，确保所有消息发送"""
        self.producer.flush()

    def close(self):
        """关闭生产者"""
        try:
            self.producer.flush()
            self.producer.close()
            print("✅ Kafka 连接已关闭")
        except Exception as e:
            print(f"⚠️  关闭异常: {e}")


# 兼容旧版接口
class KafkaConsumerClient:
    """Kafka 消费者客户端（占位）"""
    pass


if __name__ == '__main__':
    # 测试
    print("测试 Kafka 连接...")

    # 修改为你的 Kafka 地址
    KAFKA_URL = "10.165.19.227:30123"
    TOPIC = "uav_runtime_data"

    client = KafkaProducerClient(KAFKA_URL)

    # 测试发送
    test_data = {
        "uniqueProductIdentificationCode": "TEST_UAV",
        "longitude": 120.0,
        "latitude": 31.0,
        "timestamp": 1234567890
    }

    result = client.send(TOPIC, test_data)
    print(f"发送结果: {'成功' if result else '失败'}")

    client.close()
