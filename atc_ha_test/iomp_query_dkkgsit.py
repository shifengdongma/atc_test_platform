import os
import sys
import requests
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
# ==================== IOMP 统一入口配置 ====================
BASE_URL = 'https://ctsp.kedacom.com'  # IOMP 统一访问地址
ACCESS_KEY = 'tuyl03la5kkhm7ky'               # 访问密钥


# ==================== 服务配置 ====================
# 查询服务开关，true 查询全部，false 只查询前两个（调试用）
QUERY_ALL_SERVICES = True

# 日志级别：DEBUG = 输出所有查询明细；INFO = 只输出汇总表格和异常
LOG_LEVEL = "INFO"

# 公共参数模板（减少重复配置）
DEFAULT_CLUSTER = 'cloudtest'
DEFAULT_NAMESPACE = 'dkkgsit'
DEFAULT_KIND = 'Deployment'
DEFAULT_LABELS = {'app': 'clog'}

# 请在这里按资源类型分组配置服务名，只需写 deploy_name 列表
# 如需查询多个集群/命名空间，可在下方 SERVICE_CONFIGS 中为单个服务指定 cluster_name/namespace
DEPLOYMENT_SERVICES = [
    'la-atc-daemon-server',
    'cloud-rbac',
    'la-atc-data-exchange-ads-b',
    'la-atc-biz-backend',
    'al-atc-data-exchange-mqtt',
    'la-atc-ws-backend',
    'la-atc-frontend',
    'redis-atc',
    'la-atc-ops-server',
    'la-atc-ops-mqtt',
    'utm-mid-conflicts-v3',
    'utm-v3',
    'utm-conflicts-v3',
    'redis-hx',
    'gis-redis',
    'kgis-map-server',
    'kgis-portal-gateway',   
]

STATEFULSET_SERVICES = [
    'dol-mysql',
    'kafka-dkkghx',
    'dol-kafka',
    'dol-elasticsearch',
]

DAEMONSET_SERVICES = [
    'keepalivedvip',
]

# 自动展开为简写配置
SERVICE_CONFIGS = (
    [{'deploy_name': name} for name in DEPLOYMENT_SERVICES] +
    [{'deploy_name': name, 'kind': 'StatefulSet'} for name in STATEFULSET_SERVICES] +
    [{'deploy_name': name, 'kind': 'DaemonSet'} for name in DAEMONSET_SERVICES]
)


def _expand_service_config(config: dict) -> dict:
    """将简写配置展开为完整 ServiceConfig 参数字典"""
    full = {
        'cluster_name': DEFAULT_CLUSTER,
        'namespace': DEFAULT_NAMESPACE,
        'kind': DEFAULT_KIND,
        'labels': DEFAULT_LABELS,
    }
    full.update(config)
    return full


# 展开为完整配置（供主程序使用）
EXPANDED_SERVICE_CONFIGS = [_expand_service_config(cfg) for cfg in SERVICE_CONFIGS]


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
    base_url: str = BASE_URL                 # IOMP 统一访问地址
    access_key: str = ACCESS_KEY             # 访问密钥
    services: List[ServiceConfig] = field(default_factory=list)  # 服务列表


