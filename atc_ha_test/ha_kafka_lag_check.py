# -*- coding: utf-8 -*-
"""
高可用 Kafka Lag 监控脚本（双集群）

功能：
- 查询指定 Topic 的分区数量及分区详情（leader、replicas、ISR）
- 循环查询指定消费组的 Lag（CURRENT-OFFSET / LOG-END-OFFSET / LAG）
- 支持设置 Topic 分区数量（开关控制，默认关闭）

用法示例：
    # 循环查询双集群消费组 lag
    python ha_kafka_lag_check.py --group utm_demo_group --interval 5

    # 查询并设置分区数为 12（仅当 --set-partitions 传入时执行）
    python ha_kafka_lag_check.py --topic uav_runtime_data --set-partitions 12

    # 仅查询 A 集群
    python ha_kafka_lag_check.py --cluster a --group utm_demo_group
"""

import os
import sys
import time
import argparse
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 路径配置 ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))

sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, ENGINE_DIR)

from kafka import KafkaConsumer, TopicPartition
from kafka.admin import KafkaAdminClient, NewPartitions

# 优先从当前目录加载 ha_env
try:
    from ha_env import kafka_url_a, kafka_url_b
except Exception as e:
    print(f"[错误] 无法加载 ha_env.py: {e}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════
# IDE 直接执行配置区（无需命令行参数，修改此处即可在 IDE 运行）
# ═══════════════════════════════════════════════════════════════════
# 开关：设为 True 时，IDE 中直接运行本脚本将使用下方默认参数
IDE_QUICK_RUN = True

# 默认监控配置（IDE 直接执行时生效）
DEFAULT_TOPIC = "uav_runtime_data"          # Kafka topic 名称
DEFAULT_GROUPS = [
    "la-atc-biz-backend",
    "la-atc-ws-backend-atc",
    "utm_conflicts",
    "utm_mid_conflicts_server",
    "utm_server",
]         # 消费组名称列表（查询 lag 时必填，支持多个）
DEFAULT_CLUSTER = "both"                    # 目标集群："a" / "b" / "both"
DEFAULT_INTERVAL = 5                        # 循环查询间隔秒数，0=仅查询一次
DEFAULT_SET_PARTITIONS = None               # 设置分区数量（Kafka 只能增加不能减少），None=不修改分区
DEFAULT_LOG_LEVEL = "info"                  # 日志级别：info=精简，debug=详细（打印分区明细+汇总）
# ═══════════════════════════════════════════════════════════════════


# ── Kafka 分区查询 ──
def query_topic_partitions(bootstrap_servers: str, topic: str) -> Dict[str, Any]:
    """查询 Topic 的分区数量及详情"""
    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
    try:
        metadata = admin.describe_topics([topic])
        if not metadata:
            return {"partitions": 0, "details": []}

        # 兼容不同 kafka-python 版本：可能是对象或 dict
        topic_meta = metadata[0]
        if isinstance(topic_meta, dict):
            partitions = topic_meta.get("partitions", [])
            details = []
            for p in partitions:
                details.append({
                    "partition": p.get("partition"),
                    "leader": p.get("leader"),
                    "replicas": list(p.get("replicas", [])),
                    "isr": list(p.get("isr", [])),
                })
            return {"partitions": len(partitions), "details": details}
        else:
            # 旧版本对象属性访问
            partitions = topic_meta.partitions
            details = []
            for p in partitions:
                details.append({
                    "partition": p.partition,
                    "leader": p.leader,
                    "replicas": list(p.replicas),
                    "isr": list(p.isr),
                })
            return {"partitions": len(partitions), "details": details}
    except Exception as e:
        print(f"[错误] 查询分区失败 [{bootstrap_servers}]: {e}")
        return {"partitions": 0, "details": [], "error": str(e)}
    finally:
        admin.close()


# ── Kafka Lag 查询 ──
def query_consumer_lag(bootstrap_servers: str, topic: str, group_id: str) -> List[Dict[str, Any]]:
    """查询指定消费组对指定 Topic 的 Lag"""
    consumer = KafkaConsumer(bootstrap_servers=bootstrap_servers)
    try:
        partitions = consumer.partitions_for_topic(topic)
        if not partitions:
            print(f"[警告] Topic '{topic}' 在 {bootstrap_servers} 上不存在或无可访问分区")
            return []

        tps = [TopicPartition(topic, p) for p in sorted(partitions)]
        end_offsets = consumer.end_offsets(tps)
    except Exception as e:
        print(f"[错误] 获取 end offsets 失败 [{bootstrap_servers}]: {e}")
        consumer.close()
        return []
    finally:
        consumer.close()

    # 获取消费组 committed offsets
    group_consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
    )
    try:
        group_consumer.subscribe([topic])
        group_consumer.poll(timeout_ms=4000)

        result = []
        total_lag = 0
        for tp in tps:
            committed = group_consumer.committed(tp)
            current_offset = committed if committed is not None else 0
            end_offset = end_offsets.get(tp, 0)
            lag = max(0, end_offset - current_offset)
            total_lag += lag
            result.append({
                "partition": tp.partition,
                "current_offset": current_offset,
                "end_offset": end_offset,
                "lag": lag,
            })

        result.append({
            "partition": "TOTAL",
            "current_offset": "-",
            "end_offset": "-",
            "lag": total_lag,
        })
        return result
    except Exception as e:
        print(f"[错误] 获取 committed offsets 失败 [{bootstrap_servers}]: {e}")
        return []
    finally:
        group_consumer.close()


