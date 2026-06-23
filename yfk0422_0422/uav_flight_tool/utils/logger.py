#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志工具
"""

import sys
import time
from typing import Dict


class Logger:
    """简易日志器"""

    LEVELS = {
        'DEBUG': 0,
        'INFO': 1,
        'WARN': 2,
        'ERROR': 3,
    }

    def __init__(self, config: Dict = None):
        if config is None:
            config = {}
        self.level = self.LEVELS.get(config.get('level', 'INFO'), 1)
        self.file_path = config.get('file', '')
        self.console = config.get('console', True)
        self._file_handle = None
        if self.file_path:
            try:
                import os
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                self._file_handle = open(self.file_path, 'a', encoding='utf-8')
            except Exception as e:
                print(f"日志文件打开失败: {e}")

    def _log(self, level_name: str, msg: str):
        level_val = self.LEVELS.get(level_name, 1)
        if level_val < self.level:
            return

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        line = f"[{timestamp}] [{level_name}] {msg}"

        if self.console:
            print(line)

        if self._file_handle:
            try:
                self._file_handle.write(line + '\n')
                self._file_handle.flush()
            except:
                pass

    def debug(self, msg: str):
        self._log('DEBUG', msg)

    def info(self, msg: str):
        self._log('INFO', msg)

    def warn(self, msg: str):
        self._log('WARN', msg)

    def error(self, msg: str):
        self._log('ERROR', msg)

    def close(self):
        if self._file_handle:
            try:
                self._file_handle.close()
            except:
                pass


# 全局日志实例
_global_logger = None


def get_logger(config: Dict = None) -> Logger:
    """获取全局日志实例"""
    global _global_logger
    if _global_logger is None and config is not None:
        _global_logger = Logger(config)
    elif _global_logger is None:
        _global_logger = Logger()
    return _global_logger
