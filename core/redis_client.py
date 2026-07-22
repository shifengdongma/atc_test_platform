import json
import redis

try:
    from common.log_setup import debug_print, error_print
except ImportError:
    def debug_print(prefix, message): pass
    def error_print(prefix, message): print(f"[{prefix}] ❌ {message}")

class RedisClient:
    """Redis客户端封装类"""
    
    def __init__(self, host="10.67.89.106", port=16379, password=None, db=0):
        """初始化Redis客户端"""
        self.host = host
        self.port = port
        self.db = db
        if password == '':
            self.password = None
        else:
            self.password = password
        self.client = None
        self.connected = False
        self.connect()
    
    def connect(self):
        """连接Redis服务器"""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True
            )
            # 测试连接
            self.client.ping()
            self.connected = True
            print("Redis连接成功")
        except Exception as e:
            print(f"Redis连接失败: {e}, host={self.host}, port={self.port}")
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
    
    # def set_with_expire(self, key: str, value: str, expire_seconds: int) -> bool:
    #     """设置键值对，带过期时间"""
    #     if not self.is_connected():
    #         print("Redis未连接")
    #         return True
        
    #     try:
    #         self.client.setex(key, expire_seconds, value)
    #         print(f"Redis SETEX成功: {key}")
    #         return True
    #     except Exception as e:
    #         print(f"Redis SETEX失败: {e}")
    #         return False
        
    def set_with_expire(self, key: str, expire_seconds: int) -> bool:
        """设置键值对，带过期时间"""
        if not self.is_connected():
            print("Redis未连接")
            return True
        
        try:
            self.client.expire(key, expire_seconds)
            # print(f"Redis SETEX成功: {key}")
            return True
        except Exception as e:
            print(f"Redis expire失败: {e}")
            return False
    
    def sadd(self, key: str, value: str) -> bool:
        """向集合中添加元素"""
        if not self.is_connected():
            print("Redis未连接")
            return True
        
        try:
            self.client.sadd(key, value)
            debug_print("Redis", f"SADD成功: {key}")
            return True
        except Exception as e:
            error_print("Redis", f"SADD失败: {e}")
            return False
    
    def get(self, key: str) -> str:
        """获取字符串值"""
        if not self.is_connected():
            print("Redis未连接")
            return ""
        
        try:
            value = self.client.get(key)
            return value if value else ""
        except Exception as e:
            print(f"Redis GET失败: {e}")
            return ""
    
    def hget(self, key: str, field: str) -> str:
        """从哈希表获取值"""
        if not self.is_connected():
            print("Redis未连接")
            return ""
        
        try:
            value = self.client.hget(key, field)
            return value if value else ""
        except Exception as e:
            print(f"Redis HGET失败: {e}")
            return ""
        
    def hset(self, key: str, field: str, value: str) -> bool:
        """向哈希表中设置字段值。查询时用 HGET key field，例如: HGET BIZ_DATA:UAV_ROUTE UAV_00001"""
        if not self.is_connected():
            print("Redis未连接")
            return False
        
        try:
            self.client.hset(key, field, value)
            debug_print("Redis", f"HSET成功: {key}:{field}")
            return True
        except Exception as e:
            error_print("Redis", f"HSET失败: {e}")
            return False
    
    def hgetall(self, key: str):
        """获取哈希表中所有字段和值"""
        if not self.is_connected():
            print("Redis未连接")
            return {}
        
        try:
            value = self.client.hgetall(key)
            return value if value else {}
        except Exception as e:
            print(f"Redis HGETALL失败: {e}")
            return {}

    def hkeys(self, key: str):
        if not self.is_connected():
            print("Redis未连接")
            return {}
        
        try:
            all_ids = self.client.hkeys(key)
            return all_ids
        except Exception as e:
            print(f"Redis hkeys失败: {e}")
            return []

    def get_value_by_key(self, key: str):
        """根据键类型从 Redis 读取并解析单个 key 的值，返回 None 表示无数据或不支持类型"""
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
            elif key_type == "set":
                data = list(self.client.smembers(key))
                parsed = []
                for item in data:
                    try:
                        parsed.append(json.loads(item))
                    except (json.JSONDecodeError, TypeError):
                        parsed.append(item)
                return parsed
            elif key_type == "zset":
                data = self.client.zrange(key, 0, -1, withscores=True)
                if data:
                    return [{"value": v, "score": s} for v, s in data]
                return None
            elif key_type == "none":
                return None
            return None
        except Exception as e:
            print(f"Redis get_value_by_key 失败 key={key}: {e}")
            return None