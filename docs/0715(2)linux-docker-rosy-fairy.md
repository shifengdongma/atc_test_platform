# 多用户并发改造方案

## Context

ATC/UTM 自动化测试平台（UTM 模拟器）部署在 Linux Docker 容器中，当前为**单用户工具式 Web 应用**——所有进入系统的用户共享：
- 同一个仿真运行状态（只有一个 `_sim_runner`）
- 同一个定时任务列表（全局 `TaskScheduler` 单例）
- 同一份日志缓冲（全局 `LogStreamer` 单例）
- 同一个配置面板（全局 `_current_config` 字典）

**核心症状**：用户 A 启动仿真后，用户 B 看到"仿真运行中"且无法启动自己的仿真。多人共用定时任务列表，互相覆盖对方创建的任务。

改造后目标：多个用户**同时独立**使用系统，各自管理自己的仿真、任务、数据和日志。

---

## 一、根本原因分析（总计 10 类问题）

### 1. 无用户识别机制
前端无登录/Token/Cookie/SessionStorage，后端无认证中间件，60+ API 路由无任何访问控制。

### 2. 全局单例仿真运行器 `web_server.py:124`
```python
_sim_runner: Optional["SimulationRunner"] = None  # 全局唯一
```
`api_start_sim`（line 864）检查 `_runtime_state["running"]` → 409 拒绝。同时只能运行一个仿真。

### 3. 进程重启机制 `web_server.py:907-908`
停止仿真时 `os._exit(0)` 杀掉整个进程再 `subprocess.Popen` 重启。所有用户同时断开。

### 4. 全局定时任务调度器 `database/scheduler.py:224`
```python
_scheduler: Optional[TaskScheduler] = None  # 全局单例
```
所有用户共享同一个任务列表，CRUD 操作不做用户隔离。

### 5. 全局日志采集器 `database/log_streamer.py:524`
```python
_log_streamer: Optional[LogStreamer] = None  # 全局单例
```
所有用户看到相同的日志，WebSocket 广播不区分用户。

### 6. WebSocket 无用户频道隔离 `web_server.py:2316-2320`
```python
@socketio.on("connect")
def handle_connect():
    emit("status", dict(_runtime_state))  # 广播全局状态给所有客户端
```
无 Socket.IO room 机制，实时推送不加区分。

### 7. 全局配置字典 `web_server.py:87-109`
```python
_current_config: Dict[str, Any] = { "mode": "dynamic", ... }  # 全局配置
```
用户 A 改配置影响用户 B。

### 8. 数据库表无用户字段
- `sim_scheduled_tasks` — 无 `user_id`
- `sim_json_files` — 无 `owner`
- `sim_task_logs` — 无 `user_id`
- `sim_env_config` — 无 `creator`

### 9. MySQL 单连接共享——无光标锁 `database/mysql_db_manager.py:44`
```python
_mysql_client: Optional[Any] = None  # 单连接共享
```
并发 CRUD 时 `cursor.execute()` 和 `cursor.fetchall()` 之间无保护，多线程查询结果会互相覆盖。

### 10. 模块级全局可变参数 `simulation_core.py:47-56`
```python
ORIGIN_LAT = _DEFAULT_ORIGIN_LAT  # 模块级全局
CRUISE_SPEED = _DEFAULT_CRUISE_SPEED
```
`set_simulation_params()` 通过 `global` 关键字修改，两个仿真实例参数会互相覆盖。

---

## 二、整体改造方案

### 方案核心：引入"工作空间(Workspace)"概念

每个用户拥有独立的**工作空间**（workspace），通过 `username` 标识。工作空间内包含：
- 独立的仿真运行器
- 独立的配置
- 独立的定时任务列表
- 独立的日志流
- 独立的文件管理

使用**轻量级用户名机制**（无需 OAuth/注册），通过 URL 参数或 HTTP Header 传递用户名。

### 架构变更概览

```
改造前：
  浏览器A、B ──→ 同一个 Flask 进程 ──→ 共享 _sim_runner, _current_config, _scheduler...

改造后：
  浏览器A(username=userA) ──→ Flask 进程 ──→ WorkspaceManager
  浏览器B(username=userB) ──→                   ├─ workspace["userA"]
                                                 │   ├─ SimulationRunner
                                                 │   ├─ UserConfig
                                                 │   ├─ TaskScheduler (filtered)
                                                 │   └─ LogStreamer (filtered)
                                                 └─ workspace["userB"]
                                                     └─ ...
```

