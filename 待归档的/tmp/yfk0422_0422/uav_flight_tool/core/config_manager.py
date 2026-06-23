#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理器
统一读取和管理 config.yaml
"""

import os
import yaml
from typing import Dict, List, Any


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
        self.config_path = config_path
        self.config = self._load_yaml(config_path)

    def _load_yaml(self, path: str) -> Dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def get_mode(self) -> str:
        """获取运行模式"""
        return self.config.get('mode', 'simulation')

    def get_kafka_config(self) -> Dict[str, Any]:
        """获取 Kafka 配置"""
        return self.config.get('kafka', {})

    def get_redis_config(self) -> Dict[str, Any]:
        """获取 Redis 配置"""
        return self.config.get('redis', {})

    def get_scene_mode_config(self) -> Dict[str, Any]:
        """获取场景模式配置"""
        return self.config.get('scene_mode', {})

    def get_simulation_mode_config(self) -> Dict[str, Any]:
        """获取仿真模式配置"""
        return self.config.get('simulation_mode', {})

    def get_stress_test_mode_config(self) -> Dict[str, Any]:
        """获取压力测试模式配置"""
        return self.config.get('stress_test_mode', {})

    def get_aircraft_name_config(self) -> Dict[str, Any]:
        """获取航空器名称配置"""
        return self.config.get('aircraft_name', {})

    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.config.get('logging', {})

    def get_webui_config(self) -> Dict[str, Any]:
        """获取 WebUI 配置"""
        return self.config.get('webui', {})

    def get_gui_config(self) -> Dict[str, Any]:
        """获取 GUI 配置"""
        return self.config.get('gui', {})

    def get_full_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self.config

    def reload(self):
        """重新加载配置"""
        self.config = self._load_yaml(self.config_path)
        print(f"配置已重新加载: {self.config_path}")
