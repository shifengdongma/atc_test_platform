# 场景编排（Scene Orchestration）模块重构计划

## Context

当前"定时任务"模块存在以下问题：
1. **MySQL死锁(1213)** — `POST /api/schedule/tasks` 高并发写入时死锁，无重试机制
2. **缺失批量创建API** — 前端调用 `POST /api/schedule/tasks/batch` 但后端无此路由
3. **API路由无异常保护** — 8个schedule路由无try/except，返回HTML 500而非JSON
4. **前端API封装缺陷** — `apiGet`/`apiPost` 不检查 `resp.ok`，JSON解析崩溃
5. **重复建表** — `init_tables()` 从多个入口点被调用，每次启动重复执行SHOW TABLES+CREATE

同时，用户要求将"定时任务"重构为"场景编排"，支持单文件/多文件场景、秒级循环间隔、多任务并行/串行执行、任务名称编辑等功能。

## 分阶段实施计划

---

### 阶段一：Bug修复（不改表结构，最小变更）

#### 1.1 MySQL死锁重试 — `database/mysql_db_manager.py`
- `insert()` 函数增加死锁重试：捕获 `pymysql.err.OperationalError` 1213，最多重试3次（0.1s/0.3s/0.9s指数退避）
- 同样修复 `update()` 和 `delete()`

#### 1.2 添加批量创建API — `utm_simulator/web_server.py`
- 新增 `POST /api/schedule/tasks/batch` 路由
- 接收 `{items: [{name, cron_expr, sim_mode, sim_params, enabled}, ...]}`
- 逐个创建，跳过空名称项，返回成功计数

#### 1.3 API路由异常保护 — `utm_simulator/web_server.py`
- 8个schedule路由全部加 try/except，返回 `{"success": false, "message": str(e)}` + 500
- 可抽取 `_schedule_api_wrapper` 装饰器减少重复

#### 1.4 前端API健壮性 — `web/static/js/common.js`
- `apiGet`/`apiPost` 增加 `resp.ok` 检查
- 非OK响应先尝试 `resp.json()` 提取错误消息，失败则返回通用错误

#### 1.5 去重init_tables调用 — `database/mysql_db_manager.py`
- 增加模块级 `_tables_initialized` 标志
- `init_tables()` 第二次及后续调用直接返回

**验证**：并发POST创建任务不报500；批量保存不报404；API报错返回JSON；页面刷新不重复建表日志

---

### 阶段二：数据库Schema重构

#### 2.1 新增三张表 + 修改日志表 — `database/mysql_db_manager.py`

在 `_MYSQL_TABLE_DDL` 中：

**删除** `"sim_scheduled_tasks"` 条目

**新增**：
```sql
sim_scenes         — 场景编排主表 (id, name, env_id, scene_type, cron_expr, sim_mode DEFAULT 'scene', enabled, last_run_at, next_run_at, created_at, updated_at)
sim_scene_tasks    — 场景任务表 (id, scene_id, name, task_type, cycle_interval_sec, repeat_count, execution_timeout_sec, sort_order, created_at)
sim_scene_task_files — 任务文件关联表 (id, task_id, file_id, interval_sec, sort_order, created_at)
```

**修改** `sim_task_logs` — 增加 `scene_id`, `scene_task_name` 两列

#### 2.2 同步SQLite DDL — `database/db_manager.py`
- 同样的表结构变更（SQLite语法适配）

#### 2.3 数据迁移脚本（可选） — `database/migrate_scheduled_to_scene.py`
- 将旧的 `sim_scheduled_tasks` 数据迁移到新表结构
- 旧任务 → scene_type='single'，单文件单任务
- 执行后 DROP `sim_scheduled_tasks`

**验证**：新表创建成功；旧表数据正确迁移；init_tables()不再创建sim_scheduled_tasks

---

### 阶段三：后端重构（scheduler → orchestrator）

#### 3.1 新建 `database/orchestrator.py`
- 基于 `scheduler.py` 重写，类名 `SceneOrchestrator`
- 操作新表 `sim_scenes` / `sim_scene_tasks` / `sim_scene_task_files`
- 新增方法：
  - `list_scenes()`, `get_scene()`, `create_scene()`, `update_scene()`, `delete_scene()`
  - `list_tasks(scene_id)`, `create_task()`, `update_task()`, `delete_task()`
  - `list_task_files(task_id)`, `add_task_file()`, `remove_task_file()`
  - `run_scene_now(scene_id)`, `get_scene_history(scene_id)`
- 执行逻辑支持单文件/多文件、串行/并行

#### 3.2 更新 `utm_simulator/web_server.py`

