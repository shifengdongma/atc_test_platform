# UTM 模拟器综合优化实施计划

## Context

`run_plan.py` 已实现通过 Redis/Kafka 读取飞行计划并注入仿真数据。现需参考两篇分析文档（`utm_moc52 重构与测试优化分析报告.md` 和 `utm_moc52_综合优化方案.md`），结合用户的三项新增任务，完成以下优化：

1. **前端数据可视化增强**：分析 main.py 和 run_kafka_alive.py 两种数据生成方式，实现前端 JSON 文件的生成、查看和仿真启动
2. **AI 工具集成接口预留**：分析现有 skills/agents/MCP 接口，预留 AI 自动化测试接入点
3. **核心工程优化**：基于分析文档实施基础设施改造，并建立工作跟踪文档

**硬约束**：不改变现有 Redis/Kafka 数据链路（`BIZ_DATA:UAV_ROUTE`、`uav_runtime_data`、`uav_runtime_trace`）

**已有成果**（melodic-lightning 文档已实施）：
- `web_server.py` — Flask + SocketIO 后端，支持 3 种模式
- `web/` — SPA 前端（配置面板 + 监控面板 + 地图面板）
- `sim_api_bridge.py` — ATC API 桥接层
- `flight_task_templates/` — 3 个任务模板
- `test_e2e_sim.py` — 端到端测试

---

## Phase A: 基础设施（P0，预计 2-3 天）

### A1: `config.py` — 统一配置管理（新建，~150 行）

```
优先级：env_name 参数 > UTM_ENV 环境变量 > env.py 兼容回退
```

- `RedisConfig` / `KafkaConfig` / `SimulationConfig` / `AppConfig` dataclass
- `load_config()` 从 env.py 读取现有配置作为默认值，支持 UTM_ 前缀环境变量覆盖
- 不删除 env.py，保持向后兼容

### A2: `log_setup.py` — 结构化日志（新建，~80 行）

- `JsonFormatter`：输出 `{"ts","level","module","line","msg","thread"}` JSON 格式
- `setup_logging()`：双输出（控制台可读 + JSON 结构化）
- 新模块使用 `logger = get_logger(__name__)`，旧 print() 暂不替换

### A3: `exceptions.py` — 语义异常层次（新建，~60 行）

```
UTMSimulationError
├── ConfigError
├── ConnectionError
│   ├── RedisConnectionError
│   └── KafkaConnectionError
├── DataError
│   ├── ValidationError
│   └── SchemaError
└── SimulationError
    ├── StateError
    └── StepError
```

---

## Phase B: 数据契约（P0，预计 2-3 天）

### B1: `schemas.py` — TypedDict 类型定义（新建，~200 行）

| TypedDict | 对应数据 | 字段数 |
|-----------|---------|--------|
| `RouteSegmentDict` | routeList 航段 | 11 字段 |
| `FlightPlanEntryDict` | flightPlanList 条目 | 7 字段 |
| `DroneRouteDict` | Redis BIZ_DATA:UAV_ROUTE value | 2 字段 |
| `TelemetryDict` | Kafka uav_runtime_data 消息 | 22+ 字段 |
| `TraceMessageDict` | Kafka uav_runtime_trace 消息 | 4 字段 |
| `AirspaceDict` | Redis BIZ_DATA:AIRSPACE value | 12 字段 |

### B2: `validators.py` — Pydantic 数据校验（新建，~200 行）

- `RouteSegmentValidator` / `TelemetryValidator` 含边界值校验
- 便捷函数：`validate_redis_route()` / `validate_telemetry()` / `validate_scenario()`
- 返回 `(bool, List[str])` — 校验结果 + 错误列表，默认只告警不阻断

---

## Phase C1: 统一编排层（P0，预计 4-5 天）

### C1-1: `sim_manager.py` — SimulationManager（新建，~350 行）

**核心交付物**，消除 main.py / run_kafka_alive.py / run_plan.py / web_server.py 中的 DataSource/DataFlow 重复：

