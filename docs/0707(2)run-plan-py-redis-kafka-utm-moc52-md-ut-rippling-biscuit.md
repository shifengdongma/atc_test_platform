# UTM 模拟器第二轮优化计划

## Context

基于上一轮实施成果，本轮聚焦 5 个具体问题：运行时长始终为 0、日志不丰富且无法导出、Redis/Kafka 配置不可在前端修改、地图加载卡顿、以及后续未完成项（pydantic/pytest/Phase E）中高价值内容的收尾。

---

## 问题 1：运行时长始终显示 0:00:00

### 根因分析

**Plan 模式**：`web_server.py:179-191` 的 plan-mode 循环只更新了 `active_drones` 和 `kafka_msg_per_sec`，从未设置 `_runtime_state["uptime_sec"]`。

**Dynamic/Replay 模式**：`sim_manager.py` 的 `get_status()` 正确计算了 `uptime_sec`，但 `web_server.py:198` 的 `_push_status()` 中：
```python
_runtime_state["uptime_sec"] = _runtime_state.get("uptime_sec", 0)
```
只是读取已有值再写回，不是实际计算。幸运的是 dynamic/replay 模式在 `_sim_loop()` 中通过 `status = self._sim_mgr.get_status()` 拿到正确的 uptime_sec 并 `update()` 到了 `_runtime_state`，所以它们能工作——但依赖的是 `_sim_mgr` 的内部 `_start_time`，一旦 SimulationManager 不存在就无法计算。

### 修复方案

**1a. Plan 模式补上 uptime**：在 `web_server.py` 的 plan-mode 循环中加入：
```python
_runtime_state["uptime_sec"] = int(time.time() - self._start_time)
```
其中 `self._start_time` 在 `start()` 时已记录。plan 模式复用 `SimulationRunner._start_time`（初始化时设 `self._start_time = time.time()`）。

**1b. 修复 `_push_status()`**：改为直接用 `self._start_time` 计算而不是回显：
```python
if self._start_time:
    _runtime_state["uptime_sec"] = int(time.time() - self._start_time)
```

### 涉及文件
| 文件 | 行号 | 改动 |
|------|------|------|
| `web_server.py` | 179-191 | plan 模式循环增加 uptime_sec 更新 |
| `web_server.py` | 195-198 | `_push_status()` 改为基于 `_start_time` 实际计算 |

---

## 问题 2：日志增强 + 导出

### 根因分析

当前日志系统有两套且互不打通：
- **系统 A**（`web_server.py` `_add_log()`）：存到 `_runtime_state["logs"]` + WebSocket 实时推送
- **系统 B**（`sim_manager.py` `_add_log()`）：存到实例 `self._logs`，通过 `get_status()` 桥接

缺失的日志点（10 处）：
1. Redis HSET 写入确认/失败（sim_manager.py:318,329,355,484）
2. Kafka 每 tick 发送条数（sim_manager.py:442,472）
3. Kafka flush 超时告警（kafka_proc.py:93-100）
4. Replay 模式 tick 摘要（sim_manager.py `_tick_replay()`）
5. Plan 模式 tick 摘要（sim_manager.py `_tick_plan()`）
6. Trace 消费事件（sim_manager.py:504-548）
7. Dynamic 模式遥测批次大小
8. 连接健康度（需每 tick 检查）
9. Tick 超时告警（sim_manager.py:406 → 桥接到前端）
10. 错误 traceback（sim_manager.py:401 只传 message 不传 traceback）

前端目前无日志导出功能。

### 修复方案

**2a. 日志桥接统一**：给 `SimulationManager` 增加 `log_callback`，使 sim_manager.py 内部的 `_add_log()` 可回调 web_server.py 的 `_add_log()`，打通两套系统。

**2b. 补充 10 个缺失日志点**：每个 tick 输出摘要（模式、发送数、活跃数），关键操作（Redis write、Kafka send）输出成败确认，连接异常输出告警。

**2c. 前端导出按钮**：在日志面板标题旁增加"导出日志"按钮。点击后用 `Blob` + `URL.createObjectURL` 将 `logs` 数组（带时间戳）导出为 `.txt` 文件，在 `app.js` 新增一个纯前端功能（不依赖后端 API）：
```javascript
function exportLogs() {
    const text = logs.join('\n');
    const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `utm-sim-log-${new Date().toISOString().slice(0,19)}.txt`;
    a.click(); URL.revokeObjectURL(url);
}
```

### 涉及文件
| 文件 | 改动 |
|------|------|
| `sim_manager.py` | 增加 `log_callback`；10 处日志补充 |
| `web_server.py` | SimulationRunner 设置 `log_callback`；连接健康检查 |
| `web/index.html` | 日志面板增加"导出日志"按钮 |
| `web/static/js/app.js` | 新增 `exportLogs()` 函数 + 事件绑定 |

---

## 问题 3：前端 Redis/Kafka 配置编辑

### 根因分析

- `index.html:71-72`：Redis/Kafka 显示为 `<code>` 只读元素，不是 `<input>`
- `web_server.py:292-293`：`api_update_config()` 白名单不含 `redis_ip/redis_port/kafka_url`
- 无持久化机制：`_current_config` 仅在内存，重启丢失

### 修复方案

