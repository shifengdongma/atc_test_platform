# -*- coding: utf-8 -*-
"""
AI 数据生成器 — 调用大模型 API 生成模拟 JSON 数据

支持任何兼容 OpenAI Chat Completions API 的模型（DeepSeek、通义千问、GPT 等）。
内置 Prompt 模板系统，自动校验生成结果，支持保存到数据库。
"""

from __future__ import annotations

import json
import re
import requests
from typing import Any, Dict, List, Optional, Tuple

# ── Prompt 模板 ─────────────────────────────────────────────────────

PROMPT_TEMPLATES = {
    "route_random": {
        "name": "随机航线生成",
        "description": "在指定区域生成随机飞行航线",
        "category": "route",
        "params": ["count", "lat", "lon", "radius_km", "cruise_alt_m"],
        "system": "你是一个无人机飞行航线生成专家。只输出 JSON 数组，不要输出任何解释。",
        "prompt": (
            "生成 {count} 条无人机飞行航线，区域中心 ({lat}, {lon})，半径 {radius_km}km，巡航高度 {cruise_alt_m}m。\n"
            "每条航线对应一架无人机，包含 uniqueProductIdentificationCode(20位字母数字)、flightPlanList(含 routeList)。\n"
            "routeList 中每段的 JSON 格式严格如下：\n"
            '{{"sequence": 0, "type": 2, "segmentStartLon": 120.665, "segmentStartLat": 31.315, '
            '"segmentEndLon": 120.672, "segmentEndLat": 31.320, "segmentStartHeight": 0.0, '
            '"segmentEndHeight": 120.5, "segmentProtectHeight": 50.0, "segmentProtectHeightType": 1, "segmentWidth": 100.0}}\n'
            "输出格式：\n"
            '[\n  {{"key": "UAV_00001", "value": {{"uniqueProductIdentificationCode": "UAV_00001", "flightPlanList": [...]}}}},\n'
            '  ...\n]\n'
            "只输出 JSON 数组，不要 markdown 代码块。"
        ),
    },
    "telemetry_normal": {
        "name": "正常飞行遥测",
        "description": "为指定航线生成匀速飞行遥测序列",
        "category": "telemetry",
        "params": ["duration_sec", "interval_ms", "speed_ms"],
        "system": "你是一个无人机遥测数据生成专家。只输出 JSON 数组，不要输出任何解释。",
        "prompt": (
            "生成 {duration_sec} 秒的无人机飞行遥测数据，采样间隔 {interval_ms}ms，默认速度 {speed_ms}m/s。\n"
            "每条遥测记录格式：\n"
            '{{"uniqueProductIdentificationCode": "UAV_00001", "longitude": 120.665, "latitude": 31.315, '
            '"speed": 30.0, "trackAngle": 90.0, "geodeticAltitude": 100.0, "verticalSpeed": 0.0, '
            '"operatingStatus": 2, "timestamp": 1751900000000, "sourceType": 1, "active": 1}}\n'
            "沿直线从 (120.66, 31.31) 飞行到 (120.68, 31.33)，高度保持 100m。\n"
            "只输出 JSON 数组，不要 markdown 代码块。"
        ),
    },
    "scene_collision": {
        "name": "碰撞预警场景",
        "description": "生成两架无人机在交汇点的碰撞冲突场景",
        "category": "scene",
        "params": ["lat", "lon", "meeting_time_s", "uav1_uid", "uav2_uid"],
        "system": "你是一个无人机冲突场景生成专家。只输出 JSON 数组，不要输出任何解释。",
        "prompt": (
            "生成两架无人机在坐标 ({lat}, {lon}) 附近的碰撞冲突场景遥测数据。\n"
            "UAV1({uav1_uid}) 从西向东飞行，UAV2({uav2_uid}) 从南向北飞行，{meeting_time_s}秒后在 ({lat}, {lon}) 附近最近距离小于 10m。\n"
            "每条遥测记录格式同上，但额外包含 zone 字段：zone=1 正常飞行，zone=2 预警阶段，zone=3 碰撞区域。\n"
            "输出格式：\n"
            '[\n  {{"_uav": "UAV1_UID", "records": [{{"uniqueProductIdentificationCode":"...", ...}}, ...]}},\n'
            '  {{"_uav": "UAV2_UID", "records": [...]}}\n]\n'
            "只输出 JSON 数组。"
        ),
    },
    "scene_airspace": {
        "name": "空域侵入场景",
        "description": "生成无人机逐渐侵入禁飞区的轨迹",
        "category": "scene",
        "params": ["lat", "lon", "nfz_radius_m", "duration_sec"],
        "system": "你是一个空域侵入测试场景生成专家。只输出 JSON 数组，不要输出任何解释。",
        "prompt": (
            "生成 1 架无人机逐渐侵入圆形禁飞区的遥测数据。禁飞区中心 ({lat}, {lon})，半径 {nfz_radius_m}m。\n"
            "无人机从禁飞区外 500m 处沿直线飞向禁飞区中心，{duration_sec} 秒后深入禁飞区。\n"
            "巡航高度 100m，速度 15m/s。每条遥测记录包含标准字段 + zone 字段(1=正常, 2=接近禁飞区, 3=已侵入)。\n"
            "只输出 JSON 数组，不要 markdown 代码块。"
        ),
    },
    "status_alert": {
        "name": "状态告警场景",
        "description": "生成无人机状态变更告警数据（紧急/失联）",
        "category": "scene",
        "params": ["scenes", "duration_sec"],
        "system": "你是一个无人机告警数据生成专家。只输出 JSON 数组，不要输出任何解释。",
        "prompt": (
            "生成无人机状态告警遥测数据，场景类型: {scenes}（scene3=紧急后恢复, scene5=失联, scene35=紧急转失联）。\n"
            "总时长 {duration_sec} 秒，前半段正常飞行(operatingStatus=2)，后半段进入告警状态。\n"
            "坐标从 (120.66, 31.315) 开始沿航向 45° 直线飞行。\n"
            "只输出 JSON 数组。"
        ),
    },
}


