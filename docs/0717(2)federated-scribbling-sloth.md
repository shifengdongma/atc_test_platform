# 两套 MySQL 环境配置方案

## 背景

系统需要在两个环境中运行，连接不同的 MySQL 地址：
- **本地 Windows 开发**：`127.0.0.1:3306`
- **Linux Docker 部署**：`1Panel-mysql-Jdmq:3306`（同服务器的 1Panel MySQL 容器）

两套环境凭据相同（`root` / `mysql_mC2n2h`），仅 `MYSQL_HOST` 不同。

## 现有机制分析

`env.py` 文件已在 `.gitignore` 中（`**/env.py`），不提交仓库。每个环境维护自己的 `env.py`。

`config.py` 的 `_load_mysql_config()` 已有完整的优先级链：
1. 环境变量 `UTM_MYSQL_*`（最高优先级）
2. `utm_simulator/env.py` 的 `MYSQL_*` 变量
3. `atc_api_autotest/env.py` 的 `MYSQL_*` 变量（回退）
4. 默认值（`configured=False`，调用方跳过 MySQL）

Docker 部署通过 `docker-compose.yml` 注入 `UTM_MYSQL_*` 环境变量覆盖 `env.py`，且 `entrypoint.sh` 已有完整的 MySQL 诊断逻辑。

**结论：机制已完备，只需修正配置值。**

## 修改清单

### 1. `docker/.env.example` — 更新 Docker 默认 MySQL 配置

- `UTM_MYSQL_HOST` → `1Panel-mysql-Jdmq`（Docker 网络别名）
- `UTM_MYSQL_USER` → `root`
- `UTM_MYSQL_PASSWORD` → `mysql_mC2n2h`
- 添加注释：说明本地开发与 Docker 部署的 host 差异

### 2. `docker/docker-compose.yml` — 设置合理的 Docker 默认值

将 MySQL 环境变量空默认值改为有效默认值：
- `UTM_MYSQL_HOST` 默认 `1Panel-mysql-Jdmq`
- `UTM_MYSQL_USER` 默认 `root`
- `UTM_MYSQL_PASSWORD` 默认 `mysql_mC2n2h`
- `UTM_MYSQL_DB` 默认 `utm_simulator`

### 3. 本地 `utm_simulator/env.py` — 更新为本地 MySQL 配置

（gitignored 文件，直接修改本地副本）
- `MYSQL_HOST = "127.0.0.1"`
- `MYSQL_USER = "root"`
- `MYSQL_PASSWORD = "mysql_mC2n2h"`

### 4. 本地 `atc_api_autotest/env.py` — 同步更新 MySQL 配置

（gitignored 文件，直接修改本地副本）
- 同上 MySQL 凭据更新
- 达梦配置保持不变

## 工作原理

```
本地 Windows:  env.py (MYSQL_HOST=127.0.0.1) → config.py → 连接 127.0.0.1:3306 ✓
Docker Linux:  env.py (MYSQL_HOST=127.0.0.1) → UTM_MYSQL_HOST=1Panel-mysql-Jdmq 覆盖 → 连接 1Panel-mysql-Jdmq:3306 ✓
```

Docker 中环境变量 `UTM_MYSQL_HOST` 优先级高于 `env.py`，覆盖后连接 Docker 网络中的 MySQL 容器。本地无环境变量，直接使用 `env.py` 中的 `127.0.0.1`。

## 验证

1. **本地 Windows 验证**：启动 `web_server.py`，检查终端输出 `[mysql_db_manager] MySQL 连接成功`
2. **数据管理验证**：打开 Web 控制台 → "数据管理" → 确认文件列表正常显示
3. **Docker 验证**：`docker compose up -d` → `docker logs utm-simulator` → 确认 `✓ MySQL 连接成功 (1Panel-mysql-Jdmq:3306)`
