# 系统日志 & 运行日志优化计划

## Context

低空空管自动化测试平台（ATC/UTM）有两个日志功能需要优化：

1. **系统日志告警详情**：`/logs` 页面"实时告警"Tab 中，告警详情始终显示"⏳ 告警详情获取中…"而非真实数据。根因是 `situation_monitor.py::_fetch_alert_details()` 中 REST API 调用在多个环节静默失败（JWT Token 过期、HTTP 错误、响应格式不匹配），前端无超时/错误态处理。

2. **仿真执行页运行日志**：`/run` 页面当前只有单一扁平日志流，需改为 4 层可折叠结构——分别展示 Kafka 遥测、Trace 轨迹、冲突告警、ATC WebSocket 前端数据。参考 `atc_ha_test/ws_client_check.py` 的 SockJS+STOMP 连接模式。

---

## Part A：修复系统日志告警详情

### A1. `situation_monitor.py` — 增强错误日志 + 重试追踪

- `_fetch_alert_details()`（约 L641-724）：在每个返回 `None` 的分支增加 `print()` 和 `self._streamer.push("sim_status", msg)` 记录具体失败原因（无 Token、HTTP 非 200+响应体、code≠0、空列表）。
- 增加 `_alert_retry_count` / `_max_alert_retries=3`，失败累计、成功清零，超过上限后不再重试。
- 失败时在 detail 中标记 `_api_failed: True` 和 `_error: "..."`，供前端区分钟"加载中"与"失败"。
- `_get_token()`（约 L119-164）：每个 Token 来源失败时打印日志，兜底全部失败时 push 一条 `sim_status` 日志。

### A2. `situation_monitor.py` — STOMP warningTags 兜底

- 增加 `_pending_alarm_fallback` 标志位。
- `alarmStatistic` 处理中若 REST API 失败，设 `_pending_alarm_fallback = True`。
- 后续 `flightTrack` 消息中的 `_extract_warning_details()` 发现 warningTags 时，直接推送 `LOG_TYPE_ALARM`，`source="stomp_warning_tags"`，并清除 fallback 标志。

### A3. `logs.js` — 前端错误态 + 重试按钮

- `renderAlarmTab()`（L191-232）：增加 `_api_failed` 分支显示"⚠️ 告警详情 API 请求失败"和"重试"按钮；增加 `source="stomp_warning_tags"` 分支直接渲染告警列表；保留原有"加载中"和"无告警"逻辑。

### A4. `web_server.py` — 重试 API 端点

- 新增 `POST /api/sim/retry-alarm-details`，重置 `_alert_retry_count` 和 `_pending_alarm_fallback`，返回 `{"success": true}`。

---

## Part B：运行日志 4 层结构

### B1. `log_streamer.py` — 新增日志类型

- `LOG_TYPES` 增加：`"kafka_collision_alarm": "Kafka 冲突告警"`、`"ws_captured_data": "WebSocket 前端数据"`。

### B2. `web_server.py` — Kafka 冲突告警消费者

- 新增 `_start_collision_alarm_consumer()`：后台线程消费 `uav_collision_alarm` topic，通过 `LogStreamer.push("kafka_collision_alarm", ...)` 和 `socketio.emit("collision_alarm", msg)` 推送。
- 在 `_get_streamer()` 或启动流程中调用。

### B3. `sim_manager.py` + `web_server.py` — 遥测/Trace 实时推送

- `sim_manager.py`：`SimulationManager.__init__` 增加 `trace_callback` 参数；`_consume_trace()` 中 filtered 有数据时调用 `trace_callback({"count", "data", "key"})`。
- `web_server.py`：创建 SimulationManager 时传入 `trace_callback=lambda d: socketio.emit("trace_data", d)`；在 `_sim_loop` 中发送遥测后调用 `socketio.emit("telemetry_data", {"records": ..., "count": ...})`。

