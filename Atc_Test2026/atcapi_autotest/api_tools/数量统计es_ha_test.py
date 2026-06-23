import requests
import json

# 配置部分
ES_SERVERS = [
    "http://10.165.32.24:29200",
    "http://10.165.32.25:29200"
]

# 在这里设置要对比的索引名称
INDEXES = [
    "uav_runtime_data_20260408",
    "uav_runtime_data_20260409",
    "uav_runtime_data_20260410",
    "uav_runtime_data_20260411",
    "uav_runtime_data_20260412",
    "uav_runtime_data_20260413",
    "uav_runtime_data_20260414",
    "uav_runtime_data_20260415",
    "uav_runtime_data_20260416"
]

def check_server_reachable(server):
    """检查服务器是否可达"""
    try:
        # 发送一个简单的HEAD请求来检查服务器是否可达
        response = requests.head(server, timeout=5)
        return True
    except Exception as e:
        print(f"服务器 {server} 不可达: {e}")
        return False

def get_index_count(server, index, server_reachable):
    """获取指定索引的文档数量"""
    if not server_reachable:
        return -1
    
    try:
        url = f"{server}/{index}/_count"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("count", 0)
        elif response.status_code == 404:
            return 0  # 索引不存在
        else:
            print(f"Error getting count for {index} on {server}: {response.status_code}")
            return -1
    except Exception as e:
        print(f"Exception getting count for {index} on {server}: {e}")
        return -1

def format_count(count):
    """格式化数量显示"""
    if count == -1:
        return "连接不上"
    return str(count)

def compare_indexes():
    """对比两个ES服务器上的索引数据量"""
    print("=== ES索引数据量对比 ===")
    print(f"对比服务器: {ES_SERVERS[0]} vs {ES_SERVERS[1]}")
    print("-" * 120)
    
    # 检查服务器可达性
    server_reachability = {}
    for server in ES_SERVERS:
        server_reachability[server] = check_server_reachable(server)
    
    # 打印表头
    print(f"{'索引名称':<30} {ES_SERVERS[0]:<30} {ES_SERVERS[1]:<30} {'差异':<10} {'状态':<10}")
    print("-" * 120)
    
    all_match = True
    
    for index in INDEXES:
        count1 = get_index_count(ES_SERVERS[0], index, server_reachability[ES_SERVERS[0]])
        count2 = get_index_count(ES_SERVERS[1], index, server_reachability[ES_SERVERS[1]])
        
        # 格式化显示值
        display_count1 = format_count(count1)
        display_count2 = format_count(count2)
        
        if count1 == -1 or count2 == -1:
            status = "无法获取数据"
            diff = "-"
            all_match = False
        elif count1 == count2:
            status = "数据量一致"
            diff = 0
        else:
            status = "数据量不一致"
            diff = abs(count1 - count2)
            all_match = False
        
        # 打印表格行
        print(f"{index:<30} {display_count1:<30} {display_count2:<30} {diff:<10} {status:<10}")
    
    print("-" * 120)
    if all_match:
        print("结论: 所有索引数据量一致")
    else:
        print("结论: 存在索引数据量不一致的情况")

if __name__ == "__main__":
    compare_indexes()
