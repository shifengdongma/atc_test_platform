# -*- coding: utf-8 -*-
"""KafkaProducerClient.send_bulk 投递状态测试。

背景：flush 超时被静默吞掉，消息滞留 kafka-python 内部缓冲、仅在停止时
close() 一次性补投，导致"停止仿真后下游短暂出现目标"。本测试验证
send_bulk 返回投递状态字典、数字 UID 不崩溃。
"""

from unittest.mock import MagicMock, patch

from kafka.errors import KafkaTimeoutError

from core.kafka_proc import KafkaProducerClient


def _client_with_fake_producer(flush_raises=False):
    """构造 KafkaProducerClient 并替换底层 producer 为 fake。"""
    fake = MagicMock()
    fake.send.return_value = MagicMock()
    if flush_raises:
        fake.flush.side_effect = KafkaTimeoutError("flush timeout")
    with patch("core.kafka_proc.KafkaProducer", return_value=fake):
        client = KafkaProducerClient("fake-broker:9092")
        client.producer = fake
        client.connected = True
        return client, fake


def test_send_bulk_numeric_uid_no_crash():
    """数字 UID 不再触发 key_fn AttributeError，消息 key 被转成字节串。"""
    client, fake = _client_with_fake_producer()
    result = client.send_bulk(
        [{"uniqueProductIdentificationCode": 123456, "longitude": 120.6}],
        "uav_runtime_data",
    )

    assert result["sent"] == 1
    assert result["primary_flush_ok"] is True
    assert fake.send.call_args.args[2] == b"123456"


def test_send_bulk_reports_flush_timeout():
    """主集群 flush 超时时 primary_flush_ok=False，返回字典包含全部状态键。"""
    client, fake = _client_with_fake_producer(flush_raises=True)
    result = client.send_bulk(
        [{"uniqueProductIdentificationCode": "UAV_1"}],
        "uav_runtime_data",
    )

    assert result["primary_flush_ok"] is False
    assert set(result.keys()) == {"sent", "failed", "primary_flush_ok", "mirror_flush_ok"}


def test_send_bulk_empty_batch_returns_zero_status():
    """空批次直接返回零状态，不触碰 producer。"""
    client, fake = _client_with_fake_producer()
    result = client.send_bulk([], "uav_runtime_data")

    assert result == {"sent": 0, "failed": 0, "primary_flush_ok": True, "mirror_flush_ok": True}
    fake.send.assert_not_called()
    fake.flush.assert_not_called()
