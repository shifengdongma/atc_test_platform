# 场景编排模块修复与优化计划 v2

## Context

上一轮重构引入了三个严重问题：

### 问题1：系统卡顿、页面响应慢、切换页面进程崩溃

**根因A** — `json_data_manager.py` 模块级代码在每次首次导入时触发重型操作：
- 第33-34行：`_init_tables()` → MySQL连接 + SHOW TABLES + 7次CREATE TABLE
- 第71行：`_migrate_file_paths_once()` → `SELECT * FROM sim_json_files` 全表扫描
- 第729行：`_check_ssl11()` → ctypes加载 + subprocess ldconfig（仅Linux）

**根因B** — 数据管理页每次加载执行3次 `SELECT *` 全表扫描（获取categories/alarm_types/files），含数千条记录时阻塞页面

**根因C** — `os._exit(0)` 暴力退出（web_server.py:166,1019），跳过MySQL连接关闭，下次启动时连接池残留导致重连超时

**根因D** — `_get_client()` 每次调用执行 ping + SELECT 1 健康检查，每次数据页请求触发5+次往返

**根因E** — 场景编排 `_execute_scene_file()` 每个文件创建一个新的SimulationRunner线程，并行模式下线程爆炸（N×5+M个线程）

### 问题2：场景编排功能完全无法使用

**根因（关键Bug）** — `mysql_db_manager.insert()` 无条件添加 `created_at` 和 `updated_at` 列，但新增的三张表中：

| 表 | created_at | updated_at | insert结果 | update结果 |
|----|-----------|------------|-----------|-----------|
| sim_scenes | ✅ | ✅ | ✅ | ✅ |
| sim_scene_tasks | ✅ | ❌ | ❌ 失败 | ❌ 失败 |
| sim_scene_task_files | ✅ | ❌ | ❌ 失败 | ❌ 失败 |
| sim_task_logs | ❌ | ❌ | ❌ 失败 | N/A |

每次INSERT都报 `Unknown column 'updated_at'` ，异常被 `_safe_json` 捕获返回500，前端 `apiPost` 又吞掉了具体错误消息，用户只看到"请求失败 (500)"。

**附加Bug**：
- `update_scene()` 未pop非表字段(`file_id`, `cycle_interval_sec`, `tasks`)
- 前端编辑场景时重复发送POST+PUT两次请求
- `get_orchestrator()` 无线程安全保护

### 问题3：前端UI需优化

用户要求：
- 单文件场景和多文件场景页面分隔开
- 增设任务列表页面，能查看和编辑所有已创建的定时任务

---

## 修复计划

### 阶段A：关键Bug修复（让场景编排能正常工作）

#### A1. 修复DDL — 补全缺失列 — `database/mysql_db_manager.py`

**sim_scene_tasks** DDL增加：
```sql
`updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
```

**sim_scene_task_files** DDL增加：
```sql
`updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
```

**sim_task_logs** DDL增加：
```sql
`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
`updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
```

同步更新 `database/db_manager.py` 的SQLite DDL。

#### A2. 修复 `_ensure_mysql_tables()` — 支持ALTER已有表 — `database/mysql_db_manager.py`

当前 `_ensure_mysql_tables()` 只对**不存在**的表执行 CREATE，对于已存在但缺列的表不做处理。需要增加ALTER逻辑：

