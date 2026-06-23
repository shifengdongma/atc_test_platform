#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
航空器名称生成器
支持自定义格式、序号、UUID 等变量
"""

import uuid
import time
from typing import Dict, List


class AircraftNameGenerator:
    """
    航空器名称生成器 - 预留扩展接口

    支持格式模板变量:
        {seq}       - 自增序号 (如: 00001)
        {uuid}      - 短 UUID (8位)
        {timestamp} - 当前时间戳
        {date}      - 日期 (YYYYMMDD)
    """

    def __init__(self, config: Dict = None):
        if config is None:
            config = {}
        self.enabled = config.get('enabled', False)
        self.format_template = config.get('format', 'UAV_{seq:05d}')
        self.start_seq = config.get('start_seq', 1)
        self._counter = self.start_seq
        self._used_names = set()

    def generate(self) -> str:
        """生成下一个航空器名称"""
        if not self.enabled:
            return self._generate_uuid_name()

        max_attempts = 100
        for _ in range(max_attempts):
            name = self._format_name()
            if name not in self._used_names:
                self._used_names.add(name)
                self._counter += 1
                return name
            self._counter += 1

        # 去重失败后追加随机后缀
        name = f"{self._format_name()}_{uuid.uuid4().hex[:4].upper()}"
        self._used_names.add(name)
        self._counter += 1
        return name

    def _format_name(self) -> str:
        """根据模板格式化名称"""
        now = time.time()
        local_time = time.localtime(now)

        fmt = self.format_template
        fmt = fmt.replace('{seq}', f'{self._counter}')
        fmt = fmt.replace('{uuid}', uuid.uuid4().hex[:8].upper())
        fmt = fmt.replace('{timestamp}', str(int(now)))
        fmt = fmt.replace('{date}', time.strftime('%Y%m%d', local_time))

        # 支持 Python format 语法如 {seq:05d}
        try:
            fmt = fmt.format(seq=self._counter)
        except:
            pass

        return fmt

    def _generate_uuid_name(self) -> str:
        """默认使用 UUID 生成名称"""
        return f"UAV_{uuid.uuid4().hex}"

    def generate_batch(self, count: int) -> List[str]:
        """批量生成名称"""
        return [self.generate() for _ in range(count)]

    def reset(self):
        """重置计数器"""
        self._counter = self.start_seq
        self._used_names.clear()

    def get_stats(self) -> Dict:
        """获取生成统计"""
        return {
            'generated_count': self._counter - self.start_seq,
            'start_seq': self.start_seq,
            'current_seq': self._counter,
            'unique_count': len(self._used_names),
        }