# ── 批量查询多个消费组 Lag（同一集群只连一次 Kafka）──
def query_lags_for_groups(
    bootstrap_servers: str, topic: str, group_ids: List[str]
) -> Dict[str, List[Dict[str, Any]]]:
    """对同一集群查询多个消费组的 Lag，只建一次基础 consumer 获取 end_offsets"""
    consumer = KafkaConsumer(bootstrap_servers=bootstrap_servers)
    try:
        partitions = consumer.partitions_for_topic(topic)
        if not partitions:
            print(f"[警告] Topic '{topic}' 在 {bootstrap_servers} 上不存在或无可访问分区")
            return {gid: [] for gid in group_ids}

        tps = [TopicPartition(topic, p) for p in sorted(partitions)]
        end_offsets = consumer.end_offsets(tps)
    except Exception as e:
        print(f"[错误] 获取 end offsets 失败 [{bootstrap_servers}]: {e}")
        return {gid: [] for gid in group_ids}
    finally:
        consumer.close()

    results: Dict[str, List[Dict[str, Any]]] = {}
    for group_id in group_ids:
        group_consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,
        )
        try:
            group_consumer.subscribe([topic])
            group_consumer.poll(timeout_ms=4000)

            result = []
            total_lag = 0
            for tp in tps:
                committed = group_consumer.committed(tp)
                current_offset = committed if committed is not None else 0
                end_offset = end_offsets.get(tp, 0)
                lag = max(0, end_offset - current_offset)
                total_lag += lag
                result.append({
                    "partition": tp.partition,
                    "current_offset": current_offset,
                    "end_offset": end_offset,
                    "lag": lag,
                })

            result.append({
                "partition": "TOTAL",
                "current_offset": "-",
                "end_offset": "-",
                "lag": total_lag,
            })
            results[group_id] = result
        except Exception as e:
            print(f"[错误] 获取 committed offsets 失败 [{bootstrap_servers}] group={group_id}: {e}")
            results[group_id] = []
        finally:
            group_consumer.close()

    return results


# ── 设置分区数量 ──
def set_topic_partitions(bootstrap_servers: str, topic: str, new_count: int) -> bool:
    """增加 Topic 分区数量（只能增加不能减少）"""
    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
    try:
        current = query_topic_partitions(bootstrap_servers, topic)
        current_count = current.get("partitions", 0)
        if new_count <= current_count:
            print(f"[跳过] 当前分区数 {current_count} >= 目标 {new_count}，Kafka 不支持减少分区")
            return False

        admin.create_partitions({topic: NewPartitions(total_count=new_count)})
        print(f"[成功] Topic '{topic}' 分区数已从 {current_count} 调整为 {new_count}")
        return True
    except Exception as e:
        print(f"[错误] 设置分区失败 [{bootstrap_servers}]: {e}")
        return False
    finally:
        admin.close()


# ── 打印分区详情 ──
def print_partition_details(cluster_label: str, topic: str, info: Dict[str, Any]):
    print(f"\n[{cluster_label}] Topic: {topic} | Partitions: {info.get('partitions', 0)}")
    details = info.get("details", [])
    if not details:
        print(f"[{cluster_label}] 无分区详情")
        return
    for d in details:
        print(
            f"  Partition {d['partition']:>3} | "
            f"Leader: {d['leader']} | "
            f"Replicas: {d['replicas']} | "
            f"ISR: {d['isr']}"
        )


# ── 打印 Lag 详情 ──
def print_lag_details(cluster_label: str, group_id: str, lag_info: List[Dict[str, Any]], log_level: str = "info"):
    # 提取总 lag
    total_lag = 0
    for item in lag_info:
        if item.get("partition") == "TOTAL":
            total_lag = item.get("lag", 0)
            break

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    info_line = f"{ts}  {cluster_label}  {group_id}  Lag: {total_lag}"

    if log_level == "info":
        print(info_line)
        return

    # debug 模式：打印详细分区信息 + 汇总行
    print(f"\n[{cluster_label}] ConsumerGroup: {group_id}")
    if not lag_info:
        print(f"[{cluster_label}] 无 Lag 数据")
        return
    for item in lag_info:
        p = item["partition"]
        if p == "TOTAL":
            print(f"  {'TOTAL':>11} | Lag: {item['lag']}")
        else:
            print(
                f"  Partition {p:>3} | "
                f"Current: {item['current_offset']:>12} | "
                f"End: {item['end_offset']:>12} | "
                f"Lag: {item['lag']:>8}"
            )
    print(f"[汇总] {info_line}")


