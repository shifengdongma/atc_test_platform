# -*- coding: utf-8 -*-
"""
数据校验模块

基于 Pydantic 的数据校验器，对所有注入 Redis/Kafka 的数据进行格式校验。
校验失败时返回错误列表，不直接阻断（可在调用方根据错误列表决定策略）。

用法:
    from validators import validate_telemetry, validate_redis_route, validate_scenario

    ok, errors = validate_telemetry(sample_data)
    if not ok:
        for err in errors:
            logger.warning("遥测数据校验失败: %s", err)
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError


# ── Pydantic 校验模型 ───────────────────────────────────────────────

class RouteSegmentValidator(BaseModel):
    """航段数据校验模型。

    对应 schemas.RouteSegmentDict，字段范围以算法对接文档为准。
    """
    sequence: int = Field(ge=0, description="航段序号，从 0 开始")
    type: int = Field(ge=1, le=3, description="航段类型: 1=起飞, 2=巡航, 3=降落")
    segmentStartLon: float = Field(ge=-180.0, le=180.0, description="起点经度")
    segmentStartLat: float = Field(ge=-90.0, le=90.0, description="起点纬度")
    segmentEndLon: float = Field(ge=-180.0, le=180.0, description="终点经度")
    segmentEndLat: float = Field(ge=-90.0, le=90.0, description="终点纬度")
    segmentStartHeight: float = Field(ge=-500.0, le=20000.0, description="起点高度 (m)")
    segmentEndHeight: float = Field(ge=-500.0, le=20000.0, description="终点高度 (m)")
    segmentProtectHeight: float = Field(ge=0.0, le=5000.0, description="保护区高度 (m)")
    segmentProtectHeightType: int = Field(ge=0, le=10, description="保护区高度类型")
    segmentWidth: float = Field(ge=0.0, le=10000.0, description="航段宽度 (m)")


class FlightPlanEntryValidator(BaseModel):
    """飞行计划条目校验模型。"""
    flightPlanId: int = Field(ge=0, description="飞行计划 ID")
    planTakeoffTime: float = Field(ge=0.0, description="计划起飞时间")
    planLandTime: float = Field(ge=0.0, description="计划降落时间")
    flightTaskId: int = Field(ge=0, description="关联飞行任务 ID")
    flightTaskName: str = Field(min_length=1, max_length=256, description="飞行任务名称")
    routeList: List[dict] = Field(min_length=1, description="航段列表（至少 1 段）")


class DroneRouteValidator(BaseModel):
    """单机航线数据校验模型（Redis BIZ_DATA:UAV_ROUTE value）。"""
    uniqueProductIdentificationCode: str = Field(
        min_length=1, max_length=64, description="无人机唯一产品识别码"
    )
    flightPlanList: List[dict] = Field(min_length=1, description="飞行计划列表")


class TelemetryValidator(BaseModel):
    """遥测数据校验模型（Kafka uav_runtime_data 消息）。

    字段范围以算法对接文档"无人机实时运行数据"为准。
    """
    uniqueProductIdentificationCode: str = Field(min_length=1, max_length=64)
    realNameRegistrationSign: str = Field(default="", max_length=128)
    uasOperationCategory: int = Field(default=1, ge=1, le=2)
    classification: int = Field(default=1, ge=1, le=5)
    rpsLocationType: int = Field(default=1, ge=0, le=10)
    rpsLongitude: float = Field(default=0.0, ge=-180.0, le=180.0)
    rpsLatitude: float = Field(default=0.0, ge=-90.0, le=90.0)
    rpsAltitude: float = Field(default=0.0, ge=-500.0, le=20000.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    latitude: float = Field(ge=-90.0, le=90.0)
    trackAngle: float = Field(default=0.0, ge=0.0, le=360.0)
    speed: float = Field(default=0.0, ge=0.0, le=500.0)
    geodeticAltitude: float = Field(ge=-500.0, le=20000.0)
    verticalSpeed: float = Field(default=0.0, ge=-100.0, le=100.0)
    relativeAltitude: float = Field(default=0.0, ge=-500.0, le=20000.0)
    ressureAltitude: float = Field(default=0.0, ge=-500.0, le=20000.0)
    operatingStatus: int = Field(ge=0, le=5)
    coordinateSystemType: int = Field(default=0, ge=0, le=10)
    horizontalAccuracy: float = Field(default=1.0, ge=0.0, le=1000.0)
    verticalAccuracy: float = Field(default=1.0, ge=0.0, le=1000.0)
    speedAccuracy: float = Field(default=1.0, ge=0.0, le=100.0)
    timestamp: float = Field(ge=0.0)
    timestampAccuracy: int = Field(default=0, ge=0, le=1000)
    sourceType: int = Field(default=1, ge=1, le=2)
    active: int = Field(default=1, ge=0, le=1)
    addInf: dict = Field(default_factory=dict)


class AirspaceValidator(BaseModel):
    """空域/禁飞区数据校验模型。"""
    airspaceId: str = Field(min_length=1, max_length=64)
    spcNo: str = Field(default="", max_length=128)
    name: str = Field(default="", max_length=256)
    typeCode: int = Field(default=1, ge=0, le=100)
    status: int = Field(default=1, ge=0, le=1)
    times: List[dict] = Field(default_factory=list)
    usagePurpose: str = Field(default="", max_length=256)
    lowestHeight: float = Field(default=0.0, ge=-500.0, le=20000.0)
    highestHeight: float = Field(default=500.0, ge=-500.0, le=20000.0)
    capacity: int = Field(default=0, ge=0)
    monitorAbility: int = Field(default=1, ge=0, le=10)
    polygon: dict = Field(default_factory=dict)


class ScenarioMetaValidator(BaseModel):
    """场景文件元数据校验。"""
    name: str = Field(default="", max_length=256)
    description: str = Field(default="", max_length=1024)
    type: str = Field(default="", max_length=64)
    default_drone_count: int = Field(default=1, ge=1, le=5000)


# ── 便捷校验函数 ────────────────────────────────────────────────────

def _format_pydantic_errors(e: PydanticValidationError) -> List[str]:
    """将 Pydantic ValidationError 转为人类可读的错误信息列表。"""
    messages = []
    for err in e.errors():
        loc = " → ".join(str(part) for part in err["loc"])
        msg = f"{loc}: {err['msg']}"
        messages.append(msg)
    return messages


def validate_redis_route(data: dict) -> Tuple[bool, List[str]]:
    """校验单机航线数据（Redis BIZ_DATA:UAV_ROUTE value）。

    Args:
        data: 航线数据字典，含 uniqueProductIdentificationCode 和 flightPlanList

    Returns:
        (是否通过校验, 错误信息列表)
    """
    errors: List[str] = []

    # 1. 顶层结构校验
    try:
        DroneRouteValidator(**data)
    except PydanticValidationError as e:
        errors.extend(_format_pydantic_errors(e))
        return False, errors

    # 2. 逐条飞行计划校验
    for pi, plan in enumerate(data.get("flightPlanList", [])):
        try:
            FlightPlanEntryValidator(**plan)
        except PydanticValidationError as e:
            for msg in _format_pydantic_errors(e):
                errors.append(f"flightPlanList[{pi}]: {msg}")

        # 3. 逐段航段校验
        for si, seg in enumerate(plan.get("routeList", [])):
            try:
                RouteSegmentValidator(**seg)
            except PydanticValidationError as e:
                for msg in _format_pydantic_errors(e):
                    errors.append(f"flightPlanList[{pi}].routeList[{si}]: {msg}")

    return len(errors) == 0, errors


def validate_telemetry(data: dict) -> Tuple[bool, List[str]]:
    """校验单条遥测数据（Kafka uav_runtime_data 消息）。

    Args:
        data: 遥测数据字典

    Returns:
        (是否通过校验, 错误信息列表)
    """
    try:
        TelemetryValidator(**data)
        return True, []
    except PydanticValidationError as e:
        return False, _format_pydantic_errors(e)


def validate_airspace(data: dict) -> Tuple[bool, List[str]]:
    """校验单条空域/禁飞区数据（Redis BIZ_DATA:AIRSPACE value）。

    Args:
        data: 空域数据字典

    Returns:
        (是否通过校验, 错误信息列表)
    """
    try:
        AirspaceValidator(**data)
        return True, []
    except PydanticValidationError as e:
        return False, _format_pydantic_errors(e)


def validate_scenario(data: dict) -> Tuple[bool, List[str]]:
    """校验整个场景文件（如 mock/kafka_data.json）。

    检查顶层元数据、无人机列表和飞行计划模板。

    Args:
        data: 场景数据字典

    Returns:
        (是否通过校验, 错误信息列表)
    """
    errors: List[str] = []

    # 元数据校验
    meta = data.get("_meta", {})
    if meta:
        try:
            ScenarioMetaValidator(**meta)
        except PydanticValidationError as e:
            errors.extend(_format_pydantic_errors(e))

    # 校验 uasList（无人机列表）
    uas_list = data.get("uasList", [])
    for i, uas in enumerate(uas_list):
        uid = uas.get("uniqueProductIdentificationCode", f"<unknown #{i}>")
        try:
            if not isinstance(uas.get("uniqueProductIdentificationCode"), str) or \
               len(uas.get("uniqueProductIdentificationCode", "")) < 1:
                errors.append(f"uasList[{i}]: uniqueProductIdentificationCode 缺失或无效")
        except Exception:
            errors.append(f"uasList[{i}]: 结构异常")

    # 校验 planTemplate 中的 flightPlanList
    plan_template = data.get("planTemplate", {})
    flight_plans = plan_template.get("flightPlanList", [])
    for pi, plan in enumerate(flight_plans):
        try:
            FlightPlanEntryValidator(**plan)
        except PydanticValidationError as e:
            for msg in _format_pydantic_errors(e):
                errors.append(f"planTemplate.flightPlanList[{pi}]: {msg}")

        for si, seg in enumerate(plan.get("routeList", [])):
            try:
                RouteSegmentValidator(**seg)
            except PydanticValidationError as e:
                for msg in _format_pydantic_errors(e):
                    errors.append(f"planTemplate.flightPlanList[{pi}].routeList[{si}]: {msg}")

    return len(errors) == 0, errors


def validate_telemetry_batch(data_list: List[dict]) -> Tuple[int, int, List[str]]:
    """批量校验遥测数据，返回 (通过数, 失败数, 汇总错误)。

    Args:
        data_list: 遥测数据字典列表

    Returns:
        (pass_count, fail_count, 错误信息列表)
    """
    errors: List[str] = []
    passed = 0
    failed = 0

    for i, data in enumerate(data_list):
        ok, errs = validate_telemetry(data)
        if ok:
            passed += 1
        else:
            failed += 1
            for err in errs:
                errors.append(f"batch[{i}]: {err}")

    return passed, failed, errors