**替换路由**（旧 `/api/schedule/*` → 新 `/api/scenes/*`）：
```
GET    /api/scenes                          — 场景列表
POST   /api/scenes                          — 创建场景
PUT    /api/scenes/<id>                     — 更新场景
DELETE /api/scenes/<id>                     — 删除场景
POST   /api/scenes/<id>/toggle              — 启用/禁用
POST   /api/scenes/<id>/run-now             — 立即执行
GET    /api/scenes/<id>/history             — 执行历史
GET    /api/scenes/<id>/tasks               — 任务列表
POST   /api/scenes/<id>/tasks               — 创建任务
PUT    /api/scenes/<id>/tasks/<tid>         — 更新任务（含名称修改）
DELETE /api/scenes/<id>/tasks/<tid>         — 删除任务
GET    /api/scenes/<id>/tasks/<tid>/files   — 任务文件列表
POST   /api/scenes/<id>/tasks/<tid>/files   — 添加文件
PUT    /api/scenes/<id>/tasks/<tid>/files/<fid> — 更新文件间隔
DELETE /api/scenes/<id>/tasks/<tid>/files/<fid> — 移除文件
```

**重写 `_get_orchestrator()`** — 替换 `_get_scheduler()`，回调支持场景→任务→文件三级执行

**保留旧路由**：`/schedule` 页面和 `/api/schedule/*` API 重定向到新路由（兼容过渡）

#### 3.3 场景执行逻辑
- **单文件场景**：读取单个任务→单个文件，SceneEmitter执行，循环间隔(秒)等待后重复
- **多文件场景**：
  - 串行任务：按文件列表顺序执行，文件间等待 `interval_sec` 秒
  - 并行任务：`ThreadPoolExecutor` 多线程同时执行多个文件
- 循环间隔、重复次数、执行超时都在**任务级别**控制

**验证**：单文件场景按间隔循环执行；多文件场景串行/并行执行正确；任务名称可修改

---

### 阶段四：前端重构

#### 4.1 新建 `web/pages/scene.html`
- 页面标题：🎬 场景编排
- 左栏：场景创建/编辑表单
  - 场景名称、仿真环境选择（下拉联动 `sim_env_config`）、场景类型(single/multi)
  - 单文件模式：文件选择器 + 循环间隔(秒)输入
  - 多文件模式：任务标签页切换 + 任务编辑器（名称、类型、文件列表、间隔）
  - Cron调度表达式构建器（日期+时间+重复）
- 右栏：场景列表卡片 + 执行历史

#### 4.2 新建 `web/static/js/scene.js`
- 场景CRUD、任务CRUD、文件CRUD完整实现
- 任务编辑器：内联修改任务名称、切换串行/并行、添加/移除/排序文件
- 文件选择器复用现有JSON文件列表API

#### 4.3 更新导航 — `web/static/js/common.js`
- `{ href: '/scene', icon: '🎬', label: '场景编排' }`

#### 4.4 添加页面路由 — `utm_simulator/web_server.py`
- `@app.route("/scene")` → 提供 `scene.html`

#### 4.5 清理旧文件
- 删除 `web/pages/schedule.html`、`web/static/js/schedule.js`
- 删除 `database/scheduler.py`（已被 orchestrator.py 替代）
- 删除旧 `/schedule` 路由

**验证**：新页面正常加载；场景创建/编辑/删除正常；任务增删改正常；文件列表操作正常

---

## 关键文件清单

| 文件 | 阶段 | 操作 |
|------|------|------|
| `database/mysql_db_manager.py` | 1, 2 | 修改：死锁重试、去重init_tables、替换DDL |
| `database/db_manager.py` | 2 | 修改：同步SQLite DDL |
| `database/orchestrator.py` | 3 | **新建**：场景编排调度器 |
| `database/migrate_scheduled_to_scene.py` | 2 | **新建**：数据迁移脚本 |
| `utm_simulator/web_server.py` | 1, 3, 4 | 修改：API路由替换、异常保护、新页面路由 |
| `web/pages/scene.html` | 4 | **新建**：场景编排页面 |
| `web/static/js/scene.js` | 4 | **新建**：场景编排前端逻辑 |
| `web/static/js/common.js` | 1, 4 | 修改：API修复、导航更新 |
| `database/scheduler.py` | 4 | **删除**：被orchestrator.py替代 |
| `web/pages/schedule.html` | 4 | **删除** |
| `web/static/js/schedule.js` | 4 | **删除** |

## 验证方式

1. **Bug修复验证**：并发创建任务不报500；批量保存不报404；API错误返回JSON格式
2. **初始化速度**：启动项目只建表一次，日志无重复"创建表"/"建表失败"
3. **场景编排功能**：创建单文件场景 → 设置30秒循环间隔 → 手动执行 → 确认30秒间隔后重复
4. **多文件场景**：创建多文件场景 → 添加2个任务（串行+并行）→ 各添加2个文件 → 手动执行 → 验证串行按序执行、并行同时执行
5. **任务名称修改**：编辑场景 → 修改任务名称 → 保存 → 确认名称更新
6. **环境选择**：创建场景时选择非默认环境 → 执行时确认使用选中环境的Redis/Kafka配置