# ── 主函数 ──
def main():
    # IDE 快速运行模式：绕过命令行解析，直接使用上方默认参数
    if IDE_QUICK_RUN:
        args = argparse.Namespace(
            topic=DEFAULT_TOPIC,
            group=DEFAULT_GROUPS,
            cluster=DEFAULT_CLUSTER,
            interval=DEFAULT_INTERVAL,
            set_partitions=DEFAULT_SET_PARTITIONS,
            log_level=DEFAULT_LOG_LEVEL,
        )
    else:
        parser = argparse.ArgumentParser(
            description="高可用 Kafka Lag 监控脚本（双集群）",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("--topic", type=str, default=DEFAULT_TOPIC, help=f"指定 Kafka topic（默认: {DEFAULT_TOPIC}）")
        parser.add_argument("--group", type=str, action="append", default=DEFAULT_GROUPS, help=f"指定消费组名称，可多次使用（默认: {DEFAULT_GROUPS}）")
        parser.add_argument("--cluster", type=str, choices=["a", "b", "both"], default=DEFAULT_CLUSTER, help=f"目标集群 a/b/both（默认: {DEFAULT_CLUSTER}）")
        parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help=f"循环查询间隔秒数（默认: {DEFAULT_INTERVAL}，0 表示只查询一次）")
        parser.add_argument("--set-partitions", type=int, default=DEFAULT_SET_PARTITIONS, help="设置 Topic 分区数量（只能增加，默认不修改）")
        parser.add_argument("--log-level", type=str, choices=["info", "debug"], default=DEFAULT_LOG_LEVEL, help=f"日志级别 info/debug（默认: {DEFAULT_LOG_LEVEL}）")
        args = parser.parse_args()

    # 确定目标集群
    clusters = []
    if args.cluster in ("a", "both"):
        clusters.append(("A", kafka_url_a))
    if args.cluster in ("b", "both"):
        clusters.append(("B", kafka_url_b))

    # ── 设置分区（开关控制，一次性执行） ──
    if args.set_partitions is not None:
        print("=" * 70)
        print(f"设置 Topic '{args.topic}' 分区数为 {args.set_partitions}")
        print("=" * 70)
        for label, url in clusters:
            print(f"\n[{label}] 目标: {url}")
            set_topic_partitions(url, args.topic, args.set_partitions)
        return

    # ── 查询分区详情（首次） ──
    print("=" * 70)
    print(f"Kafka Lag 监控启动")
    groups_str = ", ".join(args.group) if isinstance(args.group, list) else str(args.group)
    print(f"Topic: {args.topic} | Groups: {groups_str} | Cluster: {args.cluster}")
    if args.interval > 0:
        print(f"循环间隔: {args.interval}s（按 Ctrl+C 停止）")
    print("=" * 70)

    for label, url in clusters:
        info = query_topic_partitions(url, args.topic)
        print_partition_details(label, args.topic, info)

    # ── 循环查询 Lag ──
    while True:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        groups = args.group if isinstance(args.group, list) else [args.group]

        # 并发查询所有目标集群
        results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        with ThreadPoolExecutor(max_workers=len(clusters)) as executor:
            future_to_label = {
                executor.submit(query_lags_for_groups, url, args.topic, groups): label
                for label, url in clusters
            }
            for future in as_completed(future_to_label):
                label = future_to_label[future]
                try:
                    results[label] = future.result()
                except Exception as e:
                    print(f"[错误] 查询集群 {label} 失败: {e}")
                    results[label] = {}

        # 按固定顺序（A→B）统一输出
        for label, url in clusters:
            lags_map = results.get(label, {})
            if args.log_level == "info":
                parts = []
                for gid in groups:
                    lag_info = lags_map.get(gid, [])
                    total_lag = 0
                    for item in lag_info:
                        if item.get("partition") == "TOTAL":
                            total_lag = item.get("lag", 0)
                            break
                    parts.append(f"{gid} - Lag: {total_lag}")
                print(f"{ts}  {label}  {' | '.join(parts)}")
            else:
                for gid in groups:
                    print_lag_details(label, gid, lags_map.get(gid, []), args.log_level)

        if args.interval <= 0:
            break

        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n\n[中断] 用户停止监控")
            break

    print("\n监控结束")


if __name__ == "__main__":
    main()
