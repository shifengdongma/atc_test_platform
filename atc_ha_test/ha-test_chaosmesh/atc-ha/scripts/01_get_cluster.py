#!/usr/bin/env python3
"""
脚本1：获取主集群地址
功能：从集群信息接口获取当前集群信息，支持强制集群设置

用法：
    python 01_get_cluster.py [--force CLUSTER]
    
参数：
    --force CLUSTER   强制使用指定集群（A/B）
"""

import requests
import sys
import argparse

# 集群信息获取地址
CLUSTER_INFO_URL = "https://10.165.32.35/dolphin-agent/cluster.txt"

# 集群配置
CLUSTERS = {
    "A": "http://10.165.32.24:23333",
    "B": "http://10.165.32.25:23333"
}

def get_current_cluster(force_cluster=None):
    """获取当前集群信息"""
    # 如果设置了强制集群，直接返回
    if force_cluster:
        print(f"使用强制集群: {force_cluster}")
        return force_cluster
    
    try:
        # 绕过 SSL 验证（仅用于测试）
        response = requests.get(CLUSTER_INFO_URL, timeout=10, verify=False)
        response.raise_for_status()
        cluster_info = response.json()
        cluster_sign = cluster_info.get("clusterSign", "").replace("cluster_", "").upper()
        return cluster_sign
    except Exception as e:
        print(f"获取集群信息失败: {e}")
        # 模拟返回集群 A 用于测试
        return "A"

def get_cluster_url(cluster):
    """根据集群名称获取 Chaos Mesh URL"""
    return CLUSTERS.get(cluster, CLUSTERS["A"])

def main():
    parser = argparse.ArgumentParser(description="获取集群信息")
    parser.add_argument("--force", help="强制使用指定集群（A/B）")
    args = parser.parse_args()
    
    cluster = get_current_cluster(args.force)
    cluster_url = get_cluster_url(cluster)
    
    print(f"当前集群: {cluster}")
    print(f"Chaos Mesh URL: {cluster_url}")
    
    # 返回值格式：集群名称, Chaos Mesh URL
    return f"{cluster},{cluster_url}"

if __name__ == "__main__":
    result = main()
    print(f"结果: {result}")
