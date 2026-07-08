# 态势监控日志功能实施方案

## Context

下游 ATC 系统（`dkkgsit-test.testdolphin.com`）在仿真过程中通过 WebSocket STOMP 实时推送态势数据，但这些数据目前没有被采集到系统日志中。`log_streamer.py` 已预留 `db_traffic`、`db_alarm` 类型但未接入实际数据源。

## 关键调研发现

### 数据存放位置

| 数据类型 | 来源 | 协议 | 地址/订阅 |
|---------|------|------|---------|
| **监视目标数** | ATC WebSocket | STOMP | `/flightTrack/SEAT0001` — `uavs`/`flightTrack` 列表长度 |
| **实时飞行计划数** | ATC WebSocket | STOMP | `/dataPush/seat/SEAT0001` — `flowStatistic.totalCount` |
| **实时告警数** | ATC WebSocket | STOMP | `/dataPush/seat/SEAT0001` — `alarmStatistic.value` |
| 冲突告警详情 | Kafka | — | `uav_collision_alarm` topic（暂不接入） |

### 消息解析格式（来自 `atc_api_autotest/api_tools/客户端ws无人机数量统计.py`）

- **alarmStatistic**: `{"type": "alarmStatistic", "value": "5"}` → 告警数
- **flowStatistic**: `{"type": "flowStatistic", "value": "{\"totalCount\": 100}"}` → 飞行计划数（value是嵌套JSON）
- **UAV count**: `{"uavs": [...]}` 或 `{"flightTrack": [...]}` → 监视目标数 = len(uavs) + count of flightTrack items with uavIdentifyCode

### JWT Token 获取

复用 `atc_api_autotest/api_tools/Jwt_Token_get.py` 的 `get_jwt_token()`（同 `sim_api_bridge.py` 模式），通过环境变量 `ATC_JWT_TOKEN` 或自动登录获取。

### 现有日志架构

- `LogStreamer` 单例管理 8 种日志类型（含预留的 `db_traffic`、`db_alarm`）
- `push(type, msg)` → buffer + callback → `socketio.emit("log_entry", entry)` → 前端 `logs.js`
- 新增类型仅需：① `LOG_TYPES` 字典添加 key ② `logs.html` 添加 checkbox
- `logs.js` 无需修改（自动识别新 type）

---

## 实施方案

### 1. 新建 `utm_simulator/situation_monitor.py`（~220 行）

```
class SituationMonitor:
    __init__(base_url, streamer, jwt_token=None)
    ├── base_url: "wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp"
    ├── streamer: LogStreamer 实例（通过 _get_streamer() 获取）
    └── jwt_token: 从环境变量 ATC_JWT_TOKEN 获取，或自动调用 get_jwt_token()

    start() → 启动后台线程
    ├── 线程 _run_forever():
    │   ├── SockJS /info 握手 → 生成完整 ws URL
    │   ├── websocket.WebSocketApp 连接（SSL不验证）
    │   ├── on_open → STOMP CONNECT 帧
    │   ├── 延迟 0.3s → SUBSCRIBE /flightTrack/SEAT0001
    │   ├── 延迟 0.5s → SUBSCRIBE /dataPush/seat/SEAT0001
    │   ├── on_message → SockJS 协议解析 → _handle_payload → _process_body
    │   └── on_close → 断线重连（指数退避 3s→30s）

    _process_body(data)
    ├── type="alarmStatistic" → streamer.push("situation_alarm", f"告警数: {value}")
    ├── type="flowStatistic" → streamer.push("situation_plan", f"飞行计划数: {totalCount}")
    └── uavs/flightTrack → streamer.push("situation_uav", f"监视目标: {count} 架")（每10秒汇总一次避免刷屏）

    stop() → self._running = False, ws.close()
```

**参考实现**：`atc_api_autotest/api_tools/客户端ws无人机数量统计.py` 的 `ReceiverWsStats` 类

### 2. 修改 `utm_simulator/log_streamer.py`

在 `LOG_TYPES` 字典中新增 3 条：

```python
"situation_uav":   "态势-监视目标",
"situation_plan":  "态势-飞行计划",
"situation_alarm": "态势-实时告警",
```

### 3. 修改 `utm_simulator/web/pages/logs.html`

在 `#log-type-filters` 内、现有 8 个 checkbox 之后，新增分组区块：

```html
<div style="margin-top:12px;padding-top:8px;border-top:1px solid #2a3a5c;">
  <div style="font-size:11px;color:#82aaff;margin-bottom:6px;">🛡️ 态势监控日志</div>
  <label class="plan-route-item"><input type="checkbox" class="log-type-cb" value="situation_uav" checked> 监视目标</label>
  <label class="plan-route-item"><input type="checkbox" class="log-type-cb" value="situation_plan" checked> 飞行计划</label>
  <label class="plan-route-item"><input type="checkbox" class="log-type-cb" value="situation_alarm" checked> 实时告警</label>
</div>
```

### 4. 修改 `utm_simulator/web_server.py`

新增惰性初始化（遵循已有的 `_get_xxx()` 模式）：

```python
_situation_monitor = None

def _get_situation_monitor():
    global _situation_monitor
    if _situation_monitor is None:
        from situation_monitor import SituationMonitor
        _situation_monitor = SituationMonitor(
            base_url="wss://dkkgsit-test.testdolphin.com/la-atc-ws-backend/ws/stomp",
            streamer=_get_streamer(),
        )
    return _situation_monitor
```

在 `SimulationRunner.start()` 中调用 `_get_situation_monitor().start()` 以在仿真启动时自动开始态势监控。

### 5. 修改 `utm_simulator/requirements.txt`

添加：`websocket-client>=1.6.0`

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/situation_monitor.py` | **新建** | 态势监控采集器（~220 行） |
| `utm_simulator/log_streamer.py` | 修改 | `LOG_TYPES` +3 条 |
| `utm_simulator/web/pages/logs.html` | 修改 | 新增态势监控过滤分组 |
| `utm_simulator/web_server.py` | 修改 | `_get_situation_monitor()` + `SimulationRunner.start()` 启动 |
| `utm_simulator/requirements.txt` | 修改 | +`websocket-client` |

## 验证方式

1. `pip install websocket-client` 安装依赖
2. 启动 Web 服务：`cd utm_simulator && conda run -n utm python web_server.py`
3. 打开 http://localhost:5000/logs → 确认左侧出现"🛡️ 态势监控日志"分组（3 个 checkbox）
4. 打开 http://localhost:5000/config → 启动任意仿真模式
5. 切回 /logs → 观察是否出现 `[situation_uav]`、`[situation_plan]`、`[situation_alarm]` 日志条目
6. 取消勾选态势相关 checkbox → 确认过滤生效
7. 检查服务端控制台 → 确认 STOMP 握手日志正常（`SockJS连接已打开`、`STOMP握手成功`）
