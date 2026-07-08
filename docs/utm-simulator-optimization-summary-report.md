# UTM 模拟器系统优化汇报总结报告

> **版本**：v1.0
> **日期**：2026-07-07
> **基于**：原系统架构文档（系统架构文档.md、核心代码原理.md、utm-simulator-data-link.md）+ 4 轮优化计划文档 + 工作日志

---

## 一、优化概览

### 1.1 优化背景

原 utm_moc52 模拟器已打通到 Redis/Kafka 的数据链路，具备三种运行模式（dynamic/replay/plan），能够向 ATC Dashboard 注入仿真数据。但存在以下核心痛点：

| 痛点 | 原状态 | 优化后 |
|------|--------|--------|
| **入口编排缺失** | 三种模式各自独立启动，参数散落各处 | 统一 `sim_manager.py` 编排 + CLI + Web 前端 |
| **工程化基础设施不足** | 无配置管理、无结构化日志、无异常层次 | `config.py` + `log_setup.py` + `exceptions.py` |
| **前端可视化空白** | `index.html` 仅为占位页面 | 完整 SPA（配置/监控/地图/数据管理四面板） |
| **模拟器与 API 测试割裂** | 模拟器直接写 Redis/Kafka，无 API 联动 | `sim_api_bridge.py` + `web_data_gen_bridge.py` 桥接层 |
| **不可测、不可发布** | 缺乏自动化测试 | `test_e2e_sim.py` + pytest 测试套件（23 个用例） |
| **数据创建工具门槛高** | 需命令行手动运行 tools/ 脚本 | 全部集成到 Web 前端，可视化操作 |
| **地图无法加载** | OSM 瓦片在国内被阻断 | 切换高德瓦片 + WGS-84→GCJ-02 坐标转换 |
| **仿真模式不足** | 前端仅支持 3 种模式 | 扩展到 5 种（+replay_once +scene） |

### 1.2 优化周期

| 轮次 | 日期 | 来源计划 | 核心内容 |
|------|------|----------|----------|
| 第〇轮 | 2026-07-06 | melodic-lightning | Web 可视化基础框架 + API 桥接 + 端到端测试 |
| 第一轮 | 2026-07-07 | rippling-biscuit #1 | 基础设施 + 数据契约 + 统一编排 + 前端数据面板 + AI 集成 |
| 第二轮 | 2026-07-07 | rippling-biscuit #2 | Bug 修复 + 日志增强 + 配置编辑 + 地图优化 + 收尾 |
| 第三轮 | 2026-07-07 | rippling-biscuit #3 | 工具脚本集成到前端（11 种子命令 + 5 种仿真模式） |
| 第四轮 | 2026-07-07 | 问题驱动 | 地图瓦片源修复（OSM → 高德 + 坐标转换） |

### 1.3 总量统计

| 操作 | 文件数 | 总代码行数 |
|------|--------|-----------|
| 新建 | 28 | ~3,500 |
| 修改 | 8 | ~800 |
| 重写 | 3 | ~450 |
| **合计** | **39** | **~4,750** |

---

## 二、与原系统对比：核心修改内容

### 2.1 新增模块（原系统完全不存在）

#### 2.1.1 统一编排层 `sim_manager.py`（~350 行）

**原系统问题**：`main.py`（dynamic 模式）、`tools/run_kafka_alive.py`（replay 模式）、`tools/run_plan.py`（plan 模式）各自独立实现 DataSource/DataFlow/线程管理，存在大量重复代码。

**优化内容**：
- 创建 `SimulationManager` 统一编排三种运行模式：`_tick_dynamic()` / `_tick_replay()` / `_tick_plan()`
- 统一线程模型：1 仿真线程 + 1 trace 消费线程
- `log_callback` 回调机制桥接 Web 前端日志面板
- 补充 10 处缺失日志点（Redis 写入确认、Kafka 发送条数、tick 摘要、trace 消费事件、连接健康检查等）
- 新增 `_trace_msg_count` 计数器

**效果**：消除 3 个文件中约 40% 的重复代码；新增代码集中在单一模块；向后兼容（旧脚本仍可独立运行）。

#### 2.1.2 Web 可视化前端 `web/` 目录（~1,070 行）

