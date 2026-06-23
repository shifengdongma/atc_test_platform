#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞行任务创建自动化脚本

功能：
    1. 自动获取 JWT Token（支持缓存，24h 内免重复登录）
    2. 调用 /flight/task/create 接口创建飞行任务
    3. 支持达梦数据库查询验证任务是否成功写入
    4. 关键参数可配置，支持动态时间生成

外部依赖：
    - Jwt_Token_get.py   : 同目录下，提供 get_jwt_token()
    - dmdbclient.py      : 同目录下，提供 DmDbClient
    - requests           : pip install requests
    - dmPython           : 达梦数据库驱动（如启用数据库验证）

调用示例：
    # 快速创建默认任务（单次，3分钟后开始，持续30分钟）
    python 飞行任务创建.py

    # 指定任务名、时间窗口
    python 飞行任务创建.py --task-name "巡检任务" --start-minutes 5 --duration-minutes 60

    # 创建个人运营人的应急任务（需对应任务性质支持应急）
    python 飞行任务创建.py --operator-type 1 --task-type EMERGENCY --task-purpose 14

    # 启用数据库验证
    python 飞行任务创建.py --verify-db

    # 强制使用硬编码默认值（不查库）
    python 飞行任务创建.py --no-db-defaults

    # 批量创建 10 个任务（名称自增）
    python 飞行任务创建.py -n 10 --name-template "压力测试{date}{seq:04d}"

    # 批量创建 100 个任务，间隔 0.2 秒，创建后验证数据库
    python 飞行任务创建.py -n 100 --interval 0.2 --verify-db
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# 将脚本所在目录加入模块搜索路径，确保能导入同目录的 Jwt_Token_get / dmdbclient
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from Jwt_Token_get import get_jwt_token
from dmdbclient import DmDbClient

# ============================ 全局配置 ============================

BASE_URL = "https://dkkgsit-test.testdolphin.com"
API_PATH = "/la-atc-biz-backend/flight/task/create"

# ---------------------------------------------------------------------------
# 飞行任务创建默认参数配置区
# ---------------------------------------------------------------------------
# 所有参数按 /flight/task/create 接口请求体字段顺序排列。
# 可通过直接修改以下常量、命令行传参或外部脚本注入来覆盖。
#
# 外部脚本调用示例：
#   import 飞行任务创建 as ft
#   ft.DEFAULT_OPERATOR["operatorId"] = "12345"
#   ft.DEFAULT_UAV["uavName"] = "新无人机"
#   payload = ft.make_task_payload(task_name="外部调用任务")
# ---------------------------------------------------------------------------

# ---- 00.通用配置 ----
# 批量创建数量（IDE 直接运行时可在此修改默认值）
DEFAULT_COUNT = 1

# ---- 01.taskName ----
# 任务名称由参数传入或按 nameTemplate 自动生成。
# 支持占位符：{date}(MMDD)、{datetime}(MMDDHHMMSS)、{seq}(序号)、{timestamp}
NAME_TEMPLATE = "飞行任务自动化{datetime}{seq:03d}"

# ---- 04~06. 运营人信息（operatorType: 1=个人, 2=组织机构）----
DEFAULT_OPERATOR_TYPE = "2"
DEFAULT_OPERATOR_ID = "1"
DEFAULT_OPERATOR_NAME = "atcAdmin"
DEFAULT_CONTACT = "atcAdmin"
DEFAULT_PHONE_NUMBER = "13812345661"

# ---- 07.uavType ----
DEFAULT_UAV_TYPE = "MICRO"

# ---- 20.uavInfos ----
DEFAULT_UAV = {
    "uavId": "50510186246356992",
    "uavName": "智能巡航无人机7号",
    "uavIdentifyCode": "ZT000000000000000007",
    "policyNumber": "4007093556",
    "insuranceCompany": "中华联合",
    "registrationCode": "EHH0000000007",
    "manufacturer": "科卫泰",
    "uavType": DEFAULT_UAV_TYPE,
    "uavModel": "DT-EVO",
}

# ---- 21.pilots ----
DEFAULT_PILOT = {
    "operatorId": "40633100413255680",
    "operatorName": "wwbcz",
    "idType": "0",
    "operatorIdNumber": "410825199407258824",
    "rplType": "RPL_M",
    "licenseNumber": "HK202604220030021",
    "operatorLicenseValidity": 1848499200000,
}

# ---- 24.flightLines ----
DEFAULT_FLIGHT_LINE = {
    "flightLineName": "起降场yfk起降场1-离场点-航路G00101-G00102-G00103-G00104-起降场算法测试-起降场1-进场点",
    "departureAirportId": "40307655171948544",
    "departureAirportName": "yfk起降场1",
    "departurePointLon": 120.703171,
    "departurePointLat": 31.333761,
    "departurePointHeight": "",
    "takeoffPointLon": 120.717384,
    "takeoffPointLat": 31.338784,
    "takeoffPointHeight": "",
    "arrivalAirportId": "23557376825163776",
    "arrivalAirportName": "算法测试-起降场1",
    "arrivalPointLon": 120.70778,
    "arrivalPointLat": 31.338022,
    "arrivalPointHeight": "",
    "landPointLon": 120.711524,
    "landPointLat": 31.338268,
    "landPointHeight": "",
    "lineSegments": [
        {
            "type": 2,
            "airRouteId": "23560499761315840",
            "airRouteElementId": "50734005686992896",
            "startPointLon": 120.687215,
            "startPointLat": 31.33317,
            "startPointHeight": 60,
            "endPointLon": 120.70385,
            "endPointLat": 31.334298,
            "endPointHeight": 60,
            "width": 200,
            "protectHeight": 500,
            "airRouteSegmentSeq": 1,
        },
        {
            "type": 2,
            "airRouteId": "23560499761315840",
            "airRouteElementId": "50734005691187200",
            "startPointLon": 120.70385,
            "startPointLat": 31.334298,
            "startPointHeight": 60,
            "endPointLon": 120.719165,
            "endPointLat": 31.337681,
            "endPointHeight": 60,
            "width": 200,
            "protectHeight": 500,
            "airRouteSegmentSeq": 2,
        },
        {
            "type": 2,
            "airRouteId": "23560499761315840",
            "airRouteElementId": "50734005691187201",
            "startPointLon": 120.719165,
            "startPointLat": 31.337681,
            "startPointHeight": 60,
            "endPointLon": 120.736724,
            "endPointLat": 31.337906,
            "endPointHeight": 60,
            "width": 200,
            "protectHeight": 500,
            "airRouteSegmentSeq": 3,
        },
        {
            "type": 2,
            "airRouteId": "23560499761315840",
            "airRouteElementId": "50734005691187202",
            "startPointLon": 120.736724,
            "startPointLat": 31.337906,
            "startPointHeight": 60,
            "endPointLon": 120.741081,
            "endPointLat": 31.333734,
            "endPointHeight": 60,
            "width": 200,
            "protectHeight": 500,
            "airRouteSegmentSeq": 4,
        },
    ],
}

