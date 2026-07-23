# utm-simulator 优化工作日志

## 2026-07-23 — 仿真执行文件列表修复 + 模式绑定移除 + 性能优化

### 修改清单

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-23 | `web/static/js/run.js` | 修改 | ✅ | 场景文件下拉显示全部16条数据库文件 |
| 2026-07-23 | `web/pages/run.html` | 修改 | ✅ | 下拉框高度增大至220px，可一次展示12+行 |
| 2026-07-23 | `web/server.py` | 修改 | ✅ | `/api/data/db/export-batch` 批量导出接口可用 |

### 核心修复

1. **移除模式-文件绑定**：删除 `bindModeToFile()` / `_restoreAllModes()` 函数及相关变量（~65行），选择 JSON 文件不再自动切换仿真模式，消除页面跳转问题。模式切换完全由用户手动控制。

2. **文件列表来源改为数据库**：`_loadCachedFileList()` 从 `/api/data/files`（磁盘读取 `data/mock/`）改为 `/api/data/db/files?page_size=500`（MySQL 数据库），场景文件下拉框从仅显示 2 个已导出文件变为显示全部 16 条数据库文件，与"数据管理"页面保持一致。

3. **启动前自动导出**：scene 模式启动时自动调用 `/api/data/db/export-batch` 将选中文件批量导出到 `data/mock/`；plan 模式选择航线文件时同样自动导出。后端脚本无需感知数据存储位置，始终从 `mock/` 目录读取。

4. **下拉框高度优化**：场景文件 `<select multiple>` 高度从 `60px`（约 3 行）增加到 `220px`（约 12 行），文件浏览体验显著提升。

5. **列表加载缓存**：引入 `sessionStorage` 缓存（60s TTL），避免反复请求文件列表 API。手动刷新按钮清除缓存后重新加载。

6. **新增批量导出接口**：`POST /api/data/db/export-batch` 接受 `{"file_ids": [1,2,3]}`，调用 `json_data_manager.export_to_mock_batch()` 批量复制文件到 `data/mock/`。

### 汇总

- 新建文件：0
- 修改文件：3

---

## 2026-07-22 — sim_env_config 表重建 + 达梦连接修复 + 数据管理编辑 404 修复

### 修改清单

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-22 | `database/mysql_db_manager.py` | 修改 | ✅ | 重启服务后 MySQL 写操作恢复 |
| 2026-07-22 | `database/rebuild_sim_env_config.py` | 重写 | ✅ | 执行脚本成功 DROP+CREATE 新表(25列) |
| 2026-07-22 | `database/json_data_manager.py` | 修改 | ✅ | 达梦切换环境后连接生效；编辑返回 200 |
| 2026-07-22 | `database/env_manager.py` | 修改 | ✅ | 激活环境时 env.py 变量引用写法可被正则匹配 |
| 2026-07-22 | `database/log_streamer.py` | 修改 | ✅ | 首次写入失败打印异常详情 |
| 2026-07-22 | `web/server.py` | 修改 | ✅ | 数据管理编辑功能恢复正常 |
| 2026-07-22 | `common/config.json` | 修改 | ✅ | 达梦配置被 _get_dm_client() 正确读取 |
| 2026-07-22 | `env.py` | 修改 | ✅ | 达梦连接成功(10.165.32.205:5236) |

### 核心修复

1. **sim_env_config 旧表重建**：远程 MySQL 上 36 个连接全部卡在 `Waiting for table metadata lock`（最长 5727s），导致任何 DDL 挂死。重写重建脚本：直接 pymysql 连接 → `information_schema.PROCESSLIST` 查杀卡死连接 → DROP TABLE → CREATE TABLE (25 列完整结构)

2. **pymysql 超时保护**：`_create_pool()` 添加 `read_timeout=10, write_timeout=10`，防止远程 MySQL 不响应时无限挂死；`_get_client()` 缓存连接前 `ping(reconnect=False)` 验证存活性

3. **达梦连接修复**：A 节点(10.165.32.212)宕机，切到 B 节点(10.165.32.205)；`_get_dm_client()` 优先从 config.json 读取配置、检测变更自动重连、显式传参给 DmDbClient（修复模块级 import 值冻结）

4. **数据管理编辑 404 修复**：`return jsonify(record) if record else ..., 404` 中 Python `,` 优先级低于三元表达式，导致查到数据也返回 HTTP 404。拆分为独立 if/else 分支

### 汇总

- 新建文件：0
- 修改文件：7
- 重写文件：1

---

## 2026-07-23 — 环境删除修复 + DELETE 路由异常保护 + 全部导出到磁盘

### 修改清单

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-23 | `web/static/js/env.js` | 修改 | ✅ | 环境删除不再报 `API_BASE is not defined` |
| 2026-07-23 | `web/server.py` | 修改 | ✅ | 4 个 DELETE 路由异常返回 JSON 而非 werkzeug 崩溃 |
| 2026-07-23 | `database/json_data_manager.py` | 修改 | ✅ | `export_all_to_mock()` 批量导出全部文件到磁盘 |
| 2026-07-23 | `web/pages/data.html` | 修改 | ✅ | "全部导出到磁盘"按钮可用 |
| 2026-07-23 | `web/static/js/data.js` | 修改 | ✅ | 导出按钮事件处理正常 |

### 核心修复

1. **环境删除 API_BASE 作用域错误**：`env.js` `deleteEnv()` 中 `fetch(API_BASE + '/api/env/' + id)` 的 `API_BASE` 是 `common.js` IIFE 内部 `const`，`env.js` 的 IIFE 不可访问，导致 `ReferenceError` 删除失败。改为直接使用 `'/api/env/' + id`（与 `data.js`、`scene.js` 等所有其他 DELETE 调用一致）。

2. **4 个 DELETE 路由添加 @_safe_json 装饰器**：`api_env_delete`、`api_db_delete_file`、`api_db_delete_category`、`api_db_alarm_types_delete` 添加 `@_safe_json` 异常保护。此前这些路由无任何 try/except，MySQL 不可用时异常传播至 werkzeug 触发 `AssertionError: write() before start_response`。`@_safe_json` 装饰器已存在于场景 CRUD 路由，现统一应用到所有 DELETE 路由。

3. **@_safe_json 装饰器前移**：装饰器原定义在场景路由段（~2530行），早于多个使用它的路由。将定义移至环境管理 API 段之前（~1910行），解决 `NameError: name '_safe_json' is not defined` 启动错误。

4. **新增全部导出到磁盘功能**：新增 `POST /api/data/db/export-all` 端点 + `export_all_to_mock()` 后端函数 + "💾 全部导出到磁盘"前端按钮。Docker 重建后可通过此按钮一键将 MySQL 中所有文件记录恢复到 `data/mock/`，解决磁盘文件丢失导致预览显示"(- 估, 0 行)"的问题。

### 汇总

- 新建文件：0
- 修改文件：5