```python
# 对已存在的表，检查并补全缺失列
_ALTER_DDL = {
    "sim_scene_tasks": [
        "ADD COLUMN `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ],
    "sim_scene_task_files": [
        "ADD COLUMN `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ],
    "sim_task_logs": [
        "ADD COLUMN `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP",
        "ADD COLUMN `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    ],
}
```

在 `_ensure_mysql_tables()` 末尾，遍历已存在的表，用 `SHOW COLUMNS` 检查缺失列，执行 `ALTER TABLE ADD COLUMN`（用 try/except 包裹，列已存在则跳过）。

#### A3. 修复 `update_scene()` — pop非表字段 — `database/orchestrator.py`

```python
def update_scene(self, scene_id: int, data: Dict[str, Any]) -> bool:
    # 清理非表字段（与 create_scene 对齐）
    data.pop("tasks", None)
    data.pop("file_id", None)
    data.pop("cycle_interval_sec", None)
    data["updated_at"] = _now()
    return update(SCENE_TABLE, scene_id, data)
```

#### A4. 修复前端 — 保留错误详情 + 去重请求 — `web/static/js/common.js` + `scene.js`

**common.js** `apiPost` 修复 — 不吞错误消息：
```javascript
window.apiPost = async function(path, body) {
  const resp = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!resp.ok) {
    try { const err = await resp.json(); throw new Error(err.message || `请求失败 (${resp.status})`); }
    catch(e) { 
      if (e.message && !e.message.startsWith('请求失败')) throw e;  // 保留服务器错误
      throw new Error(`请求失败 (${resp.status})`); 
    }
  }
  return resp.json();
};
```

**scene.js** 编辑保存 — 删除冗余的POST，只保留PUT：
```javascript
if (editId) {
  var resp = await fetch('/api/scenes/' + editId, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  r = await resp.json();
}
```

#### A5. 线程安全 — `database/orchestrator.py`

`get_orchestrator()` 加锁：
```python
_lock = threading.RLock()

def get_orchestrator(execute_callback=None):
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator
    with _lock:
        if _orchestrator is None:
            _orchestrator = SceneOrchestrator(execute_callback=execute_callback)
            _orchestrator.start()
        return _orchestrator
```

---

### 阶段B：性能优化（解决卡顿和崩溃）

#### B1. `json_data_manager.py` — 模块级代码延迟化

将第33-34行的 `_init_tables()` 调用移到首次实际使用数据库时（如 `list_files()` 开头），不再在 import 时执行。`_migrate_file_paths_once()` 改为在 `list_files()` 首次调用时执行。

`_check_ssl11()` 保留在模块级（仅在Linux上执行，且只检测一次）。

#### B2. 优化数据管理页查询 — `database/json_data_manager.py`

`get_categories()` 改用 `SELECT DISTINCT category FROM sim_json_files` 替代 `SELECT *` 全表扫描。

`get_alarm_types()` 同理，合并 files + custom_types 查询。

在 `mysql_db_manager.py` 增加 `query_distinct()` 辅助函数：
```python
def query_distinct(table: str, column: str) -> List[str]:
    with _lock:
        client = _get_client()
        if not client:
            return []
        cur = _cursor(client)
        cur.execute(f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` != ''")
        return [row[column] for row in cur.fetchall()]
```

#### B3. 减少 `_get_client()` 健康检查频率 — `database/mysql_db_manager.py`

增加连接级TTL：只在距离上次健康检查超过30秒时才执行 ping + SELECT 1，否则直接返回已有客户端。

```python
_last_health_check: float = 0.0
_HEALTH_CHECK_TTL: float = 30.0

# 在 _get_client() 的保活分支中:
if time.time() - _last_health_check > _HEALTH_CHECK_TTL:
    # 执行 ping + SELECT 1
    _last_health_check = time.time()
```

#### B4. 修复 `os._exit(0)` — `utm_simulator/web_server.py`

将第166行和第1019行的 `os._exit(0)` 替换为优雅关闭：
- 先关闭 MySQL 连接
- 先停止 orchestrator 线程
- 先关闭 Kafka 消费者
- 再用 `sys.exit(0)` 替代 `os._exit(0)`

```python
def _graceful_shutdown():
    """优雅关闭：清理资源后退出。"""
    try:
        if _orchestrator:
            _orchestrator.stop()
    except Exception:
        pass
    try:
        from mysql_db_manager import close as _close_mysql
        _close_mysql()
    except Exception:
        pass
    sys.exit(0)
```

#### B5. 限制场景编排线程数 — `database/orchestrator.py`

在 `_execute_scene_file` 中，添加全局线程池限制（最多5个并发仿真），避免线程爆炸。

---

### 阶段C：前端UI重构

#### C1. 页面拆分 — 单文件场景 + 多文件场景 + 任务列表

**新建三个子页面**（在同一 `scene.html` 中用标签页切换）：

| 标签页 | 功能 |
|--------|------|
| 📄 单文件场景 | 创建/编辑单文件场景（一个文件 + 循环间隔 + cron调度） |
| 📑 多文件场景 | 创建/编辑多文件场景（多任务多文件 + 串行/并行配置） |
| 📋 任务列表 | 查看所有已创建的场景和任务，支持启用/禁用、立即执行、编辑、删除 |

**scene.html** 结构调整：
- 顶部标签页切换栏
- 标签页1（单文件）：简化表单 — 场景名、环境、文件选择、循环间隔(秒)、调度
- 标签页2（多文件）：任务标签页 + 任务编辑器 + 文件列表（保持现有逻辑）
- 标签页3（任务列表）：从 `/api/scenes` 加载所有场景卡片 + 展开查看任务详情

**scene.js** 调整：
- `switchTab(tab)` 函数切换三个标签页
- 单文件表单提交逻辑独立
- 多文件表单提交逻辑独立
- 任务列表独立加载和操作

---

## 修改文件清单

| 文件 | 阶段 | 操作 | 关键改动 |
|------|------|------|----------|
| `database/mysql_db_manager.py` | A1, A2, B3 | 修改 | 补全DDL列 + ALTER逻辑 + 健康检查TTL + query_distinct |
| `database/db_manager.py` | A1 | 修改 | 同步SQLite DDL |
| `database/orchestrator.py` | A3, A5, B5 | 修改 | update_scene pop + 线程安全锁 + 线程池限制 |
| `database/json_data_manager.py` | B1, B2 | 修改 | 去模块级init + SELECT DISTINCT优化 |
| `utm_simulator/web_server.py` | B4 | 修改 | os._exit → 优雅关闭 |
| `web/static/js/common.js` | A4 | 修改 | apiPost保留错误详情 |
| `web/static/js/scene.js` | A4, C1 | 重写 | 去双重请求 + 三标签页结构 |
| `web/pages/scene.html` | C1 | 重写 | 三标签页布局 |

## 验证方式

1. **场景创建**：单文件场景创建 → 确认数据库 sim_scenes + sim_scene_tasks + sim_scene_task_files 三表均有记录
2. **场景创建**：多文件场景创建 → 多任务多文件 → 确认所有关联记录正确
3. **任务CRUD**：编辑任务名称 → 保存 → 确认数据库更新
4. **性能**：多次切换数据管理/场景编排页面 → 不再卡顿 → 进程不退出
5. **错误提示**：模拟错误场景 → 前端显示具体错误消息而非通用"请求失败 (500)"
6. **优雅退出**：Ctrl+C 停止服务 → MySQL连接正常关闭 → 立即重启无残留连接问题
