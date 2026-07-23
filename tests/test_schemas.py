# -*- coding: utf-8 -*-
"""测试 schemas.py — TypedDict 结构定义"""

import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from schemas import (
    RouteSegmentDict,
    FlightPlanEntryDict,
    DroneRouteDict,
    TelemetryDict,
    TraceMessageDict,
    AirspaceDict,
    SimulationStatusDict,
)


class TestRouteSegmentDict:
    """RouteSegmentDict 结构测试。"""

    def test_minimal_segment(self):
        seg: RouteSegmentDict = {
            "sequence": 0, "type": 2,
            "segmentStartLon": 120.6, "segmentStartLat": 31.3,
            "segmentEndLon": 120.7, "segmentEndLat": 31.4,
            "segmentStartHeight": 100.0, "segmentEndHeight": 200.0,
            "segmentProtectHeight": 50.0, "segmentProtectHeightType": 1,
            "segmentWidth": 100.0,
        }
        assert seg["sequence"] == 0
        assert seg["type"] == 2
        assert len(seg) == 11

    def test_partial_segment(self):
        """TypedDict 支持 partial（total=False）。"""
        seg: RouteSegmentDict = {"sequence": 0}  # type: ignore
        assert seg.get("sequence") == 0
        assert seg.get("type") is None  # 未提供，返回 None


class TestTelemetryDict:
    """TelemetryDict 结构测试。"""

    def test_telemetry_fields(self):
        tel: TelemetryDict = {
            "uniqueProductIdentificationCode": "UAV_00001",
            "longitude": 120.6, "latitude": 31.3,
            "geodeticAltitude": 100.0, "operatingStatus": 2,
            "speed": 15.0, "timestamp": 1000000.0,
            "sourceType": 1,
        }
        assert tel["uniqueProductIdentificationCode"] == "UAV_00001"
        assert tel["operatingStatus"] == 2
        # 默认值字段应返回 None
        assert tel.get("active") is None


class TestDroneRouteDict:
    """DroneRouteDict 结构测试。"""

    def test_drone_route(self):
        route: DroneRouteDict = {
            "uniqueProductIdentificationCode": "UAV_00001",
            "flightPlanList": [],
        }
        assert route["uniqueProductIdentificationCode"] == "UAV_00001"
        assert route["flightPlanList"] == []


class TestSimulationStatusDict:
    """SimulationStatusDict 结构测试。"""

    def test_status_fields(self):
        status: SimulationStatusDict = {
            "running": True,
            "mode": "dynamic",
            "active_drones": 100,
            "redis_msg_per_sec": 100,
            "uptime_sec": 3600,
            "errors": 0,
            "redis_connected": True,
            "kafka_connected": True,
        }
        assert status["running"] is True
        assert status["mode"] == "dynamic"
