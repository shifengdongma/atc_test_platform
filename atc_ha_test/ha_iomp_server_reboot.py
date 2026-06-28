# -*- coding: utf-8 -*-
"""
高可用 IOMP 双集群服务重启脚本

功能：
- 对 A/B 两个 IOMP 集群中的指定服务进行重启
- 支持批量服务重启
- 重启后可选检查服务状态（readyReplicas / replicas）

用法示例：
    # 重启双集群的 la-atc-biz-backend
    python ha_iomp_server_reboot.py --service la-atc-biz-backend

    # 批量重启多个服务（双集群）
    python ha_iomp_server_reboot.py --service la-atc-biz-backend --service la-atc-daemon-server

    # 仅重启 A 集群，不检查状态
    python ha_iomp_server_reboot.py --cluster a --service la-atc-biz-backend --no-check

    # 重启后等待 60 秒再检查
    python ha_iomp_server_reboot.py --service la-atc-biz-backend --wait 60
"""

import os
import sys
import time
import argparse
from typing import List, Dict, Any, Optional

# ── 路径配置 ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
PROJECT_ROOT = os.path.dirname(ENGINE_DIR)
IOMP_TOOLS_DIR = os.path.join(PROJECT_ROOT, "atcapi_autotest")

sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, IOMP_TOOLS_DIR)

from api_tools.iomp_api_servers_ops import IompServiceManager

# 从 ha_env.py 加载 IOMP 配置
try:
    from ha_env import (
        iomp_ip_a, iomp_port_a, ACCESS_KEY_a,
        iomp_ip_b, iomp_port_b, ACCESS_KEY_b,
    )
    HA_ENV_OK = True
except Exception as e:
    print(f"[错误] 无法加载 ha_env.py: {e}")
    HA_ENV_OK = False
    iomp_ip_a = iomp_ip_b = ""
    iomp_port_a = iomp_port_b = 8801
    ACCESS_KEY_a = ACCESS_KEY_b = ""


# ── 集群配置 ──
_CLUSTER_A = {
    "label": "A",
    "base_url": f"http://{iomp_ip_a}:{iomp_port_a}",
    "accesskey": ACCESS_KEY_a,
}
_CLUSTER_B = {
    "label": "B",
    "base_url": f"http://{iomp_ip_b}:{iomp_port_b}",
    "accesskey": ACCESS_KEY_b,
}

# IOMP 集群名称（已确认 A/B 均为 "dk"）
_CLUSTER_NAME = "dk"
_DEFAULT_NAMESPACE = "kedacom-project-namespace"

# ═══════════════════════════════════════════════════════════════════
# IDE 直接执行配置区（无需命令行参数，修改此处即可在 IDE 运行）
# ═══════════════════════════════════════════════════════════════════
# 开关：设为 True 时，IDE 中直接运行本脚本将使用下方默认参数
IDE_QUICK_RUN = True

# 默认重启配置（IDE 直接执行时生效）
DEFAULT_SERVICES = [
    "la-atc-biz-backend",
    "la-atc-ws-backend-atc",
    "utm_conflicts",
    "utm_mid_conflicts_server",
    "utm_server",
]       # 要重启的服务列表，可填多个服务名
DEFAULT_NAMESPACE = "kedacom-project-namespace"  # Kubernetes 命名空间
DEFAULT_CLUSTER = "both"                        # 目标集群："a" / "b" / "both"
DEFAULT_WAIT = 30                               # 重启后等待秒数再检查 Pod 状态
DEFAULT_NO_CHECK = False                        # True=跳过状态检查，False=开启状态检查
# ═══════════════════════════════════════════════════════════════════


# ── 初始化 IOMP 管理器 ──
def create_manager(cluster_cfg: Dict[str, str]) -> Optional[IompServiceManager]:
    """根据集群配置创建 IompServiceManager"""
    try:
        mgr = IompServiceManager(
            base_url=cluster_cfg["base_url"],
            accesskey=cluster_cfg["accesskey"],
            timeout=60,
        )
        # 验证连接
        token = mgr._get_token()
        if token:
            print(f"[{cluster_cfg['label']}-集群] IOMP 连接成功: {cluster_cfg['base_url']}")
            return mgr
        else:
            print(f"[{cluster_cfg['label']}-集群] IOMP Token 获取失败")
            return None
    except Exception as e:
        print(f"[{cluster_cfg['label']}-集群] IOMP 初始化失败: {e}")
        return None


# ── 重启服务 ──
def reboot_service(
    mgr: IompServiceManager,
    cluster_label: str,
    cluster_name: str,
    namespace: str,
    service_name: str,
) -> bool:
    """重启指定服务，返回是否成功"""
    print(f"[{cluster_label}-集群] 重启服务: {service_name} ... ", end="", flush=True)
    try:
        result = mgr.reboot_service(cluster_name, namespace, service_name)
        if result.get("_error"):
            print(f"失败 | {result['_error']}")
            return False
        print("成功")
        return True
    except Exception as e:
        print(f"异常 | {e}")
        return False


