# 仿真执行与系统日志功能优化方案

## Context

低空空管自动化测试平台有 5 种仿真模式，但只有 "Redis计划插值 (plan)" 模式启动后，下游态势监控系统 `dkkgsit-test.testdolphin.com/atc/situation-monitoring` 能显示"监视目标数"等实时数据。其余 4 种模式 (dynamic/replay/replay_once/scene) 的数据无法被下游系统识别。

同时，仿真执行的"运行日志"模块（5层可折叠面板）和"系统日志"页面中，轨迹预测、冲突告警等日志类型在部分模式下读取不到数据。

根本原因涉及：飞行计划时间平移缺失、operatingStatus 字段不兼容、Redis 航线未周期性刷新、Kafka URL 配置传递不一致、以及各模式下 SocketIO 事件桥接缺失。

## 问题 1：非 plan 模式下游系统无法显示监视目标数

### Fix 1.1: `_tick_dynamic()` 补充无人机航线时间平移 ⭐ 核心修复

**文件**: `utm_simulator/sim_manager.py` 第 594-600 行

**根因**: dynamic 模式中，当无人机降落后补充新无人机时，`_plan_to_route_json(plan)` 生成的航线直接写入 Redis，**未调用 `_shift_plan_times()`**。Simulator ctypes 引擎生成的 `plan.start_time` 与当前时间无确定关系，下游 ATC 系统将航线视为未激活或已过期，不启动追踪。

`_init_dynamic_mode()` 中初始批次（第 428-430 行）有正确的时间平移，但 `_tick_dynamic()` 中的替换批次遗漏了此步骤。

**修改**: 在 `redis.hset` 之前插入时间平移：
```python
route_json = self._plan_to_route_json(plan)
obj = json.loads(route_json)
self._shift_plan_times(obj)
route_json = json.dumps(obj, ensure_ascii=False)
self.redis.hset(REDIS_FLIGHT_PLAN_KEY, uid, route_json)
```

### Fix 1.2: 强制 `operatingStatus=2` — scene 模式和 replay 模式

**根因**: 下游 ATC 系统依赖 `operatingStatus=2`（飞行中）来识别活跃监视目标。scene 模式 (`run_kafka_scene.py`) 和 replay 模式 (`sim_manager.py`) 仅在字段为 `None` 时才设为 2，若 JSON 文件中已有 `operatingStatus=0`（未起飞）或 `5`（已降落），下游不会将其计入监视目标数。

**文件 1**: `utm_simulator/tools/run_kafka_scene.py` `_emit_once()` 约第 360 行
- 改为无条件 `record['operatingStatus'] = 2`

**文件 2**: `utm_simulator/sim_manager.py` `_init_replay_mode()` 第 499-502 行
- 改为无条件 `msg["operatingStatus"] = 2`

### Fix 1.3: scene 模式添加周期性 Redis 航线刷新

**文件**: `utm_simulator/tools/run_kafka_scene.py` `_emit_loop()` 

**根因**: `SceneEmitter.start()` 仅在启动时写入一次 Redis 航线，之后不再刷新。下游 ATC 系统可能因航线时间戳过期而取消追踪。replay 模式已有类似的 30 秒刷新机制，scene 模式缺失。

**修改**: 在 `_emit_loop()` 中添加 30 秒定时器，周期性调用 `_write_redis_route_batch()` 刷新航线时间戳。

### Fix 1.4: replay_once 模式支持可配置 Kafka URL

**文件 1**: `utm_simulator/tools/run_kafka.py` `DataSource.__init__()`
- 添加 `kafka_url` 可选参数，默认回退到 `env.kafka_url`

**文件 2**: `utm_simulator/web_server.py` 第 538 行
- `_rk.DataSource(kafka_url=self.config.get("kafka_url"))`

**根因**: DataSource 硬编码使用 `env.kafka_url`，当用户通过 Web UI 切换 Kafka 地址时，replay_once 仍向旧地址发送数据。

### Fix 1.5: dynamic 模式遥测桥接诊断日志增强

**文件**: `utm_simulator/tools/telemetry_bridge.py` 和 `utm_simulator/web_server.py`

**根因**: telemetry_bridge 子进程是 dynamic 模式唯一的数据输出通道。如果桥接静默失败，下游完全没有遥测数据。需要增强启动验证和运行状态日志。

**修改**: 
- telemetry_bridge.py: 增加启动时 Redis key 存在性检查和空转超时告警
- web_server.py: 启动 5 秒后验证桥接进程仍在运行且 Redis 遥测 key 不为空

## 问题 2：运行日志和系统日志缺失部分日志类型

当前各模式下 SocketIO 事件桥接状态：

| 日志层 | 事件 | dynamic | replay | replay_once | scene | plan |
|--------|------|---------|--------|-------------|-------|------|
| 1 遥测 | telemetry_data | ✅ | ✅ | ✅ | ✅ | ❌ |
| 2 轨迹预测 | trace_data | ❌(ctypes) | ✅ | ✅ | ❌ | ❌ |
| 3 冲突告警 | collision_alarm | ❌(ctypes) | ✅ | ✅ | ✅ | ✅ |
| 4 WS前端 | ws_captured | ✅ | ✅ | ✅ | ✅ | ✅ |
| 5 系统日志 | log_entry | ✅ | ✅ | ✅ | ✅ | ✅ |

### Fix 2.1: plan 模式桥接轨迹预测数据到前端 Layer 2

