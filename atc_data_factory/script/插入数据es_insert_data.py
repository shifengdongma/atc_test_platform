import requests
import json
import time

# 配置部分
ES_SERVERS = [
    "http://10.165.32.25:29200"
]

# 在这里设置要插入数据的索引名称
INDEX_NAME = "uav_runtime_data_20260318"

# 在这里设置要插入的文档ID（参数化配置）
# DOCUMENT_ID = "xFKH_JwB8aodDlRw7wqc"  # 可以根据需要修改
DOCUMENT_ID = "kdkd_JwB8aodDlRw7wqc"  # 可以根据需要修改
def get_current_timestamp():
    """获取当前时间的毫秒时间戳"""
    return int(time.time() * 1000)

def get_data_with_current_timestamp():
    """获取带有当前时间戳的数据"""
    return {
        "_class": "team.abc.laatc.base.model.UavRuntimeDataModel",
        "uniqueProductIdentificationCode": "15",
        "realNameRegistrationSign": "15",
        "classification": 3,
        "longitude": 116.4253731,
        "latitude": 39.8970406,
        "trackAngle": 257.4,
        "speed": 63.2,
        "geodeticAltitude": 2954.5,
        "pressureAltitude": 2954.5,
        "operatingStatus": 2,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 0,
        "verticalAccuracy": 2,
        "speedAccuracy": 0,
        "timestamp": get_current_timestamp(),
        "timestampAccuracy": 0
    }

def insert_data(server, index, doc_id, data):
    """向指定ES服务器的索引插入数据"""
    try:
        url = f"{server}/{index}/_doc/{doc_id}"
        headers = {"Content-Type": "application/json"}
        response = requests.put(url, data=json.dumps(data), headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print(f"数据插入成功到 {server}/{index}/_doc/{doc_id}")
            print(f"响应: {response.json()}")
            return True
        else:
            print(f"数据插入失败: {response.status_code}")
            print(f"响应: {response.text}")
            return False
    except Exception as e:
        print(f"插入数据时发生异常: {e}")
        return False

def main():
    """主函数"""
    print("=== 向ES索引插入数据 ===")
    print(f"目标索引: {INDEX_NAME}")
    print(f"文档ID: {DOCUMENT_ID}")
    print(f"目标服务器: {ES_SERVERS[0]}")
    print("-" * 120)
    
    # 获取带有当前时间戳的数据
    data = get_data_with_current_timestamp()
    current_timestamp = data["timestamp"]
    print(f"当前时间戳: {current_timestamp}")
    
    # 向第一个ES服务器插入数据
    success = insert_data(ES_SERVERS[0], INDEX_NAME, DOCUMENT_ID, data)
    
    if success:
        print("-" * 120)
        print("数据插入完成！")
        print(f"插入数据的时间戳: {current_timestamp}")
        print(f"提示: 可以使用 es_query_data.py 脚本在另一个ES服务器中查询此数据")

if __name__ == "__main__":
    main()
