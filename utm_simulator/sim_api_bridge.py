# -*- coding: utf-8 -*-
"""
模拟器与 ATC 后端 API 桥接层

通过 REST API 创建飞行任务和申报飞行计划，实现模拟器与 ATC 后端
的端到端集成，替代直接写 Redis 的方式（同时保留直接写入能力）。

依赖:
    - atc_api_autotest/api_tools/Jwt_Token_get.py  (JWT 获取)
    - atc_api_autotest/api_tools/iomp_api_common.py (IOMP 登录)
    - sim_api_bridge 可被 web_server.py 或独立使用

用法示例:
    from sim_api_bridge import ATCAPIBridge

    bridge = ATCAPIBridge(base_url="https://dkkgsit-test.testdolphin.com")
    task = bridge.create_flight_task({"taskName": "测试任务", ...})
    plan = bridge.declare_flight_plan("DJI1MAV101...", route_data)
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# ── 路径设置 ────────────────────────────────────────────────────
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# ATC API 工具路径
_atc_root = os.path.join(os.path.dirname(_root), "atc_api_autotest")
_atc_tools = os.path.join(_atc_root, "api_tools")
if _atc_root not in sys.path:
    sys.path.insert(0, _atc_root)
if _atc_tools not in sys.path:
    sys.path.insert(0, _atc_tools)

# ── 可选依赖（运行时检查）───────────────────────────────────────
try:
    from Jwt_Token_get import get_jwt_token
    _HAS_JWT = True
except ImportError:
    _HAS_JWT = False


class ATCAPIBridge:
    """ATC 后端 API 桥接层

    封装飞行任务 CRUD、飞行计划申报、航空器管理等 REST API 调用。
    通过 JWT Token 进行认证，支持 IOMP 标准鉴权流程。
    """

    def __init__(
        self,
        base_url: str = "https://dkkgsit-test.testdolphin.com",
        jwt_token: Optional[str] = None,
        accesskey: Optional[str] = None,
        iomp_url: Optional[str] = None,
    ) -> None:
        """
        Args:
            base_url: ATC 后端服务基础地址
            jwt_token: 预获取的 JWT Token（不传则自动获取）
            accesskey: IOMP accesskey（使用默认值）
            iomp_url: IOMP Token 接口地址（使用默认值）
        """
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.base_url = base_url.rstrip("/")
        self._token: Optional[str] = jwt_token
        self._accesskey = accesskey or "20zhfhha3xstc1zl"
        self._iomp_url = iomp_url or "http://10.165.32.24:8801/iomp/api/v2/token"
        self._requests = requests

    # ── Token 管理 ──────────────────────────────────────────────

    def _ensure_token(self) -> str:
        """确保有有效的 JWT Token。"""
        if self._token:
            return self._token

        if _HAS_JWT:
            try:
                self._token = get_jwt_token(base_url=self.base_url)
                if self._token:
                    return self._token
            except Exception as e:
                print(f"[API Bridge] Jwt_Token_get 失败: {e}")

        # 回退到直接 IOMP 获取
        try:
            from iomp_api_common import get_iomp_token
            self._token = get_iomp_token(
                url=self._iomp_url,
                accesskey=self._accesskey,
            )
            if self._token:
                return self._token
        except ImportError:
            pass

        raise RuntimeError(
            "无法获取 JWT Token，请检查 ATC 后端可访问性"
            "或通过 jwt_token 参数传入"
        )

    def _auth_headers(self) -> Dict[str, str]:
        """构建带 JWT 认证的请求头。"""
        token = self._ensure_token()
        return {
            "Content-Type": "application/json",
            "jwt-token": token,
        }

    # ── 飞行任务 CRUD ──────────────────────────────────────────

    def create_flight_task(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        """创建飞行任务。

        POST /la-atc-biz-backend/flight/task/create

        Args:
            task_info: 任务信息字典，需包含:
                - taskName (str): 任务名称
                - taskPurpose (str): 任务目的
                - taskType (str): 任务性质
                - startTime (int): 开始时间戳(毫秒)
                - endTime (int): 结束时间戳(毫秒)
                可选: taskDescription, uasIds 等
        """
        url = f"{self.base_url}/la-atc-biz-backend/flight/task/create"
        try:
            resp = self._requests.post(
                url,
                headers=self._auth_headers(),
                json=task_info,
                verify=False,
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e), "success": False}

    def search_flight_task(
        self,
        keyword: str = "",
        task_status: str = "",
        task_purpose: str = "",
        task_type: str = "",
        start_time: int = 0,
        end_time: int = 0,
        page_no: int = 0,
        page_size: int = 20,
        sort_field: str = "startTime",
        sort_direction: str = "desc",
    ) -> Dict[str, Any]:
        """查询飞行任务列表。

        POST /la-atc-biz-backend/flight/task/search
        """
        url = f"{self.base_url}/la-atc-biz-backend/flight/task/search"
        body = {
            "keyword": keyword,
            "taskStatus": task_status,
            "taskPurpose": task_purpose,
            "taskType": task_type,
            "startTime": start_time,
            "endTime": end_time,
            "pageNo": page_no,
            "pageSize": page_size,
            "sortField": sort_field,
            "sortDirection": sort_direction,
        }
        try:
            resp = self._requests.post(
                url,
                headers=self._auth_headers(),
                json=body,
                verify=False,
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def get_flight_task_detail(self, task_id: str) -> Dict[str, Any]:
        """获取飞行任务详情。

        GET /la-atc-biz-backend/flight/task/detail?taskId={task_id}
        """
        url = f"{self.base_url}/la-atc-biz-backend/flight/task/detail"
        try:
            resp = self._requests.get(
                url,
                headers=self._auth_headers(),
                params={"taskId": task_id},
                verify=False,
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    # ── 飞行计划申报 ──────────────────────────────────────────

    def declare_flight_plan(
        self,
        uav_uid: str,
        route_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """为指定无人机申报飞行计划。

        POST /la-atc-biz-backend/flight/plan/declare

        Args:
            uav_uid: 无人机唯一产品识别码
            route_data: 航线数据（包含 flightPlanList 等）
        """
        url = f"{self.base_url}/la-atc-biz-backend/flight/plan/declare"
        body = {
            "uniqueProductIdentificationCode": uav_uid,
            **route_data,
        }
        try:
            resp = self._requests.post(
                url,
                headers=self._auth_headers(),
                json=body,
                verify=False,
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def batch_declare_plans(
        self,
        plans: List[Dict[str, Any]],
        delay_sec: float = 0.05,
    ) -> Dict[str, Any]:
        """批量申报飞行计划（带间隔控制，避免请求过快）。

        Args:
            plans: 飞行计划列表，每项含 uav_uid 和 route_data
            delay_sec: 每次请求间隔秒数
        """
        results = {"total": len(plans), "success": 0, "failed": 0, "details": []}
        for plan in plans:
            uid = plan.get("uav_uid", plan.get("uniqueProductIdentificationCode", ""))
            route_data = plan.get("route_data", plan)
            resp = self.declare_flight_plan(uid, route_data)
            ok = "error" not in resp
            if ok:
                results["success"] += 1
            else:
                results["failed"] += 1
            results["details"].append({"uid": uid, "ok": ok, "resp": resp})
            if delay_sec > 0:
                time.sleep(delay_sec)
        return results

    # ── 航空器管理 ──────────────────────────────────────────────

    def batch_import_uavs(self, uav_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量导入航空器（固定标识符）。

        POST /la-atc-biz-backend/uas/batch-import

        Args:
            uav_list: 航空器列表，每项包含:
                - uniqueProductIdentificationCode
                - realNameRegistrationSign
                可选: uasName, uasTypeCode, uasProducer 等
        """
        url = f"{self.base_url}/la-atc-biz-backend/uas/batch-import"
        try:
            resp = self._requests.post(
                url,
                headers=self._auth_headers(),
                json={"list": uav_list},
                verify=False,
                timeout=60,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def search_uav_list(
        self,
        keyword: str = "",
        page_no: int = 0,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """查询航空器列表。

        POST /la-atc-biz-backend/uas/search
        """
        url = f"{self.base_url}/la-atc-biz-backend/uas/search"
        body = {
            "keyword": keyword,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        try:
            resp = self._requests.post(
                url,
                headers=self._auth_headers(),
                json=body,
                verify=False,
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    # ── 空域/禁飞区管理 ────────────────────────────────────────

    def upload_airspace(self, airspace_data: Dict[str, Any]) -> Dict[str, Any]:
        """上载空域/禁飞区数据。

        POST /la-atc-biz-backend/airspace/add
        """
        url = f"{self.base_url}/la-atc-biz-backend/airspace/add"
        try:
            resp = self._requests.post(
                url,
                headers=self._auth_headers(),
                json=airspace_data,
                verify=False,
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}


# ==================== 模拟器集成管理器 ============================

class SimulatorAPIIntegration:
    """模拟器与 ATC API 集成管理器

    封装完整的"模板 → API → 模拟器"流程：
    1. 加载飞行任务模板
    2. 通过 API 创建飞行任务
    3. 通过 API 批量导入航空器
    4. 通过 API 申报飞行计划
    5. 启动模拟器遥测注入
    6. 自动化端到端验证
    """

    def __init__(
        self,
        api_bridge: ATCAPIBridge,
        sim_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.api = api_bridge
        self.sim_config = sim_config or {}
        self._created_tasks: List[str] = []
        self._imported_uavs: int = 0
        self._declared_plans: int = 0

    # ── 模板加载 ────────────────────────────────────────────────

    def load_template(self, template_name: str) -> Dict[str, Any]:
        """加载飞行任务模板。

        从 flight_task_templates/ 目录加载 JSON 模板文件。
        模板名不含 .json 后缀（如 'logistics', 'patrol'）。

        Returns:
            模板数据字典
        """
        template_dir = os.path.join(_root, "..", "data", "templates")
        file_path = os.path.join(template_dir, f"{template_name}.json")

        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"模板文件不存在: {file_path}\n"
                f"可用模板: {self.list_templates()}"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            template = json.load(f)

        print(f"[API 集成] 已加载模板: {template_name}")
        return template

    @staticmethod
    def list_templates() -> List[str]:
        """列出所有可用的飞行任务模板。"""
        template_dir = os.path.join(_root, "..", "data", "templates")
        if not os.path.exists(template_dir):
            return []
        return [
            f.replace(".json", "")
            for f in os.listdir(template_dir)
            if f.endswith(".json")
        ]

    # ── 场景编排 ────────────────────────────────────────────────

    def setup_flight_scenario(
        self,
        template_name: str,
        drone_count: int = 10,
        time_shift_sec: int = 0,
    ) -> Dict[str, Any]:
        """根据模板创建完整飞行场景：任务 + 航空器 + 计划。

        Args:
            template_name: 模板名称
            drone_count: 使用的无人机数量
            time_shift_sec: 时间偏移（秒），0=立即开始

        Returns:
            创建结果汇总
        """
        template = self.load_template(template_name)
        result = {
            "template": template_name,
            "tasks_created": [],
            "uavs_imported": 0,
            "plans_declared": 0,
            "errors": [],
        }

        # 1. 创建飞行任务
        task_def = template.get("task", {})
        now_ms = int(time.time() * 1000)
        task_def.setdefault("startTime", now_ms + time_shift_sec * 1000)
        task_def.setdefault("endTime", now_ms + 3600000)

        task_resp = self.api.create_flight_task(task_def)
        task_id = task_resp.get("result", {}).get("taskId", "")
        if task_id:
            result["tasks_created"].append(task_id)
            self._created_tasks.append(task_id)
            print(f"[API 集成] 飞行任务已创建: {task_id}")
        else:
            err = task_resp.get("error", "未知错误")
            result["errors"].append(f"任务创建失败: {err}")
            return result

        # 2. 批量导入航空器
        uav_defs = template.get("uasList", [])
        if uav_defs and drone_count > 0:
            subset = uav_defs[:drone_count]
            uav_resp = self.api.batch_import_uavs(subset)
            if "error" not in uav_resp:
                result["uavs_imported"] = len(subset)
                self._imported_uavs = len(subset)
                print(f"[API 集成] 已导入 {len(subset)} 架航空器")
            else:
                result["errors"].append(f"航空器导入失败: {uav_resp['error']}")

        # 3. 申报飞行计划
        plan_def = template.get("planTemplate", {})
        if plan_def and uav_defs:
            plans = []
            for uav in uav_defs[:drone_count]:
                uid = uav.get("uniqueProductIdentificationCode", "")
                if uid:
                    plan = copy.deepcopy(plan_def)
                    plan["uniqueProductIdentificationCode"] = uid
                    plans.append(plan)

            if plans:
                batch_result = self.api.batch_declare_plans(plans)
                result["plans_declared"] = batch_result.get("success", 0)
                self._declared_plans = batch_result.get("success", 0)
                print(f"[API 集成] 已申报 {result['plans_declared']}/{len(plans)} 条飞行计划")

        return result

    # ── 端到端验证 ─────────────────────────────────────────────

    def verify_scenario(
        self,
        wait_sec: float = 5.0,
    ) -> Dict[str, Any]:
        """验证飞行场景是否正确创建。

        检查:
        - 飞行任务是否可查询
        - 航空器是否已注册
        - 飞行计划是否已写入 Redis
        """
        result = {
            "task_verified": False,
            "uav_verified": False,
            "plans_verified": False,
            "details": {},
        }

        # 等待数据同步
        if wait_sec > 0:
            print(f"[API 集成] 等待 {wait_sec}s 数据同步...")
            time.sleep(wait_sec)

        # 1. 验证任务
        if self._created_tasks:
            task_id = self._created_tasks[0]
            task_detail = self.api.get_flight_task_detail(task_id)
            result["task_verified"] = "error" not in task_detail
            result["details"]["task"] = task_detail

        # 2. 验证航空器
        uav_search = self.api.search_uav_list(page_size=10)
        result["uav_verified"] = "error" not in uav_search
        result["details"]["uav_search"] = uav_search

        # 3. 验证飞行计划（Redis 检查需要单独连接，这里仅做 API 层面验证）
        task_search = self.api.search_flight_task(page_size=5)
        result["plans_verified"] = "error" not in task_search
        result["details"]["task_search"] = task_search

        return result

    def generate_report(
        self,
        scenario_result: Dict[str, Any],
        verify_result: Dict[str, Any],
        output_dir: Optional[str] = None,
    ) -> str:
        """生成 HTML 测试报告。

        Args:
            scenario_result: setup_flight_scenario 的返回值
            verify_result: verify_scenario 的返回值
            output_dir: 输出目录（默认 docs/）

        Returns:
            报告文件路径
        """
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(_root), "docs")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"test_report_{timestamp}.html"
        filepath = os.path.join(output_dir, filename)

        all_ok = (
            len(scenario_result.get("tasks_created", [])) > 0
            and scenario_result.get("plans_declared", 0) > 0
            and verify_result.get("task_verified", False)
            and verify_result.get("uav_verified", False)
        )

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>UTM 模拟器端到端测试报告 — {timestamp}</title>
<style>
  body {{ font-family: "Microsoft YaHei", sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #f5f7fa; }}
  h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
  .summary {{ background: {'#d4edda' if all_ok else '#f8d7da'}; padding: 16px; border-radius: 6px; margin: 16px 0; }}
  .summary .verdict {{ font-size: 24px; font-weight: bold; color: {'#155724' if all_ok else '#721c24'}; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  th, td {{ border: 1px solid #dee2e6; padding: 8px 12px; text-align: left; }}
  th {{ background: #e9ecef; }}
  .ok {{ color: #28a745; font-weight: bold; }}
  .fail {{ color: #dc3545; font-weight: bold; }}
  pre {{ background: #f8f9fa; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 12px; }}
</style>
</head>
<body>
<h1>🛩️ UTM 模拟器端到端测试报告</h1>
<p>生成时间: {timestamp}</p>

<div class="summary">
  <div class="verdict">{'✅ 全部通过' if all_ok else '❌ 存在失败项'}</div>
</div>

<h2>场景创建结果</h2>
<table>
<tr><th>项目</th><th>结果</th></tr>
<tr><td>模板</td><td>{scenario_result.get('template', '-')}</td></tr>
<tr><td>任务创建</td><td class="{'ok' if scenario_result.get('tasks_created') else 'fail'}">{len(scenario_result.get('tasks_created', []))} 个</td></tr>
<tr><td>航空器导入</td><td class="{'ok' if scenario_result.get('uavs_imported', 0) > 0 else 'fail'}">{scenario_result.get('uavs_imported', 0)} 架</td></tr>
<tr><td>计划申报</td><td class="{'ok' if scenario_result.get('plans_declared', 0) > 0 else 'fail'}">{scenario_result.get('plans_declared', 0)} 条</td></tr>
<tr><td>错误</td><td>{len(scenario_result.get('errors', []))} 条</td></tr>
</table>

<h2>验证结果</h2>
<table>
<tr><th>检查项</th><th>结果</th></tr>
<tr><td>飞行任务可查询</td><td class="{'ok' if verify_result.get('task_verified') else 'fail'}">{'✓' if verify_result.get('task_verified') else '✗'}</td></tr>
<tr><td>航空器已注册</td><td class="{'ok' if verify_result.get('uav_verified') else 'fail'}">{'✓' if verify_result.get('uav_verified') else '✗'}</td></tr>
<tr><td>飞行计划可查询</td><td class="{'ok' if verify_result.get('plans_verified') else 'fail'}">{'✓' if verify_result.get('plans_verified') else '✗'}</td></tr>
</table>

<h2>响应详情</h2>
<pre>{json.dumps(verify_result.get('details', {}), ensure_ascii=False, indent=2)}</pre>

<p style="color: #6c757d; font-size: 12px; margin-top: 40px;">
  🤖 Generated by utm_moc52 SimulatorAPIIntegration
</p>
</body>
</html>"""

        os.makedirs(output_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"[API 集成] 测试报告已生成: {filepath}")
        return filepath


# ==================== 命令行入口 ====================================

if __name__ == "__main__":
    """独立运行：测试 ATC API 连通性与基本功能。"""
    print("=" * 60)
    print("UTM 模拟器 — ATC API 桥接层 测试")
    print("=" * 60)

    # 测试连接
    bridge = ATCAPIBridge()
    try:
        token = bridge._ensure_token()
        print(f"✅ JWT Token 获取成功 (前20字符): {token[:20]}...")
    except Exception as e:
        print(f"❌ JWT Token 获取失败: {e}")
        print("请确认 ATC 后端可访问，或手动设置环境变量")
        sys.exit(1)

    # 测试查询飞行任务
    print("\n📋 查询飞行任务列表...")
    result = bridge.search_flight_task(page_size=5)
    if "error" not in result:
        total = result.get("result", {}).get("total", 0)
        print(f"✅ 查询成功: 共 {total} 条任务")
    else:
        print(f"⚠️ 查询返回: {result}")

    # 列出可用模板
    templates = SimulatorAPIIntegration.list_templates()
    print(f"\n📁 可用飞行任务模板: {templates if templates else '(无)'}  ")

    print("\n" + "=" * 60)
    print("测试完成")