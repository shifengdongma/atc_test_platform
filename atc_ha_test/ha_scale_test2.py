#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HA 一键缩容测试脚本 V2.0

优化特性：
1. 支持 CLI 参数配置
2. 标准日志系统
3. 检查点解耦
4. 并行日志下载
5. 常量统一管理
6. 异常恢复独立方法
7. JSON 报告输出
8. WS 检查可选配置

使用方式：
    python ha_scale_test2.py [参数]
    python ha_scale_test2.py --service la-atc-biz-backend --rounds 2 --dry-run

配置示例：
    --service, -s        目标服务名（默认：la-atc-biz-backend）
    --namespace, -n      命名空间（默认：kedacom-project-namespace）
    --cluster, -c        集群名称（默认：dk）
    --kind, -k          资源类型（默认：All）
    --rounds, -r        测试轮次（默认：1）
    --wait, -w          缩容后等待秒数（默认：300）
    --master            主集群：auto/A/B（默认：auto）
    --dry-run           只模拟流程
    --analysis, -a      日志分析窗口分钟数（默认：10）
    --report-json       输出详细JSON报告文件
    --report-dir, -d    报告输出目录（默认：log/）

开发文档说明：
https://claude.ai/claude/models/zai-org/GLM-4.5-Air
"""

import os
import sys
import time
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
import argparse
import json
import logging
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# 模块级 logger，确保类方法中可直接使用
logger = logging.getLogger("ha_scale_test2")

# ==================== 路径处理 ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
API_TOOLS_DIR = os.path.join(PROJECT_ROOT, "atcapi_autotest", "api_tools")
if API_TOOLS_DIR not in sys.path:
    sys.path.insert(0, API_TOOLS_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ==================== 导入依赖 ====================
from iomp_api_servers_ops import IompServiceManager
from ha_log_download_analysis import HaLogAnalyzer
from ha_env import iomp_ip_a, iomp_port_a, ACCESS_KEY_a, iomp_ip_b, iomp_port_b, ACCESS_KEY_b, cluster_api
from ws_client_check import run_ws_check
import iomp_query
from iomp_query import ServiceConfig, IOMPQueryClient, print_comparison_table
from dm_ha_client import DmDbClient, DB_CONFIG_A, DB_CONFIG_B

# ==================== 配置常量类 ====================
class TestConfig:
    """测试配置常量"""
    # 超时配置
    POLL_TIMEOUT_SECONDS = 300
    CLUSTER_API_TIMEOUT = 10
    RECOVERY_TIMEOUT = 300

    # 等待配置
    SWITCH_DETECT_INTERVAL = 5       # 主集群检测间隔(秒)
    SWITCH_DETECT_EXTRA_WAIT = 120   # 检测到切换后额外等待(秒)
    DEFAULT_POLL_INTERVAL = 5        # 状态轮询间隔(秒)

    # 日志配置
    MIN_ANALYSIS_MINUTES = 5
    ROUND_COOLDOWN_FACTOR = 30       # 轮次间隔 = analysis_minutes * this

    # 重试配置
    MAX_API_ERROR_COUNT = 2

@dataclass
class CheckpointResult:
    """检查点结果"""
    name: str
    status: str  # "一致" | "不一致" | "检查失败" | "已检查"
    detail: str = ""
    timestamp: str = ""

class Checkpoint(ABC):
    """检查点抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str: pass

    @abstractmethod
    def run(self) -> CheckpointResult: pass

class RedisCheckpoint(Checkpoint):
    """Redis 双集群一致性检查"""

    @property
    def name(self) -> str: return "Redis"

    def run(self) -> CheckpointResult:
        try:
            import importlib
            redis_module = importlib.import_module("redis_sync_check")
            import io
            old_stdout = sys.stdout
            buf = io.StringIO()
            sys.stdout = buf
            try:
                redis_module.check_redis_consistency()
            finally:
                sys.stdout = old_stdout
            output = buf.getvalue()

            is_consistent = (
                "数据不一致的Key数: 0" in output
                and "至少在一个Redis实例中不存在的Key数: 0" in output
            )

            status = "一致" if is_consistent else "不一致"
            logger.info(f"[{self.name}] 数据{'一致' if is_consistent else '不一致'}")

            return CheckpointResult(
                name=self.name,
                status=status,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            )
        except Exception as e:
            logger.error(f"[{self.name}] 检查失败: {e}")
            return CheckpointResult(
                name=self.name,
                status="检查失败",
                detail=str(e),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            )

