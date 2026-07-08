# UTM 模拟器优化工作记录

> 基于 `utm_moc52 重构与测试优化分析报告.md` 和 `utm_moc52_综合优化方案.md`
> 格式参考 `utm-simulator-docs-utm-simulator-docs-u-melodic-lightning.md`

---

## 一、概述

本文档记录 UTM 模拟器综合优化实施过程中的所有工作内容、完成状态和验证结果。

## 二、优化目标

1. **前端数据可视化增强**：分析三种数据生成方式，实现数据 JSON 文件的生成/查看/仿真启动
2. **AI 工具集成接口预留**：分析现有 skills/agents/MCP 接口，预留 AI 自动化测试接入点
3. **核心工程优化**：基础设施改造（配置管理、结构化日志、异常层次、数据契约、统一编排）

**硬约束**：不改变现有 Redis/Kafka 数据链路

---

## 三、工作记录

### 2026-07-06: Web 可视化基础框架 + API 桥接 + 端到端测试

> 来源文档: `docs/0706utm-simulator-docs-utm-simulator-docs-u-melodic-lightning.md`

| 时间 | 完成内容 | 状态 |
|------|----------|------|
| 2026-07-06 14:00 | 完成代码库全面分析（utm_simulator/docs/atc_api_autotest），编写优化方案文档 | ✅ 已完成 |
| 2026-07-06 14:45 | Phase 1: 创建 `web_server.py` Flask 后端（REST API + WebSocket + 三模式编排） | ✅ 已完成 |
| 2026-07-06 14:52 | Phase 1-2: 创建前端可视化页面（index.html + CSS + app.js + charts.js + map.js） | ✅ 已完成 |
| 2026-07-06 14:58 | Phase 3: 创建 `sim_api_bridge.py` API 桥接层 + 3 个飞行任务模板（logistics/patrol/emergency） | ✅ 已完成 |
| 2026-07-06 15:05 | Phase 4: 创建 `test_e2e_sim.py` 端到端集成测试脚本（8步流程 + CLI + HTML报告） | ✅ 已完成 |
| 2026-07-06 15:10 | Phase 5: 最终验证 + 更新优化文档工作记录 | ✅ 已完成 |

**7/6 新增文件清单**：
| 文件 | 说明 | 行数 |
|------|------|------|
| `web_server.py` | Flask Web 后端（REST API + WebSocket + 三模式编排） | ~620 行 |
| `web/index.html` | SPA 主页面（三面板布局：配置/监控/地图） | ~120 行 |
| `web/static/css/style.css` | 暗色主题样式（深蓝科技风格） | ~270 行 |
| `web/static/js/app.js` | 前端主逻辑（WebSocket、API、启停、日志） | ~360 行 |
| `web/static/js/charts.js` | 趋势图表（Chart.js，无人机数量/Kafka吞吐） | ~130 行 |
| `web/static/js/map.js` | 地图模块（Leaflet + OSM，航线/禁飞区/图例） | ~190 行 |
| `sim_api_bridge.py` | ATC API 桥接层（JWT认证/任务CRUD/计划申报/场景编排） | ~400 行 |
| `flight_task_templates/logistics.json` | 物流配送任务模板 | ~90 行 |
| `flight_task_templates/patrol.json` | 巡检巡查任务模板 | ~90 行 |
| `flight_task_templates/emergency.json` | 应急救援任务模板 | ~75 行 |
| `test_e2e_sim.py` | 端到端集成测试 | ~380 行 |

---

### 2026-07-07 第一次优化: 基础设施 + 数据契约 + 统一编排 + 前端数据面板 + AI 集成

> 来源计划: `20707run-plan-py-redis-kafka-utm-moc52-md-ut-rippling-biscuit.md`

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-07 | `config.py` | 新建 (~150 行) | ✅ 完成 | `load_config()` 输出与 env.py 一致 |
| 2026-07-07 | `log_setup.py` | 新建 (~80 行) | ✅ 完成 | 控制台 + JSON 双输出正常 |
| 2026-07-07 | `exceptions.py` | 新建 (~60 行) | ✅ 完成 | 9 个异常类，层次正确 |

**设计决策**：
- config.py 使用标准库 dataclass，不引入 pydantic-settings 依赖
- 优先级：UTM_* 环境变量 > env.py 兼容回退 > 代码默认值
- log_setup.py 不替换旧 print()，新代码逐步采用 logger

### Phase B: 数据契约（P0）

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-07 | `schemas.py` | 新建 (~200 行) | ✅ 完成 | 7 个 TypedDict 定义正确 |
| 2026-07-07 | `validators.py` | 新建 (~200 行) | ✅ 完成 | 合法数据通过、非法数据被拦截 |

**TypedDict 清单**：RouteSegmentDict(11 字段)、FlightPlanEntryDict(7)、DroneRouteDict(2)、TelemetryDict(22+)、TraceMessageDict(4)、AirspaceDict(12)、SimulationStatusDict、ScenarioDict

### Phase C1: 统一编排层（P0）

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-07 | `sim_manager.py` | 新建 (~350 行) | ✅ 完成 | 导入测试通过，支持 3 种模式 |
| 2026-07-07 | `main.py` | 重写 (~15 行) | ✅ 完成 | 薄包装，委托 SimulationManager |
| 2026-07-07 | `tools/run_kafka_alive.py` | 重写 (~50 行) | ✅ 完成 | replay 模式参数化 |
| 2026-07-07 | `web_server.py` | 修改 | ✅ 完成 | SimulationRunner 改用 SimulationManager |

**关键设计**：
- SimulationManager 统一 dynamic/replay/plan 三种模式
- 保持旧脚本可独立运行（向后兼容）
- 线程模型：1 仿真线程 + 1 trace 消费线程
- PlanRunner 保留在 run_plan.py，sim_manager.py 通过 import 复用

