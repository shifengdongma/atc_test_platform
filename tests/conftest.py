# -*- coding: utf-8 -*-
"""pytest 共享 fixtures 和 mock 工具"""

import sys
import os
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

# 公共模块路径（database/ common/ 已从 utm_simulator/ 移出到项目根目录）
_database_path = os.path.join(_root, '..', 'database')
_common_path = os.path.join(_root, '..', 'common')
for _p in (_database_path, _common_path):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Mock fixtures ──────────────────────────────────────────────────

@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Mock RedisClient 用于单元测试。"""
    with patch("redis_client.RedisClient") as mock_cls:
        client = MagicMock()
        client.client = MagicMock()  # 模拟已连接
        client.hgetall.return_value = {}
        client.hset.return_value = True
        client.hget.return_value = None
        client.get_value_by_key.return_value = None
        mock_cls.return_value = client
        yield client


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Mock KafkaProducerClient 用于单元测试。"""
    with patch("kafka_proc.KafkaProducerClient") as mock_cls:
        producer = MagicMock()
        producer.is_connected.return_value = True
        producer.send_bulk.return_value = None
        mock_cls.return_value = producer
        yield producer


@pytest.fixture
def mock_kafka_consumer() -> MagicMock:
    """Mock KafkaConsumerClient 用于单元测试。"""
    with patch("kafka_proc.KafkaConsumerClient") as mock_cls:
        consumer = MagicMock()
        consumer.poll.return_value = []
        mock_cls.return_value = consumer
        yield consumer


@pytest.fixture
def mock_env(monkeypatch) -> None:
    """设置模拟的 env.py 环境变量。"""
    monkeypatch.setattr("env.redis_ip", "test-redis.local", raising=False)
    monkeypatch.setattr("env.redis_port", "6379", raising=False)
    monkeypatch.setattr("env.redis_password", "testpass", raising=False)
    monkeypatch.setattr("env.kafka_url", "test-kafka.local:9092", raising=False)
    monkeypatch.setattr("env.kafka_url2", "", raising=False)


# ── Sample data fixtures ───────────────────────────────────────────

@pytest.fixture
def sample_route_segment() -> Dict[str, Any]:
    """标准航段样本。"""
    return {
        "sequence": 0,
        "type": 2,
        "segmentStartLon": 120.665,
        "segmentStartLat": 31.315,
        "segmentEndLon": 120.675,
        "segmentEndLat": 31.325,
        "segmentStartHeight": 100.0,
        "segmentEndHeight": 200.0,
        "segmentProtectHeight": 50.0,
        "segmentProtectHeightType": 1,
        "segmentWidth": 100.0,
    }


@pytest.fixture
def sample_redis_route(sample_route_segment) -> Dict[str, Any]:
    """标准 Redis 航线样本（单机单计划）。"""
    return {
        "uniqueProductIdentificationCode": "UAV_00001",
        "flightPlanList": [{
            "flightPlanId": 1,
            "planTakeoffTime": 1700000000.0,
            "planLandTime": 1700003600.0,
            "flightTaskId": 1,
            "flightTaskName": "单元测试",
            "routeList": [sample_route_segment],
        }],
    }


@pytest.fixture
def sample_telemetry() -> Dict[str, Any]:
    """标准遥测消息样本。"""
    return {
        "uniqueProductIdentificationCode": "UAV_00001",
        "realNameRegistrationSign": "TEST_SIGN_001",
        "uasOperationCategory": 1,
        "classification": 1,
        "rpsLocationType": 1,
        "rpsLongitude": 0.0,
        "rpsLatitude": 0.0,
        "rpsAltitude": 0.0,
        "longitude": 120.670,
        "latitude": 31.320,
        "trackAngle": 45.0,
        "speed": 15.0,
        "geodeticAltitude": 150.0,
        "verticalSpeed": 2.5,
        "relativeAltitude": 50.0,
        "ressureAltitude": 148.0,
        "operatingStatus": 2,
        "coordinateSystemType": 0,
        "horizontalAccuracy": 1.0,
        "verticalAccuracy": 1.0,
        "speedAccuracy": 1.0,
        "timestamp": 1700000100000.0,
        "timestampAccuracy": 0,
        "sourceType": 1,
        "active": 1,
        "addInf": {},
    }


@pytest.fixture
def sample_scenario(sample_telemetry) -> Dict[str, Any]:
    """标准场景文件样本。"""
    return {
        "_meta": {
            "name": "测试场景",
            "description": "用于单元测试的场景",
            "type": "test",
            "default_drone_count": 1,
        },
        "task": {
            "taskName": "测试任务",
            "taskPurpose": "验证数据流",
            "taskType": "TEST",
            "taskDescription": "单元测试用",
        },
        "uasList": [{
            "uniqueProductIdentificationCode": "UAV_00001",
            "realNameRegistrationSign": "TEST_SIGN_001",
        }],
        "planTemplate": {
            "flightPlanList": [{
                "flightPlanId": 1,
                "planTakeoffTime": 1700000000.0,
                "planLandTime": 1700003600.0,
                "flightTaskId": 1,
                "flightTaskName": "测试",
                "routeList": [{
                    "sequence": 0, "type": 2,
                    "segmentStartLon": 120.665, "segmentStartLat": 31.315,
                    "segmentEndLon": 120.675, "segmentEndLat": 31.325,
                    "segmentStartHeight": 100.0, "segmentEndHeight": 200.0,
                    "segmentProtectHeight": 50.0, "segmentProtectHeightType": 1,
                    "segmentWidth": 100.0,
                }],
            }],
        },
    }
