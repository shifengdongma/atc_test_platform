#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 客户端封装
支持 kafka-python 和 confluent-kafka 两种客户端切换
"""

import json
import threading
import time
from typing import List, Dict, Any

# ==================== kafka-python 客户端 ====================

try:
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import KafkaError
    HAS_KAFKA_PYTHON = True
except ImportError:
    HAS_KAFKA_PYTHON = False


class KafkaPythonProducer:
    """基于 kafka-python 的 Kafka 生产者"""

    def __init__(self, bootstrap_servers: str = "localhost:9092", verbose: bool = True):
        self.bootstrap_servers = bootstrap_servers
        self.verbose = verbose
        self.producer = None
        self.connected = False
        self.success_count = 0
        self.failed_count = 0
        self._stats_lock = threading.Lock()
        self.connect()

    def connect(self):
        if not HAS_KAFKA_PYTHON:
            self.connected = False
            return
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
                linger_ms=50,
                batch_size=32768,
                compression_type='gzip',
                acks=1,
                retries=3,
                max_in_flight_requests_per_connection=5
            )
            self.connected = True
            print("Kafka 生产者初始化成功 (kafka-python)")
        except Exception as e:
            print(f"Kafka 生产者初始化失败: {e}")
            self.connected = False

    def is_connected(self):
        return self.connected and self.producer is not None

    def _on_send_success(self, record_metadata):
        with self._stats_lock:
            self.success_count += 1

    def _on_send_error(self, excp):
        with self._stats_lock:
            self.failed_count += 1

    def send_bulk(self, objs: List[Dict], topic: str):
        if not objs or not self.producer:
            return
        start = time.time()
        for item in objs:
            future = self.producer.send(topic, item)
            future.add_callback(self._on_send_success)
            future.add_errback(self._on_send_error)
        end = time.time()
        if self.verbose:
            print(f"[{topic}]: {int(end)} 发送 {len(objs)} 条, 耗时{(end-start)*1000:.1f}ms")

    def poll(self, timeout: float = 0):
        pass

    def get_and_reset_stats(self) -> Dict[str, int]:
        with self._stats_lock:
            stats = {
                'success': self.success_count,
                'failed': self.failed_count,
                'total': self.success_count + self.failed_count
            }
            self.success_count = 0
            self.failed_count = 0
            return stats

    def flush(self):
        if self.producer:
            self.producer.flush()

    def close(self):
        if self.producer:
            self.producer.flush()
            self.producer.close()
            print("Kafka 生产者已关闭 (kafka-python)")


class KafkaPythonConsumer:
    """基于 kafka-python 的 Kafka 消费者"""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        group_id: str = "uav_group",
        consume_from_latest_on_start: bool = False,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.consume_from_latest_on_start = consume_from_latest_on_start
        self.consumer = None
        self.connected = False
        self.connect()

    def connect(self):
        if not HAS_KAFKA_PYTHON:
            self.connected = False
            return
        try:
            self.consumer = KafkaConsumer(
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            self.connected = True
            print("Kafka 消费者初始化成功 (kafka-python)")
        except Exception as e:
            print(f"Kafka 消费者初始化失败: {e}")
            self.connected = False

    def is_connected(self):
        return self.connected and self.consumer is not None

    def subscribe(self, topics: List[str]):
        if not self.is_connected():
            return
        try:
            self.consumer.subscribe(topics)
            print(f"已订阅 Kafka topic: {topics}")
            if self.consume_from_latest_on_start:
                self.consumer.poll(timeout_ms=4000)
                if self.consumer.assignment():
                    self.consumer.seek_to_end()
                    print("已将消费位点置为最新")
        except Exception as e:
            print(f"订阅 Kafka topic 失败: {e}")

    def poll(self, timeout_ms: int = 1000) -> List[Dict[str, Any]]:
        if not self.is_connected():
            return []
        try:
            messages = []
            for message in self.consumer.poll(timeout_ms=timeout_ms).values():
                for record in message:
                    messages.append(record.value)
            return messages
        except Exception as e:
            print(f"拉取 Kafka 消息失败: {e}")
            return []

    def close(self):
        if self.consumer:
            try:
                self.consumer.close()
                print("Kafka 消费者已关闭 (kafka-python)")
            except Exception as e:
                print(f"关闭 Kafka 消费者失败: {e}")


# ==================== confluent-kafka 客户端 ====================

try:
    from confluent_kafka import Producer
    HAS_CONFLUENT = True
except ImportError:
    HAS_CONFLUENT = False


class ConfluentProducer:
    """基于 confluent-kafka (librdkafka) 的 Kafka 生产者"""

    def __init__(self, bootstrap_servers: str = "localhost:9092", verbose: bool = True):
        self.bootstrap_servers = bootstrap_servers
        self.verbose = verbose
        self.producer = None
        self.connected = False
        self.success_count = 0
        self.failed_count = 0
        self._stats_lock = threading.Lock()
        self.connect()

    def connect(self):
        if not HAS_CONFLUENT:
            self.connected = False
            return
        try:
            conf = {
                'bootstrap.servers': self.bootstrap_servers,
                'compression.type': 'gzip',
                'batch.num.messages': 1000,
                'linger.ms': 50,
                'acks': 1,
                'retries': 3,
                'max.in.flight.requests.per.connection': 5,
                'queue.buffering.max.messages': 100000,
                'queue.buffering.max.kbytes': 32768,
            }
            self.producer = Producer(conf)
            self.connected = True
            print("Kafka 生产者初始化成功 (confluent-kafka / librdkafka)")
        except Exception as e:
            print(f"Kafka 生产者初始化失败: {e}")
            self.connected = False

    def is_connected(self):
        return self.connected and self.producer is not None

    def _on_delivery(self, err, msg):
        if err:
            with self._stats_lock:
                self.failed_count += 1
            if self.verbose:
                print(f"消息发送失败: {err}")
        else:
            with self._stats_lock:
                self.success_count += 1

    def send_bulk(self, objs: List[Dict], topic: str):
        if not objs or not self.producer:
            return
        start = time.time()
        for item in objs:
            try:
                self.producer.produce(
                    topic,
                    json.dumps(item, ensure_ascii=False).encode('utf-8'),
                    callback=self._on_delivery
                )
            except BufferError:
                self.producer.poll(0.1)
                try:
                    self.producer.produce(
                        topic,
                        json.dumps(item, ensure_ascii=False).encode('utf-8'),
                        callback=self._on_delivery
                    )
                except Exception:
                    with self._stats_lock:
                        self.failed_count += 1
            except Exception:
                with self._stats_lock:
                    self.failed_count += 1
        self.producer.poll(0)
        end = time.time()
        if self.verbose:
            print(f"[{topic}]: {int(end)} 发送 {len(objs)} 条, 耗时{(end-start)*1000:.1f}ms")

    def poll(self, timeout: float = 0):
        if self.producer:
            self.producer.poll(timeout)

    def get_and_reset_stats(self) -> Dict[str, int]:
        with self._stats_lock:
            stats = {
                'success': self.success_count,
                'failed': self.failed_count,
                'total': self.success_count + self.failed_count
            }
            self.success_count = 0
            self.failed_count = 0
            return stats

    def flush(self):
        if self.producer:
            self.producer.flush()

    def close(self):
        if self.producer:
            self.producer.flush()
            self.producer = None
            print("Kafka 生产者已关闭 (confluent-kafka)")


# ==================== 统一工厂方法 ====================

def create_kafka_producer(bootstrap_servers: str, client_type: str = "kafka-python", verbose: bool = True):
    """
    创建 Kafka 生产者

    Args:
        bootstrap_servers: Kafka 地址
        client_type: "kafka-python" 或 "confluent"
        verbose: 是否打印详细日志
    """
    if client_type == "confluent":
        if not HAS_CONFLUENT:
            print("警告: confluent-kafka 未安装，回退到 kafka-python")
            print("安装命令: pip install confluent-kafka")
            return KafkaPythonProducer(bootstrap_servers, verbose)
        return ConfluentProducer(bootstrap_servers, verbose)
    else:
        if not HAS_KAFKA_PYTHON:
            raise ImportError("kafka-python 未安装，请执行: pip install kafka-python")
        return KafkaPythonProducer(bootstrap_servers, verbose)


def create_kafka_consumer(bootstrap_servers: str, group_id: str, consume_from_latest_on_start: bool = False):
    """
    创建 Kafka 消费者（仅支持 kafka-python）

    Args:
        bootstrap_servers: Kafka 地址
        group_id: 消费者组 ID
        consume_from_latest_on_start: 是否从最新位置开始消费
    """
    return KafkaPythonConsumer(bootstrap_servers, group_id, consume_from_latest_on_start)
