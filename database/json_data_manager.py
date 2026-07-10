# -*- coding: utf-8 -*-
"""
JSON 数据文件管理器 — 文件路径存储 + 数据库元数据

核心变更（v2）：
- 数据库只存 file_path，不存 content（防止大文件撑爆数据库）
- 自动检测告警类型(alarm_type)、模拟器ID(simulator_id)、关联航线(linked_route)
- 支持分页预览大文件
- 支持航线关联校验
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional

# 使用集中管理的路径常量
import sys as _sys
_common_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common")
if _common_path not in _sys.path:
    _sys.path.insert(0, _common_path)
from config import MOCK_DIR

from mysql_db_manager import query, query_one, insert, update, delete, query_all, _now

TABLE = "sim_json_files"

# 确保数据库表已创建（MySQL 优先，SQLite 降级）
from mysql_db_manager import init_tables as _init_tables
_init_tables()


# ── 路径工具 ──────────────────────────────────────────────────────────

def _ensure_mock_dir() -> str:
    """确保 data/mock/ 目录存在并返回路径。"""
    os.makedirs(MOCK_DIR, exist_ok=True)
    return MOCK_DIR


def _get_storage_dir() -> str:
    """获取 JSON 文件存储目录（统一为 data/mock/）。"""
    return _ensure_mock_dir()


# ── 元数据检测 ───────────────────────────────────────────────────────

def _detect_alarm_type(fname: str, content_sample: str = "") -> str:
    """从文件名和内容采样检测告警类型。

    优先级：文件名关键字 > 内容格式回退
    """
    # 文件名关键字匹配
    if "碰撞预警" in fname:
        return "碰撞预警"
    if "偏航" in fname:
        return "偏航"
    if "航路最低安全高度" in fname or "最低安全高度" in fname:
        return "最低安全高度"
    if "nfz" in fname.lower() or "禁飞" in fname:
        return "禁飞区"

    # 内容格式回退（使用 web_server 中的 _detect_file_format 逻辑）
    if content_sample:
        fmt = _simple_format_detect(content_sample)
        if fmt == "telemetry":
            return "正常遥测"
        if fmt in ("redis_route", "flight_plan"):
            return "飞行计划"

    return "正常遥测"


def _simple_format_detect(content_str: str) -> str:
    """简化的格式检测（不依赖 web_server.py）。"""
    if not content_str or not content_str.strip():
        return "unknown"
    try:
        data = json.loads(content_str[:65536])
    except (json.JSONDecodeError, TypeError):
        return "unknown"

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        first = data[0]
        if "key" in first and "value" in first:
            return "redis_route"
        if "longitude" in first and "latitude" in first:
            return "telemetry"
        if "flightPlanList" in first:
            return "flight_plan"
    if isinstance(data, dict):
        if "flightPlanList" in data:
            return "flight_plan"
    return "unknown"


def _extract_simulator_id(content: str) -> str:
    """从 JSON 内容提取无人机唯一标识 (uniqueProductIdentificationCode)。

    支持格式：
    - 遥测数组: [{"uniqueProductIdentificationCode": "xxx", ...}, ...]
    - Redis航线: [{"key": "UAV_00001", "value": {...}}, ...]
    - 单条航线: {"uniqueProductIdentificationCode": "xxx", ...}
    """
    if not content:
        return ""
    try:
        data = json.loads(content[:65536])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            first = data[0]
            # 遥测格式
            if "uniqueProductIdentificationCode" in first:
                return str(first["uniqueProductIdentificationCode"])
            # Redis route 格式
            if "key" in first:
                return str(first["key"])
        elif isinstance(data, dict):
            if "uniqueProductIdentificationCode" in data:
                return str(data["uniqueProductIdentificationCode"])
            # 嵌套格式
            if "value" in data and isinstance(data["value"], dict):
                val = data["value"]
                if "uniqueProductIdentificationCode" in val:
                    return str(val["uniqueProductIdentificationCode"])
    except (json.JSONDecodeError, TypeError, IndexError, KeyError):
        pass
    return ""


def _detect_linked_route(fname: str, content_sample: str = "") -> str:
    """从文件名和内容检测关联的航线名称。

    文件名模式：
    - {route_name}_碰撞预警_{uid}.json
    - {route_name}航路偏航数据_{param}.json
    - {route_name}航路最低安全高度数据_{param}.json

    内容回退：提取 flightTaskName 字段。
    """
    # 从文件名提取
    # 模式1: xxx_碰撞预警_xxx.json
    m = re.match(r"^(.+?)_碰撞预警_", fname)
    if m:
        return m.group(1)

    # 模式2: xxx航路偏航数据xxx.json
    m = re.match(r"^(.+?)航路偏航数据", fname)
    if m:
        return m.group(1)

    # 模式3: xxx航路最低安全高度xxx.json
    m = re.match(r"^(.+?)航路最低安全高度", fname)
    if m:
        return m.group(1)

    # 模式4: 从内容中提取 flightTaskName
    if content_sample:
        try:
            data = json.loads(content_sample[:65536])
            # 列表格式: 取第一个元素的 flightTaskName
            if isinstance(data, list) and data and isinstance(data[0], dict):
                first = data[0]
                # redis_route 格式
                if "value" in first and isinstance(first["value"], dict):
                    val = first["value"]
                    if "flightPlanList" in val and val["flightPlanList"]:
                        fp = val["flightPlanList"][0]
                        if isinstance(fp, dict) and fp.get("flightTaskName"):
                            return str(fp["flightTaskName"])
                # 直接格式
                if "flightTaskName" in first and first["flightTaskName"]:
                    return str(first["flightTaskName"])
            # 字典格式
            elif isinstance(data, dict):
                if "flightPlanList" in data and data["flightPlanList"]:
                    fp = data["flightPlanList"][0]
                    if isinstance(fp, dict) and fp.get("flightTaskName"):
                        return str(fp["flightTaskName"])
        except (json.JSONDecodeError, TypeError, IndexError, KeyError):
            pass

    return ""


def _detect_category(fname: str, content: str) -> str:
    """根据文件名和内容推断分类（保留兼容旧版）。"""
    name_lower = fname.lower()
    if "route" in name_lower:
        return "route"
    if "kafka_data" in name_lower or "telemetry" in name_lower:
        return "telemetry"
    if "scene" in name_lower:
        return "scene"
    if "template" in name_lower or "logistics" in name_lower or "patrol" in name_lower:
        return "template"
    # 通过 JSON 结构判断
    fmt = _simple_format_detect(content)
    if fmt == "redis_route" or fmt == "flight_plan":
        return "route"
    if fmt == "telemetry":
        return "telemetry"
    return "telemetry"


# ── 文件 CRUD ───────────────────────────────────────────────────────

def list_files(
    category: str = "",
    alarm_type: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """分页查询文件列表，支持按分类、告警类型、关键字过滤。"""
    where_parts = []
    params: List[Any] = []

    if category:
        where_parts.append("category = ?")
        params.append(category)
    if alarm_type:
        where_parts.append("alarm_type = ?")
        params.append(alarm_type)
    if keyword:
        where_parts.append("(name LIKE ? OR description LIKE ? OR tags LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])

    where = " AND ".join(where_parts) if where_parts else "1=1"

    rows = query(TABLE, where=where, params=tuple(params))
    total = len(rows)

    offset = (page - 1) * page_size
    rows = rows[offset:offset + page_size]

    return {"files": rows, "total": total, "page": page, "page_size": page_size}


def get_file(file_id: int) -> Optional[Dict[str, Any]]:
    """获取单个文件详情（含元数据，不含完整内容）。"""
    return query_one(TABLE, file_id)


def save_file(data: Dict[str, Any]) -> int:
    """新增或更新文件。

    如果 data 含 'content'，将其写入磁盘 data/mock/{name}，
    数据库仅存储 file_path 和元数据。
    自动检测 alarm_type / simulator_id / linked_route（未提供时）。
    """
    content = data.pop("content", None)
    file_id = data.pop("id", None)

    # 写入磁盘
    if content is not None:
        name = data.get("name", f"file_{int(time.time())}.json")
        storage_dir = _get_storage_dir()
        fpath = os.path.join(storage_dir, name)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        data["file_path"] = fpath
        data["size_bytes"] = len(content.encode("utf-8"))

        # 自动检测元数据（仅在未显式提供时）
        if "alarm_type" not in data or not data.get("alarm_type"):
            data["alarm_type"] = _detect_alarm_type(name, content[:4096])
        if "simulator_id" not in data or not data.get("simulator_id"):
            data["simulator_id"] = _extract_simulator_id(content[:65536])
        if "linked_route" not in data or not data.get("linked_route"):
            data["linked_route"] = _detect_linked_route(name, content[:4096])

    # 确保 source 字段
    if "source" not in data:
        # 从旧的 created_by 映射
        created_by = data.pop("created_by", None)
        if created_by:
            data["source"] = created_by
        else:
            data["source"] = "manual"

    # 更新现有记录
    if file_id:
        existing = query_one(TABLE, int(file_id))
        if existing:
            update(TABLE, int(file_id), data)
            return int(file_id)

    # 去重：同名文件覆盖
    name = data.get("name", "")
    if name:
        existing = query(TABLE, where="name = ?", params=(name,))
        if existing:
            update(TABLE, existing[0]["id"], data)
            return existing[0]["id"]

    return insert(TABLE, data)


def delete_file(file_id: int) -> bool:
    """删除文件记录（同时删除磁盘文件）。"""
    record = query_one(TABLE, file_id)
    if record:
        fpath = record.get("file_path", "")
        if fpath and os.path.exists(fpath):
            try:
                os.remove(fpath)
            except OSError:
                pass
    return delete(TABLE, file_id)


def update_file(file_id: int, data: Dict[str, Any]) -> bool:
    """更新文件字段（名称/描述/标签等），不修改磁盘文件。"""
    # 过滤掉不应该通过此接口修改的字段
    safe_fields = {"name", "category", "alarm_type", "linked_route",
                   "description", "tags", "source"}
    clean = {k: v for k, v in data.items() if k in safe_fields}
    return update(TABLE, file_id, clean)


# ── 双向同步 ────────────────────────────────────────────────────────

def import_from_mock() -> Dict[str, Any]:
    """扫描 data/mock/ 目录下所有 JSON 文件，导入元数据到数据库。

    数据库只存 file_path，不复制文件内容。
    """
    _ensure_mock_dir()
    imported, skipped, errors = 0, 0, 0
    try:
        for fname in sorted(os.listdir(MOCK_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(MOCK_DIR, fname)
            try:
                size = os.path.getsize(fpath)
                # 读取采样用于元数据检测
                with open(fpath, "r", encoding="utf-8") as f:
                    sample = f.read(65536)

                category = _detect_category(fname, sample)
                alarm_type = _detect_alarm_type(fname, sample)
                simulator_id = _extract_simulator_id(sample)
                linked_route = _detect_linked_route(fname, sample)

                save_file({
                    "name": fname,
                    "category": category,
                    "alarm_type": alarm_type,
                    "file_path": fpath,
                    "simulator_id": simulator_id,
                    "linked_route": linked_route,
                    "size_bytes": size,
                    "source": "import",
                    "description": f"从 mock/ 导入: {fname}",
                })
                imported += 1
            except Exception:
                errors += 1
    except FileNotFoundError:
        pass
    return {"imported": imported, "skipped": skipped, "errors": errors}


def export_to_mock(file_id: int) -> Dict[str, Any]:
    """将数据库记录对应的文件复制/确认到 data/mock/ 目录。"""
    record = query_one(TABLE, file_id)
    if not record:
        return {"success": False, "message": f"文件 {file_id} 不存在"}

    fpath = record.get("file_path", "")
    name = record.get("name", f"export_{file_id}.json")

    if fpath and os.path.exists(fpath):
        mock_dir = _ensure_mock_dir()
        # 如果文件已在 mock/ 目录内，无需复制
        if os.path.abspath(fpath).startswith(os.path.abspath(mock_dir)):
            return {"success": True, "message": "文件已在 mock/ 目录", "path": fpath}
        # 从外部路径复制到 mock/
        dest = os.path.join(mock_dir, name)
        shutil.copy2(fpath, dest)
        return {"success": True, "message": f"已复制到 {dest}", "path": dest}

    return {"success": False, "message": "文件内容在磁盘上不可用"}


def export_to_mock_batch(file_ids: List[int]) -> Dict[str, Any]:
    """批量导出到 mock/ 目录。"""
    results = [export_to_mock(fid) for fid in file_ids]
    success = sum(1 for r in results if r.get("success"))
    return {"success": success, "total": len(file_ids), "results": results}


def download_file(file_id: int) -> Optional[Dict[str, Any]]:
    """获取文件信息用于下载（从磁盘读取内容）。"""
    record = query_one(TABLE, file_id)
    if not record:
        return None
    fpath = record.get("file_path", "")
    content = ""
    if fpath and os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    return {
        "name": record.get("name", ""),
        "content": content,
        "category": record.get("category", ""),
        "file_path": fpath,
    }


# ── 分页预览 ────────────────────────────────────────────────────────

def preview_file(file_id: int, offset: int = 0, limit: int = 500) -> Dict[str, Any]:
    """从磁盘按行分页读取文件内容。

    Returns:
        {"id": ..., "name": ..., "total_lines": N, "offset": N,
         "limit": N, "lines": [...], "has_more": bool}
    """
    record = query_one(TABLE, file_id)
    if not record:
        return {"error": "文件不存在"}

    fpath = record.get("file_path", "")
    if not fpath or not os.path.exists(fpath):
        return {"error": "文件不存在于磁盘"}

    lines = []
    total_lines = 0
    target_start = offset
    target_end = offset + limit

    with open(fpath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if target_start <= i < target_end:
                lines.append(line.rstrip("\n\r"))
            total_lines += 1
            # 大文件提前停止计数（避免遍历整个文件）
            if total_lines > 100000 and target_end < total_lines:
                # 已经读到需要的行且知道还有很多，快速跳到末尾计数
                break

    # 如果提前退出了，计算实际总行数
    if total_lines > 100000 and target_end <= total_lines:
        # 用更高效的方式获取总行数
        fsize = os.path.getsize(fpath)
        if fsize > 10 * 1024 * 1024:  # > 10MB
            total_lines = _count_lines_fast(fpath)

    return {
        "id": file_id,
        "name": record.get("name", ""),
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "lines": lines,
        "has_more": (offset + limit) < total_lines,
    }


def _count_lines_fast(fpath: str) -> int:
    """快速统计文件行数（大文件用）。"""
    count = 0
    with open(fpath, "rb") as f:
        # 以 8MB 块读取，统计换行符
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            count += chunk.count(b"\n")
    return count


def read_file_content_partial(file_id: int, max_chars: int = 102400) -> Dict[str, Any]:
    """获取文件的部分内容（用于编辑和详情展示）。

    Args:
        file_id: 文件ID
        max_chars: 最大读取字符数（默认 100KB）

    Returns:
        {"content": "...", "truncated": bool, "total_size": int}
    """
    record = query_one(TABLE, file_id)
    if not record:
        return {"error": "文件不存在"}

    fpath = record.get("file_path", "")
    if not fpath or not os.path.exists(fpath):
        return {"error": "文件不存在于磁盘"}

    total_size = os.path.getsize(fpath)
    truncated = total_size > max_chars

    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read(max_chars)

    return {
        "content": content,
        "truncated": truncated,
        "total_size": total_size,
        "message": f"仅显示前 {max_chars // 1024}KB" if truncated else "",
    }


# ── 航线关联校验 ────────────────────────────────────────────────────

def validate_route_correlation(linked_route: str) -> Dict[str, Any]:
    """校验关联航线名称是否在数据库 air_route 表中存在。

    Returns:
        {"valid": True/False/None, "message": str}
        None 表示无法连接数据库验证
    """
    if not linked_route:
        return {"valid": False, "message": "未指定航线"}

    # 尝试从 create_data_scenes 导入查询函数
    try:
        import importlib.util
        # 尝试动态导入 — 该模块依赖 mysqldbclient
        spec = importlib.util.find_spec("create_data_scenes")
        if spec is None:
            # 尝试从 tools 路径加载
            tools_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "utm_simulator", "tools",
            )
            if tools_path not in __import__("sys").path:
                __import__("sys").path.insert(0, tools_path)
            spec = importlib.util.find_spec("create_data_scenes")

        if spec is not None:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            route_data = module.query_air_route_single(route_name=linked_route)
            if route_data:
                return {
                    "valid": True,
                    "message": f'航线 "{linked_route}" 在数据库中确认存在',
                }
            else:
                return {
                    "valid": False,
                    "message": f'航线 "{linked_route}" 在数据库中不存在',
                }
    except Exception as e:
        return {
            "valid": None,
            "message": f"无法连接航线数据库进行验证: {e}",
        }

    return {"valid": None, "message": "无法导入航线查询模块"}


# ── 分类管理 ────────────────────────────────────────────────────────

def get_categories() -> List[str]:
    """获取所有分类列表（从数据库 DISTINCT 读取）。"""
    rows = query_all(TABLE)
    cats = sorted(set(r.get("category", "") for r in rows if r.get("category", "").strip()))
    return cats


def get_alarm_types() -> List[str]:
    """获取所有告警类型列表。"""
    rows = query_all(TABLE)
    types = sorted(set(r.get("alarm_type", "") for r in rows if r.get("alarm_type", "").strip()))
    return types


def rename_category(old_name: str, new_name: str) -> Dict[str, Any]:
    """重命名分类：批量更新所有该分类的文件。"""
    if not old_name or not new_name:
        return {"success": False, "message": "分类名不能为空"}
    rows = query(TABLE, where="category = ?", params=(old_name,))
    count = len(rows)
    for row in rows:
        update(TABLE, row["id"], {"category": new_name})
    return {"success": True, "message": f"已将 {count} 个文件从 '{old_name}' 改为 '{new_name}'", "count": count}


def delete_category(name: str) -> Dict[str, Any]:
    """删除分类：清空所有该分类文件的分类字段。"""
    if not name:
        return {"success": False, "message": "分类名不能为空"}
    rows = query(TABLE, where="category = ?", params=(name,))
    count = len(rows)
    for row in rows:
        update(TABLE, row["id"], {"category": ""})
    return {"success": True, "message": f"已清空 {count} 个文件的分类 '{name}'", "count": count}


# ── 保存生成数据 ────────────────────────────────────────────────────

def save_generated(name: str, content: str, category: str = "telemetry",
                   created_by: str = "manual", description: str = "",
                   alarm_type: str = "", linked_route: str = "") -> int:
    """保存前端/AI 生成的 JSON 数据：写入磁盘 + 记录元数据到数据库。"""
    data = {
        "name": name,
        "category": category,
        "content": content,  # save_file 会处理磁盘写入
        "size_bytes": len(content.encode("utf-8")),
        "source": "generated" if created_by == "ai" else "manual",
        "description": description or f"生成: {name}",
        "alarm_type": alarm_type,
        "linked_route": linked_route,
        "created_by": created_by,
    }
    return save_file(data)
