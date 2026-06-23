# -*- coding: utf-8 -*-
"""
IOMP 服务管理模块
接口参考：https://oa.kedacom.com/confluence/pages/viewpage.action?pageId=218433676
主要实现：查询服务、重启服务、修改服务属性、获取服务相关资源

用法示例:
    from api_tools.iomp_api_servers_ops import IompServiceManager

    # 方式1：自动获取 IOMP Token
    manager = IompServiceManager()

    # 方式2：传入外部 Token
    manager = IompServiceManager(token="xxx")

    # 查询服务
    service_info = manager.query_service(
        cluster_name="cluster01",
        namespace="kedacom-project-namespace",
        kind="All",
        deploy_name="la-atc-biz-backend"
    )

    # 重启服务
    result = manager.reboot_service(
        cluster_name="cluster01",
        namespace="kedacom-project-namespace",
        deploy_name="la-atc-biz-backend"
    )

    # 修改副本数
    result = manager.update_service(
        cluster_name="cluster01",
        namespace="kedacom-project-namespace",
        deploy_name="la-atc-biz-backend",
        replicas=2
    )

    # 获取服务相关资源
    resources = manager.get_service_resources(
        cluster_name="cluster01",
        namespace="kedacom-project-namespace",
        deploy_name="la-atc-biz-backend"
    )

    # 删除服务
    result = manager.delete_service(
        cluster_name="cluster01",
        namespace="kedacom-project-namespace",
        deploy_name="la-atc-biz-backend"
    )

    # 一键删除服务（v2，支持 Job）
    result = manager.delete_service_all(
        cluster_name="cluster01",
        namespace="kedacom-project-namespace",
        deploy_name="la-atc-biz-backend",
        ignore=True
    )

    # 通过标签查询 pods
    pods = manager.query_pods_by_labels(
        cluster_name="cluster01",
        namespace="kedacom-project-namespace",
        kind="Deployment",
        labels={"app": "la-atc-biz-backend"}
    )
"""

import os
import sys



# ==================== 路径处理 ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# =================================================

import requests
import urllib3
from typing import Optional, Dict, List, Any

from api_tools.iomp_api_common import get_iomp_token

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 全局配置区域（按需修改）====================
DEFAULT_BASE_URL = "http://10.165.32.24:8801"   # IOMP 基础地址
DEFAULT_TIMEOUT = 30                             # 请求超时时间（秒）
DEFAULT_ACCESSKEY = "20zhfhha3xstc1zl"           # IOMP 接入密钥

# 运行示例时使用的目标服务配置（main() 中直接使用）
# API v2 没有提供获取集群列表的接口，请从 IOMP 页面手动获取后填入
CLUSTER_NAME = "dk"          # 必填：集群名称，如 "cluster01"
NAMESPACE = "kedacom-project-namespace"             # 必填：命名空间，如 "kedacom-project-namespace"
DEPLOY_NAME = "la-atc-biz-backend"
# ================================================================