**原系统问题**：`index.html` 仅为占位页面，不具备任何实际功能。

**优化内容**：

| 文件 | 行数 | 功能 |
|------|------|------|
| `web/index.html` | ~120 | SPA 主页面（四面板布局：仿真控制/实时监控/地图可视化/数据管理） |
| `web/static/css/style.css` | ~310 | 暗色科技风格主题（深蓝配色） |
| `web/static/js/app.js` | ~560 | 前端主逻辑（WebSocket 实时通信、API 调用、启停控制、日志导出、配置编辑持久化、数据生成 Tab 切换、批量预设加载） |
| `web/static/js/map.js` | ~365 | 地图模块（高德瓦片、WGS-84→GCJ-02 坐标转换、航线/禁飞区绘制、容器尺寸检测、批量渲染、Leaflet 1.9.4 本地化） |
| `web/static/js/charts.js` | ~130 | 趋势图表（Chart.js，无人机数量/Kafka 吞吐实时曲线） |
| `web/static/lib/leaflet/` | — | Leaflet 1.9.4 本地副本（避免 CDN 不可用导致地图无法加载） |

**效果**：从"零前端"变为完整可用的可视化控制台，操作人员无需接触命令行即可完成全部仿真操作。

#### 2.1.3 Web 后端 `web_server.py`（~620 行）

**原系统问题**：不存在 Web 服务。

**优化内容**：
- Flask + SocketIO 架构
- REST API 端点（13 个）：仿真启动/停止/状态/配置、飞行计划查询、禁飞区查询、数据文件管理、场景生成
- WebSocket 实时推送：每秒推送遥测统计、运行状态变更、错误告警
- `SimulationRunner` 包装 SimulationManager，支持 5 种仿真模式
- `POST /api/sim/config/save` 端点：前端编辑的连接配置持久化到 `config.json`

#### 2.1.4 工程基础设施（3 个文件，~290 行）

| 文件 | 行数 | 功能 |
|------|------|------|
| `config.py` | ~150 | 统一配置管理：`RedisConfig`/`KafkaConfig`/`SimulationConfig`/`AppConfig` dataclass；优先级 UTM_* 环境变量 > config.json > env.py 兼容回退 |
| `log_setup.py` | ~80 | 结构化日志：JSON 格式输出（ts/level/module/line/msg/thread），控制台 + JSON 双输出 |
| `exceptions.py` | ~60 | 9 个语义异常类：`UTMSimulationError → ConfigError/ConnectionError(RedisConnectionError/KafkaConnectionError)/DataError(ValidationError/SchemaError)/SimulationError(StateError/StepError)` |

**效果**：原系统没有配置管理、没有结构化日志、没有异常层次，优化后补齐全部三项基础设施。

#### 2.1.5 数据契约层（2 个文件，~400 行）

| 文件 | 行数 | 功能 |
|------|------|------|
| `schemas.py` | ~200 | 8 个 TypedDict：`RouteSegmentDict`(11字段)、`FlightPlanEntryDict`(7)、`DroneRouteDict`(2)、`TelemetryDict`(22+)、`TraceMessageDict`(4)、`AirspaceDict`(12)、`SimulationStatusDict`、`ScenarioDict` |
| `validators.py` | ~200 | Pydantic 校验器：`RouteSegmentValidator`/`TelemetryValidator` 含边界值检查；便捷函数 `validate_redis_route()`/`validate_telemetry()`/`validate_scenario()` 返回 `(bool, List[str])` |

**效果**：原系统的数据格式仅存在于注释和文档中，代码层面无类型约束。优化后所有关键数据结构有 TypedDict 定义 + Pydantic 校验，IDE 可提示字段名，非法数据可被拦截。

#### 2.1.6 JSON Schema 契约文件（4 个文件）

| 文件 | 用途 |
|------|------|
| `schemas/route_schema.json` | 飞行计划 Redis 数据 JSON Schema |
| `schemas/telemetry_schema.json` | 遥测 Kafka 消息 JSON Schema |
| `schemas/airspace_schema.json` | 空域/禁飞区 Redis 数据 JSON Schema |
| `schemas/scenario_schema.json` | 场景文件 JSON Schema |

**效果**：提供语言无关的数据契约，可供外部系统（前端校验、AI Agent 代码生成、CI 流水线）引用。