---

## 三、分阶段实施计划

### 阶段 1：用户身份识别基础（优先级 P0，2-3 天）

**目标**：建立最小用户识别机制，不改变业务逻辑。

#### 1.1 前端：用户名输入与传递
**改 `web/static/js/common.js`**：
```javascript
// 新增：用户名管理
function getUsername() {
    let name = localStorage.getItem('utm_username');
    if (!name) {
        name = prompt('请输入用户名（用于区分工作空间）：') || 'default_user';
        localStorage.setItem('utm_username', name);
    }
    return name;
}

// 修改 apiGet/apiPost，所有请求携带用户名
window.apiGet = async function(url) {
    const username = getUsername();
    const resp = await fetch(url, {
        headers: { 'X-UTM-Username': username }
    });
    // ...
};
```

**改 `web/pages/run.html`/`schedule.html`/`data.html`**：
- 在顶部导航栏显示当前用户名
- 提供切换用户按钮

#### 1.2 后端：用户识别中间件
**改 `utm_simulator/web_server.py`**：
```python
# Flask before_request 钩子
@app.before_request
def _identify_user():
    from flask import g, request
    g.username = request.headers.get('X-UTM-Username', 'default_user')
```

#### 1.3 数据库：添加 user_id 字段
**改 `database/mysql_db_manager.py`**（也需更新 SQLite `db_manager.py`）：

```sql
ALTER TABLE sim_scheduled_tasks ADD COLUMN user_id VARCHAR(128) DEFAULT '' AFTER id;
ALTER TABLE sim_json_files ADD COLUMN owner VARCHAR(128) DEFAULT '' AFTER id;
ALTER TABLE sim_env_config ADD COLUMN creator VARCHAR(128) DEFAULT '' AFTER id;
ALTER TABLE sim_task_logs ADD COLUMN user_id VARCHAR(128) DEFAULT '' AFTER task_id;
```

**文件**：`database/db_manager.py`、`database/mysql_db_manager.py`

---

### 阶段 2：仿真运行器多实例化（优先级 P0，3-4 天）

**目标**：允许多个用户同时运行各自的仿真，核心改动在 `web_server.py`。

#### 2.1 创建 WorkspaceManager
**新建 `utm_simulator/workspace_manager.py`**：

```python
class WorkspaceManager:
    """管理所有用户工作空间"""
    def __init__(self):
        self._lock = threading.Lock()
        self._workspaces: Dict[str, UserWorkspace] = {}

    def get_workspace(self, username: str) -> UserWorkspace:
        with self._lock:
            if username not in self._workspaces:
                self._workspaces[username] = UserWorkspace(username)
            return self._workspaces[username]

class UserWorkspace:
    def __init__(self, username: str):
        self.username = username
        self.sim_runner = None   # SimulationRunner 实例
        self.config = self._init_default_config()
        self.runtime_state = self._init_default_state()

    def _init_default_config(self):
        return { "mode": "dynamic", "target_drones": 1, ... }

    def _init_default_state(self):
        return { "running": False, "logs": [], ... }
```

#### 2.2 改造 web_server.py 全局状态
**改 `utm_simulator/web_server.py`**：

```python
# 替换以下全局单例：
# _sim_runner: Optional[SimulationRunner] = None
# _current_config: Dict = {...}
# _runtime_state: Dict = {...}

# 改为：
from workspace_manager import WorkspaceManager
_ws_mgr = WorkspaceManager()

# 每个路由从 Flask g 获取当前用户名的工作空间
def _current_ws():
    from flask import g
    return _ws_mgr.get_workspace(g.username)
```

#### 2.3 改造所有 API 路由
涉及约 30 个路由函数，模式统一改造：

```python
# 改前：
@app.route("/api/sim/status", methods=["GET"])
def api_get_status():
    with _lock:
        status = dict(_runtime_state)
    return jsonify(status)

# 改后：
@app.route("/api/sim/status", methods=["GET"])
def api_get_status():
    ws = _current_ws()
    with ws.lock:
        status = dict(ws.runtime_state)
    return jsonify(status)
```

**涉及文件**：`utm_simulator/web_server.py`（所有状态相关的 API 路由，约 30-40 处改动）

#### 2.4 移除进程重启机制
**改 `utm_simulator/web_server.py` line 891-908**：

