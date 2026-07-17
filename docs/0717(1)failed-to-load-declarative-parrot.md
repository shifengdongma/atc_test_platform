# 定时任务功能修复计划

## Context

用户在使用"定时任务"模块的"批量创建"和"单个添加"功能时遇到两类错误：

1. **404 NOT FOUND** on `POST /api/schedule/tasks/batch` — 批量创建端点不存在
2. **500 INTERNAL SERVER ERROR** on `GET/POST /api/schedule/tasks` — 单个添加/列表加载失败

这两个错误导致前端 `schedule.js` 收到 HTML 错误页面而非 JSON，抛出 `SyntaxError: Unexpected token '<'`。

## 根因分析

### Bug 1: 404 — 缺失批量创建端点
- 前端 `web/static/js/schedule.js:280` 调用 `POST /api/schedule/tasks/batch`，发送 `{ items: [...] }`
- 后端 `utm_simulator/web_server.py` 中**没有定义该路由**
- 前端期望响应格式 `{ success: true, count: N }`

### Bug 2: 500 — MySQL 不可用时异常未捕获
- `database/scheduler.py` 只导入 `mysql_db_manager`
- `mysql_db_manager.insert()` 在 MySQL 不可用时抛出 `RuntimeError("MySQL 不可用，无法写入数据")` → Flask 500 HTML 页面
- 所有 8 个 schedule 路由均无 try/except 保护

### 附加问题
- `web/static/js/common.js` 的 `apiPost`/`apiGet` 不检查 `resp.ok`，对 HTML 响应直接调用 `resp.json()` 导致 `SyntaxError`

## 修复方案

遵循 CLAUDE.md 规则："聚焦修复实际 bug，不添加防御性预判代码"。

### 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `utm_simulator/web_server.py` | 修改 | 新增批量创建端点 + 所有 8 个 schedule 路由加 try/except |
| `web/static/js/common.js` | 修改 | `apiGet`/`apiPost` 加 `resp.ok` 检查，避免 JSON 解析崩溃 |
| `CLAUDE.md` | 修改 | 删除 MySQL→SQLite 降级示例 |
| `.claude/CLAUDE.md` | 修改 | 同步删除 MySQL→SQLite 降级示例 |

### 变更 1：`utm_simulator/web_server.py` — 新增批量创建端点

在 `api_schedule_create()` 之后（约第2236行后）新增：

```python
@app.route("/api/schedule/tasks/batch", methods=["POST"])
def api_schedule_batch_create():
    """批量创建定时任务。"""
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"success": False, "message": "任务列表不能为空"}), 400
    sch = _get_scheduler()
    count = 0
    errors = []
    for i, item in enumerate(items):
        if not item.get("name"):
            errors.append({"index": i, "message": "任务名称不能为空"})
            continue
        try:
            sch.add_task(item)
            count += 1
        except Exception as e:
            errors.append({"index": i, "message": str(e)})
    if count > 0:
        _add_log(f"批量创建了 {count} 个定时任务")
        return jsonify({"success": True, "count": count, "errors": errors if errors else None})
    else:
        return jsonify({"success": False, "count": 0, "message": "所有任务均创建失败", "errors": errors}), 500
```

**关键设计**：
- 前端 `schedule.js:280` 调用 `apiPost('/api/schedule/tasks/batch', {items:items})`，检查 `r.success`（line 281）和 `r.count`（line 282）
- 跳过名称为空的项，不阻塞其余项
- 全部失败返回 `success: false` + 500，部分成功返回 `success: true` + count

### 变更 2：`utm_simulator/web_server.py` — 所有 8 个 schedule 路由加 try/except

现有路由（lines 2219-2283）全部加 try/except 包裹，返回 JSON 错误而非 500 HTML：

```python
# GET /api/schedule/tasks
@app.route("/api/schedule/tasks", methods=["GET"])
def api_schedule_list():
    try:
        sch = _get_scheduler()
        tasks = sch.list_tasks()
        return jsonify({"tasks": tasks})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# POST /api/schedule/tasks
@app.route("/api/schedule/tasks", methods=["POST"])
def api_schedule_create():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"success": False, "message": "任务名称不能为空"}), 400
    try:
        sch = _get_scheduler()
        tid = sch.add_task(data)
        _add_log(f"定时任务已创建: {data.get('name','')}")
        return jsonify({"success": True, "id": tid, "message": "已创建"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# PUT /api/schedule/tasks/<task_id>
# DELETE /api/schedule/tasks/<task_id>
# POST /api/schedule/tasks/<task_id>/pause
# POST /api/schedule/tasks/<task_id>/resume
# POST /api/schedule/tasks/<task_id>/run-now
# GET /api/schedule/tasks/<task_id>/history
# （以上 6 个路由均按相同模式包裹 try/except）
```

**模式**：`_get_scheduler()` 放到 try 块内，捕获所有异常后返回 `{"success": False, "message": str(e)}` + 500。

### 变更 3：`web/static/js/common.js` — API 封装加响应状态检查

```javascript
window.apiGet = async function(path) {
  const resp = await fetch(API_BASE + path);
  if (!resp.ok) {
    try { return await resp.json(); }
    catch(e) { return { success: false, message: `请求失败 (${resp.status})` }; }
  }
  return resp.json();
};

window.apiPost = async function(path, body) {
  const resp = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!resp.ok) {
    try { return await resp.json(); }
    catch(e) { return { success: false, message: `请求失败 (${resp.status})` }; }
  }
  return resp.json();
};
```

**设计**：
- 先尝试 `resp.json()`（后端可能返回 JSON 错误体，如 `{"success": false, "message": "..."}` + 500）
- 如果响应体不是 JSON（如 HTML），捕获并提供 fallback 错误消息
- 返回的 `{success: false, message: "..."}` 与后端约定一致，现有前端代码 `if (r.success)` 逻辑自然兼容

### 变更 4：`CLAUDE.md` + `.claude/CLAUDE.md` — 删除 SQLite 降级示例

将两处 CLAUDE.md 中的：
```
- **修改原则**：……异常路径的兜底逻辑优先用已有的 fallback 机制（如 MySQL→SQLite 降级），不在每个函数中重复添加相同的 if 判断。……
```

改为：
```
- **修改原则**：聚焦修复实际 bug，不添加防御性预判代码。保持代码精简，不为"可能发生但从未出现"的场景预先加代码
```

## 验证方式

1. **批量创建**：访问 `/schedule` 页面 → 切换到批量模式 → 添加多行任务 → 点击批量保存 → 应成功创建并在列表中显示
2. **单个添加**：填写表单 → 点击保存 → 应成功保存并在列表中显示
3. **列表加载**：刷新页面 → 任务列表应正常加载
4. **回归**：编辑、删除、暂停、恢复、立即执行、查看历史等操作均正常
5. **MySQL 不可用时**：不应再出现 500 HTML 页面 → 应有 JSON 格式错误返回 → 前端显示错误 toast 而非静默崩溃