#### 2.1.7 桥接层（3 个文件，~860 行）

| 文件 | 行数 | 功能 |
|------|------|------|
| `sim_api_bridge.py` | ~400 | ATC API 桥接层：JWT 认证、飞行任务 CRUD、飞行计划申报、任务模板场景编排 |
| `web_data_gen_bridge.py` | ~340 | 数据生成桥接层：包装 tools/ 脚本为 API 友好接口，8 个生成函数 + 11 个批量预设列表，绕过 `sys.exit()` 直接调用内部 `run_*()` |
| `flight_task_templates/` | 3 文件 | 物流配送/巡检巡查/应急救援 任务模板 |

**效果**：原系统模拟器与 ATC API 完全割裂，优化后可通过桥接层实现"创建飞行任务 → 模拟器自动生成对应数据 → 注入 Redis/Kafka"的联动流程。

#### 2.1.8 CLI 命令行工具 `cli.py`（~200 行）

**原系统问题**：没有统一 CLI，不同模式需要记住不同脚本路径和参数。

**优化内容**：6 个子命令 —— `run` / `replay` / `plan` / `server` / `validate` / `check` / `status`

**效果**：一条命令即可启动任意模式，例如 `python cli.py run --count 100`。

#### 2.1.9 AI 集成接口预留（4 个文件）

| 文件 | 功能 |
|------|------|
| `ai_integration.py` | 6 个 AI 集成点注册：`validate_scenario`/`check_redis_data`/`check_kafka_topic`/`run_simulation`/`generate_test_report`/`query_drone_state` |
| `.claude/mcp.json` | MCP 配置（Redis/Filesystem 工具） |
| `.claude/agents/utm-tester.json` | UTM 测试专用 Agent 定义 |
| `.claude/agents/data-analyst.json` | 数据分析专用 Agent 定义 |
| `skills_hub/AI_INTEGRATION_GUIDE.md` | AI 集成指南文档 |

**效果**：为后续 AI 驱动的自动化测试预留标准化接入点，Claude Code 可通过 MCP 工具直接操作 Redis/Kafka。

#### 2.1.10 测试基础设施（5 个文件，~460 行）

| 文件 | 行数 | 功能 |
|------|------|------|
| `pytest.ini` | — | pytest 全局配置（测试发现、覆盖率） |
| `tests/conftest.py` | ~80 | 4 个 mock fixtures + 4 个 sample 数据 fixtures |
| `tests/test_config.py` | ~100 | 配置管理单元测试（8 tests, 5 classes） |
| `tests/test_schemas.py` | ~90 | 数据契约单元测试（5 tests, 4 classes） |
| `tests/test_validators.py` | ~110 | 数据校验单元测试（10 tests, 4 classes） |
| `test_e2e_sim.py` | ~380 | 端到端集成测试（8 步流程 + CLI + HTML 报告） |

**效果**：原系统没有任何自动化测试，优化后拥有 23 个单元测试 + 1 个端到端集成测试。

### 2.2 修改的原有模块

#### 2.2.1 `main.py`：从 ~400 行重写为 ~15 行薄包装

**修改前**：独立实现完整的 DataSource/DataFlow/线程管理逻辑。
**修改后**：薄包装，委托 `SimulationManager`。

```python
# 修改后（示意）
from sim_manager import SimulationManager
if __name__ == "__main__":
    mgr = SimulationManager()
    mgr.start("dynamic")
```

#### 2.2.2 `tools/run_kafka_alive.py`：从 ~250 行重写为 ~50 行薄包装

**修改前**：独立实现完整的 replay 逻辑。
**修改后**：薄包装，委托 `SimulationManager`，支持命令行参数化。

#### 2.2.3 `tools/run_kafka.py`：新增 `get_next_batch()` 方法

**修改内容**：为 `DataSource` 新增 `get_next_batch()` 方法，供 `replay_once` 模式外部驱动逐批获取数据。

#### 2.2.4 `requirements.txt`：补充依赖

**新增依赖**：`pydantic`, `pytest`, `pytest-cov`, `flask`, `flask-socketio`

---

## 三、关键功能实现

### 3.1 前端完整功能矩阵

#### 3.1.1 仿真控制面板

