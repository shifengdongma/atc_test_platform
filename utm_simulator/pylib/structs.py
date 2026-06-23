"""
pylib/structs.py
ctypes 结构定义，必须与 src/utm_core.h 保持二进制级别的严格一致。
"""
import ctypes

from enum import IntEnum

class UAVClassification(IntEnum):
    MICRO  = 0
    LIGHT  = 1
    SMALL  = 2
    MEDIUM = 3
    LARGE  = 4



class GeoPoint(ctypes.Structure):
    _fields_ = [("lon", ctypes.c_double), ("lat", ctypes.c_double), ("alt", ctypes.c_double)]

class Vec3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double), ("z", ctypes.c_double)]

class TelemetryData(ctypes.Structure):
    _fields_ = [
        ("uid", ctypes.c_char * 64),
        ("classification", ctypes.c_int),  # UAVClassification 枚举值
        ("location", GeoPoint),
        ("velocity", Vec3),
        ("speed", ctypes.c_double),
        ("heading", ctypes.c_double),
        ("verticalSpeed", ctypes.c_double),  # 新增垂直速度字段
        ("longitudinal_threshold", ctypes.c_double), # 
        ("lateral_threshold", ctypes.c_double),      #
        ("v_threshold", ctypes.c_double),
        ("timestamp", ctypes.c_double),
        ("operatingStatus", ctypes.c_int), # 运营状态 (预留字段)
        ("relativeAltitude", ctypes.c_double),
        ("ressureAltitude", ctypes.c_double),
        ("coordinateSystemType", ctypes.c_int),
        ("verticalAccuracy", ctypes.c_int),
        ("horizontalAccuracy", ctypes.c_int),
        ("speedAccuracy", ctypes.c_int),
        ("timestampAccuracy", ctypes.c_int),

    ]

class Waypoint(ctypes.Structure):
    _fields_ = [("point", GeoPoint), 
                ("eta", ctypes.c_double), 
                ("stay_duration", ctypes.c_double),
                ("segmentWidth", ctypes.c_double),
                ("segmentProtectHeightType", ctypes.c_int),
                ("segmentVerticalleight", ctypes.c_double)]

class AreaGeometry(ctypes.Structure):
    _fields_ = [("vertices", ctypes.POINTER(GeoPoint)), ("vertex_count", ctypes.c_int), 
                ("min_alt", ctypes.c_double), ("max_alt", ctypes.c_double)]

# 模拟 C union
class PlanDataUnion(ctypes.Union):
    _fields_ = [
        ("traj", type("TrajStruct", (ctypes.Structure,), {"_fields_": [("wps", ctypes.POINTER(Waypoint)), ("count", ctypes.c_int)]})),
        ("area", AreaGeometry)
    ]



class AircraftProfile(ctypes.Structure):
    _fields_ = [
        ("uid", ctypes.c_char * 64),
        ("classification", ctypes.c_int),  # UAVClassification 枚举值
        ("longitudinal_threshold", ctypes.c_double), # [修改]
        ("lateral_threshold", ctypes.c_double),      # [修改]
        ("v_threshold", ctypes.c_double),
        ("max_speed", ctypes.c_double)
    ]

class FlightPlan(ctypes.Structure):
    _fields_ = [
        ("task_name", ctypes.c_char * 64),
        ("task_id", ctypes.c_int64),
        ("plan_id", ctypes.c_int64),
        ("type", ctypes.c_int), # 0=Traj, 1=Poly
        ("start_time", ctypes.c_double),
        ("end_time", ctypes.c_double),
        ("priority", ctypes.c_int),
        ("aircraft", AircraftProfile),
        ("data", PlanDataUnion)
    ]


# pylib/structs.py

class RuleThreshold(ctypes.Structure):
    _fields_ = [
        ("rule_id", ctypes.c_char * 64),
        ("longitudinal", ctypes.c_double),
        ("transverse", ctypes.c_double),
        ("vertical", ctypes.c_double),
        ("duration", ctypes.c_double),
        ("enabled", ctypes.c_bool)
    ]

