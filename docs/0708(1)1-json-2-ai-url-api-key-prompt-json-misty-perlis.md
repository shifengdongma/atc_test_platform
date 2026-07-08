# ATC 测试平台综合优化计划

> **创建日期**: 2026-07-08
> **范围**: 数据库持久化、AI 数据生成、定时任务、实时日志、环境管理、页面重构
> **原则**: 按阶段执行，每阶段独立可交付，不破坏现有核心数据链路

---

## 当前状态分析

| 维度 | 现状 | 问题 |
|------|------|------|
| 页面结构 | 单一 SPA（index.html + app.js ~1100行） | 所有功能挤在 3 个面板中，难以扩展 |
| 数据持久化 | JSON 文件存储在 `mock/` 目录 | 无数据库管理，无法检索/重命名/版本管理 |
| 环境配置 | env.py 文件 + config.json | 切换环境需手动修改文件，无多环境管理 |
| 任务调度 | 手动点击启动 | 无定时/计划执行能力 |
| AI 集成 | ai_integration.py 预留接口 | 未实现实际调用大模型能力 |
| 日志 | print() + 前端 console | 无法实时查看 Redis/Kafka/数据库日志 |

---

## Phase 1: 页面重构 — 多页面导航框架

> **目标**: 将单页面拆分为独立功能页，建立导航体系，为后续阶段打好 UI 基础
> **影响文件**: `web/index.html`, `web/static/js/app.js`, `web/static/css/style.css`, `web_server.py`
> **预计工作量**: 新建 3~4 个页面文件 + 修改路由

### 1.1 新页面架构

```
顶部导航栏（所有页面共享）
├── 🎛️ 仿真配置    → /          (index.html — 重构自当前配置面板)
├── ▶️ 仿真执行    → /run       (run.html — 仿真启停+监控+日志)
├── 📊 数据生成    → /generate  (generate.html — 当前数据管理面板)
├── 📁 数据管理    → /data      (data.html — JSON 文件浏览器 + 数据库)
├── ⚙️ 环境管理    → /env       (env.html — 多环境配置切换)
└── 📋 系统日志    → /logs      (logs.html — 实时日志流)
```

### 1.2 实施要点

1. **后端路由改造** (`web_server.py`)
   - 将当前 `GET /` 改为重定向到 `/config`
   - 新增 6 个页面路由：`/config`, `/run`, `/generate`, `/data`, `/env`, `/logs`
   - 每个路由返回对应的 HTML 文件
   - 公共资源 (`/static/`) 保持不变

2. **前端拆分**
   - 每个页面独立 HTML + JS（共享 CSS）
   - 提取公共组件到 `static/js/common.js`：
     - 顶部导航栏渲染
     - WebSocket 连接管理
     - API 调用封装 (`apiGet`, `apiPost`)
     - Toast/日志基础函数
   - 保持现有暗色科技风主题

3. **当前页面内容迁移**
   - `index.html` 内容拆分到对应页面
   - `app.js` 按功能模块拆分为多个 JS 文件
   - 地图模块保留在仿真执行页面

### 1.3 验证标准
- 6 个页面均能正常访问，导航切换流畅
- 所有现有功能（5 种仿真模式启停、数据生成、地图监控）保持不变
- WebSocket 连接在页面切换时保持

---

## Phase 2: 数据库基础设施 + 环境变量管理

> **目标**: 建立数据库持久化层，实现多环境配置管理
> **影响文件**: 新建 `db_manager.py`, `env_manager.py`; 修改 `web_server.py`; 新建 `web/pages/env.html`

### 2.1 数据库表设计

在 `ATC_DKWRJ_TEST` 模式下新建 4 张表：

