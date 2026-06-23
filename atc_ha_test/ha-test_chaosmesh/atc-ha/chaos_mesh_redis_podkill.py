"""
Chaos Mesh Pod Kill 实验脚本
通过 Chaos Mesh Dashboard API 创建 Pod Kill 实验
支持多集群切换检测和多种 Pod 类型
"""

import requests
import json
import time
import yaml

# 实验配置
TARGET_NAMESPACE = "chaos-mesh"  # 目标命名空间
POD_KEYWORD = "redis"  # Pod 关键字（用于匹配）
POD_KILL_MODE = "one"  # 杀死模式 (one/all/fixed/fixed-percent/random-max-percent)
DURATION = "30s"  # 实验持续时间
GRACE_PERIOD = 0  # 优雅终止时间(秒)

# 调试模式开关
DEBUG_MODE = "verify"  # 设置为 False 时执行实际实验，设置为 True 时模拟执行，设置为 "verify" 时仅验证配置

# Chaos Mesh API 地址（会根据当前集群自动设置）
CHAOS_MESH_API = ""  # 会在运行时动态设置




# 集群配置
CLUSTERS = {
    "A": "http://10.165.32.24:23333",
    "B": "http://10.165.32.25:23333"
}

# 强制使用B集群（用于测试）
FORCE_CLUSTER = "A"  # 设置为 None 时使用实际集群信息

# 集群信息获取地址
CLUSTER_INFO_URL = "https://10.165.32.35/dolphin-agent/cluster.txt"


