import requests
import json

# 配置部分
ES_SERVERS = [
    "http://10.165.32.25:29200",
    "http://10.165.32.24:29200"
]

# 在这里设置要查询的索引名称
INDEX_NAME = "uav_runtime_data_20260318"

# 在这里设置要查询的文档ID
DOCUMENT_ID = "kFKH_JwB8aodDlRw7wqc"

def query_data(server, index, doc_id):
    """在指定ES服务器的索引中查询数据"""
    try:
        url = f"{server}/{index}/_doc/{doc_id}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "server": server,
                "doc_id": data.get('_id'),
                "index": data.get('_index'),
                "version": data.get('_version'),
                "source": data.get('_source')
            }
        elif response.status_code == 404:
            return {
                "success": False,
                "server": server,
                "error": "文档不存在"
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
    """主函数 - 验证数据同步"""
    print("=== ES数据同步验证 ===")
    print(f"目标索引: {INDEX_NAME}")
    print(f"文档ID: {DOCUMENT_ID}")
    print("-" * 120)
    
    results = []
    
    # 在两个ES服务器中查询数据
    for i, server in enumerate(ES_SERVERS):
        print(f"正在查询服务器 {i+1}: {server}")
        result = query_data(server, INDEX_NAME, DOCUMENT_ID)
        results.append(result)
        
        if result["success"]:
            print(f"✓ 查询成功！")
            print(f"  文档ID: {result['doc_id']}")
            print(f"  版本: {result['version']}")
            print(f"  数据存在")
        else:
            print(f"✗ 查询失败: {result['error']}")
        print("-" * 60)
    
    # 分析同步状态
    print("\n=== 同步状态分析 ===")
    success_count = sum(1 for r in results if r["success"])
    
    if success_count == 2:
        print("✓ 数据同步正常：两个服务器都能查询到数据")
        
        # 比较数据一致性
        if results[0]["version"] == results[1]["version"]:
            print("✓ 数据版本一致")
        else:
            print(f"⚠ 数据版本不一致: 服务器1版本={results[0]['version']}, 服务器2版本={results[1]['version']}")
            
    elif success_count == 1:
        print("⚠ 数据同步异常：只有一个服务器能查询到数据")
        for i, result in enumerate(results):
            if result["success"]:
                print(f"  服务器 {i+1} ({result['server']}) 有数据")
            else:
                print(f"  服务器 {i+1} ({result['server']}) 无数据")
    else:
        print("✗ 数据同步失败：两个服务器都查询不到数据")

if __name__ == "__main__":
    main()