### Task 1: 前端数据可视化增强

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-07 | `web_server.py` | 新增 5 个 API | ✅ 完成 | `/api/data/files` 等端点 |
| 2026-07-07 | `web/index.html` | 新增数据管理面板 | ✅ 完成 | Tab 切换，表单控件 |
| 2026-07-07 | `web/static/css/style.css` | 新增样式 | ✅ 完成 | 面板切换、文件列表、预览样式 |
| 2026-07-07 | `web/static/js/app.js` | 新增 JS 逻辑 | ✅ 完成 | 文件浏览、生成、上传、启动 |

**新增 API 端点**：
| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/data/files` | GET | 列出 mock/ 文件 |
| `/api/data/files/{name}` | GET | 查看文件内容（分页） |
| `/api/data/files/generate` | POST | 参数化生成（random/grid/radial） |
| `/api/data/files/upload` | POST | 上传 JSON |
| `/api/data/launch-replay` | POST | 用指定文件启动 replay |

### Task 2: AI 集成接口预留

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-07 | `.claude/mcp.json` | 新建 | ✅ 完成 | MCP 配置（Redis/Filesystem） |
| 2026-07-07 | `.claude/agents/utm-tester.json` | 新建 | ✅ 完成 | Agent 定义格式正确 |
| 2026-07-07 | `.claude/agents/data-analyst.json` | 新建 | ✅ 完成 | Agent 定义格式正确 |
| 2026-07-07 | `ai_integration.py` | 新建 (~120 行) | ✅ 完成 | 6 个集成点注册 |
| 2026-07-07 | `skills_hub/AI_INTEGRATION_GUIDE.md` | 新建 | ✅ 完成 | 集成指南文档 |

**集成点清单**：validate_scenario、check_redis_data、check_kafka_topic、run_simulation、generate_test_report、query_drone_state

### Phase D: 测试基础设施（P1）

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-07 | `pytest.ini` | 新建 | ✅ 完成 | pytest 配置正确 |
| 2026-07-07 | `tests/conftest.py` | 新建 (~80 行) | ✅ 完成 | 4 mock + 4 sample fixtures |
| 2026-07-07 | `tests/test_config.py` | 新建 (~100 行) | ✅ 完成 | 8 tests, 5 classes |
| 2026-07-07 | `tests/test_schemas.py` | 新建 (~90 行) | ✅ 完成 | 5 tests, 4 classes |
| 2026-07-07 | `tests/test_validators.py` | 新建 (~110 行) | ✅ 完成 | 10 tests, 4 classes |

### Phase E: 高级工具链（P2）

| 日期 | 文件 | 操作 | 状态 |
|------|------|------|------|
| 2026-07-07 | `schemas/route_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `schemas/telemetry_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `schemas/airspace_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `schemas/scenario_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `cli.py` | 新建 (~200 行) | ✅ 完成 |
| 2026-07-07 | `requirements.txt` | 更新 | ✅ 完成 |

---

## 四、关键技术约束遵守情况

| 约束 | 状态 |
|------|------|
| 不修改 redis_client.py / kafka_proc.py / simulation_core.py 核心逻辑 | ✅ 仅导入调用 |
| 不改变 Redis Key / Kafka Topic / 消息格式 | ✅ 完全保持 |
| Python 技术栈统一 | ✅ |
| UTF-8 + 中文注释 | ✅ |
| 不破坏现有数据链路 | ✅ |

---

## 五、文件变更汇总

| 操作 | 文件数 | 总行数 |
|------|--------|--------|
| 新建 | 12 | ~1500 |
| 修改 | 5 | ~600 |
| 重写 | 2 | ~65 |

**新建文件清单**：
- `config.py`, `log_setup.py`, `exceptions.py` (Phase A)
- `schemas.py`, `validators.py` (Phase B)
- `sim_manager.py` (Phase C1)
- `ai_integration.py` (Task 2)
- `.claude/agents/utm-tester.json`, `.claude/agents/data-analyst.json` (Task 2)
- `skills_hub/AI_INTEGRATION_GUIDE.md` (Task 2)

**修改文件清单**：
- `main.py` (重写为薄包装)
- `tools/run_kafka_alive.py` (重写为薄包装)
- `web_server.py` (改用 SimulationManager + 新增数据管理 API)
- `web/index.html` (新增数据管理面板)
- `web/static/css/style.css` (新增样式)
- `web/static/js/app.js` (新增 JS 逻辑)

### Phase D+E: 测试 + 高级工具链

| 日期 | 文件 | 操作 | 状态 |
|------|------|------|------|
| 2026-07-07 | `pytest.ini` | 新建 | ✅ 完成 |
| 2026-07-07 | `tests/conftest.py` | 新建 (~80 行) | ✅ 完成 |
| 2026-07-07 | `tests/test_config.py` | 新建 (~80 行) | ✅ 完成 |
| 2026-07-07 | `tests/test_schemas.py` | 新建 (~80 行) | ✅ 完成 |
| 2026-07-07 | `tests/test_validators.py` | 新建 (~100 行) | ✅ 完成 |
| 2026-07-07 | `schemas/route_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `schemas/telemetry_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `schemas/airspace_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `schemas/scenario_schema.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `.claude/mcp.json` | 新建 | ✅ 完成 |
| 2026-07-07 | `.claude/agents/data-analyst.json` | 新建 | ✅ 完成 |

**更新汇总**：
| 操作 | 文件数 | 总行数 |
|------|--------|--------|
| 新建 | 20 | ~2000 |
| 修改 | 6 | ~600 |
| 重写 | 2 | ~65 |

---

### 2026-07-07 第二次优化: Bug修复 + 日志增强 + 配置编辑 + 地图优化 + 收尾

> 来源计划: `20707run-plan-py-redis-kafka-utm-moc52-md-ut-rippling-biscuit.md`

#### 问题 1: 运行时长始终 0:00:00

| 文件 | 改动 | 状态 |
|------|------|------|
| `web_server.py` | `_push_status()` 改为基于 `_start_time` 实时计算（不再回显旧值） | ✅ |
| `web_server.py` | Plan 模式循环增加 `_runtime_state["uptime_sec"]` 更新 | ✅ |
| `web_server.py` | `_sim_loop()` 启动时记录 `self._start_time = time.time()` | ✅ |

#### 问题 2: 日志增强 + 导出

| 文件 | 改动 | 状态 |
|------|------|------|
| `sim_manager.py` | 新增 `log_callback` 参数，`_add_log()` 调用回调桥接到前端 | ✅ |
| `sim_manager.py` | 补充动态/Replay/Plan tick 摘要日志 + 连接健康检查 + trace 消费事件 | ✅ |
| `sim_manager.py` | 新增 `_trace_msg_count` 计数器；`traceback` 导入 | ✅ |
| `web_server.py` | SimulationRunner 创建 SimulationManager 时传入 `log_callback=_add_log` | ✅ |
| `web/index.html` | 日志面板标题增加"📥 导出"按钮 | ✅ |
| `web/static/js/app.js` | 新增 `exportLogs()` 函数，纯前端 Blob 下载 | ✅ |

#### 问题 3: Redis/Kafka 前端配置编辑 + 持久化

| 文件 | 改动 | 状态 |
|------|------|------|
| `web/index.html` | `<code>` 只读 → `<input>` 可编辑 + "💾 保存连接配置"按钮 | ✅ |
| `web/static/js/app.js` | `fetchConfig()` 读写 input.value；新增保存事件调用 `/api/sim/config/save` | ✅ |
| `web_server.py` | 新增 `POST /api/sim/config/save` 端点，写入 `config.json` | ✅ |
| `config.py` | 新增 `_read_config_json()`；`load_config()` 优先读 config.json，回退 env.py | ✅ |

#### 问题 4: 地图加载卡顿优化

| 文件 | 改动 | 状态 |
|------|------|------|
| `web/static/lib/leaflet/leaflet.js` | 新增：Leaflet 1.9.4 本地副本（147KB） | ✅ |
| `web/static/lib/leaflet/leaflet.css` | 新增：Leaflet CSS 本地副本（14KB） | ✅ |
| `web/index.html` | CDN unpkg.com → 本地 `/static/lib/leaflet/` 路径 | ✅ |
| `web/static/js/map.js` | 逐个 `addTo()` → 数组收集后 `addLayer()` 批量添加 | ✅ |
| `web_server.py` | `/api/sim/plans` limit 默认 200 → 100 | ✅ |

	> **注意**：上述 Leaflet 本地化 + 批量渲染后地图仍出现大片空白，根因是 OSM 瓦片在国内被阻断。
	> 最终修复见下方 **第四次优化: 地图瓦片源修复**。

#### 问题 5: 后续未完成项收尾

| 文件 | 改动 | 状态 |
|------|------|------|
| `requirements.txt` | 添加 pydantic, pytest, pytest-cov, flask, flask-socketio | ✅ |
| `pytest.ini` | 修复配置文件格式（移除顶部注释） | ✅ |
| `cli.py` | 新建（~200 行），6 个子命令: run/replay/plan/server/validate/check/status | ✅ |

**7/7 第二次优化汇总**：
| 操作 | 文件数 |
|------|--------|
| 新建 | 3 |
| 修改 | 8 |
| 修复 Bug | 1 个（uptime） |
| 新增功能 | 3 个（日志导出、配置编辑持久化、地图本地化） |

---

### 2026-07-07 第三次优化: 工具脚本集成到前端

> 用户需求: 将 `tools/` 中数据创建脚本（create_data.py/scene.py/scenes.py）和仿真脚本（run_kafka.py/alive.py/scene.py/plan.py）的能力集成到 Web 前端

#### 数据创建: 分类 Tab 结构

| 文件 | 改动 | 状态 |
|------|------|------|
| `web_data_gen_bridge.py` | **新建** (~340 行): 桥接层，包装 tools 脚本为 API 友好接口，8 个生成函数 + 批量预设列表 | ✅ |
| `web_server.py` | +8 个 API 端点 (`/api/data/scene/*`, `/api/data/batch`, `/api/data/batch/presets`) | ✅ |
| `web/index.html` | 数据面板改为 4 个 Tab（基础/单机/多机/批量），含 10+ 子表单 | ✅ |
| `web/static/js/app.js` | +~200 行: Tab 切换、子Tab切换、10 个生成按钮 handler、批量预设加载 | ✅ |
| `web/static/css/style.css` | +~40 行: `.gen-tabs`/`.sub-tabs`/`.mode-description`/`.batch-grid` 样式 | ✅ |

**数据生成 Tab 功能清单**：
| Tab | 子Tab | 功能 | 对应脚本 |
|-----|--------|------|----------|
| 基础生成 | — | 随机/网格/放射 三种模式 | `create_data.py` |
| 单机场景 | 航线飞行 | UID+途经点+起终点+高度+速度 | `create_data_scene.py` |
| 单机场景 | 偏离航路 | 航线参数+偏离量+偏离起始点 | `create_data_scene.py` |
| 单机场景 | 状态变更 | 初始状态+变更时间+变更后状态 | `create_data_scene.py` |
| 多机场景 | 平行飞行 | 架数+中心+高度+航向+间距+布局 | `create_data_scenes.py parallel` |
| 多机场景 | 偏离(高级) | 航线名+偏离量(m)+过渡时长+偏离模式 | `create_data_scenes.py deviate` |
| 多机场景 | 碰撞预警 | 2条航线名+2个UID+相遇阈值+碰撞时间 | `create_data_scenes.py collision` |
| 多机场景 | 状态告警 | 紧急恢复/失联/紧急→失联 三种场景 | `create_data_scenes.py status` |
| 批量预设 | — | 11 个全国区域预设（一键生成全部） | `create_data_scenes.py batch` |

#### 仿真模式: 5 种模式 + 说明 + 参数联动

| 文件 | 改动 | 状态 |
|------|------|------|
| `web_server.py` | `_sim_loop()` 新增 `replay_once`/`scene` 模式分支 | ✅ |
| `web_server.py` | `_current_config` 新增 scene/replay 参数；`api_start_sim` 扩展参数白名单 | ✅ |
| `tools/run_kafka.py` | `DataSource` 新增 `get_next_batch()` 方法（供 replay_once 外部驱动） | ✅ |
| `web/index.html` | 模式选择器 3→5 选项 + 模式说明文字 + scene/replay 参数面板 | ✅ |
| `web/static/js/app.js` | 模式选择联动（显示/隐藏参数面板）+ 场景文件列表刷新 + 回放文件列表 | ✅ |

**5 种仿真模式**：
| 值 | 标签 | 说明 |
|----|------|------|
| `dynamic` | 🎮 动态仿真 | 实时生成飞行计划，Simulator引擎计算遥测 |
| `replay` | 🔁 预生成回放(循环) | mock目录JSON循环发射，永不停止 |
| `replay_once` | ▶️ 预生成回放(单次) | 数据耗尽自动停止，输出精度报告 |
| `scene` | 🎬 场景文件注入 | 选择JSON按间隔发射，三种时间戳模式 |
| `plan` | 📐 Redis计划插值 | 从计划路线数学插值生成遥测 |

**7/7 第三次优化汇总**：
| 操作 | 文件数 |
|------|--------|
| 新建 | 1 (`web_data_gen_bridge.py`) |
| 修改 | 6 (`web_server.py`, `tools/run_kafka.py`, `index.html`, `app.js`, `style.css`, work-log) |
| 新增 API | 10 个 |
| 新增后端模式 | 2 个 (`replay_once`, `scene`) |
| 新增前端表单 | 10+ 个子表单 |

---

### 2026-07-07 第四次优化: 地图瓦片源修复（OSM → 高德 + 坐标转换）

> 问题：OSM 瓦片（`tile.openstreetmap.org`）在国内完全无法访问，导致地图大片空白 + 浏览器大量超时连接

#### 根因与修复

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 1 | OSM 瓦片 `ERR_CONNECTION_TIMED_OUT` | 瓦片源切换为 **高德地图**（国内秒加载，无需 API Key） | `map.js` |
| 2 | 高德用 GCJ-02 坐标系，仿真数据是 WGS-84 | 新增 `wgs84ToGcj02()` 转换函数（中国境外自动跳过） | `map.js` |
| 3 | Leaflet 本地秒加载后，flex 布局未完成 → 容器尺寸为0 | `initMap()` 轮询等待 `clientWidth > 0`（最多 5s） | `map.js` |
| 4 | `drawPlansOnMap`/`drawNfzsOnMap` 在 map 未就绪时调用失败 | 增加 200ms 延迟重试机制 | `map.js` |
| 5 | 瓦片加载失败后浏览器不断重试卡死 | `errorTileUrl: ''` 禁止重试 | `map.js` |
| 6 | 航线图层逐个 DOM 插入导致重绘 | 使用 `L.featureGroup` 批量添加 | `map.js` |
| 7 | 无地图加载状态提示 | 新增 `#map-loading` 加载指示器，初始化完成后隐藏 | `index.html` |
| 8 | `window.resize` 后地图尺寸不更新 | 新增 `resize` 事件监听 + `invalidateSize()` | `map.js` |

#### 涉及文件

| 文件 | 改动 | 状态 |
|------|------|------|
| `web/static/js/map.js` | 重写 (~365 行): +坐标转换 +高德瓦片 +容器尺寸检测 +延迟重试 +批量渲染 +错误抑制 | ✅ |
| `web/index.html` | 地图容器内新增加载提示 `<div id="map-loading">` | ✅ |
| `web/static/css/style.css` | `#map-container` 增加 `position:relative; overflow:hidden` | ✅ |

**备选瓦片源**：代码内置 `TILE_PROVIDERS` 配置（高德 / CartoDB），可通过 `switchTileProvider()` 切换。

**7/7 第四次优化汇总**：
| 操作 | 文件数 |
|------|--------|
| 修改 | 3 (`map.js` 重写, `index.html`, `style.css`) |
| 修复 Bug | 1 个（国内地图无法加载） |
| 新增功能 | 4 个（高德瓦片、坐标转换、容器检测、加载提示） |

---

## 2026-07-08 仿真配置页布局优化 + 地图加载修复

**参考设计文档**：`docs/superpowers/specs/2026-07-08-config-layout-map-fix-design.md`

### 1. 地图加载缓慢/空白修复

**根因**：
- 高德旧版瓦片域名 `webrd0{s}.is.autonavi.com` 响应变慢或不可用
- `errorTileUrl: ''` 导致瓦片失败时静默空白
- `run.js` 残留错误调用 `loadScheduledTasks`（函数不存在）

**修复内容**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/web/static/js/map.js` | 修改 | 瓦片源切换：高德 → OpenStreetMap（默认）+ CartoDB（备用）；`wgs84ToGcj02` 改为 no-op（OSM/CartoDB 使用原生 WGS-84）；新增 `tileerror` 事件处理（≥5 次失败显示警告）+ `tileload` 成功清除；`_tileErrorCount` 提升为模块级变量；`switchTileProvider` 重置错误计数与警告 |
| `utm_simulator/web/static/js/run.js` | 修改 | 删除不存在的 `loadScheduledTasks` 调用（第 128 行） |
| `utm_simulator/web/pages/run.html` | 修改 | 地图加载提示改为 CSS spinner 动画 |

**Commit**：`e229a1b`, `6602377`, `c42ac32`, `7334bc9`

### 2. 仿真配置页布局优化

**改动**：
- 左栏（`1.2fr`）：仿真参数配置保持不变
- 右栏（`1fr`）：内联"新建定时任务"表单（上） + 定时任务列表（下）
- 移除模态框，所有 CRUD 操作在页面内完成
- 编辑已有任务时表单预填现有值，取消编辑按钮清空表单

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/web/pages/config.html` | 修改 | 右栏重构为内联表单+列表，移除模态框 HTML 和 CSS |
| `utm_simulator/web/static/js/config.js` | 修改 | `showTaskModal`/`hideTaskModal` 替换为 `resetTaskForm`；`editTask` 填充内联表单；保存后自动重置表单 |
| `utm_simulator/web/static/css/style.css` | 修改 | 新增 `.task-inline-form` 样式 + `@keyframes map-spin` 动画 |

### 本次汇总
| 操作 | 文件数 |
|------|--------|
| 修改 | 6 |
| 修复 Bug | 2 个（地图瓦片加载空白 + loadScheduledTasks 错误） |
| 新增功能 | 2 个（OSM 瓦片源 + 内联任务表单） |
| 状态 | ✅ 已完成，待验证 |

---

### 2026-07-08: Plan模式航线选择修复 + 系统日志空白页修复

> 调试修复两个功能性问题

#### 问题1：Plan模式下无法选择航线独立执行

**根因**：`web_server.py:196` 中 `selected = set(uids) if uids else None` 将空列表 `[]`（用户取消全选）当作 falsy 值处理为 `None`（全部航线），导致无法实现"只执行选中航线"。

**修复**：
- `web_server.py`：`plan_selected_uids` 默认值从 `[]` 改为 `None`，`_init_plan_mode` 区分三种情况：
  - `None`（未选择）= 全部航线
  - `[]`（明确取消全选）= 不执行任何航线
  - `['UAV_001', ...]` = 仅执行指定航线
- `config.js`：仅当 checkbox 已渲染时才发送 `plan_selected_uids`，避免未加载列表时误发空数组
- `common.js`：checkbox 默认从 `checked` 改为未选中，用户需主动选择

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/web_server.py` | 修改 | `plan_selected_uids` 默认 None；`_init_plan_mode` 三态判断 |
| `utm_simulator/web/static/js/config.js` | 修改 | 有 checkbox 才发送选择，否则不发送 |
| `utm_simulator/web/static/js/common.js` | 修改 | checkbox 默认不勾选 |

#### 问题2：系统日志页面空白

**根因**：多重静默异常吞没导致日志无法展示：
1. `logs.js` `fetchInitialLogs()` 中 `catch(e) {}` 静默吞掉 API 异常
2. `web_server.py` `_add_log` 中 `except Exception: pass` 静默吞掉 `push_sim_log` 异常
3. `log_streamer.py` DB 监控线程未调用 `init_tables()` 导致 `no such table` 异常被静默吞掉
4. `log_streamer.py` callback 异常静默吞掉

**修复**：
- `logs.js`：`fetchInitialLogs` 和 `pollLogs` 添加明确错误日志 + API 状态检查 + 占位提示
- `web_server.py`：`_add_log` 异常改为 `print` 输出
- `log_streamer.py`：DB 监控启动前调用 `init_tables()`；所有 `except: pass` 改为 `print` 输出

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/web/static/js/logs.js` | 修改 | 错误处理：HTTP状态检查 + console.error + 占位提示 |
| `utm_simulator/log_streamer.py` | 修改 | import init_tables；DB监控前初始化表；异常改为 print |
| `utm_simulator/web_server.py` | 修改 | _add_log 异常改为 print 输出 |

### 本次汇总
| 操作 | 文件数 |
|------|--------|
| 修改 | 5 |
| 修复 Bug | 2 个（Plan航线选择 + 日志页空白） |
| 状态 | ✅ 已完成，待验证 |

---

### 2026-07-08 14:00: 综合优化计划 Phase 1~6 实施完成

> 来源计划: `docs/07081-json-2-ai-url-api-key-prompt-json-misty-perlis.md`
> 工作总结: `docs/工作总结.md` §7.8 12:00

#### Phase 1: 页面重构 — 多页面导航框架

将单页 SPA 拆分为 6 个独立功能页，建立顶部导航栏体系。

| 文件 | 操作 | 说明 |
|------|------|------|
| `web_server.py` | 修改 | 新增 6 个页面路由（`/config`, `/run`, `/generate`, `/data`, `/env`, `/logs`）；首页重定向至 `/config` |
| `web/pages/config.html` | 新建 | 仿真配置页（模式选择/连接信息/启停控制） |
| `web/pages/run.html` | 新建 | 仿真执行页（监控面板/地图/日志流/定时任务） |
| `web/pages/generate.html` | 新建 | 数据生成页（基础/单机/多机/批量/AI生成 5 个 Tab） |
| `web/pages/data.html` | 新建 | JSON 数据管理页（数据库 CRUD/搜索/导入导出） |
| `web/pages/env.html` | 新建 | 环境管理页（Redis/Kafka 多环境配置切换） |
| `web/pages/logs.html` | 新建 | 系统日志页（WebSocket 实时推送/过滤/导出） |
| `web/static/js/common.js` | 新建 | 公共模块：导航栏渲染、WebSocket 单例、API 封装、工具函数 |
| `web/static/js/config.js` | 新建 | 仿真配置页逻辑（5 种模式启停/定时任务 CRUD） |
| `web/static/js/run.js` | 新建 | 仿真执行页逻辑（监控轮询/地图/日志） |
| `web/static/js/generate.js` | 新建 | 数据生成页逻辑（5 个 Tab 表单/AI 生成） |
| `web/static/js/data.js` | 新建 | JSON 管理页逻辑（数据库列表/搜索/导入导出） |
| `web/static/js/env.js` | 新建 | 环境管理页逻辑（环境 CRUD/一键激活） |
| `web/static/js/logs.js` | 新建 | 系统日志页逻辑（WebSocket 接收/类型过滤/导出） |

#### Phase 2: 数据库基础设施 + 环境变量管理

建立 SQLite 持久化层，替代文件系统存储；实现多环境配置管理。

| 文件 | 操作 | 说明 |
|------|------|------|
| `db_manager.py` | 新建 (~180 行) | SQLite 数据库管理器：4 张表 DDL + 通用 CRUD（`query`/`insert`/`update`/`delete`） |
| `env_manager.py` | 新建 (~250 行) | 环境配置管理器：`list_envs`/`save_env`/`delete_env`/`activate_env`/`import_from_env_py` |
| `web_server.py` | 修改 | +14 个 API 端点：环境 CRUD + 激活/导入 |

**4 张数据库表**：

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `sim_env_config` | 多环境 Redis/Kafka 配置 | name, redis_ip/port/pwd, kafka_url, is_default |
| `sim_json_files` | JSON 数据文件存储 | name, category, content, size_bytes, tags, created_by |
| `sim_scheduled_tasks` | 定时任务定义 | name, cron_expr, sim_mode, sim_params, enabled |
| `sim_task_logs` | 任务执行日志 | task_id, task_type, status, message, started_at |

#### Phase 3: JSON 数据管理

将 JSON 文件从 `mock/` 文件系统迁移到数据库管理。

| 文件 | 操作 | 说明 |
|------|------|------|
| `json_data_manager.py` | 新建 (~280 行) | JSON 数据管理器：`list_files`(分页+搜索)/`save_file`/`delete_file`/`download_file`/`import_from_mock`/`export_to_mock` |
| `web_server.py` | 修改 | +9 个 API 端点：文件 CRUD + 分类查询 + 导入导出 |

#### Phase 4: AI 数据生成

集成大模型 API，通过 prompt 模板生成模拟 JSON 数据。

| 文件 | 操作 | 说明 |
|------|------|------|
| `ai_data_gen.py` | 新建 (~200 行) | AI 数据生成器：模板管理、API 调用、生成结果校验、保存到数据库 |
| `flight_task_templates/` | 新增 | Prompt 模板目录（预置 route/telemetry/scene 等模板） |
| `web_server.py` | 修改 | +2 个 API 端点：`/api/ai/templates` + `/api/ai/generate` |

**支持能力**：
- 兼容 OpenAI API 格式的任意 LLM（DeepSeek、通义千问等）
- Prompt 模板系统：预置常见场景，动态参数填充
- 生成结果自动通过 `schemas.py`/`validators.py` 校验
- 一键保存到数据库

#### Phase 5: 定时任务调度

支持按 cron 表达式定时执行仿真任务，含执行历史追踪。

| 文件 | 操作 | 说明 |
|------|------|------|
| `scheduler.py` | 新建 (~230 行) | 任务调度器：`add_task`/`remove_task`/`pause_task`/`resume_task`/`run_now`/`get_history` |
| `web_server.py` | 修改 | +8 个 API 端点：任务 CRUD + 暂停/恢复 + 立即执行 + 执行历史 |

**功能特性**：
- 快捷时间选项（仅一次/每天/每周/每月）+ 自定义日期时间
- 任务执行回调自动启动 `SimulationRunner`，完成后记录日志到 `sim_task_logs`
- 支持从数据库选择 JSON 文件作为仿真数据源

#### Phase 6: 实时日志流

从 Redis/Kafka/数据库多源采集日志，WebSocket 实时推送到前端。

| 文件 | 操作 | 说明 |
|------|------|------|
| `log_streamer.py` | 新建 (~250 行) | 日志采集器：Redis 航线/空域变更监控 + DB 任务日志轮询 + Kafka 遥测计数 + 缓冲区管理 |
| `web_server.py` | 修改 | +4 个 API 端点：日志查询/导出/清空/类型列表；`_add_log` 桥接到 LogStreamer |

**8 种日志类型**：`redis_route`, `redis_airspace`, `kafka_telemetry`, `kafka_trace`, `db_run_data`, `db_traffic`, `db_alarm`, `sim_status`

**前端功能**：类型多选过滤、关键字搜索、暂停/恢复滚动、JSON/CSV 导出

### Phase 1~6 汇总

| 操作 | 文件数 |
|------|--------|
| 新建 | 15 个 Python 模块 + 6 个 HTML 页面 + 7 个 JS 文件 |
| 修改 | 1 个（`web_server.py` 大幅扩展 API） |
| 新增 API 端点 | 45+ |
| 状态 | ✅ 已完成，待验证 |

**系统功能一览**：
```
http://localhost:5000
├── /config    仿真配置（模式/连接/启停/定时任务）
├── /run       仿真执行（监控/地图/日志）
├── /generate  数据生成（基础/单机/多机/批量/AI生成）
├── /data      JSON管理（数据库CRUD/搜索/导入导出）
├── /env       环境管理（Redis/Kafka配置切换）
└── /logs      系统日志（WebSocket实时/过滤/导出）
```

---

### 2026-07-08: 态势监控日志功能

> 来源计划: `docs/07081-json-2-ai-url-api-key-prompt-json-misty-perlis.md`
> 需求: 将下游 ATC 系统实时态势数据（监视目标数/飞行计划数/告警数）接入系统日志

#### 调研结论

下游 ATC 系统通过 **WebSocket STOMP** 协议实时推送态势数据：

| 数据类型 | 订阅地址 | 数据格式 |
|---------|---------|---------|
| 监视目标数 | `/flightTrack/SEAT0001` | `uavs`/`flightTrack` 列表长度 |
| 实时飞行计划数 | `/dataPush/seat/SEAT0001` | `flowStatistic.totalCount` |
| 实时告警数 | `/dataPush/seat/SEAT0001` | `alarmStatistic.value` |

#### 实施

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/situation_monitor.py` | **新建** (~300 行) | 态势监控采集器：SockJS+STOMP 握手 → 双订阅 → 解析态势数据 → 推送到 LogStreamer |
| `utm_simulator/log_streamer.py` | 修改 | `LOG_TYPES` 新增 3 种：`situation_uav`/`situation_plan`/`situation_alarm` |
| `utm_simulator/web/pages/logs.html` | 修改 | 新增"🛡️ 态势监控日志"过滤分组（3 个 checkbox） |
| `utm_simulator/web_server.py` | 修改 | 新增 `_get_situation_monitor()` 惰性初始化；`SimulationRunner.start()` 中自动启动 |
| `utm_simulator/requirements.txt` | 修改 | 新增 `websocket-client>=1.6.0` 依赖 |

**技术细节**：
- 参考 `atc_api_autotest/api_tools/客户端ws无人机数量统计.py` 的 SockJS+STOMP 协议实现
- JWT Token 优先级：构造参数 > 环境变量 `ATC_JWT_TOKEN` > 自动登录
- UAV 数量限频推送（每 10 秒或值变更时），避免 flightTrack 每秒推送刷屏
- 断线自动重连（指数退避 3s→30s）

**本次汇总**：
| 操作 | 文件数 |
|------|--------|
| 新建 | 1 |
| 修改 | 4 |
| 新增日志类型 | 3 |
| 状态 | ✅ 已完成，待验证 |

---

### 2026-07-08: 系统日志详情增强 — 结构化数据 + Tab 分类展示 + 导出

> 需求: 态势监控日志（监视目标/飞行计划/实时告警）记录详细的结构化信息，按分类 Tab 展示，支持导出

#### 问题分析

上一轮已实现态势监控日志的基本框架，但 `situation_monitor.py` 只从 ATC WebSocket 消息中提取了简单**数量**（如"监视目标数: 5 架"），丢弃了几乎所有丰富详情：

- **flightTrack**: 每架 UAV 的 20+ 字段（位置/高度/速度/航向/状态/分类/告警标签等）全部丢弃
- **flowStatistic**: 6 个子计数（totalCount/waitingCount/activeCount/completedCount/rejectedCount/cancelledCount），只用了 totalCount
- **alarmStatistic**: 仅有 count，实际告警详情在 flightTrack 的 `warningTags` 中

#### 实施方案

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/log_streamer.py` | 修改 | `push()` 增加 `detail: Optional[Dict]` 参数；CSV 导出增加 `type_name` 和 `detail` 列 |
| `utm_simulator/situation_monitor.py` | 修改 | 新增 `_get_uav_list()` / `_extract_uav_details()` / `_extract_warning_details()` 三个提取方法；`_process_body()` 推送结构化 detail；新增 `OPERATING_STATUS_LABELS` / `CLASSIFICATION_LABELS` 中文标签常量 |
| `utm_simulator/web/pages/logs.html` | 重写 | 左侧改为竖排 Tab 栏（🛸监视目标/📋飞行计划/⚠️实时告警/📜全部日志）；右侧 4 个 `.gen-tab-content` 面板；系统日志类型复选框仅在"全部日志"Tab 可见 |
| `utm_simulator/web/static/js/logs.js` | 重写（~300 行） | Tab 切换逻辑；`renderUavTab()` — UAV 可展开详情卡片（识别码/位置/高度/速度/航向）；`renderPlanTab()` — 彩色状态摘要条（5 种状态颜色）；`renderAlarmTab()` — 告警卡片（红色调）；`renderAllTab()` — 传统文本流；导出含 detail 结构 |
| `utm_simulator/web/static/css/style.css` | 追加（~100 行） | `.uav-card`/`.uav-detail-grid`/`.uav-status-badge`/`.uav-warn-badge` UAV 卡片样式；`.plan-summary`/`.plan-summary-item` 飞行计划状态条（带左侧彩色边框）；`.alarm-card`/`.alarm-item` 告警卡片；`.gen-tabs.vertical` 竖排 Tab 样式 |

**数据结构示例**（日志条目的 `detail` 字段）：

```json
// 监视目标
{"count": 5, "uavs": [{"uavIdentifyCode": "CW...", "longitude": 116.7, "latitude": 39.99,
  "geodeticAltitude": 75.0, "speed": 64.1, "trackAngle": 72.2, "operatingStatusLabel": "飞行中",
  "classificationLabel": "C2-轻型", "warningCount": 0}, ...]}

// 飞行计划
{"totalCount": 150, "waitingCount": 30, "activeCount": 100, "completedCount": 20,
 "rejectedCount": 0, "cancelledCount": 0}

// 实时告警（从 flightTrack warningTags 提取）
{"total": 2, "warnings": [{"uavCode": "CW...", "warningType": "collision",
  "message": "与XX距离过近", "timestamp": 1782797071696}, ...]}
```

**前端 Tab 展示效果**：
- **监视目标**: 摘要栏（当前 X 架 + 更新时间）→ UAV 可展开卡片（单击展开查看位置/高度/速度网格）
- **飞行计划**: 6 色状态摘要条 → 变更历史列表（可展开 JSON 详情）
- **实时告警**: 红色调告警卡片 → 告警明细（UAV 识别码/告警类型/消息）
- **全部日志**: 传统纯文本流 + 系统日志类型复选框

**本次汇总**：
| 操作 | 文件数 |
|------|--------|
| 修改 | 3（log_streamer.py, situation_monitor.py, style.css） |
| 重写 | 2（logs.html, logs.js） |
| 新增 Python 方法 | 3（_get_uav_list, _extract_uav_details, _extract_warning_details） |
| 新增 JS 渲染函数 | 4（renderUavTab, renderPlanTab, renderAlarmTab, renderAllTab） |
| 新增 CSS 样式块 | 4（UAV 卡片/飞行计划/告警卡片/竖排 Tab） |
| 状态 | ✅ 已完成，待验证 |

---

## 2026-07-08 系统日志板块 5 项 Bug 修复 + MySQL 持久化

### 问题诊断

1. **监视目标 Tab 报错**: `uav.speed.toFixed is not a function` — ATC 下发数值字段为字符串时，前端 `.toFixed()` 崩溃
2. **飞行计划 Tab 不更新**: 去重仅比较 `totalCount`，子状态变化（待处理→执行中）时不推送
3. **实时告警 Tab 无详情**: `alarmStatistic` 仅含数字统计，缺少每条告警的具体内容
4. **缺少刷新机制**: 无手动刷新按钮，用户无法主动获取最新日志
5. **无持久化存储**: 日志仅存内存（max 1000 条），重启丢失，任务结束后无法导出

### 修改文件

**`utm_simulator/situation_monitor.py`**（修改）— Issues 1/2/3:
- 新增 `_to_float()` 静态方法，安全转换 ATC 下发的数值字段（longitude/latitude/geodeticAltitude/trackAngle/speed/verticalSpeed）
- `_extract_uav_details()` 中 6 个数值字段全部包裹 `_to_float()`，杜绝字符串传入前端
- 飞行计划去重从单值 `_last_plan_count` 改为复合键 `_last_plan_key`（6 个子计数联动比较）
- 新增 `_fetch_plan_details()` 方法，调用 `POST /flight/plan/realtimePlanPage` 获取实时计划列表
- 新增 `_fetch_alert_details()` 方法，调用 `POST /alert/search` 获取告警详情列表
- `alarmStatistic` 处理逻辑增强：当告警数 > 0 时主动调用 API 获取详情，写入 `detail["warnings"]`

**`utm_simulator/web/static/js/logs.js`**（修改）— Issues 1/4:
- 新增 `fmtNum(val, decimals, suffix)` 防御性格式化函数，检查 `typeof === 'number' && isFinite`
- 替换监视目标 Tab 中 6 处 `.toFixed()` 调用为 `fmtNum()`，彻底解决类型错误
- 轮询间隔从 5 秒改为 10 秒（`pollLogs()` 中 3 处 `setTimeout`）
- 新增刷新按钮事件处理：清空 `logs[]` → `fetchInitialLogs()` → Toast 提示

**`utm_simulator/web/pages/logs.html`**（修改）— Issue 4:
- 工具栏新增 `🔄 刷新` 按钮（带 `btn-refresh` 样式类）

**`utm_simulator/web/static/css/style.css`**（修改）— Issue 4:
- 新增 `.btn-refresh` 样式 + `@keyframes btn-spin` 旋转动画

**`utm_simulator/log_streamer.py`**（修改）— Issue 5:
- 新增 MySQL 导入（`mysqldbclient.MysqlDbClient`，带优雅降级 fallback）
- 新增 `_mysql_enabled` / `_mysql_client` 属性，延迟初始化连接
- 新增 `_get_mysql_client()` 方法 — 建立连接 + 建表
- 新增 `_ensure_mysql_table()` 方法 — 创建 `sim_system_logs` 表（id/time/type/type_name/message/detail/task_id/created_at）
- 新增 `export_logs_from_db()` 方法 — 支持日期范围/类型/关键字过滤的 MySQL 导出
- 新增 `_cleanup_old_logs(days=7)` 方法 — 定期清理 7 天前旧日志
- `push()` 方法增强：内存写入后同步持久化到 MySQL，每 ~3600 条触发一次清理

**`utm_simulator/web_server.py`**（修改）— Issue 5:
- 新增 `POST /api/logs/export/db` 端点，支持 `start_date`/`end_date`/`types`/`keyword`/`format` 参数

### 本次汇总

| 操作 | 文件数 |
|------|--------|
| 修改 | 6（situation_monitor.py, logs.js, logs.html, style.css, log_streamer.py, web_server.py） |
| 新增 Python 方法 | 7（_to_float, _fetch_alert_details, _fetch_plan_details, _get_mysql_client, _ensure_mysql_table, export_logs_from_db, _cleanup_old_logs） |
| 新增 JS 函数 | 1（fmtNum） |
| 新增 API 端点 | 1（/api/logs/export/db） |
| 新增 CSS 样式 | 1（btn-refresh 旋转动画） |
| 新增数据库表 | 1（sim_system_logs） |
| 状态 | ✅ 已完成，语法验证通过 |