### B4. `situation_monitor.py` — ATC WebSocket 数据采集

- 在 `_send_stomp_connect()` 增加对 `/topic/clusterChange` 的 SUBSCRIBE。
- `_process_body()` 中处理集群健康消息（`"clusters" in data`），push 为 `ws_captured_data`。
- `_process_body()` 末尾对已处理的数据 push 摘要 `ws_captured_data`（节流避免洪泛）。

### B5. `common.js` — 注册新 SocketIO 事件

- `_wsCallbacks` 增加：`telemetry_data`、`trace_data`、`collision_alarm`、`ws_captured`。
- `getSocket()` 增加对应的 `_socket.on(...)` 监听。

### B6. `run.html` — 四层可折叠面板 HTML

- 替换 L173-189 的单一 `log-panel` 为 5 个 `.log-layer`（遥测/Trace/告警/WS/系统日志）。
- 每层有 `log-layer-header`（点击折叠/展开 + 徽章计数）+ `log-layer-body`。
- 系统日志层折叠保留原有类型筛选复选框。

### B7. `run.js` — 四层独立数据管理

- 新增 `telemetryLogs`、`traceLogs`、`collisionLogs`、`wsCapturedLogs` 数组。
- 新增 `onWsEvent('telemetry_data', ...)`、`onWsEvent('trace_data', ...)`、`onWsEvent('collision_alarm', ...)`、`onWsEvent('ws_captured', ...)` 处理函数。
- 新增 `renderTelemetryLayer()` / `renderTraceLayer()` / `renderCollisionLayer()` / `renderWsCapturedLayer()` 渲染函数（各显示最新 20-30 条，带自动滚动）。
- 新增 `toggleLogLayer(header)` 折叠切换 + `updateBadge(id, count)`。
- 更新清空/导出逻辑覆盖全部 4 层数据。

### B8. `style.css` — 层样式

- 新增：`.log-layer`、`.log-layer-header`、`.log-layer-toggle`、`.log-layer-title`、`.log-layer-badge`、`.log-layer-body`。

---

## 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/situation_monitor.py` | 修改 | A1+A2+B4：错误日志、重试、warningTags 兜底、ws_captured_data、clusterChange 订阅 |
| `database/log_streamer.py` | 修改 | B1：新增 2 个 LOG_TYPES |
| `utm_simulator/sim_manager.py` | 修改 | B3：trace_callback 参数 |
| `utm_simulator/web_server.py` | 修改 | A4+B2+B3：retry 端点、collision 消费者、telemetry/trace 推送 |
| `web/static/js/common.js` | 修改 | B5：新 SocketIO 事件注册 |
| `web/static/js/logs.js` | 修改 | A3：告警 Tab 错误态 + 重试 + warningTags 兜底渲染 |
| `web/static/js/run.js` | 修改 | B7：四层数据管理 + 渲染 + 折叠 |
| `web/pages/run.html` | 修改 | B6：四层面板 HTML |
| `web/static/css/style.css` | 修改 | A3+B8：告警错误态样式 + 层样式 |

## 实施顺序

```
Phase 1: 告警修复（可并行于 Phase 2）
  A1 → A2 → A3+A4

Phase 2: 运行日志 4 层（可并行于 Phase 1）
  B1 → B2+B3 → B4+B5 → B6+B7+B8
```

## 验证方式

1. 启动 `start_web.ps1`，打开 `/logs` 页面 → "实时告警"Tab：确认 API 失败时显示错误信息和重试按钮，成功时显示告警详情列表
2. 打开 `/run` 页面 → "运行日志"面板：确认 4 层结构存在，启动仿真后各层实时更新数据，折叠/展开正常
3. 检查 `/api/sim/retry-alarm-details` 返回 `{"success": true}`
4. 确认新增的 SocketIO 事件 `telemetry_data`、`trace_data`、`collision_alarm`、`ws_captured` 在浏览器 DevTools Network WS 面板可见