class EsCheckpoint(Checkpoint):
    """ES 双集群一致性检查"""

    @property
    def name(self) -> str: return "ES"

    def run(self) -> CheckpointResult:
        try:
            from ha_env import es_hosts
            servers = [f"http://{host}" for host in es_hosts]
            if len(servers) < 2:
                logger.warning("[ES] 未配置双集群 ES 地址")
                return CheckpointResult(
                    name=self.name,
                    status="未配置",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )

            # 时间范围：前推30分钟
            end_time = datetime.now().astimezone()
            start_time = end_time - timedelta(minutes=30)
            slice_minutes = 5
            index_pattern = "uav_runtime_data*"
            time_field = "timestamp"

            spans = 0
            current = start_time
            slices = []
            while current < end_time:
                slice_end = min(current + timedelta(minutes=slice_minutes), end_time)
                spans += 1
                slices.append((current, slice_end))
                current = slice_end

            def _es_count(server: str, s: datetime, e: datetime) -> int:
                url = f"{server}/{index_pattern}/_count"
                query = {
                    "query": {
                        "range": {
                            time_field: {
                                "gte": int(s.timestamp() * 1000),
                                "lt": int(e.timestamp() * 1000)
                            }
                        }
                    }
                }
                try:
                    resp = requests.post(url, json=query, timeout=10)
                    if resp.status_code == 200:
                        return resp.json().get("count", -1)
                    else:
                        logger.warning(f"ES请求失败: {resp.status_code}")
                except Exception:
                    logger.warning(f"ES查询异常: {server}")
                return -1

            # 检查服务器可达性
            reach = []
            for server in servers:
                try:
                    requests.head(server, timeout=5)
                    reach.append(True)
                except Exception:
                    reach.append(False)

            if not any(reach):
                logger.error("[ES] 两个 ES 服务器均不可达")
                return CheckpointResult(
                    name=self.name,
                    status="服务器不可达",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )

            all_match = True
            mismatches = []
            total_a = 0
            total_b = 0

            for slice_start, slice_end in slices:
                count_a = _es_count(servers[0], slice_start, slice_end) if reach[0] else -1
                count_b = _es_count(servers[1], slice_start, slice_end) if reach[1] else -1

                if count_a > 0: total_a += count_a
                if count_b > 0: total_b += count_b

                label = f"{slice_start.strftime('%m-%d %H:%M')} ~ {slice_end.strftime('%H:%M')}"

                if count_a == -1 or count_b == -1:
                    all_match = False
                    mismatches.append(f"{label}: 无法获取")
                elif count_a != count_b:
                    all_match = False
                    mismatches.append(f"{label}: {count_a} vs {count_b}(差{abs(count_a - count_b)})")

            if all_match:
                logger.info(f"[ES] 所有切片一致（{len(slices)}个切片，总数据量: {total_a}/{total_b}）")
                return CheckpointResult(
                    name=self.name,
                    status="一致",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )
            else:
                detail = "；".join(mismatches)
                logger.warning(f"[ES] 不一致切片: {len(mismatches)}/{len(slices)}，总计: {total_a} vs {total_b}")
                return CheckpointResult(
                    name=self.name,
                    status="不一致",
                    detail=detail,
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )
        except Exception as e:
            logger.error(f"[{self.name}] 检查失败: {e}")
            return CheckpointResult(
                name=self.name,
                status="检查失败",
                detail=str(e),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            )

class DmCheckpoint(Checkpoint):
    """达梦数据库双集群一致性检查"""

    @property
    def name(self) -> str: return "DM"

    def run(self) -> CheckpointResult:
        try:
            tables = [
                "uav_info", "flight_task", "flight_plan", "alert", "air_route",
            ]

            client_a = DmDbClient(**DB_CONFIG_A)
            client_b = DmDbClient(**DB_CONFIG_B)

            if not client_a.connect():
                logger.warning(f"[{self.name}] A集群数据库连接失败")
                client_a.close()
                return CheckpointResult(
                    name=self.name,
                    status="A集群连接失败",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )
            if not client_b.connect():
                logger.warning(f"[{self.name}] B集群数据库连接失败")
                client_a.close()
                client_b.close()
                return CheckpointResult(
                    name=self.name,
                    status="B集群连接失败",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )

            all_match = True
            mismatches = []
            try:
                for table in tables:
                    sql = f"SELECT COUNT(*) AS TOTAL FROM {client_a.schema}.{table}"
                    result_a = client_a.execute(sql, silent=True)
                    result_b = client_b.execute(sql, silent=True)

                    count_a = result_a[0].get("TOTAL", -1) if result_a else -1
                    count_b = result_b[0].get("TOTAL", -1) if result_b else -1

                    if count_a == -1 or count_b == -1:
                        all_match = False
                        mismatches.append(f"{table}: 查询异常")
                    elif count_a != count_b:
                        all_match = False
                        mismatches.append(f"{table}: {count_a} vs {count_b}")

                status = "一致" if all_match else "不一致"
                logger.info(f"[{self.name}] 所有 {len(tables)} 个关键表数据量{'一致性' if all_match else '不一致'}")
                return CheckpointResult(
                    name=self.name,
                    status=status,
                    detail="；".join(mismatches) if mismatches else "",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )
            finally:
                client_a.close()
                client_b.close()
        except Exception as e:
            logger.error(f"[{self.name}] 检查失败: {e}")
            return CheckpointResult(
                name=self.name,
                status="检查失败",
                detail=str(e),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            )

