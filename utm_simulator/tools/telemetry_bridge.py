# -*- coding: utf-8 -*-
"""
遥测桥接子进程 — 将 dynamic 模式 Redis 遥测转发到 Kafka。

运行在独立子进程中，与 Simulator (ctypes) 主进程完全隔离，
避免 Windows 上 kafka-python (librdkafka) 与 ctypes 堆污染导致的 C-level 崩溃。

父进程退出时通过 _watch_parent 线程自动终止，避免残留孤儿进程。

用法:
    python telemetry_bridge.py \
        --redis-host 10.0.0.1 --redis-port 6379 --redis-password xxx \
        --kafka-url 10.0.0.1:9092 [--kafka-mirror-url 10.0.0.2:9092]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import threading
import time
import traceback

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from redis_client import RedisClient
from kafka_proc import KafkaProducerClient

REDIS_TELEMETRY_KEY = "BIZ_DATA:UAV_TELEMETRY"
KAFKA_UAV_DATA_TOPIC = "uav_runtime_data"
POLL_INTERVAL_SEC = 0.8

# 全局退出标志，由父进程监控线程设置
_exit_event = threading.Event()


def _watch_parent() -> None:
    """监控父进程存活状态，父进程退出时设置退出标志。

    使用 Windows WaitForSingleObject 监听父进程句柄，
    父进程终止时 WaitForSingleObject 返回 WAIT_OBJECT_0 (0)。
    """
    ppid = os.getppid()
    if ppid <= 1:  # 没有有效父进程（可能已被 init 收养）
        _exit_event.set()
        return

    SYNCHRONIZE = 0x00100000
    WAIT_OBJECT_0 = 0x00000000
    _kernel32 = ctypes.windll.kernel32

    while not _exit_event.is_set():
        try:
            handle = _kernel32.OpenProcess(SYNCHRONIZE, False, ppid)
            if not handle:
                # 无法打开 — 父进程已退出
                _exit_event.set()
                return
            # 等待父进程终止，3 秒超时后重新检查
            ret = _kernel32.WaitForSingleObject(handle, 1000)
            _kernel32.CloseHandle(handle)
            if ret == WAIT_OBJECT_0:
                _exit_event.set()
                return
        except Exception:
            time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="dynamic 模式 Redis → Kafka 遥测桥接")
    parser.add_argument("--redis-host", required=True)
    parser.add_argument("--redis-port", type=int, required=True)
    parser.add_argument("--redis-password", required=True)
    parser.add_argument("--kafka-url", required=True)
    parser.add_argument("--kafka-mirror-url", default="")
    args = parser.parse_args()

    # ── 启动父进程监控线程 ──────────────────────────────────────────
    threading.Thread(target=_watch_parent, daemon=True, name="parent-watch").start()

    # ── 初始化 Redis / Kafka ──────────────────────────────────────
    print(f"[遥测桥接] 启动中... ppid={os.getppid()} Redis={args.redis_host}:{args.redis_port} Kafka={args.kafka_url}", flush=True)
    try:
        redis_client = RedisClient(args.redis_host, str(args.redis_port), args.redis_password)
        _ = redis_client.client.ping()
        print("[遥测桥接] Redis 连接成功", flush=True)
    except Exception as e:
        print(f"[遥测桥接] Redis 连接失败: {e}", flush=True)
        sys.exit(1)

    try:
        kafka_producer = KafkaProducerClient(
            args.kafka_url,
            bootstrap_servers_mirror=args.kafka_mirror_url or None,
        )
        print("[遥测桥接] Kafka 生产者创建成功", flush=True)
    except Exception as e:
        print(f"[遥测桥接] Kafka 生产者创建失败: {e}", flush=True)
        sys.exit(1)

    sent_total = 0
    empty_count = 0
    tick = 0

    print("[遥测桥接] 开始轮询 Redis...", flush=True)

    while not _exit_event.is_set():
        try:
            raw = redis_client.client.get(REDIS_TELEMETRY_KEY)
            if raw:
                batch = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                if isinstance(batch, list) and batch:
                    uids = [m.get("uniqueProductIdentificationCode", "?") for m in batch[:5]]
                    uid_str = ", ".join(uids)
                    if len(batch) > 5:
                        uid_str += f" ... +{len(batch)-5}"
                    kafka_producer.send_bulk(batch, KAFKA_UAV_DATA_TOPIC)
                    sent_total += len(batch)
                    if tick % 10 == 0:
                        print(f"[遥测桥接] #{tick} 转发 {len(batch)} 条 → Kafka (累计{sent_total}) UIDs: {uid_str}", flush=True)
                redis_client.client.delete(REDIS_TELEMETRY_KEY)
                empty_count = 0
            else:
                empty_count += 1
                if empty_count == 1:
                    print(f"[遥测桥接] #{tick} Redis key 为空，等待 SimulationManager 写入...", flush=True)
                elif empty_count % 150 == 0:
                    print(f"[遥测桥接] #{tick} 已等待 {empty_count} 轮 (~{int(empty_count*POLL_INTERVAL_SEC)}s)，Redis 仍为空", flush=True)
        except Exception:
            print(f"[遥测桥接] #{tick} 异常:\n{traceback.format_exc()}", flush=True)

        tick += 1
        _exit_event.wait(timeout=POLL_INTERVAL_SEC)

    # ── 退出 ───────────────────────────────────────────────────────
    print(f"[遥测桥接] 父进程已退出，桥接终止 (累计转发 {sent_total} 条)", flush=True)
    try:
        kafka_producer.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
