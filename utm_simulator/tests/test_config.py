# -*- coding: utf-8 -*-
"""测试 config.py — 配置加载、环境变量覆盖、env.py 回退"""

import sys
import os

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from config import (
    load_config, get_config, reload_config,
    AppConfig, RedisConfig, KafkaConfig, SimulationConfig,
)


class TestRedisConfig:
    """RedisConfig 数据类测试。"""

    def test_defaults(self):
        cfg = RedisConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 6379
        assert cfg.password == ""
        assert cfg.db == 0

    def test_custom_values(self):
        cfg = RedisConfig(host="redis.local", port=7000, password="secret", db=1)
        assert cfg.host == "redis.local"
        assert cfg.port == 7000
        assert cfg.password == "secret"
        assert cfg.db == 1

    def test_port_int(self):
        cfg = RedisConfig(port=1234)
        assert cfg.port_int == 1234
        cfg2 = RedisConfig(port="6380")
        assert cfg2.port_int == 6380


class TestKafkaConfig:
    """KafkaConfig 数据类测试。"""

    def test_defaults(self):
        cfg = KafkaConfig()
        assert cfg.bootstrap_servers == "127.0.0.1:9092"
        assert cfg.bootstrap_servers_mirror is None
        assert cfg.flush_timeout_sec == 1.0

    def test_mirror(self):
        cfg = KafkaConfig(
            bootstrap_servers="k1:9092",
            bootstrap_servers_mirror="k2:9092",
        )
        assert cfg.bootstrap_servers == "k1:9092"
        assert cfg.bootstrap_servers_mirror == "k2:9092"


class TestSimulationConfig:
    """SimulationConfig 数据类测试。"""

    def test_defaults(self):
        cfg = SimulationConfig()
        assert cfg.target_drones == 10
        assert cfg.sim_center_lat == 31.315
        assert cfg.sim_center_lon == 120.665
        assert cfg.sim_radius_m == 800.0
        assert cfg.cruise_speed == 30.0


class TestAppConfig:
    """AppConfig 嵌套数据类测试。"""

    def test_default_construction(self):
        cfg = AppConfig()
        assert cfg.env == "dev"
        assert cfg.log_level == "INFO"
        assert isinstance(cfg.redis, RedisConfig)
        assert isinstance(cfg.kafka, KafkaConfig)
        assert isinstance(cfg.simulation, SimulationConfig)

    def test_load_config_basic(self, mock_env):
        """load_config 应该能成功加载（从 env.py fallback）。"""
        cfg = load_config()
        assert isinstance(cfg, AppConfig)
        assert cfg.redis.host != "127.0.0.1"  # mock_env 设置了 test-redis.local
        assert cfg.kafka.bootstrap_servers != "127.0.0.1:9092"

    def test_get_config_singleton(self, mock_env):
        """get_config 应该返回缓存的同一实例。"""
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_reload_config(self, mock_env):
        """reload_config 应该清除缓存并重新加载。"""
        cfg1 = get_config()
        cfg2 = reload_config()
        assert cfg1 is not cfg2
