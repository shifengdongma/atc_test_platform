#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HA 双集群日志分析脚本

功能：
1. 分别登录两个 IOMP 平台下载白名单服务的日志
2. 分析日志最后时间向前推 N 分钟（默认10分钟）内的日志
3. 根据关键字字典检索日志内容，对比两个集群中相同关键字的时间戳并计算差值
4. 【新增】分析 daemon 日志中的集群切换事件（Delete pod, old master）
5. 【新增】分析 ws-backend 日志中的主备集群告警保存状态

使用方式：
    1. 修改下方配置区的参数
    2. 直接运行: python ha_log_download_analysis.py
    3. 或被其他脚本导入调用:
       from ha_log_download_analysis import HaLogAnalyzer
       analyzer = HaLogAnalyzer()
       analyzer.run()
"""

import os
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from iomp_core import IompLogDownloader
from ha_env import iomp_ip_a, iomp_port_a, iomp_ip_b, iomp_port_b


class HaLogAnalyzer:
    """
    HA 双集群日志分析器
    """

    # ==================== 配置区（用户按需修改） ====================

    # 1. 服务白名单：只下载这些服务的日志
    SERVICE_WHITELIST: list[str] = [
        "la-atc-ws-backend",
        "la-atc-daemon-server",
        #"la-atc-biz-backend",
        # 按需添加更多服务...
    ]

    # 2. 两组 IOMP 平台配置
    CLUSTER_CONFIGS: list[dict] = [
        {
            "name": "集群A",
            "base_url": f"http://{iomp_ip_a}:{iomp_port_a}",
            "username": "wuweibin",
            "password": "Kedacom@123",
            "cluster_id": "",  # 空字符串表示自动获取
        },
        {
            "name": "集群B",
            "base_url": f"http://{iomp_ip_b}:{iomp_port_b}",
            "username": "wuweibin",
            "password": "Kedacom@123",
            "cluster_id": "",  # 空字符串表示自动获取
        },
    ]

    # 3. 日志分析时间窗口（分钟），默认10分钟
    ANALYSIS_MINUTES: int = 10

    # 4. 检索关键字字典列表 {key: value}
    # key: 用于输出标识的简短名称
    # value: 日志中实际要搜索的关键字/关键短语
    KEYWORD_DICT: dict[str, str] = {
        "主集群存储告警": "是主集群，保存告警 :",
        "备集群不存储告警": "不是主集群，不保存告警",
        "主备切换": " Delete pod, old master:",
        # 按需添加更多关键字...
    }

    # 5. 命名空间
    NAMESPACE: str = "kedacom-project-namespace"

    # 6. 日志下载开关：True=下载全部日志，False=分析本地最新日志
    DOWNLOAD_LOGS: bool = True

    # 7. 日志下载输出目录前缀（相对路径，会在实例化时转换为绝对路径）
    OUTPUT_DIR_PREFIX: str = "..\..\..\tmp\log"

    # ==================== 时间戳解析配置 ====================

    # 支持的时间戳正则表达式列表（按优先级匹配）
    TIMESTAMP_PATTERNS: list[str] = [
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?Z?)',  # ISO 8601
        r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]',            # [2026-06-03 09:58:15]
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?)',  # 空格分隔
    ]

    # 时间戳解析格式（按优先级尝试）
    TIMESTAMP_FORMATS: list[str] = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ]

    def __init__(
        self,
        service_whitelist: Optional[list[str]] = None,
        cluster_configs: Optional[list[dict]] = None,
        analysis_minutes: Optional[int] = None,
        keyword_dict: Optional[dict[str, str]] = None,
        namespace: Optional[str] = None,
        output_dir_prefix: Optional[str] = None,
        download_logs: Optional[bool] = None,
    ):
        """
        初始化分析器。所有参数均可覆盖类默认值。
        """
        self.service_whitelist = service_whitelist or self.SERVICE_WHITELIST
        self.cluster_configs = cluster_configs or self.CLUSTER_CONFIGS
        self.analysis_minutes = analysis_minutes or self.ANALYSIS_MINUTES
        self.keyword_dict = keyword_dict or self.KEYWORD_DICT
        self.namespace = namespace or self.NAMESPACE
        self.output_dir_prefix = output_dir_prefix or self.OUTPUT_DIR_PREFIX
        # 如果是相对路径，基于脚本所在目录转换为绝对路径
        if not os.path.isabs(self.output_dir_prefix):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.output_dir_prefix = os.path.normpath(os.path.join(script_dir, self.output_dir_prefix))
        self.download_logs = download_logs if download_logs is not None else self.DOWNLOAD_LOGS

    # ==================== 日志下载 ====================

    def _create_downloader(self, cluster_config: dict) -> IompLogDownloader:
        """根据集群配置创建 IompLogDownloader 实例"""
        output_dir = os.path.join(self.output_dir_prefix, cluster_config["name"])
        return IompLogDownloader(
            base_url=cluster_config["base_url"],
            username=cluster_config["username"],
            password=cluster_config["password"],
            cluster_id=cluster_config.get("cluster_id", ""),
            output_dir=output_dir,
            service_names=self.service_whitelist,
        )

    def _backup_existing_logs(self, cluster_config: dict) -> None:
        """
        下载前将集群输出目录下的现有日志备份到 back 子目录。
        若文件名冲突则自动重命名为 原文件名-log-N.txt。
        """
        log_dir = os.path.join(self.output_dir_prefix, cluster_config["name"])
        if not os.path.exists(log_dir):
            return

        back_dir = os.path.join(log_dir, "back")
        os.makedirs(back_dir, exist_ok=True)

        for root, _, files in os.walk(log_dir):
            # 跳过 back 目录本身，避免重复备份
            if os.path.commonpath([root, back_dir]) == back_dir:
                continue
            for f in files:
                if f.endswith(".log") or "log" in f.lower():
                    src = os.path.join(root, f)
                    # 保持相对目录结构或在 back 目录下扁平化存放
                    # 为简化，直接以原文件名放入 back，冲突时重命名
                    dst_name = f
                    name, ext = os.path.splitext(dst_name)
                    dst = os.path.join(back_dir, dst_name)
                    counter = 1
                    while os.path.exists(dst):
                        dst_name = f"{name}-log-{counter}{ext}"
                        dst = os.path.join(back_dir, dst_name)
                        counter += 1
                    try:
                        os.rename(src, dst)
                        print(f"  [备份日志] {f} -> back/{dst_name}")
                    except Exception as e:
                        print(f"  [备份失败] {f}: {e}")

    def download_cluster_logs(self, cluster_config: dict) -> List[str]:
        """
        下载指定集群白名单服务的日志。
        返回下载成功的日志文件绝对路径列表。
        """
        print(f"\n[{'='*40}]")
        print(f"[开始下载日志] {cluster_config['name']}")
        print(f"  地址: {cluster_config['base_url']}")
        print(f"  白名单: {self.service_whitelist}")
        print(f"  namespace: {self.namespace}")

        # 下载前备份已有日志
        self._backup_existing_logs(cluster_config)

        downloader = self._create_downloader(cluster_config)
        try:
            paths = downloader.download_all_logs(namespace=self.namespace)
            print(f"[下载完成] {cluster_config['name']} 共 {len(paths)} 个文件")
            return paths
        except Exception as e:
            print(f"[下载异常] {cluster_config['name']}: {e}")
            return []

    def get_local_logs(self, cluster_config: dict) -> List[str]:
        """
        获取本地已有的日志文件（不下载）。
        返回日志目录中所有日志文件的绝对路径列表。
        """
        log_dir = os.path.join(self.output_dir_prefix, cluster_config["name"])
        if not os.path.exists(log_dir):
            print(f"[本地日志目录不存在] {log_dir}")
            return []

        log_files: List[str] = []
        for root, _, files in os.walk(log_dir):
            for f in files:
                # 匹配 .log 结尾或包含日志关键字的文件
                if f.endswith(".log") or "log" in f.lower():
                    log_files.append(os.path.join(root, f))

        print(f"[本地日志] {cluster_config['name']} 共 {len(log_files)} 个文件")
        return log_files

    # ==================== 日志解析（通用） ====================

    def parse_timestamp(self, line: str) -> Optional[datetime]:
        """
        从单行日志中解析时间戳。
        支持多种常见格式，解析失败返回 None。
        """
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

    def _read_log_lines(self, log_path: str) -> List[Tuple[datetime, str]]:
        """读取日志文件，返回 [(timestamp, line), ...]"""
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

    def analyze_single_log(self, log_path: str) -> Dict[str, List[datetime]]:
        """
        分析单个日志文件。
        返回: {keyword_key: [timestamp1, timestamp2, ...]}
        只保留日志最后时间向前推 analysis_minutes 分钟内的匹配行。
        """
        results: Dict[str, List[datetime]] = {}
        parsed_lines = self._read_log_lines(log_path)

        if not parsed_lines:
            return results

        last_ts = max(ts for ts, _ in parsed_lines)
        cutoff_ts = last_ts - timedelta(minutes=self.analysis_minutes)

        for ts, line in parsed_lines:
            if ts < cutoff_ts:
                continue
            for key, value in self.keyword_dict.items():
                if value in line:
                    results.setdefault(key, []).append(ts)

        return results

    def _analyze_cluster_logs(self, log_paths: List[str]) -> Tuple[Dict[str, List[datetime]], Optional[datetime], Optional[datetime]]:
        """分析集群所有日志的通用关键字，返回 (结果字典, 起始时间, 结束时间)"""
        merged: Dict[str, List[datetime]] = {}
        all_timestamps: List[datetime] = []

        for path in log_paths:
            single_result = self.analyze_single_log(path)
            for key, ts_list in single_result.items():
                merged.setdefault(key, []).extend(ts_list)
                all_timestamps.extend(ts_list)

        for key in merged:
            merged[key] = sorted(list(set(merged[key])))

        # 计算时间范围
        start_ts = None
        end_ts = None
        if all_timestamps:
            end_ts = max(all_timestamps)
            start_ts = end_ts - timedelta(minutes=self.analysis_minutes)

        return merged, start_ts, end_ts

    def analyze_cluster(self, cluster_config: dict) -> Dict[str, List[datetime]]:
        """
        分析整个集群的所有白名单服务日志。
        返回合并后的 {keyword_key: [timestamp, ...]}（已按时间排序）。
        """
        log_paths = self.download_cluster_logs(cluster_config)
        merged = self._analyze_cluster_logs(log_paths)

        print(f"[分析完成] {cluster_config['name']} 关键字命中统计: ")
        for key, ts_list in sorted(merged.items()):
            print(f"  - {key}: {len(ts_list)} 次")

        return merged

    # ==================== 双集群对比（通用关键字） ====================

    def _select_failover_event(
        self,
        failover_events: List[dict],
        cluster_a_name: str,
        cluster_b_name: str,
        results_a: Dict[str, List[datetime]],
        results_b: Dict[str, List[datetime]],
    ) -> Optional[dict]:
        """
        从多条切换事件中选择最匹配的一条。
        匹配规则：切换后，新主集群应有"主集群存储告警"记录。
        """
        if not failover_events:
            return None
        if len(failover_events) == 1:
            return failover_events[0]

        best_event = None
        best_score = -999

        for evt in failover_events:
            switch_time = evt["timestamp"]
            new_master = evt["new_master"]

            # 切换后各集群的主集群存储告警数量
            a_after = sum(1 for ts in results_a.get("主集群存储告警", []) if ts > switch_time)
            b_after = sum(1 for ts in results_b.get("主集群存储告警", []) if ts > switch_time)

            # 判断 new_master 对应哪个集群
            a_is_new = (new_master.lower() in cluster_a_name.lower()) or (cluster_a_name.lower() in new_master.lower())
            b_is_new = (new_master.lower() in cluster_b_name.lower()) or (cluster_b_name.lower() in new_master.lower())

            score = 0
            if a_is_new and a_after > 0:
                score += 10
            if b_is_new and b_after > 0:
                score += 10
            if a_is_new and a_after == 0:
                score -= 5
            if b_is_new and b_after == 0:
                score -= 5

            if score > best_score:
                best_score = score
                best_event = evt

        return best_event if best_event else failover_events[-1]

    def _print_comparison(
        self,
        results_a: Dict[str, List[datetime]],
        results_b: Dict[str, List[datetime]],
        cluster_a: dict,
        cluster_b: dict,
        failover_events: Optional[List[dict]] = None,
    ) -> None:
        """
        打印双集群关键字出现次数和正确性。
        判断逻辑：
        - 主备切换: A集群有切换记录且B集群在同一时间段内没有=正确
        - 主集群存储告警: 切换前原主集群有记录=正确，切换后新主集群有记录=正确
        - 备集群不存储告警: 切换前原备集群无记录=正确，切换后新备集群无记录=正确
        """
        print(f"\n[{'='*80}]")
        print(f"{'关键字':<20} {cluster_a['name']:<12} {cluster_b['name']:<12} {'是否正确'}")
        print(f"{'-'*70}")

        all_keys = set(results_a.keys()) | set(results_b.keys())

        # 判断集群A/B对应哪个主备角色
        cluster_a_name = cluster_a["name"]
        cluster_b_name = cluster_b["name"]

        # 选择最匹配的切换事件（基于切换后告警记录匹配度）
        selected_event = None
        switch_time = None
        old_master = None
        new_master = None
        if failover_events:
            selected_event = self._select_failover_event(
                failover_events, cluster_a_name, cluster_b_name, results_a, results_b
            )
            if selected_event:
                switch_time = selected_event["timestamp"]
                old_master = selected_event["old_master"]
                new_master = selected_event["new_master"]
                print(f"[切换事件选择] 选中: {old_master}→{new_master} @ {self._fmt_ts(switch_time)}")

        for key in sorted(all_keys):
            ts_a_list = results_a.get(key, [])
            ts_b_list = results_b.get(key, [])

            count_a = len(ts_a_list)
            count_b = len(ts_b_list)

            # 判断正确性
            if key == "主备切换":
                # 判断标准：A集群有切换记录，B集群在相同时间段内没有=正确
                if switch_time and selected_event:
                    switch_start = switch_time - timedelta(seconds=3)
                    switch_end = switch_time + timedelta(seconds=3)
                    count_a_in_window = sum(1 for ts in ts_a_list if switch_start <= ts <= switch_end)
                    count_b_in_window = sum(1 for ts in ts_b_list if switch_start <= ts <= switch_end)
                    if count_a_in_window > 0 and count_b_in_window == 0:
                        correct = "正确"
                    else:
                        correct = "错误"
                else:
                    # 无切换事件，A集群有记录即可
                    if count_a > 0 and count_b == 0:
                        correct = "正确"
                    else:
                        correct = "错误"

            elif key == "主集群存储告警":
                # 切换前：原主集群有记录=正确
                # 切换后：新主集群有记录=正确
                if switch_time and old_master and new_master:
                    # 判断切换前哪个集群是主集群
                    # old_master 可能是 "cluster_A" 或 "集群A" 等格式
                    a_is_old_master = (old_master.lower() in cluster_a_name.lower()) or (cluster_a_name.lower() in old_master.lower())
                    b_is_old_master = (old_master.lower() in cluster_b_name.lower()) or (cluster_b_name.lower() in old_master.lower())

                    # 判断切换后哪个集群是主集群
                    a_is_new_master = (new_master.lower() in cluster_a_name.lower()) or (cluster_a_name.lower() in new_master.lower())
                    b_is_new_master = (new_master.lower() in cluster_b_name.lower()) or (cluster_b_name.lower() in new_master.lower())

                    # 切换前：原主集群有记录=正确
                    count_a_before = sum(1 for ts in ts_a_list if ts <= switch_time)
                    count_b_before = sum(1 for ts in ts_b_list if ts <= switch_time)

                    # 切换后：新主集群有记录=正确
                    count_a_after = sum(1 for ts in ts_a_list if ts > switch_time)
                    count_b_after = sum(1 for ts in ts_b_list if ts > switch_time)

                    # === 回退推断：当 old_master/new_master 与配置名无法匹配时 ===
                    if not a_is_old_master and not b_is_old_master:
                        if count_a_before > 0 and count_b_before == 0:
                            a_is_old_master = True
                        elif count_b_before > 0 and count_a_before == 0:
                            b_is_old_master = True

                    if not a_is_new_master and not b_is_new_master:
                        if count_a_after > 0 and count_b_after == 0:
                            a_is_new_master = True
                        elif count_b_after > 0 and count_a_after == 0:
                            b_is_new_master = True

                    # 切换前：原主集群有记录=正确
                    before_correct = False
                    if a_is_old_master and count_a_before > 0:
                        before_correct = True
                    elif b_is_old_master and count_b_before > 0:
                        before_correct = True

                    # 切换后：新主集群有记录=正确
                    after_correct = False
                    if a_is_new_master and count_a_after > 0:
                        after_correct = True
                    elif b_is_new_master and count_b_after > 0:
                        after_correct = True

                    correct = "正确" if (before_correct or after_correct) else "错误"
                else:
                    # 无切换事件，至少一个集群有记录=正确
                    if count_a > 0 or count_b > 0:
                        correct = "正确"
                    else:
                        correct = "错误"

            elif key == "备集群不存储告警":
                # 切换前：原备集群有记录=正确（备集群应打印"不保存告警"）
                # 切换后：新备集群有记录=正确
                if switch_time and old_master and new_master:
                    # 判断切换前哪个集群是主/备集群
                    a_is_old_master = (old_master.lower() in cluster_a_name.lower()) or (cluster_a_name.lower() in old_master.lower())
                    b_is_old_master = (old_master.lower() in cluster_b_name.lower()) or (cluster_b_name.lower() in old_master.lower())

                    # 判断切换后哪个集群是主/备集群
                    a_is_new_master = (new_master.lower() in cluster_a_name.lower()) or (cluster_a_name.lower() in new_master.lower())
                    b_is_new_master = (new_master.lower() in cluster_b_name.lower()) or (cluster_b_name.lower() in new_master.lower())

                    # 切换前
                    count_a_before = sum(1 for ts in ts_a_list if ts <= switch_time)
                    count_b_before = sum(1 for ts in ts_b_list if ts <= switch_time)

                    # 切换后
                    count_a_after = sum(1 for ts in ts_a_list if ts > switch_time)
                    count_b_after = sum(1 for ts in ts_b_list if ts > switch_time)

                    # === 回退推断：当 old_master/new_master 与配置名无法匹配时 ===
                    if not a_is_old_master and not b_is_old_master:
                        # 切换前：有"备集群不存储告警"记录的集群是原备集群
                        if count_a_before > 0 and count_b_before == 0:
                            b_is_old_master = True  # A 是备，B 是主
                        elif count_b_before > 0 and count_a_before == 0:
                            a_is_old_master = True  # B 是备，A 是主

                    if not a_is_new_master and not b_is_new_master:
                        # 切换后：有"备集群不存储告警"记录的集群是新备集群
                        if count_a_after > 0 and count_b_after == 0:
                            b_is_new_master = True  # A 是备，B 是主
                        elif count_b_after > 0 and count_a_after == 0:
                            a_is_new_master = True  # B 是备，A 是主

                    # 切换前：原备集群有记录=正确
                    before_correct = False
                    if a_is_old_master and count_b_before > 0:  # B是备集群，有记录=正确
                        before_correct = True
                    elif b_is_old_master and count_a_before > 0:  # A是备集群，有记录=正确
                        before_correct = True

                    # 切换后：新备集群有记录=正确
                    after_correct = False
                    if a_is_new_master and count_b_after > 0:  # B是备集群，有记录=正确
                        after_correct = True
                    elif b_is_new_master and count_a_after > 0:  # A是备集群，有记录=正确
                        after_correct = True

                    correct = "正确" if (before_correct or after_correct) else "错误"
                else:
                    # 无切换事件，至少一个集群有记录=正确
                    if count_a > 0 or count_b > 0:
                        correct = "正确"
                    else:
                        correct = "错误"

            else:
                # 其他关键字：两个集群都有记录=正确
                if count_a > 0 and count_b > 0:
                    correct = "正确"
                else:
                    correct = "错误"

            print(f"{key:<20} {count_a:<12} {count_b:<12} {correct}")

        print(f"[{'='*80}]")

    def compare_clusters(self) -> None:
        """
        对比两个集群的日志分析结果并输出。
        """
        if len(self.cluster_configs) != 2:
            raise ValueError(f"必须配置两个集群，当前配置了 {len(self.cluster_configs)} 个")

        cluster_a = self.cluster_configs[0]
        cluster_b = self.cluster_configs[1]

        print(f"\n[{'='*80}]")
        print(f"[HA 日志分析启动]")
        print(f"  集群A: {cluster_a['name']} ({cluster_a['base_url']})")
        print(f"  集群B: {cluster_b['name']} ({cluster_b['base_url']})")
        print(f"  白名单服务: {self.service_whitelist}")
        print(f"  分析时间窗口: 最后 {self.analysis_minutes} 分钟")
        print(f"  关键字字典: {self.keyword_dict}")
        print(f"[{'='*80}]")

        results_a = self.analyze_cluster(cluster_a)
        results_b = self.analyze_cluster(cluster_b)
        self._print_comparison(results_a, results_b, cluster_a, cluster_b)

    # ==================== 专项日志分析：集群切换事件 ====================

    def extract_failover_events(self, log_path: str, start_time: Optional[datetime] = None) -> List[dict]:
        """
        从 daemon 日志中提取集群切换事件。
        匹配格式: Delete pod, old master: cluster_A, new master: cluster_B, cost 689ms
        返回: [{timestamp, old_master, new_master, cost_ms, raw_line}, ...]
        若提供了 start_time，只保留 start_time 之后的匹配行；
        否则只保留日志最后时间向前推 analysis_minutes 分钟内的匹配行。
        """
        events: List[dict] = []
        parsed_lines = self._read_log_lines(log_path)

        if not parsed_lines:
            return events

        if start_time:
            cutoff_ts = start_time
        else:
            last_ts = max(ts for ts, _ in parsed_lines)
            cutoff_ts = last_ts - timedelta(minutes=self.analysis_minutes)

        failover_pattern = re.compile(
            r"Delete\s+pod,\s+old\s+master:\s+(\w+),\s+new\s+master:\s+(\w+),\s+cost\s+(\d+)ms"
        )

        for ts, line in parsed_lines:
            if ts < cutoff_ts:
                continue
            match = failover_pattern.search(line)
            if match:
                events.append({
                    "timestamp": ts,
                    "old_master": match.group(1),
                    "new_master": match.group(2),
                    "cost_ms": match.group(3),
                    "raw_line": line,
                })

        return events

    def _extract_failover_from_logs(self, log_paths: List[str], start_time: Optional[datetime] = None) -> List[dict]:
        """从日志路径列表中提取所有切换事件"""
        all_events: List[dict] = []
        for path in log_paths:
            if "daemon" not in os.path.basename(path).lower():
                continue
            events = self.extract_failover_events(path, start_time=start_time)
            all_events.extend(events)
        all_events.sort(key=lambda x: x["timestamp"])
        return all_events

    def print_failover_report(self, cluster_name: str, events: List[dict]) -> None:
        """打印集群切换事件报告"""
        if not events:
            print(f"\n[集群切换事件] {cluster_name}: 未检测到切换事件")
            return

        print(f"\n[{'='*80}]")
        print(f"[集群切换事件报告] {cluster_name}")
        print(f"{'-'*80}")
        for evt in events:
            direction = f"{evt['old_master']}切换{evt['new_master']}"
            print(
                f"关键字 Delete pod, old master:  "
                f"时间: {self._fmt_ts(evt['timestamp'])}  "
                f"{direction}  "
                f"切换时间: cost {evt['cost_ms']}ms"
            )
        print(f"[{'='*80}]")

    # ==================== 专项日志分析：主备集群告警保存状态 ====================

    def extract_ws_master_info(self, log_path: str) -> List[dict]:
        """
        从 ws-backend 日志中提取主集群状态信息。
        匹配行:
            当前集群 xxx 是否为主集群: true/false
            是主集群，保存告警
            不是主集群，不保存告警
        返回: [{timestamp, cluster_name, is_master, save_alert, raw_line}, ...]
        只保留日志最后时间向前推 analysis_minutes 分钟内的匹配行。
        """
        records: List[dict] = []
        parsed_lines = self._read_log_lines(log_path)

        if not parsed_lines:
            return records

        last_ts = max(ts for ts, _ in parsed_lines)
        cutoff_ts = last_ts - timedelta(minutes=self.analysis_minutes)

        master_pattern = re.compile(r"当前集群\s+(\w+)\s+是否为主集群:\s+(true|false)", re.IGNORECASE)
        alert_save_pattern = re.compile(r"是主集群，保存告警")
        alert_skip_pattern = re.compile(r"不是主集群，不保存告警")

        for ts, line in parsed_lines:
            if ts < cutoff_ts:
                continue

            master_match = master_pattern.search(line)
            if master_match:
                records.append({
                    "timestamp": ts,
                    "cluster_name": master_match.group(1),
                    "is_master": master_match.group(2).lower() == "true",
                    "save_alert": None,
                    "raw_line": line,
                })
                continue

            if alert_save_pattern.search(line):
                records.append({
                    "timestamp": ts,
                    "cluster_name": None,
                    "is_master": None,
                    "save_alert": True,
                    "raw_line": line,
                })
                continue

            if alert_skip_pattern.search(line):
                records.append({
                    "timestamp": ts,
                    "cluster_name": None,
                    "is_master": None,
                    "save_alert": False,
                    "raw_line": line,
                })

        return records

    def _extract_ws_master_from_logs(self, log_paths: List[str]) -> List[dict]:
        """从日志路径列表中提取所有 WS 主备状态记录"""
        all_records: List[dict] = []
        for path in log_paths:
            if "ws" not in os.path.basename(path).lower():
                continue
            records = self.extract_ws_master_info(path)
            all_records.extend(records)
        all_records.sort(key=lambda x: x["timestamp"])
        return all_records

    def print_master_status_report(
        self,
        cluster_a_name: str,
        cluster_b_name: str,
        records_a: List[dict],
        records_b: List[dict],
        failover_events: Optional[List[dict]] = None,
    ) -> None:
        """
        打印主备集群告警保存状态报告。
        主集群应检测"是主集群，保存告警 :"
        备集群应检测"不是主集群，不保存告警"
        判断逻辑：
        - 切换前：原主集群有"是主集群，保存告警"，原备集群有"不是主集群，不保存告警"=正确
        - 切换后：新主集群有"是主集群，保存告警"，新备集群有"不是主集群，不保存告警"=正确
        """
        print(f"\n[{'='*80}]")
        print("[主备集群告警保存状态报告]")
        print(f"{'集群':<12} {'主/备':<10} {'时期':<10} {'检测到'}")
        print(f"{'-'*80}")

        # 获取切换时间点
        switch_time = None
        old_master = None
        new_master = None
        if failover_events:
            switch_time = failover_events[0]["timestamp"] if failover_events else None
            old_master = failover_events[0]["old_master"] if failover_events else None
            new_master = failover_events[0]["new_master"] if failover_events else None

        def get_cluster_status_by_time(records, cluster_name, before_switch=True):
            """获取指定时期（切换前/后）的主备状态和告警保存状态"""
            if not switch_time:
                # 无切换事件，获取最新状态
                master_decls = [r for r in records if r["cluster_name"] is not None]
                if not master_decls:
                    return None, None
                latest_decl = master_decls[-1]
                is_master = latest_decl["is_master"]
                decl_ts = latest_decl["timestamp"]
                alert_records = [
                    r for r in records
                    if r["save_alert"] is not None and r["timestamp"] >= decl_ts
                ]
                save_alert = alert_records[0]["save_alert"] if alert_records else None
                return is_master, save_alert

            # 根据时期筛选记录
            if before_switch:
                # 切换前：时间 <= 切换时间点
                valid_records = [r for r in records if r["timestamp"] <= switch_time]
            else:
                # 切换后：时间 > 切换时间点
                valid_records = [r for r in records if r["timestamp"] > switch_time]

            if not valid_records:
                return None, None

            # 查找主集群声明
            master_decls = [r for r in valid_records if r["cluster_name"] is not None]
            if not master_decls:
                return None, None

            latest_decl = master_decls[-1]
            is_master = latest_decl["is_master"]
            decl_ts = latest_decl["timestamp"]

            # 查找该声明之后的告警保存记录
            alert_records = [
                r for r in valid_records
                if r["save_alert"] is not None and r["timestamp"] >= decl_ts
            ]
            save_alert = alert_records[0]["save_alert"] if alert_records else None

            return is_master, save_alert

        # 判断时期标签
        period_before = "切换前" if switch_time else "当前"
        period_after = "切换后" if switch_time else "当前"

        # 根据切换事件判断主备关系
        # old_master: 切换前的主集群, new_master: 切换后的主集群
        a_is_old_master = False
        b_is_old_master = False
        a_is_new_master = False
        b_is_new_master = False

        if old_master and new_master:
            a_is_old_master = (old_master.lower() in cluster_a_name.lower()) or (cluster_a_name.lower() in old_master.lower())
            b_is_old_master = (old_master.lower() in cluster_b_name.lower()) or (cluster_b_name.lower() in old_master.lower())
            a_is_new_master = (new_master.lower() in cluster_a_name.lower()) or (cluster_a_name.lower() in new_master.lower())
            b_is_new_master = (new_master.lower() in cluster_b_name.lower()) or (cluster_b_name.lower() in new_master.lower())

            # 若日志中的 old_master/new_master 与配置名无法直接匹配（如中英文差异），
            # 则根据日志中提取的 is_master 状态进行回退推断
            if not a_is_old_master and not b_is_old_master:
                if is_master_a_before is True and is_master_b_before is False:
                    a_is_old_master = True
                elif is_master_b_before is True and is_master_a_before is False:
                    b_is_old_master = True

            if not a_is_new_master and not b_is_new_master:
                if is_master_a_after is True and is_master_b_after is False:
                    a_is_new_master = True
                elif is_master_b_after is True and is_master_a_after is False:
                    b_is_new_master = True

        # 切换前状态
        is_master_a_before, save_alert_a_before = get_cluster_status_by_time(records_a, cluster_a_name, before_switch=True)
        is_master_b_before, save_alert_b_before = get_cluster_status_by_time(records_b, cluster_b_name, before_switch=True)

        # 切换后状态
        is_master_a_after, save_alert_a_after = get_cluster_status_by_time(records_a, cluster_a_name, before_switch=False)
        is_master_b_after, save_alert_b_after = get_cluster_status_by_time(records_b, cluster_b_name, before_switch=False)

        # 打印切换前状态
        print(f"--- {period_before} ---")
        if switch_time and old_master:
            # 根据切换事件判断
            if a_is_old_master:
                # A是切换前的主集群
                if save_alert_a_before is True:
                    print(f"{cluster_a_name:<12} 主集群    {period_before:<10} 是主集群，保存告警  正确")
                elif save_alert_a_before is False:
                    print(f"{cluster_a_name:<12} 主集群    {period_before:<10} 是主集群，不保存告警  错误")
                else:
                    print(f"{cluster_a_name:<12} 主集群    {period_before:<10} 告警保存状态未知")

                if save_alert_b_before is False:
                    print(f"{cluster_b_name:<12} 备集群    {period_before:<10} 不是主集群，不保存告警  正确")
                elif save_alert_b_before is True:
                    print(f"{cluster_b_name:<12} 备集群    {period_before:<10} 不是主集群，保存告警  错误")
                else:
                    print(f"{cluster_b_name:<12} 备集群    {period_before:<10} 告警保存状态未知")
            elif b_is_old_master:
                # B是切换前的主集群
                if save_alert_b_before is True:
                    print(f"{cluster_b_name:<12} 主集群    {period_before:<10} 是主集群，保存告警  正确")
                elif save_alert_b_before is False:
                    print(f"{cluster_b_name:<12} 主集群    {period_before:<10} 是主集群，不保存告警  错误")
                else:
                    print(f"{cluster_b_name:<12} 主集群    {period_before:<10} 告警保存状态未知")

                if save_alert_a_before is False:
                    print(f"{cluster_a_name:<12} 备集群    {period_before:<10} 不是主集群，不保存告警  正确")
                elif save_alert_a_before is True:
                    print(f"{cluster_a_name:<12} 备集群    {period_before:<10} 不是主集群，保存告警  错误")
                else:
                    print(f"{cluster_a_name:<12} 备集群    {period_before:<10} 告警保存状态未知")
            else:
                print(f"  {period_before} 无法匹配主备关系")
        else:
            # 无切换事件，根据日志中的 is_master 判断
            if is_master_a_before is True and is_master_b_before is False:
                if save_alert_a_before is True:
                    print(f"{cluster_a_name:<12} 主集群    {period_before:<10} 是主集群，保存告警  正确")
                else:
                    print(f"{cluster_a_name:<12} 主集群    {period_before:<10} 是主集群，不保存告警  错误")
                if save_alert_b_before is False:
                    print(f"{cluster_b_name:<12} 备集群    {period_before:<10} 不是主集群，不保存告警  正确")
                else:
                    print(f"{cluster_b_name:<12} 备集群    {period_before:<10} 不是主集群，保存告警  错误")
            elif is_master_b_before is True and is_master_a_before is False:
                if save_alert_b_before is True:
                    print(f"{cluster_b_name:<12} 主集群    {period_before:<10} 是主集群，保存告警  正确")
                else:
                    print(f"{cluster_b_name:<12} 主集群    {period_before:<10} 是主集群，不保存告警  错误")
                if save_alert_a_before is False:
                    print(f"{cluster_a_name:<12} 备集群    {period_before:<10} 不是主集群，不保存告警  正确")
                else:
                    print(f"{cluster_a_name:<12} 备集群    {period_before:<10} 不是主集群，保存告警  错误")
            else:
                print(f"  {period_before} 无法确定主备关系")

        # 打印切换后状态（如果有切换事件）
        if switch_time and new_master:
            print(f"--- {period_after} ---")
            if a_is_new_master:
                # A是切换后的主集群
                if save_alert_a_after is True:
                    print(f"{cluster_a_name:<12} 主集群    {period_after:<10} 是主集群，保存告警  正确")
                elif save_alert_a_after is False:
                    print(f"{cluster_a_name:<12} 主集群    {period_after:<10} 是主集群，不保存告警  错误")
                else:
                    print(f"{cluster_a_name:<12} 主集群    {period_after:<10} 告警保存状态未知")

                if save_alert_b_after is False:
                    print(f"{cluster_b_name:<12} 备集群    {period_after:<10} 不是主集群，不保存告警  正确")
                elif save_alert_b_after is True:
                    print(f"{cluster_b_name:<12} 备集群    {period_after:<10} 不是主集群，保存告警  错误")
                else:
                    print(f"{cluster_b_name:<12} 备集群    {period_after:<10} 告警保存状态未知")
            elif b_is_new_master:
                # B是切换后的主集群
                if save_alert_b_after is True:
                    print(f"{cluster_b_name:<12} 主集群    {period_after:<10} 是主集群，保存告警  正确")
                elif save_alert_b_after is False:
                    print(f"{cluster_b_name:<12} 主集群    {period_after:<10} 是主集群，不保存告警  错误")
                else:
                    print(f"{cluster_b_name:<12} 主集群    {period_after:<10} 告警保存状态未知")

                if save_alert_a_after is False:
                    print(f"{cluster_a_name:<12} 备集群    {period_after:<10} 不是主集群，不保存告警  正确")
                elif save_alert_a_after is True:
                    print(f"{cluster_a_name:<12} 备集群    {period_after:<10} 不是主集群，保存告警  错误")
                else:
                    print(f"{cluster_a_name:<12} 备集群    {period_after:<10} 告警保存状态未知")
            else:
                print(f"  {period_after} 无法匹配主备关系")

        print(f"[{'='*80}]")

    # ==================== 工具方法 ====================

    @staticmethod
    def _fmt_ts(dt: datetime) -> str:
        """格式化时间戳输出"""
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # ==================== 入口 ====================

    def run(self) -> None:
        """执行完整分析流程"""
        if len(self.cluster_configs) != 2:
            raise ValueError(f"必须配置两个集群，当前配置了 {len(self.cluster_configs)} 个")

        cluster_a = self.cluster_configs[0]
        cluster_b = self.cluster_configs[1]

        print(f"\n[{'='*80}]")
        print(f"[HA 日志分析启动]")
        print(f"  集群A: {cluster_a['name']} ({cluster_a['base_url']})")
        print(f"  集群B: {cluster_b['name']} ({cluster_b['base_url']})")
        print(f"  白名单服务: {self.service_whitelist}")
        print(f"  分析时间窗口: 最后 {self.analysis_minutes} 分钟")
        print(f"  关键字字典: {self.keyword_dict}")
        print(f"  下载开关: {self.download_logs}")
        print(f"[{'='*80}]")

        # 根据下载开关决定获取日志方式
        if self.download_logs:
            logs_a = self.download_cluster_logs(cluster_a)
            logs_b = self.download_cluster_logs(cluster_b)
        else:
            logs_a = self.get_local_logs(cluster_a)
            logs_b = self.get_local_logs(cluster_b)

        # 1. 通用关键字对比分析
        results_a, start_a, end_a = self._analyze_cluster_logs(logs_a)
        results_b, start_b, end_b = self._analyze_cluster_logs(logs_b)

        # 打印分析时间范围
        if start_a and end_a:
            print(f"[分析时间范围] {self._fmt_ts(start_a)} ~ {self._fmt_ts(end_a)}")
        elif start_b and end_b:
            print(f"[分析时间范围] {self._fmt_ts(start_b)} ~ {self._fmt_ts(end_b)}")

        print(f"[分析完成] {cluster_a['name']} 关键字命中统计: ")
        for key, ts_list in sorted(results_a.items()):
            print(f"  - {key}: {len(ts_list)} 次")
        print(f"[分析完成] {cluster_b['name']} 关键字命中统计: ")
        for key, ts_list in sorted(results_b.items()):
            print(f"  - {key}: {len(ts_list)} 次")

        # 2. Daemon 日志切换事件分析
        events_a = self._extract_failover_from_logs(logs_a)
        events_b = self._extract_failover_from_logs(logs_b)
        self.print_failover_report(cluster_a["name"], events_a)
        self.print_failover_report(cluster_b["name"], events_b)

        # 合并切换事件（两个集群的切换事件应该相同）
        all_events = events_a + events_b
        all_events.sort(key=lambda x: x["timestamp"])

        # 3. 通用关键字对比分析（传入切换事件用于判断正确性）
        self._print_comparison(results_a, results_b, cluster_a, cluster_b, all_events)

        # 4. WS 日志主备集群告警保存状态分析（传入切换事件用于判断切换前后正确性）
        ws_records_a = self._extract_ws_master_from_logs(logs_a)
        ws_records_b = self._extract_ws_master_from_logs(logs_b)
        self.print_master_status_report(cluster_a["name"], cluster_b["name"], ws_records_a, ws_records_b, all_events)


def main():
    """命令行入口"""
    analyzer = HaLogAnalyzer()
    analyzer.run()


if __name__ == "__main__":
    main()
