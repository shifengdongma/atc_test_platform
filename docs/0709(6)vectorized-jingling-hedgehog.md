# MySQL 持久化迁移方案

## Context

当前项目存在以下持久化问题：
1. **config.json 双文件不一致**：Web UI 写 `utm_simulator/config.json`，`load_config()` 读 `common/config.json`，配置保存形同虚设
2. **SQLite 单机限制**：`sim_env_config`（环境配置）和 `sim_json_files`（JSON文件内容）存储在 SQLite，不便于多实例共享和备份
3. **MySQL 已部分集成但链路脆弱**：`log_streamer.py` 已通过 `mysqldbclient.py` 写 MySQL 日志表，但 `MysqlDbClient` 依赖 `atc_api_autotest/env.py` 的硬编码凭据，Docker 注入的 `UTM_MYSQL_*` 环境变量未被消费

目标：将环境配置和 JSON 文件内容持久化到 MySQL，统一配置读写路径，修复 `mysqldbclient.py` 的环境变量支持。

## 实施方案

### Step 1: 强化 MysqlDbClient — 支持 UTM_MYSQL_* 环境变量

**文件**: `atc_api_autotest/api_tools/mysqldbclient.py`

- 修改 `__init__`：当 `env.py` 导入失败或参数为默认值时，fallback 读取 `os.environ.get("UTM_MYSQL_*")`
- 同时尝试从 `utm_simulator/env.py` 导入（为未来统一做准备）

### Step 2: 添加 MySQL 配置到 utm_simulator/env.py

**文件**: `utm_simulator/env.py`

追加 MySQL 连接配置：
```python
MYSQL_HOST = "10.165.32.147"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "mysql_mC2n2h"
MYSQL_DATABASE = "utm_simulator"
MYSQL_CHARSET = "utf8mb4"
```

### Step 3: 创建 `database/mysql_db_manager.py` — MySQL CRUD 适配层

**新建文件**: `database/mysql_db_manager.py`

提供与 `db_manager.py` 一致的接口（`query`, `query_one`, `query_all`, `insert`, `update`, `delete`, `init_tables`），底层用 `mysqldbclient.MysqlDbClient`，带**优雅降级**：MySQL 不可用时自动 fallback 到 SQLite `db_manager`。

关键设计：
- 单例连接池（避免每次调用都 connect/close）
- `init_tables()` 自动创建 MySQL 表（DDL 从 SQLite 语法转为 MySQL）
- 所有函数签名与 `db_manager.py` 保持一致（`table`, `where`, `params`）
- 参数占位符自动从 `?` 转换为 `%s`

### Step 4: 更新 `database/json_data_manager.py` — 数据库迁移

**文件**: `database/json_data_manager.py`

- 将 `from db_manager import ...` 替换为 `from mysql_db_manager import ...`（fallback 机制已内置）
- 表名常量 `TABLE = "sim_json_files"` 保持不变
- 所有 CRUD 函数签名不变，内部调用自动走 MySQL/SQLite fallback

### Step 5: 更新 `database/env_manager.py` — 环境配置迁移

**文件**: `database/env_manager.py`

- 将 `from db_manager import ...` 替换为 `from mysql_db_manager import ...`
- 重写 `set_default()`（当前用 raw sqlite3 连接）为使用 `mysql_db_manager.update()`
- 修复 `_CONFIG_JSON` 指向 `common/config.json`（已是正确路径，保持不变）
- `activate_env()` 继续写 `common/config.json` 作为文件缓存兜底

### Step 6: 修复 web_server.py config.json 写入路径

**文件**: `utm_simulator/web_server.py`

- `api_save_config()` (line ~808): 将 `cfg_path` 从 `utm_simulator/config.json` 改为 `common/config.json`
- 路径计算：`os.path.join(_root, "..", "common", "config.json")`

### Step 7: 迁移现有 SQLite 数据到 MySQL

**新建文件**: `database/migrate_to_mysql.py`

一次性脚本：读取 SQLite 中 `sim_env_config` 和 `sim_json_files` 的全部记录，写入 MySQL 对应表。

## 涉及文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `atc_api_autotest/api_tools/mysqldbclient.py` | 修改 | 支持 UTM_MYSQL_* 环境变量 fallback |
| `utm_simulator/env.py` | 修改 | 追加 MYSQL_* 配置 |
| `database/mysql_db_manager.py` | **新建** | MySQL CRUD 适配层 + SQLite 自动降级 |
| `database/migrate_to_mysql.py` | **新建** | 一次性数据迁移脚本 |
| `database/json_data_manager.py` | 修改 | db_manager → mysql_db_manager |
| `database/env_manager.py` | 修改 | db_manager → mysql_db_manager + 重写 set_default() |
| `utm_simulator/web_server.py` | 修改 | config.json 保存路径修正 |

**不改动的文件**：
- `database/log_streamer.py` — 已正确使用 MySQL，保持不变
- `common/config.py` — 已正确读取 `common/config.json`，保持不变
- 所有前端文件 — 不变

## 验证方式

1. `python database/mysql_db_manager.py` — 独立测试 MySQL 连接 + 建表 + CRUD
2. `python database/migrate_to_mysql.py` — 执行迁移，验证条数一致
3. `conda run -n utm python -c "from database.mysql_db_manager import *; init_tables(); print('OK')"` — 语法 + 导入验证
4. 启动 Web 服务 → 环境管理页 → 新建/编辑/激活 → 重启服务 → 验证配置持久化
5. 数据管理页 → 上传/编辑 JSON → 验证文件内容持久化
