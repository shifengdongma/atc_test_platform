#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高可用集群切换测试脚本

功能：
1. 自动判断主集群（通过 ws 日志分析或配置指定）
2. 对 DEPLOYMENT_SERVICES 和 STATEFULSET_SERVICES 中的所有服务逐个进行缩容测试
3. 对每个服务执行完整的 HA 测试流程
4. 收集所有测试结果，生成综合报告
5. 支持跳过某些服务（通过配置）

使用方式：
    1. 修改配置区的参数
    2. 直接运行: python high_availability_cluster_switch_test.py
"""

import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

# 引入 ha_scale_test
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from ha_scale_test import HaScaleTester, EnhancedLogger
# ==================== 测试配置 ====================
# 要跳过的服务列表（可以添加服务名来跳过测试）
SKIP_SERVICES = []

# 定向测试列表：只测试指定的服务（为空则测试所有服务，优先级高于 SKIP_SERVICES）
ONLY_SERVICES = []
#ONLY_SERVICES = ['redis-atc','emqx']

# 测试配置
TEST_CONFIG = {
    "wait_seconds": 120,        # 缩容后等待时间（秒）
    "rounds": 3,               # 每个服务的测试轮次
    "poll_interval": 5,        # 状态轮询间隔（秒）
    "poll_timeout": 300,       # 状态轮询超时（秒）
    "dry_run": False,          # True=只模拟流程，不实际缩容/恢复
    "master_node": "auto",     # "auto"=自动判断, "A"=A节点为主, "B"=B节点为主
    "analysis_minutes": 5,    # 日志分析时间窗口（分钟）
    "service_interval": 30,    # 服务间测试间隔（秒）
    "round_gap_seconds": None, # 轮次间隔（秒），None=自动计算（保底180秒）
}

# 输出配置 - 使用统一的 tmp 目录
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "tmp", "log")
REPORT_DIR = os.path.join(SCRIPT_DIR, "..", "tmp", "test_report")
# ==================== 服务列表 ====================
DEPLOYMENT_SERVICES = [
    'la-atc-ws-backend',
    'la-atc-data-exchange-ads-b',
    'al-atc-data-exchange-mqtt',
    'redis-atc',
    'la-atc-biz-backend',
    'la-atc-frontend',
    'gis-redis',
    'kgis-map-server',
    'kgis-portal-gateway',
    'cloud-rbac',
    'rbac-redis',
    'utm-mid-conflicts-v3',
    'utm-v3',
    'utm-conflicts-v3',
    'redis-hx',
    'la-atc-daemon-server',
]

STATEFULSET_SERVICES = [
    'emqx',
    'dol-kafka',
    'kafka-dkkghx',
    'dol-elasticsearch',
    #'dol-mysql',
]
DAEMONSET_SERVICES = [
    # 'keepalivedvip',
]

class UnifiedLogTee:
    """统一日志 Tee：stdout + 单一日志文件（行缓冲，即时落盘）"""
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log = open(log_path, "a", encoding="utf-8", buffering=1)
        self.log_path = log_path

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        if self.log:
            self.log.close()
            self.log = None

class HighAvailabilityClusterTester:
    """高可用集群切换测试器"""

    def __init__(self):
        self.logger = EnhancedLogger()
        self.results = []  # 存储所有测试结果
        self.output_dir = OUTPUT_DIR
        self.report_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        self.report_dir = REPORT_DIR
        os.makedirs(self.report_dir, exist_ok=True)

    def test_single_service(self, service_name: str) -> Dict:
        """单个服务的高可用测试"""
        start_time = datetime.now()

        self.logger.section(f"开始测试服务: {service_name}")
        self.logger.info(f"服务类型: {'DEPLOYMENT' if service_name in DEPLOYMENT_SERVICES else 'STATEFULSET' if service_name in STATEFULSET_SERVICES else 'DAEMONSET'}")

        result = {
            "service_name": service_name,
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "status": "pending",
            "error": None,
            "switch_events": [],
            "storage_results": {
                "redis": "未测试",
                "es": "未测试",
                "dm": "未测试"
            },
            "scale_down_ok": False,
            "scale_up_ok": False,
            "failover_events": [],
            "failover_cost_ms": None
        }

        try:
            # 创建测试器实例
            tester = HaScaleTester(
                target_service=service_name,
                target_namespace="kedacom-project-namespace",
                cluster_name="dk",
                target_kind="All",
                scale_to_zero=0,
                wait_seconds=TEST_CONFIG["wait_seconds"],
                rounds=TEST_CONFIG["rounds"],
                master_node=TEST_CONFIG["master_node"],
                analysis_minutes=TEST_CONFIG["analysis_minutes"],
                log_dir=self.output_dir,
                poll_interval=TEST_CONFIG["poll_interval"],
                poll_timeout=TEST_CONFIG["poll_timeout"],
                dry_run=TEST_CONFIG["dry_run"],
                round_gap_seconds=TEST_CONFIG.get("round_gap_seconds"),
            )

            # 执行测试（不执行前检查，因为我们会在外层检查）
            tester._pre_check = lambda: None  # 临时禁用前检查
            tester._print_summary = lambda: None  # 禁用单服务测试总结，由外层脚本统一汇总
            tester._print_test_report = lambda: None  # 禁用单服务测试报告，由外层脚本统一汇总

            # 执行测试（可能抛出异常）
            tester.run()

            # 收集结果
            if tester.round_results:
                result["round_results"] = tester.round_results
                last_round = tester.round_results[-1]
                result["status"] = "completed" if not last_round.get("error") else "failed"
                result["error"] = last_round.get("error")
                result["scale_down_ok"] = last_round.get("scale_down_ok", False)
                result["scale_up_ok"] = last_round.get("scale_up_ok", False)
                result["failover_cost_ms"] = last_round.get("failover_cost_ms")
                result["failover_events"] = last_round.get("failover_events", [])

                # 存储检查结果
                result["storage_results"] = {
                    "redis": last_round.get("redis_status", "未检查"),
                    "es": last_round.get("es_status", "未检查"),
                    "dm": last_round.get("dm_status", "未检查")
                }

                # 提取切换事件
                if last_round.get("failover_events"):
                    for evt in last_round.get("failover_events", []):
                        result["switch_events"].append({
                            "timestamp": evt.get("timestamp"),
                            "old_master": evt.get("old_master"),
                            "new_master": evt.get("new_master"),
                            "cost_ms": evt.get("cost_ms")
                        })

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self.logger.success(f"服务 {service_name} 测试完成（耗时 {duration:.1f}秒）")

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)
            self.logger.error(f"服务 {service_name} 测试失败: {e}")

        return result

    def pre_check_service(self, service_name: str) -> bool:
        """服务预检查"""
        try:
            # 创建临时测试器用于检查
            tester = HaScaleTester(
                target_service=service_name,
                target_namespace="kedacom-project-namespace",
                cluster_name="dk",
                target_kind="All",
                scale_to_zero=0,
                wait_seconds=10,
                rounds=1,
                poll_interval=5,
                poll_timeout=60,
                dry_run=False
            )

            # 执行健康检查
            tester._pre_check()
            return True

        except Exception as e:
            self.logger.warning(f"服务 {service_name} 预检查失败: {e}")
            return False

    def run_all_tests(self) -> None:
        """运行所有服务的测试"""
        # 启动统一日志：stdout 同时输出到终端和单一日志文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unified_log = os.path.join(self.output_dir, f"ha_cluster_test_{timestamp}.log")
        os.makedirs(self.output_dir, exist_ok=True)
        tee = UnifiedLogTee(unified_log)
        old_stdout = sys.stdout
        sys.stdout = tee
        try:
            self.logger.section("高可用集群切换测试")
            self.logger.info(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"统一日志文件: {unified_log}")
            self.logger.info(f"总共 {len(DEPLOYMENT_SERVICES) + len(STATEFULSET_SERVICES) + len(DAEMONSET_SERVICES)} 个服务")
            self.logger.info(f"跳过服务: {SKIP_SERVICES}")

            # 获取要测试的服务列表
            all_services = []
            all_services.extend(DEPLOYMENT_SERVICES)
            all_services.extend(STATEFULSET_SERVICES)
            all_services.extend(DAEMONSET_SERVICES)

            # 定向测试模式：若 ONLY_SERVICES 非空，只测试这些服务
            if ONLY_SERVICES:
                test_services = [s for s in all_services if s in ONLY_SERVICES]
                self.logger.warning(f"[定向测试模式] 仅测试以下 {len(test_services)} 个服务: {test_services}")
            else:
                # 过滤掉要跳过的服务
                test_services = [s for s in all_services if s not in SKIP_SERVICES]

            self.logger.info(f"实际测试服务数量: {len(test_services)}")

            # 依次测试每个服务
            success_count = 0
            failed_count = 0
            skipped_count = 0

            for i, service_name in enumerate(test_services, 1):
                self.logger.section(f"进度: {i}/{len(test_services)}")

                # 预检查
                if not self.pre_check_service(service_name):
                    self.logger.error(f"跳过服务 {service_name}，预检查失败")
                    self.results.append({
                        "service_name": service_name,
                        "status": "skipped",
                        "error": "预检查失败"
                    })
                    skipped_count += 1
                    continue

                # 执行测试
                test_result = self.test_single_service(service_name)
                self.results.append(test_result)

                if test_result["status"] == "completed":
                    success_count += 1
                elif test_result["status"] == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1

                # 增量更新报告（静默写入，不输出终端）
                self.generate_summary_report(success_count, failed_count, skipped_count, len(test_services), silent=True)

                # 服务间间隔（避免冲击太大）
                if i < len(test_services):
                    wait_time = TEST_CONFIG["service_interval"]
                    self.logger.info(f"等待 {wait_time} 秒后测试下一个服务...")
                    time.sleep(wait_time)

            # 最终完整报告（带终端输出）
            self.generate_summary_report(success_count, failed_count, skipped_count, len(test_services), silent=False)
        finally:
            sys.stdout = old_stdout
            tee.close()
            print(f"[统一日志已保存] {unified_log}")

            # === 兜底清理：只保留三类目标文件，删除其他中间日志 ===
            import glob
            try:
                for f in glob.glob(os.path.join(self.output_dir, "ws_客户端信息检查_*.txt")):
                    os.remove(f)
                    print(f"[清理] 已删除中间文件: {os.path.basename(f)}")
            except Exception as e:
                print(f"[清理警告] 删除中间文件时异常: {e}")

    def generate_summary_report(self, success_count: int, failed_count: int, skipped_count: int, total_count: int, silent: bool = False) -> None:
        """生成综合测试报告"""

        def _fmt_master(r):
            master_node = r.get("master_node", "-")
            post_master = r.get("post_failover_master", "-")
            return f"{master_node}->{post_master}" if master_node != "-" and post_master != "-" else "-"

        def _fmt_switch_time(r):
            failover_time = r.get("failover_time", "-")
            if failover_time and failover_time != "-":
                try:
                    return failover_time.split(" ")[1].split(".")[0]
                except Exception:
                    pass
            return "-"

        def _fmt_cost(r):
            if r.get("all_costs_str"):
                d = f"({r.get('failover_old_master','')}→{r.get('failover_new_master','')})" if r.get('failover_old_master') and r.get('failover_new_master') else ""
                return f"{r['all_costs_str']}ms{d}"
            elif r.get("failover_cost_ms"):
                d = f"({r.get('failover_old_master','')}→{r.get('failover_new_master','')})" if r.get('failover_old_master') and r.get('failover_new_master') else ""
                return f"{r['failover_cost_ms']}ms{d}"
            return f"注入故障{r.get('master_node','未知')} daemon日志未检索到"

        def _fmt_duration(r):
            s, e = r.get("start_time",""), r.get("end_time","")
            if s and e:
                try:
                    from datetime import datetime
                    ds = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
                    de = datetime.strptime(e, "%Y-%m-%d %H:%M:%S.%f")
                    return f"{(de-ds).total_seconds():.1f}s"
                except Exception:
                    pass
            return "-"

        def _fmt_es(r):
            es = r.get("es_status", "未检查")
            return "一致" if "一致" in es else "不一致" if "不一致" in es else "未检查"

        def _fmt_svc(r):
            svc = r.get("services_status", "未检查")
            return "正常" if "正常" in svc else "异常" if "异常" in svc or "失败" in svc else "未检查"

        def _fmt_alert(r):
            return r.get("master_alert_status", "未检查")

        def _fmt_status(r):
            return "场景测试结果 不通过" if r.get("error") else "场景测试结果 通过"

        if not silent:
            self.logger.section("测试汇总报告")

        # 收集所有输出行，同时打印并写入文件
        report_lines = []

        def _add_line(line: str = ""):
            if not silent:
                print(line)
            report_lines.append(line)

        _add_line(f"\n{'='*165}")
        _add_line("服务名                     轮次 主集群          切换时间点   副本 缩容 恢复 切换耗时                            执行时间     ES同步   关键服务状态 ws告警存储 结果")
        _add_line(f"{'-'*165}")

        for result in self.results:
            service_name = result["service_name"]
            round_results = result.get("round_results", [])

            if not round_results:
                status_label = "场景测试结果 不通过" if result.get("error") else "场景测试结果 通过"
                _add_line(f"{service_name:<24} {'-':<4} {'-':<16} {'-':<10} {'-':<4} {'-':<4} {'-':<4} {'-':<36} {'-':<8} {'-':<6} {'-':<6} {'-':<10} {status_label}")
                if result.get("error"):
                    _add_line(f"  异常信息: {result['error']}")
                continue

            svc_pass = 0
            svc_fail = 0
            for r in round_results:
                status_label = _fmt_status(r)
                if r.get("error"):
                    svc_fail += 1
                else:
                    svc_pass += 1

                _add_line(
                    f"{service_name:<24} "
                    f"{r['round']:<4} "
                    f"{_fmt_master(r):<16} "
                    f"{_fmt_switch_time(r):<10} "
                    f"{r.get('original_replicas') or '-':<4} "
                    f"{'成功' if r.get('scale_down_ok') else '失败':<4} "
                    f"{'成功' if r.get('scale_up_ok') else '失败':<4} "
                    f"{_fmt_cost(r):<36} "
                    f"{_fmt_duration(r):<8} "
                    f"{_fmt_es(r):<6} "
                    f"{_fmt_svc(r):<6} "
                    f"{_fmt_alert(r):<10} "
                    f"{status_label}"
                )
                if r.get("error"):
                    _add_line(f"  异常信息: {r['error']}")

            _add_line(f"{'-'*165}")
            _add_line(f"测试 {service_name} | 通过：{svc_pass} | 失败：{svc_fail}")

        _add_line(f"{'='*165}")

        # 按服务维度收集切换性能数据（用于TXT报告，过滤<100ms）
        txt_service_perf = {}
        for result in self.results:
            svc_name = result["service_name"]
            for r in result.get("round_results", []):
                if svc_name not in txt_service_perf:
                    txt_service_perf[svc_name] = {"count": 0, "costs": []}
                costs = []
                if r.get("all_costs_str"):
                    for c in str(r["all_costs_str"]).split(","):
                        c = c.strip()
                        if c.isdigit():
                            costs.append(int(c))
                elif r.get("failover_cost_ms"):
                    cost = r["failover_cost_ms"]
                    if isinstance(cost, (int, float)):
                        costs.append(int(cost))
                    elif isinstance(cost, str) and cost.isdigit():
                        costs.append(int(cost))
                for cost in costs:
                    if cost >= 100:
                        txt_service_perf[svc_name]["count"] += 1
                        txt_service_perf[svc_name]["costs"].append(cost)

        # 全量统计
        if not silent:
            self.logger.info(f"总服务数: {total_count}")
            self.logger.info(f"成功服务数: {success_count}")
            self.logger.info(f"失败服务数: {failed_count}")
            self.logger.info(f"跳过服务数: {skipped_count}")
            self.logger.info(f"成功率: {success_count/total_count*100:.1f}%")

        # 切换性能统计（从所有服务的所有轮次中收集，不限于 completed 状态）
        all_costs = []
        all_switch_events = []
        for result in self.results:
            rounds = result.get("round_results", [])
            if rounds:
                for r in rounds:
                    # 收集切换耗时（支持 failover_cost_ms 单值 或 all_costs_str 多值）
                    if r.get("failover_cost_ms"):
                        cost = r["failover_cost_ms"]
                        if isinstance(cost, (int, float)):
                            all_costs.append(cost)
                        elif isinstance(cost, str) and cost.isdigit():
                            all_costs.append(int(cost))
                    if r.get("all_costs_str"):
                        for c in str(r["all_costs_str"]).split(","):
                            c = c.strip()
                            if c.isdigit():
                                all_costs.append(int(c))
                    # 收集切换事件
                    if r.get("failover_events"):
                        for evt in r["failover_events"]:
                            all_switch_events.append({
                                "timestamp": evt.get("timestamp"),
                                "old_master": evt.get("old_master"),
                                "new_master": evt.get("new_master"),
                                "cost_ms": evt.get("cost_ms")
                            })
            else:
                # 兼容无轮次详情的情况（如预检查失败）
                if result.get("failover_cost_ms"):
                    cost = result["failover_cost_ms"]
                    if isinstance(cost, (int, float)):
                        all_costs.append(cost)
                    elif isinstance(cost, str) and cost.isdigit():
                        all_costs.append(int(cost))
                if result.get("switch_events"):
                    all_switch_events.extend(result["switch_events"])

        if not silent:
            if all_costs:
                avg_cost = sum(all_costs) / len(all_costs)
                self.logger.info(f"总切换次数: {len(all_switch_events)}")
                self.logger.info(f"平均切换耗时: {avg_cost:.0f}ms")
                fast_switches = [c for c in all_costs if c < 5000]
                slow_switches = [c for c in all_costs if c >= 5000]
                self.logger.info(f"快速切换(<5s): {len(fast_switches)} 次")
                self.logger.info(f"慢速切换(>=5s): {len(slow_switches)} 次")
            else:
                self.logger.info("切换性能统计: 未检测到有效切换耗时数据")

        # 存储一致性统计（从所有轮次中收集，不限于 completed 状态）
        redis_stats = {"正常": 0, "异常": 0, "检查失败": 0}
        es_stats = {"正常": 0, "异常": 0, "检查失败": 0}
        dm_stats = {"正常": 0, "异常": 0, "检查失败": 0}
        checked_count = 0
        for result in self.results:
            rounds = result.get("round_results", [])
            if rounds:
                for r in rounds:
                    redis_status = r.get("redis_status", "未检查")
                    es_status = r.get("es_status", "未检查")
                    dm_status = r.get("dm_status", "未检查")
                    # 只要任一存储类型被检查过（非未测试/未检查）就计数
                    if redis_status not in ("未测试", "未检查") or es_status not in ("未测试", "未检查") or dm_status not in ("未测试", "未检查"):
                        checked_count += 1
                        if redis_status == "一致":
                            redis_stats["正常"] += 1
                        elif redis_status == "不一致":
                            redis_stats["异常"] += 1
                        else:
                            redis_stats["检查失败"] += 1
                        if es_status == "一致":
                            es_stats["正常"] += 1
                        elif es_status == "不一致":
                            es_stats["异常"] += 1
                        else:
                            es_stats["检查失败"] += 1
                        if dm_status == "一致":
                            dm_stats["正常"] += 1
                        elif dm_status == "不一致":
                            dm_stats["异常"] += 1
                        else:
                            dm_stats["检查失败"] += 1
            else:
                # 兼容无轮次详情的情况
                storage = result.get("storage_results")
                if not storage:
                    continue
                checked_count += 1
                redis_status = storage.get("redis", "未检查")
                es_status = storage.get("es", "未检查")
                dm_status = storage.get("dm", "未检查")
                if redis_status == "一致":
                    redis_stats["正常"] += 1
                elif redis_status == "不一致":
                    redis_stats["异常"] += 1
                else:
                    redis_stats["检查失败"] += 1
                if es_status == "一致":
                    es_stats["正常"] += 1
                elif es_status == "不一致":
                    es_stats["异常"] += 1
                else:
                    es_stats["检查失败"] += 1
                if dm_status == "一致":
                    dm_stats["正常"] += 1
                elif dm_status == "不一致":
                    dm_stats["异常"] += 1
                else:
                    dm_stats["检查失败"] += 1

        if not silent:
            self.logger.info(f"Redis 一致性: {redis_stats['正常']}/{checked_count} 正常, {redis_stats['异常']} 异常, {redis_stats['检查失败']} 检查失败")
            self.logger.info(f"ES 一致性: {es_stats['正常']}/{checked_count} 正常, {es_stats['异常']} 异常, {es_stats['检查失败']} 检查失败")
            self.logger.info(f"DM 一致性: {dm_stats['正常']}/{checked_count} 正常, {dm_stats['异常']} 异常, {dm_stats['检查失败']} 检查失败")

        # 写入详细报告文件
        report_file = os.path.join(self.report_dir, f"ha_cluster_test_report_{self.report_timestamp}.txt")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"高可用集群切换测试报告 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 100 + "\n\n")

            # 写入整合表格
            f.write("[测试汇总报告]\n")
            f.write("\n".join(report_lines) + "\n\n")

            f.write("1. 测试统计\n")
            f.write("-" * 50 + "\n")
            f.write(f"总服务数: {total_count}\n")
            f.write(f"成功服务数: {success_count}\n")
            f.write(f"失败服务数: {failed_count}\n")
            f.write(f"跳过服务数: {skipped_count}\n")
            f.write(f"成功率: {success_count/total_count*100:.1f}%\n\n")

            f.write("2. 各服务详细结果\n")
            f.write("-" * 50 + "\n")
            for result in self.results:
                service_name = result["service_name"]
                f.write(f"\n服务: {service_name}\n")
                round_results = result.get("round_results", [])
                if round_results:
                    svc_pass = sum(1 for r in round_results if not r.get("error"))
                    svc_fail = sum(1 for r in round_results if r.get("error"))
                    f.write(f"通过: {svc_pass} | 失败: {svc_fail}\n")
                    for r in round_results:
                        status = "通过" if not r.get("error") else "不通过"
                        cost = r.get("all_costs_str") or r.get("failover_cost_ms") or "-"
                        f.write(f"  轮次{r['round']}: {status}, 切换耗时: {cost}ms\n")
                        if r.get("error"):
                            f.write(f"    异常: {r['error']}\n")
                else:
                    f.write(f"状态: {result['status']}\n")
                    if result.get("error"):
                        f.write(f"错误: {result['error']}\n")
                f.write("\n")

            if txt_service_perf:
                f.write("3. 切换性能（按服务维度）\n")
                f.write("-" * 50 + "\n")
                for svc_name, data in txt_service_perf.items():
                    if not data["costs"]:
                        continue
                    min_cost = min(data["costs"])
                    max_cost = max(data["costs"])
                    if min_cost == max_cost:
                        cost_str = f"{min_cost}"
                    else:
                        cost_str = f"{min_cost}~{max_cost}"
                    flag = " [超时]" if max_cost >= 1000 else ""
                    f.write(f"{svc_name}: 切换次数={data['count']}, 耗时范围={cost_str}ms{flag}\n")
                f.write("\n")

        if not silent:
            self.logger.success(f"详细报告已保存: {report_file}")

        # 生成 HTML 报告
        self._generate_html_report(success_count, failed_count, skipped_count, total_count, all_costs, all_switch_events, redis_stats, es_stats, dm_stats, silent=silent)

    def _generate_html_report(self, success_count, failed_count, skipped_count, total_count, all_costs, all_switch_events, redis_stats, es_stats, dm_stats, silent: bool = False):
        """生成 HTML 格式报告"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        def _html_master(r):
            master_node = r.get("master_node", "-")
            post_master = r.get("post_failover_master", "-")
            return f"{master_node}->{post_master}" if master_node != "-" and post_master != "-" else "-"

        def _html_switch_time(r):
            failover_time = r.get("failover_time", "-")
            if failover_time and failover_time != "-":
                try:
                    return failover_time.split(" ")[1].split(".")[0]
                except Exception:
                    pass
            return "-"

        def _html_cost(r):
            if r.get("all_costs_str"):
                return f"{r['all_costs_str']}ms"
            elif r.get("failover_cost_ms"):
                return f"{r['failover_cost_ms']}ms"
            return f"注入故障{r.get('master_node','未知')} daemon日志未检索到"

        def _html_duration(r):
            s, e = r.get("start_time",""), r.get("end_time","")
            if s and e:
                try:
                    from datetime import datetime
                    ds = datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
                    de = datetime.strptime(e, "%Y-%m-%d %H:%M:%S.%f")
                    return f"{(de-ds).total_seconds():.1f}s"
                except Exception:
                    pass
            return "-"

        def _html_es(r):
            es = r.get("es_status", "未检查")
            return "一致" if "一致" in es else "不一致" if "不一致" in es else "未检查"

        def _html_svc(r):
            svc = r.get("services_status", "未检查")
            return "正常" if "正常" in svc else "异常" if "异常" in svc or "失败" in svc else "未检查"

        def _html_alert(r):
            return r.get("master_alert_status", "未检查")

        def _check_round_pass(r) -> tuple[bool, dict]:
            """基于实际数据判定单轮是否通过，返回 (是否通过, 标红字段字典)"""
            red = {}
            # 1. 主集群变化
            master = r.get("master_node", "-")
            post = r.get("post_failover_master", "-")
            if master == "-" or post == "-" or master == post:
                red['master'] = True
            # 2. 缩容
            if not r.get("scale_down_ok"):
                red['scale_down'] = True
            # 3. 恢复
            if not r.get("scale_up_ok"):
                red['scale_up'] = True
            # 4. 切换耗时（存在性 + 超限检查）
            costs = []
            if r.get("all_costs_str"):
                for c in str(r["all_costs_str"]).split(","):
                    c = c.strip()
                    if c.isdigit():
                        costs.append(int(c))
            elif r.get("failover_cost_ms"):
                cost = r["failover_cost_ms"]
                if isinstance(cost, (int, float)):
                    costs.append(int(cost))
                elif isinstance(cost, str) and cost.isdigit():
                    costs.append(int(cost))
            if not costs:
                red['cost'] = True
            elif any(c >= 1000 for c in costs):
                red['cost_overrun'] = True
            # 5. ES
            es = r.get("es_status", "未检查")
            if "一致" not in es:
                red['es'] = True
            # 6. 服务
            svc = r.get("services_status", "未检查")
            if "正常" not in svc:
                red['svc'] = True
            # 7. 存储告警
            alert = r.get("master_alert_status", "未检查")
            if alert != "正确":
                red['alert'] = True
            return len(red) == 0, red

        # 按服务维度统计通过/失败及切换性能数据
        service_pass = 0
        service_fail = 0
        result_total = 0
        result_pass = 0
        result_fail = 0
        service_perf = {}  # 服务名 -> {"count": 次数, "costs": [耗时列表]}

        for result in self.results:
            svc_name = result["service_name"]
            rounds = result.get("round_results", [])
            svc_all_pass = True
            for r in rounds:
                is_pass, _ = _check_round_pass(r)
                result_total += 1
                if is_pass:
                    result_pass += 1
                else:
                    result_fail += 1
                    svc_all_pass = False
                # 收集切换性能（按服务维度，过滤<100ms）
                if svc_name not in service_perf:
                    service_perf[svc_name] = {"count": 0, "costs": []}
                costs = []
                if r.get("all_costs_str"):
                    for c in str(r["all_costs_str"]).split(","):
                        c = c.strip()
                        if c.isdigit():
                            costs.append(int(c))
                elif r.get("failover_cost_ms"):
                    cost = r["failover_cost_ms"]
                    if isinstance(cost, (int, float)):
                        costs.append(int(cost))
                    elif isinstance(cost, str) and cost.isdigit():
                        costs.append(int(cost))
                for cost in costs:
                    if cost >= 100:
                        service_perf[svc_name]["count"] += 1
                        service_perf[svc_name]["costs"].append(cost)
            if not rounds:
                result_total += 1
                if result.get("status") == "completed" and not result.get("error"):
                    result_pass += 1
                else:
                    result_fail += 1
                    svc_all_pass = False
            if svc_all_pass:
                service_pass += 1
            else:
                service_fail += 1

        html_rows = []
        for result in self.results:
            service_name = result["service_name"]
            round_results = result.get("round_results", [])
            if not round_results:
                status = "不通过" if result.get("error") else "通过"
                css = "pass" if status == "通过" else "fail"
                html_rows.append(f'<tr><td>{service_name}</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td class="{css}">{status}</td></tr>')
                continue
            for r in round_results:
                is_pass, red = _check_round_pass(r)
                status = "通过" if is_pass else "不通过"
                css = "pass" if is_pass else "fail"
                # 各列标红控制
                c_master = 'class="fail"' if red.get('master') else ''
                c_scale_down = 'class="fail"' if red.get('scale_down') else ''
                c_scale_up = 'class="fail"' if red.get('scale_up') else ''
                c_cost = 'class="fail"' if red.get('cost') or red.get('cost_overrun') else ''
                c_es = 'class="fail"' if red.get('es') else ''
                c_svc = 'class="fail"' if red.get('svc') else ''
                c_alert = 'class="fail"' if red.get('alert') else ''
                html_rows.append(
                    f'<tr>'
                    f'<td>{service_name}</td>'
                    f'<td>{r["round"]}</td>'
                    f'<td {c_master}>{_html_master(r)}</td>'
                    f'<td>{_html_switch_time(r)}</td>'
                    f'<td>{r.get("original_replicas") or "-"}</td>'
                    f'<td {c_scale_down}>{"成功" if r.get("scale_down_ok") else "失败"}</td>'
                    f'<td {c_scale_up}>{"成功" if r.get("scale_up_ok") else "失败"}</td>'
                    f'<td {c_cost}>{_html_cost(r)}</td>'
                    f'<td>{_html_duration(r)}</td>'
                    f'<td {c_es}>{_html_es(r)}</td>'
                    f'<td {c_svc}>{_html_svc(r)}</td>'
                    f'<td {c_alert}>{_html_alert(r)}</td>'
                    f'<td class="{css}">{status}</td>'
                    f'</tr>'
                )

        # 切换性能统计（按服务维度，过滤<100ms，>=1000ms标红）
        perf_rows = ""
        if service_perf:
            for svc_name, data in service_perf.items():
                if not data["costs"]:
                    continue
                min_cost = min(data["costs"])
                max_cost = max(data["costs"])
                if min_cost == max_cost:
                    if max_cost >= 1000:
                        cost_str = f'<span class="fail">{min_cost}</span>'
                    else:
                        cost_str = f"{min_cost}"
                else:
                    if max_cost >= 1000:
                        if min_cost >= 1000:
                            cost_str = f'<span class="fail">{min_cost}</span>~<span class="fail">{max_cost}</span>'
                        else:
                            cost_str = f'{min_cost}~<span class="fail">{max_cost}</span>'
                    else:
                        cost_str = f"{min_cost}~{max_cost}"
                perf_rows += f'<tr><td>{svc_name}</td><td>{data["count"]}</td><td>{cost_str}</td></tr>'
        else:
            perf_rows += '<tr><td colspan="3">未检测到有效切换事件</td></tr>'

        html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>高可用集群切换测试报告</title>
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
<h1>高可用集群切换测试报告</h1>
<p style="text-align:center;color:#666;">生成时间: {now_str}</p>