class IompServiceManager:
    """
    IOMP API v2 服务管理操作类

    封装海豚 IOMP 服务管理相关接口，支持：
      - 查询服务 / 通过标签查询 pods
      - 删除服务 / 一键删除服务
      - 重启服务
      - 修改服务属性（副本数等）
      - 获取服务相关资源
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: Optional[str] = None,
        token_url: Optional[str] = None,
        accesskey: str = DEFAULT_ACCESSKEY,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        初始化 IOMP 服务管理器

        Args:
            base_url: IOMP 基础地址，如 http://10.165.32.24:8801
            token: 外部传入的 IOMP JWT Token；为空时自动获取
            token_url: IOMP token 接口完整地址；为空时按 base_url 拼接
            accesskey: 获取 token 的接入密钥
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._accesskey = accesskey
        self.timeout = timeout
        self.session = requests.Session()

        if token_url:
            self._token_url = token_url
        else:
            self._token_url = f"{self.base_url}/iomp/api/v2/token"

    def _get_token(self) -> str:
        """获取 IOMP Token，优先使用外部传入的 token"""
        if self._token:
            return self._token
        self._token = get_iomp_token(url=self._token_url, accesskey=self._accesskey)
        if not self._token:
            raise RuntimeError("[IOMP] 获取 Token 失败，请检查网络或 accesskey 配置")
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求并返回解析后的 JSON 数据

        Returns:
            接口返回的 JSON 字典；请求失败时返回 {"_error": "..."}
        """
        token = self._get_token()
        url = f"{self.base_url}{path}"

        default_headers = {
            "authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            default_headers.update(headers)

        try:
            resp = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                headers=default_headers,
                timeout=self.timeout,
                verify=False,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[请求失败] {method.upper()} {url} -> {e}")
            return {"_error": str(e)}
        except ValueError as e:
            print(f"[JSON解析失败] {method.upper()} {url} -> {e}")
            return {"_error": f"JSON解析失败: {e}"}

    # ==================== 接口方法 ====================

    def query_pods_by_labels(
        self,
        cluster_name: str,
        namespace: str,
        kind: str,
        labels: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        1. 查询服务 – 通过标签查询 pods

        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            kind: 资源类型，如 Deployment / StatefulSet / DaemonSet / All
            labels: 标签字典，如 {"app": "la-atc-biz-backend"}

        Returns:
            接口返回的 JSON 字典（含 pods 分页信息）
        """
        path = f"/iomp/api/v2/service/{cluster_name}/{namespace}/{kind}"
        print(f"[查询Pods] cluster={cluster_name}, ns={namespace}, kind={kind}, labels={labels}")
        return self._request("POST", path, json_data={"labels": labels})

    def query_service(
        self,
        cluster_name: str,
        namespace: str,
        kind: str,
        deploy_name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        2. 查询服务（含 pods 详情）

        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            kind: 资源类型；一般业务默认写 All 即可
            deploy_name: 服务名（Deployment/StatefulSet/DaemonSet 名称）
            labels: 可选标签过滤

        Returns:
            接口返回的 JSON 字典（含 creationTimestamp, name, namespace, kind,
            readyReplicas, replicas, pods 等）
        """
        path = f"/iomp/api/v2/service/{cluster_name}/{namespace}/{kind}/{deploy_name}"
        body = None
        if labels:
            body = {"labels": labels}
        print(f"[查询服务] cluster={cluster_name}, ns={namespace}, kind={kind}, deploy={deploy_name}")
        return self._request("GET", path, json_data=body)

    def delete_service(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
        configmaps: Optional[List[str]] = None,
        ingresses: Optional[List[str]] = None,
        secrets: Optional[List[str]] = None,
        pvcs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        3. 删除服务（可连带删除相关资源）

        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            deploy_name: 服务名
            configmaps: 要删除的配置文件名称列表（传 ["all"] 删除全部）
            ingresses: 要删除的路由名称列表（传 ["all"] 删除全部）
            secrets: 要删除的秘钥名称列表（传 ["all"] 删除全部）
            pvcs: 要删除的 pvc 名称列表（传 ["all"] 删除全部）

        Returns:
            {"result": "success"} 或错误信息
        """
        path = f"/iomp/api/v2/service/{cluster_name}/{namespace}/{deploy_name}"
        body = {}
        if configmaps is not None:
            body["configmaps"] = configmaps
        if ingresses is not None:
            body["ingresses"] = ingresses
        if secrets is not None:
            body["secrets"] = secrets
        if pvcs is not None:
            body["pvcs"] = pvcs

        print(f"[删除服务] cluster={cluster_name}, ns={namespace}, deploy={deploy_name}, body={body if body else '{}'}")
        return self._request("DELETE", path, json_data=body if body else None)

    def delete_service_all(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
        ignore: bool = False,
        use_v2: bool = True,
    ) -> Dict[str, Any]:
        """
        4/5. 一键删除服务（连带删除服务下全部关联资源）

        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            deploy_name: 服务名
            ignore: 是否忽略 pvc 共享删除提示（true=忽略校验）
            use_v2: True 使用 v2 接口（支持 Job 作为服务），False 使用 v1

        Returns:
            {"result": "success"} 或错误信息
        """
        version = "v2" if use_v2 else "v1"
        path = f"/iomp/api/{version}/service/{cluster_name}/{namespace}/{deploy_name}/all"
        body = {"ignore": ignore} if ignore else None

        print(f"[一键删除服务] version={version}, cluster={cluster_name}, ns={namespace}, deploy={deploy_name}, ignore={ignore}")
        return self._request("DELETE", path, json_data=body)

    def reboot_service(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
    ) -> Dict[str, Any]:
        """
        6. 重启服务接口

        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            deploy_name: 服务名

        Returns:
            {"result": "success"} 或错误信息
        """
        path = f"/iomp/api/v2/service/reboot/{cluster_name}/{namespace}/{deploy_name}"
        print(f"[重启服务] cluster={cluster_name}, ns={namespace}, deploy={deploy_name}")
        return self._request("DELETE", path)

    def update_service(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
        replicas: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        7. 修改服务属性

        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            deploy_name: 服务名
            replicas: 服务实例数（副本数）
            **kwargs: 其他要修改的属性（预留扩展）

        Returns:
            {"result": "success"} 或错误信息
        """
        path = f"/iomp/api/v2/service/{cluster_name}/{namespace}/{deploy_name}"
        body = {}
        if replicas is not None:
            body["replicas"] = replicas
        body.update(kwargs)

        print(f"[修改服务属性] cluster={cluster_name}, ns={namespace}, deploy={deploy_name}, body={body}")
        return self._request("PATCH", path, json_data=body)

    def get_service_resources(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
    ) -> Dict[str, Any]:
        """
        8. 获取服务相关资源

        Args:
            cluster_name: 集群名称
            namespace: 命名空间
            deploy_name: 服务名

        Returns:
            接口返回的 JSON 字典，result 中通常包含：
            configmaps, ingresses, jobs, pvcs, secrets, services
        """
        path = f"/iomp/api/v2/service/relate/{cluster_name}/{namespace}/{deploy_name}"
        print(f"[获取服务资源] cluster={cluster_name}, ns={namespace}, deploy={deploy_name}")
        return self._request("GET", path)

    # ==================== 便捷封装方法 ====================

    def scale_service(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
        replicas: int,
    ) -> Dict[str, Any]:
        """
        便捷方法：调整服务副本数（scale）
        """
        return self.update_service(cluster_name, namespace, deploy_name, replicas=replicas)

    def is_service_exist(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
        kind: str = "All",
    ) -> bool:
        """
        便捷方法：判断服务是否存在

        Returns:
            True=存在；False=不存在或查询失败
        """
        result = self.query_service(cluster_name, namespace, kind, deploy_name)
        if result.get("_error"):
            return False
        result_data = result.get("result", {})
        if isinstance(result_data, dict) and result_data.get("name"):
            return True
        return False

    def print_service_status(
        self,
        cluster_name: str,
        namespace: str,
        deploy_name: str,
        kind: str = "All",
    ) -> None:
        """
        便捷方法：打印指定服务的运行状态
        """
        result = self.query_service(cluster_name, namespace, kind, deploy_name)
        if result.get("_error"):
            print(f"[状态查询失败] {deploy_name}: {result['_error']}")
            return

        data = result.get("result", {})
        if not isinstance(data, dict):
            print(f"[状态查询异常] 返回格式不正确: {result}")
            return

        name = data.get("name", "N/A")
        svc_kind = data.get("kind", "N/A")
        ready = data.get("readyReplicas", 0)
        replicas = data.get("replicas", 0)
        creation = data.get("creationTimestamp", "N/A")

        print(f"{'='*60}")
        print(f"服务名称: {name}")
        print(f"资源类型: {svc_kind}")
        print(f"副本状态: {ready}/{replicas}")
        print(f"创建时间: {creation}")
        if replicas > 0 and ready != replicas:
            print(f"状态: [异常] ready 副本数不等于期望副本数")
        else:
            print(f"状态: [正常]")
        print(f"{'='*60}")

        pods = data.get("pods", [])
        if pods:
            print(f"Pod 列表 ({len(pods)} 个):")
            for pod in pods:
                pod_name = pod.get("name", "N/A")
                pod_status = pod.get("status", {}).get("phase", "N/A")
                print(f"  - {pod_name}  [{pod_status}]")
        else:
            print("Pod 列表: 无")


# ==================== 命令行示例入口 ====================

def main():
    """
    命令行示例：默认仅执行查询类操作，不执行任何删除/变更/重启等写操作。
    可按需修改参数后运行本文件。
    """
    print("=" * 60)
    print("IOMP 服务管理操作示例")
    print("=" * 60)

    # 校验必填配置
    if not CLUSTER_NAME or not NAMESPACE:
        print('\n[配置提示] 请在文件顶部"全局配置区域"中填入以下参数：')
        print('  CLUSTER_NAME = "你的集群名称"')
        print('  NAMESPACE    = "你的命名空间"')
        print('\n获取方式：登录 IOMP 页面 -> 集群管理/命名空间 查看对应名称')
        print("=" * 60)
        return

    cluster_name = CLUSTER_NAME
    namespace = NAMESPACE

    # 初始化管理器并验证连接
    try:
        manager = IompServiceManager()
        token = manager._get_token()
        if token:
            print(f"[连接成功] IOMP 地址: {manager.base_url}")
            print(f"[认证成功] Token 已获取（长度: {len(token)}）")
        else:
            print("[连接失败] 无法获取 Token，请检查网络或 accesskey 配置")
            return
    except Exception as e:
        print(f"[初始化失败] {e}")
        return

    # ==================== 以下仅执行查询类操作 ====================
    # 注意：删除、重启、修改属性等写操作默认不运行，避免误操作
    # ============================================================

    # 1. 查询服务
    print("\n--- 1. 查询服务 ---")
    try:
        svc_info = manager.query_service(cluster_name, namespace, "All", DEPLOY_NAME)
        if svc_info.get("_error"):
            print(f"[查询失败] {svc_info['_error']}")
        else:
            print(f"[查询成功] 响应摘要: {str(svc_info)[:300]}...")
    except Exception as e:
        print(f"[查询异常] {e}")

    # 2. 获取服务相关资源
    print("\n--- 2. 获取服务相关资源 ---")
    try:
        resources = manager.get_service_resources(cluster_name, namespace, DEPLOY_NAME)
        if resources.get("_error"):
            print(f"[查询失败] {resources['_error']}")
        else:
            result = resources.get("result", {})
            print(f"[查询成功] configmaps: {len(result.get('configmaps', []))} 个")
            print(f"[查询成功] ingresses: {len(result.get('ingresses', []))} 个")
            print(f"[查询成功] jobs: {len(result.get('jobs', []))} 个")
            print(f"[查询成功] pvcs: {len(result.get('pvcs', []))} 个")
            print(f"[查询成功] secrets: {len(result.get('secrets', []))} 个")
            print(f"[查询成功] services: {len(result.get('services', []))} 个")
    except Exception as e:
        print(f"[查询异常] {e}")

    # 3. 打印服务状态
    print("\n--- 3. 打印服务状态 ---")
    try:
        manager.print_service_status(cluster_name, namespace, DEPLOY_NAME)
    except Exception as e:
        print(f"[状态打印异常] {e}")

    # 4. 通过标签查询 pods（查询类操作）
    print("\n--- 4. 通过标签查询 pods ---")
    try:
        pods = manager.query_pods_by_labels(cluster_name, namespace, "Deployment", {"app": DEPLOY_NAME})
        if pods.get("_error"):
            print(f"[查询失败] {pods['_error']}")
        else:
            result = pods.get("result", {})
            pods_list = result.get("pods", []) if isinstance(result, dict) else []
            print(f"[查询成功] 共查询到 {len(pods_list)} 个 pod")
    except Exception as e:
        print(f"[查询异常] {e}")

    # ==================== 写操作保护提示 ====================
    # 以下操作（修改副本数、重启服务、删除服务、一键删除）
    # 属于变更/删除类操作，默认不执行，如需使用请取消注释并谨慎操作
    # =======================================================

    print("\n" + "-" * 60)
    print("[安全提示] 以下写操作已默认禁用，仅作说明：")
    print("  - 修改副本数 (scale_service / update_service)")
    print("  - 重启服务 (reboot_service)")
    print("  - 删除服务 (delete_service)")
    print("  - 一键删除服务 (delete_service_all)")
    print("  如需执行，请直接调用对应方法并传入参数，或取消 main() 中的注释")
    print("-" * 60)

    print("\n" + "=" * 60)
    print("示例执行完毕（仅查询模式）")
    print("=" * 60)


if __name__ == "__main__":
    main()
