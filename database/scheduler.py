# -*- coding: utf-8 -*-
"""
定时任务调度器 — cron 表达式驱动的仿真任务自动执行

使用后台线程每 30 秒检查 cron 匹配，触发仿真任务执行。
任务和日志通过 mysql_db_manager 存储（MySQL 优先，不可用时自动降级 SQLite）。
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

TASK_TABLE = "sim_scheduled_tasks"
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


# ── 任务调度器 ──────────────────────────────────────────────────────

class TaskScheduler:
    """定时任务调度器。"""

    def __init__(self, execute_callback: Optional[Callable] = None):
        init_tables()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._execute_callback = execute_callback
        self._last_check: Dict[int, datetime] = {}  # task_id -> last triggered time

    def start(self) -> None:
        """启动后台调度线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()
        print("[Scheduler] 定时任务调度器已启动")

    def stop(self) -> None:
        """停止调度线程。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        print("[Scheduler] 定时任务调度器已停止")

    def _loop(self) -> None:
        """后台循环：每 30 秒检查一次。"""
        while self._running:
            try:
                self._check_and_execute()
            except Exception as e:
                print(f"[Scheduler] 检查异常: {e}")
            time.sleep(30)

    def _check_and_execute(self) -> None:
        """检查所有启用的任务，匹配 cron 则执行。"""
        now = datetime.now()
        tasks = query(TASK_TABLE, where="enabled = 1", order_by="id")

        for task in tasks:
            task_id = task["id"]
            cron_expr = task.get("cron_expr", "")
            if not cron_expr:
                continue

            if not cron_matches(cron_expr, now):
                continue

            # 防重复：同一分钟内不重复触发
            last = self._last_check.get(task_id)
            if last and (now - last).total_seconds() < 60:
                continue

            self._last_check[task_id] = now
            self._execute_task(task)

    def _execute_task(self, task: Dict[str, Any]) -> None:
        """执行单个定时任务。"""
        task_id = task["id"]
        task_name = task.get("name", f"task-{task_id}")
        sim_mode = task.get("sim_mode", "replay")

        started = _now()
        log_id = insert(LOG_TABLE, {
            "task_id": task_id,
            "task_type": "scheduled",
            "status": "running",
            "message": f"定时任务触发: {task_name} (模式={sim_mode})",
            "started_at": started,
        })

        try:
            if self._execute_callback:
                result = self._execute_callback(task)
                msg = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            else:
                msg = f"任务 {task_name} 已触发（无需执行回调）"

            update(LOG_TABLE, log_id, {
                "status": "success",
                "message": msg,
                "finished_at": _now(),
            })

            # 更新任务最后执行时间
            update(TASK_TABLE, task_id, {
                "last_run_at": started,
                "next_run_at": (next_cron_time(task.get("cron_expr", "")) or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
            })

            print(f"[Scheduler] 任务完成: {task_name}")

        except Exception as e:
            update(LOG_TABLE, log_id, {
                "status": "failed",
                "message": str(e),
                "finished_at": _now(),
            })
            print(f"[Scheduler] 任务失败: {task_name} — {e}")

    # ── 任务管理 ─────────────────────────────────────────────────────

    def list_tasks(self) -> List[Dict[str, Any]]:
        return query_all(TASK_TABLE)

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        return query_one(TASK_TABLE, task_id)

    def add_task(self, data: Dict[str, Any]) -> int:
        return insert(TASK_TABLE, data)

    def update_task(self, task_id: int, data: Dict[str, Any]) -> bool:
        return update(TASK_TABLE, task_id, data)

    def delete_task(self, task_id: int) -> bool:
        return delete(TASK_TABLE, task_id)

    def pause_task(self, task_id: int) -> bool:
        return update(TASK_TABLE, task_id, {"enabled": 0})

    def resume_task(self, task_id: int) -> bool:
        return update(TASK_TABLE, task_id, {"enabled": 1})

    def run_now(self, task_id: int) -> Dict[str, Any]:
        """立即执行一次任务。"""
        task = query_one(TASK_TABLE, task_id)
        if not task:
            return {"success": False, "message": "任务不存在"}
        threading.Thread(target=self._execute_task, args=(task,), daemon=True).start()
        return {"success": True, "message": f"任务 {task.get('name','')} 已触发"}

    def get_history(self, task_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        return query(LOG_TABLE, where=f"task_id = {int(task_id)}", order_by="id DESC")[:limit]


# ── 全局单例 ────────────────────────────────────────────────────────

_scheduler: Optional[TaskScheduler] = None


def get_scheduler(execute_callback: Optional[Callable] = None) -> TaskScheduler:
    """获取调度器单例。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler(execute_callback=execute_callback)
        _scheduler.start()
    return _scheduler