| 功能 | 说明 |
|------|------|
| 5 种仿真模式选择 | dynamic / replay / replay_once / scene / plan，选中显示说明文字 |
| 模式参数联动 | 选择不同模式自动显示/隐藏对应参数面板（scene: 文件选择+间隔+时间戳模式；replay: 文件选择） |
| 目标架数滑块 | 1~5000 |
| Redis/Kafka 配置编辑 | `<input>` 可编辑 + "💾 保存连接配置"按钮持久化到 `config.json` |
| 一键启动/停止 | WebSocket 实时状态同步 |
| 运行历史记录 | 列表展示 |

#### 3.1.2 实时监控面板

| 指标 | 展示方式 |
|------|----------|
| 活跃无人机数量 | 数字 + Chart.js 迷你趋势图 |
| Kafka 每秒发送消息数 | 数字 + Chart.js 实时曲线 |
| 运行时长 | 动态计时器（HH:MM:SS） |
| 连接状态（Redis/Kafka） | 绿/红指示灯 |
| 错误统计 | 计数器 |
| 日志面板 | 实时滚动 + "📥 导出"按钮（Blob 下载 .txt） |

#### 3.1.3 地图可视化面板

| 功能 | 技术实现 |
|------|----------|
| 瓦片底图 | 高德地图（国内秒加载） + CartoDB 备选 |
| 坐标系转换 | WGS-84 → GCJ-02 自动转换（中国境外跳过） |
| 航线绘制 | 多色折线 + 航点标记 |
| 禁飞区绘制 | GeoJSON Polygon 半透明填充 |
| 图例 | 航线/禁飞区颜色说明 |
| 加载状态 | 地图加载指示器 + 容器尺寸检测 + 延迟重试 |
| 错误抑制 | `errorTileUrl: ''` 禁止瓦片失败后无限重试 |
| 批量渲染 | `L.featureGroup` 批量添加（避免逐个 DOM 插入重绘） |
| 响应式 | `window.resize` → `invalidateSize()` |

#### 3.1.4 数据管理面板（4 个 Tab + 10+ 子表单）

| Tab | 子Tab | 功能 | 对应脚本 |
|-----|--------|------|----------|
| 基础生成 | — | 随机散点/网格分布/放射状 三种模式 | `create_data.py` |
| 单机场景 | 航线飞行 | UID+途经点+起终点+高度+速度 | `create_data_scene.py` |
| 单机场景 | 偏离航路 | 航线参数+偏离量+偏离起始点 | `create_data_scene.py` |
| 单机场景 | 状态变更 | 初始状态+变更时间+变更后状态 | `create_data_scene.py` |
| 多机场景 | 平行飞行 | 架数+中心+高度+航向+间距+布局(hex/line) | `create_data_scenes.py parallel` |
| 多机场景 | 偏离(高级) | 航线名+偏离量(m)+过渡时长+偏离模式 | `create_data_scenes.py deviate` |
| 多机场景 | 碰撞预警 | 2条航线名+2个UID+相遇阈值+碰撞时间 | `create_data_scenes.py collision` |
| 多机场景 | 状态告警 | 紧急恢复/失联/紧急→失联 三种场景 | `create_data_scenes.py status` |
| 批量预设 | — | 11 个全国区域预设（一键生成全部） | `create_data_scenes.py batch` |

### 3.2 后端 API 完整清单

#### 仿真控制 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/sim/start` | POST | 启动仿真（支持 5 种模式） |
| `/api/sim/stop` | POST | 停止仿真 |
| `/api/sim/status` | GET | 获取运行状态 |
| `/api/sim/config` | GET | 获取当前配置 |
| `/api/sim/config/save` | POST | 保存配置到 config.json（持久化） |
| `/api/sim/plans` | GET | 飞行计划列表（limit 默认 100） |
| `/api/sim/nfzs` | GET | 禁飞区列表 |

#### 数据管理 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/data/files` | GET | 列出 mock/ 目录文件 |
| `/api/data/files/{name}` | GET | 查看文件内容（分页） |
| `/api/data/files/generate` | POST | 参数化生成（random/grid/radial） |
| `/api/data/files/upload` | POST | 上传 JSON 文件 |
| `/api/data/launch-replay` | POST | 用指定文件启动 replay |