class ServicesCheckpoint(Checkpoint):
    """关键服务 A/B 双集群状态检查"""

    @property
    def name(self) -> str: return "关键服务"

    def run(self) -> CheckpointResult:
        try:
            logger.info("[关键服务] 开始查询 A/B 双集群关键服务...")
            node_results = {}

            for node in iomp_query.IOMP_NODES:
                query_config = iomp_query.QueryConfig(
                    ip=node['ip'],
                    port=node['port'],
                    access_key=node['access_key'],
                    services=[ServiceConfig(**cfg) for cfg in iomp_query.EXPANDED_SERVICE_CONFIGS]
                )
                client = IOMPQueryClient(query_config, log_level="INFO")
                results = client.query_all_services()
                node_results[node['name']] = results
                logger.info(f"[关键服务] {node['name']} 查询完成: {len(results)} 个服务")

            if len(iomp_query.IOMP_NODES) >= 2:
                a_name = iomp_query.IOMP_NODES[0]['name']
                b_name = iomp_query.IOMP_NODES[1]['name']
                print_comparison_table(
                    node_results.get(a_name, []),
                    node_results.get(b_name, []),
                    node_a_name=a_name,
                    node_b_name=b_name
                )
                return CheckpointResult(
                    name=self.name,
                    status="已检查",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )
            else:
                logger.info("[关键服务] 单节点模式，仅输出汇总")
                return CheckpointResult(
                    name=self.name,
                    status="单节点",
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                )
        except Exception as e:
            logger.error(f"[{self.name}] 检查失败: {e}")
            return CheckpointResult(
                name=self.name,
                status="检查失败",
                detail=str(e),
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            )

# ==================== 配置函数 ====================
def parse_args():
    """命令行参数解析"""
    parser = argparse.ArgumentParser(description="HA 一键缩容测试 v2.0")
    parser.add_argument("--service", "-s", default="la-atc-biz-backend", help="目标服务名")
    parser.add_argument("--namespace", "-n", default="kedacom-project-namespace", help="命名空间")
    parser.add_argument("--cluster", "-c", default="dk", help="集群名称")
    parser.add_argument("--kind", "-k", default="All", help="资源类型")
    parser.add_argument("--rounds", "-r", type=int, default=1, help="测试轮次")
    parser.add_argument("--wait", "-w", type=int, default=300, help="等待秒数")
    parser.add_argument("--master", choices=["auto", "A", "B"], default="auto", help="主集群")
    parser.add_argument("--dry-run", action="store_true", help="只模拟流程")
    parser.add_argument("--analysis", "-a", type=int, default=10, help="日志分析窗口(分钟)")
    parser.add_argument("--report-json", action="store_true", help="输出详细JSON报告")
    parser.add_argument("--report-dir", "-d", default="log", help="报告输出目录")
    parser.add_argument("--disable-ws", action="store_true", help="禁用WS检查")
    return parser.parse_args()

def setup_logging(log_dir: str):
    """设置日志系统"""
    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 生成日志文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"ha_scale_test2_{timestamp}.txt")

    # 配置日志
    logger = logging.getLogger("ha_scale_test2")
    logger.setLevel(logging.INFO)

    # 创建格式化器
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    logger.info(f"日志文件已创建: {log_file}")
    return logger, log_file

