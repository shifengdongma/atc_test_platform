# UTM 模拟器 AI 集成指南

## 概述

本文档说明如何在 UTM 模拟器项目中使用 AI 工具（Claude Code、MCP 服务器、自动化测试框架）。

## 可用技能 (Skills Hub)

`skills_hub/` 目录中与 UTM 测试直接相关的技能：

| 技能 | 用途 | 触发方式 |
|------|------|----------|
| `api-test-case-generator` | API 测试用例生成 | 从 OpenAPI 规范生成测试代码 |
| `jmx-test-generator` | JMeter 性能测试计划生成 | 从测试描述生成 JMX 文件 |
| `code-review-assistant` | 代码审查 | 提交 PR 前检查代码质量 |
| `Pretty-mermaid` | Mermaid 图表生成 | 生成架构/流程图 |
| `atc-config` | ATC 配置管理 | 多环境配置切换 |
| `e2e-testing` | 端到端测试 | 完整流程自动化验证 |
| `perf-test` | 性能测试 | 压力测试和基准测试 |

## MCP 服务器配置

项目根目录 `.claude/mcp.json` 预配置了以下 MCP 服务器（默认禁用）：

| MCP 服务器 | 功能 | 启用方式 |
|-----------|------|----------|
| `redis-inspector` | Redis 数据直查 | 设置 `enabled: true`，配置 `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD` |
| `kafka-monitor` | Kafka Topic 监控 | 设置 `enabled: true`，配置 `KAFKA_BOOTSTRAP_SERVERS` |
| `filesystem` | 文件浏览 | 设置 `enabled: true`（自动浏览 mock/ docs/ templates/） |
| `developer-tools` | Claude Code 开发工具 | 需要 Claude 账号授权 |

启用方法：
```bash
# 设置环境变量后重启 Claude Code
export REDIS_HOST=dolphin-test.kedacom.com
export REDIS_PORT=21003
export REDIS_PASSWORD=s4^dJ5^xM6^e
export KAFKA_BOOTSTRAP_SERVERS=10.165.19.213:30011
```

## AI Agent 定义

`.claude/agents/` 目录包含预定义的 AI Agent：

| Agent | 文件 | 用途 |
|-------|------|------|
| UTM Tester | `utm-tester.json` | 仿真测试助手 |
| Data Analyst | `data-analyst.json` | 数据分析助手 |

## AI 集成点 (Integration Points)

`ai_integration.py` 提供 6 个 AI 可调用的集成点：

```python
from ai_integration import registry

# 列出所有工具
registry.list_tools()

# 校验场景数据
registry.execute("validate_scenario", scenario_data={...})

# 检查 Redis 数据
registry.execute("check_redis_data", key="BIZ_DATA:UAV_ROUTE")

# 检查 Kafka 消息流
registry.execute("check_kafka_topic", topic="uav_runtime_data", timeout=10)

# 启动仿真
registry.execute("run_simulation", mode="dynamic", count=100)

# 生成测试报告
registry.execute("generate_test_report", results=[...])

# 查询无人机状态
registry.execute("query_drone_state", uid="UAV_00001")
```

## 环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `UTM_REDIS_HOST` | Redis 主机 | 从 env.py 读取 |
| `UTM_REDIS_PORT` | Redis 端口 | 从 env.py 读取 |
| `UTM_REDIS_PASSWORD` | Redis 密码 | 从 env.py 读取 |
| `UTM_KAFKA_URL` | Kafka 地址 | 从 env.py 读取 |
| `UTM_KAFKA_URL2` | Kafka 镜像地址 | 从 env.py 读取 |
| `UTM_SIM_TARGET_DRONES` | 默认无人机架数 | 10 |
| `UTM_LOG_LEVEL` | 日志级别 | INFO |

## 自动化测试工作流

典型的 AI 驱动测试工作流：

```
1. registry.execute("check_redis_data") → 确认 Redis 可连接
2. registry.execute("check_kafka_topic") → 确认 Kafka 有消息流
3. registry.execute("run_simulation", mode="dynamic", count=10) → 启动小规模仿真
4. registry.execute("validate_scenario", scenario_data=...) → 校验数据格式
5. registry.execute("generate_test_report", results=[...]) → 生成报告
```

## 扩展指南

添加新的 AI 集成点：

```python
from ai_integration import registry

def my_custom_tool(param1: str) -> dict:
    """自定义工具描述"""
    # 实现逻辑
    return {"result": "ok"}

registry.register(
    name="my_custom_tool",
    description="我的自定义 AI 工具",
    func=my_custom_tool,
    parameters={"param1": {"type": "str", "description": "参数说明"}},
)
```
