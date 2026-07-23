# -*- coding: utf-8 -*-
"""
UTM 仿真系统数据模型类型定义

使用 TypedDict 定义所有 Redis/Kafka JSON 数据的结构，
替代项目中随处可见的 Dict[str, Any]，方便 AI 工具和 IDE 类型推导。

数据格式以 _source/算法对接 2026030301.md 为准。

用法:
    from schemas import DroneRouteDict, TelemetryDict, RouteSegmentDict
    route: DroneRouteDict = {"uniqueProductIdentificationCode": "UAV_001", ...}
"""

from __future__ import annotations

from typing import List, Optional, TypedDict


# ── 航线相关 ────────────────────────────────────────────────────────

class RouteSegmentDict(TypedDict, total=False):
    """飞行计划 routeList 中的单个航段（算法对接格式）。

    对应 Redis BIZ_DATA:UAV_ROUTE hash value 中 flightPlanList[].routeList[] 条目。
    """
    sequence: int                    # 航段序号，从 0 开始
    type: int                        # 航段类型: 1=起飞, 2=巡航, 3=降落
    segmentStartLon: float           # 航段起点经度 (-180~180)
    segmentStartLat: float           # 航段起点纬度 (-90~90)
    segmentEndLon: float             # 航段终点经度
    segmentEndLat: float             # 航段终点纬度
    segmentStartHeight: float        # 航段起点高度 (m)
    segmentEndHeight: float          # 航段终点高度 (m)
    segmentProtectHeight: float      # 保护区高度 (m)
    segmentProtectHeightType: int    # 保护区高度类型
    segmentWidth: float              # 航段宽度 (m)


class FlightPlanEntryDict(TypedDict, total=False):
    """单条飞行计划（flightPlanList 中的一个条目）。"""
    flightPlanId: int                # 飞行计划 ID
    planTakeoffTime: float           # 计划起飞时间 (Unix timestamp, 秒)
    planLandTime: float              # 计划降落时间 (Unix timestamp, 秒)
    flightTaskId: int                # 关联飞行任务 ID
    flightTaskName: str              # 飞行任务名称
    routeList: List[RouteSegmentDict]  # 航段列表


class DroneRouteDict(TypedDict, total=False):
    """Redis BIZ_DATA:UAV_ROUTE Hash 中单个 field 的 value（单机全部飞行计划）。

    key 为无人机 UID（如 "UAV_00001"），value 为此结构的 JSON 字符串。
    """
    uniqueProductIdentificationCode: str   # 无人机唯一产品识别码 (UID)
    flightPlanList: List[FlightPlanEntryDict]  # 飞行计划列表


# ── 遥测相关 ────────────────────────────────────────────────────────

class TelemetryDict(TypedDict, total=False):
    """Kafka uav_runtime_data 主题中的单条遥测消息。

    对应算法对接文档中"无人机实时运行数据"格式，约 22 个字段。
    """
    uniqueProductIdentificationCode: str  # 无人机 UID
    realNameRegistrationSign: str         # 实名登记标识
    uasOperationCategory: int             # 运行类别 (1=视距内, 2=视距外)
    classification: int                   # 航空器分类 (1=微型, 2=轻型, 3=小型, 4=中型, 5=大型)
    rpsLocationType: int                  # 远程驾驶站位置类型
    rpsLongitude: float                   # 远程驾驶站经度
    rpsLatitude: float                    # 远程驾驶站纬度
    rpsAltitude: float                    # 远程驾驶站高度
    longitude: float                      # 当前经度 (-180~180)
    latitude: float                       # 当前纬度 (-90~90)
    trackAngle: float                     # 航向角 (0~360°, 正北为 0)
    speed: float                          # 地速 (m/s, 0~500)
    geodeticAltitude: float               # 大地高 (m, -500~20000)
    verticalSpeed: float                  # 垂直速度 (m/s, 正为上升)
    relativeAltitude: float               # 相对起飞点高度 (m)
    ressureAltitude: float                # 气压高度 (m)
    operatingStatus: int                  # 运行状态 (0=未起飞, 1=起飞, 2=飞行中, 3=悬停, 4=降落, 5=已降落)
    coordinateSystemType: int             # 坐标系类型
    horizontalAccuracy: float             # 水平精度 (m)
    verticalAccuracy: float               # 垂直精度 (m)
    speedAccuracy: float                  # 速度精度 (m/s)
    timestamp: float                      # 时间戳 (毫秒)
    timestampAccuracy: int                # 时间精度
    sourceType: int                       # 数据源类型 (1=无人机, 2=ADS-B)
    active: int                           # 是否活跃 (0=已降落/无效, 1=活跃飞行中)
    addInf: dict                          # 附加信息


# ── Trace 追踪相关 ──────────────────────────────────────────────────

class TraceMessageDict(TypedDict, total=False):
    """Kafka uav_runtime_trace 主题中的消息（下游 UTM 系统发布的预测结果）。"""
    redisKey: str                        # 对应 Redis 中存储预测结果的 key
    redis_key: str                       # 同上（兼容大小写差异）
    timestamp: float                     # 时间戳


class TracePredictionDict(TypedDict, total=False):
    """uav_runtime_trace → Redis 回查数据的单条预测记录。"""
    uniqueProductIdentificationCode: str  # 无人机 UID
    timestamp: float                     # 预测时间戳
    longitude: float                     # 预测经度
    latitude: float                      # 预测纬度
    geodeticAltitude: float              # 预测高度
    speed: float                         # 预测速度
    trackAngle: float                    # 预测航向


# ── 空域相关 ────────────────────────────────────────────────────────

class AirspaceDict(TypedDict, total=False):
    """Redis BIZ_DATA:AIRSPACE Hash 中单个 field 的 value（空域/禁飞区数据）。"""
    airspaceId: str                      # 空域唯一标识
    spcNo: str                           # 空域编号
    name: str                            # 空域名称
    typeCode: int                        # 空域类型代码
    status: int                          # 状态 (1=激活, 0=非激活)
    times: List[dict]                    # 时间段列表
    usagePurpose: str                    # 使用目的
    lowestHeight: float                  # 最低高度 (m)
    highestHeight: float                 # 最高高度 (m)
    capacity: int                        # 容量
    monitorAbility: int                  # 监控能力
    polygon: dict                        # GeoJSON Polygon 几何对象


# ── 仿真控制相关 ────────────────────────────────────────────────────

class SimulationStatusDict(TypedDict, total=False):
    """仿真运行状态（API 返回和内部状态）。"""
    running: bool                        # 是否运行中
    mode: str                            # 运行模式 (dynamic/replay/plan)
    active_drones: int                   # 活跃无人机数量
    kafka_msg_per_sec: int               # Kafka 每秒发送消息数
    uptime_sec: int                      # 运行时长 (秒)
    errors: int                          # 累计错误数
    redis_connected: bool                # Redis 连接状态
    kafka_connected: bool                # Kafka 连接状态
    logs: List[str]                      # 最近日志列表


# ── 辅助类型 ────────────────────────────────────────────────────────

class ScenarioDict(TypedDict, total=False):
    """场景文件（如 mock/kafka_data.json）的顶层结构。

    实际场景文件中为 TelemetryDict 的列表；此类型描述通用场景结构。
    """
    _meta: dict                          # 元数据（名称、描述、默认架数等）
    task: dict                           # 飞行任务信息
    uasList: List[dict]                  # 无人机列表
    planTemplate: dict                   # 飞行计划模板
