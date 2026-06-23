import requests
import json
from datetime import datetime, timedelta, timezone
from ha_env import es_hosts

# ==================== 配置区域 ====================
# 直接在 IDE 中修改以下参数后运行

# ---- 时间范围配置（二选一）----
# 方式A：基于当前时间向前查询 N 分钟（推荐）
QUERY_MINUTES = 300        # 向前查询分钟数：5, 60, 300 等

# 方式B：指定固定时间段（如果 START_TIME 和 END_TIME 都有值，则优先使用方式B）
START_TIME = None         # 开始时间，格式 "2026-06-08 10:00:00"
END_TIME = None           # 结束时间，格式 "2026-06-08 11:00:00"

# ---- 其他配置 ----
INDEX_PATTERN = "uav_runtime_data*"   # 索引模式
TIME_FIELD = "timestamp"              # 时间字段名（遥测数据为毫秒级 long 类型）
SLICE_MINUTES = 10                     # 切片粒度（分钟）

# ==================== 以下为脚本逻辑，通常无需修改 ====================

# 从 ha_env.py 导入 ES 地址，拼接为完整 URL
ES_SERVERS = [f"http://{host}" for host in es_hosts]

CONFIG = {
    'minutes': QUERY_MINUTES,
    'start': START_TIME,
    'end': END_TIME,
    'index_pattern': INDEX_PATTERN,
    'time_field': TIME_FIELD,
    'slice_minutes': SLICE_MINUTES,
}


def check_server_reachable(server):
    """检查服务器是否可达"""
    try:
        response = requests.head(server, timeout=5)
        return True
    except Exception as e:
        print(f"服务器 {server} 不可达: {e}")
        return False


def get_count_in_range(server, index_pattern, time_field, start_time, end_time):
    """获取指定时间范围内的文档数量"""
    url = f"{server}/{index_pattern}/_count"
    # 遥测数据 timestamp 字段为毫秒级 long，需转换为毫秒时间戳
    if time_field == "timestamp":
        query = {
            "query": {
                "range": {
                    time_field: {
                        "gte": int(start_time.timestamp() * 1000),
                        "lt": int(end_time.timestamp() * 1000)
                    }
                }
            }
        }
    else:
        query = {
            "query": {
                "range": {
                    time_field: {
                        "gte": start_time.isoformat(),
                        "lt": end_time.isoformat()
                    }
                }
            }
        }
    try:
        response = requests.post(url, json=query, timeout=10)
        if response.status_code == 200:
            return response.json().get("count", 0)
        else:
            print(f"  查询失败: {response.status_code}, {response.text[:200]}")
            return -1
    except Exception as e:
        print(f"  查询异常: {e}")
        return -1


def generate_time_slices(start_time, end_time, slice_minutes=5):
    """生成时间切片列表"""
    slices = []
    current = start_time
    while current < end_time:
        slice_end = min(current + timedelta(minutes=slice_minutes), end_time)
        slices.append((current, slice_end))
        current = slice_end
    return slices


def format_time(dt):
    """格式化时间显示"""
    return dt.strftime("%m-%d %H:%M")


def format_count(count):
    """格式化数量显示"""
    if count == -1:
        return "连接不上"
    return str(count)


def parse_time(time_str):
    """解析时间字符串"""
    if not time_str:
        return None
    # 支持多种格式
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(time_str, fmt)
            # 如果没有时区信息，假设为本地时间
            return dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {time_str}")


def compare_time_slices():
    """主函数：按时间切片对比两个ES集群的数据量"""
    # 读取场景配置
    cfg = CONFIG
    minutes = cfg.get('minutes')
    start_str = cfg.get('start')
    end_str = cfg.get('end')
    index_pattern = cfg.get('index_pattern', "uav_runtime_data*")
    time_field = cfg.get('time_field', "@timestamp")
    slice_minutes = cfg.get('slice_minutes', 5)

    # 计算时间范围
    now = datetime.now().astimezone()

    if start_str and end_str:
        start_time = parse_time(start_str)
        end_time = parse_time(end_str)
    elif start_str:
        start_time = parse_time(start_str)
        end_time = start_time + timedelta(minutes=minutes or 60)
    else:
        end_time = now
        start_time = end_time - timedelta(minutes=minutes or 5)

    if start_time >= end_time:
        print("错误: 开始时间必须早于结束时间")
        return

    # 生成时间切片
    slices = generate_time_slices(start_time, end_time, slice_minutes)

    print("=" * 120)
    print("ES 双集群时间切片数据量对比")
    print("=" * 120)
    print(f"索引模式 : {index_pattern}")
    print(f"时间字段 : {time_field}")
    print(f"时间范围 : {start_time.isoformat()} ~ {end_time.isoformat()}")
    print(f"切片粒度 : {slice_minutes} 分钟")
    print(f"切片数量 : {len(slices)}")
    print(f"ES 节点A : {ES_SERVERS[0]}")
    print(f"ES 节点B : {ES_SERVERS[1]}")
    print("=" * 120)

    # 检查服务器可达性
    reach_a = check_server_reachable(ES_SERVERS[0])
    reach_b = check_server_reachable(ES_SERVERS[1])

    if not reach_a and not reach_b:
        print("两个 ES 服务器均不可达，无法继续")
        return

    print()
    print(f"{'时间切片':<20} {ES_SERVERS[0]:<20} {ES_SERVERS[1]:<20} {'差异':<12} {'状态':<12}")
    print("-" * 120)

    all_match = True
    total_a = 0
    total_b = 0

    for slice_start, slice_end in slices:
        # 查询两个集群
        count_a = get_count_in_range(ES_SERVERS[0], index_pattern, time_field,
                                     slice_start, slice_end) if reach_a else -1
        count_b = get_count_in_range(ES_SERVERS[1], index_pattern, time_field,
                                     slice_start, slice_end) if reach_b else -1

        # 累加总数
        if count_a > 0:
            total_a += count_a
        if count_b > 0:
            total_b += count_b

        # 格式化显示
        time_label = f"{format_time(slice_start)} ~ {format_time(slice_end)}"
        display_a = format_count(count_a)
        display_b = format_count(count_b)

        if count_a == -1 or count_b == -1:
            status = "无法获取"
            diff = "-"
            all_match = False
        elif count_a == count_b:
            status = "一致"
            diff = "0"
        else:
            status = "不一致"
            diff = str(abs(count_a - count_b))
            all_match = False

        print(f"{time_label:<20} {display_a:<20} {display_b:<20} {diff:<12} {status:<12}")

    print("-" * 120)
    print(f"{'总计':<20} {str(total_a):<20} {str(total_b):<20} {str(abs(total_a - total_b)):<12}")
    print("-" * 120)

    if all_match:
        print("结论: 所有时间切片数据量一致")
    else:
        print("结论: 存在时间切片数据量不一致的情况")
    print("=" * 120)


if __name__ == "__main__":
    compare_time_slices()
