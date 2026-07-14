# 修复计划：停止漏洞 + 监视目标数 + 日志缺失

## Context

三个线上问题需要修复：

1. **Ctrl+C / 关闭仿真后数据注入残留**：`web_server.py` 的 SIGINT handler 只清理 telemetry_bridge 子进程，不调用 `_sim_runner.stop()`；`os._exit(0)` 跳过 atexit；replay_once/scene 模式资源无法被 cleanup 访问
2. **非 plan 模式下游"监视目标数"始终为 0**：ATC 系统通过 Redis `BIZ_DATA:UAV_ROUTE` 写入事件激活追踪；plan 模式有 PlanRunner 持续回写触发，其他模式仅写入一次，缺少激活机制
3. **日志面板缺失 trace / collision_alarm / WebSocket 数据**：`report_kafka_trace()` 零调用；collision_alarm 字段名与算法文档不匹配；dynamic 模式跳过所有 Kafka 消费；前端缺少 `kafka_collision_alarm` 和 `ws_captured_data` 复选框

---

## 问题 1：停止漏洞修复

### 1.1 修复 SIGINT/SIGTERM handler — 确保完整清理

**文件**: `utm_simulator/web_server.py:144-148`

当前 handler 只调 `_kill_telemetry_bridge()` 然后 `sys.exit(0)`，不调用 `_sim_runner.stop()`。

```python
# 修改 _on_exit_signal:
def _on_exit_signal(signum, frame):
    print(f"\n[web_server] 收到信号 {signum}，清理资源...", flush=True)
    # 1. 先停止仿真运行器（停止所有线程 + 清理 Redis/Kafka + 终止 bridge）
    if _sim_runner is not None:
        try:
            _sim_runner.stop()
        except Exception:
            pass
    # 2. 兜底清理 bridge（_sim_runner 可能为 None）
    _kill_telemetry_bridge()
    sys.exit(0)
```

### 1.2 为 replay_once/scene 模式存储资源引用

**文件**: `utm_simulator/web_server.py:SimulationRunner`

`_sim_loop()` 中 replay_once 和 scene 模式的 DataSource/SceneEmitter 是局部变量，`_cleanup()` 无法访问。增加实例属性。

```python
# __init__ 中新增:
self._ds = None        # replay_once 模式 DataSource
self._emitter = None   # scene 模式 SceneEmitter

# _sim_loop() replay_once 分支:
self._ds = ds = _rk.DataSource()
...
# 数据耗尽或退出后:
if self._ds:
    try: self._ds.kafka_producer.close()
    except: pass

# _sim_loop() scene 分支:
self._emitter = emitter = SceneEmitter(...)
...
# 退出后:
if self._emitter:
    try: self._emitter.stop()
    except: pass

# _cleanup() 中新增:
if self._ds:
    try: self._ds.kafka_producer.close()
    except: pass
    self._ds = None
if self._emitter:
    try: self._emitter.stop()
    except: pass
    self._emitter = None
```

### 1.3 缩短 telemetry_bridge 父进程检测间隔

**文件**: `utm_simulator/tools/telemetry_bridge.py:64`

```python
# WaitForSingleObject 超时 3000 → 1000ms
ret = _kernel32.WaitForSingleObject(handle, 1000)
```

### 1.4 碰撞告警消费者增加退出条件

**文件**: `utm_simulator/web_server.py:223`

```python
# 当前: while True → 改为:
while _collision_consumer is not None:
```

---

## 问题 2：非 plan 模式"监视目标数"修复

### 根因

ATC 系统依赖 **Redis `BIZ_DATA:UAV_ROUTE` 写入事件**来激活对某架无人机的追踪。PlanRunner 的 `_shift_and_write_plan()` 会持续将计划起降时间平移到当前时刻并回写 Redis，从而反复触发 ATC 激活。其他模式仅在初始化时写一次，无后续触发。

### 2.1 dynamic 模式：增加 Kafka 直接发送 + 周期性航线刷新

**文件**: `utm_simulator/sim_manager.py:_tick_dynamic()`

在现有 Redis 写入基础上，增加直接 Kafka 发送：

