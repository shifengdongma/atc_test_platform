# -*- coding: utf-8 -*-
"""
将 _source/nfzs.json 转换为标准空域格式并上传到 Redis BIZ_DATA:AIRSPACE。
转换规则参考：算法对接文档 空域数据 小节（BIZ_DATA:AIRSPACE）。
"""
import sys
import os
import json
from datetime import datetime
from typing import Dict, Any, List

# 将项目根目录加入 path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from redis_client import RedisClient

# 路径与 Redis 配置（与 run_kafka.py 保持一致）
SOURCE_DIR = os.path.join(_root, "_source")
MOCK_DIR = os.path.join(_root, "mock")
NFZS_JSON_PATH = os.path.join(SOURCE_DIR, "nfzs.json")
MOCK_NFZS_JSON_PATH = os.path.join(MOCK_DIR, "nfzs.json")
REDIS_AIRSPACE_KEY = "BIZ_DATA:AIRSPACE"

# redis_ip = "10.165.33.173"
# redis_port = "25379"
# redis_password = "sJ3^tH4^cT6^"
redis_ip = "10.67.89.106"
redis_port = "16379"
redis_password = ""
# nfzs.json 中 type 数字 -> 标准 typeCode
TYPE_CODE_MAP = {
    3: "noDrone",   # 空中禁区
    4: "limited",   # 限制区
    5: "danger",    # 危险区
    6: "segregated",  # 隔离空域
}


def unix_to_datetime_str(ts: float) -> str:
    """Unix 时间戳 -> yyyy-MM-dd HH:mm:ss"""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "1970-01-01 00:00:00"


def verts_to_geojson_polygon(verts: List[Dict[str, float]]) -> Dict[str, Any]:
    """将 nfzs 的 geo.verts [{lat, lon, alt}] 转为 GeoJSON Polygon。坐标顺序 [lon, lat]，首尾闭合。"""
    if not verts:
        return {"type": "Polygon", "coordinates": [[]]}
    ring = [[float(v.get("lon", 0)), float(v.get("lat", 0))] for v in verts]
    if ring and (ring[0] != ring[-1]):
        ring.append(ring[0][:])
    return {"type": "Polygon", "coordinates": [ring]}


def nfz_to_airspace(nfz_uid: str, nfz: Dict[str, Any], airspace_id: int) -> Dict[str, Any]:
    """将单条禁飞区数据转换为标准空域对象。"""
    geo = nfz.get("geo") or {}
    verts = geo.get("verts") or []
    start = nfz.get("start")
    end = nfz.get("end")
    has_times = start is not None and end is not None

    type_num = nfz.get("type")
    type_code = TYPE_CODE_MAP.get(type_num, "noDrone")

    status = "TEMPORARY_ACTIVE" if has_times else "PERMANENT"
    times: List[Dict[str, str]] = []
    if has_times:
        times = [
            {
                "startTime": unix_to_datetime_str(start),
                "endTime": unix_to_datetime_str(end),
            }
        ]

    lowest = geo.get("min")
    highest = geo.get("max")
    lowest_height = int(lowest) if lowest is not None else 0
    highest_height = int(highest) if highest is not None else 0

    return {
        "airspaceId": airspace_id,
        "spcNo": nfz_uid,
        "name": nfz.get("name") or nfz_uid,
        "typeCode": type_code,
        "status": status,
        "times": times,
        "usagePurpose": nfz.get("reason") or "",
        "lowestHeight": lowest_height,
        "highestHeight": highest_height,
        "capacity": 0,
        "monitorAbility": "FULL_SURVEILLANCE",
        "polygon": verts_to_geojson_polygon(verts),
    }


def load_nfzs(path: str) -> Dict[str, Any]:
    """从 JSON 文件加载 nfzs 数据（key 为 NFZ_001 等）。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def upload_airspaces_to_redis(redis_client: RedisClient, airspace_list: List[Dict[str, Any]]) -> None:
    """将空域列表写入 Redis BIZ_DATA:AIRSPACE（hash key 为 airspaceId）。"""
    for obj in airspace_list:
        airspace_id = obj.get("airspaceId")
        if airspace_id is None:
            continue
        field = str(airspace_id)
        value = json.dumps(obj, ensure_ascii=False)
        redis_client.hset(REDIS_AIRSPACE_KEY, field, value)
        print(f"向 Redis 插入空域数据成功: airspaceId={airspace_id}, spcNo={obj.get('spcNo')}")


def main() -> None:
    if not os.path.isfile(NFZS_JSON_PATH):
        print(f"未找到文件: {NFZS_JSON_PATH}")
        sys.exit(1)

    nfzs_data = load_nfzs(NFZS_JSON_PATH)
    if not nfzs_data:
        print("nfzs.json 为空，无需上传")
        return

    airspace_list: List[Dict[str, Any]] = []
    for idx, (nfz_uid, nfz) in enumerate(nfzs_data.items(), start=1):
        if not isinstance(nfz, dict):
            continue
        airspace_list.append(nfz_to_airspace(nfz_uid, nfz, airspace_id=idx))

    # 将转换后的数据写入 mock/nfzs.json
    os.makedirs(MOCK_DIR, exist_ok=True)
    with open(MOCK_NFZS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(airspace_list, f, ensure_ascii=False, indent=2)
    print(f"已生成: {MOCK_NFZS_JSON_PATH}")

    redis_client = RedisClient(redis_ip, redis_port, redis_password)
    if not redis_client.is_connected():
        print("Redis 未连接，退出")
        sys.exit(1)

    upload_airspaces_to_redis(redis_client, airspace_list)
    print(f"共上传 {len(airspace_list)} 条空域到 {REDIS_AIRSPACE_KEY}")


if __name__ == "__main__":
    main()