# ==================== 工具函数 ====================
def _fmt_now() -> str:
    """格式化当前时间"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

# ==================== IOMP 节点配置 ====================
IOMP_NODES: Dict[str, dict] = {
    "A": {
        "ip": iomp_ip_a,
        "port": iomp_port_a,
        "access_key": ACCESS_KEY_a,
        "name": "集群A",
        "base_url": f"http://{iomp_ip_a}:{iomp_port_a}",
    },
    "B": {
        "ip": iomp_ip_b,
        "port": iomp_port_b,
        "access_key": ACCESS_KEY_b,
        "name": "集群B",
        "base_url": f"http://{iomp_ip_b}:{iomp_port_b}",
    },
}

# ==================== HA 测试器类 ====================
class HaScaleTester2:
    """HA 缩容测试器 V2.0"""

    def __init__(
        self,
        args: argparse.Namespace,
        log_dir: str = "log",
        poll_interval: int = TestConfig.DEFAULT_POLL_INTERVAL,
        poll_timeout: int = TestConfig.POLL_TIMEOUT_SECONDS,
        ws_check_duration: int = 30,
        enable_ws_check: bool = True
    ):
        self.args = args
        self.log_dir = log_dir
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.ws_check_duration = ws_check_duration
        self.enable_ws_check = enable_ws_check

        # 初始化 IOMP 管理器
        self.managers: Dict[str, IompServiceManager] = {}
        for node_key, node_cfg in IOMP_NODES.items():
            self.managers[node_key] = IompServiceManager(
                base_url=node_cfg["base_url"],
                accesskey=node_cfg["access_key"]
            )

        self.round_results: List[dict] = []

    def get_service_replicas(self, node_key: str) -> Tuple[int, int]:
        """查询指定节点的目标服务副本状态"""
        manager = self.managers[node_key]
        result = manager.query_service(
            self.args.cluster,
            self.args.namespace,
            self.args.kind,
            self.args.service
        )

        if result.get("_error"):
            logger.error(f"[查询失败] {node_key} 节点 {self.args.service}: {result['_error']}")
            return -1, -1

        data = result.get("result", {})
        if not isinstance(data, dict):
            logger.error(f"[查询异常] {node_key} 节点返回格式不正确")
            return -1, -1

        ready = data.get("readyReplicas", 0)
        replicas = data.get("replicas", 0)
        ready = 0 if ready is None else ready
        replicas = 0 if replicas is None else replicas
        return ready, replicas

    def wait_for_replicas(self, node_key: str, expected_ready: int, expected_replicas: int) -> bool:
        """轮询等待服务达到指定副本状态"""
        if self.args.dry_run:
            logger.info(f"[DRY-RUN] 跳过状态轮询（ready={expected_ready}, replicas={expected_replicas}）")
            return True

        start_time = time.time()
        node_name = IOMP_NODES[node_key]["name"]

        if expected_replicas == 0:
            logger.info(f"[{node_name}] 轮询等待服务缩容...")
        else:
            logger.info(f"[{node_name}] 轮询等待服务恢复至 {expected_replicas} 副本...")

        last_ready = None
        last_replicas = None

        while time.time() - start_time < self.poll_timeout:
            ready, replicas = self.get_service_replicas(node_key)
            if ready == -1:
                logger.warning(f"  查询失败，{self.poll_interval}秒后重试...")
                time.sleep(self.poll_interval)
                continue

            # 只在状态变化时打印
            if ready != last_ready or replicas != last_replicas:
                logger.info(f"  当前状态: ready={ready}, replicas={replicas}")
                last_ready = ready
                last_replicas = replicas

            if ready == expected_ready and replicas == expected_replicas:
                elapsed = time.time() - start_time
                logger.info(f"  [状态达成] 耗时 {elapsed:.1f} 秒")
                return True

            time.sleep(self.poll_interval)

        logger.warning(f"  [等待超时] 超过 {self.poll_timeout} 秒仍未达到目标状态")
        return False

    def get_master_node(self) -> str:
        """获取主集群节点"""
        if self.args.master in ("A", "B"):
            logger.info(f"\n[主集群配置] 使用配置值: {IOMP_NODES[self.args.master]['name']}")
            return self.args.master

        return self.detect_master_node()

    def detect_master_node(self) -> Optional[str]:
        """自动判断主集群"""
        logger.info(f"\n[{'='*80}]")
        logger.info("[主集群自动判断]")
        logger.info(f"  方法: HTTP GET 查询 cluster_api")
        logger.info(f"  URL: {cluster_api}")
        logger.info(f"[{'='*80}]")

        try:
            urllib3.disable_warnings()
            response = requests.get(cluster_api, verify=False, timeout=10)
            response.raise_for_status()
            content = response.text.strip()

            logger.info(f"[查询结果] {content}")

            if "cluster_A" in content:
                master = "A"
            elif "cluster_B" in content:
                master = "B"
            else:
                master = None

            if master:
                logger.info(f"\n[主集群判断结果] {IOMP_NODES[master]['name']}")
                return master
        except Exception as e:
            logger.error(f"[查询失败] {e}")

        raise RuntimeError("无法确定主集群，请手动配置 --master 为 'A' 或 'B'")

    def scale_service(self, node_key: str, replicas: int) -> bool:
        """对指定节点的目标服务设置副本数"""
        node_name = IOMP_NODES[node_key]["name"]

        logger.info(f"\n[{'='*80}]")
        logger.info(f"[服务缩容/恢复] {node_name} -> {self.args.service} replicas={replicas}")
        logger.info(f"[{'='*80}]")

        if self.args.dry_run:
            logger.info(f"[DRY-RUN] 模拟设置副本数: {self.args.service} -> replicas={replicas}")
            logger.info(f"[DRY-RUN] 跳过实际 IOMP API 调用")
            return True

        manager = self.managers[node_key]
        result = manager.scale_service(
            self.args.cluster,
            self.args.namespace,
            self.args.service,
            replicas
        )

        if result.get("_error"):
            logger.error(f"[操作失败] {result['_error']}")
            return False

        status = result.get("status", result.get("code"))
        if status in (200, "0", 0):
            logger.info(f"[操作成功] 响应: {result}")
            return True
        else:
            logger.error(f"[操作异常] status={status}, 响应: {result}")
            return False

    def run_log_analysis(self, analysis_minutes: Optional[int] = None) -> List[dict]:
        """执行完整的双集群日志分析流程"""
        minutes = analysis_minutes if analysis_minutes is not None else self.args.analysis

        logger.info(f"\n[{'='*80}]")
        logger.info("[日志分析启动]")
        logger.info(f"  分析时间窗口: 最后 {minutes} 分钟")
        logger.info(f"[{'='*80}]")

        analyzer = HaLogAnalyzer(analysis_minutes=minutes)

        if len(analyzer.cluster_configs) != 2:
            logger.error("[错误] 必须配置两个集群")
            return []

        cluster_a = analyzer.cluster_configs[0]
        cluster_b = analyzer.cluster_configs[1]

        all_events: List[dict] = []
        try:
            # 并行下载日志
            with ThreadPoolExecutor(max_workers=2) as executor:
                logger.info("[日志下载] 开始并行下载双集群日志...")

                future_a = executor.submit(analyzer.download_cluster_logs, cluster_a)
                future_b = executor.submit(analyzer.download_cluster_logs, cluster_b)

                logs_a = future_a.result()
                logs_b = future_b.result()

            logger.info("[日志下载] 下载完成，开始分析...")

            # 1. 通用关键字对比
            results_a, start_a, end_a = analyzer._analyze_cluster_logs(logs_a)
            results_b, start_b, end_b = analyzer._analyze_cluster_logs(logs_b)

            # 打印分析时间范围
            if start_a and end_a:
                logger.info(f"[分析时间范围] {analyzer._fmt_ts(start_a)} ~ {analyzer._fmt_ts(end_a)}")

            logger.info(f"[分析完成] {cluster_a['name']} 关键字命中统计: ")
            for key, ts_list in sorted(results_a.items()):
                logger.info(f"  - {key}: {len(ts_list)} 次")
            logger.info(f"[分析完成] {cluster_b['name']} 关键字命中统计: ")
            for key, ts_list in sorted(results_b.items()):
                logger.info(f"  - {key}: {len(ts_list)} 次")

            # 2. Daemon 切换事件
            events_a = analyzer._extract_failover_from_logs(logs_a)
            events_b = analyzer._extract_failover_from_logs(logs_b)
            analyzer.print_failover_report(cluster_a["name"], events_a)
            analyzer.print_failover_report(cluster_b["name"], events_b)

            # 合并切换事件
            all_events = events_a + events_b
            all_events.sort(key=lambda x: x["timestamp"])

            # 3. 通用关键字对比
            analyzer._print_comparison(results_a, results_b, cluster_a, cluster_b, all_events)

            # 4. WS 主备状态
            ws_records_a = analyzer._extract_ws_master_from_logs(logs_a)
            ws_records_b = analyzer._extract_ws_master_from_logs(logs_b)
            analyzer.print_master_status_report(
                cluster_a["name"], cluster_b["name"], ws_records_a, ws_records_b, all_events
            )

        except Exception as e:
            logger.error(f"[日志分析异常] {e}")

        return all_events

    def run_checkpoints(self) -> Dict[str, CheckpointResult]:
        """运行所有检查点"""
        logger.info(f"\n[{'='*80}]")
        logger.info("[检查点验证]")
        logger.info(f"[{'='*80}]")

        checkpoints = [
            RedisCheckpoint(),
            EsCheckpoint(),
            DmCheckpoint(),
            ServicesCheckpoint()
        ]

        results = {}
        for checkpoint in checkpoints:
            result = checkpoint.run()
            results[checkpoint.name] = result

        return results

    def attempt_recovery(self, master_key: str, original_replicas: int) -> bool:
        """尽最大努力恢复服务"""
        if original_replicas is None or original_replicas == 0:
            logger.info("[恢复] 无需恢复（原始副本数为空或0）")
            return True

        current_ready, current_replicas = self.get_service_replicas(master_key)
        if current_replicas == original_replicas:
            logger.info(f"[恢复] 当前副本数已是 {original_replicas}，无需恢复")
            return True

        logger.info(f"[恢复] 尝试恢复服务至 {original_replicas} 副本...")
        success = self.scale_service(master_key, original_replicas)
        if success:
            self.wait_for_replicas(master_key, original_replicas, original_replicas)
            status = "恢复成功"
        else:
            status = "恢复失败"

        # 尝试轮询状态（但不作为失败条件）
        new_ready, new_replicas = self.get_service_replicas(master_key)
        if new_replicas == original_replicas:
            logger.info(f"[恢复] 副本数已恢复至 {new_replicas}")
        else:
            logger.warning(f"[恢复] 恢复后状态查询：ready={new_ready}, replicas={new_replicas}")

        return success

    def get_post_failover_master(self) -> str:
        """故障注入后查询当前主集群"""
        try:
            urllib3.disable_warnings()
            resp = requests.get(cluster_api, verify=False, timeout=10)
            resp.raise_for_status()
            content = resp.text.strip()

            if "cluster_A" in content:
                return "集群A"
            elif "cluster_B" in content:
                return "集群B"
            else:
                return "未知"
        except Exception:
            return "查询失败"

    def run_single_round(self, round_num: int) -> dict:
        """执行单轮缩容测试"""
        logger.info(f"\n{'#'*80}")
        logger.info(f"# 第 {round_num} / {self.args.rounds} 轮测试开始")
        logger.info(f"# 开始时间: {_fmt_now()}")
        logger.info(f"{'#'*80}")

        result = {
            "round": round_num,
            "start_time": _fmt_now(),
            "master_node": None,
            "original_replicas": None,
            "scale_down_ok": False,
            "scale_up_ok": False,
            "wait_seconds": self.args.wait,
            "end_time": None,
            "error": None,
            # 关键时间点
            "failover_time": None,
            "recovery_time": None,
            "service_ready_time": None,
            "post_failover_master": None,
            # 检查点结果
            "checkpoint_results": {},
            # 其他
            "failover_cost_ms": None,
            "ws_status": None,
        }

        master_key = None  # 提前初始化，避免异常恢复时 NameError

        try:
            # Step 1: 判断主集群
            master_key = self.get_master_node()
            result["master_node"] = IOMP_NODES[master_key]["name"]

            # Step 2: 查询原始副本数
            ready, replicas = self.get_service_replicas(master_key)
            if ready == -1:
                raise RuntimeError(f"无法查询 {self.args.service} 的原始状态")
            result["original_replicas"] = replicas

            logger.info(f"\n[原始状态] {IOMP_NODES[master_key]['name']} {self.args.service}: ready={ready}, replicas={replicas}")

            if replicas == 0:
                logger.warning("[警告] 当前副本数已是 0，跳过缩容")
            else:
                # Step 3: 缩容
                if not self.scale_service(master_key, 0):
                    raise RuntimeError("缩容操作失败")

                result["scale_down_ok"] = True
                result["failover_time"] = _fmt_now()

                # Step 4: 等待缩容生效
                if not self.wait_for_replicas(master_key, 0, 0):
                    logger.warning("[警告] 缩容后状态轮询超时，但操作已成功下发，继续执行...")

            # Step 5: 等待观察期
            logger.info(f"\n[等待阶段] 最长等待 {self.args.wait} 秒，观察集群行为...")

            elapsed = 0
            check_interval = TestConfig.SWITCH_DETECT_INTERVAL
            switched = False
            api_err_count = 0

            while elapsed < self.args.wait:
                time.sleep(check_interval)
                elapsed += check_interval

                logger.info(f"  已等待 {elapsed}/{self.args.wait} 秒...")

                # 检查主集群是否切换
                try:
                    resp = requests.get(cluster_api, verify=False, timeout=5)
                    resp.raise_for_status()
                    content = resp.text.strip()
                    current_master = None

                    if "cluster_A" in content:
                        current_master = "A"
                    elif "cluster_B" in content:
                        current_master = "B"

                    if current_master and current_master != master_key:
                        logger.info(f"  [检测到主集群切换] {IOMP_NODES[master_key]['name']} -> {IOMP_NODES[current_master]['name']}")

                        extra_wait = TestConfig.SWITCH_DETECT_EXTRA_WAIT
                        logger.info(f"  [提示] 请人工检查系统切换功能，{extra_wait}秒后自动继续...")

                        time.sleep(extra_wait)
                        switched = True
                        break

                except Exception as e:
                    api_err_count += 1
                    if api_err_count <= TestConfig.MAX_API_ERROR_COUNT:
                        logger.warning(f"  [切换检测] cluster_api 查询失败: {e}")

            if not switched:
                logger.info("  等待完成（未检测到切换或已达最大等待时间）")

            # 如果检测到切换且启用 WS 检查
            if switched and self.enable_ws_check:
                logger.info("\n[WS 检查] 检测到集群切换，启动 WebSocket 数据采集...")
                try:
                    ws_result = run_ws_check(duration=self.ws_check_duration)
                    result["ws_status"] = ws_result

                    for conn_name, data in ws_result.get("cluster_switch", {}).items():
                        changes = data.get("cluster_changes", 0)
                        master = data.get("master_cluster", "未知")
                        logger.info(f"  [WS] {conn_name}: 主集群={master}, 切换次数={changes}")

                    for conn_name, data in ws_result.get("track_data", {}).items():
                        uav_total = data.get("uav_total", 0)
                        msg_count = data.get("msg_count", 0)
                        logger.info(f"  [WS] {conn_name}: 消息数={msg_count}, UAV总数={uav_total}")

                except Exception as e:
                    result["ws_status"] = f"WS检查失败({e})"
                    logger.error(f"[WS 检查] 执行失败: {e}")

            # Step 6: 恢复副本数
            if result["original_replicas"] is not None and result["original_replicas"] != 0:
                success = self.scale_service(master_key, result["original_replicas"])
                result["scale_up_ok"] = success
                result["recovery_time"] = _fmt_now()

                if success:
                    wait_ok = self.wait_for_replicas(
                        master_key,
                        result["original_replicas"],
                        result["original_replicas"]
                    )
                    if wait_ok:
                        result["service_ready_time"] = _fmt_now()
                    else:
                        logger.warning("[警告] 恢复后状态轮询超时，但操作已成功下发")

            # Step 7: 业务恢复后下载并分析日志
            try:
                round_start_dt = datetime.strptime(result["start_time"], "%Y-%m-%d %H:%M:%S.%f")
                elapsed_minutes = int((datetime.now() - round_start_dt).total_seconds() / 60) + 2
                dynamic_minutes = max(elapsed_minutes, TestConfig.MIN_ANALYSIS_MINUTES)
            except Exception:
                dynamic_minutes = self.args.analysis

            logger.info(f"\n[日志采集] 服务已恢复，开始下载并分析日志...")
            logger.info(f"[日志采集] 动态分析窗口: 最后 {dynamic_minutes} 分钟（基于本轮测试时长）")

            failover_events = self.run_log_analysis(analysis_minutes=dynamic_minutes)
            if failover_events:
                # 选择匹配的切换事件：old_master 对应被缩容集群
                selected_event = None
                for evt in reversed(failover_events):
                    if master_key.lower() in evt["old_master"].lower():
                        selected_event = evt
                        break
                if not selected_event:
                    selected_event = failover_events[-1]
                result["failover_cost_ms"] = selected_event.get("cost_ms")
                logger.info(f"[日志采集] 主备切换耗时: {result['failover_cost_ms'] or '无记录'}ms ({selected_event['old_master']}→{selected_event['new_master']})")

            # Step 8: 检查点验证
            checkpoint_results = self.run_checkpoints()

            # 转换检查点结果为兼容格式
            result["redis_status"] = checkpoint_results.get("Redis", {}).get("status", "未检查")
            result["es_status"] = checkpoint_results.get("ES", {}).get("status", "未检查")
            result["es_mismatch_detail"] = checkpoint_results.get("ES", {}).get("detail", "")
            result["dm_status"] = checkpoint_results.get("DM", {}).get("status", "未检查")
            result["services_status"] = checkpoint_results.get("关键服务", {}).get("status", "未检查")

            # 故障注入后查询当前主集群
            result["post_failover_master"] = self.get_post_failover_master()

            result["end_time"] = _fmt_now()
            logger.info(f"\n{'#'*80}")
            logger.info(f"# 第 {round_num} 轮测试完成")
            logger.info(f"# 结束时间: {result['end_time']}")
            logger.info(f"{'#'*80}")

        except Exception as e:
            result["error"] = str(e)
            result["end_time"] = _fmt_now()
            logger.error(f"\n[第 {round_num} 轮异常] {e}")

            # 尝试恢复
            if result.get("original_replicas") is not None and master_key is not None:
                self.attempt_recovery(master_key, result["original_replicas"])

            # 异常后仍执行日志分析
            try:
                failover_events = self.run_log_analysis()
                if failover_events and master_key is not None:
                    # 选择匹配的切换事件：old_master 对应被缩容集群
                    selected_event = None
                    for evt in reversed(failover_events):
                        if master_key.lower() in evt["old_master"].lower():
                            selected_event = evt
                            break
                    if not selected_event:
                        selected_event = failover_events[-1]
                    result["failover_cost_ms"] = selected_event.get("cost_ms")
            except Exception as log_err:
                logger.error(f"[日志分析异常] {log_err}")

        return result

    def pre_check(self) -> None:
        """执行前健康检查"""
        logger.info(f"\n[{'='*80}]")
        logger.info("[执行前健康检查]")
        logger.info(f"  检查服务: {self.args.service}")
        logger.info(f"[{'='*80}]")

        issues = []
        for node_key in ["A", "B"]:
            node_name = IOMP_NODES[node_key]["name"]
            ready, replicas = self.get_service_replicas(node_key)

            if ready == -1 or replicas == -1:
                issues.append(f"{node_name}: 查询失败")
                logger.warning(f"  [{node_name}] 查询失败")
                continue

            logger.info(f"  [{node_name}] ready={ready}, replicas={replicas}")

            if replicas == 0:
                issues.append(f"{node_name}: 副本数为 0（可能上次未恢复）")
            elif ready != replicas:
                issues.append(f"{node_name}: Pod 状态异常 ready={ready} != replicas={replicas}")

        if issues:
            logger.error("\n[检查不通过] 发现以下问题，终止测试:")
            for issue in issues:
                logger.error(f"  - {issue}")
            raise RuntimeError("执行前健康检查不通过")

        logger.info("[检查通过] 两个集群服务状态正常，继续执行测试")

    def save_json_report(self, log_file: str) -> None:
        """保存 JSON 报告"""
        if not self.args.report_json:
            return

        # 确保报告目录存在
        report_dir = self.args.report_dir
        os.makedirs(report_dir, exist_ok=True)

        # 生成报告文件名
        base_name = os.path.splitext(os.path.basename(log_file))[0]
        json_file = os.path.join(report_dir, f"{base_name}_report.json")

        report = {
            "test_metadata": {
                "version": "2.0",
                "script": "ha_scale_test2.py",
                "log_file": log_file,
                "test_time": datetime.now().isoformat(),
                "command": " ".join(sys.argv),
            },
            "test_config": {
                "service": self.args.service,
                "namespace": self.args.namespace,
                "cluster": self.args.cluster,
                "kind": self.args.kind,
                "scale_to_zero": 0,
                "wait_seconds": self.args.wait,
                "rounds": self.args.rounds,
                "master_node": self.args.master,
                "analysis_minutes": self.args.analysis,
                "dry_run": self.args.dry_run,
                "enable_ws_check": self.enable_ws_check,
            },
            "round_results": self.round_results,
            "summary": {
                "total_rounds": len(self.round_results),
                "passed_rounds": sum(1 for r in self.round_results if not r.get("error")),
                "failed_rounds": sum(1 for r in self.round_results if r.get("error")),
                "total_time": (
                    f"{(datetime.strptime(self.round_results[-1]['end_time'], '%Y-%m-%d %H:%M:%S.%f') -
                       datetime.strptime(self.round_results[0]['start_time'], '%Y-%m-%d %H:%M:%S.%f')).total_seconds():.1f}s"
                ) if len(self.round_results) >= 2 else None,
            }
        }

        try:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            logger.info(f"\n[JSON报告已保存] {json_file}")

        except Exception as e:
            logger.error(f"[保存JSON报告失败] {e}")

    def summarize_results(self) -> None:
        """打印测试总结"""
        logger.info(f"\n{'='*80}")
        logger.info("[测试总结]")
        logger.info(f"{'='*80}")

        if not self.round_results:
            logger.warning("没有生成任何轮次结果")
            return

        # 表头
        logger.info(f"{'轮次':<6} {'主集群':<10} {'原始副本':<8} {'缩容成功':<8} {'切换时间':<16} {'整轮耗时':<10} {'状态'}")
        logger.info("-" * 70)

        total_ok = 0
        for r in self.round_results:
            # 切换耗时
            cost_str = "-"
            if r.get("failover_cost_ms"):
                cost_str = f"{r['failover_cost_ms']}ms"

            # 整轮耗时
            duration = "-"
            start = r.get("start_time", "")
            end = r.get("end_time", "")
            if start and end:
                try:
                    dt_start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S.%f")
                    dt_end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f")
                    duration = f"{(dt_end - dt_start).total_seconds():.1f}s"
                except Exception:
                    duration = "-"

            # 状态
            status = "异常" if r.get("error") else "通过"
            if not r.get("error"):
                total_ok += 1

            logger.info(
                f"{r['round']:<6} "
                f"{r.get('master_node', '-'):10} "
                f"{r.get('original_replicas', '-'):8} "
                f"{'是' if r.get('scale_down_ok') else '否':8} "
                f"{cost_str:<16} "
                f"{duration:<10} "
                f"{status}"
            )

            if r.get("error"):
                logger.error(f"  异常信息: {r['error']}")

        # 总结
        logger.info("-" * 70)
        logger.info(f"总计: {len(self.round_results)} 轮 | 通过: {total_ok} | 失败: {len(self.round_results) - total_ok}")
        logger.info(f"{'='*80}")

    def run(self) -> None:
        """执行完整测试流程"""
        logger.info(f"\n{'='*80}")
        logger.info("[HA 一键缩容测试 V2.0]")
        if self.args.dry_run:
            logger.info("  [DRY-RUN 模式] 不实际执行缩容/恢复操作")
        logger.info(f"  目标服务: {self.args.service}")
        logger.info(f"  命名空间: {self.args.namespace}")
        logger.info(f"  集群名称: {self.args.cluster}")
        logger.info(f"  资源类型: {self.args.kind}")
        logger.info(f"  缩容至: 0")
        logger.info(f"  等待时间: {self.args.wait} 秒")
        logger.info(f"  轮次: {self.args.rounds}")
        logger.info(f"  主集群: {self.args.master}")
        logger.info(f"  日志分析窗口: {self.args.analysis} 分钟")
        logger.info(f"  启用WS检查: {self.enable_ws_check}")
        logger.info(f"{'='*80}")

        # 执行前健康检查
        try:
            self.pre_check()
        except RuntimeError as e:
            logger.error(f"\n[测试终止] {e}")
            return

        self.round_results = []

        for i in range(1, self.args.rounds + 1):
            round_result = self.run_single_round(i)
            self.round_results.append(round_result)

            # 轮次间隔（最后一轮不间隔）
            if i < self.args.rounds:
                gap_seconds = max(
                    10,
                    self.args.analysis * TestConfig.ROUND_COOLDOWN_FACTOR
                )
                logger.info(f"\n[轮次间隔] 等待 {gap_seconds} 秒后进入下一轮...")
                logger.info(f"[提示] 如需完全避免前一轮日志影响，建议手动间隔至少 {self.args.analysis} 分钟")
                time.sleep(gap_seconds)

        # 测试总结
        self.summarize_results()

def main():
    """命令行入口"""
    # 解析命令行参数
    args = parse_args()

    # 设置日志系统
    logger, log_file = setup_logging(args.report_dir)

    logger.info(f"\n[启动] HA 缩容测试 V2.0")
    logger.info(f"  命令行参数: {vars(args)}")

    try:
        # 创建测试器并运行
        tester = HaScaleTester2(
            args=args,
            log_dir=args.report_dir,
            enable_ws_check=not args.disable_ws if not args.dry_run else False
        )

        tester.run()

        # 保存 JSON 报告
        tester.save_json_report(log_file)

    except KeyboardInterrupt:
        logger.warning("\n[用户中断] 测试被手动终止")
    except Exception as e:
        logger.error(f"\n[运行异常] {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info(f"\n[完成] 测试日志已保存到: {log_file}")

if __name__ == "__main__":
    main()