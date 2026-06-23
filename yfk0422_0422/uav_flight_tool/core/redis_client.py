#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis 客户端封装
"""

import json
import redis


class RedisClient:
    """Redis 客户端封装类"""

    def __init__(self, host: str = "127.0.0.1", port: int = 6379, password: str = None, db: int = 0):
        self.host = host
        self.port = port
        self.db = db
        if password == '' or password is None:
            self.password = None
        else:
            self.password = password
        self.client = None
        self.connected = False
        self.connect()

    def connect(self):
        """连接 Redis 服务器"""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True
            )
            self.client.ping()
            self.connected = True
            print("Redis 连接成功")
        except Exception as e:
            print(f"Redis 连接失败: {e}, host={self.host}, port={self.port}")
            self.connected = False

    def is_connected(self):
        """检查连接状态"""
        try:
            if self.client:
                self.client.ping()
                return True
        except:
            pass
        return False

    def hset(self, key: str, field: str, value: str) -> bool:
        """向哈希表中设置字段值"""
        if not self.is_connected():
            print("Redis 未连接")
            return False
        try:
            self.client.hset(key, field, value)
            return True
        except Exception as e:
            print(f"Redis HSET 失败: {e}")
            return False

    def hget(self, key: str, field: str) -> str:
        """从哈希表获取值"""
        if not self.is_connected():
            return ""
        try:
            value = self.client.hget(key, field)
            return value if value else ""
        except Exception as e:
            print(f"Redis HGET 失败: {e}")
            return ""

    def hgetall(self, key: str):
        """获取哈希表中所有字段和值"""
        if not self.is_connected():
            return {}
        try:
            return self.client.hgetall(key) or {}
        except Exception as e:
            print(f"Redis HGETALL 失败: {e}")
            return {}

    def get(self, key: str) -> str:
        """获取字符串值"""
        if not self.is_connected():
            return ""
        try:
            value = self.client.get(key)
            return value if value else ""
        except Exception as e:
            print(f"Redis GET 失败: {e}")
            return ""

    def get_value_by_key(self, key: str):
        """根据键类型从 Redis 读取并解析单个 key 的值"""
        if not self.is_connected():
            return None
        try:
            key_type = self.client.type(key)
            if key_type == "string":
                raw = self.client.get(key)
                if raw is None:
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
            elif key_type == "hash":
                data = self.client.hgetall(key)
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
                data = self.client.lrange(key, 0, -1)
                if not data:
                    return None
                parsed = []
                for item in data:
                    try:
                        parsed.append(json.loads(item))
                    except (json.JSONDecodeError, TypeError):
                        parsed.append(item)
                return parsed
            elif key_type == "none":
                return None
            return None
        except Exception as e:
            print(f"Redis get_value_by_key 失败 key={key}: {e}")
            return None

    def expire(self, key: str, expire_seconds: int) -> bool:
        """设置过期时间"""
        if not self.is_connected():
            return False
        try:
            self.client.expire(key, expire_seconds)
            return True
        except Exception as e:
            print(f"Redis expire 失败: {e}")
            return False

    def close(self):
        """关闭连接"""
        if self.client:
            try:
                self.client.close()
                print("Redis 连接已关闭")
            except Exception as e:
                print(f"关闭 Redis 失败: {e}")