`/api/sim/stop` 不再调用 `os._exit(0)`，改为：
```python
@app.route("/api/sim/stop", methods=["POST"])
def api_stop_sim():
    ws = _current_ws()
    if ws.sim_runner:
        ws.sim_runner.stop()
        ws.sim_runner = None
    ws.runtime_state["running"] = False
    return jsonify({"success": True, "message": "仿真已停止"})
```

#### 2.5 修复 simulation_core.py 模块级全局参数
**改 `utm_simulator/simulation_core.py`**：

将 `ORIGIN_LAT`、`CRUISE_SPEED` 等从模块级全局改为 `Simulator` 实例属性：
```python
class Simulator:
    def __init__(self, origin_lat=..., cruise_speed=..., ...):
        self.origin_lat = origin_lat
        self.cruise_speed = cruise_speed
        # ... 不再修改全局变量
```

---

### 阶段 3：定时任务用户隔离（优先级 P1，2 天）

**目标**：每个用户只能看到和管理自己创建的定时任务。

#### 3.1 定时任务 CRUD 加用户过滤
**改 `database/scheduler.py`**：

```python
# 所有查询加 user_id 过滤
def list_tasks(self, username: str) -> List[Dict]:
    return query(TASK_TABLE, where="user_id = ? AND enabled = 1", 
                 params=(username,), order_by="id DESC")

def add_task(self, data: Dict, username: str) -> int:
    data["user_id"] = username
    return insert(TASK_TABLE, data)
```

#### 3.2 调度器改为每用户独立线程
```python
# 保持全局 TaskScheduler，但循环中：
def _check_and_execute(self):
    # 获取所有不重复的 user_id
    users = query(TASK_TABLE, columns="DISTINCT user_id")
    for user in users:
        tasks = query(TASK_TABLE, where="enabled = 1 AND user_id = ?", ...)
        for task in tasks:
            # 每个用户的任务在独立线程中执行
            self._execute_task(task)
```

#### 3.3 前端定时任务页加用户过滤
**改 `web/static/js/schedule.js`**：

所有 API 调用已通过 `common.js` 携带 `X-UTM-Username` header，后端按用户名过滤。

涉及文件：`database/scheduler.py`、`utm_simulator/web_server.py`（schedule 相关路由）

---

### 阶段 4：日志流用户隔离（优先级 P1，1.5 天）

**目标**：每个用户看到自己的仿真日志。

#### 4.1 LogStreamer 按用户分组
**改 `database/log_streamer.py`**：

```python
class LogStreamer:
    def __init__(self):
        self._user_buffer: Dict[str, List[Dict]] = {}  # username → logs
        self._user_counts: Dict[str, Dict[str, int]] = {}

    def push_sim_log(self, username: str, msg: str):
        # 推送到指定用户的缓冲区
        ...

    def get_logs(self, username: str, ...) -> List[Dict]:
        return self._user_buffer.get(username, [])
```

#### 4.2 WebSocket 按用户房间推送
**改 `utm_simulator/web_server.py`**：

```python
@socketio.on("connect")
def handle_connect():
    from flask import request
    username = request.headers.get('X-UTM-Username', 'default_user')
    join_room(username)  # Socket.IO room
    
    # 只推送该用户的状态
    ws = _current_ws()
    emit("status", dict(ws.runtime_state), to=username)
```

涉及文件：`database/log_streamer.py`、`utm_simulator/web_server.py`

---

### 阶段 5：数据文件用户隔离（优先级 P2，1.5 天）

**目标**：不同用户的数据文件相互隔离，避免覆盖。

#### 5.1 JSON 文件按用户路径隔离
**改 `database/json_data_manager.py`**：

```python
def get_user_mock_dir(username: str) -> str:
    user_dir = os.path.join(MOCK_DIR, username)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir
```

#### 5.2 数据库文件表加 owner 过滤
```python
def list_files(self, username: str, ...):
    return query("sim_json_files", where="owner = ?", params=(username,))
```

涉及文件：`database/json_data_manager.py`、`utm_simulator/web_server.py`（data 相关路由）

---

### 阶段 6：环境配置用户隔离（优先级 P2，1 天）

**目标**：每个用户可以维护自己的环境配置集合。

#### 6.1 env_config 加 creator 过滤
**改 `database/env_manager.py`**：