```python
# 当前 line 590-606: 只写 Redis
# 新增：同时发 Kafka（telemetry_bridge 子进程也转发，双路径避免单点故障）
if kafka_msgs:
    # 写 Redis（现有逻辑，telemetry_bridge 子进程转发）
    payload = json.dumps(kafka_msgs, ensure_ascii=False)
    self.redis.client.set(telemetry_key, payload)
    
    # 新增：直接发 Kafka（如果 producer 可用）
    # 在 web_server 中 dynamic 模式通过独立子进程做转发，
    # 这里增加直接发送作为 backup 路径
```

**文件**: `utm_simulator/sim_manager.py:_init_dynamic_mode()`

增加航线时间平移（与 replay/plan 模式一致）：

```python
# 在 _init_dynamic_mode 中，写入 Redis 前调用 _shift_plan_times
route_json = self._plan_to_route_json(plan)
# 解析 → 平移时间 → 重新序列化
obj = json.loads(route_json)
self._shift_plan_times(obj)
route_json = json.dumps(obj, ensure_ascii=False)
self.redis.hset(REDIS_FLIGHT_PLAN_KEY, uid, route_json)
```

### 2.2 replay 模式：周期性 Redis 航线时间刷新

**文件**: `utm_simulator/sim_manager.py:_tick_replay()`

每 30 秒刷新一次所有活跃 UAV 的 Redis 航线时间：

```python
# _tick_replay 中新增（在现有发送逻辑后）:
if self._tick_count % 30 == 0:
    for uid in self._replay_index:
        self._refresh_single_redis_route(uid)
    if self._tick_count % 60 == 0:
        self._add_log(f"Replay: 已刷新 {len(self._replay_index)} 条航线时间")
```

### 2.3 scene 模式：确保 Redis 飞行计划写入

**文件**: `utm_simulator/web_server.py:SimulationRunner._sim_loop()` scene 分支

SceneEmitter 启动后，确保从场景数据中提取飞行计划写入 Redis：

```python
# scene 分支 line 510-553，emitter.start() 之后:
# 如果 emitter 有 _write_redis_route_batch 方法，调用它
if hasattr(emitter, '_write_redis_route_batch'):
    emitter._write_redis_route_batch()
# 检查并记录
try:
    route_count = len(RedisClient(...).hgetall(REDIS_FLIGHT_PLAN_KEY) or {})
    _add_log(f"scene 模式: Redis 中当前 {route_count} 条飞行计划")
except Exception:
    pass
```

---

## 问题 3：日志缺失 trace / collision_alarm / WebSocket 数据

### 3.1 为 kafka_trace 添加 LogStreamer 推送

**文件**: `utm_simulator/sim_manager.py:_consume_trace()`

```python
# 在 line 718 附近，过滤并打印后，增加:
# 推送 kafka_trace 日志
try:
    from database.log_streamer import get_streamer
    get_streamer().report_kafka_trace(len(filtered))
except Exception:
    pass
```

**文件**: `utm_simulator/tools/run_plan.py:_consume_uav_runtime_trace()`

```python
# 在 line 438-441 打印后，增加:
try:
    from database.log_streamer import get_streamer
    get_streamer().report_kafka_trace(len(filtered))
except Exception:
    pass
```

### 3.2 修复 kafka_collision_alarm 字段名提取

**文件**: `utm_simulator/web_server.py:_start_collision_alarm_consumer():line 226-233`

当前代码使用不存在的字段名 `involvedUavs` / `alertUavList`。依据算法文档 `_source/算法对接2026.md:492-558`，告警消息是数组，每个元素以告警类型为 key：

```python
# 修复后的提取逻辑:
for msg in messages:
    if not isinstance(msg, dict):
        continue
    
    # 提取告警类型（collisionShortAlert / collisionShortWarn / lowHeightAlert 等）
    alert_types = []
    total_uavs = 0
    for key in msg:
        alert_obj = msg[key]
        if isinstance(alert_obj, dict):
            alert_types.append(key)
            uav_list = alert_obj.get("uavList", [])
            total_uavs += len(uav_list)
    
    if alert_types:
        alert_type_str = ", ".join(alert_types)
        _get_streamer().push(
            "kafka_collision_alarm",
            f"冲突告警: {alert_type_str} 涉及 {total_uavs} 架无人机",
            detail={"alert_types": alert_types, "uav_count": total_uavs, "raw": msg}
        )
```

