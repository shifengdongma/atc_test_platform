# -*- coding: utf-8 -*-
"""
JSON 数据文件管理器 — 数据库存储 + 文件系统双向同步

功能：
- 文件 CRUD：上传/下载/重命名/删除/分类搜索
- 与 mock/ 目录双向同步：导入文件 → 数据库，导出数据库 → 文件
- 支持分页查询、分类筛选、关键字搜索
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from db_manager import query, query_one, insert, update, delete, query_all, _now

TABLE = "sim_json_files"
_MOCK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock")


def _ensure_mock_dir() -> str:
    os.makedirs(_MOCK_DIR, exist_ok=True)
    return _MOCK_DIR


# ── 文件 CRUD ───────────────────────────────────────────────────────

def list_files(
    category: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """分页查询文件列表。"""
    where_parts = []
    params: List[Any] = []

    if category:
        where_parts.append("category = ?")
        params.append(category)
    if keyword:
        where_parts.append("(name LIKE ? OR description LIKE ? OR tags LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])

    where = " AND ".join(where_parts) if where_parts else "1=1"

    # 总数
    rows = query(TABLE, where=where, params=tuple(params))
    total = len(rows)

    # 分页
    offset = (page - 1) * page_size
    rows = rows[offset:offset + page_size]

    return {"files": rows, "total": total, "page": page, "page_size": page_size}


def get_file(file_id: int) -> Optional[Dict[str, Any]]:
    """获取单个文件详情。"""
    return query_one(TABLE, file_id)


def save_file(data: Dict[str, Any]) -> int:
    """新增或更新文件。如果 data 含 id 则更新，否则新增。"""
    file_id = data.pop("id", None)
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
    """删除文件记录。"""
    return delete(TABLE, file_id)


def update_file(file_id: int, data: Dict[str, Any]) -> bool:
    """更新文件字段（名称/描述/标签等）。"""
    return update(TABLE, file_id, data)


# ── 双向同步 ────────────────────────────────────────────────────────

def import_from_mock() -> Dict[str, Any]:
    """扫描 mock/ 目录下所有 JSON 文件，导入到数据库。"""
    _ensure_mock_dir()
    imported, skipped, errors = 0, 0, 0
    try:
        for fname in sorted(os.listdir(_MOCK_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(_MOCK_DIR, fname)
            try:
                size = os.path.getsize(fpath)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                # 检测分类
                category = _detect_category(fname, content)

                save_file({
                    "name": fname,
                    "category": category,
                    "content": content,
                    "size_bytes": size,
                    "description": f"从 mock/ 导入: {fname}",
                    "created_by": "import",
                })
                imported += 1
            except Exception:
                errors += 1
    except FileNotFoundError:
        pass
    return {"imported": imported, "skipped": skipped, "errors": errors}


def export_to_mock(file_id: int) -> Dict[str, Any]:
    """将数据库中的文件导出到 mock/ 目录。"""
    record = query_one(TABLE, file_id)
    if not record:
        return {"success": False, "message": f"文件 {file_id} 不存在"}
    _ensure_mock_dir()
    fname = record.get("name", f"export_{file_id}.json")
    fpath = os.path.join(_MOCK_DIR, fname)
    try:
        content = record.get("content", "")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "message": f"已导出到 {fpath}", "path": fpath}
    except Exception as e:
        return {"success": False, "message": str(e)}


def export_to_mock_batch(file_ids: List[int]) -> Dict[str, Any]:
    """批量导出到 mock/ 目录。"""
    results = []
    for fid in file_ids:
        results.append(export_to_mock(fid))
    success = sum(1 for r in results if r.get("success"))
    return {"success": success, "total": len(file_ids), "results": results}


def download_file(file_id: int) -> Optional[Dict[str, Any]]:
    """获取文件内容用于下载。"""
    record = query_one(TABLE, file_id)
    if not record:
        return None
    return {
        "name": record.get("name", ""),
        "content": record.get("content", ""),
        "category": record.get("category", ""),
    }


# ── 辅助 ────────────────────────────────────────────────────────────

def _detect_category(fname: str, content: str) -> str:
    """根据文件名和内容推断分类。"""
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
    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            if "flightPlanList" in obj or "routeList" in obj:
                return "route"
            if "_meta" in obj and "task" in obj:
                return "template"
        if isinstance(obj, list) and len(obj) > 0:
            if isinstance(obj[0], dict):
                if "uniqueProductIdentificationCode" in obj[0]:
                    return "telemetry"
    except (json.JSONDecodeError, TypeError):
        pass
    return "telemetry"


def get_categories() -> List[str]:
    """获取所有分类列表。"""
    return ["route", "telemetry", "scene", "template"]


# ── 保存生成数据 ────────────────────────────────────────────────────

def save_generated(name: str, content: str, category: str = "telemetry",
                   created_by: str = "manual", description: str = "") -> int:
    """保存前端生成的 JSON 数据到数据库。"""
    data = {
        "name": name,
        "category": category,
        "content": content,
        "size_bytes": len(content.encode("utf-8")),
        "description": description or f"手动生成: {name}",
        "created_by": created_by,
    }
    return save_file(data)
