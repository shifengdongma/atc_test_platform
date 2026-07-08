# UTM 模拟器入口编排与工程化优化方案

## 一、背景与问题分析

### 1.1 项目现状

基于对 `utm_simulator/` 和 `docs/` 中全部代码与文档的分析，当前 utm_moc52 模拟器已打通到 Redis/Kafka 的数据链路和下游 ATC Dashboard 实时监控系统，核心能力如下：

| 运行模式 | 入口脚本 | 数据来源 | Redis 写入 | Kafka 注入 | 适用场景 |
|----------|----------|----------|------------|------------|----------|
| 动态仿真 | `main.py` | Simulator 引擎实时生成 | 实时动态写入 | 实时仿真遥测 | 开发调试 |
| 预生成注入 | `tools/run_kafka_alive.py` | `mock/` JSON 文件 | 启动时一次性写入 | 预生成数据按秒回放 | 生产部署 |
| Redis 计划插值 | `tools/run_plan.py` | Redis `BIZ_DATA:UAV_ROUTE` | 仅时间平移回写 | 航线几何线性插值 | 轻量注入 |

### 1.2 核心痛点

参考 `utm_moc52 重构与测试优化分析报告.md` 和 `utm_moc52_综合优化方案.md`，结合代码实际分析，确认以下问题：

1. **入口编排缺失**：三种运行模式各自独立启动，无统一入口；参数散落在 `main.py`/`env.py`/命令行参数中，无可视化配置界面
2. **工程化基础设施不足**：无 CLI 参数解析、无启动前校验、无配置文件管理、无运行状态上报
3. **前端可视化空白**：`index.html`/`monitor.html` 仅为占位页面，不具备实际功能；无法直观查看模拟器参数、无人机航线、实时状态
4. **模拟器与 API 测试割裂**：模拟器直接写 Redis/Kafka 而不经过 ATC 后端 API；API 测试工具（`atc_api_autotest/`）独立运行，无法与模拟器联动创建飞行任务
5. **不可测、不可发布**：缺乏可重复的端到端自动化测试流程

---

## 二、优化目标

1. **可视化控制台**：提供 Web 前端页面，直观设置模拟参数、启动/停止仿真、查看实时运行状态和无人机航线
2. **统一入口编排**：通过 Web 后端统一管理三种运行模式，提供 REST API
3. **模拟器-API 测试联动**：建立模拟器与 ATC 后端 API 的连接，支持通过 API 创建飞行任务并驱动模拟器数据生成
4. **不破坏现有数据链路**：严格保持原 Redis/Kafka 数据通路不变，新增功能在现有基础上叠加

---

## 三、方案设计

### 3.1 任务一：前端可视化页面

#### 3.1.1 架构设计

```
┌──────────────────────────────────────────────────────────────────────┐
│                    前端可视化层 (Web Browser)                          │
│  ┌────────────────┐  ┌────────────────┐  ┌─────────────────────────┐ │
│  │ 参数配置面板    │  │ 实时监控面板    │  │ 地图可视化面板           │ │
│  │ · 运行模式选择  │  │ · 无人机数量    │  │ · Leaflet 地图           │ │
│  │ · 目标架数      │  │ · Kafka 吞吐    │  │ · 航线/航点叠加          │ │
│  │ · Redis/Kafka   │  │ · 运行时长      │  │ · 禁飞区多边形           │ │
│  │ · 禁飞区参数    │  │ · 错误统计      │  │ · 无人机实时位置(可选)   │ │
│  │ · 一键启动/停止 │  │ · 连接状态      │  │                         │ │
│  └────────────────┘  └────────────────┘  └─────────────────────────┘ │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │ HTTP REST + WebSocket
┌──────────────────────────────────┴───────────────────────────────────┐
│                     Web 后端服务层 (Python Flask)                      │
│  ┌──────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ REST API 控制器       │  │ WebSocket 实时推送                    │  │
│  │ POST /api/sim/start   │  │ · 每 tick 推送遥测统计               │  │
│  │ POST /api/sim/stop    │  │ · 推送运行状态变更                   │  │
│  │ GET  /api/sim/status  │  │ · 推送错误/告警                      │  │
│  │ GET  /api/sim/config  │  │                                      │  │
│  │ PUT  /api/sim/config  │  │                                      │  │
│  │ GET  /api/sim/plans   │  │                                      │  │
│  └──────────────────────┘  └──────────────────────────────────────┘  │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │ 复用现有模块 (不修改)
┌──────────────────────────────────┴───────────────────────────────────┐
│  原 utm_simulator 模块 (只读调用，不改代码)                            │
│  simulation_core.py · redis_client.py · kafka_proc.py · env.py       │
└──────────────────────────────────────────────────────────────────────┘
```