```python
def list_envs(self, username: str) -> List[Dict]:
    return query("sim_env_config", 
                 where="creator = ? OR is_default = 1",
                 params=(username,))
```

涉及文件：`database/env_manager.py`、`utm_simulator/web_server.py`（env 相关路由）

---

### 阶段 7：共享基础设施冲突处理（优先级 P1，2 天）

**目标**：多个用户同时向共享 Redis/Kafka 注入数据时的命名空间隔离。

#### 7.1 Redis UID 前缀隔离
**改 `utm_simulator/sim_manager.py`**：

为每个用户的无人机 UID 添加用户名前缀：
```python
# 改前: uid = "UAV_00001"
# 改后: uid = f"{username}_UAV_00001"

def _plan_to_route_json(self, plan):
    uid = plan.aircraft.uid.decode("utf-8").rstrip("\x00")
    namespaced_uid = f"{self.username}:{uid}"  # 加用户名前缀
    ...
```

#### 7.2 Kafka 消息加 source_user 标记
```python
msg["sourceUser"] = self.username  # 在遥测消息中添加用户标记
```

#### 7.3 停止时精确清理
```python
def stop(self):
    # 只清理该用户自己写入的 Redis key
    for uid in self._dynamic_uids:
        self.redis.client.hdel(REDIS_FLIGHT_PLAN_KEY, uid)
```

涉及文件：`utm_simulator/sim_manager.py`

---

### 阶段 8：MySQL 连接池改造（优先级 P1，1.5 天）

**目标**：修复 MySQL 单连接多线程不安全的问题。

#### 8.1 引入连接池
**改 `database/mysql_db_manager.py`**：

使用 `pymysql` + `DBUtils.PooledDB` 或 `queue.Queue` 实现简易连接池：
```python
from queue import Queue

class MysqlPool:
    def __init__(self, cfg, pool_size=5):
        self._pool = Queue(maxsize=pool_size)
        for _ in range(pool_size):
            conn = MysqlDbClient(host=cfg.host, ...)
            conn.connect()
            self._pool.put(conn)

    def get_conn(self):
        return self._pool.get()

    def return_conn(self, conn):
        self._pool.put(conn)

_mysql_pool: Optional[MysqlPool] = None

def _get_client():
    global _mysql_pool
    with _lock:
        if _mysql_pool is None:
            _mysql_pool = MysqlPool(_load_config())
    return _mysql_pool.get_conn()  # 每个线程获取独立连接
```

涉及文件：`database/mysql_db_manager.py`

---

### 阶段 9：前端多用户界面适配（优先级 P2，2 天）

**目标**：前端界面对多用户友好。

#### 9.1 用户切换 UI
- 顶部导航栏显示当前用户名 + 下拉切换
- 首次访问引导输入用户名

#### 9.2 运行状态面板标注用户
- 当有多个仿真同时运行时，状态卡片显示所属用户
- 机器人列表标注 owner

涉及文件：`web/static/js/common.js`、`web/pages/run.html`、`web/css/style.css`

---

### 阶段 10：Docker 部署适配（优先级 P3，1 天）

**目标**：确保多用户环境部署稳定。

#### 10.1 连接池配置
**改 `docker/docker-compose.yml`**：
```yaml
environment:
  - UTM_MYSQL_POOL_SIZE=${UTM_MYSQL_POOL_SIZE:-10}
```

#### 10.2 移除旧的进程重启逻辑
- 容器不再需要每停一次仿真就重启

#### 10.3 健康检查保持
- Healthcheck 保持不变（检查 `/api/sim/status`）

涉及文件：`docker/docker-compose.yml`、`docker/entrypoint.sh`

---

## 四、关键改造文件清单

| 优先级 | 文件 | 改动性质 | 改动量估计 |
|--------|------|----------|-----------|
| P0 | `utm_simulator/web_server.py` | 重写全局状态 → 工作空间 | ~50 处 |
| P0 | `utm_simulator/workspace_manager.py` | **新建**核心管理模块 | ~200 行 |
| P0 | `database/mysql_db_manager.py` | 加 user_id 字段 + 连接池 | ~20 处 |
| P0 | `database/db_manager.py` | 加 user_id 字段 | ~10 处 |
| P0 | `utm_simulator/simulation_core.py` | 模块级全局 → 实例属性 | ~15 处 |
| P0 | `web/static/js/common.js` | 加用户识别逻辑 | ~30 行 |
| P1 | `database/scheduler.py` | 加 user_id 过滤 | ~10 处 |
| P1 | `database/log_streamer.py` | 按用户分组日志 | ~20 处 |
| P1 | `utm_simulator/sim_manager.py` | UID 命名空间隔离 | ~10 处 |
| P2 | `database/json_data_manager.py` | 用户路径隔离 + owner 过滤 | ~15 处 |
| P2 | `database/env_manager.py` | creator 字段过滤 | ~5 处 |
| P2 | `web/static/js/run.js` | 用户状态显示 | ~10 处 |
| P2 | `web/pages/*.html` | UI 用户名显示 | ~5 处 |
| P3 | `docker/docker-compose.yml` | 连接池配置 | ~3 行 |

