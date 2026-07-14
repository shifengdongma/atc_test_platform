# 修复计划：动态仿真遥测进程外桥接（Redis → Kafka）

## Context

动态仿真模式下 `sim_manager.py:_tick_dynamic()` 将遥测写入 Redis `BIZ_DATA:UAV_TELEMETRY`，但未转发到 Kafka。ATC 系统需要 Kafka `uav_runtime_data` 中的遥测来更新"监视目标数"。

**硬约束**：Simulator (ctypes) 与 kafka-python (librdkafka) 在同一进程中会触发 C-level 堆污染崩溃。前两次尝试（lazy init / pre-init）均已证实无法在进程内安全共存。

**解决方向**：进程外桥接 — 独立子进程读取 Redis、写入 Kafka，与 Simulator 进程完全隔离。

## 方案

### 新增文件：`utm_simulator/tools/telemetry_bridge.py`

一个轻量级独立脚本，作为子进程运行：

```
启动参数: --redis-host --redis-port --redis-password --kafka-url [--kafka-mirror-url]
主循环:
  while True:
    raw = redis.get("BIZ_DATA:UAV_TELEMETRY")
    if raw:
      batch = json.loads(raw)            # JSON 数组
      kafka.send_bulk(batch, "uav_runtime_data")
      redis.delete("BIZ_DATA:UAV_TELEMETRY")
    sleep(0.8)
```

- 不 import SimulationManager / Simulator / simulation_core — **零 ctypes 依赖**
- 复用现有 `redis_client.py` 和 `kafka_proc.py`（与 PlanRunner 相同的调用方式）
- 使用 `sys.path` 插入项目根目录，与 tools/ 下其他脚本一致的路径处理

### 修改文件：`utm_simulator/web_server.py`

在 `SimulationRunner` 中增加桥接子进程管理，**仅新增代码，不改动现有逻辑**：

**1. `__init__`** — 新增属性（行 250 附近）：
```python
self._telemetry_bridge: Optional[subprocess.Popen] = None
```

**2. `start()`** — dynamic 模式启动后，启动桥接子进程（行 605-606 附近）：
```python
# dynamic 模式：启动遥测桥接子进程（Redis → Kafka）
if self.mode == "dynamic":
    self._start_telemetry_bridge()
```

**3. 新增方法 `_start_telemetry_bridge()`**：
```python
def _start_telemetry_bridge(self):
    """启动遥测桥接子进程：将 Redis BIZ_DATA:UAV_TELEMETRY 转发到 Kafka。"""
    import sys as _sys, subprocess as _sp
    bridge_script = os.path.join(_root, "tools", "telemetry_bridge.py")
    cfg = self._app_cfg
    cmd = [
        _sys.executable, bridge_script,
        "--redis-host", cfg.redis.host,
        "--redis-port", str(cfg.redis.port_int),
        "--redis-password", cfg.redis.password,
        "--kafka-url", cfg.kafka.bootstrap_servers,
    ]
    if cfg.kafka.bootstrap_servers_mirror:
        cmd += ["--kafka-mirror-url", cfg.kafka.bootstrap_servers_mirror]
    try:
        self._telemetry_bridge = _sp.Popen(cmd, close_fds=True)
        _add_log("遥测桥接子进程已启动")
    except Exception as e:
        print(f"[web_server] 遥测桥接启动失败: {e}")
        self._telemetry_bridge = None
```

**4. `_cleanup()`** — 终止桥接子进程（行 555-571 附近）：
```python
# 终止遥测桥接子进程
if getattr(self, "_telemetry_bridge", None) and self._telemetry_bridge.poll() is None:
    try:
        self._telemetry_bridge.terminate()
        self._telemetry_bridge.wait(timeout=3)
    except Exception:
        try:
            self._telemetry_bridge.kill()
        except Exception:
            pass
    self._telemetry_bridge = None
    _add_log("遥测桥接子进程已终止")
```

## 为什么安全

| 关注点 | 保证 |
|--------|------|
| C-level 崩溃 | 桥接在独立子进程运行，零 ctypes 依赖，完全隔离于 Simulator 的堆污染 |
| 不修改 sim_manager | `sim_manager.py` 零变更，`_tick_dynamic()` 逻辑不变 |
| 不修改仿真循环 | `_sim_loop()` dynamic 分支代码不变 |
| 不修改停止/重启 | `api_stop_sim()` 的 `subprocess.Popen` + `os._exit(0)` 逻辑不变。`os._exit(0)` 终止整个进程树，桥接子进程自动消亡 |
| 不影响其他模式 | 仅 dynamic 模式启动桥接，replay/plan/scene 不受影响 |
| 容错 | 桥接启动失败不影响仿真运行（仅记录日志）；桥接子进程崩溃后自动退出，不影响主进程 |
| 配置一致性 | 通过 CLI 参数传递当前配置，与 Web UI 环境管理器的连接参数保持一致 |

## 影响文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/tools/telemetry_bridge.py` | **新建** | 独立子进程脚本，Redis → Kafka 桥接 |
| `utm_simulator/web_server.py` | **修改** | SimulationRunner 增加桥接子进程生命周期管理 |

## 数据流

```
动态仿真 (主进程，有 ctypes):
  SimulationManager._tick_dynamic()
    → Redis SET BIZ_DATA:UAV_TELEMETRY    ← 不变

遥测桥接 (独立子进程，零 ctypes):
  telemetry_bridge.py
    → Redis GET BIZ_DATA:UAV_TELEMETRY
    → Kafka send_bulk(uav_runtime_data)   ← 新增
    → Redis DEL BIZ_DATA:UAV_TELEMETRY

ATC 后端:
  Kafka consume uav_runtime_data
    → "监视目标数" 更新 ✓
```

## 验证方式

1. 通过 Web UI 启动 dynamic 模式仿真
2. 检查 web_server 日志应出现 "遥测桥接子进程已启动"
3. 用 kafka 消费者验证 `uav_runtime_data` 有数据到达
4. 打开 `https://dkkgsit-test.testdolphin.com/atc/situation-monitoring`，"监视目标数" > 0
5. 停止仿真，确认 "遥测桥接子进程已终止" 日志，进程重启正常
