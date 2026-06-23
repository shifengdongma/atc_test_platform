import requests
import json
import os
import sys
import time
from ha_env import es_hosts
# 查询两个集群所有uav_runtime_data索引的数据，进行比对，检测数据同步一致性，验证兜底策略

# 从 ha_env.py 导入 ES 地址，拼接为完整 URL
ES_SERVERS = [f"http://{host}" for host in es_hosts]

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 创建日志目录
LOG_DIR = os.path.join(SCRIPT_DIR, "log")
os.makedirs(LOG_DIR, exist_ok=True)

# 生成日志文件名：ElasticSearch全量查询_日期时分秒.txt
log_filename = time.strftime("ElasticSearch全量查询_%Y%m%d_%H%M%S.txt")
log_filepath = os.path.join(LOG_DIR, log_filename)

class TeeOutput:
    """同时输出到控制台和日志文件"""
    def __init__(self, filepath):
        self.file = open(filepath, "a", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, data):
        self.stdout.write(data)
        self.file.write(data)
        self.file.flush()

    def flush(self):
        self.stdout.flush()
        self.file.flush()

# 重定向标准输出，实现打印内容同时写入日志
sys.stdout = TeeOutput(log_filepath)
print(f"日志文件路径: {log_filepath}")
print("-" * 120)


def get_indexes_from_es(server):
    """从 ES 查询 uav_runtime_data* 索引列表"""
    try:
        url = f"{server}/_cat/indices/uav_runtime_data*?format=json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            indexes = [item['index'] for item in data if 'index' in item]
            indexes.sort()
            print(f"从 {server} 获取到 {len(indexes)} 个 uav_runtime_data* 索引")
            return indexes
        else:
            print(f"从 {server} 获取索引列表失败，状态码: {response.status_code}")
            return []
    except Exception as e:
        print(f"从 {server} 获取索引列表异常: {e}")
        return []

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
    
    # 从第一个可达的 ES 服务器获取索引列表
    indexes = []
    for server in ES_SERVERS:
        if server_reachability[server]:
            indexes = get_indexes_from_es(server)
            if indexes:
                break
    
    if not indexes:
        print("无法从任何 ES 服务器获取索引列表")
        return
    
    print(f"\n开始对比 {len(indexes)} 个索引...")
    print("-" * 120)
    
    # 打印表头
    print(f"{'索引名称':<30} {ES_SERVERS[0]:<30} {ES_SERVERS[1]:<30} {'差异':<10} {'状态':<10}")
    print("-" * 120)
    
    all_match = True
    
    for index in indexes:
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
