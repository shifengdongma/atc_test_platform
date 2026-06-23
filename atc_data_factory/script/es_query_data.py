import requests
import json

# 配置部分
ES_SERVERS = [
    "http://10.165.32.25:29200",
    "http://10.165.32.24:29200"
]

# 在这里设置要查询的索引名称
INDEX_NAME = "uav_runtime_data_20260318"

# 在这里设置要查询的文档ID（与插入脚本中使用的ID保持一致）
DOCUMENT_ID = "kdkd_JwB8aodDlRw7wqc"  # 确保与插入脚本中的ID一致

def query_data(server, index, doc_id):
    """在指定ES服务器的索引中查询数据"""
    try:
        url = f"{server}/{index}/_doc/{doc_id}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"查询成功！")
            print(f"文档ID: {data.get('_id')}")
            print(f"索引: {data.get('_index')}")
            print(f"版本: {data.get('_version')}")
            print(f"数据源:")
            print(json.dumps(data.get('_source'), indent=4, ensure_ascii=False))
            return True
        elif response.status_code == 404:
            print(f"文档不存在: {server}/{index}/_doc/{doc_id}")
            return False
        else:
            print(f"查询失败: {response.status_code}")
            print(f"响应: {response.text}")
            return False
    except Exception as e:
        print(f"查询数据时发生异常: {e}")
        return False

def main():
    """主函数"""
    print("=== 在另一个ES服务器中查询数据 ===")
    print(f"目标索引: {INDEX_NAME}")
    print(f"文档ID: {DOCUMENT_ID}")
    print(f"目标服务器: {ES_SERVERS[1]}")  # 使用第二个ES服务器
    print("-" * 120)
    
    # 在第二个ES服务器中查询数据
    success = query_data(ES_SERVERS[1], INDEX_NAME, DOCUMENT_ID)
    
    if success:
        print("-" * 120)
        print("查询完成！")
    else:
        print("-" * 120)
        print("查询失败或文档不存在！")

if __name__ == "__main__":
    main()
