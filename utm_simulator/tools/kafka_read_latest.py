# -*- coding: utf-8 -*-
"""连接 Kafka，从指定 topic 最新位点起消费 10 秒，将收到的消息写入项目根目录 kafka_latest.json；每 10ms poll 一次，每秒汇总打印拉取条数。"""
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

from kafka import KafkaConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# kafka-python 默认大量 INFO（连接、协调器、分区、offset），只保留 WARNING 及以上
for _name in (
    "kafka",
    "kafka.conn",
    "kafka.client",
    "kafka.cluster",
    "kafka.coordinator",
    "kafka.consumer",
    "kafka.consumer.fetcher",
    "kafka.consumer.subscription_state",
):
    logging.getLogger(_name).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

kafka_url = "10.165.19.213:30011"
kafka_uav_data_topic = 'uav_runtime_data'
DURATION_SEC = 10
# 消费循环中每次 poll 阻塞超时（毫秒），约等于拉取间隔
POLL_INTERVAL_MS = 10
OUTPUT_PATH = os.path.join(_root, "kafka_latest.json")


def _value_deserializer(m: bytes) -> Any:
    if m is None:
        return None
    try:
        return json.loads(m.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return m.decode("utf-8", errors="replace")


def main() -> None:
    group_id = f"kafka_latest_reader_{os.getpid()}_{int(time.time())}"
    logger.info(
        "准备连接 Kafka: bootstrap_servers=%s, topic=%s, group_id=%s",
        kafka_url,
        kafka_uav_data_topic,
        group_id,
    )
    consumer: KafkaConsumer
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=kafka_url,
            group_id=group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=_value_deserializer,
        )
        logger.info("KafkaConsumer 已创建")
    except Exception as e:
        logger.exception("创建 KafkaConsumer 失败: %s", e)
        return

    try:
        consumer.subscribe([kafka_uav_data_topic])
        logger.info("已订阅 topic: %s", kafka_uav_data_topic)
        # 触发分区分配后跳到各分区末尾，只消费之后产生的新消息
        consumer.poll(timeout_ms=4000)
        assigned = consumer.assignment()
        if not assigned:
            logger.warning("未分配到任何分区（broker/topic 异常），后续可能收不到消息")
        else:
            parts = sorted((p.topic, p.partition) for p in assigned)
            consumer.seek_to_end()
            logger.info(
                "分区 %d 个 %s，已 seek 到末尾，开始拉取 %d 秒",
                len(assigned),
                parts,
                DURATION_SEC,
            )

        rows: List[Dict[str, Any]] = []
        consume_start = time.monotonic()
        deadline = consume_start + DURATION_SEC
        per_second: Dict[int, int] = {}
        last_flushed_sec = -1

        def _flush_completed_seconds(now_mono: float) -> None:
            nonlocal last_flushed_sec
            now_sec = int(now_mono - consume_start)
            while last_flushed_sec + 1 < now_sec:
                last_flushed_sec += 1
                c = per_second.pop(last_flushed_sec, 0)
                logger.info("第 %d 秒: 拉取 %d 条", last_flushed_sec + 1, c)

        while time.monotonic() < deadline:
            # 固定短间隔轮询；临近结束时缩短 timeout，避免整体拖长超过 DURATION_SEC
            remaining_ms = (deadline - time.monotonic()) * 1000.0
            timeout_ms = min(POLL_INTERVAL_MS, max(int(remaining_ms), 1))
            for _tp, records in consumer.poll(timeout_ms=timeout_ms).items():
                for rec in records:
                    sec_idx = int(time.monotonic() - consume_start)
                    per_second[sec_idx] = per_second.get(sec_idx, 0) + 1
                    rows.append(
                        {
                            "topic": rec.topic,
                            "partition": rec.partition,
                            "offset": rec.offset,
                            "timestamp": rec.timestamp,
                            "value": rec.value,
                        }
                    )
            _flush_completed_seconds(time.monotonic())

        _flush_completed_seconds(time.monotonic())
        tail = sum(per_second.values())
        if tail:
            logger.info("收尾不足 1 秒: 拉取 %d 条", tail)
        logger.info("拉取结束: %d 条", len(rows))
    except Exception as e:
        logger.exception("Kafka 订阅或消费过程失败: %s", e)
        return
    finally:
        try:
            consumer.close()
            logger.info("KafkaConsumer 已关闭")
        except Exception as e:
            logger.warning("关闭 KafkaConsumer 时异常: %s", e)

    out = {
        "kafka_url": kafka_url,
        "topic": kafka_uav_data_topic,
        "duration_seconds": DURATION_SEC,
        "message_count": len(rows),
        "messages": rows,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    logger.info("已写入 %s，共 %d 条消息", OUTPUT_PATH, len(rows))


if __name__ == "__main__":
    main()