```sql
-- 1. 环境配置表
CREATE TABLE sim_env_config (
    id          INT IDENTITY PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,      -- 配置名称（如"开发环境"）
    redis_ip    VARCHAR(200),
    redis_port  VARCHAR(20),
    redis_pwd   VARCHAR(200),              -- 加密存储
    kafka_url   VARCHAR(500),
    kafka_url2  VARCHAR(500),
    db_host     VARCHAR(200),
    db_port     VARCHAR(20),
    is_default  INT DEFAULT 0,             -- 是否默认环境
    created_at  VARCHAR(30),
    updated_at  VARCHAR(30)
);

-- 2. JSON 数据文件表
CREATE TABLE sim_json_files (
    id          INT IDENTITY PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,      -- 文件名
    category    VARCHAR(50),               -- 分类: route/telemetry/scene/template
    content     CLOB,                      -- JSON 内容
    size_bytes  INT,
    description VARCHAR(500),              -- 文件描述
    tags        VARCHAR(300),              -- 标签,逗号分隔
    created_by  VARCHAR(50),              -- ai / manual / script
    created_at  VARCHAR(30),
    updated_at  VARCHAR(30)
);

-- 3. 定时任务表
CREATE TABLE sim_scheduled_tasks (
    id          INT IDENTITY PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    cron_expr   VARCHAR(100),              -- cron 表达式
    sim_mode    VARCHAR(30),               -- dynamic/replay/plan/scene
    json_file_ids VARCHAR(500),            -- 关联的 JSON 文件 ID,逗号分隔
    sim_params  CLOB,                      -- 仿真参数 JSON
    enabled     INT DEFAULT 1,
    last_run_at VARCHAR(30),
    next_run_at VARCHAR(30),
    created_at  VARCHAR(30)
);

-- 4. 任务执行日志表
CREATE TABLE sim_task_logs (
    id          INT IDENTITY PRIMARY KEY,
    task_id     INT,
    task_type   VARCHAR(30),               -- scheduled / manual / ai_generate
    status      VARCHAR(20),               -- running / success / failed
    message     CLOB,
    started_at  VARCHAR(30),
    finished_at VARCHAR(30)
);
```

### 2.2 后端模块

新建 `utm_simulator/db_manager.py`：
- 封装达梦数据库 DDL/DML 操作
- 提供 `init_tables()` 自动建表
- 提供 CRUD 方法供各模块调用
- 复用现有 `dmdbclient.py` 连接模式

新建 `utm_simulator/env_manager.py`：
- `list_envs()` — 列出所有环境
- `get_env(id)` — 获取单个环境配置
- `save_env(data)` — 新增/更新环境
- `delete_env(id)` — 删除环境
- `set_default(id)` — 设为默认环境
- `activate_env(id)` — 切换当前环境（更新 config.json 或环境变量）

### 2.3 前端页面 (`/env`)

- 环境列表（表格）：名称、Redis/Kafka 地址、是否默认、操作按钮
- 新建/编辑环境：表单弹窗
- 一键切换：点击"激活"按钮 → 后端更新当前配置 → 前端刷新连接信息
- 从现有 env.py 导入：自动解析并新增为一条记录
- 密码字段脱敏显示（`****`），编辑时才输入

### 2.4 验证标准
- 4 张表在达梦数据库成功创建
- 能新增/编辑/删除/切换环境配置
- 切换后仿真功能能使用新环境的 Redis/Kafka 连接

---

## Phase 3: JSON 数据管理

> **目标**: 将 JSON 文件管理从文件系统迁移到数据库，支持上传/下载/重命名/分类
> **影响文件**: 新建 `json_data_manager.py`; 新建 `web/pages/data.html`; 修改 `web_server.py`

### 3.1 后端模块

新建 `utm_simulator/json_data_manager.py`：
- `list_files(category, keyword, page, size)` — 分页+分类+搜索
- `get_file(id)` — 获取文件详情+内容
- `upload_file(name, content, category, description)` — 上传存入数据库
- `update_file(id, name/content/description)` — 重命名/编辑
- `delete_file(id)` — 删除
- `download_file(id)` — 返回 JSON 内容（支持直接下载）
- `import_from_mock()` — 扫描 `mock/` 目录批量导入数据库
- `export_to_mock(id)` — 从数据库导出到 `mock/` 目录

### 3.2 API 端点

```
GET    /api/data/db/files?category=&keyword=&page=&size=   → 分页列表
GET    /api/data/db/files/<id>                              → 文件详情
POST   /api/data/db/files                                   → 上传/保存
PUT    /api/data/db/files/<id>                              → 重命名/编辑
DELETE /api/data/db/files/<id>                              → 删除
GET    /api/data/db/files/<id>/download                     → 下载 JSON
POST   /api/data/db/import                                  → mock/ → DB 批量导入
POST   /api/data/db/export/<id>                             → DB → mock/ 导出
```

### 3.3 前端页面 (`/data`)

- 左侧分类树：全部 / 航线数据 / 遥测数据 / 场景文件 / 任务模板
- 右侧表格：文件名、分类、大小、来源（手动/AI/脚本）、时间、操作按钮
- 顶部工具栏：搜索框、上传按钮、批量导入按钮
- 点击文件名：展开 JSON 内容预览（语法高亮）
- 数据生成页面保存按钮 → 选择分类和名称 → 存入数据库
- 仿真执行页面选择 JSON 文件时 → 同时支持从文件和数据库选择

