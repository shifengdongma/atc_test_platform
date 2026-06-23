# 指定具体时间段查询es数据库总数
import requests
import json
from datetime import datetime


# 配置部分
ES_SERVERS = [
    "http://10.165.32.25:29200",
    "http://10.165.32.24:29200"
]

# 在这里设置要查询的索引名称
INDEX_NAME = "uav_runtime_data_20260401"

# 时间范围配置
# 方式1：使用基准时间 + 时间范围
BASE_TIMESTAMP = 1773763208989  # 基准时间戳
TIME_RANGE_HOURS = 1  # 时间范围（小时）

# 方式2：直接指定起止时间（格式：YYYYMMDD HH:MM:SS）
# 如果设置了起止时间，将优先使用起止时间进行查询
START_TIME_STR = "20260401 11:00:00"  # 开始时间
END_TIME_STR = "20260401 23:59:59"    # 结束时间

# 使用自定义起止时间（设置为True使用方式2，False使用方式1）
USE_CUSTOM_TIME_RANGE = True

def timestamp_to_datetime(timestamp_ms):
    """将毫秒时间戳转换为可读时间"""
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%Y-%m-%d %H:%M:%S')

def datetime_str_to_timestamp(datetime_str):
    """将时间字符串转换为毫秒时间戳"""
    # 支持格式：YYYYMMDD HH:MM:SS
    try:
        dt = datetime.strptime(datetime_str, '%Y%m%d %H:%M:%S')
        timestamp_ms = int(dt.timestamp() * 1000)
        return timestamp_ms
    except ValueError as e:
        print(f"时间格式错误: {datetime_str}, 请使用格式: YYYYMMDD HH:MM:SS")
        return None

def query_count_by_time_range(server, index, start_time, end_time):
    """查询指定时间范围内的数据总数"""
    try:
        url = f"{server}/{index}/_count"
        headers = {"Content-Type": "application/json"}
        
        # 构建时间范围查询
        query = {
            "query": {
                "range": {
                    "timestamp": {
                        "gte": start_time,
                        "lte": end_time
                    }
                }
            }
        }
        
        # 打印查询命令信息
        print(f"\n=== ES查询命令详情 ===")
        print(f"服务器: {server}")
        print(f"URL: {url}")
        print(f"请求方法: POST")
        print(f"请求头: {headers}")
        print(f"请求体:")
        print(json.dumps(query, indent=2, ensure_ascii=False))
        print("=" * 50)
        
        response = requests.post(url, data=json.dumps(query), headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "server": server,
                "count": data.get("count", 0),
                "start_time": start_time,
                "end_time": end_time
            }
        else:
            return {
                "success": False,
                "server": server,
                "error": f"查询失败: {response.status_code}",
                "response": response.text
            }
    except Exception as e:
        return {
            "success": False,
            "server": server,
            "error": f"查询异常: {e}"
        }

def query_total_count(server, index):
    """查询索引中的总数据量"""
    try:
        url = f"{server}/{index}/_count"
        
        # 打印查询命令信息
        print(f"\n=== ES查询命令详情 ===")
        print(f"服务器: {server}")
        print(f"URL: {url}")
        print(f"请求方法: GET")
        print(f"请求体: 无")
        print("=" * 50)
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "server": server,
                "total_count": data.get("count", 0)
            }
        else:
            return {
                "success": False,
                "server": server,
                "error": f"查询失败: {response.status_code}"
            }
    except Exception as e:
        return {
            "success": False,
            "server": server,
            "error": f"查询异常: {e}"
        }

def main():
    """主函数"""
    # 根据配置选择时间范围计算方式
    if USE_CUSTOM_TIME_RANGE:
        # 转换时间字符串为时间戳
        start_time = datetime_str_to_timestamp(START_TIME_STR)
        end_time = datetime_str_to_timestamp(END_TIME_STR)
        
        if start_time is None or end_time is None:
            print("时间转换失败，程序退出")
            return
            
        start_time_str = timestamp_to_datetime(start_time)
        end_time_str = timestamp_to_datetime(end_time)
        
    else:
        # 计算时间范围
        time_range_ms = TIME_RANGE_HOURS * 60 * 60 * 1000  # 转换为毫秒
        start_time = BASE_TIMESTAMP - time_range_ms
        end_time = BASE_TIMESTAMP + time_range_ms
        
        start_time_str = timestamp_to_datetime(start_time)
        end_time_str = timestamp_to_datetime(end_time)
    
    # 查询时间范围内的数据
    results = []
    for server in ES_SERVERS:
        result = query_count_by_time_range(server, INDEX_NAME, start_time, end_time)
        results.append(result)
    
    # 输出结果：ip | 查询起止时间 | 数量
    for result in results:
        if result["success"]:
            # 提取IP地址
            server_url = result["server"]
            ip = server_url.split("//")[1].split(":")[0]
            time_range = f"{start_time_str}~{end_time_str}"
            count = result["count"]
            print(f"{ip} | {time_range} | {count}")
        else:
            # 查询失败的情况
            server_url = result["server"]
            ip = server_url.split("//")[1].split(":")[0]
            time_range = f"{start_time_str}~{end_time_str}"
            print(f"{ip} | {time_range} | 查询失败")

if __name__ == "__main__":
    main()