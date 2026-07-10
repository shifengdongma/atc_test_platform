# 系统日志板块：告警详情 + 飞行计划计数修复

## Context

系统日志（`/logs` 页面）存在两个 bug：
1. **实时告警板块**：显示"（无告警详情，来自 alarmStatistic 计数）"，无法查看具体告警信息
2. **实时飞行计划数**：显示 1→0，但下游系统和 Redis 中实际有 2 条飞行计划

这两个 bug 在 commit `9130f42` 中已尝试修复，但修复不完整。根因是**同一问题**：`SituationMonitor._get_token()` 永久缓存 JWT Token，过期后不刷新，导致 `_fetch_alert_details()` 和 `_fetch_plan_details()` 两个 REST API 调用全部静默失败。

### 数据流

```
ATC WebSocket (STOMP) → situation_monitor.py → log_streamer.py → WebSocket → logs.js (前端)
                              │                       │
                              ├─ _fetch_alert_details()    ← REST API (依赖 JWT)
                              └─ _fetch_plan_details()     ← REST API (依赖 JWT)
```

### Token 缓存问题

- `Jwt_Token_get.py` 模块级 `_token_cache` 有完善的过期检测（`exp > time.time() + 60`），过期自动重新登录
- `situation_monitor.py` 的 `_get_token()` 把 token 存在 `self._jwt_token`，首次获取后**永不刷新**，完全绕过了 `Jwt_Token_get.get_jwt_token()` 的缓存机制
- Token 过期后，WebSocket 连接仍存活（已建立连接），但 REST API 调用全部静默失败返回 `None`

## 修改方案

### 文件 1: `utm_simulator/situation_monitor.py`（核心修改）

#### A. 添加 `_parse_token_exp()` 方法
新增静态方法解析 JWT exp 时间戳，用于本地过期判断（不依赖导入 Jwt_Token_get）。

#### B. 改写 `_get_token()` — 支持自动刷新（修复两个 bug 的共同根因）
- 返回缓存 token 前检查 `exp > time.time() + 60`
- 过期时清除 `self._jwt_token`，重新调用 `Jwt_Token_get.get_jwt_token()`（利用其模块级缓存+自动刷新）
- 保留环境变量和 ha_test 回退路径

#### C. 修复 `alarmStatistic` 去重 — 允许失败重试
- **当前行为**：先更新 `_last_alarm_count`，再调用 `_fetch_alert_details()`；API 失败后同计数的后续消息被跳过
- **修复**：仅在 `_fetch_alert_details()` 成功时更新 `_last_alarm_count`；失败时保持旧值，下次消息触发重试

#### D. `_fetch_alert_details()` 失败时推送错误日志
- 当前仅 `print()` 到控制台，前端看不到
- 修复：失败时调用 `self._streamer.push("sim_status", msg)` 推送到前端

#### E. `_fetch_plan_details()` — 添加 Redis 兜底
- 拆分为 `_fetch_plan_details_from_api()` + `_fetch_plan_details_from_redis()`
- `_fetch_plan_details()` 先调 API，失败则回退到 Redis `BIZ_DATA:UAV_ROUTE` Hash 直接读取
- Redis 读取每个 field 的 `flightPlanList[]`，汇总所有计划条目
- 同样添加错误日志推送

#### F. flowStatistic 处理器 — 交叉校验 Redis 计数
- `_fetch_plan_details()` 返回结果后，与 flowStatistic 的 `totalCount` 比较
- 若 Redis 计划数 > WS 统计数，在 detail 中添加 `redisCount` 和 `countMismatch: true`

### 文件 2: `utm_simulator/web/static/js/logs.js`（前端优化）

#### G. `renderAlarmTab()` — 改进告警状态展示
- **有 warnings 数据时**：正常渲染告警详情（不变）
- **alarmStatistic 来源且 total > 0 但无 warnings**：显示 "⏳ 正在获取 N 条告警详情..."
- **alarmStatistic 来源且 total == 0**：显示 "当前无告警 ✅"
- **其他情况**：显示 "（无告警详情）"

#### H. `renderPlanTab()` — 显示计数不匹配提示
- 当 `detail.countMismatch` 为 true：显示 "⚠️ Redis 实际: N 条"
- 当 `totalCount` 有值但无 `plans`：显示 "(计划列表 API 不可用)"

### 文件 3: `utm_simulator/web/static/css/style.css`（样式补充）

#### I. 新增告警状态 CSS 类
- `.alarm-item-loading` / `.alarm-item-empty` / `.alarm-item-error` 颜色区分

## 关键文件

| 文件 | 变更类型 |
|------|---------|
| `utm_simulator/situation_monitor.py` | **主要修改** — Token 刷新、API 重试、Redis 兜底 |
| `utm_simulator/web/static/js/logs.js` | 前端状态展示优化 |
| `utm_simulator/web/static/css/style.css` | CSS 补充 |

## 验证方式

1. **Token 刷新**：启动仿真后等待足够长时间（超过 token 有效期），确认 `_get_token()` 自动刷新而非返回过期 token
2. **告警详情**：触发告警场景，确认实时告警 Tab 显示具体告警内容（UAV 编号、类型、消息），而非"无告警详情"
3. **飞行计划数**：Redis 中写入 2 条飞行计划，确认系统日志显示 2 条；当 API 不可用时，Redis 兜底仍能显示正确计划列表
4. **错误可见性**：关闭网络后查看"全部日志"Tab，确认能看到 REST API 失败的错误日志
5. **前端边界**：确认 `detail` 为 null、`warnings` 缺失、`plans` 缺失时不报 JS 错误
