import redis
import json
from ha_env import redis_ip_a, redis_port_a, redis_password_a, redis_ip_b, redis_port_b, redis_password_b

# 从 ha_env.py 导入 Redis 配置
REDIS1_CONFIG = {
    'host': redis_ip_a,
    'port': int(redis_port_a),
    'password': redis_password_a or None,
    'db': 0
}

REDIS2_CONFIG = {
    'host': redis_ip_b,
    'port': int(redis_port_b),
    'password': redis_password_b or None,
    'db': 0
}

# 要检查的key列表及其描述
KEYS_TO_CHECK = {
    'uavAlertParameterConfig::0': '告警管理实时同步',
    'BIZ_DATA:AIRSPACE': '空域管理实时同步',
    'BIZ_DATA:UAV_ROUTE': '飞行任务实时同步',
}

def parse_json(value):
    """尝试将字符串解析为JSON"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value

def get_redis_value(redis_client, key):
    """获取Redis中key的值，支持不同类型的数据结构"""
    try:
        # 先获取key的类型
        key_type = redis_client.type(key).decode('utf-8')
        
        if key_type == 'string':
            value = redis_client.get(key)
            if value:
                value_str = value.decode('utf-8')
                # 尝试解析为JSON
                return parse_json(value_str)
            return None
        elif key_type == 'hash':
            return redis_client.hgetall(key)
        elif key_type == 'list':
            return redis_client.lrange(key, 0, -1)
        elif key_type == 'set':
            return redis_client.smembers(key)
        elif key_type == 'zset':
            return redis_client.zrange(key, 0, -1, withscores=True)
        else:
            return f"Unsupported type: {key_type}"
    except Exception as e:
        return f"Error: {str(e)}"

def get_data_size(value):
    """计算数据大小"""
    if value is None:
        return 0
    elif isinstance(value, str):
        return len(value)
    elif isinstance(value, dict):
        return len(value)
    elif isinstance(value, (list, set)):
        return len(value)
    elif isinstance(value, tuple):
        return len(value)
    else:
        return len(str(value))

def find_string_differences(str1, str2):
    """找出两个字符串的差异"""
    if not isinstance(str1, str) or not isinstance(str2, str):
        return "至少一个值不是字符串类型"
    
    # 找出第一个不同的位置
    min_len = min(len(str1), len(str2))
    for i in range(min_len):
        if str1[i] != str2[i]:
            # 显示差异周围的上下文
            start = max(0, i - 10)
            end = min(max(len(str1), len(str2)), i + 10)
            return f"在位置 {i} 发现差异:\n" \
                   f"Redis 1: ...{str1[start:i]}[{str1[i]}]{str1[i+1:end]}...\n" \
                   f"Redis 2: ...{str2[start:i]}[{str2[i]}]{str2[i+1:end]}..."
    
    # 如果长度不同
    if len(str1) != len(str2):
        return f"字符串长度不同: Redis 1 长度={len(str1)}, Redis 2 长度={len(str2)}"
    
    return "未发现差异"

def find_json_differences(json1, json2):
    """找出两个JSON对象的差异"""
    if not isinstance(json1, dict) or not isinstance(json2, dict):
        return "至少一个值不是JSON对象"
    
    differences = []
    
    # 检查所有键
    all_keys = set(json1.keys()) | set(json2.keys())
    
    for key in all_keys:
        if key not in json1:
            differences.append(f"键 '{key}' 在Redis 1中不存在")
        elif key not in json2:
            differences.append(f"键 '{key}' 在Redis 2中不存在")
        elif json1[key] != json2[key]:
            differences.append(f"键 '{key}' 的值不同: Redis 1 = {json1[key]}, Redis 2 = {json2[key]}")
    
    if not differences:
        return "未发现差异"
    else:
        return "\n".join(differences)


def check_redis_consistency():
    """检查两个Redis实例之间的数据一致性"""
    try:
        # 连接Redis 1
        r1 = redis.Redis(**REDIS1_CONFIG)
        r1.ping()  # 测试连接
        print(f"成功连接到Redis 1: {REDIS1_CONFIG['host']}:{REDIS1_CONFIG['port']}")
        
        # 连接Redis 2
        r2 = redis.Redis(**REDIS2_CONFIG)
        r2.ping()  # 测试连接
        print(f"成功连接到Redis 2: {REDIS2_CONFIG['host']}:{REDIS2_CONFIG['port']}")
        
        # 检查每个key的数据一致性
        inconsistent_keys = []
        not_exist_keys = []
        
        # 输出详细值对比（放在最上面）
        print("\n=== 详细值对比 ===")
        
        for key, description in KEYS_TO_CHECK.items():
            try:
                # 检查key是否存在
                exists1 = r1.exists(key)
                exists2 = r2.exists(key)
                
                if not exists1 and not exists2:
                    # 两个都不存在 → 视为一致
                    print(f"redis 1 {key}：不存在 | redis2 {key}：不存在 | 一致")
                elif not exists1 or not exists2:
                    not_exist_keys.append(key)
                    # 打印详细值对比
                    print(f"redis 1 {key}：{'不存在' if not exists1 else '存在'} | redis2 {key}：{'不存在' if not exists2 else '存在'} | 不一致")
                else:
                    # 获取Redis 1中的值
                    value1 = get_redis_value(r1, key)
                    # 获取Redis 2中的值
                    value2 = get_redis_value(r2, key)
                    
                    # 计算数据量
                    size1 = get_data_size(value1)
                    size2 = get_data_size(value2)
                    
                    if value1 != value2:
                        inconsistent_keys.append(key)
                        # 打印详细值对比
                        print(f"redis 1 {key}：{value1} | redis2 {key}：{value2} | 不一致")
                    else:
                        # 打印详细值对比
                        print(f"redis 1 {key}：{value1} | redis2 {key}：{value2} | 一致")
                    
            except Exception as e:
                print(f"redis 1 {key}：错误 | redis2 {key}：错误 | 错误")
                print(f"  检查Key '{key}' 时出错: {str(e)}")
        
        # 输出表格标题（过程数据）
        print("\n=== 详细检查结果 ===")
        print(f"{'Key':<35} {'描述':<10} {'Redis1数据量':<12} {'Redis2数据量':<12} {'是否一致':<10}")
        print("-" * 90)
        
        for key, description in KEYS_TO_CHECK.items():
            try:
                # 检查key是否存在
                exists1 = r1.exists(key)
                exists2 = r2.exists(key)
                
                if not exists1 and not exists2:
                    print(f"{key:<35} {description:<10} {'不存在':<12} {'不存在':<12} {'一致':<10}")
                elif not exists1 or not exists2:
                    print(f"{key:<35} {description:<10} {'不存在':<12} {'不存在':<12} {'不一致':<10}")
                    print(f"  Redis 1: {'存在' if exists1 else '不存在'}")
                    print(f"  Redis 2: {'存在' if exists2 else '不存在'}")
                else:
                    # 获取Redis 1中的值
                    value1 = get_redis_value(r1, key)
                    # 获取Redis 2中的值
                    value2 = get_redis_value(r2, key)
                    
                    # 计算数据量
                    size1 = get_data_size(value1)
                    size2 = get_data_size(value2)
                    
                    if value1 != value2:
                        print(f"{key:<35} {description:<10} {size1:<12} {size2:<12} {'不一致':<10}")
                        # 显示差异详情
                        if isinstance(value1, dict) and isinstance(value2, dict):
                            # 处理JSON对象
                            diff = find_json_differences(value1, value2)
                            print(f"  差异详情: {diff}")
                        elif isinstance(value1, str) and isinstance(value2, str):
                            # 处理字符串
                            diff = find_string_differences(value1, value2)
                            print(f"  差异详情: {diff}")
                        else:
                            # 处理其他类型
                            print(f"  Redis 1: {value1}")
                            print(f"  Redis 2: {value2}")
                    else:
                        print(f"{key:<35} {description:<10} {size1:<12} {size2:<12} {'一致':<10}")
                    
            except Exception as e:
                print(f"{key:<35} {description:<10} {'错误':<12} {'错误':<12} {'错误':<10}")
                print(f"  检查Key '{key}' 时出错: {str(e)}")
        
        # 输出总结（放在最下面）
        print("\n=== 检查结果 ===")
        print(f"总检查Key数: {len(KEYS_TO_CHECK)}")
        print(f"数据一致的Key数: {len(KEYS_TO_CHECK) - len(inconsistent_keys) - len(not_exist_keys)}")
        print(f"数据不一致的Key数: {len(inconsistent_keys)}")
        print(f"至少在一个Redis实例中不存在的Key数: {len(not_exist_keys)}")
        
        if inconsistent_keys:
            print(f"\n数据不一致的Key: {inconsistent_keys}")
        if not_exist_keys:
            print(f"\n不存在的Key: {not_exist_keys}")
            
    except Exception as e:
        print(f"连接Redis时出错: {str(e)}")
    finally:
        # 关闭连接
        if 'r1' in locals():
            r1.close()
        if 'r2' in locals():
            r2.close()

if __name__ == "__main__":
    print("开始检查Redis数据一致性...")
    check_redis_consistency()
    print("检查完成！")