#### 3.1.2 新增文件清单

| 文件 | 说明 |
|------|------|
| `web/` | 前端可视化代码目录 |
| `web/index.html` | SPA 主页面（含配置面板、监控面板、地图面板） |
| `web/static/css/style.css` | 页面样式 |
| `web/static/js/app.js` | 前端主逻辑（配置、API 调用、WebSocket） |
| `web/static/js/map.js` | 地图模块（Leaflet 航线/禁飞区绘制） |
| `web/static/js/charts.js` | 监控图表模块（无人机数量/吞吐量趋势） |
| `web_server.py` | Flask Web 后端服务（REST API + WebSocket） |
| `web_config.py` | Web 服务默认配置 |

#### 3.1.3 前端功能设计

**面板 A：参数配置**
- 运行模式下拉选择（动态仿真 / 预生成注入 / Redis 插值）
- 目标无人机架数滑块（1~5000）
- Redis/Kafka 连接信息展示（只读，从 env.py 读取）
- 禁飞区开关 + 数量设置
- "启动仿真" / "停止仿真" 按钮
- 运行历史记录列表

**面板 B：实时监控**
- 活跃无人机数量（数字 + 迷你趋势图）
- Kafka 每秒发送消息数
- 运行时长计时器
- Redis/Kafka 连接状态指示灯（绿/红）
- 最近 10 条日志流

**面板 C：地图可视化**
- 使用 Leaflet.js + OSM 瓦片（无需 API Key）
- 加载时展示当前 Redis 中飞行计划航线（从 REST API 获取）
- 航线按不同颜色区分
- 禁飞区多边形叠加
- 底部统计栏：总航线数、总航点数、覆盖范围

#### 3.1.4 后端 API 设计

```python
# web_server.py 核心 API

# 启动仿真（异步后台线程执行）
POST /api/sim/start
  body: {mode: "dynamic"|"replay"|"plan", count: 1000, nfz_count: 3, ...}
  → {success: true, message: "仿真已启动"}

# 停止仿真
POST /api/sim/stop
  → {success: true, message: "仿真已停止"}

# 获取运行状态
GET /api/sim/status
  → {running: true, mode: "dynamic", active_drones: 950,
     kafka_msg_per_sec: 950, uptime_sec: 3600,
     redis_connected: true, kafka_connected: true}

# 获取当前飞行计划（供地图渲染）
GET /api/sim/plans?limit=200
  → {plans: [{uid, routeList, ...}], total: 950}

# 获取/更新配置
GET/PUT /api/sim/config
  → {redis_ip, kafka_url, target_drones, ...}
```

#### 3.1.5 WebSocket 推送协议

```json
// 每秒推送 (由 web_server.py 中的 WebSocket 线程发送)
{
  "type": "tick",
  "active_drones": 950,
  "kafka_msg_sent": 950,
  "uptime_sec": 3600,
  "errors": 0,
  "timestamp": 1751500000
}

// 状态变更推送
{
  "type": "status_change",
  "event": "started" | "stopped" | "error",
  "message": "..."
}
```

#### 3.1.6 实现策略

1. **复用现有模块**：不修改 `simulation_core.py`、`kafka_proc.py`、`redis_client.py`、`env.py`，Web 后端通过导入现有模块来驱动仿真
2. **轻量集成**：`web_server.py` 创建 `DataFlow`/`PlanRunner` 实例，管理生命周期，暴露状态查询接口
3. **Flask + Flask-SocketIO**：Python 技术栈一致，无额外重量级依赖
4. **前端纯静态**：HTML+CSS+JS（Leaflet + Chart.js），无需 Node 构建工具，直接在浏览器打开

