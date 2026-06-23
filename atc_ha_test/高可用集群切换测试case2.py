#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高可用集群切换测试case2脚本

功能：
1. 只测试 la-atc-frontend 和 la-atc-daemon-server 两个服务
2. 使用 cluster.txt 实时探测（0.1秒轮询）获取毫秒级切换指标
3. WS 日志分析（检查告警存储变化）
4. 生成综合测试报告

使用方式：
    python 高可用集群切换测试case2.py
"""

import os
import sys
import time
import ssl
import threading
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# 引入依赖模块
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from ha_scale_test import HaScaleTester, EnhancedLogger
from ha_env import cluster_api
from ws_client_check import run_ws_check

# ==================== 测试配置 ====================
# 只测试这两个服务
TEST_SERVICES = [
    'la-atc-frontend',
    'la-atc-daemon-server',
]

# 测试配置
TEST_CONFIG = {
    "rounds": 3,                # 每个服务的测试轮次
    "poll_interval": 5,         # 状态轮询间隔（秒）
    "poll_timeout": 300,        # 状态轮询超时（秒）
    "dry_run": False,           # True=只模拟流程，不实际缩容/恢复
    "master_node": "auto",       # "auto"=自动判断, "A"=A节点为主, "B"=B节点为主
}

# 输出配置 - 使用统一的 tmp 目录
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "tmp", "log")
REPORT_DIR = os.path.join(SCRIPT_DIR, "..", "tmp", "test_report")

# Cluster.txt 探测配置
CLUSTER_URL = "https://10.165.26.246/dolphin-agent/cluster.txt"
PROBE_INTERVAL = 0.1  # 探测间隔（秒）


# ==================== 数据结构 ====================
@dataclass
class ProbeEvent:
    """探测事件"""
    timestamp: str       # 时间戳字符串
    timestamp_ns: int    # 纳秒时间戳
    status: str          # "通" 或 "不通"
    cost_us: int         # 请求耗时（微秒）
    response: str         # 响应内容


@dataclass
class SwitchMetrics:
    """切换指标"""
    service_name: str
    round_num: int
    injection_time: str           # 故障注入时间
    detection_time: str           # 故障检测时间（检测到不通）
    recovery_time: str            # 恢复检测时间（检测到恢复通）
    propagation_cost_ms: float    # 故障传播耗时 (ms)
    recovery_cost_ms: float       # 故障恢复耗时 (ms)
    total_cost_ms: float         # 切换总耗时 (ms)
    scale_down_ok: bool           # 缩容是否成功
    scale_up_ok: bool            # 恢复是否成功
    ws_alert_status: str         # WS告警存储状态
    error: Optional[str] = None


# ==================== Cluster.txt 探测类 ====================
class ClusterProbe:
    """Cluster.txt 状态探测"""

    def __init__(self, url: str, interval: float = 0.1):
        self.url = url
        self.interval = interval
        self.events: List[ProbeEvent] = []
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_status: Optional[str] = None
        self.inject_time_ns: Optional[int] = None  # 注入故障时间

        # 状态变化回调
        self.on_failover_detected: Optional[callable] = None
        self.on_recovery_detected: Optional[callable] = None

    def do_request(self) -> tuple:
        """发起请求，返回 (status, cost_us, response)"""
        try:
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(self.url, method="GET")
            start_ns = time.time_ns()
            with urllib.request.urlopen(req, timeout=0.5, context=ctx) as resp:
                response = ' '.join(resp.read().decode("utf-8").strip().split())
                end_ns = time.time_ns()
                cost_us = (end_ns - start_ns) // 1000
                return ("通", cost_us, response)
        except Exception:
            end_ns = time.time_ns()
            cost_us = (end_ns - start_ns) // 1000 if 'start_ns' in locals() else 0
            return ("不通", cost_us, "")

    def probe_loop(self):
        """探测循环"""
        while self.running:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            now_ns = time.time_ns()
            status, cost_us, response = self.do_request()

            event = ProbeEvent(
                timestamp=now_str,
                timestamp_ns=now_ns,
                status=status,
                cost_us=cost_us,
                response=response
            )
            self.events.append(event)

            # 检测状态变化
            if self.last_status == "通" and status == "不通":
                # 故障传播
                if self.on_failover_detected:
                    self.on_failover_detected(now_str, now_ns)
            elif self.last_status == "不通" and status == "通":
                # 恢复检测
                if self.on_recovery_detected:
                    self.on_recovery_detected(now_str, now_ns)

            self.last_status = status
            time.sleep(self.interval)

    def start(self):
        """启动探测线程"""
        self.running = True
        self.events = []
        self.last_status = None
        self.thread = threading.Thread(target=self.probe_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """停止探测线程"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def set_injection_time(self):
        """设置故障注入时间点"""
        self.inject_time_ns = time.time_ns()

    def get_metrics(self) -> Dict:
        """从事件中提取切换指标"""
        metrics = {
            "injection_time": None,
            "detection_time": None,
            "recovery_time": None,
            "propagation_cost_ms": None,
            "recovery_cost_ms": None,
        }

        for i, event in enumerate(self.events):
            if self.last_status == "不通" and event.status == "通":
                # 恢复检测
                metrics["recovery_time"] = event.timestamp
                metrics["recovery_cost_ms"] = (event.timestamp_ns - self.last_failover_ns) / 1_000_000
            if self.last_status != "不通" and event.status == "不通":
                # 故障检测
                if metrics["injection_time"] is None and self.inject_time_ns:
                    metrics["injection_time"] = datetime.fromtimestamp(
                        self.inject_time_ns / 1_000_000_000
                    ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                metrics["detection_time"] = event.timestamp
                self.last_failover_ns = event.timestamp_ns
                metrics["propagation_cost_ms"] = (event.timestamp_ns - self.inject_time_ns) / 1_000_000

        # 计算总耗时
        if metrics["detection_time"] and metrics["recovery_time"]:
            d1 = datetime.strptime(metrics["detection_time"], "%Y-%m-%d %H:%M:%S.%f")
            d2 = datetime.strptime(metrics["recovery_time"], "%Y-%m-%d %H:%M:%S.%f")
            metrics["total_cost_ms"] = (d2 - d1).total_seconds() * 1000 + (metrics["recovery_cost_ms"] or 0) + (metrics["propagation_cost_ms"] or 0)

        return metrics


# ==================== WS 日志分析器 ====================
class WSLogAnalyzer:
    """WS 日志分析器（简化版，不下载完整日志）"""

    def __init__(self, log_dir: str):
        self.log_dir = log_dir

    def check_alert_status(self, service_name: str, round_num: int) -> Dict:
        """检查告警存储状态"""
        try:
            # 运行 WS 检查
            result = run_ws_check(save_report=True)
            if result:
                return {
                    "status": "正常",
                    "details": "WS连接正常"
                }
            return {
                "status": "异常",
                "details": "WS连接异常"
            }
        except Exception as e:
            return {
                "status": "检查失败",
                "details": str(e)
            }


# ==================== 主测试器 ====================
class HighAvailabilityCase2Tester:
    """高可用集群切换测试器 Case2"""

    def __init__(self):
        self.logger = EnhancedLogger()
        self.results: List[SwitchMetrics] = []
        self.output_dir = OUTPUT_DIR
        self.report_dir = REPORT_DIR
        self.report_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.report_dir, exist_ok=True)

        # 初始化组件
        self.ws_analyzer = WSLogAnalyzer(self.output_dir)

    def test_single_service(self, service_name: str, round_num: int) -> SwitchMetrics:
        """测试单个服务单轮"""
        self.logger.section(f"测试服务: {service_name} 第 {round_num} 轮")

        metrics = SwitchMetrics(
            service_name=service_name,
            round_num=round_num,
            injection_time="",
            detection_time="",
            recovery_time="",
            propagation_cost_ms=0,
            recovery_cost_ms=0,
            total_cost_ms=0,
            scale_down_ok=False,
            scale_up_ok=False,
            ws_alert_status="未检查"
        )

        # 创建探测器和回调
        probe = ClusterProbe(CLUSTER_URL, interval=PROBE_INTERVAL)
        failover_ns = None
        recovery_ns = None

        def on_failover(ts_str, ts_ns):
            nonlocal failover_ns
            failover_ns = ts_ns
            self.logger.info(f"[故障检测] {ts_str} - 检测到集群不通")

        def on_recovery(ts_str, ts_ns):
            nonlocal recovery_ns
            recovery_ns = ts_ns
            self.logger.info(f"[恢复检测] {ts_str} - 检测到集群恢复")

        probe.on_failover_detected = on_failover
        probe.on_recovery_detected = on_recovery

        try:
            # 阶段1: 缩容前检查
            self.logger.info("阶段1: 缩容前检查")
            tester = HaScaleTester(
                target_service=service_name,
                target_namespace="kedacom-project-namespace",
                cluster_name="dk",
                target_kind="Deployment",
                scale_to_zero=0,
                wait_seconds=10,
                rounds=1,
                poll_interval=5,
                poll_timeout=60,
                dry_run=False
            )
            tester._pre_check = lambda: None  # 跳过预检查

            # 获取当前副本数
            original_replicas = self._get_current_replicas(service_name)
            self.logger.info(f"当前副本数: {original_replicas}")

            # 阶段2: 启动探测
            self.logger.info("阶段2: 启动 cluster.txt 探测")
            probe.start()

            # 等待探测稳定
            time.sleep(1)

            # 阶段3: 注入故障（缩容）
            self.logger.info("阶段3: 注入故障（缩容）")
            injection_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            metrics.injection_time = injection_time
            probe.set_injection_time()

            scale_down_ok = self._scale_service(service_name, 0)
            metrics.scale_down_ok = scale_down_ok

            if not scale_down_ok:
                raise Exception("缩容失败")

            # 阶段4: 等待故障检测和恢复
            self.logger.info("阶段4: 等待故障检测和恢复")

            # 等待恢复检测（超时 5 分钟）
            wait_start = time.time()
            while recovery_ns is None and (time.time() - wait_start) < 300:
                time.sleep(0.5)

            if failover_ns:
                detection_time = datetime.fromtimestamp(
                    failover_ns / 1_000_000_000
                ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                metrics.detection_time = detection_time
                metrics.propagation_cost_ms = (failover_ns - probe.inject_time_ns) / 1_000_000

            if recovery_ns:
                recovery_time = datetime.fromtimestamp(
                    recovery_ns / 1_000_000_000
                ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                metrics.recovery_time = recovery_time
                if failover_ns:
                    metrics.recovery_cost_ms = (recovery_ns - failover_ns) / 1_000_000
                    metrics.total_cost_ms = metrics.propagation_cost_ms + metrics.recovery_cost_ms

            # 阶段5: 恢复服务
            self.logger.info("阶段5: 恢复服务")
            scale_up_ok = self._scale_service(service_name, original_replicas)
            metrics.scale_up_ok = scale_up_ok

            if not scale_up_ok:
                raise Exception("扩容失败")

            # 等待服务 Running
            self._wait_for_running(service_name, timeout=120)

            # 阶段6: 后置检查
            self.logger.info("阶段6: WS告警检查")
            ws_result = self.ws_analyzer.check_alert_status(service_name, round_num)
            metrics.ws_alert_status = ws_result.get("status", "检查失败")

            # 停止探测
            probe.stop()

        except Exception as e:
            self.logger.error(f"测试异常: {e}")
            metrics.error = str(e)
            probe.stop()

        return metrics

    def _get_current_replicas(self, service_name: str) -> int:
        """获取当前副本数"""
        try:
            from kubernetes import client, config
            config.load_kube_config()
            apps_v1 = client.AppsV1Api()
            namespace = "kedacom-project-namespace"

            deployment = apps_v1.read_namespaced_deployment(service_name, namespace)
            return deployment.spec.replicas or 1
        except Exception as e:
            self.logger.warning(f"获取副本数失败，使用默认值1: {e}")
            return 1

    def _scale_service(self, service_name: str, replicas: int) -> bool:
        """缩放服务"""
        try:
            from kubernetes import client, config
            config.load_kube_config()
            apps_v1 = client.AppsV1Api()
            namespace = "kedacom-project-namespace"

            body = {"spec": {"replicas": replicas}}
            apps_v1.patch_namespaced_deployment_scale(service_name, namespace, body)
            self.logger.info(f"缩放 {service_name} 到 {replicas} 副本")
            return True
        except Exception as e:
            self.logger.error(f"缩放失败: {e}")
            return False

    def _wait_for_running(self, service_name: str, timeout: int = 120) -> bool:
        """等待服务 Running"""
        try:
            from kubernetes import client, config
            config.load_kube_config()
            apps_v1 = client.AppsV1Api()
            namespace = "kedacom-project-namespace"

            start_time = time.time()
            while time.time() - start_time < timeout:
                deployment = apps_v1.read_namespaced_deployment(service_name, namespace)
                ready = deployment.status.ready_replicas or 0
                self.logger.info(f"就绪副本: {ready}/{deployment.spec.replicas}")
                if ready >= (deployment.spec.replicas or 1):
                    return True
                time.sleep(5)

            return False
        except Exception as e:
            self.logger.error(f"等待 Running 失败: {e}")
            return False

    def run_all_tests(self) -> None:
        """运行所有测试"""
        self.logger.section("高可用集群切换测试 Case2")
        self.logger.info(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"测试服务: {TEST_SERVICES}")
        self.logger.info(f"每服务轮次: {TEST_CONFIG['rounds']}")
        self.logger.info(f"探测间隔: {PROBE_INTERVAL}秒")

        total_tests = len(TEST_SERVICES) * TEST_CONFIG['rounds']
        current_test = 0

        for service_name in TEST_SERVICES:
            for round_num in range(1, TEST_CONFIG['rounds'] + 1):
                current_test += 1
                self.logger.section(f"进度: {current_test}/{total_tests}")

                metrics = self.test_single_service(service_name, round_num)
                self.results.append(metrics)

                # 轮次间隔
                if current_test < total_tests:
                    wait_time = 60
                    self.logger.info(f"等待 {wait_time} 秒后继续...")
                    time.sleep(wait_time)

        # 生成报告
        self.generate_reports()

    def generate_reports(self) -> None:
        """生成测试报告"""
        self.logger.section("生成测试报告")

        # TXT 报告
        report_file = os.path.join(self.report_dir, f"ha_case2_report_{self.report_timestamp}.txt")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"高可用集群切换测试报告 Case2 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 100 + "\n\n")

            f.write("[测试汇总]\n")
            f.write(f"测试服务: {TEST_SERVICES}\n")
            f.write(f"每服务轮次: {TEST_CONFIG['rounds']}\n")
            f.write(f"总测试数: {len(self.results)}\n\n")

            f.write("[详细指标]\n")
            f.write("-" * 100 + "\n")
            f.write(f"{'服务名':<25} {'轮次':<4} {'故障注入':<24} {'故障检测':<24} {'恢复检测':<24} "
                    f"{'传播ms':<10} {'恢复ms':<10} {'总计ms':<10} {'缩容':<6} {'扩容':<6} {'WS告警':<10}\n")
            f.write("-" * 100 + "\n")

            for m in self.results:
                error_str = f"错误: {m.error}" if m.error else ""
                f.write(
                    f"{m.service_name:<25} {m.round_num:<4} "
                    f"{m.injection_time:<24} {m.detection_time:<24} {m.recovery_time:<24} "
                    f"{m.propagation_cost_ms:<10.1f} {m.recovery_cost_ms:<10.1f} {m.total_cost_ms:<10.1f} "
                    f"{'成功' if m.scale_down_ok else '失败':<6} "
                    f"{'成功' if m.scale_up_ok else '失败':<6} "
                    f"{m.ws_alert_status:<10}\n"
                )
                if error_str:
                    f.write(f"  {error_str}\n")

            f.write("-" * 100 + "\n")

            # 性能统计
            valid_results = [m for m in self.results if m.total_cost_ms > 0]
            if valid_results:
                avg_propagation = sum(m.propagation_cost_ms for m in valid_results) / len(valid_results)
                avg_recovery = sum(m.recovery_cost_ms for m in valid_results) / len(valid_results)
                avg_total = sum(m.total_cost_ms for m in valid_results) / len(valid_results)

                f.write("\n[性能统计]\n")
                f.write(f"有效测试数: {len(valid_results)}\n")
                f.write(f"平均故障传播耗时: {avg_propagation:.1f} ms\n")
                f.write(f"平均故障恢复耗时: {avg_recovery:.1f} ms\n")
                f.write(f"平均切换总耗时: {avg_total:.1f} ms\n")

        self.logger.success(f"TXT报告已保存: {report_file}")

        # HTML 报告
        self._generate_html_report()

    def _generate_html_report(self) -> None:
        """生成 HTML 报告"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 性能统计
        valid_results = [m for m in self.results if m.total_cost_ms > 0]
        service_pass = sum(1 for m in self.results if not m.error)
        service_fail = len(self.results) - service_pass

        avg_propagation = sum(m.propagation_cost_ms for m in valid_results) / len(valid_results) if valid_results else 0
        avg_recovery = sum(m.recovery_cost_ms for m in valid_results) / len(valid_results) if valid_results else 0
        avg_total = sum(m.total_cost_ms for m in valid_results) / len(valid_results) if valid_results else 0

        html_rows = []
        for m in self.results:
            status = "通过" if not m.error else "不通过"
            css = "pass" if status == "通过" else "fail"
            propagation_str = f"{m.propagation_cost_ms:.1f}" if m.propagation_cost_ms > 0 else "-"
            recovery_str = f"{m.recovery_cost_ms:.1f}" if m.recovery_cost_ms > 0 else "-"
            total_str = f"{m.total_cost_ms:.1f}" if m.total_cost_ms > 0 else "-"

            html_rows.append(
                f'<tr>'
                f'<td>{m.service_name}</td>'
                f'<td>{m.round_num}</td>'
                f'<td>{m.injection_time or "-"}</td>'
                f'<td>{m.detection_time or "-"}</td>'
                f'<td>{m.recovery_time or "-"}</td>'
                f'<td>{propagation_str}</td>'
                f'<td>{recovery_str}</td>'
                f'<td>{total_str}</td>'
                f'<td>{"成功" if m.scale_down_ok else "失败"}</td>'
                f'<td>{"成功" if m.scale_up_ok else "失败"}</td>'
                f'<td>{m.ws_alert_status}</td>'
                f'<td class="{css}">{status}</td>'
                f'</tr>'
            )

        html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>高可用集群切换测试报告 Case2</title>
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
.container {{ max-width: 1400px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
h1 {{ text-align: center; color: #333; border-bottom: 3px solid #2196F3; padding-bottom: 15px; }}
h2 {{ color: #2196F3; margin-top: 30px; border-left: 4px solid #2196F3; padding-left: 10px; }}
.summary {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
.card {{ flex: 1; min-width: 180px; background: #fafafa; border-radius: 6px; padding: 15px; text-align: center; border: 1px solid #e0e0e0; }}
.card .label {{ font-size: 14px; color: #666; }}
.card .value {{ font-size: 24px; font-weight: bold; color: #333; margin-top: 5px; }}
.card.pass .value {{ color: #4CAF50; }}
.card.fail .value {{ color: #f44336; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }}
th, td {{ border: 1px solid #ddd; padding: 10px; text-align: center; }}
th {{ background: #2196F3; color: #fff; font-weight: bold; }}
tr:nth-child(even) {{ background: #f9f9f9; }}
tr:hover {{ background: #f1f1f1; }}
td.pass {{ color: #4CAF50; font-weight: bold; }}
td.fail, span.fail {{ color: #f44336; font-weight: bold; }}
.footer {{ text-align: center; margin-top: 30px; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
<h1>高可用集群切换测试报告 Case2</h1>
<p style="text-align:center;color:#666;">生成时间: {now_str}</p>

<div class="summary">
<div class="card"><div class="label">总测试数</div><div class="value">{len(self.results)}</div></div>
<div class="card pass"><div class="label">通过</div><div class="value">{service_pass}</div></div>
<div class="card fail"><div class="label">失败</div><div class="value">{service_fail}</div></div>
<div class="card"><div class="label">成功率</div><div class="value">{service_pass/len(self.results)*100:.1f if self.results else 0}%</div></div>
</div>

<div class="summary">
<div class="card"><div class="label">平均故障传播</div><div class="value">{avg_propagation:.1f}ms</div></div>
<div class="card"><div class="label">平均故障恢复</div><div class="value">{avg_recovery:.1f}ms</div></div>
<div class="card"><div class="label">平均切换总耗时</div><div class="value">{avg_total:.1f}ms</div></div>
</div>

<h2>测试明细</h2>
<table>
<thead>
<tr>
<th>服务名</th><th>轮次</th><th>故障注入</th><th>故障检测</th><th>恢复检测</th>
<th>传播耗时(ms)</th><th>恢复耗时(ms)</th><th>总耗时(ms)</th>
<th>缩容</th><th>扩容</th><th>WS告警</th><th>结果</th>
</tr>
</thead>
<tbody>
{''.join(html_rows)}
</tbody>
</table>

<div class="footer">Generated by HighAvailabilityCase2Tester</div>
</div>
</body>
</html>'''

        html_file = os.path.join(self.report_dir, f"ha_case2_report_{self.report_timestamp}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        self.logger.success(f"HTML报告已保存: {html_file}")


def main():
    """主函数"""
    tester = HighAvailabilityCase2Tester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