# ---------------------------------------------------------------------------
# 聚合配置字典（外部脚本可直接修改实现全局配置变更）
# ---------------------------------------------------------------------------
DEFAULT_TASK_CONFIG = {
    "taskPurpose": "13",                # 02.任务目的代码（code_item ID 104~136）
    "taskType": "SINGLE",               # 03.任务类别：SINGLE/REPEAT/EMERGENCY
    "operatorType": DEFAULT_OPERATOR_TYPE,  # 04.运营人类型
    "flightMode": "0",                  # 08.飞行模式：0=超视距, 1=视距内
    "flightControlMode": "2",           # 09.操控模式：1=遥控, 2=自主
    "files": [],                        # 12.附件列表
    "isDangerousGoods": False,          # 13.运载危险品
    "isMovingOper": False,              # 14.在移动交通工具上操控
    "isOverCrowds": False,              # 15.飞跃集会人群上空
    "isRtOrSwarm": False,               # 16.实时分布式或集群飞行
    "isRelayOrNet": False,              # 17.通过通信基站或互联网中继飞行
    "taskDesc": "",                     # 18.飞行事由描述
    "startMinutesOffset": 3.0,          # 19.起始时间偏移（分钟）
    "durationMinutes": 30.0,            # 19.持续时长（分钟）
    "timeSliceMinutes": 15.0,           # 19.批量创建时间间隔（分钟）
    "observers": [],                    # 22.观察员列表
    "repeatConfig": {},                 # 23.重复配置
    "airspaceType": "NON_SEGREGATED",   # 25.空域类型
    "isDraft": False,                   # 26.是否草稿
    "nameTemplate": NAME_TEMPLATE,      # 01.名称模板
}

DEFAULT_OPERATOR = {
    "operatorType": DEFAULT_OPERATOR_TYPE,
    "operatorId": DEFAULT_OPERATOR_ID,
    "operatorName": DEFAULT_OPERATOR_NAME,
    "contact": DEFAULT_CONTACT,
    "phoneNumber": DEFAULT_PHONE_NUMBER,
}

# 脚本导入时是否自动从数据库加载运营人/UAV/飞行员/航线默认值
# 设为 False 则完全使用上方硬编码值，设为 True 则优先查库（失败静默回退）
AUTO_LOAD_DB_DEFAULTS = True


# ============================ 数据库动态加载默认值 ============================

def _try_load_default_operator_from_db(
    schema: str = "ATC_DKWRJ_TEST", operator_type: str = "2"
) -> dict:
    """
    尝试从数据库读取运营人默认值。
    operator_type="1"(个人) → operation_people 表
    operator_type="2"(组织机构) → operation_organization 表
    对应字段: OPERATOR_TYPE, OPERATOR_ID, OPERATOR_NAME, CONTACT, PHONE_NUMBER
    失败时返回 None，调用方回退到 DEFAULT_OPERATOR。
    """
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return None

        if operator_type == "1":
            # 个人运营人：从 operation_people 查询
            rows = client.query("operation_people", limit=1)
            client.close()
            if rows:
                r = rows[0]
                return {
                    "operatorType": "1",
                    "operatorId": str(r.get("ID", r.get("OPERATOR_ID", DEFAULT_OPERATOR["operatorId"]))),
                    "operatorName": str(r.get("NAME", r.get("OPERATOR_NAME", DEFAULT_OPERATOR["operatorName"]))),
                    "contact": str(r.get("NAME", r.get("OPERATOR_NAME", DEFAULT_OPERATOR["operatorName"]))),
                    "phoneNumber": str(r.get("PHONE", r.get("PHONE_NUMBER", DEFAULT_OPERATOR.get("phoneNumber", "13812345661")))),
                }
        else:
            # 组织机构：从 operation_organization 查询
            rows = client.query("operation_organization", limit=1)
            client.close()
            if rows:
                r = rows[0]
                return {
                    "operatorType": "2",
                    "operatorId": str(r.get("ID", DEFAULT_OPERATOR["operatorId"])),
                    "operatorName": str(r.get("NAME", r.get("ORG_NAME", DEFAULT_OPERATOR["operatorName"]))),
                    "contact": str(r.get("CONTACT", r.get("CONTACT_NAME", DEFAULT_OPERATOR.get("contact", "atcAdmin")))),
                    "phoneNumber": str(r.get("PHONE", r.get("PHONE_NUMBER", DEFAULT_OPERATOR.get("phoneNumber", "13812345661")))),
                }
    except Exception:
        pass
    return None


def _try_load_default_pilot_from_db(schema: str = "ATC_DKWRJ_TEST") -> dict:
    """
    尝试从 operation_people 表读取操作员/飞行员记录作为默认值。
    对应字段（推测）: ID/OPERATOR_ID, NAME/OPERATOR_NAME, ID_TYPE,
                     ID_NUMBER/OPERATOR_ID_NUMBER, RPL_TYPE, LICENSE_NUMBER,
                     LICENSE_VALIDITY/OPERATOR_LICENSE_VALIDITY
    失败时返回 None，调用方回退到 DEFAULT_PILOT。
    """
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return None
        rows = client.query("operation_people", limit=1)
        client.close()
        if rows:
            r = rows[0]
            return {
                "operatorId": str(r.get("ID", r.get("OPERATOR_ID", DEFAULT_PILOT["operatorId"]))),
                "operatorName": str(r.get("NAME", r.get("OPERATOR_NAME", DEFAULT_PILOT["operatorName"]))),
                "idType": str(r.get("ID_TYPE", DEFAULT_PILOT["idType"])),
                "operatorIdNumber": str(r.get("ID_NUMBER", r.get("OPERATOR_ID_NUMBER", DEFAULT_PILOT["operatorIdNumber"]))),
                "rplType": str(r.get("RPL_TYPE", DEFAULT_PILOT["rplType"])),
                "licenseNumber": str(r.get("LICENSE_NUMBER", DEFAULT_PILOT["licenseNumber"])),
                "operatorLicenseValidity": int(r.get("LICENSE_VALIDITY", r.get("OPERATOR_LICENSE_VALIDITY", DEFAULT_PILOT["operatorLicenseValidity"]))),
            }
    except Exception:
        pass
    return None


