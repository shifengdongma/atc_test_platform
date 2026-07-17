# 优化计划：地图瓦片、运行日志、仿真模式修复

## Context

ATC 测试平台有三个问题需要修复：
1. "飞行计划可视化"页面默认使用 CartoDB 瓦片源（国外 CDN），而非高德地图（国内加载更快）
2. "实时监控"→"运行日志"面板在启动仿真后各层日志无数据显示
3. "仿真执行"中仅"redis计划插值"模式能让下游态势监控系统看到数据，其他四种 JSON 文件注入模式不行

---

## Task 1: 地图瓦片源优先级调整

**文件**: `web/static/js/map.js`（仅 2 行修改）

| 行号 | 当前值 | 改为 | 说明 |
|------|--------|------|------|
| 82 | `let _tileProviderKey = 'cartodb'` | `let _tileProviderKey = 'gaode'` | 默认使用高德 |
| 83 | `const TILE_FALLBACK_ORDER = ['cartodb', 'osm', 'gaode']` | `const TILE_FALLBACK_ORDER = ['gaode', 'cartodb', 'osm']` | 回退顺序：高德→CartoDB→OSM |

> 注释（62行、114行）已是"高德为默认"，无需修改。

---

## Task 2: 运行日志实时捕获

**根因**：后端在多种模式下未向前端推送日志事件，导致前端 5 个日志层收不到数据。

### 2.1 `ws_captured` 事件桥接（Layer 4: ATC WebSocket 前端数据）

**文件**: `utm_simulator/web_server.py:207-213`，修改 `_get_streamer()` 的 `_ws_push` 回调：

在 `socketio.emit("log_entry", entry)` 后增加判断——当 `entry["type"] == "ws_captured_data"` 时，**同时** emit `ws_captured` 事件给前端 Layer 4。

### 2.2 replay 模式缺少 telemetry/trace 回调（Layer 1+2）

**文件**: `utm_simulator/web_server.py:459-461`

当前 replay 模式创建 `SimulationManager` 时缺少回调参数，改为：

```python
self._sim_mgr = SimulationManager(self._app_cfg, log_callback=_add_log,
                                  trace_callback=lambda d: socketio.emit("trace_data", d),
                                  telemetry_callback=lambda d: socketio.emit("telemetry_data", d))
```

### 2.3 scene 模式缺少遥测推送（Layer 1）

**文件**: `utm_simulator/web_server.py:572-584`，在 scene 模式的 `while` 循环中，每次 `_push_status()` 前增加遥测计数桥接。

### 2.4 dynamic 模式冲突告警跳过提示（Layer 3）

**文件**: `utm_simulator/web_server.py:706-711`，在已有的 `print()` 后追加 `_add_log(...)` 调用，向前端日志面板告知冲突告警消费者已跳过。

### 2.5 replay_once 模式缺少 trace 数据推送（Layer 2）

**文件**: `utm_simulator/web_server.py:518-533`，在 `replay_once` 循环中增加 Kafka trace consumer 轮询，有消息时 emit `trace_data`。

---

## Task 3: 非 Redis 插值模式下仿真数据可被下游感知

**根因**：下游 ATC 态势系统需要 **Redis 飞行计划 + Kafka 遥测** 两样齐全才能显示"监视目标数"。

### 3.1 scene 模式：Redis 写入时序修复

**文件**: `utm_simulator/tools/run_kafka_scene.py:257-272`

当前顺序：`emit 线程启动 → trace 线程启动 → 写 Redis 航线`  
正确顺序：**先写 Redis 航线 → 再启动 emit 线程 → 最后 trace 线程**

原因：emit 线程启动后立即向 Kafka 发遥测，但 Redis 中尚无飞行计划，下游 UTM 收到遥测后无法关联到计划，无人机不会出现在监视列表。

### 3.2 scene 模式：operatingStatus 补齐

**文件**: `utm_simulator/tools/run_kafka_scene.py:355-357`

在 `_emit_once()` 中发送前检查 `operatingStatus`，缺失时设为 `2`（飞行中），确保下游 UTM 将 UAV 识别为活跃状态。

### 3.3 dynamic 模式：遥测桥接进程健康监控

**文件**: `utm_simulator/web_server.py:424-453`（dynamic 模式循环）

- 初始化 `_tick_count_telemetry = 0`
- 每 30 个 tick（约 30 秒）通过 `proc.poll()` 检查 bridge 子进程存活
- 若已退出则自动重启并记录日志
- 启动 bridge 时做 0.5 秒延迟验证

### 3.4 replay 模式：Redis 航线写入验证 + operatingStatus 补齐

**文件**: `utm_simulator/sim_manager.py:477`（航线写入后）和 `:488-491`（遥测加载后）

- 航线写入后做 `hgetall` 验证，写入为空时打 Warning 日志
- 加载 `kafka_data` 建索引后遍历补齐缺失的 `operatingStatus = 2`

### 3.5 scene 模式：单记录场景文件处理

**文件**: `utm_simulator/tools/run_kafka_scene.py:521-523`（`_build_redis_route` 函数）

当前 `< 2` 条记录返回 `None`（不写 Redis），改为：
- `< 1` → `None`
- `== 1` → 构造悬停航线并写入 Redis（允许单点遥测也能被下游识别）

---

## 修改文件汇总

| 文件 | Tasks | 改动数 |
|------|-------|--------|
| `web/static/js/map.js` | Task 1 | 2 行 |
| `utm_simulator/web_server.py` | Task 2.1~2.5 + Task 3.3 | ~5 处 |
| `utm_simulator/sim_manager.py` | Task 3.4 | ~2 处 |
| `utm_simulator/tools/run_kafka_scene.py` | Task 3.1, 3.2, 3.5 | ~3 处 |

## 验证方式

1. **Task 1**: 打开页面 → 浏览器 Network 面板确认瓦片请求发往 `webrd0*.is.autonavi.com` → 断开网络确认自动切换到 CartoDB
2. **Task 2**: 依次启动 5 种仿真模式 → 检查运行日志 5 个层面板是否都有数据流入
3. **Task 3**: 每种模式启动后 → 打开 `https://dkkgsit-test.testdolphin.com/atc/situation-monitoring` → 确认"监视目标数"显示正确的无人机数量
