import requests
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


# ==================== 服务配置 ====================
# 请在这里配置要查询的服务信息
SERVICE_CONFIGS = [
    # 示例配置1：查询clog服务
    {
        'cluster_name': 'dk',  # 集群名称
        'namespace': 'dp',             # 命名空间
        'kind': 'Deployment',          # 资源类型 (Deployment/StatefulSet/DaemonSet/Job等)
        'deploy_name': 'la-atc-daemon-server',         # 服务名
        'labels': {'app': 'clog'}      # 可选：标签查询条件
    },
    # 示例配置2：查询mysql服务
    {
        'cluster_name': 'dk',  # 集群名称
        'namespace': 'dp',             # 命名空间
        'kind': 'StatefulSet',         # 资源类型 (Deployment/StatefulSet/DaemonSet/Job等)
        'deploy_name': 'dol-mysql'         # 服务名
    },
    # 示例配置3：可以添加更多服务配置
    # {
    #     'cluster_name': 'production',
    #     'namespace': 'default',
    #     'kind': 'Deployment',
    #     'deploy_name': 'nginx'
    # },
]


# ==================== IOMP配置 ====================
# IOMP服务配置
IOMP_IP = "10.165.32.25"            # IOMP服务IP
IOMP_PORT = 8801                     # IOMP服务端口
IOMP_ACCESS_KEY = "3791khbrwxc9j66p"  # 访问密钥


@dataclass
class ServiceConfig:
    """服务配置类"""
    cluster_name: str          # 集群名称
    namespace: str             # 命名空间
    kind: str                  # 资源类型 (Deployment/StatefulSet/DaemonSet/Job等)
    deploy_name: str           # 服务名
    labels: Optional[Dict[str, str]] = None  # 可选：标签查询条件


@dataclass
class QueryConfig:
    """查询配置类"""
    ip: str = IOMP_IP                      # IOMP服务IP
    port: int = IOMP_PORT                 # IOMP服务端口
    access_key: str = IOMP_ACCESS_KEY           # 访问密钥
    services: List[ServiceConfig] = field(default_factory=list)  # 服务列表