#### 场景生成 API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/data/scene/single` | POST | 单机场景生成（航线飞行/偏离航路/状态变更） |
| `/api/data/scene/parallel` | POST | 平行飞行场景生成 |
| `/api/data/scene/deviate` | POST | 偏离航路场景生成 |
| `/api/data/scene/collision` | POST | 碰撞预警场景生成 |
| `/api/data/scene/status` | POST | 状态告警场景生成 |
| `/api/data/scene/scale` | POST | 模板扩展场景生成 |
| `/api/data/batch` | POST | 批量预设生成 |
| `/api/data/batch/presets` | GET | 获取 11 个批量预设列表 |

### 3.3 5 种仿真模式完整支持

| 模式 | 前端标签 | 原理 | 数据来源 | 停止条件 |
|------|----------|------|----------|----------|
| `dynamic` | 🎮 动态仿真 | Simulator 引擎实时生成飞行计划+遥测 | 实时生成 | 手动停止 |
| `replay` | 🔁 预生成回放(循环) | mock/ JSON 游标循环回放 | 预生成 JSON 文件 | 手动停止 |
| `replay_once` | ▶️ 预生成回放(单次) | mock/ JSON 游标单次回放 | 预生成 JSON 文件 | 数据耗尽自动停止 |
| `scene` | 🎬 场景文件注入 | 场景 JSON 按间隔发射 | 场景 JSON 文件 | 数据耗尽/手动停止 |
| `plan` | 📐 Redis计划插值 | 从 Redis 读计划，航线数学插值生成遥测 | Redis BIZ_DATA:UAV_ROUTE | 手动停止 |

---

## 四、Bug 修复与质量提升

### 4.1 Bug 修复清单

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | 运行时长始终 0:00:00 | Plan 模式循环未更新 `uptime_sec`；`_push_status()` 回显旧值而非实时计算 | Plan 循环加入 `int(time.time() - self._start_time)`；`_push_status()` 改为基于 `_start_time` 实时计算 |
| 2 | 地图大片空白 | OSM 瓦片在国内被阻断（`ERR_CONNECTION_TIMED_OUT`） | 切换高德瓦片 + WGS-84→GCJ-02 坐标转换 + 瓦片加载失败禁止重试 |
| 3 | 地图容器尺寸为 0 | Leaflet 初始化时 flex 布局未完成 | 轮询等待 `clientWidth > 0`（最多 5s） |
| 4 | 航线/禁飞区绘制失败 | 在 map 未就绪时调用 | 200ms 延迟重试机制 |
| 5 | `window.resize` 后地图错位 | 未监听 resize 事件 | 新增 `resize` 监听 + `invalidateSize()` |

### 4.2 质量提升

| 项目 | 优化前 | 优化后 |
|------|--------|--------|
| 单元测试覆盖率 | 0% | ~23 个用例覆盖核心模块 |
| 端到端测试 | 无 | 8 步流程自动化验证 |
| 类型校验 | 无 | TypedDict + Pydantic 双层契约 |
| 异常处理 | 通用 Exception | 9 个语义异常类 |
| 日志系统 | 散落的 print() | 结构化 JSON 日志 + 前端实时面板 |
| 配置管理 | 散落在 env.py + 代码常量 | 统一 dataclass + 多级优先级 |

---

## 五、关键约束遵守情况

| 约束 | 遵守情况 |
|------|----------|
| 不修改 Redis Key (`BIZ_DATA:UAV_ROUTE`, `BIZ_DATA:AIRSPACE`) | ✅ 完全保持 |
| 不修改 Kafka Topic (`uav_runtime_data`, `uav_runtime_trace`) | ✅ 完全保持 |
| 不修改消息格式（飞行计划 JSON、遥测 22+ 字段） | ✅ 完全保持 |
| 不修改 `redis_client.py` / `kafka_proc.py` / `simulation_core.py` 核心逻辑 | ✅ 仅导入调用 |
| 不破坏现有数据链路 | ✅ 完全保持 |
| Python 技术栈统一 | ✅ |
| UTF-8 + 中文注释 | ✅ |

---

## 六、架构演进对比

### 6.1 原系统架构

