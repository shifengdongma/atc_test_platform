# 修复: Dynamic 模式切换 Plan 模式 Redis 残留数据导致崩溃

## Context

dynamic 模式停止后切换 plan 模式时项目终止，Redis 中飞行计划数量不正确。

**根因**: dynamic 模式的 `stop()` 只删除当前活跃代理的 UID（`simulator.agents.keys()`），已完成飞行的无人机航线残留在 Redis 中。plan 模式启动时使用 `HSET` 追加而非覆盖，导致读取到脏数据。

## 修复方案

双重保险 — 停止时清理 + 启动时清理：

### 1. `utm_simulator/sim_manager.py` — `stop()` 方法

**位置约 L317-326**，将逐字段 HDEL 改为全量 DELETE：

```python
# 改前：只删当前活跃代理
for uid in list(self.simulator.agents.keys()):
    self.redis.client.hdel(REDIS_FLIGHT_PLAN_KEY, uid)

# 改后：全量清理
self.redis.client.delete(REDIS_FLIGHT_PLAN_KEY)
```

同时将 `self.redis.client.delete("BIZ_DATA:UAV_TELEMETRY")` 扩展为同时删除飞行计划 key。

### 2. `utm_simulator/sim_manager.py` — `_init_plan_mode()` 方法

**位置约 L509**，在 HSET 写入前先 DELETE 清空残留数据。

### 3. `utm_simulator/web_server.py` — `SimulationRunner._init_plan_mode()` 方法

**位置约 L300**，同样在 HSET 前先 DELETE。

## 验证

1. 启动 dynamic 模式，运行 30 秒后停止
2. `redis-cli HLEN BIZ_DATA:UAV_ROUTE` 确认 key 已被删除
3. 切换到 plan 模式，确认只加载 route 文件中的计划数
4. 重复 3 次切换，确认计划数始终正确