def _try_load_default_uav_from_db(
    schema: str = "ATC_DKWRJ_TEST", operator_type: str = "2", operator_id: str = None
) -> dict:
    """
    尝试从 uav_info 表读取无人机记录作为默认值。
    个人(operator_type="1")：查询个人名下的航空器
    组织机构(operator_type="2")：查询组织机构下的航空器
    对应字段（推测）: ID, NAME, IDENTIFY_CODE, POLICY_NUMBER,
                     INSURANCE_COMPANY, REGISTRATION_CODE,
                     MANUFACTURER, TYPE, MODEL, OPERATOR_ID / ORGANIZATION_ID
    失败时返回 None，调用方回退到 DEFAULT_UAV。
    """
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return None

        # 尝试根据运营人过滤
        where = None
        if operator_id:
            # 优先尝试 OPERATOR_ID 字段过滤，其次 ORGANIZATION_ID
            where = f"OPERATOR_ID = '{operator_id}' OR ORGANIZATION_ID = '{operator_id}'"

        rows = client.query("uav_info", where=where, limit=1)
        client.close()
        if rows:
            r = rows[0]
            return {
                "uavId": str(r.get("ID", DEFAULT_UAV["uavId"])),
                "uavName": str(r.get("NAME", DEFAULT_UAV["uavName"])),
                "uavIdentifyCode": str(r.get("IDENTIFY_CODE", r.get("UAV_IDENTIFY_CODE", DEFAULT_UAV["uavIdentifyCode"]))),
                "policyNumber": str(r.get("POLICY_NUMBER", DEFAULT_UAV["policyNumber"])),
                "insuranceCompany": str(r.get("INSURANCE_COMPANY", DEFAULT_UAV["insuranceCompany"])),
                "registrationCode": str(r.get("REGISTRATION_CODE", r.get("UAV_REGISTRATION_CODE", DEFAULT_UAV["registrationCode"]))),
                "manufacturer": str(r.get("MANUFACTURER", DEFAULT_UAV["manufacturer"])),
                "uavType": str(r.get("TYPE", r.get("UAV_TYPE", DEFAULT_UAV["uavType"]))),
                "uavModel": str(r.get("MODEL", r.get("UAV_MODEL", DEFAULT_UAV["uavModel"]))),
            }
    except Exception:
        pass
    return None


def _try_load_default_flight_line_from_db(schema: str = "ATC_DKWRJ_TEST") -> dict:
    """
    尝试从数据库组装航线默认值。
    涉及表: air_route, air_route_segment, airport
    失败时返回 None，调用方回退到 DEFAULT_FLIGHT_LINE。
    """
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return None

        routes = client.query("air_route", limit=1)
        if not routes:
            client.close()
            return None
        route = routes[0]
        route_id = route.get("ID")

        segs = client.query(
            "air_route_segment",
            where=f"AIR_ROUTE_ID = '{route_id}'" if route_id else "ROWNUM <= 4",
        )
        airports = client.query("airport", limit=2)
        client.close()

        line_segments = []
        for i, s in enumerate(segs or [], 1):
            line_segments.append({
                "type": 2,
                "airRouteId": str(route_id or DEFAULT_FLIGHT_LINE["lineSegments"][0]["airRouteId"]),
                "airRouteElementId": str(s.get("ID", s.get("ELEMENT_ID", ""))),
                "startPointLon": float(s.get("START_POINT_LON", 0)),
                "startPointLat": float(s.get("START_POINT_LAT", 0)),
                "startPointHeight": int(s.get("START_POINT_HEIGHT", 60)),
                "endPointLon": float(s.get("END_POINT_LON", 0)),
                "endPointLat": float(s.get("END_POINT_LAT", 0)),
                "endPointHeight": int(s.get("END_POINT_HEIGHT", 60)),
                "width": int(s.get("WIDTH", 200)),
                "protectHeight": int(s.get("PROTECT_HEIGHT", 500)),
                "airRouteSegmentSeq": int(s.get("SEGMENT_SEQ", s.get("AIR_ROUTE_SEGMENT_SEQ", i))),
            })

        dep = (airports or [{}])[0] if airports else {}
        arr = (airports or [{}, {}])[1] if len(airports or []) > 1 else {}

        return {
            "flightLineName": f"航线-{route.get('NAME', '默认航路')}",
            "departureAirportId": str(dep.get("ID", DEFAULT_FLIGHT_LINE["departureAirportId"])),
            "departureAirportName": str(dep.get("NAME", DEFAULT_FLIGHT_LINE["departureAirportName"])),
            "departurePointLon": float(dep.get("LON", DEFAULT_FLIGHT_LINE["departurePointLon"])),
            "departurePointLat": float(dep.get("LAT", DEFAULT_FLIGHT_LINE["departurePointLat"])),
            "departurePointHeight": dep.get("HEIGHT", ""),
            "takeoffPointLon": float(dep.get("LON", DEFAULT_FLIGHT_LINE["takeoffPointLon"])),
            "takeoffPointLat": float(dep.get("LAT", DEFAULT_FLIGHT_LINE["takeoffPointLat"])),
            "takeoffPointHeight": dep.get("HEIGHT", ""),
            "arrivalAirportId": str(arr.get("ID", DEFAULT_FLIGHT_LINE["arrivalAirportId"])),
            "arrivalAirportName": str(arr.get("NAME", DEFAULT_FLIGHT_LINE["arrivalAirportName"])),
            "arrivalPointLon": float(arr.get("LON", DEFAULT_FLIGHT_LINE["arrivalPointLon"])),
            "arrivalPointLat": float(arr.get("LAT", DEFAULT_FLIGHT_LINE["arrivalPointLat"])),
            "arrivalPointHeight": arr.get("HEIGHT", ""),
            "landPointLon": float(arr.get("LON", DEFAULT_FLIGHT_LINE["landPointLon"])),
            "landPointLat": float(arr.get("LAT", DEFAULT_FLIGHT_LINE["landPointLat"])),
            "landPointHeight": arr.get("HEIGHT", ""),
            "lineSegments": line_segments or DEFAULT_FLIGHT_LINE["lineSegments"],
        }
    except Exception:
        pass
    return None