# ── AI 生成器 ───────────────────────────────────────────────────────

class AIDataGenerator:
    """大模型数据生成器。"""

    def __init__(self, api_url: str, api_key: str, model: str = ""):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model or "gpt-3.5-turbo"
        self._last_raw = ""

    def generate(self, template_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """根据模板生成 JSON 数据。

        Returns:
            {success, data, raw_response, error, usage}
        """
        template = PROMPT_TEMPLATES.get(template_name)
        if not template:
            return {"success": False, "error": f"未知模板: {template_name}"}

        try:
            prompt_text = template["prompt"].format(**params)
        except KeyError as e:
            return {"success": False, "error": f"模板参数缺失: {e}"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": template["system"]},
                {"role": "user", "content": prompt_text},
            ],
            "temperature": 0.3,
            "max_tokens": 8192,
        }

        try:
            resp = requests.post(
                self.api_url + "/v1/chat/completions" if not self.api_url.endswith("/chat/completions") else self.api_url,
                json=body,
                headers=headers,
                timeout=120,
            )
            resp.raise_for_status()
            result = resp.json()
        except requests.exceptions.Timeout:
            return {"success": False, "error": "API 调用超时（120秒）"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": f"无法连接到 API: {self.api_url}"}
        except requests.exceptions.HTTPError as e:
            err_msg = str(e)
            try:
                err_detail = resp.json()
                err_msg = err_detail.get("error", {}).get("message", str(e))
            except Exception:
                pass
            return {"success": False, "error": f"API 错误: {err_msg}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

        choice = result.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        self._last_raw = content

        # 解析 JSON
        parsed = self._extract_json(content)
        if parsed is None:
            return {
                "success": False,
                "error": "模型输出无法解析为 JSON",
                "raw_response": content[:500],
            }

        return {
            "success": True,
            "data": parsed,
            "usage": result.get("usage", {}),
            "model": result.get("model", self.model),
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[Any]:
        """从模型输出中提取 JSON，兼容 markdown 代码块。"""
        # 尝试提取 ```json ... ``` 代码块
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass
        # 尝试直接解析
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试找第一个 [ 或 { 开始
        for start_char in ("[", "{"):
            idx = text.find(start_char)
            if idx >= 0:
                for end_char in ("]", "}"):
                    end_idx = text.rfind(end_char)
                    if end_idx > idx:
                        try:
                            return json.loads(text[idx:end_idx + 1])
                        except json.JSONDecodeError:
                            continue
        return None

    def validate_result(self, data: Any, category: str) -> Tuple[bool, str]:
        """校验生成结果格式。"""
        try:
            from validators import (
                validate_redis_route,
                validate_telemetry,
                validate_telemetry_batch,
                validate_scenario,
            )

            if category == "route":
                # 支持批量航线格式 [{key, value}, ...]
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict) and "value" in data[0]:
                        ok, msgs = True, []
                        for item in data[:5]:
                            o, m = validate_redis_route(item["value"])
                            if not o:
                                ok = False
                                msgs.extend(m)
                        return ok, "; ".join(msgs[:3]) if msgs else "校验通过"
                return True, "跳过校验（非标准格式）"

            elif category == "telemetry":
                if isinstance(data, list) and len(data) > 0:
                    ok, msgs = True, []
                    for item in data[:10]:
                        o, m = validate_telemetry(item)
                        if not o:
                            ok = False
                            msgs.extend(m)
                    return ok, "; ".join(msgs[:3]) if msgs else "校验通过"
                return True, "跳过校验"

            elif category == "scene":
                if isinstance(data, list) and len(data) > 0:
                    ok, msgs = True, []
                    for item in data[:5]:
                        # scene 可以是嵌套格式
                        records = item.get("records", [item])
                        if isinstance(records, list):
                            for r in records[:3]:
                                o, m = validate_telemetry(r)
                                if not o:
                                    ok = False
                                    msgs.extend(m)
                    return ok, "; ".join(msgs[:3]) if msgs else "校验通过"
                return True, "跳过校验"

            return True, "跳过校验（未知分类）"

        except ImportError:
            return True, "校验模块未加载，跳过校验"


# ── 便捷函数 ────────────────────────────────────────────────────────

def generate_and_save(
    api_url: str,
    api_key: str,
    model: str,
    template_name: str,
    params: Dict[str, Any],
    save_to_db: bool = True,
    save_name: str = "",
) -> Dict[str, Any]:
    """生成数据并可选保存到数据库。"""
    gen = AIDataGenerator(api_url, api_key, model)
    result = gen.generate(template_name, params)

    if not result["success"]:
        return result

    # 校验
    template = PROMPT_TEMPLATES.get(template_name, {})
    category = template.get("category", "telemetry")
    ok, msg = gen.validate_result(result["data"], category)
    result["validation"] = {"passed": ok, "message": msg}

    # 保存到数据库
    if save_to_db and result["data"]:
        try:
            from json_data_manager import save_generated

            name = save_name or f"AI-{template_name}-{_ts()}.json"
            content = json.dumps(result["data"], ensure_ascii=False, indent=2)
            fid = save_generated(
                name=name,
                content=content,
                category=category,
                created_by="ai",
                description=f"AI 生成: {template.get('name','')} (模型: {model})",
            )
            result["db_id"] = fid
            result["db_saved"] = True
        except Exception as e:
            result["db_saved"] = False
            result["db_error"] = str(e)

    return result


def list_templates() -> List[Dict[str, Any]]:
    """列出所有可用 Prompt 模板。"""
    return [
        {
            "key": key,
            "name": t["name"],
            "description": t["description"],
            "category": t["category"],
            "params": t["params"],
        }
        for key, t in PROMPT_TEMPLATES.items()
    ]


def _ts() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")
