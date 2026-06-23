# -*- coding: utf-8 -*-
"""
从 Redis 读取所有以 uav_runtime_trace_ 开头的数据并保存到 json/redis_trace.json
"""
import argparse
import json
import os
import sys

import redis

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
from env import redis_ip, redis_password, redis_port

REDIS_KEY_PATTERN = "BIZ_DATA:UAV_ROUTE"
OUTPUT_PATH = "redis_search.json"


def get_redis_client():
    """创建并返回 Redis 客户端"""
    return redis.Redis(
        host=redis_ip,
        port=int(redis_port),
        password=redis_password,
        db=0,
        decode_responses=True,
    )


def _get_value_by_type(client, key):
    """根据键类型从 Redis 读取并解析单个 key 的值，返回 None 表示无数据或不支持类型"""
    key_type = client.type(key)
    if key_type == "string":
        raw = client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    elif key_type == "hash":
        data = client.hgetall(key)
        if not data:
            return None
        parsed = {}
        for k, v in data.items():
            try:
                parsed[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                parsed[k] = v
        return parsed
    elif key_type == "list":
        data = client.lrange(key, 0, -1)
        if not data:
            return None
        parsed = []
        for item in data:
            try:
                parsed.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                parsed.append(item)
        return parsed
    elif key_type == "set":
        data = list(client.smembers(key))
        parsed = []
        for item in data:
            try:
                parsed.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                parsed.append(item)
        return parsed
    elif key_type == "zset":
        data = client.zrange(key, 0, -1, withscores=True)
        if data:
            return [{"value": v, "score": s} for v, s in data]
        return None
    elif key_type == "none":
        return None
    else:
        return None


def fetch_and_save():
    """从 Redis 读取所有 uav_runtime_trace_* 键并写入 JSON 文件"""
    client = get_redis_client()
    try:
        client.ping()
    except Exception as e:
        print(f"Redis 连接失败: {e}")
        return

    keys = list(client.scan_iter(match=REDIS_KEY_PATTERN, count=1000))
    if not keys:
        print(f"未找到匹配 {REDIS_KEY_PATTERN} 的键")
        if os.environ.get("REDIS_TO_JSON_MOCK"):
            _write_mock_file()
        return

    result = {}
    for key in sorted(keys):
        value = _get_value_by_type(client, key)
        if value is not None:
            result[key] = value
        else:
            result[key] = None

    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"已读取 {len(keys)} 个键，写入 {OUTPUT_PATH}")


def list_keys(pattern="*"):
    """列出 Redis 中匹配 pattern 的 key（默认 * 表示全部）"""
    client = get_redis_client()
    try:
        client.ping()
    except Exception as e:
        print(f"Redis 连接失败: {e}")
        return
    keys = list(client.scan_iter(match=pattern, count=1000))
    print(f"共 {len(keys)} 个 key (pattern={pattern!r}):")
    for k in sorted(keys):
        ktype = client.type(k)
        print(f"  {k}  ({ktype})")
    if not keys:
        print("  (无)")


def _write_mock_file():
    """键不存在时写入示例文件，用于验证脚本"""
    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    sample = {"_mock": True, "pattern": REDIS_KEY_PATTERN, "message": "Redis 中暂无匹配键，此为示例文件"}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    print(f"已写入示例文件 {OUTPUT_PATH}（设置 REDIS_TO_JSON_MOCK=1 时）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 Redis 读取所有 uav_runtime_trace_* 键并保存到 JSON")
    parser.add_argument("--mock", action="store_true", help="键不存在时也写入示例 JSON 以验证脚本")
    args = parser.parse_args()
    if args.mock:
        os.environ["REDIS_TO_JSON_MOCK"] = "1"
    fetch_and_save()
