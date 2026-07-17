# 定时任务优化 + 仿真数据注入修复 实施计划

## Context

两个问题的根因分析和修复方案：

### 问题1：非 plan 模式下游 Dashboard 无法显示"监视目标数"

- **scene 模式**：`run_kafka_scene.py:_build_redis_route()` 使用 JSON 文件原始时间戳作为 `planTakeoffTime`/`planLandTime`，ATC 后端读到已过期的计划，不激活追踪
- **replay 模式**：已有时间平移和定时刷新，但遥测缺少 `active: 1` 字段，首次激活时序窗口较宽

### 问题2：定时任务只能选择单个 JSON 文件

- 当前 UI 只支持选择一个 JSON 文件 + 一个仿真模式
- 需要支持批量创建多个独立任务，每个可配置不同的 JSON 文件、仿真模式、cron 时间

---

## 实施步骤

### Step 1: 修复 Scene 模式 — 时间平移 (`utm_simulator/tools/run_kafka_scene.py`)

修改 `_build_redis_route()` 方法（约第 518-558 行）：
- 保存原始起降时间计算的 `duration`
- 将 `planTakeoffTime` 改为 `time.time()`（当前时间）
- 将 `planLandTime` 改为 `time.time() + duration`
- 保持 `duration` 至少 60 秒保底

修改遥测发送逻辑（`_emit_loop` 附近）：
- 每条发往 Kafka 的遥测记录添加 `"active": 1` 字段

### Step 2: 修复 Replay 模式 — `active` 字段 + 首次刷新 (`utm_simulator/sim_manager.py`)

修改 `_tick_replay()`（约第 614-639 行）：
- 在 `msg = dict(msgs[cursor])` 后添加 `msg["active"] = 1`

修改 `_init_replay_mode()`（约第 449-494 行）：
- 航线写入 Redis 完成后，追加一次立即全量刷新（调用 `_shift_plan_times` + `hset`）

### Step 3: 定时任务批量创建 — 后端 API (`utm_simulator/web_server.py`)

在 `/api/schedule/tasks` 路由区域（约第 2115 行附近）新增：
- `POST /api/schedule/tasks/batch` — 接受 `{"items": [...]}` 数组，逐条调用 `add_task()` 创建，返回成功列表

### Step 4: 定时任务批量创建 — 前端 UI

修改 `web/pages/schedule.html`：
- 在表单区域添加"单个/批量"切换标签
- 批量模式下显示可编辑表格（JSON文件、仿真模式、cron时间、参数、删除按钮）
- "添加一行"按钮追加空行
- "批量保存"按钮调用 `/api/schedule/tasks/batch`

修改 `web/static/js/schedule.js`：
- 新增 `switchToBatchMode()` / `switchToSingleMode()` 切换逻辑
- 新增 `addBatchRow()` / `removeBatchRow(index)` 行操作
- 新增 `batchSaveTasks()` 批量提交
- 保存成功后刷新任务列表

### Step 5: 更新工作日志和总结

- 更新 `docs/utm-simulator-optimization-work-log.md`
- 更新 `docs/工作总结.md`

---

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/tools/run_kafka_scene.py` | 修改 | `_build_redis_route()` 时间平移 + 遥测 `active: 1` |
| `utm_simulator/sim_manager.py` | 修改 | `_tick_replay()` 添加 `active: 1`；`_init_replay_mode()` 首次刷新 |
| `utm_simulator/web_server.py` | 修改 | 新增 `POST /api/schedule/tasks/batch` 批量 API |
| `web/pages/schedule.html` | 修改 | 批量模式 UI（表格切换、行操作按钮） |
| `web/static/js/schedule.js` | 修改 | 批量模式 JS 逻辑 |
| `docs/utm-simulator-optimization-work-log.md` | 更新 | 记录本次优化 |
| `docs/工作总结.md` | 更新 | 记录本次工作总结 |

---

## 验证方式

1. **Scene 模式修复验证**：
   - 启动 scene 模式注入一个测试 JSON 文件
   - 打开 `https://dkkgsit-test.testdolphin.com/atc/situation-monitoring`
   - 确认"监视目标数"显示正确的无人机数量

2. **Replay 模式修复验证**：
   - 启动 replay 模式
   - 确认下游 Dashboard 显示"监视目标数"

3. **定时任务批量创建验证**：
   - 打开 `/schedule` 页面
   - 切换到批量模式
   - 添加 3 行任务（不同 JSON 文件 + 不同模式）
   - 批量保存
   - 确认任务列表显示 3 条独立任务
   - 手动"立即执行"其中一条，确认正常工作
