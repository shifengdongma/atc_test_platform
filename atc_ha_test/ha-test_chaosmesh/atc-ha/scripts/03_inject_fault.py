#!/usr/bin/env python3
"""
脚本3：根据pod实例名称执行故障注入
功能：根据集群地址、命名空间、pod名称和实验名称执行pod-kill故障注入

用法：
    python 03_inject_fault.py --cluster-url http://10.165.32.24:23333 --namespace chaos-mesh --pod-name redis-7bbb5459cb-hbd5w --experiment-name redis-podkill-$(Get-Date -Format 'yyyyMMddHHmmss') --mode one --duration 10 --grace-period 10
    python 03_inject_fault.py --cluster-url http://10.165.32.25:23333 --namespace chaos-mesh --pod-name redis-0 --experiment-name redis-podkill --mode one --duration 10 --grace-period 0
    
参数：
    --cluster-url CLUSTER_URL       Chaos Mesh 集群地址
    --namespace NAMESPACE           目标命名空间
    --pod-name POD_NAME             Pod 名称
    --experiment-name EXPERIMENT_NAME 实验名称，实验名称重复可能执行失败
    --mode MODE                     杀死模式 (one/all/fixed/fixed-percent/random-max-percent)
    --duration DURATION             实验持续时间
    --grace-period GRACE_PERIOD     优雅终止时间(秒)
    --debug                         调试模式（不执行实际实验）
"""

import requests
import yaml
import argparse
import time

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
        # 直接发送experiment_config作为请求体
        response = self.session.post(url, json=experiment_config)
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
    pod_name: str,
    mode: str = "all",
    duration: str = "30s",
    grace_period: int = 0
) -> dict:
    # 确保duration包含时间单位
    print(f"原始duration: {duration}, 类型: {type(duration)}")
    if isinstance(duration, str) and duration.isdigit():
        duration = f"{duration}s"
    print(f"处理后duration: {duration}")
    
    # 构建标签选择器 - 使用 app.kubernetes.io/component: redis
    label_selector = {"app.kubernetes.io/component": "redis"}
    
    # 生成 labelSelectors 部分
    label_selectors_str = ""
    for key, value in label_selector.items():
        label_selectors_str += f"{" " * 6}{key}: {value}\n"
    
    # 按照用户提供的格式生成 YAML
    experiment_yaml = f"""
kind: PodChaos
apiVersion: chaos-mesh.org/v1alpha1
metadata:
  namespace: {target_namespace}
  name: {experiment_name}
spec:
  selector:
    namespaces:
      - {target_namespace}
    labelSelectors:
{label_selectors_str}
  mode: {mode}
  action: pod-kill
  gracePeriod: {grace_period}
  duration: "{duration}"
"""
    
    print(f"生成的YAML:\n{experiment_yaml}")
    
    config = yaml.safe_load(experiment_yaml)
    print(f"解析后的配置: {config}")
    
    return client.create_experiment(config, target_namespace)

def main():
    parser = argparse.ArgumentParser(description="根据pod实例名称执行故障注入")
    parser.add_argument("--cluster-url", required=True, help="Chaos Mesh 集群地址")
    parser.add_argument("--namespace", required=True, help="目标命名空间")
    parser.add_argument("--pod-name", required=True, help="Pod 名称")
    parser.add_argument("--experiment-name", default="", help="实验名称，留空则自动生成")
    parser.add_argument("--mode", default="one", help="杀死模式")
    parser.add_argument("--duration", default="30s", help="实验持续时间")
    parser.add_argument("--grace-period", type=int, default=0, help="优雅终止时间(秒)")
    parser.add_argument("--debug", action="store_true", help="调试模式（不执行实际实验）")
    args = parser.parse_args()
    
    # 自动生成唯一的实验名称
    if not args.experiment_name:
        timestamp = time.strftime("%Y%m%d%H%M%S")
        pod_suffix = args.pod_name.replace('-', '')[:10]
        args.experiment_name = f"pod-kill-{pod_suffix}-{timestamp}"
    
    print(f"集群地址: {args.cluster_url}")
    print(f"命名空间: {args.namespace}")
    print(f"Pod 名称: {args.pod_name}")
    print(f"实验名称: {args.experiment_name}")
    print(f"杀死模式: {args.mode}")
    print(f"持续时间: {args.duration}")
    print(f"优雅终止时间: {args.grace_period}秒")
    print(f"调试模式: {args.debug}")
    
    client = ChaosMeshClient(args.cluster_url)
    
    try:
        if args.debug:
            print(f"\n[调试模式] 模拟创建 {args.pod_name} 实验")
            experiment_success = True
            result = {"status": "success", "message": "Experiment created successfully"}
        else:
            # 创建实验
            result = create_podkill_experiment(
                client=client,
                experiment_name=args.experiment_name,
                target_namespace=args.namespace,
                pod_name=args.pod_name,
                mode=args.mode,
                duration=args.duration,
                grace_period=args.grace_period
            )
            print(f"\n✓ {args.pod_name} 实验创建成功!")
            print(f"响应: {result}")
            experiment_success = True
        
        return {
            "success": experiment_success,
            "experiment_name": args.experiment_name,
            "pod_name": args.pod_name,
            "result": result
        }
        
    except Exception as e:
        print(f"\n✗ {args.pod_name} 实验失败: {e}")
        return {
            "success": False,
            "experiment_name": args.experiment_name,
            "pod_name": args.pod_name,
            "error": str(e)
        }

if __name__ == "__main__":
    result = main()
    print(f"\n结果: {result}")