### 3.3 dynamic 模式也启动冲突告警消费者

**文件**: `utm_simulator/web_server.py:SimulationRunner.start():line 648-654`

移除 dynamic 模式的排除。告警消费者只做 Kafka 读取 + LogStreamer 推送，不涉及 Simulator ctypes 内存，不会导致 C-level 崩溃：

```python
# 删除 dynamic 模式的排除条件:
# 所有模式都启动冲突告警消费者
try:
    _start_collision_alarm_consumer()
except Exception as e:
    print(f"[web_server] 冲突告警消费者启动失败: {e}")
```

### 3.4 前端增加 kafka_collision_alarm 和 ws_captured_data 复选框

**文件**: `web/pages/logs.html:37-42`

在系统日志类型区域增加两个复选框：

```html
<label class="plan-route-item" style="font-size:11px;"><input type="checkbox" class="log-type-cb" value="kafka_collision_alarm" checked> <span class="plan-route-uid">Kafka 冲突告警</span></label>
<label class="plan-route-item" style="font-size:11px;"><input type="checkbox" class="log-type-cb" value="ws_captured_data" checked> <span class="plan-route-uid">WebSocket 前端数据</span></label>
```

---

## 影响文件汇总

| 文件 | 操作 | 修改内容 |
|------|------|---------|
| `utm_simulator/web_server.py` | 修改 | 1) SIGINT handler 增加 `_sim_runner.stop()` 调用；2) `_sim_loop` scene/replay_once 资源引用；3) `_cleanup()` 增加 ds/emitter 清理；4) 修复 collision_alarm 字段名；5) 移除 dynamic 告警消费排除；6) 碰撞消费者退出条件 |
| `utm_simulator/sim_manager.py` | 修改 | 1) `_init_dynamic_mode()` 增加航线时间平移；2) `_tick_replay()` 增加周期性 Redis 刷新；3) `_consume_trace()` 增加 LogStreamer 推送 |
| `utm_simulator/tools/telemetry_bridge.py` | 修改 | 父进程检测间隔 3000→1000ms |
| `utm_simulator/tools/run_plan.py` | 修改 | `_consume_uav_runtime_trace()` 增加 LogStreamer 推送 |
| `web/pages/logs.html` | 修改 | 增加 `kafka_collision_alarm` 和 `ws_captured_data` 复选框 |

---

## 验证方式

### 问题 1 验证
1. Web UI 启动 dynamic 模式 → 确认 telemetry_bridge 子进程存在（`tasklist /FI "IMAGENAME eq python.exe"` 含 bridge）
2. Web UI 点击"停止" → 确认 `stop_all_injection.py --check` 输出全 ✅
3. Web UI 启动 → 终端 Ctrl+C → 确认无残留 bridge 进程和 Redis key
4. 多次启停 → 确认每次停止后 state 干净

### 问题 2 验证
1. **dynamic 模式**：启动 → Kafka `uav_runtime_data` 有数据 → Dashboard 监视目标数 > 0
2. **replay 模式**：启动 → Dashboard 监视目标数 > 0（等待最多 30s 航线刷新）
3. **scene 模式**：上传含 UID 的场景文件 → 启动 → Redis `BIZ_DATA:UAV_ROUTE` 有该 UID → Dashboard 监视目标数 > 0

### 问题 3 验证
1. 启动 plan 模式 → `/logs` 页面勾选"Kafka 轨迹预测" → 等待 trace 日志出现
2. 启动含碰撞告警的场景 → `/logs` 页面勾选"Kafka 冲突告警" → 应显示告警类型和涉及 UAV 数
3. `/logs` 页面"全部日志" Tab → 应有 `ws_captured_data` 和 `kafka_collision_alarm` 复选框