---

### 3.2 任务二：模拟器与飞行任务创建的关联优化

#### 3.2.1 现状分析

当前模拟器与 ATC 后端的交互方式：
- **模拟器 → Redis/Kafka → ATC Dashboard**（单向数据注入）
- 不经过 ATC 后端 REST API 层
- ATC 后端有完整的飞行任务管理 API（`atc_api_autotest/api_test_cases/飞行任务列表查询.py`）

已知 ATC 后端 API（来自 `atc_api_autotest/`）：
- `POST /la-atc-biz-backend/flight/task/...` — 飞行任务 CRUD
- `POST /la-atc-biz-backend/flight/plan/...` — 飞行计划申报
- `POST /la-atc-biz-backend/uas/...` — 航空器管理
- `JWT Token 鉴权` — 所有 API 需 Bearer Token

#### 3.2.2 优化方案

**方案 A：模拟器通过 API 创建飞行任务（推荐）**

在模拟器启动时，通过调用 ATC 后端 REST API 来创建飞行任务和申报飞行计划，替代直接写 Redis。这样：
- 飞行任务/计划经过 ATC 后端正常的校验和持久化流程
- ATC 后端会将计划写入 Redis，与直接写入的结果一致
- 可端到端测试"创建任务 → 模拟器注入遥测 → Dashboard 展示"完整链路

```
模拟器启动
    │
    ├─ 1. POST /la-atc-biz-backend/flight/task/create   ← 创建飞行任务
    ├─ 2. POST /la-atc-biz-backend/flight/plan/declare  ← 为每架无人机申报飞行计划
    │      (ATC 后端自动将计划写入 Redis BIZ_DATA:UAV_ROUTE)
    ├─ 3. 启动仿真遥测注入 → Kafka uav_runtime_data
    │      (此部分保持现有逻辑不变)
    └─ 4. API 测试验证：查询任务状态/计划审批/Redis 一致性检查
```

**方案 B：模拟器数据 → API 测试自动化验证**

在模拟器运行期间或之后，自动触发 API 测试进行端到端验证：
- 飞行任务列表查询 → 确认任务已创建
- Redis 一致性检查 → 确认 Redis 中数据与 API 返回一致
- Kafka Topic 检查 → 确认遥测数据正常消费
- 航空器列表查询 → 确认无人机已注册

**方案 C：配置化飞行任务模板**

预定义飞行任务模板（JSON 配置），模拟器启动时根据模板通过 API 批量创建任务：
- `flight_task_templates/` 目录存放模板文件
- 支持多任务类型（物流配送、巡检巡查、应急救援等）
- 支持批量生成航空器并关联到任务

#### 3.2.3 新增文件清单

| 文件 | 说明 |
|------|------|
| `sim_api_bridge.py` | 模拟器 ↔ ATC API 桥接层（JWT 认证、任务创建、计划申报） |
| `flight_task_templates/` | 飞行任务模板目录 |
| `flight_task_templates/logistics.json` | 物流配送任务模板 |
| `flight_task_templates/patrol.json` | 巡检巡查任务模板 |
| `flight_task_templates/emergency.json` | 应急救援任务模板 |
| `test_e2e_sim.py` | 端到端集成测试：模拟器 → API → Redis/Kafka 验证 |

#### 3.2.4 sim_api_bridge.py 核心接口设计