```python
class SimulationManager:
    modes: "dynamic" | "replay" | "plan"
    
    start(mode, config_override)   # 启动仿真
    stop(timeout)                  # 停止仿真
    get_status() -> StatusDict     # 运行状态
    get_flight_plans() -> list     # 飞行计划列表
    
    _tick_dynamic()   # 复用 main.py DataSource 逻辑
    _tick_replay()    # 复用 run_kafka_alive.py 逻辑
    _tick_plan()      # 复用 run_plan.py RoutePlanSim 逻辑
    _consume_trace()  # 共享 trace 消费线程
```

关键设计：保持旧脚本可独立运行；不改变任何数据格式；线程模型与现有一致。

### C1-2: 入口脚本瘦身

- `main.py` → 重写为 ~40 行薄包装
- `tools/run_kafka_alive.py` → 重写为 ~100 行薄包装
- `tools/run_plan.py` → RoutePlanSim 保留在本文件，PlanRunner 替换为 SimulationManager

### C1-3: `web_server.py` 适配

- SimulationRunner 内部改用 SimulationManager，API 保持不变

---

## Phase C2: 前端数据可视化增强（Task 1，预计 2-3 天）

### 后端 — web_server.py 新增 API（修改，+150 行）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/data/files` | GET | 列出 mock/ 目录文件（文件名、大小、记录数） |
| `/api/data/files/{filename}` | GET | 查看 JSON 文件内容（分页） |
| `/api/data/files/generate` | POST | 参数化生成模拟数据 `{count, center_lat, center_lon, radius, pattern}` |
| `/api/data/files/upload` | POST | 上传自定义 JSON |
| `/api/data/launch-replay` | POST | 用指定文件启动 replay 模拟 |

### 前端 — 新增"数据管理"面板

**修改文件**：`web/index.html`（+80 行）、`web/static/css/style.css`（+40 行）、`web/static/js/app.js`（+150 行）

新增 UI：
- 配置面板 Tab 切换（"仿真配置" / "数据管理"）
- 文件浏览器（mock/ 目录列表，含大小/记录数）
- JSON 文件预览（可折叠，前 N 条记录）
- 数据生成表单（架数、中心坐标、半径、路径模式）
- "用此数据启动仿真"按钮

### 数据生成增强 — tools/create_data.py（修改，+100 行）

- 抽取 `generate_mock_data(count, center_lat, center_lon, radius, pattern)` 可编程入口
- 支持 pattern: `random`（随机）/ `grid`（网格）/ `radial`（放射状）

---

## Phase C3: AI 集成接口预留（Task 2，预计 1-2 天）

### 新建文件

| 文件 | 说明 | 行数 |
|------|------|------|
| `.claude/mcp.json` | MCP 服务器配置占位（Redis/Kafka/Filesystem） | ~30 |
| `.claude/agents/utm-tester.json` | UTM 测试 Agent 定义 | ~40 |
| `ai_integration.py` | AI 集成注册中心，暴露 6 个集成点 | ~80 |
| `skills_hub/AI_INTEGRATION_GUIDE.md` | AI 集成指南（技能清单 + 工作流） | ~60 |

### ai_integration.py 注册的集成点

| 集成点 | 功能 | 参数 |
|--------|------|------|
| `validate_scenario` | 校验场景 JSON | scenario_data: dict |
| `check_redis_data` | 检查 Redis 数据完整性 | key: str |
| `check_kafka_topic` | 验证 Kafka topic 消息 | topic, timeout |
| `run_simulation` | 启动仿真并等待完成 | config: dict |
| `generate_test_report` | 生成 HTML 测试报告 | results: list |
| `query_drone_state` | 查询特定无人机遥测 | uid: str |

---

## Phase D: 测试基础设施（P1，预计 4-5 天）

### 新建文件清单（11 个文件，~1100 行）

```
tests/
├── conftest.py              # pytest fixtures (mock Redis/Kafka, sample data)
├── test_config.py           # 配置加载、环境变量覆盖、env.py 回退
├── test_schemas.py          # TypedDict 结构验证
├── test_validators.py       # 边界值、非法格式
├── test_drone_agent.py      # DroneAgent 状态机、速度平滑
├── test_simulator.py        # 计划生成、step()、禁飞区
├── test_kafka_proc.py       # send_bulk、镜像发送、超时
├── test_redis_client.py     # hset/hgetall、类型检测
├── test_sim_manager.py      # 生命周期、模式切换、状态查询
├── test_web_server.py       # API 端点集成测试 (Flask test client)
├── test_data_flow.py        # 端到端：生成→Redis→Kafka→trace
└── pytest.ini               # 配置 + markers
```