class IOMPQueryClient:
    """IOMP查询客户端"""

    def __init__(self, config: QueryConfig, log_level: str = LOG_LEVEL):
        self.config = config
        self.jwt_token = None
        self.base_url = config.base_url
        self.log_level = log_level.upper()
    
    def _log(self, level: str, message: str):
        """根据日志级别输出"""
        levels = {'DEBUG': 0, 'INFO': 1, 'WARN': 2, 'ERROR': 3}
        if levels.get(level.upper(), 1) >= levels.get(self.log_level, 1):
            print(message)

    def authenticate(self) -> bool:
        """登录鉴权获取JWT token"""
        url = f"{self.base_url}/iomp/api/v2/token"
        headers = {'Content-Type': 'application/json'}
        data = {'accesskey': self.config.access_key}

        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            print(f"[鉴权调试] HTTP状态码: {response.status_code}")
            print(f"[鉴权调试] 响应内容: {response.text}")
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 200:
                    self.jwt_token = result.get('result', {}).get('jwtToken')
                    if self.jwt_token:
                        self._log('INFO', f"[鉴权] | OK | 状态码: {response.status_code}")
                        return True
            self._log('ERROR', f"[鉴权] | FAIL | 状态码: {response.status_code}")
            return False
        except Exception as e:
            self._log('ERROR', f"[鉴权] | ERROR | {e}")
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
            self._log('DEBUG', f"[查询集群] | {cluster_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            self._log('ERROR', f"[查询集群] | {cluster_name} | ERROR | {e}")
            return {}

    def query_namespace_info(self, cluster_name: str, namespace: str) -> Dict[str, Any]:
        """查询指定空间资源信息"""
        url = f"{self.base_url}/iomp/api/v2/cluster/{cluster_name}/{namespace}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            result = response.json()
            self._log('DEBUG', f"[查询空间] | {cluster_name}/{namespace} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            self._log('ERROR', f"[查询空间] | {cluster_name}/{namespace} | ERROR | {e}")
            return {}

    def query_service_deployment(self, cluster_name: str, namespace: str, kind: str, deploy_name: str) -> Dict[str, Any]:
        """查询指定服务部署的相关信息"""
        url = f"{self.base_url}/iomp/api/v2/cluster/{cluster_name}/{namespace}/{kind}/{deploy_name}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            result = response.json()
            self._log('DEBUG', f"[查询部署] | {cluster_name}/{namespace}/{kind}/{deploy_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            self._log('ERROR', f"[查询部署] | {cluster_name}/{namespace}/{kind}/{deploy_name} | ERROR | {e}")
            return {}

    def query_service_by_labels(self, cluster_name: str, namespace: str, kind: str, labels: Dict[str, str]) -> Dict[str, Any]:
        """查询服务–通过标签查询pods"""
        url = f"{self.base_url}/iomp/api/v2/service/{cluster_name}/{namespace}/{kind}"
        try:
            response = requests.post(url, headers=self._get_headers(), json={'labels': labels}, timeout=10)
            result = response.json()
            self._log('DEBUG', f"[标签查询] | {cluster_name}/{namespace}/{kind} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            self._log('ERROR', f"[标签查询] | {cluster_name}/{namespace}/{kind} | ERROR | {e}")
            return {}

    def query_all_services_in_namespace(self, cluster_name: str, namespace: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """通过标签查询空间下的服务（返回单个服务详情及其匹配的pods）"""
        url = f"{self.base_url}/iomp/api/v2/service/{cluster_name}/{namespace}/All"
        try:
            payload = {'labels': labels} if labels else {'labels': {'all': ''}}
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=10)
            result = response.json()
            self._log('DEBUG', f"[标签查询] | {cluster_name}/{namespace}/All | 状态码: {result.get('status', response.status_code)}")
            return result
        except Exception as e:
            self._log('ERROR', f"[标签查询] | {cluster_name}/{namespace}/All | ERROR | {e}")
            return {}

    def query_service_detail(self, cluster_name: str, namespace: str, kind: str, deploy_name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """查询服务详情"""
        url = f"{self.base_url}/iomp/api/v2/service/{cluster_name}/{namespace}/{kind}/{deploy_name}"
        try:
            payload = {'labels': labels} if labels else {}
            response = requests.get(url, headers=self._get_headers(), json=payload, timeout=10)
            result = response.json()
            self._log('DEBUG', f"[查询服务] | {cluster_name}/{namespace}/{kind}/{deploy_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            self._log('ERROR', f"[查询服务] | {cluster_name}/{namespace}/{kind}/{deploy_name} | ERROR | {e}")
            return {}

    def query_service_resources(self, cluster_name: str, namespace: str, deploy_name: str) -> Dict[str, Any]:
        """获取服务相关资源"""
        url = f"{self.base_url}/iomp/api/v2/service/relate/{cluster_name}/{namespace}/{deploy_name}"
        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            result = response.json()
            self._log('DEBUG', f"[查询资源] | {cluster_name}/{namespace}/{deploy_name} | 状态码: {response.status_code}")
            return result
        except Exception as e:
            self._log('ERROR', f"[查询资源] | {cluster_name}/{namespace}/{deploy_name} | ERROR | {e}")
            return {}
    
    def _extract_service_summary(self, deploy_info: dict, detail_info: dict) -> dict:
        """从部署详情和服务详情中提取汇总字段"""
        summary = {
            'status': '-',
            'instances': '-',
            'cpu_limit': '-',
            'mem_limit': '-',
            'version': '-',
        }

        # 从 service_detail 提取状态和实例
        detail_result = (detail_info or {}).get('result') or {}
        pods = detail_result.get('pods', [])
        ready = detail_result.get('readyReplicas', 0)
        replicas = detail_result.get('replicas', 0)

        if pods:
            pod_statuses = [p.get('status', 'Unknown') for p in pods]
            if all(s == 'Running' for s in pod_statuses):
                summary['status'] = 'Running'
            else:
                summary['status'] = '/'.join(set(pod_statuses))
        elif replicas == 0 and ready == 0:
            summary['status'] = 'Stopped'
        else:
            summary['status'] = 'Pending'
        summary['instances'] = f"{ready}/{replicas}"

        # 版本号（保留完整，超长截断）
        labels = detail_result.get('labels', {})
        version = labels.get('app.kubernetes.io/version', '')
        if not version:
            version = labels.get('app.kubernetes.io/name', '-')
        summary['version'] = version[:40]  # 仅超长截断，不截取

        # 从 deployment_info 提取 CPU/内存 limit（取第一个容器）
        deploy_result = (deploy_info or {}).get('result') or {}
        spec = deploy_result.get('spec', {})
        template = spec.get('template', {})
        pod_spec = template.get('spec', {})
        containers = pod_spec.get('containers', [])

        if containers:
            main_container = containers[0]
            limits = main_container.get('resources', {}).get('limits', {})
            cpu = limits.get('cpu', {})
            mem = limits.get('memory', {})
            cpu_amount = cpu.get('amount', '-')
            cpu_format = cpu.get('format', '')
            mem_amount = mem.get('amount', '-')
            mem_format = mem.get('format', '')
            summary['cpu_limit'] = f"{cpu_amount}{cpu_format}" if cpu_format else str(cpu_amount)
            summary['mem_limit'] = f"{mem_amount}{mem_format}" if mem_format else str(mem_amount)

        return summary

    def query_all_services(self) -> List[Dict[str, Any]]:
        """批量查询所有配置的服务，返回带汇总的结构化结果（内部不打印表格）"""
        if not self.authenticate():
            self._log('ERROR', "鉴权失败，无法继续查询")
            return []

        services_to_query = self.config.services if QUERY_ALL_SERVICES else \
            (self.config.services[:2] if len(self.config.services) >= 2 else self.config.services)

        results = []
        for service in services_to_query:
            deploy_info = self.query_service_deployment(
                service.cluster_name, service.namespace, service.kind, service.deploy_name
            )
            detail_info = self.query_service_detail(
                service.cluster_name, service.namespace, service.kind, service.deploy_name
            )
            summary = self._extract_service_summary(deploy_info, detail_info)
            results.append({
                'config': service,
                'deployment_info': deploy_info,
                'service_detail': detail_info,
                'summary': summary,
            })
        return results


def print_comparison_table(node_a_results: List[dict], node_b_results: List[dict],
                           node_a_name: str = 'A节点', node_b_name: str = 'B节点'):
    """合并 A/B 节点结果，输出对比表格并判断一致性"""
    # 建立索引
    a_map = {r['config'].deploy_name: r for r in node_a_results}
    b_map = {r['config'].deploy_name: r for r in node_b_results}
    all_names = sorted(set(a_map.keys()) | set(b_map.keys()))

    # 按 kind 分组
    groups: Dict[str, List[dict]] = {}
    for name in all_names:
        cfg = (a_map.get(name) or b_map.get(name))['config']
        groups.setdefault(cfg.kind, []).append(name)

    inconsistent_count = 0
    for kind, names in groups.items():
        print(f"\n{'='*150}")
        print(f"【{kind} 类型服务 A/B 对比】")
        print(f"{'='*150}")
        header = (
            f"{'服务名':<26} {'节点':<6} {'状态':<8} {'实例':<6} "
            f"{'CPU(limit)':<10} {'内存(limit)':<12} {'版本号':<40} {'一致性'}"
        )
        print(header)
        print("-" * 150)

        for name in names:
            a_item = a_map.get(name)
            b_item = b_map.get(name)

            rows = []
            if a_item:
                s = a_item['summary']
                rows.append((node_a_name, s.get('status', '-'), s.get('instances', '-'),
                             s.get('cpu_limit', '-'), s.get('mem_limit', '-'), s.get('version', '-')))
            if b_item:
                s = b_item['summary']
                rows.append((node_b_name, s.get('status', '-'), s.get('instances', '-'),
                             s.get('cpu_limit', '-'), s.get('mem_limit', '-'), s.get('version', '-')))

            # 判断一致性
            if a_item and b_item:
                a_s = a_item['summary']
                b_s = b_item['summary']
                same = (
                    a_s.get('status') == b_s.get('status') and
                    a_s.get('instances') == b_s.get('instances') and
                    a_s.get('cpu_limit') == b_s.get('cpu_limit') and
                    a_s.get('mem_limit') == b_s.get('mem_limit') and
                    a_s.get('version') == b_s.get('version')
                )
                consistency = "一致" if same else "不一致"
                if not same:
                    inconsistent_count += 1
            else:
                consistency = "缺失"
                inconsistent_count += 1

            for idx, (node, status, inst, cpu, mem, ver) in enumerate(rows):
                prefix = f"{name:<26} " if idx == 0 else f"{'':<26} "
                print(f"{prefix}{node:<6} {status:<8} {inst:<6} {cpu:<10} {mem:<12} {ver:<40} {consistency if idx == 0 else ''}")
        print("-" * 150)

    print(f"\n[一致性判定] 总服务数: {len(all_names)} | 一致: {len(all_names) - inconsistent_count} | 不一致/缺失: {inconsistent_count}")


class Tee:
    """同时输出到多个文件对象（如 stdout + 日志文件）"""
    def __init__(self, *files):
        self.files = files

    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()

    def flush(self):
        for f in self.files:
            f.flush()


if __name__ == "__main__":
    # 构造日志文件路径
    log_dir = os.path.join(os.path.dirname(__file__), '..', 'tmp', 'log')
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(log_dir, f'关键服务配置及版本信息_{timestamp}.txt')

    with open(log_file, 'w', encoding='utf-8') as f:
        old_stdout = sys.stdout
        sys.stdout = Tee(sys.stdout, f)
        try:
            query_config = QueryConfig(
                base_url=BASE_URL,
                access_key=ACCESS_KEY,
                services=[ServiceConfig(**config) for config in EXPANDED_SERVICE_CONFIGS]
            )
            client = IOMPQueryClient(query_config, log_level=LOG_LEVEL)
            results = client.query_all_services()
            print(f"[INFO] 查询完成: {len(results)} 个服务")

            # 按 (cluster_name, namespace) 分组输出
            env_groups: Dict[tuple, List[dict]] = {}
            for r in results:
                key = (r['config'].cluster_name, r['config'].namespace)
                env_groups.setdefault(key, []).append(r)

            for (cluster, namespace), items in sorted(env_groups.items()):
                print(f"\n{'='*120}")
                print(f"【集群: {cluster} | 命名空间: {namespace}】")
                print(f"{'='*120}")

                # 按 kind 分组
                kind_groups: Dict[str, List[dict]] = {}
                for item in items:
                    kind_groups.setdefault(item['config'].kind, []).append(item)

                for kind, kind_items in sorted(kind_groups.items()):
                    print(f"\n--- {kind} ---")
                    header = (
                        f"{'服务名':<26} {'状态':<8} {'实例':<6} "
                        f"{'CPU(limit)':<10} {'内存(limit)':<12} {'版本号'}"
                    )
                    print(header)
                    print("-" * 100)
                    for item in kind_items:
                        s = item['summary']
                        print(f"{item['config'].deploy_name:<26} {s.get('status'):<8} {s.get('instances'):<6} "
                              f"{s.get('cpu_limit'):<10} {s.get('mem_limit'):<12} {s.get('version')}")

            print(f"\n[INFO] 日志已保存至: {log_file}")
        finally:
            sys.stdout = old_stdout