def _get_occupied_uav_pilot_ids(schema: str = "ATC_DKWRJ_TEST") -> tuple[set, set]:
    """
    查询数据库中当前非结束状态的飞行任务，提取已占用的 uavId 和 pilot operatorId。

    查询策略（按优先级尝试）：
        1. flight_task 表若存在 UAV_ID / PILOT_ID 列，直接查询
        2. 尝试关联表 flight_task_uav / flight_task_pilot
        3. 尝试从 JSON 列（REQUEST_BODY / CONTENT / PARAMS）解析

    Returns:
        (occupied_uav_ids: set, occupied_pilot_ids: set)
    """
    occupied_uavs: set = set()
    occupied_pilots: set = set()
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return occupied_uavs, occupied_pilots

        # 查询 flight_task 表列名
        cols = client.execute(
            f"SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS "
            f"WHERE TABLE_NAME = 'FLIGHT_TASK' AND OWNER = '{schema}'"
        )
        col_names = {c["COLUMN_NAME"].upper() for c in (cols or [])}

        # 结束状态值（可能编码）
        end_statuses = ("'END'", "'FINISHED'", "'COMPLETED'", "'3'", "'4'")
        status_where = "TASK_STATUS NOT IN (" + ",".join(end_statuses) + ")"

        # 策略1: 直接字段
        if "UAV_ID" in col_names and "PILOT_ID" in col_names:
            rows = client.execute(
                f"SELECT UAV_ID, PILOT_ID FROM {schema}.flight_task WHERE {status_where}"
            )
            for r in rows or []:
                if r.get("UAV_ID"):
                    occupied_uavs.add(str(r["UAV_ID"]))
                if r.get("PILOT_ID"):
                    occupied_pilots.add(str(r["PILOT_ID"]))
        elif "UAV_IDS" in col_names:
            rows = client.execute(
                f"SELECT UAV_IDS, PILOT_IDS FROM {schema}.flight_task WHERE {status_where}"
            )
            for r in rows or []:
                if r.get("UAV_IDS"):
                    occupied_uavs.update(x.strip() for x in str(r["UAV_IDS"]).split(",") if x.strip())
                if r.get("PILOT_IDS"):
                    occupied_pilots.update(x.strip() for x in str(r["PILOT_IDS"]).split(",") if x.strip())
        else:
            # 策略2: 关联表
            for assoc, target in (("flight_task_uav", occupied_uavs), ("flight_task_pilot", occupied_pilots)):
                try:
                    fk_col = "UAV_ID" if "uav" in assoc else "PILOT_ID"
                    rows = client.execute(
                        f"SELECT {fk_col} FROM {schema}.{assoc} WHERE TASK_ID IN ("
                        f"  SELECT ID FROM {schema}.flight_task WHERE {status_where}"
                        f")"
                    )
                    for r in rows or []:
                        if r.get(fk_col):
                            target.add(str(r[fk_col]))
                except Exception:
                    pass

            # 策略3: JSON 列解析（CLOB/TEXT 类型存储请求体）
            json_cols = [c for c in col_names if c in ("REQUEST_BODY", "CONTENT", "PARAMS", "EXT_DATA")]
            if json_cols and not occupied_uavs and not occupied_pilots:
                try:
                    col = json_cols[0]
                    rows = client.execute(
                        f"SELECT {col} FROM {schema}.flight_task WHERE {status_where}"
                    )
                    for r in rows or []:
                        raw = r.get(col)
                        if not raw:
                            continue
                        try:
                            data = json.loads(str(raw))
                            for u in data.get("uavInfos", []):
                                if u.get("uavId"):
                                    occupied_uavs.add(str(u["uavId"]))
                            for p in data.get("pilots", []):
                                if p.get("operatorId"):
                                    occupied_pilots.add(str(p["operatorId"]))
                        except Exception:
                            continue
                except Exception:
                    pass

        client.close()
    except Exception:
        pass
    return occupied_uavs, occupied_pilots


def _get_available_uavs(
    schema: str = "ATC_DKWRJ_TEST",
    operator_type: str = "2",
    operator_id: str = None,
    limit: int = 10,
    exclude_ids: set = None,
) -> list:
    """
    从 uav_info 表批量查询可用航空器列表，排除已被占用的。

    Returns:
        list[dict]: 可用航空器字典列表，字段同 DEFAULT_UAV
    """
    exclude_ids = exclude_ids or set()
    results = []
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return results

        where = None
        conditions = []
        if exclude_ids:
            id_str = ",".join(f"'{uid}'" for uid in exclude_ids)
            conditions.append(f"ID NOT IN ({id_str})")
        if operator_id:
            conditions.append(f"(OPERATOR_ID = '{operator_id}' OR ORGANIZATION_ID = '{operator_id}')")

        if conditions:
            where = " AND ".join(conditions)

        rows = client.query("uav_info", where=where, limit=limit)
        client.close()

        for r in rows or []:
            results.append({
                "uavId": str(r.get("ID", "")),
                "uavName": str(r.get("NAME", "")),
                "uavIdentifyCode": str(r.get("IDENTIFY_CODE", r.get("UAV_IDENTIFY_CODE", ""))),
                "policyNumber": str(r.get("POLICY_NUMBER", "")),
                "insuranceCompany": str(r.get("INSURANCE_COMPANY", "")),
                "registrationCode": str(r.get("REGISTRATION_CODE", r.get("UAV_REGISTRATION_CODE", ""))),
                "manufacturer": str(r.get("MANUFACTURER", "")),
                "uavType": str(r.get("TYPE", r.get("UAV_TYPE", DEFAULT_UAV_TYPE))),
                "uavModel": str(r.get("MODEL", r.get("UAV_MODEL", ""))),
            })
    except Exception:
        pass
    return results


def _get_available_pilots(
    schema: str = "ATC_DKWRJ_TEST",
    limit: int = 10,
    exclude_ids: set = None,
) -> list:
    """
    从 operation_people 表批量查询可用操作员列表，排除已被占用的。

    Returns:
        list[dict]: 可用操作员字典列表，字段同 DEFAULT_PILOT
    """
    exclude_ids = exclude_ids or set()
    results = []
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return results

        where = None
        if exclude_ids:
            id_str = ",".join(f"'{pid}'" for pid in exclude_ids)
            where = f"ID NOT IN ({id_str})"

        rows = client.query("operation_people", where=where, limit=limit)
        client.close()

        for r in rows or []:
            results.append({
                "operatorId": str(r.get("ID", r.get("OPERATOR_ID", ""))),
                "operatorName": str(r.get("NAME", r.get("OPERATOR_NAME", ""))),
                "idType": str(r.get("ID_TYPE", "0")),
                "operatorIdNumber": str(r.get("ID_NUMBER", r.get("OPERATOR_ID_NUMBER", ""))),
                "rplType": str(r.get("RPL_TYPE", "RPL_M")),
                "licenseNumber": str(r.get("LICENSE_NUMBER", "")),
                "operatorLicenseValidity": int(r.get("LICENSE_VALIDITY", r.get("OPERATOR_LICENSE_VALIDITY", 1848499200000))),
            })
    except Exception:
        pass
    return results


# 模块级缓存：数据库加载的默认值（避免重复查库）
_db_defaults_cache = None


