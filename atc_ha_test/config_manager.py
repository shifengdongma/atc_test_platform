#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置管理模块

功能：
1. 集中管理所有测试配置
2. 支持多环境配置
3. 配置验证和自动加载
4. 环境变量覆盖
5. 配置缓存和版本控制
"""

import os
import json
import hashlib
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class TestServiceConfig:
    """单个服务测试配置"""
    name: str
    namespace: str = "kedacom-project-namespace"
    cluster_name: str = "dk"
    kind: str = "All"
    scale_to_zero: int = 0
    wait_seconds: int = 120
    rounds: int = 1
    poll_interval: int = 5
    poll_timeout: int = 300
    dry_run: bool = False
    master_node: str = "auto"
    analysis_minutes: int = 5
    round_gap_seconds: Optional[int] = None
    priority: int = 5  # 测试优先级，1-10，数字越大优先级越高
    parallelizable: bool = True  # 是否支持并行测试
    dependencies: list = field(default_factory=list)  # 依赖的服务列表


@dataclass
class ClusterConfig:
    """集群配置"""
    endpoint_a: str = "http://10.0.0.1:8080"
    endpoint_b: str = "http://10.0.0.2:8080"
    access_key_a: str = "your-access-key-a"
    access_key_b: str = "your-access-key-b"
    ws_endpoint: str = "ws://10.0.0.1:8080"
    kafka_bootstrap_servers: str = "10.0.0.3:9092,10.0.0.4:9092"
    redis_endpoint: str = "10.0.0.5:6379"
    es_endpoint: str = "http://10.0.0.6:9200"
    db_endpoint_a: str = "jdbc:dm://10.0.0.7:5236"
    db_endpoint_b: str = "jdbc:dm://10.0.0.8:5236"


@dataclass
class PerformanceConfig:
    """性能配置"""
    parallel_tests: bool = True  # 是否启用并行测试
    max_workers: int = 3  # 最大并发数
    timeout_per_test: int = 3600  # 单个测试超时时间（秒）
    circuit_breaker_threshold: int = 5  # 熔断阈值
    cache_enabled: bool = True  # 启用缓存
    cache_ttl: int = 3600  # 缓存TTL（秒）
    retry_enabled: bool = True  # 启用重试
    max_retries: int = 3  # 最大重试次数


@dataclass
class NotificationConfig:
    """通知配置"""
    email_enabled: bool = False
    webhook_enabled: bool = False
    webhook_url: str = ""
    slack_webhook_url: str = ""
    threshold_failures: int = 2  # 触发通知的失败次数


@dataclass
class DatabaseConfig:
    """数据库配置"""
    db_config_path: str = "/path/to/config.json"
    username: str = "root"
    password: str = "password"
    database: str = "utm_db"
    connection_timeout: int = 30


@dataclass
class TestEnvironment:
    """测试环境配置"""
    name: str = "dev"
    cluster_config: ClusterConfig = field(default_factory=ClusterConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)


class ConfigManager:
    """统一配置管理器"""

    # 预定义的环境配置
    ENVIRONMENTS = {
        "dev": TestEnvironment(name="dev"),
        "test": TestEnvironment(name="test", cluster_config=ClusterConfig(
            endpoint_a="http://test1.company.com:8080",
            endpoint_b="http://test2.company.com:8080",
            redis_endpoint="test-redis.company.com:6379"
        )),
        "staging": TestEnvironment(name="staging", cluster_config=ClusterConfig(
            endpoint_a="http://staging1.company.com:8080",
            endpoint_b="http://staging2.company.com:8080",
            redis_endpoint="staging-redis.company.com:6379"
        )),
        "prod": TestEnvironment(name="prod", cluster_config=ClusterConfig(
            endpoint_a="http://prod1.company.com:8080",
            endpoint_b="http://prod2.company.com:8080",
            redis_endpoint="prod-redis.company.com:6379"
        ))
    }

    DEFAULT_SERVICES = [
        TestServiceConfig(
            name="la-atc-ws-backend",
            wait_seconds=120,
            rounds=3,
            analysis_minutes=5
        ),
        TestServiceConfig(
            name="redis-atc",
            wait_seconds=60,
            rounds=2,
            analysis_minutes=3
        ),
        TestServiceConfig(
            name="emqx",
            wait_seconds=180,
            rounds=1,
            analysis_minutes=10
        )
    ]

    def __init__(self, env_name: str = "dev"):
        self.env_name = env_name
        self.env = self.ENVIRONMENTS.get(env_name, self.ENVIRONMENTS["dev"])
        self.services = self.DEFAULT_SERVICES.copy()
        self.config_loaded = False

    def load_config(self, config_file: Optional[str] = None) -> None:
        """加载配置文件"""
        if config_file:
            self._load_from_file(config_file)
        else:
            self._load_from_env()

        self._validate_config()
        self.config_loaded = True

    def _load_from_file(self, config_file: str) -> None:
        """从文件加载配置"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 更新环境配置
            if 'cluster' in config_data:
                self.env.cluster_config = ClusterConfig(
                    **config_data['cluster']
                )

            if 'performance' in config_data:
                self.env.performance = PerformanceConfig(
                    **config_data['performance']
                )

            if 'notification' in config_data:
                self.env.notification = NotificationConfig(
                    **config_data['notification']
                )

            if 'database' in config_data:
                self.env.database = DatabaseConfig(
                    **config_data['database']
                )

            # 更新服务配置
            if 'services' in config_data:
                self.services = []
                for svc_config in config_data['services']:
                    self.services.append(TestServiceConfig(**svc_config))

        except Exception as e:
            raise ValueError(f"配置文件加载失败: {e}")

    def _load_from_env(self) -> None:
        """从环境变量加载配置"""
        # 集群配置
        if os.getenv('ENDPOINT_A'):
            self.env.cluster_config.endpoint_a = os.getenv('ENDPOINT_A')
        if os.getenv('ENDPOINT_B'):
            self.env.cluster_config.endpoint_b = os.getenv('ENDPOINT_B')
        if os.getenv('REDIS_ENDPOINT'):
            self.env.cluster_config.redis_endpoint = os.getenv('REDIS_ENDPOINT')

        # 性能配置
        if os.getenv('MAX_WORKERS'):
            self.env.performance.max_workers = int(os.getenv('MAX_WORKERS'))
        if os.getenv('PARALLEL_TESTS'):
            self.env.performance.parallel_tests = os.getenv('PARALLEL_TESTS') == 'true'

    def _validate_config(self) -> None:
        """验证配置有效性"""
        # 验证服务配置
        if not self.services:
            raise ValueError("必须配置至少一个测试服务")

        # 验证性能配置
        if self.env.performance.max_workers <= 0:
            raise ValueError("max_workers 必须大于0")

        # 验证集群配置
        if not self.env.cluster_config.endpoint_a or not self.env.cluster_config.endpoint_b:
            raise ValueError("必须配置双集群端点")

    def get_config(self, key: str) -> Any:
        """获取配置值"""
        if not self.config_loaded:
            self.load_config()

        # 根据键路径获取配置值
        keys = key.split('.')
        value = self.env

        for k in keys:
            if hasattr(value, k):
                value = getattr(value, k)
            else:
                raise KeyError(f"配置键 '{key}' 不存在")

        return value

    def get_service_config(self, service_name: str) -> TestServiceConfig:
        """获取指定服务的配置"""
        service_configs = [svc for svc in self.services if svc.name == service_name]
        if not service_configs:
            # 创建默认配置
            default_config = TestServiceConfig(name=service_name)
            self.services.append(default_config)
            return default_config

        return service_configs[0]

    def update_service_config(self, service_name: str, **kwargs) -> None:
        """更新服务配置"""
        if not self.config_loaded:
            self.load_config()

        service_config = self.get_service_config(service_name)

        # 更新配置参数
        for key, value in kwargs.items():
            if hasattr(service_config, key):
                setattr(service_config, key, value)
            else:
                setattr(service_config, key, value)

    def get_config_hash(self) -> str:
        """获取配置哈希值，用于缓存键"""
        if not self.config_loaded:
            self.load_config()

        config_dict = {
            'env': asdict(self.env),
            'services': [asdict(svc) for svc in self.services]
        }

        config_str = json.dumps(config_dict, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    def save_config(self, output_file: str) -> None:
        """保存当前配置到文件"""
        if not self.config_loaded:
            self.load_config()

        config_data = {
            'environment': self.env_name,
            'cluster': asdict(self.env.cluster_config),
            'performance': asdict(self.env.performance),
            'notification': asdict(self.env.notification),
            'database': asdict(self.env.database),
            'services': [asdict(svc) for svc in self.services]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        print(f"配置已保存到: {output_file}")

    def list_services(self) -> list:
        """列出所有服务配置"""
        if not self.config_loaded:
            self.load_config()

        services_info = []
        for svc in self.services:
            services_info.append({
                "name": svc.name,
                "namespace": svc.namespace,
                "wait_seconds": svc.wait_seconds,
                "rounds": svc.rounds,
                "priority": svc.priority,
                "parallelizable": svc.parallelizable
            })

        return sorted(services_info, key=lambda x: x['priority'], reverse=True)

    @staticmethod
    def create_sample_config(output_file: str = "config_sample.json") -> None:
        """创建示例配置文件"""
        # 创建示例配置管理器
        sample_manager = ConfigManager("test")
        sample_manager.services = [
            TestServiceConfig(
                name="la-atc-ws-backend",
                wait_seconds=120,
                rounds=3,
                analysis_minutes=5,
                priority=10,
                parallelizable=True
            ),
            TestServiceConfig(
                name="redis-atc",
                wait_seconds=60,
                rounds=2,
                analysis_minutes=3,
                priority=8,
                parallelizable=True
            ),
            TestServiceConfig(
                name="emqx",
                wait_seconds=180,
                rounds=1,
                analysis_minutes=10,
                priority=9,
                parallelizable=False,
                dependencies=["kafka"]
            )
        ]

        # 根据实际环境更新配置
        sample_manager.env.cluster_config = ClusterConfig(
            endpoint_a="http://10.0.0.1:8080",
            endpoint_b="http://10.0.0.2:8080"
        )

        sample_manager.save_config(output_file)
        print(f"示例配置已创建: {output_file}")


# 全局配置实例
_config_manager = None


def get_config_manager(env_name: str = "dev") -> ConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager

    if _config_manager is None:
        _config_manager = ConfigManager(env_name)

    return _config_manager


def init_config(env_name: str = "dev", config_file: Optional[str] = None) -> ConfigManager:
    """初始化配置"""
    global _config_manager

    _config_manager = ConfigManager(env_name)
    _config_manager.load_config(config_file)

    return _config_manager