### 3.4 验证标准
- `mock/` 中现有 JSON 文件能批量导入数据库
- 能上传/下载/重命名/删除 JSON 文件
- 数据生成页面创建的数据能保存到数据库

---

## Phase 4: AI 数据生成

> **目标**: 集成大模型 API，通过 prompt 生成模拟 JSON 数据文件
> **影响文件**: 新建 `ai_data_gen.py`; 修改 `web_server.py` 和 `web/pages/generate.html`

### 4.1 后端模块

新建 `utm_simulator/ai_data_gen.py`：

```python
class AIDataGenerator:
    def __init__(self, api_url: str, api_key: str, model: str = ""):
        ...
    
    def generate_route_data(self, prompt: str, count: int = 10) -> Dict:
        """根据 prompt 描述生成飞行航线 JSON"""
        ...
    
    def generate_telemetry_data(self, prompt: str, duration_sec: int = 3600) -> Dict:
        """生成遥测序列 JSON"""
        ...
    
    def generate_scene(self, prompt: str, scene_type: str) -> Dict:
        """生成场景文件（碰撞/偏离/告警等）"""
        ...
    
    def validate_generated(self, data: Dict, schema_type: str) -> Tuple[bool, str]:
        """使用 schemas.py/validators.py 校验生成结果"""
        ...
```

### 4.2 Prompt 模板系统

预置模板（存储在数据库或 JSON 文件中）：

| 模板名称 | 用途 | 示例 Prompt |
|---------|------|-----------|
| `route_random` | 随机航线生成 | "在苏州区域生成 {count} 条随机飞行航线，巡航高度 50~200m..." |
| `route_collision` | 冲突场景航线 | "生成 2 条航线，在坐标 ({lat},{lon})附近的交汇点发生水平迎头冲突..." |
| `telemetry_normal` | 正常遥测 | "为航线 {route_json} 生成 {duration} 秒的匀速飞行遥测数据..." |
| `scene_airspace` | 空域侵入 | "在禁飞区边界生成 1 架逐渐侵入空域的无人机轨迹..." |

### 4.3 API 端点

```
POST /api/ai/generate
  body: {
    "api_url": "https://api.openai.com/v1/chat/completions",
    "api_key": "sk-...",
    "model": "gpt-4",
    "prompt_template": "route_random",
    "params": {"count": 10, "lat": 31.315, "lon": 120.665},
    "save_to_db": true,
    "category": "route",
    "name": "AI生成-苏州航线"
  }
  → 返回生成的 JSON 内容 + 校验结果 + 数据库保存状态
```

### 4.4 前端页面 (`/generate` — AI 生成 Tab)

- LLM 连接配置：API URL、API Key（密码框）、模型名称
- Prompt 模板选择器（下拉框 + 预览）
- 参数填写区（动态表单，根据模板参数变化）
- 生成按钮 → 显示进度 → 展示结果
- 校验结果展示（通过/失败 + 具体错误）
- 一键保存到数据库按钮

### 4.5 验证标准
- 配置有效的 LLM API 后能成功生成 JSON
- 生成的 JSON 通过 schemas.py 校验
- 生成结果能保存到数据库
- API Key 不为空时正常调用，为空时给出友好错误提示

---

## Phase 5: 定时任务调度

> **目标**: 支持按 cron 表达式或固定间隔定时执行仿真任务
> **影响文件**: 新建 `scheduler.py`; 修改 `web_server.py`; 新建 `web/pages/schedule.html`

### 5.1 后端模块

新建 `utm_simulator/scheduler.py`：
- 使用 Python 标准库 `sched` 或 `APScheduler`（轻量方案）
- `TaskScheduler` 类：
  - `add_task(name, cron_expr, sim_config)` — 添加定时任务
  - `remove_task(id)` — 移除任务
  - `pause_task(id)` / `resume_task(id)` — 暂停/恢复
  - `list_tasks()` — 列出所有任务
  - `get_task_history(id, limit)` — 任务执行历史
- 任务触发时自动调用 `SimulationManager` 或 `PlanRunner` 执行仿真
- 任务完成后回调记录日志到数据库 `sim_task_logs`

### 5.2 cron 表达式支持

| 快捷选项 | cron 表达式 | 说明 |
|---------|-----------|------|
| 每 30 分钟 | `*/30 * * * *` | 30 分钟执行一次 |
| 每小时 | `0 * * * *` | 整点执行 |
| 每 2 小时 | `0 */2 * * *` | |
| 每天 9:00 | `0 9 * * *` | 工作日上午执行 |
| 自定义 | 用户输入 | 标准 5 字段 cron |