def get_db_defaults(
    schema: str = "ATC_DKWRJ_TEST",
    operator_type: str = "2",
    operator_id: str = None,
    force_refresh: bool = False,
) -> dict:
    """
    获取数据库默认值字典，优先查库，失败回退到硬编码。
    结果会被缓存，避免同一进程内重复连接数据库。

    Args:
        schema: 数据库模式名
        operator_type: 运营人类型 "1"(个人) / "2"(组织机构)
        operator_id: 运营人ID，用于过滤个人/组织名下的无人机
        force_refresh: 是否强制刷新缓存

    Returns:
        {
            "operator": {...},
            "uav": {...},
            "pilot": {...},
            "flight_line": {...},
        }
    """
    global _db_defaults_cache
    if _db_defaults_cache is not None and not force_refresh:
        return _db_defaults_cache

    op = _try_load_default_operator_from_db(schema, operator_type)
    # 若数据库查到了运营人，优先用数据库中的 operator_id 过滤无人机
    uav_op_id = operator_id or (op.get("operatorId") if op else None)
    uav = _try_load_default_uav_from_db(schema, operator_type, uav_op_id)
    pilot = _try_load_default_pilot_from_db(schema)
    fl = _try_load_default_flight_line_from_db(schema)

    _db_defaults_cache = {
        "operator": op or DEFAULT_OPERATOR,
        "uav": uav or DEFAULT_UAV,
        "pilot": pilot or DEFAULT_PILOT,
        "flight_line": fl or DEFAULT_FLIGHT_LINE,
    }
    return _db_defaults_cache


def _init_defaults_from_db(schema: str = "ATC_DKWRJ_TEST") -> None:
    """
    脚本导入时尝试从数据库初始化实体默认值（运营人/UAV/飞行员/航线）。
    查询成功则覆盖顶部硬编码常量；失败则静默回退，保持原有值不变。
    可通过设置 AUTO_LOAD_DB_DEFAULTS = False 禁用此行为。
    """
    if not AUTO_LOAD_DB_DEFAULTS:
        return

    global DEFAULT_OPERATOR, DEFAULT_OPERATOR_TYPE, DEFAULT_UAV, DEFAULT_PILOT, DEFAULT_FLIGHT_LINE

    try:
        # 1. 运营人
        op = _try_load_default_operator_from_db(schema, DEFAULT_OPERATOR_TYPE)
        if op:
            DEFAULT_OPERATOR = op
            # 同步 operatorType 到 DEFAULT_TASK_CONFIG
            new_op_type = op.get("operatorType", DEFAULT_OPERATOR_TYPE)
            if new_op_type != DEFAULT_OPERATOR_TYPE:
                DEFAULT_OPERATOR_TYPE = new_op_type
                DEFAULT_TASK_CONFIG["operatorType"] = new_op_type
    except Exception:
        pass

    try:
        # 2. UAV（用查到的运营人ID过滤，确保个人/组织隔离）
        op_id = DEFAULT_OPERATOR.get("operatorId")
        uav = _try_load_default_uav_from_db(schema, DEFAULT_OPERATOR_TYPE, op_id)
        if uav:
            DEFAULT_UAV = uav
    except Exception:
        pass

    try:
        # 3. 飞行员/操作员
        pilot = _try_load_default_pilot_from_db(schema)
        if pilot:
            DEFAULT_PILOT = pilot
    except Exception:
        pass

    try:
        # 4. 航线
        fl = _try_load_default_flight_line_from_db(schema)
        if fl:
            DEFAULT_FLIGHT_LINE = fl
    except Exception:
        pass


# ============================ 工具函数 ============================

def current_timestamp_ms(dt: datetime = None) -> int:
    """将 datetime 转为毫秒级时间戳"""
    if dt is None:
        dt = datetime.now()
    return int(dt.timestamp() * 1000)


# 任务性质与任务类别的关联规则（来自 UI 填写规则文档）
# 属于 "应急" 类别的任务性质：城市空中消防、空中医疗紧急救援、森林防火与护林
_EMERGENCY_ALLOWED_PURPOSES = {"14", "15", "16"}  # 需根据 code_item 实际值调整


def _validate_task_purpose_type(task_purpose: str, task_type: str) -> str:
    """
    校验任务性质与任务类别的关联规则。
    城市空中消防、空中医疗紧急救援、森林防火与护林：可选 SINGLE/REPEAT/EMERGENCY
    其余：只能选 SINGLE/REPEAT
    若传入非法组合，自动修正为 SINGLE 并打印警告。
    """
    if task_type == "EMERGENCY" and task_purpose not in _EMERGENCY_ALLOWED_PURPOSES:
        print(
            f"[警告] 任务性质 '{task_purpose}' 不支持应急(EMERGENCY)类别，"
            f"自动修正为 SINGLE。仅以下性质支持应急: {_EMERGENCY_ALLOWED_PURPOSES}"
        )
        return "SINGLE"
    return task_type


