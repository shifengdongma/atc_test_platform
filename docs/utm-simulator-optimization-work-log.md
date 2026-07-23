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

---

## 2026-07-23 — scene 模式仿真数据发送修复 + flight_data 格式兼容 + 批量操作 + 监控指标重命名

### 修改清单

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-23 | `web/server.py` | 修改 | ✅ | mock_dir 路径修复 + scene 诊断日志 + config.json 路径修复 |
| 2026-07-23 | `core/sim_manager.py` | 修改 | ✅ | mock_dir 路径修复 |
| 2026-07-23 | `core/kafka_proc.py` | 修改 | ✅ | null UID 保护 + max_request_size(10MB) + flush 超时(10s) |
| 2026-07-23 | `tools/run_kafka_scene.py` | 修改 | ✅ | flight_data 格式识别 + `_normalize_flight_data()` 转换 + Redis 航线格式完善 |
| 2026-07-23 | `database/json_data_manager.py` | 修改 | ✅ | `delete_files_batch()` + `export_all_to_mock()` + 文件截断保护 |
| 2026-07-23 | `database/log_streamer.py` | 修改 | ✅ | `report_kafka_telemetry` → `report_redis_telemetry` |
| 2026-07-23 | `common/schemas.py` | 修改 | ✅ | `kafka_msg_per_sec` → `redis_msg_per_sec` |
| 2026-07-23 | `web/pages/data.html` | 修改 | ✅ | 批量上传/删除按钮 + 复选框列 |
| 2026-07-23 | `web/pages/run.html` | 修改 | ✅ | canvas id + 卡片标签改为 Redis |
| 2026-07-23 | `web/index.html` | 修改 | ✅ | 同上 |
| 2026-07-23 | `web/static/js/data.js` | 修改 | ✅ | 批量上传/删除逻辑 + 文件截断保护 |
| 2026-07-23 | `web/static/js/run.js` | 修改 | ✅ | `kafka_msg_per_sec` → `redis_msg_per_sec` |
| 2026-07-23 | `web/static/js/app.js` | 修改 | ✅ | 同上 |
| 2026-07-23 | `web/static/js/charts.js` | 修改 | ✅ | `kafkaData` → `redisData` 全部重命名 |
| 2026-07-23 | `tests/test_schemas.py` | 修改 | ✅ | 同步字段重命名 |
| 2026-07-23 | `README.md` | 修改 | ✅ | 文档同步 |

### 核心修复

1. **mock_dir 路径修复（11 处）**：`os.path.join(_root, "..", "data", "mock")` → `os.path.join(_root, "data", "mock")`，`_root` 已是项目根目录，多余的 `".."` 跳到父目录导致 SceneEmitter 找不到文件；同时修复 `config.json` 写入路径。

2. **flight_data 格式兼容**：新增 `_normalize_flight_data()` 将 flight_data 格式 `{"data": [{uav_id, position:{lat,lon,alt}, track_angle, status:{ground_speed}}]}` 完整转换为 ATC 遥测格式（23+ 字段，含 `coordinateSystemType`/`rpsLocationType`/`pressureAltitude` 等全部必填字段），5360 个坐标点逐条发送而非整体打包。

3. **Kafka 生产者健壮性**：null UID 兜底 `or 'UNKNOWN'`；`max_request_size` 1MB→10MB 支持大消息；flush 超时 1s→10s 避免 KafkaTimeoutError。

4. **Redis 航线格式完善**：`segmentProtectHeight`(0→50)、`segmentProtectHeightType`(0→1)、`segmentWidth`(0→100) 匹配标准 ATC 格式；航段数限制 ≤200 段防止下游因过多航段拒绝；补齐 `realNameRegistrationSign` 字段。

5. **批量操作**：上传支持 `multiple` 多文件选择并逐个上传显示进度；删除支持勾选多行 → 批量删除确认 → `POST /api/data/db/files/batch-delete` → 汇总结果。

6. **文件截断保护**：编辑 >100KB 文件时仅加载前 100KB（预览），保存时不发送 content 防止截断覆盖原文件；后端 `save_file()` 检测新内容 < 原文件 80% 时拒绝覆盖。

7. **监控指标重命名**：卡片、图表、JS 变量/ID、服务端状态 key、日志函数 全部 `Kafka` → `Redis`（`kafka_msg_per_sec` → `redis_msg_per_sec`，`chart-kafka` → `chart-redis`，`#kafka-tp` → `#redis-tp` 等）。

8. **scene 模式诊断日志**：启动前检查文件存在性并记录到 Web UI 运行日志；创建 SceneEmitter 后报告加载的 UAV 数量和记录数。

### 汇总

- 新建文件：0
- 修改文件：16

---

## 2026-07-23 — 监控页面 Redis→Kafka 标签修正 + 错误计数字号修复