### 5.3 API 端点

```
GET    /api/schedule/tasks              → 列出所有定时任务
POST   /api/schedule/tasks              → 创建定时任务
PUT    /api/schedule/tasks/<id>         → 更新任务
DELETE /api/schedule/tasks/<id>         → 删除任务
POST   /api/schedule/tasks/<id>/pause   → 暂停
POST   /api/schedule/tasks/<id>/resume  → 恢复
GET    /api/schedule/tasks/<id>/history → 执行历史
POST   /api/schedule/tasks/<id>/run-now → 立即执行
```

### 5.4 前端页面（整合到仿真执行页面 `/run`）

在仿真执行页面增加"定时任务"Tab 或区域：
- 任务列表：名称、cron 表达式、仿真模式、状态（启用/暂停）、下次执行时间、操作
- 新建任务对话框：
  - 任务名称
  - 仿真模式选择（dynamic/replay/plan/scene）
  - JSON 数据文件选择（从数据库选择）
  - 快捷时间选择 + 自定义 cron
  - 其他仿真参数
- 执行历史：时间、状态、耗时、日志摘要

### 5.5 验证标准
- 创建定时任务后能在指定时间自动执行
- 执行结果记录到 sim_task_logs 表
- 暂停/恢复/删除功能正常

---

## Phase 6: 实时日志流

> **目标**: 从 Redis/Kafka/数据库拉取日志，通过 WebSocket 实时推送前端，支持过滤和导出
> **影响文件**: 新建 `log_streamer.py`; 修改 `web_server.py`; 新建 `web/pages/logs.html`

### 6.1 后端模块

新建 `utm_simulator/log_streamer.py`：

```python
class LogStreamer:
    def __init__(self, redis_client, kafka_consumer, db_client):
        ...
    
    def start_streaming(self):
        """启动多线程日志采集"""
        # 线程 1: Redis 日志轮询 (BIZ_DATA:* 变更)
        # 线程 2: Kafka 日志消费 (uav_runtime_data, uav_runtime_trace)
        # 线程 3: 数据库日志查询 (run_data, traffic, alarm)
        ...
    
    def get_logs_by_type(self, log_type, since, limit):
        """按类型获取历史日志"""
        ...
    
    def export_logs(self, log_type, format, since, until):
        """导出日志（JSON/CSV/TXT）"""
        ...
```

### 6.2 日志类型分类

| 类型 | 来源 | Key/Table | 说明 |
|------|------|-----------|------|
| `redis_route` | Redis | `BIZ_DATA:UAV_ROUTE` 变更事件 | 飞行计划写入/更新 |
| `redis_airspace` | Redis | `BIZ_DATA:AIRSPACE` 变更事件 | 空域数据变更 |
| `kafka_telemetry` | Kafka | `uav_runtime_data` | 遥测数据发送记录 |
| `kafka_trace` | Kafka | `uav_runtime_trace` | 轨迹预测反馈 |
| `db_run_data` | 达梦 | `run_data` 表 | 系统运行日志 |
| `db_traffic` | 达梦 | `traffic` 表 | 流量/通信日志 |
| `db_alarm` | 达梦 | `alarm` 表 | 告警日志 |
| `sim_status` | 内部 | 仿真状态变更 | 启动/停止/错误 |

### 6.3 API 端点

```
GET  /api/logs/stream/start   → 启动日志采集
GET  /api/logs/stream/stop    → 停止日志采集
GET  /api/logs/status         → 采集状态
GET  /api/logs?types=&since=&limit=  → 按类型查询历史日志
POST /api/logs/export          → 导出日志 (types, format, time_range)
WebSocket: log_entry 事件       → 实时推送日志条目
```

### 6.4 前端页面 (`/logs`)

- 左侧：日志类型多选过滤器（checkbox 列表）
- 右上：时间范围选择器 + 导出按钮（JSON/CSV/TXT）
- 中间：实时日志流区域（自动滚动，新日志高亮）
- 日志条目格式：`[时间戳] [类型标签] 日志内容`
- 底部统计栏：各类型日志计数、采集状态指示灯
- 支持关键字搜索高亮 + 暂停/恢复滚动

### 6.5 验证标准
- 选择日志类型后能看到实时日志推送
- 日志导出文件内容正确
- 暂停/恢复/过滤功能正常
- 性能：1000+ 条/秒日志不卡顿

---

## 执行顺序与依赖关系

```text
Phase 1 (页面重构)          ← 基础，必须先做
    ↓
Phase 2 (数据库+环境管理)    ← 基础设施，Phase 3~5 依赖
    ↓
┌─── Phase 3 (JSON数据管理)
├─── Phase 4 (AI数据生成)    ← 可并行开发
├─── Phase 5 (定时任务)
└─── Phase 6 (实时日志)
```

