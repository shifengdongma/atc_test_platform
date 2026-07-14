# -*- coding: utf-8 -*-
"""
检测并停止所有数据注入活动。

检查项:
  1. 孤儿遥测桥接进程 (telemetry_bridge.py)
  2. Redis BIZ_DATA:UAV_TELEMETRY 残留数据
  3. Kafka uav_runtime_data 最新消息

用法:
  python stop_all_injection.py           # 检测 + 交互式停止
  python stop_all_injection.py --force   # 检测 + 自动全部停止
  python stop_all_injection.py --check   # 仅检测，不停止
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from redis_client import RedisClient
from kafka_proc import KafkaConsumerClient, KafkaProducerClient
import env as _env


def list_bridge_processes() -> list[dict]:
    """通过 tasklist 查找所有 telemetry_bridge.py 进程。"""
    results = []
    try:
        out = subprocess.check_output(
            'tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH',
            shell=True, text=True, timeout=10
        )
        for line in out.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.replace('"', "").split(",")
            if len(parts) >= 2:
                pid = parts[1].strip()
                try:
                    cmd_out = subprocess.check_output(
                        f'wmic process where ProcessId={pid} get CommandLine /value',
                        shell=True, text=True, timeout=5
                    )
                    if "telemetry_bridge.py" in cmd_out:
                        results.append({"pid": int(pid), "name": parts[0].strip()})
                except Exception:
                    pass
    except Exception:
        pass
    return results


def check_redis(host: str, port: str, password: str) -> dict:
    """检查 Redis 中是否有遥测残留数据。"""
    try:
        r = RedisClient(host, port, password)
        raw = r.client.get("BIZ_DATA:UAV_TELEMETRY")
        if raw:
            batch = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            if isinstance(batch, list):
                uids = list({m.get("uniqueProductIdentificationCode", "?") for m in batch})
                return {"has_data": True, "count": len(batch), "uids": uids[:10]}
        return {"has_data": False, "count": 0, "uids": []}
    except Exception as e:
        return {"has_data": False, "count": 0, "uids": [], "error": str(e)}


def check_kafka(kafka_url: str) -> dict:
    """检查 Kafka 中是否有最近的遥测消息。"""
    try:
        c = KafkaConsumerClient(
            bootstrap_servers=kafka_url,
            group_id=f"stop_check_{os.getpid()}",
            consume_from_latest_on_start=True,
        )
        c.subscribe(["uav_runtime_data"])
        msgs = c.poll(timeout_ms=3000)
        c.close()
        if msgs:
            uids = []
            for m in msgs:
                try:
                    if isinstance(m, dict):
                        uids.append(m.get("uniqueProductIdentificationCode", "?"))
                except Exception:
                    pass
            return {"has_data": True, "count": len(msgs), "uids": list(set(uids))[:10]}
        return {"has_data": False, "count": 0, "uids": []}
    except Exception as e:
        return {"has_data": False, "count": 0, "uids": [], "error": str(e)}


def kill_bridge_processes(processes: list[dict]) -> int:
    """终止所有桥接进程，返回成功终止数。"""
    killed = 0
    for p in processes:
        try:
            subprocess.run(f"taskkill /PID {p['pid']} /F", shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            killed += 1
            print(f"  已终止 PID {p['pid']}")
        except Exception as e:
            print(f"  终止 PID {p['pid']} 失败: {e}")
    return killed


def clear_redis(host: str, port: str, password: str) -> bool:
    """清除 Redis 遥测缓存 key。"""
    try:
        r = RedisClient(host, port, password)
        r.client.delete("BIZ_DATA:UAV_TELEMETRY")
        return True
    except Exception as e:
        print(f"  清除 Redis key 失败: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="检测并停止所有数据注入活动")
    parser.add_argument("--force", action="store_true", help="自动停止，不询问确认")
    parser.add_argument("--check", action="store_true", help="仅检测，不停止")
    args = parser.parse_args()

    redis_host = getattr(_env, "redis_ip", "localhost")
    redis_port = str(getattr(_env, "redis_port", 6379))
    redis_password = getattr(_env, "redis_password", "")
    kafka_url = getattr(_env, "kafka_url", "localhost:9092")

    print("=" * 60)
    print("  数据注入状态检测")
    print("=" * 60)

    # 1. 检查桥接进程
    print("\n[1] 检查孤儿桥接进程...")
    bridges = list_bridge_processes()
    if bridges:
        print(f"  ⚠️  发现 {len(bridges)} 个 telemetry_bridge.py 进程:")
        for b in bridges:
            print(f"     PID={b['pid']}")
    else:
        print("  ✅ 无残留桥接进程")

    # 2. 检查 Redis
    print("\n[2] 检查 Redis BIZ_DATA:UAV_TELEMETRY...")
    redis_status = check_redis(redis_host, redis_port, redis_password)
    if redis_status["has_data"]:
        print(f"  ⚠️  Redis 中有 {redis_status['count']} 条遥测缓存")
        if redis_status["uids"]:
            print(f"     UIDs: {', '.join(redis_status['uids'][:5])}")
    elif "error" in redis_status:
        print(f"  ❓ Redis 连接失败: {redis_status['error']}")
    else:
        print("  ✅ Redis 遥测缓存为空")

    # 3. 检查 Kafka
    print("\n[3] 检查 Kafka uav_runtime_data...")
    kafka_status = check_kafka(kafka_url)
    if kafka_status["has_data"]:
        print(f"  ⚠️  Kafka 中仍有 {kafka_status['count']} 条新消息在流入")
        if kafka_status["uids"]:
            print(f"     UIDs: {', '.join(kafka_status['uids'][:5])}")
    elif "error" in kafka_status:
        print(f"  ❓ Kafka 连接失败: {kafka_status['error']}")
    else:
        print("  ✅ Kafka 无新消息")

    # 汇总
    has_activity = bool(bridges) or redis_status["has_data"] or kafka_status["has_data"]
    print("\n" + "=" * 60)
    if has_activity:
        print("  ⚠️  仍有数据注入活动")
    else:
        print("  ✅ 无数据注入活动")
    print("=" * 60)

    if args.check or not has_activity:
        return

    # 确认停止
    if not args.force:
        resp = input("\n是否停止所有数据注入? [y/N]: ").strip().lower()
        if resp not in ("y", "yes"):
            print("已取消")
            return

    print("\n停止所有数据注入...")

    # 终止桥接进程
    if bridges:
        print(f"\n  终止 {len(bridges)} 个桥接进程...")
        kill_bridge_processes(bridges)

    # 清除 Redis
    if redis_status["has_data"]:
        print("\n  清除 Redis 遥测缓存...")
        if clear_redis(redis_host, redis_port, redis_password):
            print("  ✅ Redis key 已清除")

    # 最终验证
    print("\n--- 最终状态 ---")
    time.sleep(1)
    remaining = list_bridge_processes()
    redis2 = check_redis(redis_host, redis_port, redis_password)
    if not remaining and not redis2["has_data"]:
        print("✅ 所有数据注入已停止")
    else:
        if remaining:
            print(f"⚠️  仍有 {len(remaining)} 个进程残留，请手动 taskkill /F /PID <pid>")
        if redis2["has_data"]:
            print(f"⚠️  Redis 仍有数据，请手动 redis-cli DEL BIZ_DATA:UAV_TELEMETRY")


if __name__ == "__main__":
    main()