<div class="summary">
<div class="card"><div class="label">总服务数</div><div class="value">{total_count}</div></div>
<div class="card pass"><div class="label">通过服务数</div><div class="value">{service_pass}</div></div>
<div class="card fail"><div class="label">失败服务数</div><div class="value">{service_fail}</div></div>
<div class="card"><div class="label">成功率</div><div class="value">{service_pass/total_count*100:.1f}%</div></div>
</div>

<div class="summary">
<div class="card"><div class="label">测试结果统计</div><div class="value">{result_total}</div></div>
<div class="card pass"><div class="label">通过</div><div class="value">{result_pass}</div></div>
<div class="card fail"><div class="label">失败</div><div class="value">{result_fail}</div></div>
<div class="card"><div class="label">跳过</div><div class="value">{skipped_count}</div></div>
<div class="card"><div class="label">通过率</div><div class="value">{(result_pass/result_total*100 if result_total else 0):.1f}%</div></div>
</div>

<h2>测试汇总表格</h2>
<table>
<thead>
<tr>
<th>服务名</th><th>轮次</th><th>主集群</th><th>切换时间点</th><th>副本</th><th>缩容</th><th>恢复</th>
<th>切换耗时</th><th>执行时间</th><th>ES同步</th><th>关键服务状态</th><th>ws告警存储</th><th>结果</th>
</tr>
</thead>
<tbody>
{''.join(html_rows)}
</tbody>
</table>

<h2>切换性能统计</h2>
<table>
<thead><tr><th>服务名</th><th>切换次数</th><th>切换耗时范围(ms)</th></tr></thead>
<tbody>{perf_rows}</tbody>
</table>

<div class="footer">Generated by HighAvailabilityClusterTester</div>
</div>
</body>
</html>'''

        html_file = os.path.join(self.report_dir, f"ha_cluster_test_report_{self.report_timestamp}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        if not silent:
            self.logger.success(f"HTML报告已保存: {html_file}")


def main():
    """主函数"""
    tester = HighAvailabilityClusterTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()