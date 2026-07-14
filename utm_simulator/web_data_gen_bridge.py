# -*- coding: utf-8 -*-
"""
Web API 桥接层：包装 tools/ 脚本为 API 友好的函数接口

避免直接调用 main() 导致的 sys.exit() 问题。
每个函数接受扁平参数，构造 argparse.Namespace，调用内部 run_*() 函数。
所有输出文件写入 mock/ 目录。
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Any, Dict, List, Optional

# 确保项目根在 sys.path 中
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# tools/ 脚本也依赖此路径
_TOOLS_DIR = os.path.join(_SCRIPT_DIR, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)


def _mock_path(filename: str) -> str:
    """返回 mock/ 目录下的完整路径"""
    mock_dir = os.path.join(_SCRIPT_DIR, "..", "data", "mock")
    os.makedirs(mock_dir, exist_ok=True)
    return os.path.join(mock_dir, filename)


def _make_ts_filename(prefix: str) -> str:
    """生成带时间戳的输出文件名"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.json"


def _safe_run(func, *args, **kwargs) -> Dict[str, Any]:
    """安全调用 tools 函数，捕获 SystemExit 和异常"""
    try:
        result = func(*args, **kwargs)
        return {"success": True, "result": result}
    except SystemExit as e:
        if e.code != 0 and e.code is not None:
            if isinstance(e.code, str):
                return {"success": False, "error": e.code}
            return {"success": False, "error": f"脚本异常退出(code={e.code})"}
        return {"success": True, "result": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================ create_data_scenes.py 桥接 ============================


def gen_parallel(
    count: int = 30,
    center_lng: float = 85.070136,
    center_lat: float = 40.818724,
    altitude: float = 50.0,
    speed: float = 15.0,
    heading: float = 90.0,
    spacing: float = 2000.0,
    spacing_along: float = 0.0,
    layout: str = "hex",
    points: int = 1200,
    interval: int = 1000,
    uid_offset: int = 0,
    classification: int = 2,
    output: Optional[str] = None,
    multi: bool = False,
    start_time: Optional[int] = None,
) -> Dict[str, Any]:
    """
    大规模平行飞行数据生成（六边形/直线布局，ID碰撞避让）

    对应: tools/create_data_scenes.py run_parallel()
    """
    from tools.create_data_scenes import run_parallel

    if output is None:
        output = "../data/mock/kafka_data_parallel.json"

    ns = argparse.Namespace(
        count=count,
        center_lng=center_lng,
        center_lat=center_lat,
        altitude=altitude,
        speed=speed,
        heading=heading,
        spacing=spacing,
        spacing_along=spacing_along,
        layout=layout,
        sim_radius=100000.0,
        classification=classification,
        points=points,
        interval=interval,
        start_time=start_time,
        output=output,
        uid_offset=uid_offset,
        multi=multi,
    )

    result = _safe_run(run_parallel, ns)
    if result["success"]:
        result["file"] = ns.output
        result["count"] = count
    return result


def gen_deviate_adv(
    route_name: str = "铁门关至吐鲁番",
    route_id: Optional[int] = None,
    uid_offset: int = 1,
    classification: int = 3,
    speed: float = 15.0,
    altitude: Optional[float] = None,
    deviate_offset: float = 3000.0,
    deviate_start: int = 20,
    deviate_transition: Optional[int] = None,
    deviate_altitude_offset: float = 0.0,
    deviate_mode: str = "horizontal",
    coord_system: str = "wgs84",
    coord_output: Optional[str] = None,
    output_dir: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    高级偏离航路数据生成（垂直偏移、平滑过渡、多模式）

    对应: tools/create_data_scenes.py run_deviate()
    """
    from tools.create_data_scenes import run_deviate

    if output_dir is None:
        output_dir = os.path.join(_SCRIPT_DIR, "mock")

    ns = argparse.Namespace(
        route_name=route_name,
        route_id=route_id,
        uid_offset=uid_offset,
        classification=classification,
        speed=speed,
        altitude=altitude,
        deviate_offset=deviate_offset,
        deviate_start=deviate_start,
        deviate_transition=deviate_transition,
        deviate_altitude_offset=deviate_altitude_offset,
        deviate_mode=deviate_mode,
        coord_system=coord_system,
        coord_output=coord_output,
        output_dir=output_dir,
        filename=filename,
    )

    result = _safe_run(run_deviate, ns)
    if result["success"]:
        if filename:
            result["file"] = os.path.join(output_dir, filename if filename.endswith(".json") else filename + ".json")
        elif route_name:
            safe_name = route_name.replace(" ", "").replace("/", "_")
            result["file"] = os.path.join(output_dir, f"{safe_name}航路偏航数据_0.1.json")
    return result


def gen_collision(
    route_names: str = "跨顺义三河段,三河区航路",
    route_id: Optional[int] = None,
    uids: str = "CW000000000000000004,CH000000000000000003",
    uid_start_offset: int = 0,
    classification: int = 2,
    altitude: Optional[float] = None,
    meeting_threshold: float = 10.0,
    warning_time: int = 20,
    collision_time: float = 300.0,
    zone_output: bool = True,
    interval: int = 1000,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    碰撞预警场景生成（交汇点检测、同步到达、区域标记）

    对应: tools/create_data_scenes.py run_collision()
    """
    from tools.create_data_scenes import run_collision

    if output_dir is None:
        output_dir = os.path.join(_SCRIPT_DIR, "mock")

    ns = argparse.Namespace(
        route_names=route_names,
        route_id=route_id,
        uids=uids,
        uid_start_offset=uid_start_offset,
        classification=classification,
        altitude=altitude,
        meeting_threshold=meeting_threshold,
        warning_time=warning_time,
        collision_time=collision_time,
        zone_output=zone_output,
        output_dir=output_dir,
        interval=interval,
    )

    result = _safe_run(run_collision, ns)
    if result["success"]:
        result["output_dir"] = output_dir
    return result


def gen_status(
    count: int = 1,
    center_lng: float = 120.7418,
    center_lat: float = 31.3689,
    altitude: float = 50.0,
    speed: float = 15.0,
    heading: float = 90.0,
    flight_minutes: int = 1,
    emergency_count: int = 5,
    ground_seconds: int = 0,
    climb_seconds: int = 0,
    spacing: float = 2000.0,
    classification: int = 2,
    scene3: bool = False,
    scene5: bool = False,
    scene3_5: bool = False,
    id_offset: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    飞行器状态告警场景生成（紧急/丢失/紧急后丢失）

    对应: tools/create_data_scenes.py run_status()
    """
    from tools.create_data_scenes import run_status

    if output_dir is None:
        output_dir = os.path.join(_SCRIPT_DIR, "mock")

    # 防止 SystemExit 在无场景时退出
    if not any([scene3, scene5, scene3_5]):
        return {"success": False, "error": "至少选择一种状态告警场景 (scene3/scene5/scene3-5)"}

    ns = argparse.Namespace(
        count=count,
        center_lng=center_lng,
        center_lat=center_lat,
        altitude=altitude,
        speed=speed,
        heading=heading,
        interval=1000,
        ground_seconds=ground_seconds,
        climb_seconds=climb_seconds,
        flight_minutes=flight_minutes,
        emergency_count=emergency_count,
        spacing=spacing,
        classification=classification,
        sim_radius=100000.0,
        id_offset=id_offset,
        scene3=scene3,
        scene5=scene5,
        scene3_5=scene3_5,
        output_dir=output_dir,
    )

    result = _safe_run(run_status, ns)
    if result["success"]:
        result["output_dir"] = output_dir
    return result


def gen_scale(
    source: str = "../data/mock/kafka_data_yfk.json",
    count: int = 100,
    center_lng: float = 89.2306,
    center_lat: float = 38.19424,
    spacing: float = 300.0,
    output: Optional[str] = None,
) -> Dict[str, Any]:
    """
    基于模板批量扩展（蜂窝网格分布）

    对应: tools/create_data_scenes.py run_scale()
    """
    from tools.create_data_scenes import run_scale

    if output is None:
        output = "../data/mock/kafka_data_alarm_100.json"

    ns = argparse.Namespace(
        source=source,
        count=count,
        center_lng=center_lng,
        center_lat=center_lat,
        spacing=spacing,
        output=output,
    )

    result = _safe_run(run_scale, ns)
    if result["success"]:
        result["file"] = ns.output
        result["count"] = count
    return result


def gen_batch(config_index: Optional[int] = None) -> Dict[str, Any]:
    """
    批量预设生成（一键执行全部或指定 BATCH_CONFIGS 预设）

    对应: tools/create_data_scenes.py run_batch()
    """
    from tools.create_data_scenes import run_batch

    ns = argparse.Namespace(config_index=config_index)
    result = _safe_run(run_batch, ns)
    return result


# ============================ create_data_scene.py 桥接 ============================


def gen_single_route(
    uid: str = "UAV_TEST_001",
    reg_sign: Optional[str] = None,
    classification: int = 2,
    route_name: Optional[str] = None,
    route_id: Optional[int] = None,
    points: Optional[str] = None,
    start_lon: Optional[float] = None,
    start_lat: Optional[float] = None,
    end_lon: Optional[float] = None,
    end_lat: Optional[float] = None,
    altitude: float = 30.0,
    start_alt: Optional[float] = None,
    end_alt: Optional[float] = None,
    speed: float = 15.0,
    start_time: Optional[int] = None,
    interval: int = 1000,
    operating_status: int = 2,
    output_dir: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    单机航线飞行数据生成（线性插值）

    对应: tools/create_data_scene.py generate_trajectory() + build_waypoints()
    """
    from tools.create_data_scene import build_waypoints, generate_trajectory, apply_deviation

    if output_dir is None:
        output_dir = os.path.join(_SCRIPT_DIR, "mock")

    # 构造 args 用于 build_waypoints
    ns = argparse.Namespace(
        route_name=route_name,
        route_id=route_id,
        points=points,
        start_lon=start_lon,
        start_lat=start_lat,
        end_lon=end_lon,
        end_lat=end_lat,
        altitude=altitude,
        start_alt=start_alt,
        end_alt=end_alt,
        speed=speed,
        start_time=start_time,
        interval=interval,
    )

    try:
        waypoints = build_waypoints(ns)
        if not waypoints or len(waypoints) < 2:
            return {"success": False, "error": "至少需要2个航路点，请提供途经点或起终点坐标"}

        trajectory = generate_trajectory(
            waypoints=waypoints,
            uid=uid,
            speed_ms=speed,
            start_time_ms=start_time,
            interval_ms=interval,
            reg_sign=reg_sign,
            classification=classification,
            operating_status=operating_status,
        )

        # 保存
        os.makedirs(output_dir, exist_ok=True)
        if filename:
            out_name = filename if filename.endswith(".json") else filename + ".json"
        else:
            out_name = _make_ts_filename(f"scene_{uid}")

        out_path = os.path.join(output_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(trajectory, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "file": out_path,
            "points": len(trajectory),
            "uid": uid,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def gen_single_deviate(
    uid: str = "UAV_TEST_001",
    reg_sign: Optional[str] = None,
    classification: int = 2,
    route_name: Optional[str] = None,
    points: Optional[str] = None,
    start_lon: Optional[float] = None,
    start_lat: Optional[float] = None,
    end_lon: Optional[float] = None,
    end_lat: Optional[float] = None,
    altitude: float = 30.0,
    speed: float = 15.0,
    interval: int = 1000,
    deviate: bool = True,
    deviate_offset: float = 0.001,
    deviate_start_index: int = 5,
    operating_status: int = 2,
    output_dir: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    单机偏离航路数据生成（在航线飞行基础上叠加坐标偏移）

    对应: tools/create_data_scene.py generate_trajectory() + apply_deviation()
    """
    from tools.create_data_scene import build_waypoints, generate_trajectory, apply_deviation

    if output_dir is None:
        output_dir = os.path.join(_SCRIPT_DIR, "mock")

    # 构造 args 用于 build_waypoints
    ns = argparse.Namespace(
        route_name=route_name,
        route_id=None,
        points=points,
        start_lon=start_lon,
        start_lat=start_lat,
        end_lon=end_lon,
        end_lat=end_lat,
        altitude=altitude,
        start_alt=None,
        end_alt=None,
        speed=speed,
        start_time=None,
        interval=interval,
    )

    try:
        waypoints = build_waypoints(ns)
        if not waypoints or len(waypoints) < 2:
            return {"success": False, "error": "至少需要2个航路点，请提供途经点或起终点坐标"}

        trajectory = generate_trajectory(
            waypoints=waypoints,
            uid=uid,
            speed_ms=speed,
            interval_ms=interval,
            reg_sign=reg_sign,
            classification=classification,
            operating_status=operating_status,
        )

        # 叠加偏离
        if deviate:
            apply_deviation(trajectory, deviate_offset, deviate_start_index)

        # 保存
        os.makedirs(output_dir, exist_ok=True)
        if filename:
            out_name = filename if filename.endswith(".json") else filename + ".json"
        else:
            prefix = f"deviate_{uid}"
            out_name = _make_ts_filename(prefix)

        out_path = os.path.join(output_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(trajectory, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "file": out_path,
            "points": len(trajectory),
            "uid": uid,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================ 批量预设信息（供前端展示） ============================

# 从 create_data_scenes.py 的 BATCH_CONFIGS 提取预设信息
BATCH_PRESETS = [
    {"index": 0, "name": "新疆空域1-平行飞行", "count": 100, "lat": 40.818724, "lng": 85.070136, "spacing": 1000},
    {"index": 1, "name": "新疆空域2-平行飞行", "count": 100, "lat": 41.5, "lng": 86.0, "spacing": 1000},
    {"index": 2, "name": "西藏空域1-平行飞行", "count": 100, "lat": 29.65, "lng": 91.1, "spacing": 1000},
    {"index": 3, "name": "西藏空域2-平行飞行", "count": 100, "lat": 29.65, "lng": 91.1, "spacing": 1000},
    {"index": 4, "name": "青海空域1-平行飞行", "count": 300, "lat": 35.5, "lng": 96.0, "spacing": 1000},
    {"index": 5, "name": "青海空域2-平行飞行", "count": 500, "lat": 36.0, "lng": 96.5, "spacing": 1000},
    {"index": 6, "name": "甘肃空域1-平行飞行", "count": 100, "lat": 38.0, "lng": 103.0, "spacing": 1000},
    {"index": 7, "name": "内蒙古空域1-平行飞行", "count": 100, "lat": 40.82, "lng": 111.75, "spacing": 1000},
    {"index": 8, "name": "新疆空域3-平行飞行", "count": 100, "lat": 41.0, "lng": 86.5, "spacing": 1000},
    {"index": 9, "name": "西藏空域3-平行飞行", "count": 100, "lat": 29.65, "lng": 91.1, "spacing": 1000},
    {"index": 10, "name": "青海空域3-平行飞行", "count": 500, "lat": 36.0, "lng": 97.0, "spacing": 1000},
]