def make_task_payload(
    task_name: str = None,
    start_minutes_offset: float = None,
    duration_minutes: float = None,
    task_purpose: str = None,
    task_type: str = None,
    operator_type: str = None,
    flight_mode: str = None,
    flight_control_mode: str = None,
    airspace_type: str = None,
    is_draft: bool = None,
    contact: str = None,
    phone_number: str = None,
    uav_info: dict = None,
    pilot_info: dict = None,
    flight_line: dict = None,
    operator_info: dict = None,
    schema: str = "ATC_DKWRJ_TEST",
) -> dict:
    """
    构造 /flight/task/create 接口的请求 Payload

    关于默认值来源：
        若传入参数为 None，本函数优先尝试从数据库（uav_info / operation_people /
        operation_organization / air_route / air_route_segment / airport / code_item
        等表）查询真实记录作为默认值。当数据库不可用时，自动回退到硬编码值。

    数据库字段映射：
        - operator_info  → operation_organization / operation_people
        - uav_info       → uav_info（个人名下或组织机构下）
        - pilot_info     → operation_people
        - flight_line    → air_route + air_route_segment + airport 组合
        - task_purpose   → code_item (ID 104~136) CODE_ITEM_VALUE
        - task_type      → code_item (ID 137~139) CODE_ITEM_VALUE

    时间规则（单次任务默认）：
        - 起始时间 = 当前时间 + start_minutes_offset（默认延迟 3 分钟）
        - 结束时间 = 起始时间 + duration_minutes（默认持续 30 分钟）

    Args:
        task_name: 任务名称，为空时自动生成；不超过 50 个字符
        start_minutes_offset: 开始偏移（分钟），为 None 时取 DEFAULT_TASK_CONFIG
        duration_minutes: 持续时长（分钟），为 None 时取 DEFAULT_TASK_CONFIG
        task_purpose: 任务目的代码，为 None 时取 DEFAULT_TASK_CONFIG
        task_type: 任务类型，为 None 时取 DEFAULT_TASK_CONFIG
        operator_type: 运营人类型，为 None 时取 DEFAULT_TASK_CONFIG
        flight_mode: 飞行模式，为 None 时取 DEFAULT_TASK_CONFIG
        flight_control_mode: 操控模式，为 None 时取 DEFAULT_TASK_CONFIG
        airspace_type: 空域类型，为 None 时取 DEFAULT_TASK_CONFIG
        is_draft: 是否为草稿，为 None 时取 DEFAULT_TASK_CONFIG
        contact: 联系人，为 None 时从运营人信息提取
        phone_number: 联系电话，为 None 时从运营人信息提取
        uav_info: 无人机信息字典，为 None 时自动从数据库/默认值获取
        pilot_info: 飞行员信息字典，为 None 时自动从默认值获取
        flight_line: 航线信息字典，为 None 时自动从数据库/默认值获取
        operator_info: 运营人信息字典，为 None 时自动从数据库/默认值获取
        schema: 数据库模式名，用于动态查库

    Returns:
        dict: 可直接 JSON 序列化的请求体
    """
    # 若参数为 None，从顶部 DEFAULT_TASK_CONFIG 读取默认值
    # 外部脚本可直接修改 DEFAULT_TASK_CONFIG 实现全局配置变更
    def _cfg(key, override):
        return override if override is not None else DEFAULT_TASK_CONFIG[key]

    _task_purpose = _cfg("taskPurpose", task_purpose)
    _task_type = _cfg("taskType", task_type)
    _operator_type = _cfg("operatorType", operator_type)
    _flight_mode = _cfg("flightMode", flight_mode)
    _flight_control_mode = _cfg("flightControlMode", flight_control_mode)
    _airspace_type = _cfg("airspaceType", airspace_type)
    _is_draft = _cfg("isDraft", is_draft)
    _start_offset = _cfg("startMinutesOffset", start_minutes_offset)
    _duration = _cfg("durationMinutes", duration_minutes)

    # 获取实体默认值（优先数据库，其次硬编码 DEFAULT_*）
    # 根据 operator_type 和 operator_id 动态查库，确保个人/组织名下的无人机隔离
    op_id = operator_info.get("operatorId") if operator_info else None
    db_defaults = get_db_defaults(
        schema=schema,
        operator_type=_operator_type,
        operator_id=op_id,
    )

    _operator = operator_info if operator_info is not None else db_defaults["operator"]
    _uav = uav_info if uav_info is not None else db_defaults["uav"]
    _pilot = pilot_info if pilot_info is not None else db_defaults["pilot"]
    _flight_line = flight_line if flight_line is not None else db_defaults["flight_line"]

    # 联系人/电话若未传入，尝试从运营人信息中提取，否则从 DEFAULT_TASK_CONFIG / DEFAULT_OPERATOR
    _contact = contact if contact is not None else _operator.get("contact", DEFAULT_OPERATOR.get("contact", "atcAdmin"))
    _phone = phone_number if phone_number is not None else _operator.get("phoneNumber", DEFAULT_OPERATOR.get("phoneNumber", "13812345661"))

    now = datetime.now()
    start_dt = now + timedelta(minutes=_start_offset)
    end_dt = start_dt + timedelta(minutes=_duration)

    if not task_name:
        task_name = format_task_name(NAME_TEMPLATE, 1, now)

    # 任务名称长度校验（UI 规则：不超过 50 个字符）
    if len(task_name) > 50:
        raise ValueError(f"任务名称长度不能超过 50 个字符，当前 {len(task_name)} 个字符: '{task_name}'")

    # 任务性质与类别关联校验
    validated_task_type = _validate_task_purpose_type(_task_purpose, _task_type)

    payload = {
        "taskName": task_name,
        "taskPurpose": _task_purpose,
        "taskType": validated_task_type,
        "operatorType": _operator_type,
        "operatorId": _operator["operatorId"],
        "operatorName": _operator["operatorName"],
        "uavType": _uav["uavType"],
        "flightMode": _flight_mode,
        "flightControlMode": _flight_control_mode,
        "contact": _contact,
        "phoneNumber": _phone,
        "files": DEFAULT_TASK_CONFIG["files"],
        "isDangerousGoods": DEFAULT_TASK_CONFIG["isDangerousGoods"],
        "isMovingOper": DEFAULT_TASK_CONFIG["isMovingOper"],
        "isOverCrowds": DEFAULT_TASK_CONFIG["isOverCrowds"],
        "isRtOrSwarm": DEFAULT_TASK_CONFIG["isRtOrSwarm"],
        "isRelayOrNet": DEFAULT_TASK_CONFIG["isRelayOrNet"],
        "taskDesc": DEFAULT_TASK_CONFIG["taskDesc"],
        "periods": [
            {
                "startTime": current_timestamp_ms(start_dt),
                "endTime": current_timestamp_ms(end_dt),
            }
        ],
        "uavInfos": [_uav],
        "pilots": [_pilot],
        "observers": DEFAULT_TASK_CONFIG["observers"],
        "repeatConfig": DEFAULT_TASK_CONFIG["repeatConfig"],
        "flightLines": [_flight_line],
        "airspaceType": _airspace_type,
        "isDraft": _is_draft,
    }
    return payload


def create_flight_task(
    payload: dict,
    base_url: str = BASE_URL,
    timeout: int = 30,
    print_request: bool = False,
) -> dict:
    """
    调用创建飞行任务接口

    Args:
        payload: 请求体字典
        base_url: 服务基础地址
        timeout: 请求超时秒数
        print_request: 是否打印请求体

    Returns:
        dict: 接口响应字典，包含 id / taskName / taskNumber / taskStatus
              失败时返回 {"success": False, "error": "..."}
    """
    token = get_jwt_token(base_url=base_url)
    if not token:
        return {"success": False, "error": "获取 JWT Token 失败"}

    url = f"{base_url}{API_PATH}"
    headers = {
        "jwt-token": token,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }

    if print_request:
        print(f"\n[Request] POST {url}")
        print(f"[Headers] {json.dumps(headers, ensure_ascii=False, indent=2)}")
        print(f"[Body] {json.dumps(payload, ensure_ascii=False, indent=2)}")

    try:
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == "0" and isinstance(data.get("result"), dict):
            result = data["result"]
            result["success"] = True
            return result
        else:
            return {
                "success": False,
                "error": f"接口返回异常: code={data.get('code')}, msg={data}",
                "raw": data,
            }
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"HTTP 请求异常: {e}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"响应 JSON 解析失败: {e}", "text": resp.text}


