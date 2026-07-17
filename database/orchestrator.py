# -*- coding: utf-8 -*-
"""
场景编排调度器 — cron 表达式驱动的场景自动执行

使用后台线程每 30 秒检查 cron 匹配，触发场景中所有任务的仿真执行。
场景、任务和文件关联通过 mysql_db_manager 存储
（MySQL 优先，不可用时自动降级 SQLite）。
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from mysql_db_manager import (
    query, query_one, insert, update, delete, query_all, _now, init_tables,
)

SCENE_TABLE = "sim_scenes"
TASK_TABLE = "sim_scene_tasks"
TASK_FILE_TABLE = "sim_scene_task_files"
LOG_TABLE = "sim_task_logs"


# ── Cron 匹配 ───────────────────────────────────────────────────────

def _match_cron_field(value: int, field: str) -> bool:
    """匹配单个 cron 字段。field 可以是 *, */n, n, n-m, n,m,... """
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        if part == "*":
            return True
        if "/" in part:
            base, step = part.split("/")
            if base == "*":
                base = 0
            else:
                base = int(base)
            step = int(step)
            if (value - base) % step == 0:
                return True
        elif "-" in part:
            lo, hi = part.split("-")
            if int(lo) <= value <= int(hi):
                return True
        else:
            if int(part) == value:
                return True
    return False


def cron_matches(cron_expr: str, dt: Optional[datetime] = None) -> bool:
    """检查给定时间（默认现在）是否匹配 cron 表达式（5字段：分 时 日 月 周）。"""
    if not cron_expr:
        return False
    dt = dt or datetime.now()
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    return (
        _match_cron_field(dt.minute, minute)
        and _match_cron_field(dt.hour, hour)
        and _match_cron_field(dt.day, dom)
        and _match_cron_field(dt.month, month)
        and _match_cron_field(dt.isoweekday() % 7, dow)  # Sunday=0
    )


def next_cron_time(cron_expr: str, after: Optional[datetime] = None) -> Optional[datetime]:
    """计算 cron 表达式的下一次触发时间（近似，向后搜索最多 365 天）。"""
    after = after or datetime.now()
    dt = after.replace(second=0, microsecond=0) + time.resolution
    for _ in range(365 * 24 * 60):  # 最多搜一年
        dt = dt + time.resolution * 60  # +1 分钟
        if cron_matches(cron_expr, dt):
            return dt
    return None


# ── 场景编排调度器 ──────────────────────────────────────────────────

class SceneOrchestrator:
    """场景编排调度器：管理场景、任务和文件关联，cron 触发执行。"""

    def __init__(self, execute_callback: Optional[Callable] = None):
        init_tables()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._execute_callback = execute_callback
        self._last_check: Dict[int, datetime] = {}  # scene_id -> last triggered time

    # ── 生命周期 ──────────────────────────────────────────────────

    def start(self) -> None:
        """启动后台调度线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="orchestrator")
        self._thread.start()
        print("[Orchestrator] 场景编排调度器已启动")

    def stop(self) -> None:
        """停止调度线程。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        print("[Orchestrator] 场景编排调度器已停止")

    def _loop(self) -> None:
        """后台循环：每 30 秒检查一次。"""
        while self._running:
            try:
                self._check_and_execute()
            except Exception as e:
                print(f"[Orchestrator] 检查异常: {e}")
            time.sleep(30)

    def _check_and_execute(self) -> None:
        """检查所有启用的场景，匹配 cron 则执行。"""
        now = datetime.now()
        try:
            scenes = query(SCENE_TABLE, where="enabled = 1", order_by="id")
        except Exception as e:
            print(f"[Orchestrator] 查询场景失败 (MySQL 可能不可用): {e}")
            return

        for scene in scenes:
            scene_id = scene["id"]
            cron_expr = scene.get("cron_expr", "")
            if not cron_expr:
                continue

            if not cron_matches(cron_expr, now):
                continue

            # 防重复：同一分钟内不重复触发
            last = self._last_check.get(scene_id)
            if last and (now - last).total_seconds() < 60:
                continue

            self._last_check[scene_id] = now
            self._execute_scene(scene)

    def _execute_scene(self, scene: Dict[str, Any]) -> None:
        """执行场景中的所有任务。"""
        scene_id = scene["id"]
        scene_name = scene.get("name", f"scene-{scene_id}")

        started = _now()
        log_id = insert(LOG_TABLE, {
            "task_id": scene_id,
            "scene_id": scene_id,
            "scene_task_name": scene_name,
            "task_type": "scene",
            "status": "running",
            "message": f"场景触发: {scene_name}",
            "started_at": started,
        })

        try:
            # 如果有外部回调（web_server 提供的仿真执行），优先使用
            if self._execute_callback:
                result = self._execute_callback(scene)
                msg = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            else:
                msg = f"场景 {scene_name} 已触发（无需执行回调）"

            update(LOG_TABLE, log_id, {
                "status": "success",
                "message": msg,
                "finished_at": _now(),
            })

            # 更新场景最后/下次执行时间
            update(SCENE_TABLE, scene_id, {
                "last_run_at": started,
                "next_run_at": (next_cron_time(scene.get("cron_expr", "")) or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
            })

            print(f"[Orchestrator] 场景完成: {scene_name}")

        except Exception as e:
            update(LOG_TABLE, log_id, {
                "status": "failed",
                "message": str(e),
                "finished_at": _now(),
            })
            print(f"[Orchestrator] 场景失败: {scene_name} — {e}")

    # ── 场景 CRUD ─────────────────────────────────────────────────

    def list_scenes(self) -> List[Dict[str, Any]]:
        """列出所有场景。"""
        return query_all(SCENE_TABLE)

    def get_scene(self, scene_id: int) -> Optional[Dict[str, Any]]:
        """获取单个场景。"""
        return query_one(SCENE_TABLE, scene_id)

    def create_scene(self, data: Dict[str, Any]) -> int:
        """创建场景。单文件场景可通过 data['tasks'] 内嵌创建任务和文件。

        单文件场景 data 格式:
            {name, env_id, scene_type='single', cron_expr, sim_mode, enabled,
             file_id, cycle_interval_sec}

        多文件场景 data 格式:
            {name, env_id, scene_type='multi', cron_expr, sim_mode, enabled,
             tasks: [{name, task_type, cycle_interval_sec, repeat_count,
                      execution_timeout_sec, files: [{file_id, interval_sec}]}]}
        """
        tasks_data = data.pop("tasks", None)
        file_id = data.pop("file_id", None)
        cycle_interval = data.pop("cycle_interval_sec", 0)

        now = _now()
        data["created_at"] = data.get("created_at", now)
        data["updated_at"] = data.get("updated_at", now)

        scene_id = insert(SCENE_TABLE, data)

        # 单文件场景：自动创建单个任务和单个文件
        if data.get("scene_type", "single") == "single":
            task_data = {
                "scene_id": scene_id,
                "name": data.get("name", ""),
                "task_type": "sequential",
                "cycle_interval_sec": cycle_interval,
                "repeat_count": 1,
                "execution_timeout_sec": 300,
                "sort_order": 0,
                "created_at": now,
            }
            task_id = insert(TASK_TABLE, task_data)
            if file_id:
                insert(TASK_FILE_TABLE, {
                    "task_id": task_id,
                    "file_id": int(file_id),
                    "interval_sec": 0,
                    "sort_order": 0,
                    "created_at": now,
                })

        # 多文件场景：创建多个任务和文件
        elif tasks_data:
            for ti, task_item in enumerate(tasks_data):
                task_files = task_item.pop("files", [])
                task_item["scene_id"] = scene_id
                task_item.setdefault("sort_order", ti)
                task_item.setdefault("created_at", now)
                task_id = insert(TASK_TABLE, task_item)
                for fi, file_item in enumerate(task_files):
                    insert(TASK_FILE_TABLE, {
                        "task_id": task_id,
                        "file_id": int(file_item.get("file_id", 0)),
                        "interval_sec": file_item.get("interval_sec", 0),
                        "sort_order": fi,
                        "created_at": now,
                    })

        return scene_id

    def update_scene(self, scene_id: int, data: Dict[str, Any]) -> bool:
        """更新场景基本信息。不修改关联的任务/文件。"""
        # 清理非表字段（与 create_scene 对齐）
        data.pop("tasks", None)
        data.pop("file_id", None)
        data.pop("cycle_interval_sec", None)
        data["updated_at"] = _now()
        return update(SCENE_TABLE, scene_id, data)

    def delete_scene(self, scene_id: int) -> bool:
        """删除场景及其所有关联的任务和文件。"""
        # 级联删除任务和文件
        tasks = self.list_tasks(scene_id)
        for task in tasks:
            self.delete_task(task["id"])
        return delete(SCENE_TABLE, scene_id)

    def toggle_scene(self, scene_id: int) -> Optional[Dict[str, Any]]:
        """切换场景启用/禁用状态。"""
        scene = query_one(SCENE_TABLE, scene_id)
        if not scene:
            return None
        new_enabled = 0 if scene.get("enabled") == 1 else 1
        update(SCENE_TABLE, scene_id, {"enabled": new_enabled, "updated_at": _now()})
        return query_one(SCENE_TABLE, scene_id)

    def run_scene_now(self, scene_id: int) -> Dict[str, Any]:
        """立即执行场景一次（异步线程）。"""
        scene = query_one(SCENE_TABLE, scene_id)
        if not scene:
            return {"success": False, "message": "场景不存在"}
        threading.Thread(target=self._execute_scene, args=(scene,), daemon=True).start()
        return {"success": True, "message": f"场景 '{scene.get('name', '')}' 已触发"}

    def get_scene_history(self, scene_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """获取场景执行历史。"""
        return query(LOG_TABLE, where=f"scene_id = {int(scene_id)}", order_by="id DESC")[:limit]

    # ── 任务 CRUD ─────────────────────────────────────────────────

    def list_tasks(self, scene_id: int) -> List[Dict[str, Any]]:
        """列出场景下所有任务（按 sort_order 排序）。"""
        return query(TASK_TABLE, where=f"scene_id = {int(scene_id)}", order_by="sort_order ASC, id ASC")

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """获取单个任务。"""
        return query_one(TASK_TABLE, task_id)

    def create_task(self, data: Dict[str, Any]) -> int:
        """创建任务。data 可包含 files 列表用于内嵌创建文件关联。

        data 格式:
            {scene_id, name, task_type, cycle_interval_sec, repeat_count,
             execution_timeout_sec, sort_order,
             files: [{file_id, interval_sec}]}
        """
        files_data = data.pop("files", None)
        data.setdefault("created_at", _now())
        task_id = insert(TASK_TABLE, data)
        if files_data:
            for fi, file_item in enumerate(files_data):
                insert(TASK_FILE_TABLE, {
                    "task_id": task_id,
                    "file_id": int(file_item.get("file_id", 0)),
                    "interval_sec": file_item.get("interval_sec", 0),
                    "sort_order": fi,
                    "created_at": _now(),
                })
        return task_id

    def update_task(self, task_id: int, data: Dict[str, Any]) -> bool:
        """更新任务（支持修改名称）。"""
        return update(TASK_TABLE, task_id, data)

    def delete_task(self, task_id: int) -> bool:
        """删除任务及其所有文件关联。"""
        # 删除关联文件
        task_files = self.list_task_files(task_id)
        for tf in task_files:
            delete(TASK_FILE_TABLE, tf["id"])
        return delete(TASK_TABLE, task_id)

    def reorder_tasks(self, scene_id: int, task_ids: List[int]) -> bool:
        """重新排序场景下的任务。"""
        for i, tid in enumerate(task_ids):
            update(TASK_TABLE, tid, {"sort_order": i})
        return True

    # ── 任务文件 CRUD ─────────────────────────────────────────────

    def list_task_files(self, task_id: int) -> List[Dict[str, Any]]:
        """列出任务下所有文件关联（按 sort_order 排序）。"""
        return query(TASK_FILE_TABLE, where=f"task_id = {int(task_id)}", order_by="sort_order ASC, id ASC")

    def add_task_file(self, data: Dict[str, Any]) -> int:
        """为任务添加文件关联。

        data: {task_id, file_id, interval_sec, sort_order}
        """
        data.setdefault("interval_sec", 0)
        data.setdefault("sort_order", 0)
        data.setdefault("created_at", _now())
        return insert(TASK_FILE_TABLE, data)

    def update_task_file(self, file_rel_id: int, data: Dict[str, Any]) -> bool:
        """更新任务文件关联（修改间隔等）。"""
        return update(TASK_FILE_TABLE, file_rel_id, data)

    def remove_task_file(self, file_rel_id: int) -> bool:
        """移除任务文件关联。"""
        return delete(TASK_FILE_TABLE, file_rel_id)


# ── 全局单例 ────────────────────────────────────────────────────────

_orchestrator: Optional[SceneOrchestrator] = None
_orch_lock = threading.RLock()


def get_orchestrator(execute_callback: Optional[Callable] = None) -> SceneOrchestrator:
    """获取编排调度器单例（线程安全）。"""
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator
    with _orch_lock:
        if _orchestrator is None:
            _orchestrator = SceneOrchestrator(execute_callback=execute_callback)
            _orchestrator.start()
        return _orchestrator