class IOMPQueryClient:
    """IOMP查询客户端"""
    
    def __init__(self, config: QueryConfig):
        self.config = config
        self.jwt_token = None
        self.base_url = f"http://{config.ip}:{config.port}"
    
    def authenticate(self) -> bool:
        """登录鉴权获取JWT token"""
        url = f"{self.base_url}/iomp/api/v2/token"
        headers = {'Content-Type': 'application/json'}
        data = {'accesskey': self.config.access_key}
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 200:
                    self.jwt_token = result.get('result', {}).get('jwtToken')
                    if self.jwt_token:
                        print(f"[鉴权] | OK | 状态码: {response.status_code}")
                        return True
            print(f"[鉴权] | FAIL | 状态码: {response.status_code}")
            return False
        except Exception as e:
            print(f"[鉴权] | ERROR | {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {'Content-Type': 'application/json'}
        if self.jwt_token:
            headers['Authorization'] = self.jwt_token
        return headers
    
    def query_cluster_info(self, cluster_name: str) -> Dict[str, Any]:
        """查询集群资源信息"""
        url = f"{self.base_url}/iomp/api/v2/cluster/{cluster_name}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            result = response.json()
            print(f"[查询集群] | {cluster_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            print(f"[查询集群] | {cluster_name} | ERROR | {e}")
            return {}
    
    def query_namespace_info(self, cluster_name: str, namespace: str) -> Dict[str, Any]:
        """查询指定空间资源信息"""
        url = f"{self.base_url}/iomp/api/v2/cluster/{cluster_name}/{namespace}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            result = response.json()
            print(f"[查询空间] | {cluster_name}/{namespace} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            print(f"[查询空间] | {cluster_name}/{namespace} | ERROR | {e}")
            return {}
    
    def query_service_deployment(self, cluster_name: str, namespace: str, kind: str, deploy_name: str) -> Dict[str, Any]:
        """查询指定服务部署的相关信息"""
        url = f"{self.base_url}/iomp/api/v2/cluster/{cluster_name}/{namespace}/{kind}/{deploy_name}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            result = response.json()
            print(f"[查询部署] | {cluster_name}/{namespace}/{kind}/{deploy_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            print(f"[查询部署] | {cluster_name}/{namespace}/{kind}/{deploy_name} | ERROR | {e}")
            return {}
    
    def query_service_by_labels(self, cluster_name: str, namespace: str, kind: str, labels: Dict[str, str]) -> Dict[str, Any]:
        """查询服务–通过标签查询pods"""
        url = f"{self.base_url}/iomp/api/v2/service/{cluster_name}/{namespace}/{kind}"
        try:
            response = requests.post(url, headers=self._get_headers(), json={'labels': labels}, timeout=10)
            result = response.json()
            print(f"[标签查询] | {cluster_name}/{namespace}/{kind} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            print(f"[标签查询] | {cluster_name}/{namespace}/{kind} | ERROR | {e}")
            return {}
    
    def query_service_detail(self, cluster_name: str, namespace: str, kind: str, deploy_name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """查询服务详情"""
        url = f"{self.base_url}/iomp/api/v2/service/{cluster_name}/{namespace}/{kind}/{deploy_name}"
        try:
            payload = {'labels': labels} if labels else {}
            response = requests.get(url, headers=self._get_headers(), json=payload, timeout=10)
            result = response.json()
            print(f"[查询服务] | {cluster_name}/{namespace}/{kind}/{deploy_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            print(f"[查询服务] | {cluster_name}/{namespace}/{kind}/{deploy_name} | ERROR | {e}")
            return {}
    
    def query_service_resources(self, cluster_name: str, namespace: str, deploy_name: str) -> Dict[str, Any]:
        """获取服务相关资源"""
        url = f"{self.base_url}/iomp/api/v2/service/relate/{cluster_name}/{namespace}/{deploy_name}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            result = response.json()
            print(f"[查询资源] | {cluster_name}/{namespace}/{deploy_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            print(f"[查询资源] | {cluster_name}/{namespace}/{deploy_name} | ERROR | {e}")
            return {}
    
    def query_all_services(self) -> List[Dict[str, Any]]:
        """批量查询所有配置的服务"""
        if not self.authenticate():
            print("鉴权失败，无法继续查询")
            return []
        
        print("\n" + "="*60)
        print("开始批量查询服务信息")
        print("="*60 + "\n")
        
        results = []
        
        for idx, service in enumerate(self.config.services, 1):
            print(f"\n--- 查询服务 {idx}/{len(self.config.services)} ---")
            print(f"集群: {service.cluster_name}")
            print(f"空间: {service.namespace}")
            print(f"类型: {service.kind}")
            print(f"服务: {service.deploy_name}")
            print("-"*40)
            
            service_result = {
                'config': service,
                'cluster_info': None,
                'namespace_info': None,
                'deployment_info': None,
                'service_detail': None,
                'service_resources': None
            }
            
            # 1. 查询集群信息
            service_result['cluster_info'] = self.query_cluster_info(service.cluster_name)
            
            # 2. 查询空间信息
            service_result['namespace_info'] = self.query_namespace_info(
                service.cluster_name, service.namespace
            )
            
            # 3. 查询服务部署信息
            service_result['deployment_info'] = self.query_service_deployment(
                service.cluster_name, service.namespace, service.kind, service.deploy_name
            )
            
            # 4. 查询服务详情
            service_result['service_detail'] = self.query_service_detail(
                service.cluster_name, service.namespace, service.kind, service.deploy_name
            )
            
            # 5. 查询服务相关资源
            service_result['service_resources'] = self.query_service_resources(
                service.cluster_name, service.namespace, service.deploy_name
            )
            
            # 6. 如果有标签，进行标签查询
            if service.labels:
                service_result['label_query'] = self.query_service_by_labels(
                    service.cluster_name, service.namespace, service.kind, service.labels
                )
            
            results.append(service_result)
            print("-"*40)
        
        print("\n" + "="*60)
        print("批量查询完成")
        print("="*60)
        
        return results


# ==================== 初始化配置 ====================
# 基于上方的配置创建查询配置
QUERY_CONFIG = QueryConfig(
    services=[ServiceConfig(**config) for config in SERVICE_CONFIGS]
)


if __name__ == "__main__":
    # 创建查询客户端
    client = IOMPQueryClient(QUERY_CONFIG)
    
    # 执行批量查询
    results = client.query_all_services()
    
    # 可以在这里添加结果处理逻辑
    print(f"\n共查询了 {len(results)} 个服务")