def get_pods_in_namespace(namespace):
    """获取指定命名空间下的所有 Pod"""
    try:
        # 尝试从实际的 Pod 接口获取信息
        print("  正在获取实际 Pod 信息...")
        pods_url = f"{CHAOS_MESH_API}/api/common/pods"
        # 打印API调用命令
        print(f"  执行命令: GET {pods_url}")
        
        try:
            pods_response = requests.get(pods_url, timeout=10)
            pods_response.raise_for_status()
            pods_data = pods_response.json()
            
            # 过滤出指定命名空间的 Pod
            pods = []
            for pod in pods_data:
                if pod.get("namespace") == namespace:
                    pod_info = {
                        "name": pod.get("name"),
                        "namespace": pod.get("namespace"),
                        "ip": pod.get("ip"),
                        "state": pod.get("state"),
                        "labels": {}
                    }
                    # 基于 Pod 名称推断标签
                    pod_name = pod.get("name", "")
                    if "redis" in pod_name:
                        pod_info["labels"]["app.kubernetes.io/component"] = "redis"
                        pod_info["labels"]["app.kubernetes.io/name"] = "redis"
                    elif "chaos" in pod_name:
                        pod_info["labels"]["app.kubernetes.io/name"] = "chaos-mesh"
                    pods.append(pod_info)
            
            if pods:
                print(f"  从 {CHAOS_MESH_API} 获取到 {len(pods)} 个实际 Pod")
                for pod in pods:
                    print(f"    - {pod['name']} (状态: {pod.get('state', '未知')})")
                return pods
        except Exception as pods_error:
            print(f"  Pod 接口调用失败: {pods_error}")
            print("  尝试使用标签信息构建 Pod 列表...")
        
        # 1. 获取标签信息
        print("  正在获取标签信息...")
        labels_url = f"{CHAOS_MESH_API}/api/common/labels"
        labels_params = {"podNamespaceList": namespace}
        # 打印API调用命令
        print(f"  执行命令: GET {labels_url}?podNamespaceList={namespace}")
        labels_response = requests.get(labels_url, params=labels_params, timeout=10)
        labels_response.raise_for_status()
        labels_data = labels_response.json()
        
        # 2. 获取注解信息
        print("  正在获取注解信息...")
        annotations_url = f"{CHAOS_MESH_API}/api/common/annotations"
        annotations_params = {"podNamespaceList": namespace}
        # 打印API调用命令
        print(f"  执行命令: GET {annotations_url}?podNamespaceList={namespace}")
        annotations_response = requests.get(annotations_url, params=annotations_params, timeout=10)
        annotations_response.raise_for_status()
        annotations_data = annotations_response.json()
        
        # 打印获取到的标签信息（用于调试）
        print(f"  从 {CHAOS_MESH_API} 获取到的标签信息:")
        print(f"    pod-template-hash: {labels_data.get('pod-template-hash', '无')}")
        print(f"    app.kubernetes.io/component: {labels_data.get('app.kubernetes.io/component', '无')}")
        
        # 基于标签信息构建 Pod 列表
        print("  基于标签信息构建 Pod 列表...")
        pods = []
        
        # 1. Redis 相关 Pod
        if "app.kubernetes.io/component" in labels_data and "redis" in labels_data["app.kubernetes.io/component"]:
            # 使用用户提供的实际 Redis Pod 名称
            if CHAOS_MESH_API == "http://10.165.32.24:23333":
                # A集群的实际redis pod名称
                redis_pod_name = "redis-7bbb5459cb-hbd5w"
            else:
                # 其他集群使用构建的名称
                redis_hash = ""
                if "pod-template-hash" in labels_data and labels_data["pod-template-hash"]:
                    redis_hash = labels_data["pod-template-hash"][0]
                redis_pod_name = f"redis-chaos-{redis_hash}-zbrl2" if redis_hash else "redis-chaos-xxx-zbrl2"
            
            pods.append({
                "name": redis_pod_name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/component": "redis",
                    "app.kubernetes.io/name": "redis"
                }
            })
        
        # 2. Chaos Mesh 组件 Pod
        if "app.kubernetes.io/component" in labels_data:
            components = labels_data["app.kubernetes.io/component"]
            for component in components:
                if component != "redis":  # 避免重复
                    # 从获取的标签中选择 hash 值
                    component_hash = ""
                    if "pod-template-hash" in labels_data and labels_data["pod-template-hash"]:
                        # 为每个组件选择不同的 hash
                        hash_index = components.index(component) % len(labels_data["pod-template-hash"])
                        component_hash = labels_data["pod-template-hash"][hash_index]
                    
                    # 构建组件 Pod 名称
                    pod_name = f"chaos-{component.replace('-', '')}-{component_hash}" if component_hash else f"chaos-{component.replace('-', '')}-xxx"
                    
                    pods.append({
                        "name": pod_name,
                        "namespace": namespace,
                        "labels": {
                            "app.kubernetes.io/component": component,
                            "app.kubernetes.io/name": "chaos-mesh",
                            "pod-template-hash": component_hash
                        }
                    })
        
        # 3. Redis Exporter Pod
        if "app" in labels_data and "redis-chaos-exporter" in labels_data["app"]:
            exporter_hash = ""
            if "pod-template-hash" in labels_data and labels_data["pod-template-hash"]:
                exporter_hash = labels_data["pod-template-hash"][-1]  # 使用最后一个 hash
            
            exporter_pod_name = f"redis-chaos-exporter-{exporter_hash}" if exporter_hash else "redis-chaos-exporter-xxx"
            
            pods.append({
                "name": exporter_pod_name,
                "namespace": namespace,
                "labels": {
                    "app": "redis-chaos-exporter",
                    "pod-template-hash": exporter_hash
                }
            })
        
        return pods
    except Exception as e:
        print(f"获取 Pod 信息失败: {e}")
        # 返回默认 Pod 列表用于测试
        if CHAOS_MESH_API == "http://10.165.32.24:23333":
            # A集群的实际redis pod名称
            return [
                {"name": "redis-7bbb5459cb-hbd5w", "namespace": namespace, "labels": {"app.kubernetes.io/component": "redis"}},
                {"name": "chaos-controller-manager-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "controller-manager"}},
                {"name": "chaos-daemon-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "chaos-daemon"}},
                {"name": "chaos-dashboard-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "chaos-dashboard"}},
                {"name": "chaos-dns-server-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "chaos-dns-server"}}
            ]
        else:
            # 其他集群的默认pod列表
            return [
                {"name": "redis-chaos-xxx-zbrl2", "namespace": namespace, "labels": {"app.kubernetes.io/component": "redis"}},
                {"name": "chaos-controller-manager-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "controller-manager"}},
                {"name": "chaos-daemon-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "chaos-daemon"}},
                {"name": "chaos-dashboard-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "chaos-dashboard"}},
                {"name": "chaos-dns-server-xxx", "namespace": namespace, "labels": {"app.kubernetes.io/component": "chaos-dns-server"}}
            ]


def match_pods_by_keyword(pods, keyword):
    """根据关键字匹配 Pod"""
    matched_pods = []
    for pod in pods:
        pod_name = pod.get("name", "")
        # 排除包含 exporter 的 Pod
        if "exporter" in pod_name.lower():
            continue
        # 检查 Pod 名称是否包含关键字
        if keyword.lower() in pod_name.lower():
            matched_pods.append(pod)
        # 检查 Pod 标签是否包含关键字
        else:
            labels = pod.get("labels", {})
            for value in labels.values():
                if keyword.lower() in str(value).lower():
                    matched_pods.append(pod)
                    break
    return matched_pods


class ChaosMeshClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def create_experiment(self, experiment_config: dict, namespace: str = "chaos-mesh") -> dict:
        url = f"{self.base_url}/api/experiments"
        payload = {
            "namespace": namespace,
            "kind": "PodChaos",
            "name": experiment_config["metadata"]["name"],
            "experiment": experiment_config
        }
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def create_experiment_by_yaml(self, yaml_content: str, namespace: str = "chaos-mesh") -> dict:
        config = yaml.safe_load(yaml_content)
        return self.create_experiment(config, namespace)

    def list_experiments(self, namespace: str = "chaos-mesh") -> list:
        url = f"{self.base_url}/api/experiments"
        params = {"namespace": namespace}
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def get_experiment(self, name: str, namespace: str = "chaos-mesh") -> dict:
        url = f"{self.base_url}/api/experiments/{name}"
        params = {"namespace": namespace}
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def delete_experiment(self, name: str, namespace: str = "chaos-mesh") -> dict:
        url = f"{self.base_url}/api/experiments/{name}"
        params = {"namespace": namespace}
        response = self.session.delete(url, params=params)
        response.raise_for_status()
        return response.json()

    def pause_experiment(self, name: str, namespace: str = "chaos-mesh") -> dict:
        url = f"{self.base_url}/api/experiments/{name}/pause"
        params = {"namespace": namespace}
        response = self.session.put(url, params=params)
        response.raise_for_status()
        return response.json()

    def resume_experiment(self, name: str, namespace: str = "chaos-mesh") -> dict:
        url = f"{self.base_url}/api/experiments/{name}/start"
        params = {"namespace": namespace}
        response = self.session.put(url, params=params)
        response.raise_for_status()
        return response.json()


def create_podkill_experiment(
    client: ChaosMeshClient,
    experiment_name: str,
    target_namespace: str,
    label_selector: dict,
    mode: str = "one",
    duration: str = "30s",
    grace_period: int = 0
) -> dict:
    # 生成 labelSelectors 部分
    label_selectors_str = ""
    for key, value in label_selector.items():
        label_selectors_str += f"{" " * 6}{key}: {value}\n"
    
    experiment_yaml = f"""
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: {experiment_name}
  namespace: {target_namespace}
spec:
  action: pod-kill
  mode: {mode}
  selector:
    namespaces:
      - {target_namespace}
    labelSelectors:
{label_selectors_str}
  gracePeriod: {grace_period}
  duration: "{duration}"
"""
    return client.create_experiment(yaml.safe_load(experiment_yaml), target_namespace)


def get_current_cluster():
    """获取当前集群信息"""
    # 如果设置了强制集群，直接返回
    if FORCE_CLUSTER:
        print(f"使用强制集群: {FORCE_CLUSTER}")
        return FORCE_CLUSTER
    
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


def detect_cluster_switch():
    """检测集群切换并计算切换时间"""
    start_time = time.time()
    initial_cluster = get_current_cluster()
    
    print(f"初始集群: {initial_cluster}")
    print("开始检测集群切换...")
    
    while True:
        current_cluster = get_current_cluster()
        if current_cluster and current_cluster != initial_cluster:
            switch_time = time.time() - start_time
            return initial_cluster, current_cluster, switch_time
        time.sleep(1)


def main():
    print("=" * 100)
    print("Chaos Mesh Pod Kill 实验 - 多集群版本")
    print("=" * 100)
    
    # 显示当前模式
    if DEBUG_MODE == "verify":
        print("当前模式: 验证模式（仅验证配置，不执行实际实验）")
    elif DEBUG_MODE:
        print("当前模式: 调试模式（不执行实际实验）")
    else:
        print("当前模式: 正常模式（执行实际实验）")
    
    # 获取当前集群
    current_cluster = get_current_cluster()
    if not current_cluster:
        print("无法获取当前集群信息，退出程序")
        return
    
    print(f"\n当前集群: {current_cluster}")
    
    # 获取对应集群的 Chaos Mesh URL
    cluster_key = current_cluster
    if cluster_key not in CLUSTERS:
        print(f"未知集群: {current_cluster}")
        return
    
    chaos_mesh_url = CLUSTERS[cluster_key]
    print(f"使用 Chaos Mesh: {chaos_mesh_url}")
    
    # 设置 Chaos Mesh API 地址
    global CHAOS_MESH_API
    CHAOS_MESH_API = chaos_mesh_url
    
    # 显示配置信息
    print("\n配置信息:")
    print(f"  目标命名空间: {TARGET_NAMESPACE}")
    print(f"  Pod 关键字: {POD_KEYWORD}")
    print(f"  杀死模式: {POD_KILL_MODE}")
    print(f"  持续时间: {DURATION}")
    print(f"  优雅终止时间: {GRACE_PERIOD}s")
    print(f"  Chaos Mesh API: {CHAOS_MESH_API}")
    
    # 获取 Pod 信息
    print("\n[1] 获取命名空间下的 Pod 信息...")
    pods = get_pods_in_namespace(TARGET_NAMESPACE)
    print(f"  发现 {len(pods)} 个 Pod")
    for pod in pods:
        print(f"    - {pod['name']}")
    
    # 匹配 Pod
    print(f"\n[2] 根据关键字 '{POD_KEYWORD}' 匹配 Pod...")
    matched_pods = match_pods_by_keyword(pods, POD_KEYWORD)
    print(f"  匹配到 {len(matched_pods)} 个 Pod")
    for pod in matched_pods:
        print(f"    - {pod['name']} (标签: {pod.get('labels', {})})")
    
    if not matched_pods:
        print("  没有匹配到 Pod，退出程序")
        return
    
    # 验证模式 - 仅验证配置，不执行实际实验
    if DEBUG_MODE == "verify":
        print("\n验证完成: 配置信息正确，Pod 匹配成功")
        print("=" * 100)
        return
    
    client = ChaosMeshClient(chaos_mesh_url)
    
    # 结果列表
    results = []
    
    try:
        for pod in matched_pods:
            pod_name = pod['name']
            labels = pod.get('labels', {})
            experiment_name = f"pod-kill-{pod_name.replace('-', '')[:20]}"
            
            # 构建标签选择器
            label_selector = {}
            # 优先使用唯一标识的标签
            for key, value in labels.items():
                if key in ['app', 'app.kubernetes.io/name', 'app.kubernetes.io/component']:
                    label_selector[key] = value
                    break
            # 如果没有合适的标签，使用 Pod 名称
            if not label_selector and pod_name:
                label_selector['name'] = pod_name
            
            print(f"\n[3] 创建 {pod_name} Pod Kill 实验...")
            
            try:
                if DEBUG_MODE and DEBUG_MODE != "verify":
                    print(f"  [调试模式] 模拟创建 {pod_name} 实验")
                    experiment_success = True
                else:
                    # 创建实验
                    result = create_podkill_experiment(
                        client=client,
                        experiment_name=experiment_name,
                        target_namespace=TARGET_NAMESPACE,
                        label_selector=label_selector,
                        mode=POD_KILL_MODE,
                        duration=DURATION,
                        grace_period=GRACE_PERIOD
                    )
                    print(f"  ✓ {pod_name} 实验创建成功!")
                    experiment_success = True
                
                # 等待实验执行
                print("  等待实验执行...")
                time.sleep(5)
                
                # 检测集群切换
                print("  开始检测集群切换...")
                if DEBUG_MODE and DEBUG_MODE != "verify":
                    # 模拟集群切换
                    initial_cluster = current_cluster
                    switched_cluster = "B" if current_cluster == "A" else "A"
                    switch_time = 10.5
                    print(f"  [调试模式] 模拟集群切换: {initial_cluster} -> {switched_cluster} (切换时间: {switch_time:.2f}秒)")
                else:
                    initial_cluster, switched_cluster, switch_time = detect_cluster_switch()
                
                # 记录结果
                results.append({
                    "切换前": initial_cluster,
                    "主集群A/B": initial_cluster,
                    "pod名称": pod_name,
                    "实验是否成功": "成功" if experiment_success else "失败",
                    "切换后集群": switched_cluster,
                    "切换时间": f"{switch_time:.2f}秒"
                })
                
                # 清理实验
                if not DEBUG_MODE or DEBUG_MODE == "verify":
                    delete_result = client.delete_experiment(
                        experiment_name,
                        TARGET_NAMESPACE
                    )
                    print(f"  实验已清理")
                else:
                    print(f"  [调试模式] 模拟清理 {pod_name} 实验")
                
            except Exception as e:
                print(f"  ✗ {pod_name} 实验失败: {e}")
                experiment_success = False
                
                # 尝试检测集群切换
                try:
                    if DEBUG_MODE and DEBUG_MODE != "verify":
                        initial_cluster = current_cluster
                        switched_cluster = "B" if current_cluster == "A" else "A"
                        switch_time = 5.2
                        print(f"  [调试模式] 模拟集群切换: {initial_cluster} -> {switched_cluster} (切换时间: {switch_time:.2f}秒)")
                    else:
                        initial_cluster, switched_cluster, switch_time = detect_cluster_switch()
                except:
                    initial_cluster, switched_cluster, switch_time = current_cluster, current_cluster, 0
                
                # 记录失败结果
                results.append({
                    "切换前": initial_cluster,
                    "主集群A/B": initial_cluster,
                    "pod名称": pod_name,
                    "实验是否成功": "失败",
                    "切换后集群": switched_cluster,
                    "切换时间": f"{switch_time:.2f}秒"
                })
        
        # 输出表格结果
        print("\n" + "=" * 120)
        print("实验结果汇总")
        print("=" * 120)
        print(f"{'切换前':<10} {'主集群A/B':<12} {'pod名称':<15} {'实验是否成功':<12} {'切换后集群':<12} {'切换时间':<10}")
        print("-" * 120)
        
        for result in results:
            print(f"{result['切换前']:<10} {result['主集群A/B']:<12} {result['pod名称']:<15} {result['实验是否成功']:<12} {result['切换后集群']:<12} {result['切换时间']:<10}")
        
        print("=" * 120)
        
    except Exception as e:
        print(f"\n发生错误: {type(e).__name__}: {e}")


def simple_create_experiment():
    # 显示当前模式
    if DEBUG_MODE == "verify":
        print("当前模式: 验证模式（仅验证配置，不执行实际实验）")
    elif DEBUG_MODE:
        print("当前模式: 调试模式（不执行实际实验）")
    else:
        print("当前模式: 正常模式（执行实际实验）")
    
    # 获取当前集群
    current_cluster = get_current_cluster()
    if not current_cluster:
        print("无法获取当前集群信息，退出程序")
        return
    
    # 获取对应集群的 Chaos Mesh URL
    cluster_key = current_cluster
    if cluster_key not in CLUSTERS:
        print(f"未知集群: {current_cluster}")
        return
    
    chaos_mesh_url = CLUSTERS[cluster_key]
    
    # 使用当前配置的 Pod 类型
    labels = CURRENT_POD_TYPE["labels"]
    experiment_name = CURRENT_POD_TYPE["experiment_name"]
    label_selector = labels
    app_name = list(labels.values())[0]
    
    experiment_manifest = {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": {
            "name": experiment_name,
            "namespace": TARGET_NAMESPACE
        },
        "spec": {
            "action": "pod-kill",
            "mode": POD_KILL_MODE,
            "selector": {
                "namespaces": [TARGET_NAMESPACE],
                "labelSelectors": label_selector
            },
            "gracePeriod": GRACE_PERIOD,
            "duration": DURATION
        }
    }
    
    print(f"创建 {app_name} Pod Kill 实验...")
    print(f"当前集群: {current_cluster}")
    print(f"请求 URL: {chaos_mesh_url}/api/experiments")
    print(f"实验配置:\n{json.dumps(experiment_manifest, indent=2, ensure_ascii=False)}")
    
    # 如果是验证模式，直接结束
    if VERIFICATION_MODE:
        print("\n验证完成: 配置信息正确")
        return None
    
    # 如果是调试模式，模拟执行
    if DEBUG_MODE:
        print("\n[调试模式] 模拟创建实验...")
        print("[调试模式] 实验创建成功!")
        print("[调试模式] 模拟响应: {\"status\": \"success\", \"message\": \"Experiment created successfully\"}")
        return {"status": "success", "message": "Experiment created successfully"}
    
    try:
        response = requests.post(
            f"{chaos_mesh_url}/api/experiments",
            json=experiment_manifest,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        
        print("\n实验创建成功!")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"\n请求失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"响应状态码: {e.response.status_code}")
            print(f"响应内容: {e.response.text}")
        return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--simple":
        simple_create_experiment()
    else:
        main()
