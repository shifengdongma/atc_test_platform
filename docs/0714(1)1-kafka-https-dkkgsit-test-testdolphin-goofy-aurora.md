# 修复计划：动态仿真监视目标数 + 碰撞告警错误提示

## Context

两个问题：
1. **动态仿真模式**启动后，Kafka 遥测数据正常生成但下游 ATC Dashboard "监视目标数" 始终为 0
2. **碰撞告警**两航线无交汇点时，后端日志正确显示"未找到交汇点"，但前端显示泛化的"脚本异常退出"

---

## 问题 1：动态仿真模式 "监视目标数" 为 0

### 根因分析

`utm_simulator/sim_manager.py` 的 `_tick_dynamic()` 方法（第 561-606 行）在 dynamic 模式下将遥测数据写入 Redis `BIZ_DATA:UAV_TELEMETRY`，但 **从未转发到 Kafka `uav_runtime_data`**。

注释写明"由 tools/run_plan.py 的 PlanRunner 统一转发到 Kafka"，但 PlanRunner 仅在 `plan` 模式下启动，**dynamic 模式下没有启动**。

ATC 系统依赖 Kafka `uav_runtime_data` 中的遥测数据来识别活跃无人机并更新"监视目标数"。没有 Kafka 数据 → ATC 看不到无人机 → Dashboard 显示 0。

### 数据流对比

```
旧 main.py (CLI 模式):  Simulator.step() → kafka_producer.send_bulk() → Kafka ✓
sim_manager.py (Web UI): Simulator.step() → Redis BIZ_DATA:UAV_TELEMETRY → (无人转发) → Kafka ✗
```

### 修复方案

**在 `sim_manager.py:_tick_dynamic()` 中增加直接发送 Kafka 的逻辑**（第 590 行附近）：

```python
# 现有：写入 Redis
kafka_msgs = self._telemetry_list_to_kafka(telemetry_list)
if kafka_msgs:
    # 写入 Redis（保留，用于 PlanRunner 兼容）
    self.redis.client.set("BIZ_DATA:UAV_TELEMETRY", payload)
    
    # 新增：同步发送到 Kafka（供 ATC 系统消费，使"监视目标数"生效）
    if self._ensure_kafka_producer():
        try:
            self.kafka_producer.send_bulk(kafka_msgs, KAFKA_UAV_DATA_TOPIC)
        except Exception as e:
            if self._tick_count % 30 == 0:
                self._add_log(f"Kafka 发送异常: {e}")
```

**为什么安全**：`SimulationManager._ensure_kafka_producer()` 已内置惰性初始化 + 容错降级（失败时返回 False，仿真继续运行）。`send_bulk` + `flush` 在 `simulator.step()` 返回后同步调用，与 ctypes 无并发冲突。

### 影响文件

| 文件 | 操作 |
|------|------|
| `utm_simulator/sim_manager.py` | 在 `_tick_dynamic()` 中添加 Kafka 直接发送 |

---

## 问题 2：碰撞告警错误提示不准确

### 根因分析

`utm_simulator/tools/create_data_scenes.py` 的 `run_collision()` 函数中有 4 处错误退出：

```python
print("[错误] 未找到交汇点")   # ← 只打印到控制台
sys.exit(1)                   # ← 被 _safe_run 捕获，返回 "脚本异常退出(code=1)"
```

`utm_simulator/web_data_gen_bridge.py` 的 `_safe_run()` 捕获 `SystemExit` 时丢失了具体错误信息：

```python
except SystemExit as e:
    if e.code != 0 and e.code is not None:
        return {"success": False, "error": f"脚本异常退出(code={e.code})"}
```

### 修复方案

**方案**：利用 `sys.exit("message")` 传递错误信息（Python 支持，string 成为 `e.code`），然后 `_safe_run` 识别 string 类型的 code。

**Step 1** — `create_data_scenes.py:run_collision()` 中 4 处改为：

```python
# Before:
print("[错误] 未找到交汇点")
sys.exit(1)

# After:
sys.exit("未找到交汇点")
```

涉及的 4 处（行号 1442/1450/1458/1465）：
- `sys.exit("碰撞预警模式需要至少2条航线")`
- `sys.exit(f"无法获取航线 '{route_name}'")`
- `sys.exit(f"航线 '{route_name}' 航路点不足")`
- `sys.exit("未找到交汇点")`

**Step 2** — `web_data_gen_bridge.py:_safe_run()` 第 46-48 行改为：

```python
except SystemExit as e:
    if e.code != 0 and e.code is not None:
        if isinstance(e.code, str):
            return {"success": False, "error": e.code}
        return {"success": False, "error": f"脚本异常退出(code={e.code})"}
    return {"success": True, "result": None}
```

### 影响文件

| 文件 | 操作 |
|------|------|
| `utm_simulator/tools/create_data_scenes.py` | `run_collision()` 中 4 处 `sys.exit(1)` → `sys.exit("message")` |
| `utm_simulator/web_data_gen_bridge.py` | `_safe_run()` 中处理 string 类型的 SystemExit code |

---

## 验证方式

### 问题 1 验证
1. 通过 Web UI 启动 dynamic 模式仿真（目标 1-2 架无人机）
2. 用 kafka 消费者验证 `uav_runtime_data` topic 有数据：`kafka-console-consumer --topic uav_runtime_data --max-messages 5`
3. 打开 `https://dkkgsit-test.testdolphin.com/atc/situation-monitoring`，确认"监视目标数" > 0
4. 检查模拟器日志，确认无 Kafka 发送异常

### 问题 2 验证
1. 在 Web UI "数据生成" → "碰撞告警" 中选择两条无交汇的航线（如"三河区航路"和"潮白河段航路"）
2. 点击"生成碰撞预警场景"
3. 确认前端显示红色错误消息 **"失败: 未找到交汇点"** 而非 "失败: 脚本异常退出(code=1)"
4. 确认后端日志仍正常输出 `[错误] 未找到交汇点`