### 修改清单

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-23 | `web/pages/run.html` | 修改 | ✅ | 卡片和图表标签显示"Kafka 吞吐" |
| 2026-07-23 | `web/index.html` | 修改 | ✅ | 同上，旧版页面同步修正 |
| 2026-07-23 | `web/static/js/run.js` | 修改 | ✅ | DOM 引用/变量 `redisTp`→`kafkaTp` |
| 2026-07-23 | `web/static/js/app.js` | 修改 | ✅ | 同上，旧版 JS 同步修正 |
| 2026-07-23 | `web/static/js/charts.js` | 修改 | ✅ | 图表变量/label/title 全部改为 Kafka |
| 2026-07-23 | `web/server.py` | 修改 | ✅ | 状态字段 `redis_msg_per_sec`→`kafka_msg_per_sec`（7处） |
| 2026-07-23 | `core/sim_manager.py` | 修改 | ✅ | 返回字段名同步为 `kafka_msg_per_sec` |
| 2026-07-23 | `common/schemas.py` | 修改 | ✅ | Schema 字段名+注释同步 |
| 2026-07-23 | `tests/test_schemas.py` | 修改 | ✅ | 测试数据字段名同步 |

### 核心修复

1. **监控标签回正：Redis→Kafka**：上轮优化错误地将监控卡片"Kafka 吞吐"改为"Redis 吞吐"，但该指标实际统计的是 `kafka_ps`（Kafka 消息发送速率），并非 Redis 吞吐量。本次将所有前端标签、JS 变量名（`redisTp`→`kafkaTp`、`chartRedis`→`chartKafka`、`redisData`→`kafkaData`）、后端字段名（`redis_msg_per_sec`→`kafka_msg_per_sec`）全部改回 Kafka 命名，与数据来源一致。

2. **错误计数字号统一**：`#error-count` 卡片缺少 `big` CSS 类，字号仅 14px，而其余三个数值卡片（活跃无人机、Kafka 吞吐、运行时长）均为 22px。添加 `class="card-value big"` 后字号一致。

3. **全链路同步**：HTML→JS→WebSocket 服务端→仿真核心→Schema 定义→单元测试，6 层全部同步，`grep` 确认无 `redis_msg_per_sec` / `redis-tp` / `chart-redis` / `chartRedis` 残留引用。

### 汇总

- 新建文件：0
- 修改文件：9

---

## 2026-07-23 — 环境管理精简：移除 MySQL + ATC 集群/ES 环境配置

### 修改清单

| 日期 | 文件 | 操作 | 状态 | 验证方式 |
|------|------|------|------|----------|
| 2026-07-23 | `web/pages/env.html` | 修改 | ✅ | 编辑弹窗仅保留 Redis/Kafka/达梦 三个分组 |
| 2026-07-23 | `web/static/js/env.js` | 修改 | ✅ | 移除 MySQL/ATC/ES 字段读写和当前激活信息展示 |
| 2026-07-23 | `database/env_manager.py` | 修改 | ✅ | `activate_env`/`get_current_config`/`import_from_env_py`/`_update_env_py` 全部移除 10 个废弃字段 |
| 2026-07-23 | `web/server.py` | 修改 | ✅ | `api_env_activate` 移除 MySQL 配置同步和连接重置逻辑 |
| 2026-07-23 | `database/db_manager.py` | 修改 | ✅ | SQLite DDL 删除 MySQL/ATC/ES 10列；移除迁移行；新增 `_migrate_drop_env_config_columns()` 表重建迁移 |
| 2026-07-23 | `database/mysql_db_manager.py` | 修改 | ✅ | MySQL DDL 删除 10 列；移除 `_ALTER_COLUMNS` 中 sim_env_config 条目；新增 `_migrate_mysql_drop_env_config_columns()` 表重建迁移 |
| 2026-07-23 | `common/config.json` | 修改 | ✅ | 清理 MySQL/ATC/ES 字段，仅保留 Redis/Kafka/达梦 |

### 核心修复

1. **环境配置职责分离**：MySQL 数据库连接（平台自身存储）和 ATC 集群/ES 配置不再作为"可切换环境"的一部分。这些配置由 `env.py` / 环境变量统一管理，切换环境仅影响 Redis / Kafka / 达梦数据库三个外部依赖。避免因环境切换导致平台自身 MySQL 连接跳变。

2. **sim_env_config 表精简**：从 24 列缩减为 14 列（id, name, redis_ip/port/pwd, kafka_url/url2, is_default, dm_host/port/user/password/schema, created_at, updated_at），移除 10 个废弃列（mysql_*×5, atc_*×4, es_hosts×1）。

3. **平滑迁移**：SQLite 和 MySQL 均通过检测旧列→创建新表→复制数据→删旧表→重命名的方式完成表重建，保留已有的 Redis/Kafka/达梦环境配置数据不丢失。

4. **系统 MySQL 连接不受影响**：`common/config.py` 的 `MysqlConfig` 数据类和 `_load_mysql_config()` / `database/mysql_db_manager.py` 连接池逻辑完全保留，平台持久化功能正常。

### 汇总

- 新建文件：0
- 修改文件：7
