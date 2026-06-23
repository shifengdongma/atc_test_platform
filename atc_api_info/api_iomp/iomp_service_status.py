import requests
import json
import argparse
from typing import Dict, Optional, List

# 配置部分
# 每个IP地址对应自己的配置
CONFIGS = [
    {
        'ip': '10.165.32.25',
        'port': 8801,
        'opapikey': '3791khbrwxc9j66p',
        'cluster_names': ['dk'],
        'namespaces': ['kedacom-project-namespace', 'kube-system'],
        'kinds': ['deployment'],
        'deploy_names': ['dol-kafka', 'dol-elasticsearch'],
        'labels': None,
        'all_param': None
    }
]

class IOMPServiceStatus:
    def __init__(self, ip: str, port: int = 8801, opapikey: str = None):
        self.ip = ip
        self.port = port
        self.opapikey = opapikey
        self.base_url = f"http://{ip}:{port}/iomp/api/v2/service"
        self.token_url = f"http://{ip}:{port}/iomp/api/v2/token"
        self.jwt_token = None
        self.refresh_token = None
    
    def get_token(self) -> Dict:
        """
        获取认证信息
        
        Returns:
            包含jwtToken和refreshToken的字典
        """
        # 构建请求头
        headers = {}
        if self.opapikey:
            headers['opapikey'] = self.opapikey
        
        try:
            # 尝试使用POST请求获取token，添加请求体
            data = {}
            if self.opapikey:
                data['accesskey'] = self.opapikey
            # 尝试不同的请求体结构
            response = requests.post(self.token_url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            token_info = response.json()
            # 从result字段中获取token信息
            result = token_info.get('result', {})
            # 尝试获取不同可能的字段名
            self.jwt_token = result.get('jwtToken') or result.get('token') or result.get('accessToken')
            self.refresh_token = result.get('refreshToken') or result.get('refresh_token')
            return token_info
        except requests.exceptions.RequestException as e:
            print(f"获取token失败: {e}")
            return {}
        except ValueError as e:
            print(f"解析token信息失败: {e}")
            return {}
    
    def refresh_token_method(self) -> Dict:
        """
        刷新认证信息
        
        Returns:
            刷新后的认证信息
        """
        if not self.refresh_token:
            print("没有refreshToken，无法刷新")
            return {}
        
        # 构建请求头
        headers = {}
        if self.opapikey:
            headers['opapikey'] = self.opapikey
        
        try:
            url = f"http://{self.ip}:{self.port}/iomp/api/v2/token/refresh"
            response = requests.post(url, json={'refreshToken': self.refresh_token}, headers=headers, timeout=10)
            response.raise_for_status()
            token_info = response.json()
            self.jwt_token = token_info.get('jwtToken')
            self.refresh_token = token_info.get('refreshToken')
            return token_info
        except requests.exceptions.RequestException as e:
            print(f"刷新token失败: {e}")
            return {}
    
    def access_token(self) -> Dict:
        """
        访问续期
        
        Returns:
            续期后的信息
        """
        if not self.jwt_token:
            print("没有jwtToken，无法续期")
            return {}
        
        # 构建请求头
        headers = {'Authorization': f'Bearer {self.jwt_token}'}
        if self.opapikey:
            headers['opapikey'] = self.opapikey
        
        try:
            url = f"http://{self.ip}:{self.port}/iomp/api/v2/token/access"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"访问续期失败: {e}")
            return {}
    
    def get_current_user(self) -> Dict:
        """
        获取当前登录人username
        
        Returns:
            当前用户信息
        """
        if not self.jwt_token:
            print("没有jwtToken，无法获取用户信息")
            return {}
        
        # 构建请求头
        headers = {'Authorization': f'Bearer {self.jwt_token}'}
        if self.opapikey:
            headers['opapikey'] = self.opapikey
        
        try:
            url = f"http://{self.ip}:{self.port}/iomp/api/v2/token/user"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"获取用户信息失败: {e}")
            return {}
    
    def get_service_status(
        self,
        cluster_name: str,
        namespace: str,
        kind: str,
        deploy_name: str,
        labels: Optional[Dict[str, str]] = None,
        all_param: Optional[str] = None
    ) -> Dict:
        """
        获取指定服务的状态信息
        
        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            kind: 资源类型
            deploy_name: 服务名
            labels: 标签（可选）
            all_param: All参数（可选）
            
        Returns:
            服务状态信息
        """
        # 构建URL
        url = f"{self.base_url}/{cluster_name}/{namespace}/{kind}/{deploy_name}"
        
        # 构建查询参数
        params = {}
        if labels:
            params['labels'] = json.dumps(labels)
        if all_param:
            params['All'] = all_param
        
        # 构建请求头
        headers = {}
        if self.opapikey:
            headers['opapikey'] = self.opapikey
        # 暂时不使用token，只使用opapikey
        # if self.jwt_token:
        #     headers['token'] = self.jwt_token
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()  # 检查响应状态
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return {}
    
    def print_service_info(self, service_info: Dict):
        """
        打印服务信息
        
        Args:
            service_info: 服务状态信息
        """
        if not service_info:
            print("未获取到服务信息")
            return
        
        print("\n=== 服务基本信息 ===")
        print(f"创建时间: {service_info.get('creationTimestamp', 'N/A')}")
        print(f"服务名: {service_info.get('name', 'N/A')}")
        print(f"命名空间: {service_info.get('namespace', 'N/A')}")
        print(f"资源类型: {service_info.get('kind', 'N/A')}")
        print(f"Ready副本数: {service_info.get('readyReplicas', 'N/A')}")
        print(f"期望副本数: {service_info.get('replicas', 'N/A')}")
        
        # 打印Pod信息
        pods = service_info.get('pods', [])
        print(f"\n=== Pod信息 ({len(pods)}个) ===")
        for i, pod in enumerate(pods, 1):
            print(f"\nPod {i}:")
            print(f"  名称: {pod.get('metadata', {}).get('name', 'N/A')}")
            print(f"  状态: {pod.get('status', {}).get('phase', 'N/A')}")
            print(f"  IP: {pod.get('status', {}).get('podIP', 'N/A')}")
            print(f"  节点: {pod.get('spec', {}).get('nodeName', 'N/A')}")
            print(f"  容器状态:")
            for container in pod.get('status', {}).get('containerStatuses', []):
                print(f"    - {container.get('name', 'N/A')}: {container.get('state', {}).get('running', {}).get('startedAt', 'N/A') or 'Not Running'}")

