#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Biz/WS 日志健康检测脚本

功能：
1. 按配置时间间隔（默认5分钟）循环下载 A/B 集群的 daemon、biz、ws 日志
2. 分析 daemon 日志，检测 "data expired for cluster" 且 age > 5000ms 的情况
3. 分析 biz 日志，检测 "健康检查定时任务开始" 时间不连续的情况
4. 检测到异常时立即保存相关日志到 Bug_yes 目录
5. 正常日志保存到 back_no 目录

日志存储结构：
    E:\下载\
    ├── cluster_A\
    │   ├── back_no\        # 无问题日志
    │   └── Bug_yes\        # 异常日志
    └── cluster_B\
        ├── back_no\
        └── Bug_yes\

使用方式：
    1. 修改下方配置区参数
    2. 直接运行: python bizws_log_check.py
"""

import os
import re
import sys
import time
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from iomp_core import IompLogDownloader
from ha_env import iomp_ip_a, iomp_port_a, iomp_ip_b, iomp_port_b


class AnalysisResult:
    """单次检测分析结果"""
    def __init__(self):
        self.check_count: int = 0
        self.check_time: datetime = None
        self.cluster_results: Dict[str, dict] = {}


class BizWsLogChecker:
    """
    Biz/WS 日志健康检测器
    """

    # ==================== 配置区 ====================

    # 1. 日志下载时间间隔（分钟）
    CHECK_INTERVAL_MINUTES: int = 10

    # 2. 最大检测次数（0 表示无限循环）
    MAX_CHECK_COUNT: int = 0

    # 3. 两组 IOMP 平台配置
    CLUSTER_CONFIGS: list[dict] = [
        {
            "name": "集群A",
            "cluster_dir": "cluster_A",
            "base_url": f"http://{iomp_ip_a}:{iomp_port_a}",
            "username": "wuweibin",
            "password": "Kedacom@123",
            "cluster_id": "",
        },
        {
            "name": "集群B",
            "cluster_dir": "cluster_B",
            "base_url": f"http://{iomp_ip_b}:{iomp_port_b}",
            "username": "wuweibin",
            "password": "Kedacom@123",
            "cluster_id": "",
        },
    ]

    # 4. 需要下载的服务白名单
    SERVICE_WHITELIST: list[str] = [
        "la-atc-daemon-server",
        "la-atc-biz-backend",
        "la-atc-ws-backend",
    ]

    # 5. 命名空间
    NAMESPACE: str = "kedacom-project-namespace"

    # 6. 日志输出根目录
    OUTPUT_ROOT: str = r"E:\下载"

    # 7. Daemon 日志异常阈值（毫秒）
    DAEMON_AGE_THRESHOLD_MS: int = 5000

    # 8. Biz 健康检测间隔（秒），用于判断时间连续性
    BIZ_HEALTH_CHECK_INTERVAL: int = 1

    # ==================== 正则表达式 ====================

    # Daemon 日志异常匹配正则
    # 格式: "Business service la-atc-biz-backend data expired for cluster cluster_B (age: 5629ms)"
    DAEMON_EXPIRED_PATTERN = re.compile(
        r"Business\s+service\s+la-atc-biz-backend\s+data\s+expired\s+for\s+cluster\s+(\w+)\s+\(age:\s*(\d+)ms\)"
    )

    # Biz 健康检查开始关键字
    BIZ_HEALTH_START_KEYWORD = "健康检查定时任务开始 当前时间"

    # 支持的时间戳正则
    TIMESTAMP_PATTERNS: list[str] = [
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?Z?)',  # ISO 8601
        r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]',              # [2026-06-03 09:58:15]
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?)',   # 空格分隔
    ]

    TIMESTAMP_FORMATS: list[str] = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ]

    def __init__(self, **kwargs):
        """初始化检测器，支持覆盖默认配置"""
        self.check_interval = kwargs.get("check_interval", self.CHECK_INTERVAL_MINUTES)
        self.max_check_count = kwargs.get("max_check_count", self.MAX_CHECK_COUNT)
        self.cluster_configs = kwargs.get("cluster_configs", self.CLUSTER_CONFIGS)
        self.service_whitelist = kwargs.get("service_whitelist", self.SERVICE_WHITELIST)
        self.namespace = kwargs.get("namespace", self.NAMESPACE)
        self.output_root = kwargs.get("output_root", self.OUTPUT_ROOT)
        self.daemon_age_threshold = kwargs.get("daemon_age_threshold", self.DAEMON_AGE_THRESHOLD_MS)
        self.biz_health_interval = kwargs.get("biz_health_interval", self.BIZ_HEALTH_CHECK_INTERVAL)

        # 运行状态
        self.should_stop = False
        self.check_count = 0
        self.last_check_time: Dict[str, datetime] = {}
        
        # 当前检测结果（用于生成报告）
        self.current_analysis: Optional[AnalysisResult] = None

        # 初始化输出目录
        self._init_output_dirs()

    def _init_output_dirs(self) -> None:
        """初始化输出目录结构"""
        for cluster_config in self.cluster_configs:
            cluster_dir = cluster_config["cluster_dir"]
            os.makedirs(os.path.join(self.output_root, cluster_dir, "back_no"), exist_ok=True)
            os.makedirs(os.path.join(self.output_root, cluster_dir, "Bug_yes"), exist_ok=True)
        print(f"[初始化] 输出目录: {self.output_root}")

    # ==================== 日志下载 ====================

    def _create_downloader(self, cluster_config: dict) -> IompLogDownloader:
        """创建日志下载器"""
        return IompLogDownloader(
            base_url=cluster_config["base_url"],
            username=cluster_config["username"],
            password=cluster_config["password"],
            cluster_id=cluster_config.get("cluster_id", ""),
            output_dir=os.path.join(self.output_root, cluster_config["cluster_dir"]),
            service_names=self.service_whitelist,
        )

    def download_cluster_logs(self, cluster_config: dict) -> Dict[str, str]:
        """
        下载指定集群的日志。
        返回: {服务类型: 日志文件路径}
        """
        print(f"\n[{'='*60}]")
        print(f"[下载日志] {cluster_config['name']}")
        print(f"  地址: {cluster_config['base_url']}")
        print(f"  服务: {self.service_whitelist}")

        downloader = self._create_downloader(cluster_config)
        result: Dict[str, str] = {}

        try:
            for service_name in self.service_whitelist:
                try:
                    path = downloader.download_service_log(
                        service_name=service_name,
                        namespace=self.namespace,
                    )
                    # 根据服务名确定类型
                    if "daemon" in service_name.lower():
                        result["daemon"] = path
                    elif "biz" in service_name.lower():
                        result["biz"] = path
                    elif "ws" in service_name.lower():
                        result["ws"] = path
                    print(f"  [下载成功] {service_name} -> {path}")
                except Exception as e:
                    print(f"  [下载失败] {service_name}: {e}")
                time.sleep(0.5)
        except Exception as e:
            print(f"[下载异常] {cluster_config['name']}: {e}")

        return result

    def download_ws_logs_urgent(self, cluster_config: dict) -> Dict[str, str]:
        """
        紧急下载 WS 日志（用于检测到 biz 时间不连续时）
        """
        print(f"\n[紧急下载WS日志] {cluster_config['name']}")
        downloader = self._create_downloader(cluster_config)
        result: Dict[str, str] = {}

        ws_service = "la-atc-ws-backend"
        try:
            path = downloader.download_service_log(
                service_name=ws_service,
                namespace=self.namespace,
            )
            result["ws"] = path
            print(f"  [下载成功] {ws_service} -> {path}")
        except Exception as e:
            print(f"  [下载失败] {ws_service}: {e}")

        return result

    # ==================== 日志分析 ====================

    def parse_timestamp(self, line: str) -> Optional[datetime]:
        """解析日志行中的时间戳"""
        for pattern in self.TIMESTAMP_PATTERNS:
            match = re.search(pattern, line)
            if match:
                ts_str = match.group(1)
                for fmt in self.TIMESTAMP_FORMATS:
                    try:
                        return datetime.strptime(ts_str, fmt)
                    except ValueError:
                        continue
        return None

    def _read_log_with_timestamps(self, log_path: str) -> List[Tuple[datetime, str]]:
        """读取日志文件，返回带时间戳的行列表"""
        parsed_lines: List[Tuple[datetime, str]] = []
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip("\n")
                    ts = self.parse_timestamp(line)
                    if ts:
                        parsed_lines.append((ts, line))
        except Exception as e:
            print(f"[读取日志失败] {log_path}: {e}")
        return parsed_lines

    def analyze_daemon_log(self, log_path: str) -> Tuple[bool, List[dict], List[dict]]:
        """
        分析 daemon 日志，检测 age > 5000ms 的情况。
        
        返回: (是否异常, 异常记录列表, 所有关键字记录列表)
        异常记录格式: {timestamp, cluster, age_ms, raw_line}
        关键字记录格式: {timestamp, cluster, age_ms, raw_line, is_anomaly}
        """
        anomalies: List[dict] = []
        all_keywords: List[dict] = []
        parsed_lines = self._read_log_with_timestamps(log_path)

        for ts, line in parsed_lines:
            match = self.DAEMON_EXPIRED_PATTERN.search(line)
            if match:
                cluster = match.group(1)
                age_ms = int(match.group(2))
                record = {
                    "timestamp": ts,
                    "cluster": cluster,
                    "age_ms": age_ms,
                    "raw_line": line,
                    "is_anomaly": age_ms > self.daemon_age_threshold
                }
                all_keywords.append(record)
                if record["is_anomaly"]:
                    anomalies.append(record)

        is_anomaly = len(anomalies) > 0
        return is_anomaly, anomalies, all_keywords

    def analyze_biz_log(self, log_path: str) -> Tuple[bool, List[dict], List[datetime], List[dict]]:
        """
        分析 biz 日志，检测"健康检查定时任务开始"时间不连续的情况。
        
        返回: (是否异常, 异常记录列表, 健康检测时间列表, 所有检测点记录)
        异常记录格式: {timestamp, expected_time, actual_time, gap_seconds}
        检测点记录: {timestamp, gap_from_prev, is_anomaly}
        """
        parsed_lines = self._read_log_with_timestamps(log_path)
        anomalies: List[dict] = []
        health_check_times: List[datetime] = []
        all_check_points: List[dict] = []

        # 收集所有健康检查时间点
        for ts, line in parsed_lines:
            if self.BIZ_HEALTH_START_KEYWORD in line:
                health_check_times.append(ts)

        # 时间去重并排序
        health_check_times = sorted(list(set(health_check_times)))

        # 检测时间不连续
        for i in range(len(health_check_times)):
            curr_time = health_check_times[i]
            gap_seconds = 0.0
            
            if i > 0:
                prev_time = health_check_times[i - 1]
                gap_seconds = (curr_time - prev_time).total_seconds()

            # 如果间隔不是默认的 1 秒左右，认为不连续（允许±0.5秒误差）
            expected_gap = self.biz_health_interval
            is_gap_anomaly = i > 0 and abs(gap_seconds - expected_gap) > 0.5
            
            check_point = {
                "timestamp": curr_time,
                "gap_from_prev": gap_seconds,
                "is_anomaly": is_gap_anomaly
            }
            all_check_points.append(check_point)
            
            if is_gap_anomaly:
                anomalies.append({
                    "timestamp": curr_time,
                    "expected_time": health_check_times[i-1] + timedelta(seconds=expected_gap),
                    "actual_time": curr_time,
                    "gap_seconds": gap_seconds,
                })

        is_anomaly = len(anomalies) > 0
        return is_anomaly, anomalies, health_check_times, all_check_points

    # ==================== 日志归档 ====================

    def archive_logs(
        self,
        cluster_config: dict,
        log_paths: Dict[str, str],
        is_bug: bool,
        bug_summary: Optional[str] = None,
    ) -> None:
        """
        将日志归档到 back_no 或 Bug_yes 目录
        
        Args:
            cluster_config: 集群配置
            log_paths: {服务类型: 日志文件路径}
            is_bug: 是否为异常日志
            bug_summary: 异常摘要信息
        """
        target_dir = "Bug_yes" if is_bug else "back_no"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_base = os.path.join(
            self.output_root, 
            cluster_config["cluster_dir"], 
            target_dir,
            f"check_{timestamp}"
        )

        os.makedirs(archive_base, exist_ok=True)

        for service_type, log_path in log_paths.items():
            if os.path.exists(log_path):
                dst_path = os.path.join(archive_base, f"{service_type}.log")
                shutil.copy2(log_path, dst_path)
                print(f"  [归档] {service_type} -> {dst_path}")

        # 如果是异常日志，写入摘要文件
        if is_bug and bug_summary:
            summary_path = os.path.join(archive_base, "bug_summary.txt")
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(bug_summary)
            print(f"  [摘要] -> {summary_path}")

    def generate_report(self, check_count: int) -> str:
        """
        生成日志分析报告文件。
        文件名: bizws_bug_check_log年月日时分秒.txt
        保存位置: OUTPUT_ROOT 目录
            
        返回: 报告文件路径
        """
        if self.current_analysis is None:
            return ""
            
        now = datetime.now()
        timestamp_str = now.strftime("%Y%m%d%H%M%S")
        report_filename = f"bizws_bug_check_log{timestamp_str}.txt"
        report_path = os.path.join(self.output_root, report_filename)
            
        lines = []
        lines.append("=" * 70)
        lines.append(f"#### 第 {check_count} 次日志下载分析 {now.strftime('%Y-%m-%d %H:%M:%S')} ####")
        lines.append("=" * 70)
        lines.append("")
            
        # 遍历每个集群的分析结果
        for cluster_name, result in self.current_analysis.cluster_results.items():
            lines.append(f"{'=' * 70}")
            lines.append(f"【{cluster_name}】")
            lines.append(f"{'=' * 70}")
                
            # Daemon 日志分析结果
            daemon_data = result.get("daemon", {})
            daemon_keywords = daemon_data.get("keywords", [])
            daemon_anomalies = daemon_data.get("anomalies", [])
                
            lines.append("")
            lines.append("--- Daemon 日志分析 ---")
            if daemon_keywords:
                lines.append(f"  关键字采集总数: {len(daemon_keywords)} 条")
                lines.append(f"  是否存在异常 (> {self.daemon_age_threshold}ms): {'是' if daemon_anomalies else '否'}")
                lines.append("")
                lines.append("  所有采集到的关键字信息:")
                for kw in daemon_keywords:
                    status = "[异常]" if kw.get("is_anomaly") else "[正常]"
                    lines.append(f"    {status} {self._fmt_ts(kw['timestamp'])} cluster={kw['cluster']} age={kw['age_ms']}ms")
                    
                if daemon_anomalies:
                    lines.append("")
                    lines.append(f"  >>> 异常详情 (age > {self.daemon_age_threshold}ms):")
                    for anomaly in daemon_anomalies:
                        lines.append(f"    时间: {self._fmt_ts(anomaly['timestamp'])}")
                        lines.append(f"    cluster: {anomaly['cluster']}")
                        lines.append(f"    age: {anomaly['age_ms']}ms")
                        lines.append(f"    日志: {anomaly['raw_line']}")
            else:
                lines.append("  无关键字采集记录")
                
            # Biz 日志分析结果
            biz_data = result.get("biz", {})
            biz_check_points = biz_data.get("check_points", [])
            biz_anomalies = biz_data.get("anomalies", [])
                
            lines.append("")
            lines.append("--- Biz 健康检查分析 ---")
            if biz_check_points:
                lines.append(f"  健康检测时间点总数: {len(biz_check_points)} 个")
                lines.append(f"  是否存在时间不连续 (> {self.biz_health_interval}秒): {'是' if biz_anomalies else '否'}")
                    
                # 统计信息
                gap_values = [cp["gap_from_prev"] for cp in biz_check_points if cp["gap_from_prev"] > 0]
                if gap_values:
                    max_gap = max(gap_values)
                    min_gap = min(gap_values)
                    avg_gap = sum(gap_values) / len(gap_values)
                    lines.append(f"  间隔统计: 最大={max_gap:.2f}s, 最小={min_gap:.2f}s, 平均={avg_gap:.2f}s")
                    
                if biz_anomalies:
                    lines.append("")
                    lines.append("  >>> 时间不连续详情 (> 1秒):")
                    for anomaly in biz_anomalies:
                        lines.append(f"    时间点: {self._fmt_ts(anomaly['timestamp'])}")
                        lines.append(f"    期望时间: {self._fmt_ts(anomaly['expected_time'])}")
                        lines.append(f"    实际时间: {self._fmt_ts( anomaly['actual_time'])}")
                        lines.append(f"    间隔: {anomaly['gap_seconds']:.2f}s")
                        lines.append("")
                else:
                    lines.append("")
                    lines.append("  所有检测点时间（最近20个）:")
                    recent_points = biz_check_points[-20:]
                    for cp in recent_points:
                        status = "[异常]" if cp.get("is_anomaly") else "[正常]"
                        gap_str = f"{cp['gap_from_prev']:.2f}s" if cp['gap_from_prev'] > 0 else "-"
                        lines.append(f"    {status} {self._fmt_ts(cp['timestamp'])} 间隔:{gap_str}")
            else:
                lines.append("  无健康检测时间点记录")
                
            lines.append("")
            
        # 汇总信息
        lines.append("=" * 70)
        lines.append("【汇总】")
        lines.append("=" * 70)
            
        has_any_anomaly = False
        for cluster_name, result in self.current_analysis.cluster_results.items():
            daemon_anomalies = result.get("daemon", {}).get("anomalies", [])
            biz_anomalies = result.get("biz", {}).get("anomalies", [])
                
            if daemon_anomalies or biz_anomalies:
                has_any_anomaly = True
                lines.append(f"")
                lines.append(f"{cluster_name}:")
                if daemon_anomalies:
                    lines.append(f"  - Daemon异常: {len(daemon_anomalies)} 条 (> {self.daemon_age_threshold}ms)")
                if biz_anomalies:
                    lines.append(f"  - Biz健康检查异常: {len(biz_anomalies)} 处时间不连续")
            
        if not has_any_anomaly:
            lines.append("")
            lines.append("  所有集群检测正常，未发现异常")
            
        lines.append("")
        lines.append("=" * 70)
        lines.append(f"报告生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)
            
        # 写入文件
        report_content = "\n".join(lines)
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            # 终端显示报告路径
            print(f"\n{'='*60}")
            print(f"[报告已写入] {report_path}")
            print(f"{'='*60}")
            # 打印报告内容
            print("\n" + report_content)
        except Exception as e:
            print(f"[报告生成失败] {e}")
            
        return report_path
    
    def save_immediate_report(self, check_count: int) -> str:
        """
        立即保存当前检测结果的报告（不打印内容，只写入文件）。
        每次检测完成后调用，确保报告及时保存。
        """
        if self.current_analysis is None:
            return ""
            
        now = datetime.now()
        # 固定文件名，每次追加写入
        report_filename = "bizws_bug_check_log.txt"
        report_path = os.path.join(self.output_root, report_filename)
            
        lines = []
        lines.append("=" * 70)
        lines.append(f"#### 第 {check_count} 次日志下载分析 {now.strftime('%Y-%m-%d %H:%M:%S')} ####")
        lines.append("=" * 70)
        lines.append("")
            
        for cluster_name, result in self.current_analysis.cluster_results.items():
            lines.append(f"{'=' * 70}")
            lines.append(f"【{cluster_name}】")
            lines.append(f"{'=' * 70}")
                
            # Daemon 日志分析结果
            daemon_data = result.get("daemon", {})
            daemon_keywords = daemon_data.get("keywords", [])
            daemon_anomalies = daemon_data.get("anomalies", [])
                
            lines.append("")
            lines.append("--- Daemon 日志分析 ---")
            if daemon_keywords:
                lines.append(f"  关键字采集总数: {len(daemon_keywords)} 条")
                lines.append(f"  是否存在异常 (> {self.daemon_age_threshold}ms): {'是' if daemon_anomalies else '否'}")
                lines.append("")
                lines.append("  所有采集到的关键字信息:")
                for kw in daemon_keywords:
                    status = "[异常]" if kw.get("is_anomaly") else "[正常]"
                    lines.append(f"    {status} {self._fmt_ts(kw['timestamp'])} cluster={kw['cluster']} age={kw['age_ms']}ms")
                    
                if daemon_anomalies:
                    lines.append("")
                    lines.append(f"  >>> 异常详情 (age > {self.daemon_age_threshold}ms):")
                    for anomaly in daemon_anomalies:
                        lines.append(f"    时间: {self._fmt_ts(anomaly['timestamp'])}")
                        lines.append(f"    cluster: {anomaly['cluster']}")
                        lines.append(f"    age: {anomaly['age_ms']}ms")
                        lines.append(f"    日志: {anomaly['raw_line']}")
            else:
                lines.append("  无关键字采集记录")
                
            # Biz 日志分析结果
            biz_data = result.get("biz", {})
            biz_check_points = biz_data.get("check_points", [])
            biz_anomalies = biz_data.get("anomalies", [])
                
            lines.append("")
            lines.append("--- Biz 健康检查分析 ---")
            if biz_check_points:
                lines.append(f"  健康检测时间点总数: {len(biz_check_points)} 个")
                lines.append(f"  是否存在时间不连续 (> {self.biz_health_interval}秒): {'是' if biz_anomalies else '否'}")
                    
                gap_values = [cp["gap_from_prev"] for cp in biz_check_points if cp["gap_from_prev"] > 0]
                if gap_values:
                    max_gap = max(gap_values)
                    min_gap = min(gap_values)
                    avg_gap = sum(gap_values) / len(gap_values)
                    lines.append(f"  间隔统计: 最大={max_gap:.2f}s, 最小={min_gap:.2f}s, 平均={avg_gap:.2f}s")
                    
                if biz_anomalies:
                    lines.append("")
                    lines.append("  >>> 时间不连续详情 (> 1秒):")
                    for anomaly in biz_anomalies:
                        lines.append(f"    时间点: {self._fmt_ts(anomaly['timestamp'])}")
                        lines.append(f"    期望时间: {self._fmt_ts(anomaly['expected_time'])}")
                        lines.append(f"    实际时间: {self._fmt_ts(anomaly['actual_time'])}")
                        lines.append(f"    间隔: {anomaly['gap_seconds']:.2f}s")
                        lines.append("")
                else:
                    lines.append("")
                    lines.append("  所有检测点时间（最近20个）:")
                    recent_points = biz_check_points[-20:]
                    for cp in recent_points:
                        status = "[异常]" if cp.get("is_anomaly") else "[正常]"
                        gap_str = f"{cp['gap_from_prev']:.2f}s" if cp['gap_from_prev'] > 0 else "-"
                        lines.append(f"    {status} {self._fmt_ts(cp['timestamp'])} 间隔:{gap_str}")
            else:
                lines.append("  无健康检测时间点记录")
                
            lines.append("")
            
        # 汇总
        lines.append("=" * 70)
        lines.append("【汇总】")
        lines.append("=" * 70)
            
        has_any_anomaly = False
        for cluster_name, result in self.current_analysis.cluster_results.items():
            daemon_anomalies = result.get("daemon", {}).get("anomalies", [])
            biz_anomalies = result.get("biz", {}).get("anomalies", [])
                
            if daemon_anomalies or biz_anomalies:
                has_any_anomaly = True
                lines.append(f"")
                lines.append(f"{cluster_name}:")
                if daemon_anomalies:
                    lines.append(f"  - Daemon异常: {len(daemon_anomalies)} 条 (> {self.daemon_age_threshold}ms)")
                if biz_anomalies:
                    lines.append(f"  - Biz健康检查异常: {len(biz_anomalies)} 处时间不连续")
            
        if not has_any_anomaly:
            lines.append("")
            lines.append("  所有集群检测正常，未发现异常")
            
        lines.append("")
        lines.append("=" * 70)
        lines.append(f"报告生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 70)
        lines.append("")
            
        report_content = "\n".join(lines)
        try:
            # 以追加模式写入文件（每次追加到同一个日志文件）
            with open(report_path, "a", encoding="utf-8") as f:
                f.write(report_content)
            print(f"\n[报告已追加写入] {report_path}")
        except Exception as e:
            print(f"[报告写入失败] {e}")
            
        return report_path

    # ==================== 主检测流程 ====================

    def check_single_cluster(self, cluster_config: dict) -> Tuple[bool, str, dict]:
        """
        检测单个集群的日志。
        
        返回: (是否停止循环, 异常摘要, 详细分析结果)
        """
        print(f"\n{'='*60}")
        print(f"[开始检测] {cluster_config['name']}")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        # 1. 下载日志
        log_paths = self.download_cluster_logs(cluster_config)

        # 2. 分析 daemon 日志
        daemon_anomaly = False
        daemon_summary = ""
        daemon_anomalies: List[dict] = []
        daemon_keywords: List[dict] = []
        
        if "daemon" in log_paths and os.path.exists(log_paths["daemon"]):
            daemon_anomaly, daemon_anomalies, daemon_keywords = self.analyze_daemon_log(log_paths["daemon"])
            if daemon_anomaly:
                print(f"\n[警告] Daemon 日志检测到 age > {self.daemon_age_threshold}ms 的异常!")
                for anomaly in daemon_anomalies:
                    print(f"  [{self._fmt_ts(anomaly['timestamp'])}] cluster={anomaly['cluster']}, age={anomaly['age_ms']}ms")
                daemon_summary = f"Daemon 异常检测:\n"
                for anomaly in daemon_anomalies:
                    daemon_summary += f"  时间: {self._fmt_ts(anomaly['timestamp'])}, cluster={anomaly['cluster']}, age={anomaly['age_ms']}ms\n"
                    daemon_summary += f"  日志: {anomaly['raw_line']}\n"
            else:
                print(f"[Daemon] 关键字采集: {len(daemon_keywords)} 条，无异常")

        # 3. 分析 biz 日志
        biz_anomaly = False
        biz_summary = ""
        biz_anomalies: List[dict] = []
        biz_health_times: List[datetime] = []
        biz_check_points: List[dict] = []
        
        if "biz" in log_paths and os.path.exists(log_paths["biz"]):
            biz_anomaly, biz_anomalies, biz_health_times, biz_check_points = self.analyze_biz_log(log_paths["biz"])
            if biz_anomaly:
                print(f"\n[警告] Biz 日志检测到健康检查时间不连续!")
                for anomaly in biz_anomalies:
                    print(f"  [{self._fmt_ts(anomaly['timestamp'])}] 期望: {self._fmt_ts(anomaly['expected_time'])}, 实际: {self._fmt_ts(anomaly['actual_time'])}, 间隔: {anomaly['gap_seconds']:.1f}s")
                biz_summary = f"Biz 健康检查异常:\n"
                biz_summary += f"  健康检测时间点: {len(biz_health_times)} 个\n"
                for anomaly in biz_anomalies:
                    biz_summary += f"  时间: {self._fmt_ts(anomaly['timestamp'])}, 期望: {self._fmt_ts(anomaly['expected_time'])}, 实际: {self._fmt_ts(anomaly['actual_time'])}, 间隔: {anomaly['gap_seconds']:.1f}s\n"
            else:
                print(f"[Biz] 健康检测时间点: {len(biz_health_times)} 个，无时间不连续")

        # 4. 根据检测结果处理
        should_stop = False
        combined_summary = ""

        if daemon_anomaly:
            # Daemon 检测到 > 5000ms，停止循环
            should_stop = True
            combined_summary = f"[Daemon 异常 - 停止检测]\n{daemon_summary}"
            print(f"\n[触发条件] Daemon 异常 age > {self.daemon_age_threshold}ms，停止检测循环")
            
            # 归档到 Bug_yes
            self.archive_logs(cluster_config, log_paths, is_bug=True, bug_summary=combined_summary)

        elif biz_anomaly:
            # Biz 检测到时间不连续，立即下载 WS 日志
            combined_summary = f"[Biz 健康检查异常]\n{biz_summary}"
            print(f"\n[触发条件] Biz 健康检查时间不连续，紧急下载 WS 日志")
            
            # 紧急下载 WS 日志
            ws_paths = self.download_ws_logs_urgent(cluster_config)
            log_paths["ws"] = ws_paths.get("ws", log_paths.get("ws"))
            
            # 归档到 Bug_yes
            self.archive_logs(cluster_config, log_paths, is_bug=True, bug_summary=combined_summary)

        else:
            # 正常，归档到 back_no
            print(f"\n[正常] 未检测到异常")
            self.archive_logs(cluster_config, log_paths, is_bug=False)

        # 保存详细分析结果用于生成报告
        cluster_result = {
            "daemon": {
                "keywords": daemon_keywords,
                "anomalies": daemon_anomalies,
            },
            "biz": {
                "check_points": biz_check_points,
                "anomalies": biz_anomalies,
                "health_times_count": len(biz_health_times),
            }
        }

        return should_stop, combined_summary, cluster_result

    def run(self) -> None:
        """
        执行主检测流程
        """
        print(f"\n{'#'*60}")
        print(f"# Biz/WS 日志健康检测启动")
        print(f"# 检测间隔: {self.check_interval} 分钟")
        print(f"# 最大检测次数: {'无限' if self.max_check_count == 0 else self.max_check_count}")
        print(f"# 集群: {[c['name'] for c in self.cluster_configs]}")
        print(f"# Daemon age 阈值: > {self.daemon_age_threshold}ms 触发停止")
        print(f"# 输出目录: {self.output_root}")
        print(f"# 报告文件: {self.output_root}\bizws_bug_check_log.txt (追加模式)")
        print(f"{'#'*60}")

        while not self.should_stop:
            self.check_count += 1
            print(f"\n>>> 第 {self.check_count} 次检测 <<<")
            
            # 初始化当前检测结果
            self.current_analysis = AnalysisResult()
            self.current_analysis.check_count = self.check_count
            self.current_analysis.check_time = datetime.now()

            # 检测每个集群
            any_daemon_anomaly = False
            all_summaries = []

            for cluster_config in self.cluster_configs:
                should_stop, summary, cluster_result = self.check_single_cluster(cluster_config)
                self.current_analysis.cluster_results[cluster_config["name"]] = cluster_result
                
                if summary:
                    all_summaries.append(f"{cluster_config['name']}:\n{summary}")
                if should_stop:
                    any_daemon_anomaly = True
                    break

            # 【立即保存报告】每次检测完成后立即写入文件
            print(f"\n[保存报告] 第 {self.check_count} 次检测报告...")
            report_path = self.save_immediate_report(self.check_count)
            print(f"[报告已保存] {report_path}")

            # 如果任何集群检测到 daemon > 5000ms，停止循环
            if any_daemon_anomaly:
                print(f"\n{'='*60}")
                print(f"[检测完成] 检测到 Daemon 异常 age > {self.daemon_age_threshold}ms，停止循环")
                print(f"{'='*60}")
                break

            # 检查最大检测次数
            if self.max_check_count > 0 and self.check_count >= self.max_check_count:
                print(f"\n{'='*60}")
                print(f"[检测完成] 达到最大检测次数 {self.max_check_count}")
                print(f"{'='*60}")
                break

            # 等待下次检测
            print(f"\n[等待] {self.check_interval} 分钟后进行下一次检测...")
            print(f"  按 Ctrl+C 可提前停止")
            try:
                time.sleep(self.check_interval * 60)
            except KeyboardInterrupt:
                print(f"\n[用户中断] 停止检测")
                break

        # 打印最终汇总
        print(f"\n\n{'='*60}")
        print(f"[汇总报告]")
        print(f"  总检测次数: {self.check_count}")
        print(f"  输出目录: {self.output_root}")
        print(f"  报告文件: {self.output_root}\bizws_bug_check_log.txt")
        print(f"{'='*60}")

    @staticmethod
    def _fmt_ts(dt: datetime) -> str:
        """格式化时间戳"""
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def main():
    """命令行入口"""
    # 可通过参数调整配置
    checker = BizWsLogChecker(
        check_interval=5,       # 检测间隔 5 分钟
        max_check_count=0,      # 0 表示无限循环
        daemon_age_threshold=5000,
    )
    checker.run()


if __name__ == "__main__":
    main()