# 定义枚举映射
NFZ_TYPE_MAP = {
    "controlled": 0, "restrictedUse": 1, "fusion": 2, "noDrone": 3,
    "limited": 4, "danger": 5, "segregated": 6, "suppression": 7
}
SIZE_MAP = {"LIGHT": 1, "SMALL": 2, "MEDIUM": 3, "LARGE": 4} # Micro=0, 假设 Light=1

# 辅助映射字典
NFZ_STATUS_MAP = {
    "NFZ_STATUS_PERMANENT": 0,
    "NFZ_STATUS_TEMPORARY_ACTIVE": 1,
    "NFZ_STATUS_INACTIVE": 2
}

class SystemConfig(ctypes.Structure):
    _fields_ = [
        ("collision_alert", RuleThreshold * 5),
        ("collision_warn", RuleThreshold * 5),
        ("airspace_alert", (RuleThreshold * 5) * 8), # [8][5]
        ("airspace_warn", (RuleThreshold * 5) * 8),
        ("deviation_alert", RuleThreshold),
        ("deviation_warn", RuleThreshold)
    ]


class DynamicNoFlyZone(ctypes.Structure):
    _fields_ = [
        ("uid", ctypes.c_char * 64),
        ("type", ctypes.c_int),      # NFZType
        ("status", ctypes.c_int),    # <--- 新增: NFZStatus
        ("geometry", AreaGeometry),
        ("start_time", ctypes.c_double),
        ("end_time", ctypes.c_double),
        ("priority", ctypes.c_int),
        ("reason", ctypes.c_char * 64)
    ]


class TelemetrySnapshot(ctypes.Structure):
    _fields_ = [
        ("location", GeoPoint),
        ("timestamp", ctypes.c_double),
        
        ("h_accuracy", ctypes.c_int),
        ("v_accuracy", ctypes.c_int),
        ("speed_accuracy", ctypes.c_int),
        
        # [修改] 对应 C++ 的变化
        ("speed", ctypes.c_double),
        ("heading", ctypes.c_double),
        ("verticalSpeed", ctypes.c_double)
    ]


class AircraftStateInput(ctypes.Structure):
    _fields_ = [
        ("uid", ctypes.c_char * 64),
        ("current", TelemetryData),
        ("history", ctypes.POINTER(TelemetrySnapshot)),
        ("history_count", ctypes.c_int)
    ]




class TrajectoryPoint(ctypes.Structure):
    _fields_ = [
        ("time", ctypes.c_double),
        ("pos", GeoPoint),
        ("vel", Vec3),
        # [关键修复] 补全缺失字段，严格对齐 C++ 结构体 (utm_core.h)
        ("longitude", ctypes.c_double),
        ("latitude", ctypes.c_double),
        ("trackAngle", ctypes.c_double),
        ("speed", ctypes.c_double),
        ("Altitude", ctypes.c_double),      # 注意 C++ 中是大写
        ("verticalSpeed", ctypes.c_double),
        ("operatingStatus", ctypes.c_int), # 运营状态 (预留字段)
        ("uid", ctypes.c_char * 64), # 飞机唯一标识符
        ("classification", ctypes.c_int), # 机型名称
        ("longitudinal_threshold", ctypes.c_double), # [修改] 纵向保护阈值 (沿着速度方向)
        ("lateral_threshold", ctypes.c_double), # [修改] 横向保护阈值 (垂直于速度方向)
        ("v_threshold", ctypes.c_double),       # 垂直保护区半径 (meters)
        ("relativeAltitude", ctypes.c_double),
        ("ressureAltitude", ctypes.c_double),
        ("coordinateSystemType", ctypes.c_int),
        ("verticalAccuracy", ctypes.c_int),
        ("horizontalAccuracy", ctypes.c_int),
        ("speedAccuracy", ctypes.c_int),
        ("timestampAccuracy", ctypes.c_int)




    ]





