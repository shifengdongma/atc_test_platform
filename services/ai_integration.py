# -*- coding: utf-8 -*-
"""
AI 集成与自动化入口注册中心

为 AI 工具（Claude Code、MCP 服务器、自动化测试框架）提供统一的
仿真系统操作接口。每个集成点都是可调用的函数/方法，带类型注解和文档。

用法:
    from ai_integration import AIIntegrationRegistry

    registry = AIIntegrationRegistry()
    registry.list_tools()                              # 列出所有可用工具
    result = registry.execute("check_redis_data")      # 执行指定工具
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# 公共模块路径（database/ common/ 已从 utm_simulator/ 移出到项目根目录）
_database_path = os.path.join(_root, '..', 'database')
_common_path = os.path.join(_root, '..', 'common')
for _p in (_database_path, _common_path):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# =====================================================================
# 集成点注册表
# =====================================================================

class AIIntegrationRegistry:
    """AI 集成点注册中心。

    注册所有 AI 可调用的仿真系统操作接口，提供工具发现和执行功能。
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self) -> None:
        """注册内置集成点。"""
        self.register(
            name="validate_scenario",
            description="校验场景 JSON 数据格式是否符合规范",
            func=_validate_scenario_entry,
            parameters={
                "scenario_data": {"type": "dict", "description": "场景数据字典"},
            },
        )
        self.register(
            name="check_redis_data",
            description="检查 Redis 中指定 Key 的数据完整性",
            func=_check_redis_data_entry,
            parameters={
                "key": {"type": "str", "description": "Redis Key，如 BIZ_DATA:UAV_ROUTE"},
            },
        )
        self.register(
            name="check_kafka_topic",
            description="检查 Kafka Topic 是否有正常消息流",
            func=_check_kafka_topic_entry,
            parameters={
                "topic": {"type": "str", "description": "Kafka Topic 名称"},
                "timeout": {"type": "int", "description": "等待超时（秒），默认 10"},
            },
        )
        self.register(
            name="run_simulation",
            description="启动仿真并返回初始状态",
            func=_run_simulation_entry,
            parameters={
                "mode": {"type": "str", "description": "运行模式: dynamic/replay/plan"},
                "count": {"type": "int", "description": "目标无人机架数"},
            },
        )
        self.register(
            name="generate_test_report",
            description="根据测试结果生成 HTML 测试报告",
            func=_generate_test_report_entry,
            parameters={
                "results": {"type": "list", "description": "测试结果列表"},
                "output_path": {"type": "str", "description": "报告输出路径"},
            },
        )
        self.register(
            name="query_drone_state",
            description="查询特定无人机的当前遥测状态（从 Redis 回查）",
            func=_query_drone_state_entry,
            parameters={
                "uid": {"type": "str", "description": "无人机 UID"},
            },
        )

    def register(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """注册一个新的 AI 集成点。

        Args:
            name: 集成点唯一名称
            description: 功能描述
            func: 实现函数
            parameters: 参数定义字典
        """
        self._tools[name] = {
            "name": name,
            "description": description,
            "func": func,
            "parameters": parameters or {},
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有注册的 AI 集成点。

        Returns:
            工具列表，每个工具含 name, description, parameters
        """
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
            for t in self._tools.values()
        ]

    def execute(self, name: str, **kwargs: Any) -> Dict[str, Any]:
        """执行指定的 AI 集成点。

        Args:
            name: 集成点名称
            **kwargs: 传递给实现函数的参数

        Returns:
            包含 success, data, error 的结果字典
        """
        tool = self._tools.get(name)
        if not tool:
            return {"success": False, "error": f"未知工具: {name}", "data": None}

        try:
            result = tool["func"](**kwargs)
            return {"success": True, "data": result, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e), "data": None}


# =====================================================================
# 内置集成点实现
# =====================================================================

def _validate_scenario_entry(scenario_data: dict) -> Dict[str, Any]:
    """校验场景数据格式。"""
    try:
        from validators import validate_scenario
        ok, errors = validate_scenario(scenario_data)
        return {"valid": ok, "errors": errors, "error_count": len(errors)}
    except ImportError:
        return {"valid": None, "errors": ["validators 模块未安装 pydantic"], "error_count": 1}


def _check_redis_data_entry(key: str = "BIZ_DATA:UAV_ROUTE") -> Dict[str, Any]:
    """检查 Redis 数据完整性。"""
    try:
        from redis_client import RedisClient
        from env import redis_ip, redis_port, redis_password
        client = RedisClient(redis_ip, redis_port, redis_password)
        if not client.client:
            return {"connected": False, "error": "无法连接到 Redis"}

        if key.endswith(":UAV_ROUTE") or key.endswith(":AIRSPACE"):
            data = client.hgetall(key)
            total = len(data) if data else 0
            # 抽样检查前 3 条
            samples = []
            for i, (k, v) in enumerate((data or {}).items()):
                if i >= 3:
                    break
                try:
                    obj = json.loads(v) if isinstance(v, str) else v
                    samples.append({"key": k, "uid": obj.get("uniqueProductIdentificationCode", "N/A")})
                except Exception:
                    samples.append({"key": k, "error": "JSON 解析失败"})
            return {"connected": True, "key": key, "total_records": total, "samples": samples}
        else:
            value = client.get_value_by_key(key)
            return {"connected": True, "key": key, "has_data": value is not None}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _check_kafka_topic_entry(topic: str = "uav_runtime_data_1", timeout: int = 10) -> Dict[str, Any]:
    """检查 Kafka Topic 消息流。"""
    try:
        from kafka_proc import KafkaConsumerClient
        from env import kafka_url
        consumer = KafkaConsumerClient(
            bootstrap_servers=kafka_url,
            group_id=f"ai_check_{os.getpid()}_{int(time.time())}",
            consume_from_latest_on_start=True,
        )
        consumer.subscribe([topic])

        messages = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            batch = consumer.poll(timeout_ms=1000)
            messages.extend(batch)
            if len(messages) >= 5:
                break

        consumer.close()
        return {
            "topic": topic,
            "messages_received": len(messages),
            "timeout_sec": timeout,
            "has_traffic": len(messages) > 0,
        }
    except Exception as e:
        return {"topic": topic, "error": str(e), "has_traffic": False}


def _run_simulation_entry(mode: str = "dynamic", count: int = 10) -> Dict[str, Any]:
    """启动仿真并返回初始状态。"""
    try:
        from sim_manager import SimulationManager, load_config
        cfg = load_config()
        cfg.simulation.target_drones = count
        mgr = SimulationManager(cfg)
        mgr.start(mode=mode, target_drones=count)
        time.sleep(1)  # 等待第一个 tick
        status = mgr.get_status()
        mgr.stop()
        return {"started": True, "mode": mode, "initial_status": status}
    except Exception as e:
        return {"started": False, "error": str(e)}


def _generate_test_report_entry(results: list, output_path: str = "") -> Dict[str, Any]:
    """生成 HTML 测试报告。"""
    if not output_path:
        output_path = os.path.join(_root, "docs", f"ai_test_report_{int(time.time())}.html")

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>AI 测试报告</title>
<style>
body{font-family:Arial,sans-serif;max-width:900px;margin:20px auto;padding:20px;background:#f5f5f5}
h1{color:#333;border-bottom:2px solid #4CAF50;padding-bottom:10px}
table{width:100%;border-collapse:collapse;margin:15px 0;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
th,td{padding:10px;text-align:left;border-bottom:1px solid #ddd}
th{background:#4CAF50;color:#fff}
.pass{color:#4CAF50;font-weight:bold}.fail{color:#f44336;font-weight:bold}
.summary{background:#fff;padding:15px;border-radius:5px;margin:15px 0;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
</style></head>
<body>
<h1>UTM 仿真 AI 测试报告</h1>
<div class="summary">
<p><strong>生成时间:</strong> """ + time.strftime("%Y-%m-%d %H:%M:%S") + """</p>
<p><strong>测试项目数:</strong> """ + str(len(results)) + """</p>
</div>
<table>
<tr><th>#</th><th>测试项</th><th>状态</th><th>详情</th></tr>"""

    passed = 0
    for i, r in enumerate(results):
        status = "PASS" if r.get("passed", False) else "FAIL"
        if status == "PASS":
            passed += 1
        html += f"<tr><td>{i+1}</td><td>{r.get('name','N/A')}</td><td class='{'pass' if status == 'PASS' else 'fail'}'>{status}</td><td>{r.get('detail','')}</td></tr>"

    html += f"""</table>
<div class="summary"><p><strong>通过率:</strong> {passed}/{len(results)} ({100*passed//max(len(results),1)}%)</p></div>
</body></html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return {"report_path": output_path, "total": len(results), "passed": passed}


def _query_drone_state_entry(uid: str) -> Dict[str, Any]:
    """查询特定无人机状态。"""
    try:
        from redis_client import RedisClient
        from env import redis_ip, redis_port, redis_password
        client = RedisClient(redis_ip, redis_port, redis_password)
        raw = client.hget("BIZ_DATA:UAV_ROUTE", uid)
        if raw:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return {"found": True, "uid": uid, "flight_plans": len(data.get("flightPlanList", []))}
        return {"found": False, "uid": uid}
    except Exception as e:
        return {"found": False, "uid": uid, "error": str(e)}


# ── 全局注册表实例 ──────────────────────────────────────────────────

registry = AIIntegrationRegistry()


# ── 命令行入口 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("AI 集成点注册表")
    print("=" * 60)
    for tool in registry.list_tools():
        print(f"  {tool['name']}: {tool['description']}")
    print(f"\n共 {len(registry.list_tools())} 个集成点可用")
    print("使用 registry.execute('<name>', **kwargs) 调用")
