# 系统日志板块修复方案

## Context

系统日志（`/logs` 页面）存在 5 个问题，影响监视目标、飞行计划、实时告警三个核心 Tab 的正常使用。用户要求修复所有问题，并将日志持久化到 MySQL 数据库以便任务结束后导出。

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `utm_simulator/situation_monitor.py` | Issue 1/2/3 — 数值类型转换、飞行计划去重、告警详情 API 调用 |
| `utm_simulator/web/static/js/logs.js` | Issue 1/4 — fmtNum 防御性格式化、刷新按钮、轮询间隔 |
| `utm_simulator/web/pages/logs.html` | Issue 4 — 刷新按钮 HTML |
| `utm_simulator/web/static/css/style.css` | Issue 4 — 刷新按钮动画样式 |
| `utm_simulator/log_streamer.py` | Issue 5 — MySQL 持久化、导出方法 |
| `utm_simulator/web_server.py` | Issue 5 — `/api/logs/export/db` 端点 |

---

## Issue 1: `uav.speed.toFixed is not a function`

**根因**: ATC 下发的数值字段可能是字符串，后端透传未做类型转换，前端 `!= null` 无法防御非数字类型。

### 后端修复 (`situation_monitor.py`)

1. 在 `_extract_uav_details` 方法前添加 `_to_float()` 辅助函数（约第 526 行之前）
2. 修改 `item` 字典中 6 个数值字段：`longitude`、`latitude`、`geodeticAltitude`、`trackAngle`、`speed`、`verticalSpeed` 全部包裹 `_to_float()`

### 前端修复 (`logs.js`)

1. 在文件顶部（第 4 行之后）添加 `fmtNum(val, decimals, suffix)` 辅助函数：检查 `typeof val === 'number' && isFinite(val)`
2. 替换第 98-103 行的 6 个 `.toFixed()` 调用为 `fmtNum()` 调用

---

## Issue 2: 飞行计划不更新且与下游数据不一致

**根因**: 去重仅比较 `totalCount`，当总数不变但子状态（待处理→执行中）变化时不会推送。

### 修复 (`situation_monitor.py`)

1. 将 `self._last_plan_count`（第 95 行）替换为 `self._last_plan_key = ""`（复合键）
2. 修改 `_process_body()` 中 flowStatistic 处理逻辑（第 420-443 行）：构建 `"total|waiting|active|completed|rejected|cancelled"` 复合键进行去重比较
3. 额外增强：调用 ATC REST API `POST /flight/plan/realtimePlanPage` 获取实时计划列表详情，丰富 `detail` 字段（调用时使用 `_get_token()` 获取 JWT）

---

## Issue 3: 实时告警无详情（"无告警详情，来自 alarmStatistic 计数"）

**根因**: `alarmStatistic` 消息仅含数字统计，不含每条告警的详情。`flightTrack.warningTags` 中的告警数据可能未及时到达。

### 修复 (`situation_monitor.py`)

1. 新增 `_fetch_alert_details(count)` 方法：调用 ATC REST API `POST /alert/search` 获取最近告警列表（含 UAV 编号、告警类别、等级、原因、时间）
2. 修改 `alarmStatistic` 处理逻辑（第 407-417 行）：当 `alarm_count > 0` 时调用 `_fetch_alert_details()`，将返回的详情写入 `detail["warnings"]`
3. JWT 认证复用 `self._get_token()` 方法

---

## Issue 4: 缺少自动刷新和手动刷新按钮

### 修复

1. **`logs.js`**: 
   - 轮询间隔从 5 秒改为 10 秒（第 325、330、354 行）
   - 添加刷新按钮点击事件（清空 `logs[]` → 重新 `fetchInitialLogs()` → Toast 提示）
2. **`logs.html`**: 在清空按钮（第 59 行）后添加 `<button id="btn-logs-refresh" class="btn btn-small btn-refresh">🔄 刷新</button>`
3. **`style.css`**: 添加 `.btn-refresh` 和 `.btn-refresh.refreshing::before` 旋转动画样式

---

## Issue 5: 日志 MySQL 持久化 + 任务结束后导出

### 修复 (`log_streamer.py`)

1. 添加 MySQL 导入（从 `mysqldbclient` 导入 `MysqlDbClient`，带 fallback）
2. 新增 `_mysql_enabled`、`_mysql_client` 属性（延迟初始化）
3. 新增方法：
   - `_get_mysql_client()` — 延迟连接
   - `_ensure_mysql_table()` — 创建 `sim_system_logs` 表（id, time, type, type_name, message, detail, task_id, created_at）
   - `export_logs_from_db(start_date, end_date, types, keyword, limit)` — 从 MySQL 按日期范围导出
   - `_cleanup_old_logs(days=7)` — 定期清理 7 天前的日志
4. 修改 `push()` 方法：在内存缓冲区写入后同步写入 MySQL

### 修复 (`web_server.py`)

1. 新增 `POST /api/logs/export/db` 端点：接收 `start_date`、`end_date`、`types`、`keyword`、`format` 参数，返回 JSON/CSV 文件下载

---

## 实现顺序

1. Issue 1（数值转换）— 最关键的运行时错误
2. Issue 2（飞行计划去重）
3. Issue 3（告警详情 API）
4. Issue 4（刷新按钮 + 10s 轮询）
5. Issue 5（MySQL 持久化）

---

## 验证方式

1. **Issue 1**: 确认监视目标 Tab 中 UAV 卡片正常渲染，无 `toFixed` 报错
2. **Issue 2**: 确认飞行计划子状态变化时 Tab 能更新；对比下游 Dashboard 数据一致性
3. **Issue 3**: 确认实时告警 Tab 显示具体告警内容（UAV 编号、告警类型、消息），而非"无告警详情"
4. **Issue 4**: 点击刷新按钮有动画，10 秒后自动刷新，日志为最新数据
5. **Issue 5**: 日志写入 MySQL `sim_system_logs` 表；调用 `/api/logs/export/db` 可导出指定日期范围的日志文件