```python
# -*- coding: utf-8 -*-
"""
模拟器与 ATC 后端 API 桥接层
通过 REST API 创建飞行任务和申报飞行计划，实现端到端集成
"""

class ATCAPIBridge:
    """ATC 后端 API 桥接"""

    def __init__(self, base_url: str, jwt_token: str = None):
        """初始化，自动获取 JWT Token"""
        ...

    def create_flight_task(self, task_info: dict) -> dict:
        """创建飞行任务
        POST /la-atc-biz-backend/flight/task/create
        """
        ...

    def declare_flight_plan(self, uav_uid: str, plan: dict) -> dict:
        """申报飞行计划
        POST /la-atc-biz-backend/flight/plan/declare
        """
        ...

    def batch_create_uavs(self, uav_list: list) -> dict:
        """批量导入航空器
        POST /la-atc-biz-backend/uas/batch-import
        """
        ...

    def search_flight_tasks(self, filters: dict) -> list:
        """查询飞行任务列表"""
        ...

    def verify_redis_consistency(self, expected_plans: list) -> bool:
        """验证 Redis 中数据与预期一致"""
        ...


class SimulatorAPIIntegration:
    """模拟器与 API 集成管理器"""

    def __init__(self, api_bridge: ATCAPIBridge, sim_config: dict):
        """初始化"""
        ...

    def setup_flight_scenario(self, template_name: str) -> dict:
        """根据模板创建飞行场景：任务 + 航空器 + 计划
        返回创建的飞行任务 ID 列表
        """
        ...

    def start_simulation_with_api(self):
        """启动模拟器，先通过 API 创建任务和计划，再开始仿真遥测注入"""
        ...
```

#### 3.2.5 关联优化流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                      端到端测试流程                                   │
│                                                                     │
│  1. 加载模板                                                        │
│     flight_task_templates/logistics.json                             │
│                    │                                                │
│  2. 通过 API 创建飞行任务                                            │
│     POST /la-atc-biz-backend/flight/task/create                     │
│                    │                                                │
│  3. 通过 API 批量导入航空器                                          │
│     POST /la-atc-biz-backend/uas/batch-import                       │
│                    │                                                │
│  4. 通过 API 申报飞行计划                                            │
│     POST /la-atc-biz-backend/flight/plan/declare                    │
│     → ATC 后端自动将计划写入 Redis BIZ_DATA:UAV_ROUTE                │
│                    │                                                │
│  5. 启动模拟器遥测注入（复用现有机理）                                │
│     → Kafka uav_runtime_data                                        │
│                    │                                                │
│  6. 自动化验证                                                      │
│     ├─ API 查询任务状态 ✓                                            │
│     ├─ API 查询计划审批状态 ✓                                        │
│     ├─ Redis 一致性检查 ✓（apitools/Redis同步redis_consistency_check）│
│     ├─ Kafka Topic 消费验证 ✓                                       │
│     └─ Dashboard 数据展示验证 ✓                                      │
│                                                                     │
│  7. 生成测试报告                                                     │
│     → docs/test_report_{timestamp}.html                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 四、实施计划

### Phase 1: Web 可视化基础框架
- [ ] 创建 `web_server.py` Flask 后端，实现 REST API 和 WebSocket
- [ ] 创建 `web/index.html` SPA 主页面（三面板布局）
- [ ] 实现参数配置面板（运行模式选择、参数滑块、启停按钮）
- [ ] 实现实时监控面板（状态指示灯、数字统计、日志流）
- [ ] 实现 WebSocket 实时推送

### Phase 2: 地图可视化
- [ ] 创建地图模块（Leaflet + OSM 瓦片）
- [ ] 实现航线数据获取 API（`GET /api/sim/plans`）
- [ ] 绘制飞行计划航线（多段折线、颜色区分）
- [ ] 绘制禁飞区多边形
- [ ] 添加图例和统计栏

### Phase 3: API 桥接与任务创建
- [ ] 创建 `sim_api_bridge.py` ATC API 桥接层
- [ ] 实现 JWT 认证、飞行任务创建、飞行计划申报
- [ ] 创建飞行任务模板 JSON 配置
- [ ] 在 Web 前端添加"通过 API 创建任务"选项

### Phase 4: 端到端集成测试
- [ ] 创建 `test_e2e_sim.py` 端到端测试脚本
- [ ] 实现 API 创建任务 → 模拟器注入 → 一致性验证流程
- [ ] 生成 HTML 测试报告

### Phase 5: 文档与发布
- [ ] 更新 `docs/` 下文档
- [ ] 编写使用手册
- [ ] 部署验证

---

## 五、关键技术约束

