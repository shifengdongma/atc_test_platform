# MySQL 连接优化 + 移除 SQLite 降级 — 实施计划

## Context

当前 `database/mysql_db_manager.py` 存在两个问题：

1. **MySQL 连接每次加载过慢**：每次 CRUD 操作经过 `_get_client()` 时，每 30 秒执行一次 `conn.ping(reconnect=True)` + `SELECT 1` 健康检查（2 次网络往返）；首次连接时 `_ensure_mysql_tables()` 执行 SHOW TABLES + 逐个 CREATE TABLE + SHOW COLUMNS + ALTER TABLE（最多 15-20 次往返）；SSL 握手每次都执行；`connect_timeout=10s` 使失败等待过长。

2. **SQLite 降级导致数据分歧**：MySQL 连接异常时，连续失败 10 次后自动切换到 SQLite（`database/data.db`）。场景编排创建的任务写入 SQLite 后，MySQL 恢复时这些任务"消失"（数据在 SQLite 文件中），导致用户无法查看任务列表。且降级后的恢复路径实际是死代码（`_using_sqlite=True` 时 CRUD 函数从不调用 `_get_client()`，MySQL 永远不会被重试）。

**目标**：优化连接速度 + 彻底移除 SQLite 降级，MySQL 不可用时直接报错而非静默切换。

## 修改方案

### 方案概述

- 引入 `DBUtils.PooledDB` 连接池，替代手动单连接管理，利用 `ping=1` 自动校验连接
- 移除 30 秒健康检查 ping 逻辑（连接池自动处理）
- 添加 `_tables_verified` 标记，DDL 验证只执行一次
- SSL 改为可配置（`UTM_MYSQL_SSL=false` 可关闭）
- `connect_timeout` 从 10s 降到 5s
- 移除所有 SQLite 降级代码（约 150 行）：`_using_sqlite`、`_mark_mysql_failed/success`、`_get_sqlite_fn`、各 CRUD 函数中的 fallback 分支
- CRUD 函数在 MySQL 不可用时抛出 `RuntimeError`，由上层 `_safe_json` 装饰器转为 HTTP 500 响应

### 修改文件清单

#### 1. `utm_simulator/requirements.txt` — 添加依赖

在 `# 数据库` 段添加一行：
```
DBUtils>=3.0
```

#### 2. `common/config.py` — SSL 可配置

- `MysqlConfig` dataclass 添加 `use_ssl: bool = True` 字段
- `_load_mysql_config()` 读取 `UTM_MYSQL_SSL` 环境变量（`"false"/"0"/"no"` → 关闭）
- `return MysqlConfig(...)` 传入 `use_ssl=use_ssl`

#### 3. `database/mysql_db_manager.py` — 核心改造（主要文件）

**3a. 新增导入和变量**
- `from DBUtils.PooledDB import PooledDB`
- 新增：`_pool: Optional[PooledDB] = None`、`_tables_verified: bool = False`
- 删除：`_last_health_check`、`_HEALTH_CHECK_TTL`、`_using_sqlite`、`_mysql_fail_count`、`_MYSQL_FAIL_THRESHOLD`、`_mysql_success_count`、`_MYSQL_RECOVERY_THRESHOLD`、`_sqlite_functions`

**3b. 删除函数**
- `_get_sqlite_fn()`（第 54-71 行）
- `_mark_mysql_failed()`（第 74-88 行）
- `_mark_mysql_success()`（第 91-100 行）

**3c. `_create_mysql_client()` → `_create_pool()`**
- 使用 `PooledDB(creator=pymysql, mincached=1, maxcached=5, maxconnections=10, blocking=True, ping=1, ...)`
- `connect_timeout=5`（从 10 降低）
- SSL 根据 `cfg.use_ssl` 决定是否传 `{'ssl': {}}`
- 创建后 test_conn 验证可用性

**3d. 简化 `_get_client()`**
- 移除健康检查 TTL 逻辑（`_last_health_check` / ping / SELECT 1 块）
- 移除断线重连块（ping 失败后重新 `_create_mysql_client` 的逻辑）
- 连接从 `pool.connection()` 获取，`_tables_verified` 控制 DDL 只执行一次
- 断线恢复：依赖连接池的 `ping=1`，操作失败时设 `_mysql_client = None`，下次自动从池中获取新连接

**3e. `_try_reset_broken_connection()`**
- 增加 `_tables_verified = False` 重置

**3f. 更新所有 CRUD 函数**
- `client.conn.cursor()` → `client.cursor()`
- `client.conn.commit()` → `client.commit()`
- `client.conn.rollback()` → `client.rollback()`
- 移除每个函数开头的 `if _using_sqlite:` 分支
- 移除 `_mark_mysql_failed()` / `_mark_mysql_success()` 调用
- 移除 except 块中的 SQLite fallback 逻辑
- `client is None` 时 `raise RuntimeError("MySQL 不可用")`
- insert/update/delete 保留死锁重试（1213），重试耗尽后 raise

**3g. 简化 `init_tables()`**
- 移除 `_using_sqlite` 分支和 SQLite fallback
- 直接调用 `_ensure_mysql_tables()`

**3h. `_ensure_mysql_tables()`**
- `client.execute(ddl)` → `client.cursor().execute(ddl)` (因为 client 现在是 pymysql 连接，不再有 execute 封装方法)

#### 4. `database/migrate_to_mysql.py` — 适配新连接类型

- `client.cursor.execute(...)` → `cur = client.cursor(); cur.execute(...)`
- `client.conn.commit()` → `client.commit()`
- `client.conn.rollback()` → `client.rollback()`
- `client.host`/`client.port`/`client.database` → 使用 `_mysql_conn_target`

#### 5. `utm_simulator/web_server.py` — 优雅关闭适配

- 第 192-202 行关闭逻辑：`_mysql_client.close()` 改为归还连接到池

#### 6. `database/orchestrator.py` — 错误处理增强（可选）

- `_check_and_execute()` 中 `query()` 调用加 try/except，打印明确错误信息

## 不影响的部分

- `database/db_manager.py` — 保留不动（可能被独立使用）
- `database/json_data_manager.py` — 通过 `mysql_db_manager` 间接使用，接口不变
- `database/log_streamer.py` — 已有 try/except，适配新异常类型即可
- `database/env_manager.py` — 同上

## 验证方式

1. **启动测试**：`conda run -n utm python -c "from database.mysql_db_manager import init_tables, query_all; init_tables(); print(query_all('sim_scenes'))"`
   - 预期：连接成功，返回场景列表（可能为空）
2. **连接速度测试**：观察启动日志，首次连接应在 1-2 秒内完成（之前 5-10 秒）
3. **MySQL 不可用测试**：临时改错 MySQL 配置，调用 CRUD 函数应抛出 `RuntimeError` 而非静默切换到 SQLite
4. **场景编排 API 测试**：启动 web_server，访问 `/api/scenes`，应正常返回数据
5. **SSL 关闭测试**：设置 `UTM_MYSQL_SSL=false`，观察连接日志确认未使用 SSL
6. **`database/data.db` 不再生成**：MySQL 正常时不应有新的 SQLite 写入