def main():
    parser = argparse.ArgumentParser(description="获取iomp服务状态")
    parser.add_argument('--ip', help="iomp服务IP地址")
    parser.add_argument('--port', type=int, help="iomp服务端口")
    parser.add_argument('--cluster', help="集群名称")
    parser.add_argument('--namespace', help="命名空间")
    parser.add_argument('--kind', help="资源类型")
    parser.add_argument('--deploy', help="服务名")
    parser.add_argument('--labels', type=str, help="标签，格式: key1=value1,key2=value2")
    parser.add_argument('--all', help="All参数")
    
    args = parser.parse_args()
    
    # 解析标签参数
    labels = None
    if args.labels:
        labels = {}
        for label in args.labels.split(','):
            if '=' in label:
                key, value = label.split('=', 1)
                labels[key.strip()] = value.strip()
    
    # 确定使用的配置
    if args.ip:
        # 如果指定了IP，使用该IP的配置
        target_configs = [
            config for config in CONFIGS if config['ip'] == args.ip
        ]
        if not target_configs:
            # 如果没有找到对应IP的配置，创建一个临时配置
            target_configs = [{
                'ip': args.ip,
                'port': args.port or 8801,
                'opapikey': 'your_api_key_here',
                'cluster_names': [args.cluster] if args.cluster else ['cluster1'],
                'namespaces': [args.namespace] if args.namespace else ['default'],
                'kinds': [args.kind] if args.kind else ['deployment'],
                'deploy_names': [args.deploy] if args.deploy else ['mysql'],
                'labels': labels,
                'all_param': args.all
            }]
    else:
        # 否则使用所有配置
        target_configs = CONFIGS
    
    # 遍历所有配置
    for config in target_configs:
        ip = config['ip']
        port = args.port if args.port else config['port']
        opapikey = config['opapikey']
        cluster_names = [args.cluster] if args.cluster else config['cluster_names']
        namespaces = [args.namespace] if args.namespace else config['namespaces']
        kinds = [args.kind] if args.kind else config['kinds']
        deploy_names = [args.deploy] if args.deploy else config['deploy_names']
        all_param = args.all if args.all else config['all_param']
        
        print(f"\n=== 处理IP: {ip} ===")
        
        # 创建IOMPServiceStatus实例
        iomp_client = IOMPServiceStatus(ip, port, opapikey)
        
        # 获取认证信息
        print("获取认证信息...")
        token_info = iomp_client.get_token()
        if not token_info:
            print("认证失败，无法继续")
            continue
        print(f"认证成功，获取到token")
        
        # 可选：获取当前用户信息
        print("获取当前用户信息...")
        user_info = iomp_client.get_current_user()
        if user_info:
            print(f"当前登录用户: {user_info.get('username', 'N/A')}")
        
        # 遍历服务组合
        for cluster in cluster_names:
            for namespace in namespaces:
                for kind in kinds:
                    for deploy in deploy_names:
                        print(f"\n=== 获取服务状态: {cluster}/{namespace}/{kind}/{deploy} ===")
                        # 获取服务状态
                        service_info = iomp_client.get_service_status(
                            cluster_name=cluster,
                            namespace=namespace,
                            kind=kind,
                            deploy_name=deploy,
                            labels=labels or config['labels'],
                            all_param=all_param
                        )
                        
                        # 打印服务信息
                        iomp_client.print_service_info(service_info)

if __name__ == "__main__":
    main()
