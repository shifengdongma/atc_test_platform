#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HA 双集群日志分析脚本

功能：
1. 分别登录两个 IOMP 平台下载白名单服务的日志
2. 分析日志最后时间向前推 N 分钟（默认10分钟）内的日志
3. 根据关键字字典检索日志内容
4. 对比两个集群中相同关键字的时间戳，计算差值
5. 输出对比结果并总结出现次数

使用方式：
    1. 修改下方配置区的参数
    2. 直接运行: python api_tools/ha_日志分析.py
    3. 或被其他脚本导入调用:
       from api_tools.ha_日志分析 import HaLogAnalyzer
       analyzer = HaLogAnalyzer()
       analyzer.run()
"""

import os
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 将项目根目录加入 sys.path 以便导入 iomp_core
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api_tools.iomp_core import IompLogDownloader


class HaLogAnalyzer:
    """
    HA 双集群日志分析器
    """

    # ==================== 配置区（用户按需修改） ====================

    # 1. 服务白名单：只下载这些服务的日志
    SERVICE_WHITELIST: list[str] = [
        "la-atc-ws-backend",
        "la-atc-daemon-server",
        # 按需添加更多服务...
    ]

    # 2. 两组 IOMP 平台配置
    CLUSTER_CONFIGS: list[dict] = [
        {
            "name": "集群24",
            "base_url": "http://10.165.32.24:8801",
            "username": "wuweibin",
            "password": "kedacom@123",
            "cluster_id": "02b01cdf6b534d80a67d8b1994870547",
        },
        {
            "name": "集群25",
            "base_url": "http://10.165.32.25:8801",  # 按需修改地址
            "username": "wuweibin",
            "password": "kedacom@123",
            "cluster_id": "",  # 空字符串表示自动获取
        },
    ]

    # 3. 日志分析时间窗口（分钟），默认10分钟
    ANALYSIS_MINUTES: int = 10

    # 4. 检索关键字字典列表 {key: value}
    # key: 用于输出标识的简短名称
    # value: 日志中实际要搜索的关键字/关键短语
    KEYWORD_DICT: dict[str, str] = {
        "ERROR_DB": "数据库连接失败",
        "WARN_TIMEOUT": "请求超时",
        # 按需添加更多关键字...
    }

    # 5. 命名空间
    NAMESPACE: str = "kedacom-project-namespace"

    # 6. 日志下载输出目录前缀
    OUTPUT_DIR_PREFIX: str = "./tmp/ha_logs"

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

        downloader = self._create_downloader(cluster_config)
        try:
            paths = downloader.download_all_logs(namespace=self.namespace)
            print(f"[下载完成] {cluster_config['name']} 共 {len(paths)} 个文件")
            return paths
        except Exception as e:
            print(f"[下载异常] {cluster_config['name']}: {e}")
            return []

    # ==================== 日志解析 ====================

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

    def analyze_single_log(self, log_path: str) -> Dict[str, List[datetime]]:
        """
        分析单个日志文件。
        返回: {keyword_key: [timestamp1, timestamp2, ...]}
        只保留日志最后时间向前推 analysis_minutes 分钟内的匹配行。
        """
        results: Dict[str, List[datetime]] = {}

        # 读取所有行并解析时间戳
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
            return results

        if not parsed_lines:
            return results

        # 计算时间窗口
        last_ts = max(ts for ts, _ in parsed_lines)
        cutoff_ts = last_ts - timedelta(minutes=self.analysis_minutes)

        # 在时间窗口内搜索关键字
        for ts, line in parsed_lines:
            if ts < cutoff_ts:
                continue
            for key, value in self.keyword_dict.items():
                if value in line:
                    results.setdefault(key, []).append(ts)

        return results

    def analyze_cluster(self, cluster_config: dict) -> Dict[str, List[datetime]]:
        """
        分析整个集群的所有白名单服务日志。
        返回合并后的 {keyword_key: [timestamp, ...]}（已按时间排序）。
        """
        log_paths = self.download_cluster_logs(cluster_config)
        merged: Dict[str, List[datetime]] = {}

        for path in log_paths:
            single_result = self.analyze_single_log(path)
            for key, ts_list in single_result.items():
                merged.setdefault(key, []).extend(ts_list)

        # 去重并排序
        for key in merged:
            merged[key] = sorted(list(set(merged[key])))

        print(f"[分析完成] {cluster_config['name']} 关键字命中统计: ")
        for key, ts_list in sorted(merged.items()):
            print(f"  - {key}: {len(ts_list)} 次")

        return merged

    # ==================== 双集群对比 ====================

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

        # 输出对比结果
        print(f"\n[{'='*80}]")
        print(f"{'关键字':<15} {'集群A':<12} {'时间戳':<26} {'集群B':<12} {'时间戳':<26} {'差值(秒)'}")
        print(f"{'-'*120}")

        all_keys = set(results_a.keys()) | set(results_b.keys())
        summary: Dict[str, dict] = {}

        for key in sorted(all_keys):
            ts_a_list = results_a.get(key, [])
            ts_b_list = results_b.get(key, [])
            pair_count = 0

            max_len = max(len(ts_a_list), len(ts_b_list))
            for i in range(max_len):
                t_a = ts_a_list[i] if i < len(ts_a_list) else None
                t_b = ts_b_list[i] if i < len(ts_b_list) else None

                if t_a and t_b:
                    diff_seconds = abs((t_a - t_b).total_seconds())
                    print(
                        f"{key:<15} "
                        f"{cluster_a['name']:<12} "
                        f"{self._fmt_ts(t_a):<26} "
                        f"{cluster_b['name']:<12} "
                        f"{self._fmt_ts(t_b):<26} "
                        f"{diff_seconds:.3f}"
                    )
                    pair_count += 1
                elif t_a:
                    print(
                        f"{key:<15} "
                        f"{cluster_a['name']:<12} "
                        f"{self._fmt_ts(t_a):<26} "
                        f"{cluster_b['name']:<12} "
                        f"{'N/A':<26} "
                        f"N/A"
                    )
                elif t_b:
                    print(
                        f"{key:<15} "
                        f"{cluster_a['name']:<12} "
                        f"{'N/A':<26} "
                        f"{cluster_b['name']:<12} "
                        f"{self._fmt_ts(t_b):<26} "
                        f"N/A"
                    )

            summary[key] = {
                cluster_a["name"]: len(ts_a_list),
                cluster_b["name"]: len(ts_b_list),
                "paired": pair_count,
            }

        # 总结
        print(f"\n[{'='*80}]")
        print("[出现次数总结]")
        print(f"{'关键字':<15} {cluster_a['name']:<12} {cluster_b['name']:<12} {'配对成功':<10}")
        print(f"{'-'*60}")
        for key, stats in summary.items():
            print(
                f"{key:<15} "
                f"{stats[cluster_a['name']]:<12} "
                f"{stats[cluster_b['name']]:<12} "
                f"{stats['paired']:<10}"
            )
        print(f"[{'='*80}]")

    @staticmethod
    def _fmt_ts(dt: datetime) -> str:
        """格式化时间戳输出"""
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # ==================== 入口 ====================

    def run(self) -> None:
        """执行完整分析流程"""
        self.compare_clusters()


def main():
    """命令行入口"""
    analyzer = HaLogAnalyzer()
    analyzer.run()


if __name__ == "__main__":
    main()
