#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HA 一键缩容测试脚本

功能：
1. 自动判断主集群（通过 ws 日志分析或配置指定）
2. 对主集群的指定服务缩容至 0
3. 等待指定时间
4. 采集日志并分析（daemon 切换事件、ws 主备状态、通用关键字对比）
5. 恢复服务副本数
6. 支持多轮次循环
7. 测试日志同时输出到控制台和文件

使用方式：
    1. 修改下方配置区的参数
    2. 直接运行: python ha_scale_test.py
    3. 或被其他脚本导入调用:
       from ha_scale_test import HaScaleTester
       tester = HaScaleTester()
       tester.run()
脚本处理流程及关键信息：

    [执行前健康检查]  A/B 双集群目标服务状态检查，异常则终止
           |
           v
    [判断主集群]  通过 HTTP GET cluster_api 自动判断，或配置固定值
           |
           v
    [查询原始副本数]  记录当前 ready/replicas，用于后续恢复
           |
           v
    [缩容至 0]  PATCH IOMP API 修改 replicas=0，HTTP 200 即判定成功
           |
           v
    [等待观察期]  轮询检测主集群切换，检测到切换可提前结束（最长 WAIT_SECONDS）
           |
           v
    [恢复副本数]  PATCH IOMP API 恢复原始副本数，轮询确认服务就绪（最长 300s）
           |
           v
    [日志采集与分析]  动态计算分析窗口（本轮测试时长+2min缓冲），下载双集群日志
           |           分析内容：daemon 切换事件 / ws 主备状态 / 通用关键字对比
           v
    [检查点验证]  Redis 双集群一致性 / ES 索引数据量对比 / DM 关键表 COUNT 对比
           |           关键服务 A/B 状态对比 / 故障注入后主集群确认
           v
    [生成测试报告]  结构化输出：故障注入时间、恢复时间、服务恢复耗时、各检查点状态

关键信息：
    - DRY_RUN=True：只模拟流程，不实际调用缩容/恢复 API，用于流程验证
    - 日志输出路径：脚本同级 log/ 目录，文件名 ha_scale_test_YYYYMMDD_HHMMSS.txt
    - 成功判定标准：缩容/恢复以 IOMP API 返回 HTTP 200 为准，状态轮询仅辅助确认
    - 轮次间隔：自动根据 ANALYSIS_MINUTES 动态调整，避免前一轮日志混入下一轮
    - 动态分析窗口：每轮根据实际测试时长自动计算，无需手动调整 ANALYSIS_MINUTES

注意：
    - 若目标服务为 la-atc-ws-backend，自动判断主集群时会在缩容前先下载 ws 日志
    - 建议将 MASTER_NODE 配置为固定值以避免首次判断的额外耗时
