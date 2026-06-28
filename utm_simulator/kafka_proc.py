import json
import time
import traceback
from kafka import KafkaProducer, KafkaConsumer, TopicPartition
from kafka.errors import KafkaTimeoutError
from typing import List, Dict, Any, Optional, Tuple, Callable

# 单次 flush 最大等待，避免副本集群不可达时仿真主线程永久阻塞（trace 消费线程仍会照常打印）
_KAFKA_FLUSH_TIMEOUT_SEC = 1.0
# 显式 close() 时使用；进程退出前须先关闭生产者以解除 kafka-python 注册的 atexit（否则会 timeout=0 flush）
_KAFKA_PRODUCER_CLOSE_TIMEOUT_SEC = 5.0

class KafkaProducerClient:
    """Kafka生产者封装类"""    
    def __init__(
        self,
        bootstrap_servers="10.67.89.106:9092",
        bootstrap_servers_mirror: Optional[str] = None,
        producer_config: Optional[Dict[str, Any]] = None,
        flush_timeout_sec: Optional[float] = None,
    ):
        """初始化Kafka生产者

        bootstrap_servers_mirror:
            若为非空字符串，会额外建一个生产者；向主集群发送的消息会同步发往该集群（flush 后主从均完成排队）。
        flush_timeout_sec:
            覆盖全局默认的 flush 超时（秒），None 则使用全局默认值 _KAFKA_FLUSH_TIMEOUT_SEC。
        """
        self.bootstrap_servers = bootstrap_servers
        mirror = (bootstrap_servers_mirror or "").strip()
        self.bootstrap_servers_mirror = mirror if mirror else None
        self.producer = None
        self.producer_secondary = None
        self.connected = False
        self.producer_config = producer_config or {}
        self.flush_timeout_sec = flush_timeout_sec
        self.connect()
    
    def connect(self):
        """连接Kafka服务器"""  
        try:
            config = {
                'bootstrap_servers': self.bootstrap_servers,
                'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
            }
            # 用用户传入的配置覆盖/扩展默认配置
            config.update(self.producer_config)
            self.producer = KafkaProducer(**config)
            self.connected = True
            print("Kafka生产者初始化成功")
        except Exception as e:
            print(f"Kafka生产者初始化失败: {e}, server url:{self.bootstrap_servers}")
            traceback.print_exc()
            self.connected = False

        self.producer_secondary = None
        if self.connected and self.bootstrap_servers_mirror:
            try:
                self.producer_secondary = KafkaProducer(
                    bootstrap_servers=self.bootstrap_servers_mirror,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                )
                print(f"[Kafka-Mirror] ✅ 高可用集群生产者初始化成功: {self.bootstrap_servers_mirror}")
            except Exception as e:
                print(f"[Kafka-Mirror] ❌ 高可用集群生产者初始化失败: {e}, server url:{self.bootstrap_servers_mirror}")
                traceback.print_exc()
                self.producer_secondary = None
        elif not self.connected:
            print("[Kafka-Mirror] ⚠️ 主集群未连接，跳过高可用集群生产者初始化")
        elif not self.bootstrap_servers_mirror:
            print("[Kafka-Mirror] ⚠️ 未配置高可用集群地址，仅发送主集群")

    def is_connected(self):
        """检查连接状态"""
        return self.connected and self.producer is not None

    def send_bulk(self, objs, topic):
        if not objs:
            return
        if not self.producer:
            print(f"❌ Kafka生产者未初始化，无法发送 {len(objs)} 条消息到 {topic}")
            return
        if self.bootstrap_servers_mirror and not self.producer_secondary:
            print(f"[Kafka-Mirror] ⚠️ 高可用集群生产者未初始化，本次仅发送主集群")
        _flush_to = self.flush_timeout_sec if self.flush_timeout_sec is not None else _KAFKA_FLUSH_TIMEOUT_SEC
        start = time.time()
        key_fn = lambda it: it.get("uniqueProductIdentificationCode").encode('utf-8')
        for item in objs:
            self.producer.send(topic, item, key_fn(item))
            if self.producer_secondary:
                self.producer_secondary.send(topic, item, key_fn(item))
        try:
            self.producer.flush(timeout=_flush_to)
        except KafkaTimeoutError as e:
            print(f"[Kafka-Primary] ❌ 主集群 flush 超时 ({_flush_to}s): {e}")
        if self.producer_secondary:
            try:
                self.producer_secondary.flush(timeout=_flush_to)
            except KafkaTimeoutError as e:
                print(f"[Kafka-Mirror] ❌ 副本集群 flush 超时 ({_flush_to}s): {e}")
        end = time.time()
        suffix = "（同步高可用集群）" if self.producer_secondary else "（仅主集群）"
        print(f"[{topic}]: {int(end)} 发送 {len(objs)} 条{suffix}")

    
    def send_message(self, topic: str, message: Dict[str, Any]) -> bool:
        """发送消息到指定topic"""
        if not self.is_connected():
            print("Kafka未连接，使用模拟模式")
            print(f"模拟发送Kafka消息到 {topic}: {message}")
            return True
        _flush_to = self.flush_timeout_sec if self.flush_timeout_sec is not None else _KAFKA_FLUSH_TIMEOUT_SEC
        try:
            self.producer.send(topic, message)
            if self.producer_secondary:
                self.producer_secondary.send(topic, message)
            try:
                self.producer.flush(timeout=_flush_to)
            except KafkaTimeoutError as e:
                print(f"Kafka 主集群 flush 超时 ({_flush_to}s): {e}")
            if self.producer_secondary:
                try:
                    self.producer_secondary.flush(timeout=_flush_to)
                except KafkaTimeoutError as e:
                    print(f"Kafka 副本集群 flush 超时 ({_flush_to}s): {e}")
            return True
        except Exception as e:
            print(f"Kafka消息发送失败: {e}")
            return False

    # ==================== 批量发送方法 ====================

    def send_batch(
            self,
            topic: str,
            messages: List[Dict[str, Any]],
            batch_size: int = 100,
            callback: Optional[Callable[[Dict, bool], None]] = None
    ) -> Dict[str, Any]:
        """
        批量发送消息到指定topic

        Args:
            topic: 目标topic
            messages: 消息列表
            batch_size: 每批发送数量
            callback: 可选回调函数 (message, success) -> None

        Returns:
            发送统计结果
        """
        if not messages:
            return {'sent': 0, 'failed': 0, 'total': 0}

        if not self.is_connected():
            print(f"⚠️ Kafka未连接，模拟批量发送 {len(messages)} 条消息")
            return {'sent': len(messages), 'failed': 0, 'total': len(messages), 'simulated': True}

        results = {'sent': 0, 'failed': 0, 'total': len(messages), 'batches': 0}
        futures = []

        # 分批次发送
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            batch_futures = []

            for msg in batch:
                try:
                    future = self.producer.send(topic, msg)
                    batch_futures.append((future, msg))
                except Exception as e:
                    results['failed'] += 1
                    if callback:
                        callback(msg, False)
                    print(f"❌ 消息入队失败: {e}")

            # 等待当前批次确认
            if batch_futures:
                results['batches'] += 1
                for future, msg in batch_futures:
                    try:
                        future.get(timeout=10)
                        results['sent'] += 1
                        if callback:
                            callback(msg, True)
                    except Exception as e:
                        results['failed'] += 1
                        if callback:
                            callback(msg, False)
                        print(f"❌ 消息确认失败: {e}")

                if self.producer_secondary:
                    _flush_to = self.flush_timeout_sec if self.flush_timeout_sec is not None else _KAFKA_FLUSH_TIMEOUT_SEC
                    try:
                        for msg in batch:
                            self.producer_secondary.send(topic, msg)
                        self.producer_secondary.flush(timeout=_flush_to)
                    except KafkaTimeoutError as e:
                        print(f"❌ 副本集群 flush 超时 ({_flush_to}s): {e}")
                    except Exception as e:
                        print(f"❌ 副本集群批量发送失败: {e}")

            # 进度提示
            if (i // batch_size + 1) % 10 == 0:
                print(f"� 已发送批次: {i // batch_size + 1}/{(len(messages) + batch_size - 1) // batch_size}")

        print(f"✅ 批量发送完成: {results['sent']}/{results['total']} 成功")
        return results
    
    def close(self) -> None:
        """关闭生产者；调用后 kafka-python 会 unregister atexit，避免进程末尾用 timeout=0 flush 报错。"""
        if self.producer:
            try:
                self.producer.close(timeout=_KAFKA_PRODUCER_CLOSE_TIMEOUT_SEC)
                print("Kafka生产者已关闭")
            except Exception as e:
                print(f"关闭Kafka生产者失败: {e}")
        if self.producer_secondary:
            try:
                self.producer_secondary.close(timeout=_KAFKA_PRODUCER_CLOSE_TIMEOUT_SEC)
                print("Kafka生产者（高可用集群）已关闭")
            except Exception as e:
                print(f"关闭Kafka生产者（高可用集群）失败: {e}")
        self.producer = None
        self.producer_secondary = None
        self.connected = False


class KafkaConsumerClient:
    """Kafka消费者封装类"""

    def __init__(
        self,
        bootstrap_servers="10.67.89.106:9092",
        group_id="utm_demo_group",
        consume_from_latest_on_start: bool = False,
    ):
        """
        初始化Kafka消费者。

        Args:
            bootstrap_servers: Broker 地址。
            group_id: 消费者组 ID。
            consume_from_latest_on_start: 若为 True，订阅后会将各分区消费位点置为最新（seek_to_end），
                跳过历史积压，只消费连接之后产生的新消息。适用于历史消息很多、只关心新消息的场景。
        """
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.consume_from_latest_on_start = consume_from_latest_on_start
        self.consumer = None
        self.connected = False
        self.connect()

    def connect(self):
        """连接Kafka服务器"""
        try:
            self.consumer = KafkaConsumer(
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset='latest',
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            self.connected = True
            print("Kafka消费者初始化成功")
        except Exception as e:
            print(f"Kafka消费者初始化失败: {e}, server url:{self.bootstrap_servers}")
            self.connected = False

    def is_connected(self):
        """检查连接状态"""
        return self.connected and self.consumer is not None

    def subscribe(self, topics: List[str]) -> None:
        """订阅 topic。若创建时设置了 consume_from_latest_on_start=True，会在首次拉取前将位点置为最新，跳过历史消息。"""
        if not self.is_connected():
            print("Kafka未连接，使用模拟模式")
            return

        try:
            self.consumer.subscribe(topics)
            print(f"已订阅Kafka topic: {topics}")
            if self.consume_from_latest_on_start:
                # 触发分区分配（subscribe 后需 poll 才会完成 rebalance）
                self.consumer.poll(timeout_ms=4000)
                if self.consumer.assignment():
                    self.consumer.seek_to_end()
                    print("已将消费位点置为各分区最新，跳过历史积压消息，仅消费之后的新消息")
        except Exception as e:
            print(f"订阅Kafka topic失败: {e}")
    
    def poll(self, timeout_ms: int = 1000) -> List[Dict[str, Any]]:
        """拉取消息"""
        if not self.is_connected():
            print("Kafka未连接，使用模拟模式")
            return []
        
        try:
            messages = []
            for message in self.consumer.poll(timeout_ms=timeout_ms).values():
                for record in message:
                    messages.append(record.value)
            return messages
        except Exception as e:
            print(f"拉取Kafka消息失败: {e}")
            return []
    
    def close(self) -> None:
        """关闭 Kafka 消费者。进程退出阶段内部引用可能已半销毁，勿将常见收尾异常打日志。"""
        c = self.consumer
        if c is None:
            return
        self.consumer = None
        self.connected = False
        try:
            c.close()
            print("Kafka消费者已关闭")
        except (AttributeError, TypeError, RuntimeError) as e:
            msg = str(e)
            if "_lock" in msg or "NoneType" in msg or "callable" in msg:
                return
            print(f"关闭Kafka消费者失败: {e}")
        except Exception as e:
            print(f"关闭Kafka消费者失败: {e}")

