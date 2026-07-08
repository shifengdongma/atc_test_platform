# -*- coding: utf-8 -*-
"""测试 validators.py — 数据校验功能"""

import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from validators import (
    validate_telemetry,
    validate_redis_route,
    validate_airspace,
    validate_scenario,
    validate_telemetry_batch,
)


class TestValidateTelemetry:
    """遥测数据校验。"""

    def test_valid_telemetry(self, sample_telemetry):
        ok, errors = validate_telemetry(sample_telemetry)
        assert ok, f"合法遥测不应报错: {errors}"
        assert len(errors) == 0

    def test_invalid_longitude(self, sample_telemetry):
        sample_telemetry["longitude"] = 999.0
        ok, errors = validate_telemetry(sample_telemetry)
        assert not ok
        assert len(errors) > 0

    def test_invalid_latitude(self, sample_telemetry):
        sample_telemetry["latitude"] = -999.0
        ok, errors = validate_telemetry(sample_telemetry)
        assert not ok

    def test_invalid_operating_status(self, sample_telemetry):
        sample_telemetry["operatingStatus"] = 99
        ok, errors = validate_telemetry(sample_telemetry)
        assert not ok

    def test_missing_uid(self):
        ok, errors = validate_telemetry({"longitude": 120.0, "latitude": 31.0})
        assert not ok

    def test_empty_uid(self):
        ok, errors = validate_telemetry({
            "uniqueProductIdentificationCode": "",
            "longitude": 120.0, "latitude": 31.0,
            "geodeticAltitude": 100.0, "operatingStatus": 2,
            "timestamp": 1000.0,
        })
        assert not ok


class TestValidateRedisRoute:
    """Redis 航线数据校验。"""

    def test_valid_route(self, sample_redis_route):
        ok, errors = validate_redis_route(sample_redis_route)
        assert ok, f"合法航线不应报错: {errors}"
        assert len(errors) == 0

    def test_invalid_segment_lon(self, sample_redis_route):
        sample_redis_route["flightPlanList"][0]["routeList"][0]["segmentStartLon"] = 999.0
        ok, errors = validate_redis_route(sample_redis_route)
        assert not ok

    def test_missing_flight_plan_list(self):
        ok, errors = validate_redis_route({"uniqueProductIdentificationCode": "UAV_001"})
        assert not ok

    def test_empty_route_list(self):
        ok, errors = validate_redis_route({
            "uniqueProductIdentificationCode": "UAV_001",
            "flightPlanList": [{
                "flightPlanId": 1, "planTakeoffTime": 1000.0, "planLandTime": 2000.0,
                "flightTaskId": 1, "flightTaskName": "test",
                "routeList": [],
            }],
        })
        assert not ok


class TestValidateScenario:
    """场景文件校验。"""

    def test_valid_scenario(self, sample_scenario):
        ok, errors = validate_scenario(sample_scenario)
        assert ok, f"合法场景不应报错: {errors}"

    def test_bad_segment_in_scenario(self, sample_scenario):
        sample_scenario["planTemplate"]["flightPlanList"][0]["routeList"][0]["type"] = 99
        ok, errors = validate_scenario(sample_scenario)
        assert not ok


class TestValidateBatch:
    """批量遥测校验。"""

    def test_batch_mixed(self, sample_telemetry):
        bad = dict(sample_telemetry)
        bad["longitude"] = 999.0
        passed, failed, errors = validate_telemetry_batch([sample_telemetry, bad])
        assert passed == 1
        assert failed == 1
        assert len(errors) == 1
