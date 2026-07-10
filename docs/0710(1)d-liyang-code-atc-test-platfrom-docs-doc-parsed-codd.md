# 修复计划：Redis插值模式 + async_mode + MySQL 三个问题

## Context

低空空管自动化测试平台出现三个问题：
1. **async_mode="eventlet"** 导致本地启动直接崩溃
2. **Redis插值模式(plan)** UI强制要求选JSON文件，但该模式应直接读Redis
3. **MySQL持续写入异常** `(0, '')` 刷屏，影响docker日志可读性

用户补充：启动plan模式后，下游系统飞行任务进入管制状态但监控目标数查不到该任务 — 此问题需进一步排查数据格式。

---

## 问题1：`ValueError: Invalid async_mode specified` 🔴 CRITICAL

**根因**：`utm_simulator/web_server.py:77` 写死 `async_mode="eventlet"`，但本地 `utm` conda环境未安装 eventlet。`start_web.ps1` 依赖检查列表不含 eventlet。

**修复方案**：移除硬编码的 `async_mode="eventlet"`，让python-socketio自动检测可用异步模式。

### 修改文件

#### A. `utm_simulator/web_server.py` 第77行
```python
# 修改前：
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# 修改后：
socketio = SocketIO(app, cors_allowed_origins="*")
```
- 自动检测优先级：eventlet > gevent > threading
- 本地的 `simple-websocket` 已安装（在 `start_web.ps1` 列表中），可正常工作
- Docker中 eventlet 已通过 requirements.txt 安装，也会正常自动检测到

#### B. `start_web.ps1` 补充 eventlet 到依赖列表（防御性）
- 在第97-107行的包列表中增加 `eventlet`，确保本地环境也安装

---

## 问题2：Redis插值模式(plan)不应要求选择JSON文件 🟡

**根因**：后端 `_init_plan_mode()` 已正确处理文件缺失情况（回退到读Redis），但前端UI（`run.html` + `run.js`）强制显示文件选择器且始终发送 `plan_route_file` 参数。

### 修改文件

#### A. `web/pages/run.html` 第91-96行
将 plan-params 中的文件选择器改为可选，增加说明文字：
```html
<div class="form-group">
  <label for="plan-route-file">航线数据文件 (可选)</label>
  <select id="plan-route-file" ...></select>
  <div class="hint">留空则直接使用 Redis 中已有航线数据，无需本地文件</div>
</div>
```

#### B. `web/static/js/run.js` 第353行
不强制发送默认文件名：
```javascript
// 修改前：
body.plan_route_file = (document.getElementById('plan-route-file')||{}).value || 'redis_route.json';

// 修改后：
var planFile = (document.getElementById('plan-route-file')||{}).value;
if (planFile) body.plan_route_file = planFile;
// 不设置时后端跳过文件加载，直接读Redis
```

#### C. `web/static/js/run.js` `refreshPlanFileList()` 第263行
在文件列表中添加"不使用文件"选项：
```javascript
sel.innerHTML = '<option value="">— 直接使用 Redis 数据（不加载文件） —</option>' + files.map(...)
```

#### D. `utm_simulator/web_server.py` `_init_plan_mode()` 第224-289行
当 `plan_route_file` 为空时跳过文件加载：
```python
route_file = self.config.get("plan_route_file", "").strip()
if route_file:
    # 现有文件加载逻辑...
else:
    _add_log("plan 模式: 未指定航线文件，直接从 Redis 读取已有数据")
```

---

## 问题3：MySQL写入异常 `(0, '')` 刷屏 🟡

**根因**：`database/log_streamer.py` 的 `push()` 方法中，MySQL insert 失败后仅打印错误，不设置 `_mysql_enabled = False`，导致每条日志都重试一次MySQL写入。对比 `mysql_db_manager.py` 有60秒冷却期，`log_streamer.py` 缺少此机制。

### 修改文件

#### A. `database/log_streamer.py` — 两处改动

**改动1**：`_get_mysql_client()` 方法（第161行附近）添加冷却期机制：
```python
# 类初始化中增加冷却期字段
self._mysql_fail_count = 0
self._mysql_last_fail_time = 0.0
_MYSQL_COOLDOWN_SEC = 60.0

# _get_mysql_client() 中，连接失败时增加冷却期检查
```

**改动2**：`push()` 方法第338行，写入异常时禁用后续MySQL写入：
```python
except Exception as e:
    print(f"[LogStreamer] MySQL 写入异常: {e}")
    self._mysql_fail_count += 1
    self._mysql_last_fail_time = time.time()
    if self._mysql_fail_count >= 5:
        print("[LogStreamer] MySQL 连续写入失败超过5次，禁用持久化")
        self._mysql_enabled = False
```

#### B. `atc_api_autotest/api_tools/mysqldbclient.py` `insert()` 方法
- `(0, '')` 异常来自 pymysql 底层，`insert()` 已捕获但 `print` 不够详细
- 改进：在 except 块中增加异常类型判断，区分连接断开 vs 数据格式错误

---

## 问题4：监控目标数不显示（待排查）🔍

启动plan模式后，下游系统飞行任务进入管制状态，但监控目标数查不到。可能原因：
- 遥测消息中的 `operatingStatus` 字段值不对
- 监控目标发现依赖于特定字段组合
- 需排查 `tools/run_plan.py` 中 `_make_kafka_msg()` 的输出格式与下游期望的差异

**不在本次修改范围**，需单独排查。

---

## 修改顺序

1. **问题1**（本地启动崩溃）→ 最高优先级，先修
2. **问题2**（UI文件选择器）→ 中等优先级
3. **问题3**（MySQL日志刷屏）→ 中等优先级
4. **问题4**（监控目标）→ 后续排查

## 验证方式

1. **问题1**：本地执行 `conda run -n utm python utm_simulator/web_server.py`，确认不再抛 `ValueError`
2. **问题2**：浏览器打开web界面，选plan模式，不选文件直接启动，确认仿真正常运行
3. **问题3**：观察docker日志，确认MySQL异常出现5次后自动静默，不再刷屏