- Phase 1 必须最先执行（其他 Phase 的 UI 都基于新页面结构）
- Phase 2 必须在 Phase 3~5 之前（数据库表是基础设施）
- Phase 3/4/5/6 可灵活调整顺序或并行开发

## 技术约束遵守

| 约束 | 遵守方式 |
|------|---------|
| 不修改核心链路 | 所有新增功能通过新增文件和 API 实现 |
| Python 3.11 + `utm` 环境 | 所有新脚本使用相同环境 |
| UTF-8 + 中文注释 | 保持现有代码规范 |
| 敏感信息不提交 | API Key、数据库密码不存入代码，存数据库时加密 |
| 暗色科技风主题 | 新页面继续使用现有 CSS 变量和风格 |

## 新增文件清单（预估）

| Phase | 新增文件 | 修改文件 |
|-------|---------|---------|
| 1 | `web/pages/run.html`, `web/pages/generate.html`, `web/pages/data.html`, `web/pages/env.html`, `web/pages/logs.html`, `web/static/js/run.js`, `web/static/js/generate.js`, `web/static/js/data.js`, `web/static/js/env.js`, `web/static/js/logs.js`, `web/static/js/common.js` | `web_server.py`, `web/index.html`, `web/static/js/app.js`, `web/static/css/style.css` |
| 2 | `db_manager.py`, `env_manager.py` | `web_server.py` |
| 3 | `json_data_manager.py` | `web_server.py`, `web/pages/data.html` |
| 4 | `ai_data_gen.py` | `web_server.py`, `web/pages/generate.html` |
| 5 | `scheduler.py` | `web_server.py`, `web/pages/run.html` |
| 6 | `log_streamer.py` | `web_server.py`, `web/pages/logs.html` |

---

## 附录：用户原始想法的补充完善

> 以下是对用户 6 点想法的理解和优化补充：

### 关于第 1 点（JSON 数据管理）

用户提出"创建数据库存储 JSON 文件"，我的设计在此基础上增加了：
- **分类体系**（航线/遥测/场景/模板），便于检索
- **文件系统 ↔ 数据库双向同步**，不丢弃现有的 `mock/` 文件工作流
- **标签和描述字段**，方便大量文件时搜索
- **来源标记**（手动/AI生成/脚本生成），可追溯数据来源

### 关于第 2 点（AI 数据生成）

用户提出"通过 URL+API Key 调用大模型"，我的设计在此基础上增加了：
- **Prompt 模板系统**，预置常见场景的 prompt，降低使用门槛
- **生成结果自动校验**（复用 schemas.py/validators.py），防止大模型输出格式错误
- **"保存到数据库"一步完成**，生成后无需手动导入
- **支持任何兼容 OpenAI API 格式的 LLM**（包括国内模型如 DeepSeek、通义千问等）

### 关于第 3 点（定时任务）

用户提出"定时执行仿真任务"，我的设计在此基础上增加了：
- **快捷时间选项**（30分钟/1小时/每天）+ 自定义 cron
- **任务执行历史**，方便追踪每次执行结果
- **暂停/恢复**功能，无需删除重建
- **从数据库选择 JSON 文件**而非硬编码路径

### 关于第 4 点（实时日志）

用户提出"Redis/Kafka/数据库日志实时输出+导出"，我的设计在此基础上增加了：
- **日志类型标签分类**，支持按类型过滤
- **WebSocket 实时推送**（复用已有 SocketIO 基础设施）
- **多种导出格式**（JSON/CSV/TXT）
- **日志采集独立线程**，不阻塞仿真主循环

### 关于第 5 点（环境变量管理）

用户提出"配置存入数据库+重命名+切换"，我的设计在此基础上增加了：
- **密码加密存储**（数据库中的密码字段不存明文）
- **从 env.py 一键导入**，迁移方便
- **默认环境标记**，快速切换
- **与现有 config.py 兼容**，`activate_env` 时同步更新 config.json

### 关于第 6 点（页面重构）

用户提出"每个功能独立页面"，我设计的 6 页面架构与用户列出的 5 项基本一致，额外增加了"系统日志"页面。具体对应：
- "仿真参数配置" → `/config`
- "仿真计划执行" → `/run`
- "模拟数据生成" → `/generate`
- "JSON数据管理" → `/data`
- "环境变量管理" → `/env`
- "系统日志" → `/logs`（新增，对应第 4 点功能）