---

## 五、风险评估

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| **ctypes 堆污染**（Simulator + kafka-python 并发） | HIGH | dynamic 模式已通过 `telemetry_bridge.py` 子进程隔离；多个 SimulationManager 可各自启动独立子进程 |
| **Redis key 冲突**（多用户向同一 `BIZ_DATA:UAV_ROUTE` 写入） | MEDIUM | UID 前缀命名空间隔离，停止时精确清理 |
| **Kafka topic 共享**（多用户同时注入 `uav_runtime_data`） | LOW | 下游 ATC 按 UID 区分，每个用户加 `sourceUser` 标记 |
| **MySQL 连接池增加连接数** | LOW | 默认 pool_size=5，通过环境变量可调 |
| **SQLite 回退不适用多用户** | MEDIUM | 多用户时强制需要 MySQL；SQLite 模式不支持并发写 |
| **向后兼容性**（现有脚本依赖全局状态） | LOW | CLI 脚本和 HA 测试脚本仍可直接使用 SimulationManager，不受 web 层改动影响 |
| **Simulator.agents 数据竞态** | MEDIUM | 加 `threading.Lock` 保护 Simulator.agents 的读写 |

---

## 六、验证方案

### 单元测试
1. `WorkspaceManager` 多用户创建/隔离测试
2. 调度器用户过滤测试
3. 日志用户过滤测试

### 集成测试
1. **双用户并发仿真**：用户 A 启动 dynamic 模式 100 架无人机 + 用户 B 同时启动 replay 模式
2. **定时任务隔离**：用户 A 创建任务 → 用户 B 登录看不到用户 A 的任务
3. **日志隔离**：两用户同时运行仿真 → 各自只看到自己的日志
4. **配置独立**：用户 A 改 mode=plan → 用户 B 的 mode 不变

### 端到端测试
```bash
# 终端 1：用户 A 启动仿真
curl -H "X-UTM-Username: Alice" -X POST http://localhost:5000/api/sim/start \
     -d '{"mode":"dynamic","target_drones":50}'

# 终端 2：用户 B 查看状态（应该是独立空间，"未在运行"）
curl -H "X-UTM-Username: Bob" http://localhost:5000/api/sim/status

# 终端 2：用户 B 启动自己的仿真
curl -H "X-UTM-Username: Bob" -X POST http://localhost:5000/api/sim/start \
     -d '{"mode":"replay","target_drones":30}'

# 验证两个仿真同时运行，状态互不干扰
curl -H "X-UTM-Username: Alice" http://localhost:5000/api/sim/status
curl -H "X-UTM-Username: Bob" http://localhost:5000/api/sim/status
```

---

## 七、改造总量估算

| 阶段 | 工作天数 | 改动文件数 | 新建文件数 |
|------|---------|-----------|-----------|
| 阶段 1：用户身份 | 2-3 天 | 5 | 0 |
| 阶段 2：仿真多实例 | 3-4 天 | 3 | 1 |
| 阶段 3：任务隔离 | 2 天 | 2 | 0 |
| 阶段 4：日志隔离 | 1.5 天 | 2 | 0 |
| 阶段 5：文件隔离 | 1.5 天 | 2 | 0 |
| 阶段 6：环境隔离 | 1 天 | 2 | 0 |
| 阶段 7：基础设施隔离 | 2 天 | 1 | 0 |
| 阶段 8：MySQL 连接池 | 1.5 天 | 1 | 0 |
| 阶段 9：前端适配 | 2 天 | 5 | 0 |
| 阶段 10：部署适配 | 1 天 | 2 | 0 |
| **合计** | **17-21 天** | **约 25 个文件** | **1 个新文件** |