覆盖率目标：DroneAgent 90%+、validators 95%+、SimulationManager 80%+、API 80%+

---

## Phase E: 高级工具链（P2，预计 4-5 天，可延后）

| 文件 | 说明 | 行数 |
|------|------|------|
| `schemas/route_schema.json` | 航线 JSON Schema | ~50 |
| `schemas/telemetry_schema.json` | 遥测 JSON Schema | ~60 |
| `schemas/airspace_schema.json` | 空域 JSON Schema | ~40 |
| `schemas/scenario_schema.json` | 场景 JSON Schema | ~50 |
| `tools/generate_docs.py` | 文档自动生成（TypedDict→MD 表格 + API→参考 + 测试→索引） | ~300 |
| `tools/data_check.py` | 数据完整性检查脚本 | ~100 |
| `cli.py` | CLI 命令行接口（argparse，复用 SimulationManager） | ~200 |
| `api/server.py` | 独立 FastAPI REST API（与 Flask 共存，端口 8000） | ~200 |

---

## 工作跟踪文档

新建 `docs/utm-simulator-optimization-work-log.md`，格式参考 `docs/utm-simulator-docs-utm-simulator-docs-u-melodic-lightning.md`，包含：
- 按 Phase 分组的工作记录表（日期、文件、操作、状态、验证方式）
- Task 1 / Task 2 独立跟踪小节
- 关键技术约束遵守情况检查清单

---

## 实施顺序与依赖

```
Phase A (config + log + exceptions)  ← 零风险，所有后续阶段基础
    │
Phase B (schemas + validators)       ← 定义数据契约，Phase C 引用
    │
    ├── Phase C1 (SimulationManager)  ← 核心重构，最高风险
    ├── Phase C2 (前端 Task 1)        ← 与 C1 并行，相对独立
    └── Phase C3 (AI Task 2)         ← 与 C1/C2 并行，仅新增文件
            │
Phase D (测试)                        ← 依赖 A-C 代码稳定
            │
Phase E (高级工具)                     ← 最低优先级，可延后
```

## 总估算

| Phase | 新建 | 修改 | 新代码 | 改代码 | 天 |
|-------|------|------|--------|--------|-----|
| A 基础 | 3 | 0 | 290 | 0 | 2-3 |
| B 数据契约 | 2 | 0 | 400 | 0 | 2-3 |
| C1 编排层 | 1 | 3 | 350 | 300 | 4-5 |
| C2 前端 Task1 | 0 | 4 | 0 | 420 | 2-3 |
| C3 AI Task2 | 4 | 0 | 210 | 0 | 1-2 |
| D 测试 | 11 | 0 | 1100 | 0 | 4-5 |
| E 高级工具 | 8 | 0 | 800 | 0 | 4-5 |
| **合计** | **29** | **7** | **~3150** | **~720** | **19-26** |

---

## 关键文件

- `utm_simulator/sim_manager.py` — 最重要交付物，统一三种模式编排
- `utm_simulator/config.py` — 配置管理基础
- `utm_simulator/schemas.py` — 类型定义，消除 `Dict[str, Any]`
- `utm_simulator/web_server.py` — Task 1 修改目标
- `utm_simulator/web/static/js/app.js` — Task 1 前端修改目标
- `docs/utm-simulator-optimization-work-log.md` — 工作跟踪文档

## 验证方式

1. **Phase A**：`python -c "from config import load_config; print(load_config())"` 输出与 env.py 一致
2. **Phase B**：`python -c "from validators import validate_telemetry; print(validate_telemetry(sample))"` 返回 (True, [])
3. **Phase C1**：分别以 3 种模式启动，Redis/Kafka 数据与旧版一致
4. **Phase C2**：浏览器访问 `http://localhost:5000`，数据面板可浏览/生成/预览/启动
5. **Phase C3**：`python -c "from ai_integration import registry; registry.list_tools()"` 输出 ≥5 个集成点
6. **Phase D**：`pytest tests/ -v` 全部通过
7. **Phase E**：`python cli.py status --json` 返回有效 JSON
