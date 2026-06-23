# -*- coding: utf-8 -*-
"""
IOMP 微服务日志下载脚本

基于 chrome 浏览器下载的 网络请求HAR 请求分析生成，查询pod示例状态、下载日志等。

用法示例:
    from api_tools.iomp_log_download import IompLogDownloader
    downloader = IompLogDownloader()
    # 下载单个微服务日志
    downloader.download_service_log("la-atc-ws-backend", namespace="kedacom-project-namespace")
    # 批量下载 namespace 下所有微服务日志
    downloader.download_all_logs(namespace="kedacom-project-namespace")
"""

import base64
import json
import os
import time
from datetime import datetime
from typing import List, Optional

import requests


class IompLogDownloader:
    """IOMP 平台微服务日志下载器"""

    # 微服务名称白名单（为空则下载 namespace 下全部）
    DEFAULT_SERVICE_NAMES: list[str] = ["la-atc-ws-backend", "la-atc-daemon-server"]

    # 默认配置（从 HAR 文件提取）
    DEFAULT_BASE_URL = "http://10.165.32.24:8801" #iomp地址
    DEFAULT_USERNAME = "wuweibin"   #iomp用户名
    DEFAULT_PASSWORD = "kedacom@123"   #iomp密码
    DEFAULT_CLUSTER_ID = ""   # 空字符串表示自动获取集群ID

    # 接口路径（从 HAR 请求分析）
    LOGIN_PATH = "/iomp/auth/login"
    NAMESPACE_DICT_PATH = "/iomp/namespace/data-dict"
    DEPLOYMENT_LIST_PATH = "/iomp/deployment"
    # 集群列表接口（按 IOMP 常见模式推导，用于自动获取 clusterId）
    CLUSTER_LIST_PATH = "/iomp/cluster"
    # 日志下载接口（从 10.165.32.24日志下载.har 提取）
    # GET /iomp/pod/log/download?name={podName}&clusterId={clusterId}&namespace={namespace}&containerId={containerId}
    LOG_DOWNLOAD_PATH = "/iomp/pod/log/download"
    # Pod 列表接口（按 IOMP 常见模式推导，用于获取 Pod 名称）
    POD_LIST_PATH = "/iomp/pod"
    STATEFULSET_LIST_PATH = "/iomp/statefulset"
    DAEMONSET_LIST_PATH = "/iomp/daemonset"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        username: str = DEFAULT_USERNAME,
        password: str = DEFAULT_PASSWORD,
        cluster_id: str = DEFAULT_CLUSTER_ID,
        output_dir: str = "./tmp/iomp_logs",
        service_names: Optional[list[str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.service_names = service_names or self.DEFAULT_SERVICE_NAMES
        self.session = requests.Session()
        self._logged_in = False

        # cluster_id 为空时尝试自动获取
        if not cluster_id:
            auto_id = self._get_cluster_id_auto()
            if auto_id:
                self.cluster_id = auto_id
                print(f"[自动获取集群ID] {auto_id}")
            else:
                raise RuntimeError("自动获取集群ID失败，请手动配置 cluster_id")
        else:
            self.cluster_id = cluster_id

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_cluster_id_auto(self) -> Optional[str]:
        """尝试自动获取第一个可用的 clusterId（需先登录）"""
        try:
            self.login()
            resp = self._request("GET", self.CLUSTER_LIST_PATH, timeout=10)
            data = resp.json()
            result = data.get("result", {})
            clusters = result.get("data", []) if isinstance(result, dict) else result
            if clusters and isinstance(clusters, list):
                return clusters[0].get("id") or clusters[0].get("clusterId")
        except Exception as e:
            print(f"[自动获取集群ID失败] {e}")
        return None

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: int = 30,
    ) -> requests.Response:
        """发送 HTTP 请求并自动处理异常"""
        url = f"{self.base_url}{path}"
        default_headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "max-age=20, public",
            "Connection": "keep-alive",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
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
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"[请求失败] {method.upper()} {url} -> {e}")
            raise

    def login(self) -> bool:
        """
        登录 IOMP 平台获取会话。
        对应 HAR 请求: POST /iomp/auth/login
        """
        if self._logged_in:
            return True

        payload = {
            "username": self.username,
            "password": base64.b64encode(self.password.encode()).decode(),
        }
        try:
            resp = self._request(
                "POST",
                self.LOGIN_PATH,
                json_data=payload,
                headers={"Content-Type": "application/json;charset=UTF-8"},
            )
            result = resp.json()
            if result.get("code") == "0" or result.get("status") == 200:
                self._logged_in = True
                print(f"[登录成功] user={self.username}")
                return True
            else:
                print(f"[登录失败] 响应: {result}")
                return False
        except Exception as e:
            print(f"[登录异常] {e}")
            return False

    def get_namespaces(self) -> List[dict]:
        """
        获取 namespace 列表。
        对应 HAR 请求: GET /iomp/namespace/data-dict?clusterId=xxx
        """
        self.login()
        params = {"clusterId": self.cluster_id}
        resp = self._request("GET", self.NAMESPACE_DICT_PATH, params=params)
        data = resp.json()
        result = data.get("result", [])
        namespaces = result if isinstance(result, list) else []
        print(f"[获取命名空间] 共 {len(namespaces)} 个")
        return namespaces

    def get_deployments(
        self,
        namespace: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[dict]:
        """
        获取微服务(Deployment)列表。
        对应 HAR 请求: GET /iomp/deployment?clusterId=xxx&name=xxx&phase=ALL&...
        """
        self.login()
        params = {
            "clusterId": self.cluster_id,
            "phase": "ALL",
            "pageNo": 0,
            "pageSize": 1000,
            "f_eq_hostIp": "",
            "scriptType": "normal",
            "type": "Deployment",
        }
        if namespace:
            params["namespace"] = namespace
        if name:
            params["name"] = name

        resp = self._request("GET", self.DEPLOYMENT_LIST_PATH, params=params)
        data = resp.json()
        result = data.get("result", {})
        deployments = result.get("data", []) if isinstance(result, dict) else []
        print(f"[获取微服务列表] namespace={namespace or '全部'}, 共 {len(deployments)} 个")
        return deployments

    def get_statefulsets(
        self,
        namespace: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[dict]:
        """
        获取 StatefulSet 列表。
        对应 HAR 请求: GET /iomp/statefulset?clusterId=xxx&phase=ALL&...
        注意: 该接口不支持 namespace 过滤，获取全部后在客户端过滤。
        """
        self.login()
        params = {
            "clusterId": self.cluster_id,
            "phase": "ALL",
            "pageNo": 0,
            "pageSize": 1000,
            "f_eq_hostIp": "",
            "scriptType": "normal",
            "type": "StatefulSet",
        }
        if name:
            params["name"] = name

        resp = self._request("GET", self.STATEFULSET_LIST_PATH, params=params)
        data = resp.json()
        result = data.get("result", {})
        statefulsets = result.get("data", []) if isinstance(result, dict) else []
        if namespace:
            statefulsets = [s for s in statefulsets if s.get("namespace") == namespace]
        print(f"[获取StatefulSet列表] namespace={namespace or '全部'}, 共 {len(statefulsets)} 个")
        return statefulsets

    def get_daemonsets(
        self,
        namespace: Optional[str] = None,
        name: Optional[str] = None,
    ) -> List[dict]:
        """
        获取 DaemonSet 列表。
        对应 HAR 请求: GET /iomp/daemonset?clusterId=xxx&phase=ALL&...
        注意: 该接口不支持 namespace 过滤，获取全部后在客户端过滤。
        """
        self.login()
        params = {
            "clusterId": self.cluster_id,
            "phase": "ALL",
            "pageNo": 0,
            "pageSize": 1000,
            "f_eq_hostIp": "",
            "scriptType": "normal",
            "type": "DaemonSet",
        }
        if name:
            params["name"] = name

        resp = self._request("GET", self.DAEMONSET_LIST_PATH, params=params)
        data = resp.json()
        result = data.get("result", {})
        daemonsets = result.get("data", []) if isinstance(result, dict) else []
        if namespace:
            daemonsets = [d for d in daemonsets if d.get("namespace") == namespace]
        print(f"[获取DaemonSet列表] namespace={namespace or '全部'}, 共 {len(daemonsets)} 个")
        return daemonsets

    def get_all_services(
        self,
        namespace: Optional[str] = None,
    ) -> List[dict]:
        """
        获取指定 namespace 下所有类型服务（Deployment + StatefulSet + DaemonSet）。
        返回列表中每个 dict 会增加 _type 字段标识类型。
        """
        deps = self.get_deployments(namespace=namespace)
        sts = self.get_statefulsets(namespace=namespace)
        ds = self.get_daemonsets(namespace=namespace)

        for d in deps:
            d["_type"] = "Deployment"
        for s in sts:
            s["_type"] = "StatefulSet"
        for d in ds:
            d["_type"] = "DaemonSet"

        all_services = deps + sts + ds
        return all_services

    def get_abnormal_services(
        self,
        namespace: Optional[str] = None,
    ) -> List[dict]:
        """
        获取异常服务列表。
        异常定义: replicas > 0 且 readyReplicas != replicas
        """
        all_services = self.get_all_services(namespace=namespace)
        abnormal = []
        for svc in all_services:
            ready = svc.get("readyReplicas") or 0
            replicas = svc.get("replicas") or 0
            if replicas > 0 and ready != replicas:
                abnormal.append(svc)
        return abnormal

    def print_service_status(
        self,
        namespace: Optional[str] = None,
    ) -> None:
        """
        打印指定 namespace 下所有服务状态，并高亮异常服务。
        """
        all_services = self.get_all_services(namespace=namespace)
        print(f"\n{'类型':<12} {'名称':<40} {'pods':<10} {'状态'}")
        print("-" * 80)
        for svc in all_services:
            ready = svc.get("readyReplicas") or 0
            replicas = svc.get("replicas") or 0
            is_abnormal = replicas > 0 and ready != replicas
            status = "[异常]" if is_abnormal else "正常"
            print(f"{svc['_type']:<12} {svc['name']:<40} {ready}/{replicas:<8} {status}")

        abnormal = [s for s in all_services if s.get("replicas", 0) > 0 and (s.get("readyReplicas") or 0) != s.get("replicas", 0)]
        if abnormal:
            print(f"\n[异常服务汇总] 共 {len(abnormal)} 个:")
            for svc in abnormal:
                ready = svc.get("readyReplicas") or 0
                replicas = svc.get("replicas") or 0
                print(f"  - {svc['_type']} {svc['name']} (pods={ready}/{replicas})")
        else:
            print("\n[异常服务汇总] 无异常")

    def get_pods(
        self,
        namespace: str,
        deployment_name: Optional[str] = None,
    ) -> List[dict]:
        """
        获取 Pod 列表。
        优先尝试 GET /iomp/pod，若未返回目标 Pod 则回退到 deployment 详情接口。
        """
        self.login()

        # 尝试 1：调用 Pod 列表接口
        params = {
            "clusterId": self.cluster_id,
            "namespace": namespace,
            "pageNo": 0,
            "pageSize": 1000,
            "type": "Pod",
        }
        if deployment_name:
            params["deploymentName"] = deployment_name

        pods = []
        try:
            resp = self._request("GET", self.POD_LIST_PATH, params=params)
            data = resp.json()
            result = data.get("result", {})
            pods = result.get("data", []) if isinstance(result, dict) else []
        except Exception as e:
            print(f"[获取Pod列表失败] {e}")

        # 尝试 2：若未获取到且指定了 deployment_name，调用 deployment 详情接口
        if not pods and deployment_name:
            try:
                dep_params = {
                    "clusterId": self.cluster_id,
                    "namespace": namespace,
                    "name": deployment_name,
                    "phase": "ALL",
                    "pageNo": 0,
                    "pageSize": 1,
                    "type": "Deployment",
                }
                resp = self._request("GET", self.DEPLOYMENT_LIST_PATH, params=dep_params)
                data = resp.json()
                dep = data.get("result", {}).get("data", [])
                if dep and isinstance(dep, list):
                    pods = dep[0].get("pods") or []
            except Exception as e:
                print(f"[获取deployment详情失败] {e}")

        print(f"[获取Pod列表] namespace={namespace}, deployment={deployment_name or '全部'}, 共 {len(pods)} 个")
        return pods

    def download_pod_log(
        self,
        pod_name: str,
        namespace: str = "kedacom-project-namespace",
        container_id: str = "",
        output_filename: Optional[str] = None,
    ) -> str:
        """
        下载指定 Pod 的日志。
        对应 HAR 请求: GET /iomp/pod/log/download?name={podName}&clusterId=xxx&namespace=xxx&containerId=xxx

        参数:
            pod_name: Pod 完整名称，如 "la-atc-biz-backend-776776f6c5-52rr9"
            namespace: 命名空间
            container_id: 容器 ID（多容器场景需指定，默认空字符串）
            output_filename: 自定义输出文件名，默认从响应头 Content-Disposition 提取

        返回:
            保存的日志文件绝对路径
        """
        self.login()

        # 构建下载参数（严格匹配 HAR 中的 queryString）
        download_params = {
            "name": pod_name,
            "clusterId": self.cluster_id,
            "namespace": namespace,
            "containerId": container_id,
        }

        url = f"{self.base_url}{self.LOG_DOWNLOAD_PATH}"
        print(f"[开始下载] Pod={pod_name}, containerId={container_id or 'default'} -> {url}")

        try:
            resp = self.session.get(url, params=download_params, timeout=120, stream=True)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[下载失败] {pod_name}: {e}")
            content = f"# 日志下载失败\n# Pod: {pod_name}\n# 错误: {e}\n".encode("utf-8")
            # 若用户未指定文件名，使用 pod 名
            if not output_filename:
                output_filename = f"{pod_name}_failed.log"
        else:
            content = resp.content
            # 尝试从响应头提取文件名
            if not output_filename:
                cd = resp.headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    output_filename = cd.split("filename=")[-1].strip().strip('"')
                else:
                    output_filename = f"{pod_name}-log.txt"

        # 生成输出路径
        file_path = os.path.join(self.output_dir, output_filename)
        with open(file_path, "wb") as f:
            f.write(content)

        print(f"[下载完成] 已保存 -> {file_path} ({len(content)} bytes)")
        return os.path.abspath(file_path)

    def download_service_log(
        self,
        service_name: str,
        namespace: str = "kedacom-project-namespace",
        container_id: str = "",
        output_filename: Optional[str] = None,
    ) -> str:
        """
        下载指定微服务的日志（自动查找对应 Pod）。
        若配置了 service_names 白名单，非白名单服务将被拒绝。

        参数:
            service_name: Deployment/微服务名称，如 "la-atc-biz-backend"
            namespace: 命名空间
            container_id: 容器 ID（多容器场景需指定）
            output_filename: 自定义输出文件名

        返回:
            保存的日志文件绝对路径
        """
        self.login()

        # 白名单校验
        if self.service_names and service_name not in self.service_names:
            raise ValueError(
                f"服务 '{service_name}' 不在白名单 {self.service_names} 中，跳过下载"
            )

        # 获取该服务下的 Pod 列表
        pods = self.get_pods(namespace=namespace, deployment_name=service_name)

        # 按 deployment 名称匹配正确的 Pod（接口可能返回全部 Pod）
        matched_pods = [
            pod for pod in pods
            if pod.get("name", "").startswith(service_name + "-")
            or pod.get("name") == service_name
        ]

        if not matched_pods:
            # 降级：直接用 service_name 作为 pod_name 尝试下载
            print(f"[警告] 未找到 {service_name} 的 Pod 信息，尝试直接用名称下载")
            return self.download_pod_log(
                pod_name=service_name,
                namespace=namespace,
                container_id=container_id,
                output_filename=output_filename,
            )

        target_pod = matched_pods[0]
        pod_name = target_pod.get("name", service_name)
        return self.download_pod_log(
            pod_name=pod_name,
            namespace=namespace,
            container_id=container_id,
            output_filename=output_filename,
        )

    def download_all_logs(
        self,
        namespace: str = "kedacom-project-namespace",
    ) -> List[str]:
        """
        批量下载指定 namespace 下微服务的日志。
        若配置了 service_names，则只下载白名单内的服务。

        返回:
            下载成功的日志文件路径列表
        """
        deployments = self.get_deployments(namespace=namespace)
        downloaded_files = []

        # 过滤目标服务
        target_names = set(self.service_names) if self.service_names else None
        filtered_deps = [
            dep for dep in deployments
            if not target_names or dep.get("name") in target_names
        ]

        print(f"[批量下载] 白名单: {target_names or '全部'}, 匹配到 {len(filtered_deps)} 个服务")

        for dep in filtered_deps:
            svc_name = dep.get("name")
            if not svc_name:
                continue
            try:
                path = self.download_service_log(
                    service_name=svc_name,
                    namespace=namespace,
                )
                downloaded_files.append(path)
            except Exception as e:
                print(f"[跳过] {svc_name}: {e}")
            # 简单限速，避免对服务端造成压力
            time.sleep(0.5)

        print(f"\n[批量下载完成] 成功 {len(downloaded_files)} / 目标 {len(filtered_deps)}")
        return downloaded_files


def main():
    """命令行入口示例"""
    downloader = IompLogDownloader(
        base_url="http://10.165.32.24:8801",
        username="wuweibin",
        password="kedacom@123",
        cluster_id="02b01cdf6b534d80a67d8b1994870547",
        output_dir="./tmp/iomp_logs",
        # service_names 不传入时，使用类变量 DEFAULT_SERVICE_NAMES
    )

    # 示例 1：列出所有 namespace
    print("=== Namespace 列表 ===")
    for ns in downloader.get_namespaces():
        print(f"  - {ns.get('name')} (id={ns.get('id')})")

    # 示例 2：列出指定 namespace 下的微服务（含 Pod 运行状态）
    target_ns = "kedacom-project-namespace"
    print(f"\n=== {target_ns} 下的微服务 ===")
    for dep in downloader.get_deployments(namespace=target_ns):
        dep_name = dep.get("name", "")
        replicas = dep.get("replicas") or 0
        ready = dep.get("readyReplicas") or 0
        print(f"  - {dep_name} (pods={ready}/{replicas})")

    # 示例 3：批量下载 namespace 下白名单微服务日志
    print("\n=== 批量下载白名单微服务日志 ===")
    downloader.download_all_logs(namespace=target_ns)

    # 示例 4：服务状态监控（Deployment + StatefulSet + DaemonSet）
    print("\n=== 服务状态监控 ===")
    downloader.print_service_status(namespace=target_ns)

    # 示例 5：获取异常服务列表（可被其他脚本调用）
    print("\n=== 异常服务列表 ===")
    abnormal = downloader.get_abnormal_services(namespace=target_ns)
    if abnormal:
        for svc in abnormal:
            ready = svc.get("readyReplicas") or 0
            replicas = svc.get("replicas") or 0
            print(f"  [异常] {svc['_type']} {svc['name']} (pods={ready}/{replicas})")
    else:
        print("  无异常服务")

    # 示例 6：如需单独下载某个微服务，可取消注释并指定名称
    # print("\n=== 下载单个微服务日志 ===")
    # try:
    #     downloader.download_service_log("la-atc-biz-backend", namespace=target_ns)
    # except ValueError as e:
    #     print(f"[跳过] {e}")


if __name__ == "__main__":
    main()