```
main.py / run_kafka_alive.py / run_plan.py (各自独立)
    └── 直接调用 simulation_core.py / redis_client.py / kafka_proc.py
    └── 无 Web 前端
    └── 无配置管理
    └── 无测试
```

### 6.2 优化后架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端可视化层                           │
│  index.html + app.js + map.js + charts.js + style.css   │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP REST + WebSocket
┌────────────────────────┴────────────────────────────────┐
│                  Web 后端服务层                           │
│  web_server.py (Flask + SocketIO + SimulationRunner)     │
│  web_data_gen_bridge.py (数据生成桥接)                    │
│  sim_api_bridge.py (ATC API 桥接)                        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                  统一编排层                               │
│  sim_manager.py (SimulationManager)                      │
│  ├── _tick_dynamic() → simulation_core.Simulator         │
│  ├── _tick_replay()  → tools/run_kafka.DataSource        │
│  ├── _tick_plan()    → tools/run_plan.PlanRunner         │
│  └── _consume_trace() → kafka_proc.KafkaConsumerClient   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                  工程基础设施层                            │
│  config.py (统一配置)  │  log_setup.py (结构化日志)        │
│  exceptions.py (异常)  │  schemas.py + validators.py     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              原核心模块 (未修改)                           │
│  simulation_core.py  │  redis_client.py  │  kafka_proc.py│
└─────────────────────────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    ┌───────────┐               ┌──────────────┐
    │   Redis   │               │    Kafka     │
    └───────────┘               └──────────────┘
```

---

## 七、达成效果总结

### 7.1 功能维度

| 指标 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 仿真模式入口 | 3 个独立脚本 | 1 个 CLI + 1 个 Web 前端（5 种模式） | 统一 |
| 前端页面 | 0（占位页） | 完整 SPA（4 面板 + 10+ 表单） | 从无到有 |
| 数据创建方式 | 命令行运行 tools/ 脚本 | Web 前端可视化 + 命令行两种方式 | 门槛大幅降低 |
| AI 集成接口 | 0 | 6 个标准化集成点 + 2 个 Agent 定义 | 从无到有 |
| API 端点 | 0 | 21 个 REST API | 从无到有 |
| 自动化测试 | 0 | 23 个单元测试 + 1 个 E2E 测试 | 从无到有 |
| 数据契约 | 无（仅注释） | 8 个 TypedDict + 4 个 JSON Schema | 从无到有 |
| 配置管理 | 散落 | 统一 dataclass + 3 级优先级 | 规范化 |
| 异常处理 | 通用 Exception | 9 个语义异常类 | 可精确捕获 |
| 日志 | 散落 print() | 结构化 JSON + 前端实时面板 | 可观测 |

### 7.2 质量维度

- **代码重复率**：通过 `SimulationManager` 统一编排，消除 3 个脚本间约 40% 的重复逻辑
- **类型安全**：所有关键数据结构有 TypedDict 定义 + Pydantic 校验，IDE 可自动提示
- **可测试性**：建立了从单元测试（23 个）到端到端测试（1 个）的完整测试金字塔
- **可观测性**：结构化日志 + WebSocket 实时推送 + 前端日志导出
- **用户体验**：从命令行操作变为可视化 Web 控制台，操作门槛从"需懂 Python 命令行"降为"浏览器点击操作"

### 7.3 兼容性

- **完全向后兼容**：原 `main.py`、`run_kafka_alive.py`、`run_plan.py` 仍可独立运行
- **数据链路不变**：Redis Key/Topic/消息格式完全保持，下游 ATC Dashboard 无感知
- **渐进式采用**：新模块可独立启用，不强制替换旧代码

---

## 八、后续建议

1. **持续完善测试覆盖**：当前测试覆盖核心模块（config/schemas/validators），建议逐步覆盖 sim_manager.py 和 web_server.py
2. **CI/CD 流水线**：利用已有的 pytest 套件 + test_e2e_sim.py，建立自动化 CI 流水线
3. **AI 集成深化**：基于已预留的 6 个集成点和 MCP 配置，实现 AI 驱动的场景自动生成、异常自动诊断
4. **性能优化**：大规模（5000+ 架）场景下的前端渲染性能、Kafka 批量发送优化
5. **多环境管理**：利用 config.py 的多级优先级机制，建立开发/测试/生产环境切换面板
