# 系统日志详情增强 + Tab 分类展示

## Context

用户已在上一轮工作中完成了态势监控日志的基本框架（`situation_monitor.py` 连接 ATC WebSocket，向 `LogStreamer` 推送 `situation_uav`/`situation_plan`/`situation_alarm` 三类日志）。但当前日志只记录了简单的**数量**（如"监视目标数: 5 架"），ATC WebSocket 下发的丰富详情（每架 UAV 的位置/高度/速度/航向/状态/分类、告警标签内容、飞行计划各状态子计数）全部被丢弃。

本次增强目标：**将丢弃的详细信息结构化记录到日志中，前端按 Tab 分类展示，并支持导出**。

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/log_streamer.py` | 修改 | `push()` 增加 `detail` 可选参数；CSV 导出增加 detail 列 |
| `utm_simulator/situation_monitor.py` | 修改 | 新增 UAV 详情/告警详情提取方法；`_process_body` 推送结构化 detail |
| `utm_simulator/web/pages/logs.html` | 重写 | 竖排 Tab 栏（监视目标/飞行计划/实时告警/全部日志）+ 4 个内容面板 |
| `utm_simulator/web/static/js/logs.js` | 重写 | Tab 切换逻辑 + 按类别渲染详情卡片 + 导出含 detail 数据 |
| `utm_simulator/web/static/css/style.css` | 追加 | UAV 详情卡片、飞行计划摘要、告警卡片等新样式 |
| `docs/utm-simulator-optimization-work-log.md` | 追加 | 记录本次优化 |

## 实现步骤

### Step 1: `log_streamer.py` — 日志条目增加 `detail` 字段

- `push()` 签名增加 `detail: Optional[Dict] = None`，仅当非 None 时写入 entry
- `export_logs()` CSV 格式增加 `type_name` 和 `detail` 列（detail 序列化为 JSON 字符串）
- `get_logs()` 无需改动 — 缓冲区条目直接透传

### Step 2: `situation_monitor.py` — 从 ATC 消息提取结构化详情

- 新增常量 `OPERATING_STATUS_LABELS`（0-5 中文标签）、`CLASSIFICATION_LABELS`（1-5 无人机分类标签）
- 新增 `_extract_uav_details()` — 从 flightTrack/uavs 提取每架 UAV 的关键字段列表（识别码、经纬度、高度、速度、航向、升降速、运行状态+标签、分类+标签、实名签、时间戳、warningTags 数量）
- 新增 `_extract_warning_details()` — 从 flightTrack 的 warningTags 提取告警详情列表（UAV 识别码、告警类型、消息、时间戳）
- 修改 `_process_body()`：
  - **监视目标**：调用 `_extract_uav_details()`，推送 `detail: {count, uavs: [...]}` 
  - **实时告警**：调用 `_extract_warning_details()`，通过内容哈希去重后推送 `detail: {total, warnings: [...]}`
  - **飞行计划**：解析 flowStatistic 的 6 个子计数，推送 `detail: {totalCount, waitingCount, activeCount, completedCount, rejectedCount, cancelledCount}`，message 中显示完整状态摘要
- `_push_log()` 增加 `detail` 参数并透传给 streamer

### Step 3: `logs.html` — Tab 布局重构

- **左侧面板**（240px）改为竖排 Tab 按钮栏：
  - 🛸 监视目标 | 📋 飞行计划 | ⚠️ 实时告警 | 📜 全部日志
  - 使用 `.gen-tab` + `data-gentab` 模式（复用现有 CSS）
  - 底部保留关键字搜索 + JSON/CSV 导出按钮
- **右侧面板**改为 flex column 布局：
  - 顶部工具栏（标题 + 暂停/清空/统计）
  - 4 个 `.gen-tab-content` 面板（`id="gentab-{value}"`），默认激活监视目标
  - 全部日志面板保留 `.log-stream` 样式

### Step 4: `logs.js` — Tab 感知渲染 + 详情卡片

- 数据存储扩展：`logs[]` 每项增加 `type_name`、`detail` 字段
- `initLogsTabs()` — 按 `generate.js` 的 `.gen-tab` 切换模式实现
- 分类渲染函数：
  - `renderUavTab()` — 最近一条日志显示 UAV 摘要卡片（可展开，显示每架 UAV 的识别码/位置/高度/速度/航向/状态/分类网格）；历史日志显示折叠的时间线
  - `renderPlanTab()` — 彩色状态摘要条（待/执/完/拒/取 5 色）+ 变更历史列表
  - `renderAlarmTab()` — 告警卡片（红色调），显示告警列表（UAV 识别码/告警类型/消息/时间）
  - `renderAllTab()` — 保持现有纯文本日志流
- `addLogEntry()` 接受 detail 参数；`onWsEvent('log_entry')` 映射 `data.detail`
- `exportLogs()` 导出当前 Tab 过滤后的日志（JSON 含 detail，CSV 增加 detail 列）
- 轮询 API 映射 `l.detail` 字段

### Step 5: `style.css` — 详情卡片样式

- `.uav-card` / `.uav-card-header` / `.uav-card-body` — UAV 可展开卡片
- `.uav-detail-card` / `.uav-detail-grid` — UAV 字段网格
- `.plan-summary` / `.plan-summary-item` — 飞行计划状态摘要条（带左侧彩色边框）
- `.alarm-card` / `.alarm-card-header` / `.alarm-item` — 告警卡片（红色调半透明背景）
- 使用现有 CSS 变量（`--bg-card`, `--border`, `--accent-bright`, `--danger`, `--warning`, `--success`, `--text-dim`）

### Step 6: 更新工作日志

按 `docs/utm-simulator-optimization-work-log.md` 格式追加本次优化记录。

## 向后兼容

- 非态势日志类型（redis_route, kafka_telemetry, sim_status 等）无 `detail` 字段，在"全部日志"Tab 中正常渲染
- API `/api/logs` 仅在条目有 detail 时返回该字段（加法变更）
- WebSocket `log_entry` 事件的 `detail` 字段为可选，现有消费者不受影响

## 验证方式

1. 启动 `web_server.py`，打开 `/logs` 页面，确认 4 个 Tab 正常切换
2. 启动仿真（触发 SituationMonitor），观察监视目标 Tab 是否展示 UAV 详情卡片
3. 观察飞行计划 Tab 是否展示状态摘要条
4. 观察实时告警 Tab 是否展示告警卡片（需 ATC 环境有活跃告警）
5. 切换到"全部日志"Tab，确认传统日志流正常
6. 点击导出 JSON/CSV，确认文件包含 detail 结构化数据
7. 关键字搜索、暂停/恢复、清空功能在各 Tab 下正常工作