# 告警类型字典
ALARM_TYPE_MAP = {
    "ALARM_TYPE_COLLISION_ALERT": 0,    # 短期飞机碰撞告警
    "ALARM_TYPE_COLLISION_WARN": 1,     # 短期飞机碰撞预警
    "ALARM_TYPE_AIRSPACE_ALERT": 2,  # 短期空域入侵告警
    "ALARM_TYPE_AIRSPACE_WARN": 3,   # 短期空域入侵预警
    "ALARM_TYPE_DEVIATION_ALERT": 4,  # 偏离航线告警
    "ALARM_TYPE_DEVIATION_WARN": 5,  # 偏离航线预警
    "ALARM_TYPE_STRATEGIC_AIRSPACE_WARN": 6,  # 战略空域入侵预警（也是预估）
    "ALARM_TYPE_STRATEGIC_COLLISION_WARN": 7,   # 战略碰撞预警（也是预估）
    "ALARM_TYPE_ESTIMATE_AIRSPACE_WARN": 8,  # 预估空域入侵预警
    "ALARM_TYPE_ESTIMATE_COLLISION_WARN": 9   # 预估碰撞预警

}


class ConflictInfo(ctypes.Structure):
    _fields_ = [
        ("alarm_id", ctypes.c_char * 64),
        ("type", ctypes.c_int),          # 0:Coll, 1:Air, 2:Dev, 3:Strat
        ("conflict_time", ctypes.c_double),
        ("conflict_end_time", ctypes.c_double),
        ("rule_id", ctypes.c_char * 64),
        ("status", ctypes.c_char * 16),
        ("subject_uid", ctypes.c_char * 64),
        ("subject_task_id",ctypes.c_int64)  ,
        ("subject_plan_id", ctypes.c_int64),
        ("route_id", ctypes.c_int),
        ("segment_index", ctypes.c_int),

        ("subject_location",GeoPoint),

        ("object_uid", ctypes.c_char * 64),
        ("object_task_id",ctypes.c_int64)  ,
        ("object_plan_id", ctypes.c_int64),
        ("object_location", GeoPoint),
        ("conflict_location", GeoPoint),
        ("separation", ctypes.c_double),
        ("sep_lon", ctypes.c_double),
        ("sep_lat", ctypes.c_double),
        ("sep_v", ctypes.c_double),
        
        ("limit_long", ctypes.c_double),
        ("limit_lat", ctypes.c_double),
        ("limit_vert", ctypes.c_double),
        
        ("metadata", ctypes.c_char * 128),
        ("is_critical", ctypes.c_bool)
    ]


class DeviationInfo(ctypes.Structure):
    _fields_ = [
        ("is_deviated", ctypes.c_bool),
        ("deviation_val", ctypes.c_double),
        ("msg", ctypes.c_char * 64),
        ("alarm_id", ctypes.c_char * 64),
        ("status", ctypes.c_char * 16),
        ("rule_id", ctypes.c_char * 64),
        ("subject_uid", ctypes.c_char * 64),
        ("subject_location", GeoPoint),
        ("deviated_time", ctypes.c_double),
        ("task_id",ctypes.c_int64),
        ("plan_id", ctypes.c_int64),
        ("route_id", ctypes.c_int),
        ("segment_index", ctypes.c_int),
        ("type", ctypes.c_int)  # AlarmType
    ]


class PairwiseDistResult(ctypes.Structure):
    _fields_ = [
        ("min_distance", ctypes.c_double),
        ("time_stamp", ctypes.c_double),
        ("pos_subject", GeoPoint),
        ("vel_subject", Vec3),
        ("pos_object", GeoPoint),
        ("vel_object", Vec3),
        ("success", ctypes.c_bool)
    ]