def format_task_name(template: str, seq: int, now: datetime = None) -> str:
    """
    根据模板生成带序号的任务名称。

    支持的占位符：
        {date}      → 当前日期 MMDD（如 0602）
        {datetime}  → 当前日期时间 MMDDHHMMSS（如 0602143015）
        {seq}       → 序号（如 1, 2, 3）
        {seq:Nd}    → 带前导零的序号（如 {seq:04d} → 0001）
        {timestamp} → 毫秒级时间戳

    Args:
        template: 名称模板，如 "飞行任务自动化测试{date}{seq:04d}"
        seq: 当前序号（从 1 开始）
        now: 当前时间，为空时使用 datetime.now()

    Returns:
        str: 格式化后的任务名称

    Raises:
        ValueError: 若生成结果超过 50 个字符
    """
    if now is None:
        now = datetime.now()

    name = template
    name = name.replace("{date}", now.strftime("%m%d"))
    name = name.replace("{datetime}", now.strftime("%m%d%H%M%S"))
    name = name.replace("{timestamp}", str(current_timestamp_ms(now)))

    def _replace_seq(m):
        fmt = m.group(1)
        if fmt:
            return format(seq, fmt)
        return str(seq)

    name = re.sub(r"\{seq(?::([^}]+))?\}", _replace_seq, name)

    if len(name) > 50:
        raise ValueError(f"格式化后的任务名称超过 50 字符: '{name}' ({len(name)} 字符)")
    return name


def verify_task_in_db(task_number: str, schema: str = "ATC_DKWRJ_TEST") -> dict:
    """
    在达梦数据库 flight_task 表中查询任务是否存在

    Args:
        task_number: 任务编号
        schema: 数据库模式名

    Returns:
        dict: 查询结果，success=True 表示找到记录
    """
    try:
        client = DmDbClient(schema=schema)
        if not client.connect():
            return {"success": False, "error": "数据库连接失败"}

        rows = client.query(
            table_name="flight_task",
            columns=["ID", "TASK_NUMBER", "TASK_NAME", "TASK_STATUS", "CREATED_TIME"],
            where=f"TASK_NUMBER = '{task_number}'",
        )
        client.close()

        if rows:
            return {"success": True, "record": rows[0]}
        else:
            return {"success": False, "error": f"未找到任务编号为 {task_number} 的记录"}
    except Exception as e:
        return {"success": False, "error": f"数据库查询异常: {e}"}


# ============================ 主流程 ============================