1. **不修改现有数据链路**：`redis_client.py`、`kafka_proc.py`、`simulation_core.py` 核心逻辑不动，Web 后端通过导入调用，API 桥接作为可选附加层
2. **Python 技术栈统一**：Flask（Web）+ 现有 Python 模块，不引入 Node.js 等异构技术
3. **前端零构建**：纯 HTML/CSS/JS + CDN 引入 Leaflet/Chart.js，无需 webpack/vite
4. **UTF-8 + 中文注释**：遵循项目代码规范

---

## 六、验证方式

1. 启动 `python web_server.py`，浏览器访问 `http://localhost:5000`
2. 配置参数 → 点击"启动仿真" → 观察监控面板数字变化
3. 地图面板加载航线数据，检查航线绘制正确性
4. 通过 Web UI 选择"API 模式" → 自动创建飞行任务 → 验证 ATC Dashboard 展示
5. 运行 `python test_e2e_sim.py` → 确认端到端测试通过

---

## 七、新增文件清单（实施结果）

### Phase 1-2: Web 可视化基础框架 + 地图

| 文件 | 说明 | 行数/大小 |
|------|------|-----------|
| `web_server.py` | Flask Web 后端服务（REST API + WebSocket + 三模式统一编排） | ~500 行 |
| `web/index.html` | SPA 主页面（三面板布局：配置/监控/地图） | ~120 行 |
| `web/static/css/style.css` | 暗色主题样式（深蓝科技风格） | ~270 行 |
| `web/static/js/app.js` | 前端主逻辑（WebSocket、API调用、启停控制、日志） | ~280 行 |
| `web/static/js/charts.js` | 趋势图表模块（Chart.js 折线图，无人机数量/Kafka吞吐） | ~130 行 |
| `web/static/js/map.js` | 地图模块（Leaflet + OSM，航线绘制/禁飞区多边形/图例） | ~190 行 |

### Phase 3: API 桥接与任务创建

| 文件 | 说明 | 行数/大小 |
|------|------|-----------|
| `sim_api_bridge.py` | 模拟器 ↔ ATC API 桥接层（JWT认证/任务CRUD/计划申报/场景编排） | ~400 行 |
| `flight_task_templates/logistics.json` | 物流配送任务模板（DJI无人机, 3段航线） | ~90 行 |
| `flight_task_templates/patrol.json` | 巡检巡查任务模板（EHANG无人机, 4段航线） | ~90 行 |
| `flight_task_templates/emergency.json` | 应急救援任务模板（AVIC无人机, 3段航线含盘旋） | ~75 行 |

### Phase 4: 端到端集成测试

| 文件 | 说明 | 行数/大小 |
|------|------|-----------|
| `test_e2e_sim.py` | 端到端集成测试（8步流程 + CLI + HTML报告） | ~380 行 |

### 关键技术约束遵守情况

| 约束 | 状态 |
|------|------|
| 不修改 `redis_client.py` / `kafka_proc.py` / `simulation_core.py` | ✅ 仅导入调用 |
| Python 技术栈统一（Flask + 现有模块） | ✅ |
| 前端零构建（纯 HTML/CSS/JS + CDN） | ✅ |
| UTF-8 + 中文注释 | ✅ |
| 不改变 Redis/Kafka 数据链路 | ✅ |

---

## 八、工作记录

| 日期 | 完成内容 | 状态 |
|------|----------|------|
| 2026-07-06 14:00 | 完成代码库全面分析（utm_simulator/docs/atc_api_autotest），编写优化方案文档 | ✅ 已完成 |
| 2026-07-06 14:45 | Phase 1: 创建 `web_server.py` Flask 后端（REST API + WebSocket + 三模式编排） | ✅ 已完成 |
| 2026-07-06 14:52 | Phase 1-2: 创建前端可视化页面（index.html + CSS + app.js + charts.js + map.js） | ✅ 已完成 |
| 2026-07-06 14:58 | Phase 3: 创建 `sim_api_bridge.py` API 桥接层 + 3个飞行任务模板 | ✅ 已完成 |
| 2026-07-06 15:05 | Phase 4: 创建 `test_e2e_sim.py` 端到端集成测试脚本 | ✅ 已完成 |
| 2026-07-06 15:10 | Phase 5: 最终验证 + 更新优化文档工作记录 | ✅ 已完成 |