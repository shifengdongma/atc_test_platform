#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行模式基类
所有模式必须继承此类并实现抽象方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseMode(ABC):
    """运行模式基类"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.running = False

    @abstractmethod
    def start(self):
        """启动模式"""
        pass

    @abstractmethod
    def stop(self):
        """停止模式"""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """检查是否正在运行"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        pass