**文件**: `utm_simulator/tools/run_plan.py` 和 `utm_simulator/web_server.py`

**根因**: PlanRunner 有 `_consume_uav_runtime_trace()` 线程消费 trace 并写入 LogStreamer，但**没有**通过 SocketIO 桥接到前端运行日志面板 Layer 2。其他模式通过 `trace_callback` 实现此功能，PlanRunner 缺少此回调机制。

**修改**: 
- PlanRunner 添加 `trace_callback` 参数，在 `_consume_uav_runtime_trace()` 中调用
- web_server.py 创建 PlanRunner 时传入 `trace_callback=lambda d: socketio.emit("trace_data", d)`

### Fix 2.2: scene 模式启用 trace 消费并桥接到前端 Layer 2

**文件**: `utm_simulator/web_server.py` scene 分支（第 593-633 行）

**根因**: SceneEmitter 创建时 `consume_trace` 默认为 `False`，从不消费 `uav_runtime_trace`。即使开启也没有桥接逻辑。

**修改**: 
- 设置 `consume_trace=True`
- 在 scene 循环中添加 trace 数据 SocketIO 桥接（类似 `_push_replay_once_trace`）

### Fix 2.3: dynamic 模式明确说明 trace/collision 不可用原因

**文件**: `utm_simulator/web_server.py` dynamic 分支

**根因**: dynamic 模式因 ctypes 兼容性问题跳过了 Kafka trace 和 collision 消费者，但前端 Layer 2/3 只能看到"等待数据中…"，用户不知道原因。

**修改**: push 明确的日志消息说明限制原因，建议使用 replay 或 plan 模式查看完整日志。

### Fix 2.4: plan 模式桥接遥测数据到前端 Layer 1

**文件**: `utm_simulator/tools/run_plan.py` 和 `utm_simulator/web_server.py`

**根因**: PlanRunner 直接向 Kafka 发送遥测数据，但**没有**通过 `telemetry_data` SocketIO 事件桥接到前端。其他模式通过 `telemetry_callback` 实现。

**修改**:
- PlanRunner 添加 `telemetry_callback` 参数，在 `tick_send()` 发送 batch 后调用
- web_server.py 传入 `telemetry_callback=lambda d: socketio.emit("telemetry_data", d)`

### Fix 2.5: LogStreamer 缓冲区从 1000 扩大到 3000

**文件**: `database/log_streamer.py` 第 94 行
- `self._max_buffer = 3000`（内存影响约 1.5MB）

## 涉及文件汇总

| 文件 | 修改内容 |
|------|----------|
| `utm_simulator/sim_manager.py` | Fix 1.1: `_tick_dynamic` 时间平移; Fix 1.2: operatingStatus 强制 |
| `utm_simulator/tools/run_kafka_scene.py` | Fix 1.2: operatingStatus 强制; Fix 1.3: 周期性 Redis 刷新 |
| `utm_simulator/tools/run_kafka.py` | Fix 1.4: DataSource 可选 kafka_url 参数 |
| `utm_simulator/web_server.py` | Fix 1.4: 传递 kafka_url; Fix 1.5: 桥接诊断; Fix 2.2: scene trace; Fix 2.3: dynamic 说明; Fix 2.1/2.4: plan 回调 |
| `utm_simulator/tools/telemetry_bridge.py` | Fix 1.5: 诊断日志增强 |
| `utm_simulator/tools/run_plan.py` | Fix 2.1: trace_callback; Fix 2.4: telemetry_callback |
| `database/log_streamer.py` | Fix 2.5: 缓冲区扩大到 3000 |
| `docs/utm-simulator-optimization-work-log.md` | 工作日志更新 |
| `docs/工作总结.md` | 工作总结更新 |

## 实施顺序

1. **问题 1 修复**（独立，可并行）: Fix 1.1 → 1.2 → 1.3 → 1.4 → 1.5
2. **问题 2 修复**（依赖问题 1 — 下游 ATC 需要先识别 UAV 才会产生 trace/collision 数据）: Fix 2.1 → 2.2 → 2.3 → 2.4 → 2.5
3. **文档更新**: 最后执行

## 验证方式

1. **Fix 1.1**: 启动 dynamic 模式，每 5 秒检查 Redis `BIZ_DATA:UAV_ROUTE` 中替换无人机的 `planTakeoffTime` 接近 `time.time()`
2. **Fix 1.2**: 使用含 `operatingStatus=0` 的场景文件启动 scene 模式，消费 Kafka 确认 `operatingStatus` 始终为 2
3. **Fix 1.3**: 启动 scene 模式，每 10 秒读取 Redis 航线，确认 `planTakeoffTime` 周期性刷新
4. **Fix 1.4**: Web UI 切换 Kafka 地址后启动 replay_once，确认数据发送到正确 broker
5. **Fix 2.1-2.4**: 各模式启动后打开 `/run` 页面，展开对应日志层，确认数据实时更新
6. **Fix 2.5**: 长时间仿真后导出日志，确认可检索超过 1000 条

## 风险评估

- **Fix 1.1** 的 `json.loads/dumps` 循环在高架数（5000+）时可能增加 tick 延迟，但已与 `_init_dynamic_mode` 模式一致
- **Fix 1.3** 的 `_write_redis_route_batch` 在大场景文件时可能耗时较长，但仅每 30 秒执行一次
- **Fix 2.1/2.4** 的回调在 PlanRunner 后台线程中执行，SocketIO emit 可能阻塞，现有 `except Exception: pass` 保护