"""

import os
import sys
import time
import io
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
import urllib3

# ==================== 路径处理 ====================
# 引入 atcapi_autotest/api_tools 模块
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
API_TOOLS_DIR = os.path.join(PROJECT_ROOT, "atcapi_autotest", "api_tools")
if API_TOOLS_DIR not in sys.path:
    sys.path.insert(0, API_TOOLS_DIR)

# 引入 ha_log_download_analysis（同目录）
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
# ==================== 导入依赖 ====================
from iomp_api_servers_ops import IompServiceManager
from ha_log_download_analysis import HaLogAnalyzer
from ha_env import iomp_ip_a, iomp_port_a, ACCESS_KEY_a, iomp_ip_b, iomp_port_b, ACCESS_KEY_b, cluster_api
from ws_client_check import run_ws_check, MultiWsClient, _get_ha_connections

# 引入 iomp_query 进行关键服务状态检查
import iomp_query
from iomp_query import ServiceConfig, IOMPQueryClient, print_comparison_table


# ==================== 配置区（用户按需修改）====================

# 1. 目标服务配置
TARGET_SERVICE: str = "al-atc-data-exchange-mqtt"       # 要缩容的目标服务名
TARGET_NAMESPACE: str = "kedacom-project-namespace"  # 命名空间
CLUSTER_NAME: str = "dk"                             # IOMP 集群名称
TARGET_KIND: str = "All"                             # 资源类型，一般写 All 即可

# 2. 缩容与恢复配置
SCALE_TO_ZERO: int = 0        # 缩容后的副本数（默认 0）
WAIT_SECONDS: int = 300        # 缩容后等待时间（秒）
ROUNDS: int = 1               # 执行轮次
POLL_INTERVAL: int = 5        # 状态轮询间隔（秒）
POLL_TIMEOUT: int = 300       # 状态轮询超时（秒），部分服务恢复需3-5分钟
DRY_RUN: bool = False        # True=只模拟流程，不实际缩容/恢复

# 3. 主集群配置
MASTER_NODE: str = "auto"     # "auto"=自动判断, "A"=A节点为主, "B"=B节点为主

# 4. 日志分析配置
ANALYSIS_MINUTES: int = 5    # 日志分析时间窗口（分钟）

# 5. 输出配置（基于脚本所在目录，使用统一的 tmp 目录）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR: str = os.path.join(_SCRIPT_DIR, "..", "tmp", "log")  # 测试日志输出目录

# 6. IOMP 节点配置（通常无需修改，从 ha_env.py 导入）
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


# ==================== 日志格式化工具 ====================
class ColoredFormatter:
    """增强的日志格式化器，支持颜色和时间戳"""

    # ANSI 颜色代码
    COLORS = {
        'HEADER': '\033[95m',
        'BLUE': '\033[94m',
        'CYAN': '\033[96m',
        'GREEN': '\033[92m',
        'YELLOW': '\033[93m',
        'RED': '\033[91m',
        'BOLD': '\033[1m',
        'UNDERLINE': '\033[4m',
        'END': '\033[0m',
        'DIM': '\033[2m',  # 暗淡色
    }

    @classmethod
    def colorize(cls, text: str, color: str) -> str:
        """为文本添加颜色"""
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            return f"{cls.COLORS.get(color, '')}{text}{cls.COLORS['END']}"
        return text

    @classmethod
    def timestamp(cls) -> str:
        """生成带毫秒的时间戳"""
        now = datetime.now()
        return now.strftime("%H:%M:%S.%f")[:-3]

    @classmethod
    def section(cls, title: str, width: int = 80) -> str:
        """生成分隔线标题"""
        border = cls.colorize('=' * width, 'CYAN')
        title_line = cls.colorize(f"[ {title} ]", 'CYAN')
        return f"\n{border}\n{title_line:\^{width}}\n{border}\n"

    @classmethod
    def subtitle(cls, title: str, level: int = 1) -> str:
        """生成子标题"""
        prefix = "  " * level
        color = 'YELLOW' if level == 1 else 'CYAN'
        return f"{prefix}{cls.colorize(f'[{title}]', color)}"

    @classmethod
    def success(cls, text: str) -> str:
        """成功消息格式"""
        return cls.colorize(f"✓ {text}", 'GREEN')

    @classmethod
    def warning(cls, text: str) -> str:
        """警告消息格式"""
        return cls.colorize(f"⚠ {text}", 'YELLOW')

    @classmethod
    def error(cls, text: str) -> str:
        """错误消息格式"""
        return cls.colorize(f"✗ {text}", 'RED')

    @classmethod
    def info(cls, text: str) -> str:
        """信息消息格式"""
        return cls.colorize(f"ℹ {text}", 'BLUE')

    @classmethod
    def debug(cls, text: str) -> str:
        """调试消息格式"""
        return cls.colorize(f"◆ {text}", 'DIM')


class EnhancedLogger:
    """增强的日志器，支持颜色和格式化"""

    def __init__(self):
        self.formatter = ColoredFormatter()

    def log(self, level: str, message: str, timestamp: bool = True):
        """统一的日志输出方法"""
        if timestamp:
            ts = self.formatter.timestamp()
            prefix = f"[{ts}] {level}"
        else:
            prefix = f"{' ' * 10}{level}"

        colored_level = self.formatter.colorize(prefix, level.upper())
        print(f"{colored_level} {message}")

    def section(self, title: str):
        """打印分隔线标题"""
        print(self.formatter.section(title))

    def subtitle(self, title: str, level: int = 1):
        """打印子标题"""
        print(self.formatter.subtitle(title, level))

    def success(self, message: str):
        """打印成功消息"""
        print(self.formatter.success(message))

    def warning(self, message: str):
        """打印警告消息"""
        print(self.formatter.warning(message))

    def error(self, message: str):
        """打印错误消息"""
        print(self.formatter.error(message))

    def info(self, message: str):
        """打印信息消息"""
        print(self.formatter.info(message))

    def debug(self, message: str):
        """打印调试消息"""
        print(self.formatter.debug(message))



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


class HaScaleTester:
    """
    HA 一键缩容测试器
    """

    def __init__(
        self,
        target_service: str = TARGET_SERVICE,
        target_namespace: str = TARGET_NAMESPACE,
        cluster_name: str = CLUSTER_NAME,
        target_kind: str = TARGET_KIND,
        scale_to_zero: int = SCALE_TO_ZERO,
        wait_seconds: int = WAIT_SECONDS,
        rounds: int = ROUNDS,
        master_node: str = MASTER_NODE,
        analysis_minutes: int = ANALYSIS_MINUTES,
        log_dir: str = LOG_DIR,
        poll_interval: int = POLL_INTERVAL,
        poll_timeout: int = POLL_TIMEOUT,
        dry_run: bool = DRY_RUN,
        round_gap_seconds: int = None,
    ):
        self.target_service = target_service
        self.target_namespace = target_namespace
        self.cluster_name = cluster_name
        self.target_kind = target_kind
        self.scale_to_zero = scale_to_zero
        self.wait_seconds = wait_seconds
        self.rounds = rounds
        self.master_node = master_node
        self.analysis_minutes = analysis_minutes
        self.log_dir = log_dir
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.dry_run = dry_run
        self.round_gap_seconds = round_gap_seconds

        # 初始化日志器
        self.logger = EnhancedLogger()

        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)

        # 初始化 IOMP 管理器（A/B 节点）
        self.managers: Dict[str, IompServiceManager] = {}
        for node_key, node_cfg in IOMP_NODES.items():
            self.managers[node_key] = IompServiceManager(
                base_url=node_cfg["base_url"],
                accesskey=node_cfg["access_key"],
            )

        # 记录每轮测试结果
        self.round_results: List[dict] = []

    # ==================== 工具方法 ====================

    def _fmt_now(self) -> str:
        """格式化当前时间"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _get_service_replicas(self, node_key: str) -> Tuple[int, int]:
        """
        查询指定节点的目标服务副本状态。
        返回: (ready_replicas, replicas)
        """
        manager = self.managers[node_key]
        result = manager.query_service(
            self.cluster_name,
            self.target_namespace,
            self.target_kind,
            self.target_service,
        )
        if result.get("_error"):
            self.logger.error(f"{node_key} 节点 {self.target_service}: {result['_error']}")
            return -1, -1

        data = result.get("result", {})
        if not isinstance(data, dict):
            self.logger.warning(f"{node_key} 节点返回格式不正确")
            return -1, -1

        ready = data.get("readyReplicas", 0)
        replicas = data.get("replicas", 0)
        # 缩容到 0 后接口可能返回 None，统一处理为 0
        ready = 0 if ready is None else ready
        replicas = 0 if replicas is None else replicas
        return ready, replicas

    def _wait_for_replicas(self, node_key: str, expected_ready: int, expected_replicas: int) -> bool:
        """
        轮询等待服务达到指定副本状态。
        返回: True=成功, False=超时
        """
        if self.dry_run:
            self.logger.warning(f"DRY-RUN: 跳过状态轮询（ready={expected_ready}, replicas={expected_replicas}）")
            return True

        start = time.time()
        node_name = IOMP_NODES[node_key]["name"]
        print(
            f"[{node_name}] 等待 {self.target_service} 达到 "
            f"ready={expected_ready}, replicas={expected_replicas} ..."
        )

        last_ready = None
        last_replicas = None
        while time.time() - start < self.poll_timeout:
            ready, replicas = self._get_service_replicas(node_key)
            if ready == -1:
                print(f"  查询失败，{self.poll_interval}秒后重试...")
                time.sleep(self.poll_interval)
                continue

            # 只在状态变化时打印，避免日志刷屏
            if ready != last_ready or replicas != last_replicas:
                print(f"  当前状态: ready={ready}, replicas={replicas}")
                last_ready = ready
                last_replicas = replicas

            if ready == expected_ready and replicas == expected_replicas:
                print(f"  [状态达成] 耗时 {time.time() - start:.1f} 秒")
                return True

            time.sleep(self.poll_interval)

        print(f"  [等待超时] 超过 {self.poll_timeout} 秒仍未达到目标状态")
        return False

    # ==================== 主集群判断 ====================

    def detect_master_node(self) -> Optional[str]:
        """
        自动判断主集群所在节点（A 或 B）。
        通过 HTTP GET 查询 cluster_api 获取当前主集群信息。
        返回: "A" | "B" | None
        """
        self.logger.section("主集群自动判断")
        self.logger.info("方法: HTTP GET 查询 cluster_api")
        self.logger.info(f"URL: {cluster_api}")

        master_node = None
        try:
            # 抑制 SSL 警告
            import urllib3
            urllib3.disable_warnings()

            response = requests.get(cluster_api, verify=False, timeout=10)
            response.raise_for_status()
            content = response.text.strip()

            self.logger.info(f"查询结果: {content}")

            if "cluster_A" in content:
                master_node = "A"
            elif "cluster_B" in content:
                master_node = "B"
            else:
                self.logger.warning(f"响应内容无法识别主集群: {content}")

        except Exception as e:
            self.logger.error(f"查询失败: {e}")

        if master_node:
            self.logger.success(f"主集群判断结果: {IOMP_NODES[master_node]['name']}")
        else:
            self.logger.error("主集群判断结果: 无法自动判断，请手动配置 MASTER_NODE")
        return master_node

    def get_master_node(self) -> str:
        """
        获取主集群节点。优先使用配置，配置为 auto 时自动判断。
        """
        if self.master_node in ("A", "B"):
            self.logger.success(f"主集群配置: 使用配置值: {IOMP_NODES[self.master_node]['name']}")
            return self.master_node

        detected = self.detect_master_node()
        if detected:
            return detected

        raise RuntimeError(
            "无法确定主集群，请手动配置 MASTER_NODE 为 'A' 或 'B'"
        )

    # ==================== 缩容与恢复 ====================

    def scale_service(self, node_key: str, replicas: int) -> bool:
        """
        对指定节点的目标服务设置副本数。
        返回: True=成功, False=失败
        """
        node_name = IOMP_NODES[node_key]["name"]
        self.logger.section(f"服务缩容/恢复: {node_name} -> {self.target_service} replicas={replicas}")

        if self.dry_run:
            self.logger.warning(f"DRY-RUN: 模拟设置副本数: {self.target_service} -> replicas={replicas}")
            self.logger.warning("跳过实际 IOMP API 调用")
            return True

        manager = self.managers[node_key]
        result = manager.scale_service(
            self.cluster_name,
            self.target_namespace,
            self.target_service,
            replicas,
        )

        if result.get("_error"):
            self.logger.error(f"操作失败: {result['_error']}")
            return False

        status = result.get("status", result.get("code"))
        if status in (200, "0", 0):
            self.logger.success(f"操作成功: status={status}")
            return True
        else:
            self.logger.error(f"操作异常: status={status}, 响应: {result}")
            return False

    # ==================== 日志分析 ====================

    def run_log_analysis(self, analysis_minutes: Optional[int] = None, round_start_time: Optional[str] = None) -> Tuple[List[dict], Optional[str]]:
        """
        执行完整的双集群日志分析流程。
        analysis_minutes: 为 None 时使用 self.analysis_minutes
        round_start_time: 本轮测试开始时间字符串，用于精确过滤切换事件时间范围
        返回: (切换事件列表, 主集群存储告警判断结果)，异常返回 ([], None)
        """
        minutes = analysis_minutes if analysis_minutes is not None else self.analysis_minutes
        self.logger.section("日志分析启动")
        self.logger.info(f"分析时间窗口: 最后 {minutes} 分钟")

        # 解析本轮测试开始时间，用于切换事件精确过滤
        start_dt = None
        if round_start_time:
            try:
                start_dt = datetime.strptime(round_start_time, "%Y-%m-%d %H:%M:%S.%f")
                self.logger.info(f"切换事件过滤范围: {start_dt.strftime('%Y-%m-%d %H:%M:%S')} 之后")
            except Exception:
                pass

        analyzer = HaLogAnalyzer(analysis_minutes=minutes)

        # 为避免重复下载，手动控制流程
        if len(analyzer.cluster_configs) != 2:
            self.logger.error("必须配置两个集群")
            return [], None

        cluster_a = analyzer.cluster_configs[0]
        cluster_b = analyzer.cluster_configs[1]

        all_events: List[dict] = []
        master_alert_status: Optional[str] = None
        try:
            # 统一下载日志（抑制过程详情，只保留关键结果）
            old_stdout = sys.stdout
            buf = io.StringIO()
            sys.stdout = buf
            try:
                logs_a = analyzer.download_cluster_logs(cluster_a)
            finally:
                sys.stdout = old_stdout
            for line in buf.getvalue().splitlines():
                if "下载完成" in line or "下载异常" in line or "错误" in line:
                    self.logger.info(line)

            buf = io.StringIO()
            sys.stdout = buf
            try:
                logs_b = analyzer.download_cluster_logs(cluster_b)
            finally:
                sys.stdout = old_stdout
            for line in buf.getvalue().splitlines():
                if "下载完成" in line or "下载异常" in line or "错误" in line:
                    self.logger.info(line)

            # 1. 通用关键字对比
            results_a, start_a, end_a = analyzer._analyze_cluster_logs(logs_a)
            results_b, start_b, end_b = analyzer._analyze_cluster_logs(logs_b)

            # 打印分析时间范围
            if start_a and end_a:
                self.logger.info(f"分析时间范围: {analyzer._fmt_ts(start_a)} ~ {analyzer._fmt_ts(end_a)}")
            elif start_b and end_b:
                self.logger.info(f"分析时间范围: {analyzer._fmt_ts(start_b)} ~ {analyzer._fmt_ts(end_b)}")

            # 简化输出，只显示汇总
            self.logger.info(f"{cluster_a['name']} 关键字命中统计汇总")
            for key, ts_list in sorted(results_a.items()):
                self.logger.debug(f"  - {key}: {len(ts_list)} 次")
            self.logger.info(f"{cluster_b['name']} 关键字命中统计汇总")
            for key, ts_list in sorted(results_b.items()):
                self.logger.debug(f"  - {key}: {len(ts_list)} 次")

            # 2. Daemon 切换事件（使用本轮测试开始时间作为过滤起点）
            events_a = analyzer._extract_failover_from_logs(logs_a, start_time=start_dt)
            events_b = analyzer._extract_failover_from_logs(logs_b, start_time=start_dt)

            # 只打印汇总信息
            if events_a:
                self.logger.info(f"{cluster_a['name']}: 检测到 {len(events_a)} 个切换事件")
            if events_b:
                self.logger.info(f"{cluster_b['name']}: 检测到 {len(events_b)} 个切换事件")

            # 合并切换事件用于正确性判断
            all_events = events_a + events_b
            all_events.sort(key=lambda x: x["timestamp"])

            # 主集群存储告警判断
            if "主集群存储告警" in results_a or "主集群存储告警" in results_b:
                a_has = len(results_a.get("主集群存储告警", [])) > 0
                b_has = len(results_b.get("主集群存储告警", [])) > 0
                master_alert_status = "正确" if (a_has != b_has) else "异常"

        except Exception as e:
            self.logger.error(f"日志分析异常: {e}")

        return all_events, master_alert_status

    # ==================== 检查点方法 ====================

    def _check_redis(self) -> str:
        """Redis 双集群一致性检查，返回状态描述"""
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

            # 精确判断一致性，仅输出一行状态，不打印任何详细对比
            is_consistent = (
                "数据不一致的Key数: 0" in output
                and "至少在一个Redis实例中不存在的Key数: 0" in output
            )

            if is_consistent:
                self.logger.success("Redis 数据一致")
                return "一致"
            else:
                self.logger.warning("Redis 数据不一致")
                return "不一致"
        except Exception as e:
            self.logger.error(f"Redis 检查失败: {e}")
            return f"检查失败({e})"

    def _check_es(self) -> Tuple[str, Optional[str]]:
        """ES 双集群一致性检查：前推30分钟，按5分钟切片对比数据量"""
        try:
            from ha_env import es_hosts
            servers = [f"http://{host}" for host in es_hosts]
            if len(servers) < 2:
                self.logger.warning("[ES] 未配置双集群 ES 地址")
                return "未配置", None

            # 时间范围：前推30分钟
            end_time = datetime.now().astimezone()
            start_time = end_time - timedelta(minutes=30)
            slice_minutes = 5
            index_pattern = "uav_runtime_data*"
            time_field = "timestamp"  # 毫秒级 long

            # 生成时间切片
            slices = []
            current = start_time
            while current < end_time:
                slice_end = min(current + timedelta(minutes=slice_minutes), end_time)
                slices.append((current, slice_end))
                current = slice_end

            def _es_count(server: str, s: datetime, e: datetime) -> int:
                """查询单个切片文档数"""
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
                except Exception:
                    pass
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
                self.logger.error("[ES] 两个 ES 服务器均不可达")
                return "服务器不可达", None

            all_match = True
            mismatches = []
            total_a = 0
            total_b = 0

            for slice_start, slice_end in slices:
                count_a = _es_count(servers[0], slice_start, slice_end) if reach[0] else -1
                count_b = _es_count(servers[1], slice_start, slice_end) if reach[1] else -1

                if count_a > 0:
                    total_a += count_a
                if count_b > 0:
                    total_b += count_b

                label = f"{slice_start.strftime('%m-%d %H:%M')} ~ {slice_end.strftime('%H:%M')}"

                if count_a == -1 or count_b == -1:
                    all_match = False
                    mismatches.append(f"{label}: 无法获取")
                elif count_a != count_b:
                    all_match = False
                    mismatches.append(f"{label}: {count_a} vs {count_b}(差{abs(count_a - count_b)})")

            if all_match:
                self.logger.success(f"ES 所有切片一致（{len(slices)}个切片，总数据量: {total_a}/{total_b}）")
                return "一致", None
            else:
                detail = "; ".join(mismatches)
                self.logger.warning(f"ES 不一致切片: {len(mismatches)}/{len(slices)}，总计: {total_a} vs {total_b}")
                return "不一致", detail
        except Exception as e:
            self.logger.error(f"ES 检查失败: {e}")
            return f"检查失败({e})", str(e)

    def _check_dm(self) -> str:
        """达梦数据库双集群一致性检查，返回状态描述"""
        try:
            from dm_ha_client import DmDbClient, DB_CONFIG_A, DB_CONFIG_B

            # 关键业务表（参考 dm_data_snyc_check.py）
            tables = [
                "uav_info",
                "flight_task",
                "flight_plan",
                "alert",
                "air_route",
            ]

            client_a = DmDbClient(**DB_CONFIG_A)
            client_b = DmDbClient(**DB_CONFIG_B)

            if not client_a.connect():
                self.logger.error("[DM] A集群数据库连接失败")
                return "A集群连接失败"
            if not client_b.connect():
                self.logger.error("[DM] B集群数据库连接失败")
                client_a.close()
                return "B集群连接失败"

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

                if all_match:
                    self.logger.success(f"DM 所有 {len(tables)} 个关键表数据量一致")
                    return "一致"
                else:
                    self.logger.warning(f"DM 不一致表: {mismatches}")
                    return "不一致"
            finally:
                client_a.close()
                client_b.close()
        except Exception as e:
            self.logger.error(f"DM 检查失败: {e}")
            return f"检查失败({e})"

    def _check_services(self) -> str:
        """关键服务 A/B 双集群状态检查，返回状态描述"""
        try:
            self.logger.info("[关键服务状态检查] 开始查询 A/B 双集群关键服务...")
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
                self.logger.info(f"[关键服务] {node['name']} 查询完成: {len(results)} 个服务")

            if len(iomp_query.IOMP_NODES) >= 2:
                a_name = iomp_query.IOMP_NODES[0]['name']
                b_name = iomp_query.IOMP_NODES[1]['name']
                a_results = node_results.get(a_name, [])
                b_results = node_results.get(b_name, [])

                # 先输出对比表格（保留原有打印）
                print_comparison_table(
                    a_results,
                    b_results,
                    node_a_name=a_name,
                    node_b_name=b_name
                )

                # 计算一致性状态（与 print_comparison_table 相同逻辑）
                a_map = {r['config'].deploy_name: r for r in a_results}
                b_map = {r['config'].deploy_name: r for r in b_results}
                all_names = set(a_map.keys()) | set(b_map.keys())
                inconsistent_count = 0
                for name in all_names:
                    a_item = a_map.get(name)
                    b_item = b_map.get(name)
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
                        if not same:
                            inconsistent_count += 1
                    else:
                        inconsistent_count += 1

                if inconsistent_count == 0:
                    self.logger.success("[关键服务] A/B 双集群关键服务配置一致")
                    return "正常"
                else:
                    self.logger.warning(f"[关键服务] A/B 双集群关键服务不一致/缺失: {inconsistent_count} 个")
                    return "异常"
            else:
                self.logger.info("[关键服务] 单节点模式，仅输出汇总")
                return "单节点"
        except Exception as e:
            self.logger.error(f"[关键服务] 检查失败: {e}")
            return f"检查失败({e})"

    # ==================== 单轮测试 ====================

    def run_single_round(self, round_num: int) -> dict:
        """
        执行单轮缩容测试。
        返回本轮结果字典。
        """
        print(f"\n{'#'*80}")
        print(f"# 第 {round_num} / {self.rounds} 轮测试开始")
        print(f"# 开始时间: {self._fmt_now()}")
        print(f"{'#'*80}")

        result = {
            "round": round_num,
            "start_time": self._fmt_now(),
            "master_node": None,
            "original_replicas": None,
            "scale_down_ok": False,
            "scale_up_ok": False,
            "wait_seconds": self.wait_seconds,
            "end_time": None,
            "error": None,
            # 新增：关键时间点与检查点
            "failover_time": None,           # 故障注入时间
            "recovery_time": None,           # 故障恢复时间
            "service_ready_time": None,      # 服务正常时间
            "post_failover_master": None,    # 故障注入后主集群
            "redis_status": None,            # Redis 同步状态
            "es_status": None,               # ES 同步状态
            "es_mismatch_detail": None,      # ES 不一致详细信息
            "dm_status": None,               # DM 数据库同步状态
            "services_status": None,         # 关键服务状态检查
            "failover_cost_ms": None,        # 日志中主备切换耗时(ms)
            "failover_old_master": None,      # 日志中切换事件原主集群
            "failover_new_master": None,      # 日志中切换事件新主集群
            "failover_events": None,          # 日志中所有切换事件列表
            "ws_status": None,               # WS 切换后检查状态
        }

        ws_client = None
        ws_thread = None
        master_key = None

        try:
            # === WS 后台采集启动（每轮开始时）===
            if not self.dry_run:
                try:
                    conns = _get_ha_connections()
                    if conns:
                        ws_client = MultiWsClient(connections=conns, debug=False, log_fp=sys.stdout, save_report=False)
                        ws_thread = threading.Thread(target=ws_client.start, args=(0,), daemon=True)
                        ws_thread.start()
                        print("\n[WS] 后台采集已启动（每轮开始时）")
                except Exception as e:
                    print(f"[WS] 后台采集启动失败: {e}")

            # Step 1: 判断主集群
            master_key = self.get_master_node()
            result["master_node"] = IOMP_NODES[master_key]["name"]

            # Step 2: 查询原始副本数
            ready, replicas = self._get_service_replicas(master_key)
            if ready == -1:
                raise RuntimeError(f"无法查询 {self.target_service} 的原始状态")
            result["original_replicas"] = replicas
            print(
                f"\n[原始状态] {IOMP_NODES[master_key]['name']} "
                f"{self.target_service}: ready={ready}, replicas={replicas}"
            )

            if replicas == self.scale_to_zero:
                print(f"[警告] 当前副本数已是 {self.scale_to_zero}，跳过缩容")
                result["scale_down_ok"] = True
            else:
                # Step 3: 缩容
                if not self.scale_service(master_key, self.scale_to_zero):
                    raise RuntimeError("缩容操作失败")

                # API 返回 200 即认为缩容操作成功下发
                result["scale_down_ok"] = True
                result["failover_time"] = self._fmt_now()

                # Step 4: 等待缩容生效（辅助确认，超时不阻断）
                if not self._wait_for_replicas(
                    master_key, self.scale_to_zero, self.scale_to_zero
                ):
                    print("[警告] 缩容后状态轮询超时，但操作已成功下发，继续执行...")

            # Step 5: 等待观察期（支持检测到主集群切换后提前结束）
            print(f"\n[等待阶段] 最长等待 {self.wait_seconds} 秒，观察集群行为...")
            elapsed = 0
            check_interval = 5
            switched = False
            api_err_count = 0
            while elapsed < self.wait_seconds:
                time.sleep(check_interval)
                elapsed += check_interval
                print(f"  已等待 {elapsed}/{self.wait_seconds} 秒...")

                # 每次循环都检查主集群是否切换（5秒间隔）
                try:
                    resp = requests.get(cluster_api, verify=False, timeout=5)
                    content = resp.text.strip()
                    current_master = None
                    if "cluster_A" in content:
                        current_master = "A"
                    elif "cluster_B" in content:
                        current_master = "B"
                    if current_master and current_master != master_key:
                        print(
                            f"  [检测到主集群切换] "
                            f"{IOMP_NODES[master_key]['name']} -> {IOMP_NODES[current_master]['name']}"
                        )
                        # 切换后继续等待 2 分钟供人工检查
                        extra_wait = 120
                        print(f"  [提示] 请人工检查系统切换功能，{extra_wait}秒后自动继续...")
                        time.sleep(extra_wait)
                        switched = True
                        break
                except Exception as e:
                    api_err_count += 1
                    if api_err_count <= 2:
                        print(f"  [切换检测] cluster_api 查询失败: {e}")
                    # 查询失败不中断等待

            if not switched:
                print(f"  等待完成（未检测到切换或已达最大等待时间）")

            # Step 6: 恢复副本数
            if result["original_replicas"] is not None and result["original_replicas"] != self.scale_to_zero:
                if not self.scale_service(master_key, result["original_replicas"]):
                    raise RuntimeError("恢复副本数操作失败")

                # API 返回 200 即认为恢复操作成功下发
                result["scale_up_ok"] = True
                result["recovery_time"] = self._fmt_now()

                # 等待恢复生效（辅助确认，超时不阻断）
                wait_ok = self._wait_for_replicas(
                    master_key,
                    result["original_replicas"],
                    result["original_replicas"],
                )
                if wait_ok:
                    result["service_ready_time"] = self._fmt_now()
                else:
                    print("[警告] 恢复后状态轮询超时，但操作已成功下发，继续执行...")

            # Step 7: 检查点验证（Redis / ES / DM）
            print(f"\n[{'='*80}]")
            print("[检查点验证]")
            print(f"[{'='*80}]")
            result["redis_status"] = self._check_redis()
            result["es_status"], result["es_mismatch_detail"] = self._check_es()
            result["dm_status"] = self._check_dm()
            result["services_status"] = self._check_services()

            # Step 8: 故障注入后查询当前主集群
            try:
                import urllib3
                urllib3.disable_warnings()
                resp = requests.get(cluster_api, verify=False, timeout=10)
                content = resp.text.strip()
                if "cluster_A" in content:
                    result["post_failover_master"] = "集群A"
                elif "cluster_B" in content:
                    result["post_failover_master"] = "集群B"
                else:
                    result["post_failover_master"] = "未知"
            except Exception as api_err:
                result["post_failover_master"] = f"查询失败({api_err})"

            # Step 9: 业务恢复后下载并分析日志
            # 动态计算分析窗口：从本轮开始到当前的分钟数 + 2 分钟缓冲
            try:
                round_start_dt = datetime.strptime(result["start_time"], "%Y-%m-%d %H:%M:%S.%f")
                elapsed_minutes = int((datetime.now() - round_start_dt).total_seconds() / 60) + 2
                dynamic_minutes = max(elapsed_minutes, 5)  # 至少 5 分钟
            except Exception:
                dynamic_minutes = self.analysis_minutes
            print(f"\n[日志采集] 服务已恢复，开始下载并分析日志...")
            print(f"[日志采集] 动态分析窗口: 最后 {dynamic_minutes} 分钟（基于本轮测试时长）")
            failover_events, master_alert_status = self.run_log_analysis(analysis_minutes=dynamic_minutes, round_start_time=result["start_time"])
            result["master_alert_status"] = master_alert_status
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
                result["failover_old_master"] = selected_event.get("old_master")
                result["failover_new_master"] = selected_event.get("new_master")
                result["failover_events"] = failover_events

                # 打印所有切换事件的详细信息
                print(f"\n[日志采集] 检测到 {len(failover_events)} 个切换事件:")
                for evt in failover_events:
                    ts_str = evt["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(evt["timestamp"], "strftime") else str(evt["timestamp"])
                    new_master = evt.get("new_master", "")
                    if "cluster_a" in new_master.lower():
                        master_label = "主集群A"
                    elif "cluster_b" in new_master.lower():
                        master_label = "主集群B"
                    else:
                        master_label = f"主集群{new_master}"
                    raw_line = evt.get("raw_line", "")
                    print(f"  {ts_str}  {master_label} {raw_line}")

                # 收集所有 cost 值，逗号分割
                all_costs = [str(evt.get("cost_ms", "")) for evt in failover_events if evt.get("cost_ms") is not None]
                result["all_costs_str"] = ",".join(all_costs) if all_costs else None
                print(f"[日志采集] 主备切换耗时: {result.get('all_costs_str') or result['failover_cost_ms']}ms ({result['failover_old_master']}→{result['failover_new_master']})")

            # 综合判断本轮测试是否通过
            failures = []
            if not result["scale_down_ok"]:
                failures.append("缩容失败")
            if not result["scale_up_ok"]:
                failures.append("恢复失败")
            if not result["failover_cost_ms"] and not result["failover_events"]:
                failures.append("未采集到切换耗时")
            if result["es_status"] != "一致":
                failures.append(f"ES不一致({result['es_status']})")
            if result["services_status"] is None or "正常" not in str(result["services_status"]):
                failures.append(f"关键服务异常({result['services_status']})")
            if result["master_alert_status"] != "正确":
                failures.append(f"存储告警判断异常({result['master_alert_status']})")
            # 主集群变化判断
            if result["post_failover_master"] == result["master_node"]:
                failures.append("主集群未发生变化")
            elif result["post_failover_master"] in ["未知", None] or "查询失败" in str(result["post_failover_master"]):
                failures.append(f"主集群判断异常({result['post_failover_master']})")

            if failures:
                result["error"] = "；".join(failures)
                print(f"\n[第 {round_num} 轮检查不通过] {'；'.join(failures)}")

            result["end_time"] = self._fmt_now()
            print(f"\n{'#'*80}")
            print(f"# 第 {round_num} 轮测试完成")
            print(f"# 结束时间: {result['end_time']}")
            print(f"{'#'*80}")

        except Exception as e:
            result["error"] = str(e)
            result["end_time"] = self._fmt_now()
            print(f"\n[第 {round_num} 轮异常] {e}")

            # 异常时尝试恢复（尽最大努力），恢复前检查避免重复操作
            if master_key is not None and result["original_replicas"] is not None and result["original_replicas"] != self.scale_to_zero:
                ready, replicas = self._get_service_replicas(master_key)
                if ready == -1:
                    print(f"[异常恢复] 查询当前状态失败，尝试恢复至 {result['original_replicas']} 副本...")
                    try:
                        self.scale_service(master_key, result["original_replicas"])
                    except Exception as recover_err:
                        print(f"[异常恢复失败] {recover_err}")
                elif replicas == result["original_replicas"]:
                    print(f"[异常恢复] 当前副本数已是 {replicas}，无需重复恢复")
                    result["scale_up_ok"] = True
                else:
                    print(f"[异常恢复] 尝试将服务恢复至 {result['original_replicas']} 副本...")
                    try:
                        self.scale_service(master_key, result["original_replicas"])
                    except Exception as recover_err:
                        print(f"[异常恢复失败] {recover_err}")

            # 异常恢复后仍执行日志分析（记录异常期间发生了什么）
            print(f"\n[日志采集] 异常恢复后，开始下载并分析日志...")
            try:
                failover_events, master_alert_status = self.run_log_analysis(round_start_time=result["start_time"])
                result["master_alert_status"] = master_alert_status
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
                    result["failover_old_master"] = selected_event.get("old_master")
                    result["failover_new_master"] = selected_event.get("new_master")
                    result["failover_events"] = failover_events

                    # 打印所有切换事件的详细信息
                    print(f"\n[日志采集] 异常恢复后检测到 {len(failover_events)} 个切换事件:")
                    for evt in failover_events:
                        ts_str = evt["timestamp"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(evt["timestamp"], "strftime") else str(evt["timestamp"])
                        new_master = evt.get("new_master", "")
                        if "cluster_a" in new_master.lower():
                            master_label = "主集群A"
                        elif "cluster_b" in new_master.lower():
                            master_label = "主集群B"
                        else:
                            master_label = f"主集群{new_master}"
                        raw_line = evt.get("raw_line", "")
                        print(f"  {ts_str}  {master_label} {raw_line}")

                    # 收集所有 cost 值，逗号分割
                    all_costs = [str(evt.get("cost_ms", "")) for evt in failover_events if evt.get("cost_ms") is not None]
                    result["all_costs_str"] = ",".join(all_costs) if all_costs else None
                    print(f"[日志采集] 主备切换耗时: {result.get('all_costs_str') or result['failover_cost_ms']}ms ({result['failover_old_master']}→{result['failover_new_master']})")
            except Exception as log_err:
                print(f"[日志分析异常] {log_err}")

        finally:
            # === 停止 WS 后台采集并获取结果 ===
            if ws_client:
                try:
                    ws_client.stop()
                    result["ws_status"] = ws_client._get_check_result()
                    print("\n[WS] 后台采集已停止，结果已收集")
                    for conn_name, data in result["ws_status"].get("cluster_switch", {}).items():
                        changes = data.get("cluster_changes", 0)
                        master = data.get("master_cluster", "未知")
                        print(f"  [WS] {conn_name}: 主集群={master}, 切换次数={changes}")
                    for conn_name, data in result["ws_status"].get("track_data", {}).items():
                        uav_total = data.get("uav_total", 0)
                        msg_count = data.get("msg_count", 0)
                        print(f"  [WS] {conn_name}: 消息数={msg_count}, UAV总数={uav_total}")
                except Exception as e:
                    result["ws_status"] = f"WS采集异常({e})"
                    print(f"\n[WS] 停止采集时异常: {e}")

        return result

    # ==================== 入口 ====================

    def _pre_check(self) -> None:
        """
        执行前健康检查。
        检查 A/B 两个集群的目标服务状态，任一集群异常则终止测试。
        """
        print(f"\n[{'='*80}]")
        print("[执行前健康检查]")
        print(f"  检查服务: {self.target_service}")
        print(f"[{'='*80}]")

        issues = []
        for node_key in ["A", "B"]:
            node_name = IOMP_NODES[node_key]["name"]
            ready, replicas = self._get_service_replicas(node_key)

            if ready == -1 or replicas == -1:
                issues.append(f"{node_name}: 查询失败")
                print(f"  [{node_name}] 查询失败")
                continue

            print(f"  [{node_name}] ready={ready}, replicas={replicas}")

            if replicas == 0:
                issues.append(f"{node_name}: 副本数为 0（可能上次未恢复）")
            elif ready != replicas:
                issues.append(f"{node_name}: Pod 状态异常 ready={ready} != replicas={replicas}")

        if issues:
            print(f"\n[检查不通过] 发现以下问题，终止测试:")
            for issue in issues:
                print(f"  - {issue}")
            raise RuntimeError("执行前健康检查不通过")

        print("[检查通过] 两个集群服务状态正常，继续执行测试")

    def run(self) -> None:
        """执行完整测试流程"""
        print(f"\n{'='*80}")
        print("[HA 一键缩容测试]")
        if self.dry_run:
            print("  [DRY-RUN 模式] 不实际执行缩容/恢复操作")
        print(f"  目标服务: {self.target_service}")
        print(f"  命名空间: {self.target_namespace}")
        print(f"  集群名称: {self.cluster_name}")
        print(f"  缩容至: {self.scale_to_zero}")
        print(f"  等待时间: {self.wait_seconds} 秒")
        print(f"  轮次: {self.rounds}")
        print(f"  主集群: {self.master_node}")
        print(f"  日志分析窗口: {self.analysis_minutes} 分钟")
        print(f"{'='*80}")

        # 执行前健康检查
        try:
            self._pre_check()
        except RuntimeError as e:
            print(f"\n[测试终止] {e}")
            return

        self.round_results = []

        for i in range(1, self.rounds + 1):
            round_result = self.run_single_round(i)
            self.round_results.append(round_result)

            # 轮次间隔（最后一轮不间隔）
            # 为避免前一轮日志混入下一轮分析，建议间隔至少等于分析窗口时长
            if i < self.rounds:
                if self.round_gap_seconds is not None:
                    gap_seconds = self.round_gap_seconds
                else:
                    gap_seconds = max(180, self.analysis_minutes * 15)  # 至少分析窗口1/4的冷却时间，保底3分钟
                print(f"\n[轮次间隔] 等待 {gap_seconds} 秒后进入下一轮...")
                time.sleep(gap_seconds)

        # 测试报告与总结
        self._print_test_report()
        self._print_summary()

    def _print_summary(self) -> None:
        """打印测试总结"""
        print(f"\n{'='*140}")
        print("[测试总结]")
        print(f"{'='*140}")
        print(f"{'轮次':<4} {'主集群':<18} {'切换时间点':<10} {'副本':<4} {'缩容':<4} {'切换耗时':<38} {'执行时间':<8} {'ES同步':<6} {'关键服务状态':<8} {'ws告警存储':<10} {'结果'}")
        print(f"{'-'*140}")

        total_ok = 0
        for r in self.round_results:
            # 主集群方向
            master_node = r.get("master_node", "-")
            post_master = r.get("post_failover_master", "-")
            master_str = f"{master_node}->{post_master}" if master_node != "-" and post_master != "-" else "-"

            # 切换时间
            failover_time = r.get("failover_time", "-")
            if failover_time and failover_time != "-":
                try:
                    switch_time = failover_time.split(" ")[1].split(".")[0]
                except Exception:
                    switch_time = "-"
            else:
                switch_time = "-"

            # 主备切换耗时
            cost_str = "-"
            if r.get("all_costs_str"):
                old_m = r.get("failover_old_master", "")
                new_m = r.get("failover_new_master", "")
                direction = f"({old_m}→{new_m})" if old_m and new_m else ""
                cost_str = f"{r['all_costs_str']}ms{direction}"
            elif r.get("failover_cost_ms"):
                old_m = r.get("failover_old_master", "")
                new_m = r.get("failover_new_master", "")
                direction = f"({old_m}→{new_m})" if old_m and new_m else ""
                cost_str = f"{r['failover_cost_ms']}ms{direction}"
            else:
                master_node_name = r.get("master_node", "未知")
                cost_str = f"注入故障{master_node_name} daemon日志未检索到"

            # 整轮耗时
            duration = "-"
            start = r["start_time"] or ""
            end = r["end_time"] or ""
            if start and end:
                try:
                    dt_start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S.%f")
                    dt_end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f")
                    duration = f"{(dt_end - dt_start).total_seconds():.1f}s"
                except Exception:
                    duration = "-"

            # ES 同步状态简化
            es_status = r.get("es_status", "未检查")
            if "一致" in es_status:
                es_str = "一致"
            elif "不一致" in es_status:
                es_str = "不一致"
            else:
                es_str = "未检查"

            # 关键服务状态简化
            svc_status = r.get("services_status", "未检查")
            if "正常" in svc_status:
                svc_str = "正常"
            elif "异常" in svc_status or "失败" in svc_status:
                svc_str = "异常"
            else:
                svc_str = "未检查"

            # 主集群存储告警
            alert_str = r.get("master_alert_status", "未检查")

            # 场景测试结果
            status = "场景测试结果 不通过" if r["error"] else "场景测试结果 通过"
            if not r["error"]:
                total_ok += 1

            print(
                f"{r.get('round') or '-':<4} "
                f"{master_str:<18} "
                f"{switch_time:<10} "
                f"{r['original_replicas'] or '-':<4} "
                f"{'是' if r['scale_down_ok'] else '否':<4} "
                f"{cost_str:<38} "
                f"{duration:<8} "
                f"{es_str:<6} "
                f"{svc_str:<6} "
                f"{alert_str:<10} "
                f"{status}"
            )
            if r["error"]:
                print(f"  异常信息: {r['error']}")

        print(f"{'-'*140}")
        print(f"总计: {len(self.round_results)} 轮 | 通过: {total_ok} | 失败: {len(self.round_results) - total_ok}")
        print(f"{'='*140}")

    def _print_test_report(self) -> None:
        """生成简化版高可用测试报告"""
        now = datetime.now()

        # 1. 整体汇总信息
        self.logger.section("高可用测试报告")
        self.logger.info(f"测试服务名称: {self.target_service}")
        self.logger.info(f"命名空间: {self.target_namespace}")
        self.logger.info(f"集群名称: {self.cluster_name}")
        self.logger.info(f"报告生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        # 2. 切换指标汇总
        self.logger.subtitle("切换性能指标", 1)
        costs = []
        if self.round_results:
            # 提取所有切换耗时
            for r in self.round_results:
                if r.get('failover_cost_ms'):
                    cost = r['failover_cost_ms']
                    # 确保 cost 是数字类型
                    if isinstance(cost, (int, float)):
                        costs.append(cost)
                    elif isinstance(cost, str) and cost.isdigit():
                        costs.append(int(cost))
                    elif isinstance(cost, str) and cost.replace('.', '', 1).isdigit():
                        costs.append(float(cost))

            if costs:
                avg_cost = sum(costs) / len(costs)
                max_cost = max(costs)
                min_cost = min(costs)
                self.logger.info(f"切换次数: {len(costs)} 次")
                self.logger.info(f"平均耗时: {avg_cost:.0f}ms")
                self.logger.info(f"最大耗时: {max_cost}ms")
                self.logger.info(f"最小耗时: {min_cost}ms")

                # 每次切换的具体耗时
                self.logger.subtitle("各次切换耗时", 2)
                for i, cost in enumerate(costs, 1):
                    # 找到对应的轮次信息
                    for r in self.round_results:
                        cost_str = str(r.get('failover_cost_ms'))
                        cost_to_compare = str(cost)
                        if cost_str == cost_to_compare:
                            old_m = r.get('failover_old_master', '?')
                            new_m = r.get('failover_new_master', '?')
                            self.logger.debug(f"第{i}轮: {cost}ms ({old_m}→{new_m})")
                            break
            else:
                self.logger.warning("未检测到切换事件")

        # 3. 存储一致性检查汇总
        self.logger.subtitle("存储一致性检查", 1)

        # Redis 一致性
        redis_status = "未知"
        redis_consistent = True
        for r in self.round_results:
            if r.get('redis_status') and r['redis_status'] != "一致":
                redis_consistent = False
                break
        redis_status = "✓ 一致" if redis_consistent else "✗ 不一致"
        self.logger.info(f"Redis 同步状态: {redis_status}")

        # ES 一致性
        es_status = "未知"
        es_consistent = True
        es_mismatches = []
        for r in self.round_results:
            if r.get('es_status'):
                if r['es_status'] != "一致":
                    es_consistent = False
                    if r.get('es_mismatch_detail'):
                        es_mismatches.append(r['es_mismatch_detail'])
        es_status = "✓ 一致" if es_consistent else "✗ 不一致"
        if es_mismatches:
            self.logger.debug(f"ES 差异数量: {len(es_mismatches)} 个")
        self.logger.info(f"ES 数据同步状态: {es_status}")

        # DM 数据库一致性
        dm_status = "未知"
        dm_consistent = True
        for r in self.round_results:
            if r.get('dm_status') and r['dm_status'] != "一致":
                dm_consistent = False
                break
        dm_status = "✓ 一致" if dm_consistent else "✗ 不一致"
        self.logger.info(f"DM 数据库同步状态: {dm_status}")

        # 4. 其他检查项汇总
        self.logger.subtitle("其他检查项", 1)

        # 关键服务状态
        services_ok = True
        for r in self.round_results:
            if r.get('services_status') and "失败" in str(r['services_status']):
                services_ok = False
                break
        self.logger.info(f"关键服务状态: {'✓ 正常' if services_ok else '✗ 异常'}")

        # 服务恢复成功率
        scale_down_ok = sum(1 for r in self.round_results if r.get('scale_down_ok'))
        scale_up_ok = sum(1 for r in self.round_results if r.get('scale_up_ok'))
        self.logger.info(f"缩容成功率: {scale_down_ok}/{len(self.round_results)}")
        self.logger.info(f"恢复成功率: {scale_up_ok}/{len(self.round_results)}")

        # 5. 异常汇总
        failed_rounds = [r for r in self.round_results if r.get('error')]
        if failed_rounds:
            self.logger.subtitle("异常信息", 1)
            for i, r in enumerate(failed_rounds, 1):
                self.logger.error(f"异常轮次 {r['round']}: {r['error']}")

        self.logger.success("报告生成完毕")

        # 保存到文件
        report_file = os.path.join(self.log_dir, f"ha_test_report_{now.strftime('%Y%m%d_%H%M%S')}.txt")
        with open(report_file, 'w', encoding='utf-8') as f:
            # 保存到文件的格式化内容
            f.write(f"高可用测试报告 {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"=" * 80 + "\n\n")
            f.write(f"测试服务: {self.target_service}\n")
            f.write(f"总轮次: {len(self.round_results)}\n\n")

            # 切换指标
            f.write("切换性能指标:\n")
            f.write("-" * 40 + "\n")
            if costs:
                f.write(f"切换次数: {len(costs)} 次\n")
                f.write(f"平均耗时: {avg_cost:.0f}ms\n")
                f.write(f"最大耗时: {max_cost}ms\n")
                f.write(f"最小耗时: {min_cost}ms\n")
                f.write("\n各次切换耗时:\n")
                for i, cost in enumerate(costs, 1):
                    for r in self.round_results:
                        if r.get('failover_cost_ms') == cost:
                            old_m = r.get('failover_old_master', '?')
                            new_m = r.get('failover_new_master', '?')
                            f.write(f"  第{i}轮: {cost}ms ({old_m}→{new_m})\n")
                            break
            else:
                f.write("未检测到切换事件\n")

            # 存储一致性
            f.write("\n存储一致性检查:\n")
            f.write("-" * 40 + "\n")
            f.write(f"Redis 同步状态: {redis_status}\n")
            f.write(f"ES 数据同步状态: {es_status}\n")
            f.write(f"DM 数据库同步状态: {dm_status}\n")

            # 其他检查
            f.write("\n其他检查项:\n")
            f.write("-" * 40 + "\n")
            f.write(f"关键服务状态: {'✓ 正常' if services_ok else '✗ 异常'}\n")
            f.write(f"缩容成功率: {scale_down_ok}/{len(self.round_results)}\n")
            f.write(f"恢复成功率: {scale_up_ok}/{len(self.round_results)}\n")

            # 异常信息
            if failed_rounds:
                f.write("\n异常信息:\n")
                f.write("-" * 40 + "\n")
                for i, r in enumerate(failed_rounds, 1):
                    f.write(f"异常轮次 {r['round']}: {r['error']}\n")

        self.logger.success(f"详细报告已保存: {report_file}")


def main():
    """命令行入口"""
    # 生成日志文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"ha_scale_test_{timestamp}.txt")
    os.makedirs(LOG_DIR, exist_ok=True)

    with open(log_file, "w", encoding="utf-8") as f:
        old_stdout = sys.stdout
        sys.stdout = Tee(sys.stdout, f)
        try:
            tester = HaScaleTester()
            tester.run()
        finally:
            sys.stdout = old_stdout

    print(f"\n[日志已保存] {os.path.abspath(log_file)}")


if __name__ == "__main__":
    main()