**3a. 前端改为可编辑**：将 `<code>` 替换为 `<input type="text">`，添加"💾 保存连接配置"按钮。

**3b. 后端 API 白名单扩展**：`api_update_config()` 增加 `redis_ip`、`redis_port`、`kafka_url` 三个 key。注意 `redis_password` 不暴露到前端。

**3c. 持久化**：新增 `POST /api/sim/config/save` 端点，将 `_current_config` 中的连接信息写入 `utm_simulator/config.json`。`config.py` 的 `load_config()` 优先读 `config.json`，回退到 `env.py`。

### 涉及文件
| 文件 | 改动 |
|------|------|
| `web/index.html:68-74` | `<code>` → `<input>` + 保存按钮 |
| `web/static/js/app.js` | fetchConfig 读写 input.value；新增保存事件 |
| `web_server.py:292-296` | API 白名单扩展 + 新增 POST `/api/sim/config/save` |
| `web_server.py:46-55` | _current_config 增加 redis_password（后端保留，不发给前端） |
| `config.py` | 增加 `save_config()` + `load_config()` 优先读 config.json |

---

## 问题 4：地图加载卡顿优化

### 根因分析（按严重程度排序）

| # | 原因 | 文件:行 | 严重度 |
|---|------|---------|--------|
| 1 | unpkg.com CDN 加载 Leaflet（国内 3-15 秒） | index.html:8,12 | **高** |
| 2 | 200 航线 × 3 层/航线 = 600 次逐次 DOM 插入触发重绘 | map.js:108,124,134 | **中** |
| 3 | 未使用 `L.featureGroup` 批量添加 | map.js:42-43 | **中** |
| 4 | `fitBounds()` 触发二次全量重渲染 | map.js:142-143 | **低-中** |
| 5 | 禁飞区 permanent tooltip 持续布局开销 | map.js:197-207 | **低** |

### 修复方案

**4a. Leaflet 本地化（关键）**：下载 Leaflet 1.9.4 的 `.css` 和 `.js` 到 `web/static/lib/leaflet/`，将 index.html 的 CDN 引用改为本地路径。这是单一最大改进。

**4b. 批量图层添加**：将 `forEach` 中逐个 `addTo()` 改为先收集所有 layer 到数组，最后一次性 `L.featureGroup(layers).addTo(map)`，减少重绘次数。

**4c. API limit 默认减小**：`/api/sim/plans` 默认 limit 从 200 降到 100，前端可手动刷新加载更多。

### 涉及文件
| 文件 | 改动 |
|------|------|
| `web/static/lib/leaflet/leaflet.js` | 新增：本地 Leaflet JS |
| `web/static/lib/leaflet/leaflet.css` | 新增：本地 Leaflet CSS |
| `web/index.html:8,12` | CDN → 本地路径 |
| `web/static/js/map.js:74-138` | 批量 `addTo()` → `L.featureGroup` |
| `web_server.py:340` | limit 默认值 200 → 100 |

---

## 问题 5：后续未完成项收尾

### 高价值项

| 项 | 价值 | 工作量 | 阻塞 |
|----|------|--------|------|
| pydantic + validators.py 启用 | 高 | 极小 | pip install pydantic |
| pytest 测试套件运行 | 高 | 小 | pip install pytest pydantic |
| cli.py 统一入口 | 中高 | 中 | 无 |

### 低价值项（延后）
- `tools/generate_docs.py` — 低价值，延后
- `tools/data_check.py` — 中价值，可用 validators.py 替代

### 修复方案

**5a. 依赖安装**：`pip install pydantic pytest pytest-cov`，更新 `requirements.txt`。

**5b. 运行测试套件**：`python -m pytest tests/ -v`，确认全部 23 个测试通过。

**5c. 创建 cli.py**：用 argparse 统一入口，子命令 `run`/`replay`/`plan`/`server`/`validate`，每项委托给现有模块。

### 涉及文件
| 文件 | 改动 |
|------|------|
| `requirements.txt` | 添加 pydantic、pytest、pytest-cov |
| `cli.py` | 新建 (~200 行)，统一 CLI 入口 |

---

## 实施顺序

```
1. 问题 5a (pip install pydantic pytest)  ← 解除阻塞，先行
2. 问题 1 (uptime 修复)                    ← 简单，1 个文件 2 处改动
3. 问题 2 (日志增强 + 导出)                ← 3 个文件
4. 问题 3 (配置编辑 + 持久化)             ← 4 个文件
5. 问题 4 (地图优化)                       ← 3 个文件
6. 问题 5b (测试验证)                      ← 收尾
7. 问题 5c (cli.py)                        ← 收尾
```

## 验证方式

1. **Uptime**：启动动态/plan/replay 任一模式，运行 5+ 秒，计时器应正常递增
2. **日志导出**：运行仿真 → 点击"导出日志" → 下载 .txt 文件含完整时间戳日志
3. **配置编辑**：前端修改 Redis IP → 保存 → 刷新页面 → 值保持（config.json 持久化）
4. **地图**：打开页面，地图 2 秒内加载完成（不再等 unpkg.com）
5. **测试**：`python -m pytest tests/ -v` 全部 PASS
6. **CLI**：`python cli.py validate --help` 输出正确