# ── 检查服务状态 ──
def check_service_status(
    mgr: IompServiceManager,
    cluster_label: str,
    cluster_name: str,
    namespace: str,
    service_name: str,
) -> bool:
    """检查服务 readyReplicas / replicas 是否一致"""
    try:
        result = mgr.query_service(cluster_name, namespace, "All", service_name)
        if result.get("_error"):
            print(f"[{cluster_label}-集群] {service_name} 状态查询失败: {result['_error']}")
            return False

        data = result.get("result", {})
        if not isinstance(data, dict):
            print(f"[{cluster_label}-集群] {service_name} 状态查询返回格式异常")
            return False

        ready = data.get("readyReplicas", 0)
        replicas = data.get("replicas", 0)
        name = data.get("name", service_name)

        if replicas > 0 and ready == replicas:
            print(f"[{cluster_label}-集群] {name} 状态: {ready}/{replicas} 正常")
            return True
        elif replicas > 0:
            print(f"[{cluster_label}-集群] {name} 状态: {ready}/{replicas} [异常] ready 副本数不足")
            return False
        else:
            print(f"[{cluster_label}-集群] {name} 状态: {ready}/{replicas} [未知]")
            return False
    except Exception as e:
        print(f"[{cluster_label}-集群] {service_name} 状态检查异常: {e}")
        return False


# ── 主函数 ──
def main():
    # IDE 快速运行模式：绕过命令行解析，直接使用上方默认参数
    if IDE_QUICK_RUN:
        args = argparse.Namespace(
            service=DEFAULT_SERVICES,
            namespace=DEFAULT_NAMESPACE,
            cluster=DEFAULT_CLUSTER,
            wait=DEFAULT_WAIT,
            no_check=DEFAULT_NO_CHECK,
        )
    else:
        parser = argparse.ArgumentParser(
            description="高可用 IOMP 双集群服务重启脚本",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument(
            "--service",
            type=str,
            action="append",
            default=DEFAULT_SERVICES,
            help=f"指定要重启的服务名，可多次使用（默认: {DEFAULT_SERVICES}）",
        )
        parser.add_argument(
            "--namespace",
            type=str,
            default=DEFAULT_NAMESPACE,
            help=f"命名空间（默认: {DEFAULT_NAMESPACE}）",
        )
        parser.add_argument(
            "--cluster",
            type=str,
            choices=["a", "b", "both"],
            default=DEFAULT_CLUSTER,
            help=f"目标集群 a/b/both（默认: {DEFAULT_CLUSTER}）",
        )
        parser.add_argument(
            "--wait",
            type=int,
            default=DEFAULT_WAIT,
            help=f"重启后等待秒数再检查状态（默认: {DEFAULT_WAIT}）",
        )
        parser.add_argument(
            "--no-check",
            action="store_true",
            default=DEFAULT_NO_CHECK,
            help="跳过重启后状态检查",
        )
        args = parser.parse_args()

    if not HA_ENV_OK:
        print("[错误] ha_env.py 加载失败，无法继续")
        sys.exit(1)

    services = args.service
    namespace = args.namespace
    check_enabled = not args.no_check
    wait_sec = args.wait

    # 确定目标集群
    clusters = []
    if args.cluster in ("a", "both"):
        clusters.append(_CLUSTER_A)
    if args.cluster in ("b", "both"):
        clusters.append(_CLUSTER_B)

    print("=" * 70)
    print("高可用 IOMP 双集群服务重启")
    print("=" * 70)
    print(f"目标服务: {', '.join(services)}")
    print(f"命名空间: {namespace}")
    print(f"目标集群: {args.cluster}")
    print(f"状态检查: {'开启' if check_enabled else '跳过'}")
    if check_enabled:
        print(f"等待时间: {wait_sec}s")
    print("=" * 70)

    # ── 初始化 IOMP 管理器 ──
    managers: Dict[str, IompServiceManager] = {}
    for cfg in clusters:
        mgr = create_manager(cfg)
        if mgr:
            managers[cfg["label"]] = mgr

    if not managers:
        print("[错误] 所有集群 IOMP 连接失败，退出")
        sys.exit(1)

    # ── 执行重启 ──
    reboot_results: Dict[str, Dict[str, bool]] = {}
    for svc in services:
        reboot_results[svc] = {}
        print(f"\n--- 服务: {svc} ---")
        for cfg in clusters:
            label = cfg["label"]
            mgr = managers.get(label)
            if not mgr:
                continue
            ok = reboot_service(mgr, label, _CLUSTER_NAME, namespace, svc)
            reboot_results[svc][label] = ok

    # ── 状态检查 ──
    if check_enabled:
        print(f"\n等待 {wait_sec} 秒，待 Pod 重启完成...")
        time.sleep(wait_sec)

        print("\n" + "=" * 70)
        print("服务状态检查")
        print("=" * 70)

        all_ok = True
        for svc in services:
            print(f"\n--- 服务: {svc} ---")
            for cfg in clusters:
                label = cfg["label"]
                mgr = managers.get(label)
                if not mgr:
                    continue
                if not reboot_results[svc].get(label, False):
                    print(f"[{label}-集群] {svc} 跳过检查（重启失败）")
                    all_ok = False
                    continue
                ok = check_service_status(mgr, label, _CLUSTER_NAME, namespace, svc)
                if not ok:
                    all_ok = False

        print("\n" + "=" * 70)
        if all_ok:
            print("所有服务状态正常")
        else:
            print("部分服务状态异常，请检查")
        print("=" * 70)
    else:
        print("\n[提示] 已跳过状态检查，如需检查请使用 --check 参数")

    print("\n执行完毕")


if __name__ == "__main__":
    main()