def main():
    parser = argparse.ArgumentParser(description="飞行任务创建自动化脚本")
    parser.add_argument(
        "--task-name",
        type=str,
        default=None,
        help="任务名称，为空时自动生成（如：飞行任务060201）。"
             "若同时指定 --count 和 --name-template，此参数被模板覆盖",
    )
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=DEFAULT_COUNT,
        help="批量创建任务数量，默认 1。大于 1 时必须配合 --name-template 使用",
    )
    parser.add_argument(
        "--name-template",
        type=str,
        default=None,
        help='名称模板，支持占位符：{date}(MMDD)、{datetime}(MMDDHHMM)、'
             '{seq}(序号)、{seq:04d}(前导零序号)、{timestamp}(毫秒时间戳)。'
             '为空时取 DEFAULT_TASK_CONFIG["nameTemplate"]',
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="批量创建时每次请求间隔（秒），默认 0.5",
    )
    parser.add_argument(
        "--time-slice-minutes",
        type=float,
        default=None,
        help="批量创建时任务时间间隔（分钟），默认 15 分钟。"
             "第N个任务的开始时间 = 第1个任务开始时间 + (N-1) * time_slice_minutes",
    )
    parser.add_argument(
        "--task-purpose",
        type=str,
        default="13",
        help="任务目的代码（code_item ID 104~136），默认 13",
    )
    parser.add_argument(
        "--task-type",
        type=str,
        default="SINGLE",
        choices=["SINGLE", "REPEAT", "EMERGENCY"],
        help="任务类别：SINGLE（单次）、REPEAT（多次）、EMERGENCY（应急）。"
             "注意：仅城市空中消防/空中医疗紧急救援/森林防火与护林支持应急，默认 SINGLE",
    )
    parser.add_argument(
        "--operator-type",
        type=str,
        default="2",
        choices=["1", "2"],
        help="运营人类型：1（个人）/ 2（组织机构），默认 2",
    )
    parser.add_argument(
        "--start-minutes",
        type=float,
        default=3.0,
        help="任务开始时间偏移（分钟），默认 3 分钟后开始（单次任务 UI 规则）",
    )
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=30.0,
        help="任务持续时长（分钟），默认 30 分钟（单次任务 UI 规则）",
    )
    parser.add_argument(
        "--flight-mode",
        type=str,
        default="0",
        choices=["0", "1"],
        help="飞行模式：0（超视距飞行）/ 1（视距内飞行），默认 0",
    )
    parser.add_argument(
        "--flight-control-mode",
        type=str,
        default="2",
        choices=["1", "2"],
        help="操控模式：1（遥控飞行）/ 2（自主飞行），默认 2",
    )
    parser.add_argument(
        "--airspace-type",
        type=str,
        default="NON_SEGREGATED",
        help="空域类型，默认 NON_SEGREGATED",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="创建为草稿任务（isDraft=true）",
    )
    parser.add_argument(
        "--contact",
        type=str,
        default=None,
        help="联系人，为空时从运营人信息自动获取",
    )
    parser.add_argument(
        "--phone",
        type=str,
        default=None,
        help="联系电话，为空时从运营人信息自动获取",
    )
    parser.add_argument(
        "--verify-db",
        action="store_true",
        help="创建成功后查询数据库验证任务是否写入",
    )
    parser.add_argument(
        "--print-request",
        action="store_true",
        help="打印完整的请求体 JSON",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=BASE_URL,
        help=f"服务基础地址，默认 {BASE_URL}",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default="ATC_DKWRJ_TEST",
        help="数据库模式名，用于动态加载默认值，默认 ATC_DKWRJ_TEST",
    )
    parser.add_argument(
        "--no-db-defaults",
        action="store_true",
        help="强制使用硬编码默认值，不尝试从数据库加载",
    )

    args = parser.parse_args()

    # 确定时间切片间隔
    time_slice = args.time_slice_minutes if args.time_slice_minutes is not None else DEFAULT_TASK_CONFIG.get("timeSliceMinutes", 15.0)

    # 若强制禁用数据库默认值，清空缓存使 get_db_defaults 直接回退到硬编码
    if args.no_db_defaults:
        global _db_defaults_cache
        _db_defaults_cache = {
            "operator": DEFAULT_OPERATOR,
            "uav": DEFAULT_UAV,
            "pilot": DEFAULT_PILOT,
            "flight_line": DEFAULT_FLIGHT_LINE,
        }

    # 确定名称模板（命令行 > DEFAULT_TASK_CONFIG）
    name_template = args.name_template if args.name_template is not None else DEFAULT_TASK_CONFIG["nameTemplate"]

    # 批量创建前置校验
    if args.count > 1 and args.task_name:
        print(f"[警告] 批量创建 {args.count} 个任务时，--task-name 将被 --name-template 覆盖")

    # 预先生成所有任务名称（提前校验长度）
    now = datetime.now()
    task_names = []
    for i in range(1, args.count + 1):
        if args.count == 1 and args.task_name:
            name = args.task_name
        else:
            name = format_task_name(name_template, i, now)
        task_names.append(name)

    # ---------------------------------------------------------------
    # 批量资源准备：查询数据库获取可用航空器和操作员，避免冲突
    # ---------------------------------------------------------------
    available_uavs = []
    available_pilots = []
    occupied_uavs = set()
    occupied_pilots = set()

    if args.count > 1 and not args.no_db_defaults:
        print("[准备] 查询数据库获取可用资源（非结束状态任务已占用资源将被排除）...")
        occupied_uavs, occupied_pilots = _get_occupied_uav_pilot_ids(args.schema)
        if occupied_uavs:
            print(f"  已占用航空器: {len(occupied_uavs)} 个")
        if occupied_pilots:
            print(f"  已占用操作员: {len(occupied_pilots)} 个")

        # 获取运营人ID用于过滤航空器
        db_defaults = get_db_defaults(schema=args.schema, operator_type=args.operator_type)
        op_id = db_defaults["operator"].get("operatorId")

        available_uavs = _get_available_uavs(
            schema=args.schema,
            operator_type=args.operator_type,
            operator_id=op_id,
            limit=args.count + len(occupied_uavs) + 5,
            exclude_ids=occupied_uavs,
        )
        available_pilots = _get_available_pilots(
            schema=args.schema,
            limit=args.count + len(occupied_pilots) + 5,
            exclude_ids=occupied_pilots,
        )

        if available_uavs:
            print(f"  可用航空器: {len(available_uavs)} 个")
        if available_pilots:
            print(f"  可用操作员: {len(available_pilots)} 个")

        # 资源不足警告
        if len(available_uavs) < args.count:
            print(f"[警告] 可用航空器数量({len(available_uavs)})不足，需要 {args.count} 个，将循环复用")
        if len(available_pilots) < args.count:
            print(f"[警告] 可用操作员数量({len(available_pilots)})不足，需要 {args.count} 个，将循环复用")

    # 1. 构造并发送请求
    print("=" * 60)
    print(f"[Step 1] 批量构造请求参数（共 {args.count} 个任务，时间切片 {time_slice} 分钟）")
    print("=" * 60)

    success_results = []
    fail_results = []

    for idx, task_name in enumerate(task_names, 1):
        print(f"\n--- 任务 {idx}/{args.count}: {task_name} ---")

        # 时间切片：第1个任务按默认偏移，后续任务依次顺延
        start_offset = args.start_minutes + (idx - 1) * time_slice

        # 资源轮询分配
        uav_info = None
        pilot_info = None
        if available_uavs:
            uav_info = available_uavs[(idx - 1) % len(available_uavs)]
        if available_pilots:
            pilot_info = available_pilots[(idx - 1) % len(available_pilots)]

        payload = make_task_payload(
            task_name=task_name,
            start_minutes_offset=start_offset,
            duration_minutes=args.duration_minutes,
            task_purpose=args.task_purpose,
            task_type=args.task_type,
            operator_type=args.operator_type,
            flight_mode=args.flight_mode,
            flight_control_mode=args.flight_control_mode,
            airspace_type=args.airspace_type,
            is_draft=args.draft,
            contact=args.contact,
            phone_number=args.phone,
            uav_info=uav_info,
            pilot_info=pilot_info,
            schema=args.schema,
        )

        print(f"  任务性质 : {payload['taskPurpose']}")
        print(f"  任务类别 : {payload['taskType']}")
        print(f"  运营人类型 : {'个人' if payload['operatorType'] == '1' else '组织机构'}")
        print(f"  开始时间 : {datetime.fromtimestamp(payload['periods'][0]['startTime'] / 1000)}")
        print(f"  结束时间 : {datetime.fromtimestamp(payload['periods'][0]['endTime'] / 1000)}")
        print(f"  无人机   : {payload['uavInfos'][0]['uavName']} ({payload['uavInfos'][0]['uavId']})")
        print(f"  飞行员   : {payload['pilots'][0]['operatorName']} ({payload['pilots'][0]['operatorId']})")

        # 2. 调用接口
        result = create_flight_task(
            payload=payload,
            base_url=args.base_url,
            print_request=args.print_request,
        )

        if result.get("success"):
            print(f"  [成功] 任务编号: {result.get('taskNumber')}, 状态: {result.get('taskStatus')}")
            success_results.append(result)
        else:
            print(f"  [失败] {result.get('error')}")
            if "raw" in result:
                print(f"  [原始响应] {json.dumps(result['raw'], ensure_ascii=False, indent=2)}")
            fail_results.append({"task_name": task_name, "error": result.get("error"), "raw": result.get("raw")})

        # 批量创建间隔（最后一个不等待）
        if idx < args.count and args.interval > 0:
            time.sleep(args.interval)

    # 3. 汇总结果
    print("\n" + "=" * 60)
    print("[汇总] 批量创建结果")
    print("=" * 60)
    print(f"  总计   : {args.count}")
    print(f"  成功   : {len(success_results)}")
    print(f"  失败   : {len(fail_results)}")

    if success_results:
        print(f"\n  成功任务编号列表:")
        for r in success_results:
            print(f"    - {r.get('taskNumber')} | {r.get('taskName')} | {r.get('taskStatus')}")

    if fail_results:
        print(f"\n  失败任务列表:")
        for f in fail_results:
            print(f"    - {f['task_name']} | {f['error']}")

    # 4. 数据库验证（可选）
    if args.verify_db and success_results:
        print("\n" + "=" * 60)
        print("[Step 3] 数据库验证（flight_task 表）")
        print("=" * 60)

        time.sleep(1)  # 等待数据落库
        verified = 0
        for r in success_results:
            tn = r.get("taskNumber")
            if not tn:
                continue
            db_result = verify_task_in_db(tn, schema=args.schema)
            if db_result.get("success"):
                verified += 1
                print(f"  [通过] {tn}")
            else:
                print(f"  [未通过] {tn} - {db_result.get('error')}")
        print(f"\n  数据库验证通过: {verified}/{len(success_results)}")

    print("\n" + "=" * 60)
    print("[完成] 脚本执行结束")
    print("=" * 60)

    # 返回结果供外部调用
    return {
        "total": args.count,
        "success_count": len(success_results),
        "fail_count": len(fail_results),
        "success_results": success_results,
        "fail_results": fail_results,
    }


# 脚本导入时自动尝试从数据库加载实体默认值（静默回退）
_init_defaults_from_db()


if __name__ == "__main__":
    main()
