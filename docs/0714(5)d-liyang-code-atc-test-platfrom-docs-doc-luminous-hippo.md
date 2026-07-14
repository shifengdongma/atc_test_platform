# Docker 数据库连接问题 — 诊断增强与修复方案

## 问题上下文

用户在 1Panel 上部署 ATC/UTM 自动化测试平台容器，数据库连接持续失败。
日志来源：`docs/docker报错日志.md`

## 根因分析（已验证）

### 根因 1：MySQL 连接 127.0.0.1 → 环境变量未配或 env.py 含本地开发值

- `mysql_db_manager.py:_create_mysql_client()` → `config.py:load_mysql_config()` 获取配置
- docker-compose.yml 中 `UTM_MYSQL_HOST=${UTM_MYSQL_HOST:-}` 默认为空
- 当 `UTM_MYSQL_HOST` 为空时，回退读取挂载的 `env.py`
- 若 `env.py` 中 `MYSQL_HOST="127.0.0.1"`（本地开发值），`configured=True`，容器会尝试连接 127.0.0.1:3306
- 容器内无 MySQL → Connection Refused
- **缺乏诊断日志**，无法判断配置来源

### 根因 2：AttributeError `query_available_routes` → 命名卷缓存旧代码（**核心问题**）

- docker-compose.yml 第 58 行：`utm-database:/app/database` 是 Docker **命名卷**
- 命名卷首次创建时从镜像复制内容，之后**持久化保留，永不再更新**
- `json_data_manager.py` 在 `/app/database/` 下，`query_available_routes` 函数（第 676 行）是新增的
- 镜像重建后，卷中**旧代码覆盖镜像新代码**
- **这就是为什么重建容器多次仍然出错的原因**

### 根因 3：达梦 -70089 → libssl1.1/libcrypto1.1 可能未完整安装

- dmPython Linux .so 动态链接 `libssl.so.1.1` + `libcrypto.so.1.1`
- Dockerfile 仅验证 `libssl.so.1.1`，未验证 `libcrypto.so.1.1`
- 1Panel 构建环境网络可能不稳定，apt 从 bullseye 源拉取失败
- 需要增强验证 + `LD_LIBRARY_PATH`

---

## 修改计划

### 1. `common/config.py` — 增加 MySQL 配置来源追踪日志

在 `_load_mysql_config()` 函数中增加 print 诊断：
- 记录尝试读取的每个 env.py 路径及是否找到 MYSQL_HOST
- 记录每个 UTM_MYSQL_* 环境变量的覆盖情况
- 最终输出：`host/port/user/database/configured/SOURCE`

### 2. `database/mysql_db_manager.py` — 增强连接决策日志

在 `_create_mysql_client()` 中：
- 打印 `configured/host/port/database` 信息
- `configured=False` 时明确打印"跳过 MySQL 连接"
- 存储最终连接目标信息到模块变量，供 `_get_client()` 错误路径使用

### 3. `database/json_data_manager.py` — 达梦连接诊断增强

在 `_get_dm_client()` 中增加：
- 使用 `ctypes.CDLL` 直接测试 libssl.so.1.1 和 libcrypto.so.1.1 加载
- 打印 `LD_LIBRARY_PATH`
- 打印 dmdbclient.py 加载路径
- 达梦连接失败时打印完整 traceback

### 4. `docker/Dockerfile` — 加固 libssl1.1 安装

- 拆分 libssl1.1 安装为独立 RUN 层（便于缓存和排查）
- 验证 **同时检查** `libssl.so.1.1` + `libcrypto.so.1.1`
- 添加 `dpkg -L libssl1.1` 确认包文件存在
- 添加 `ENV LD_LIBRARY_PATH` 确保 dmPython 能找到 .so 文件

### 5. `docker/entrypoint.sh` — 启动时全量诊断

增加启动诊断区块：
- MySQL：检查 `UTM_MYSQL_HOST` 环境变量是否设置
- 命名卷：`grep` 检查 `json_data_manager.py` 是否包含 `query_available_routes`
- 达梦：`ldconfig -p` 检查 `libssl.so.1.1` 和 `libcrypto.so.1.1`
- Python import 检查：直接尝试 import 并验证关键函数

### 6. `docker/docker-compose.yml` — 添加关键注释

在 `utm-database` 卷上方添加警告注释，说明命名卷会缓存旧代码，更新代码需手动删除卷。

---

## 验证方式

1. 重新构建镜像：`docker compose -f docker/docker-compose.yml build --no-cache`
2. 启动容器后查看 entrypoint.sh 输出，确认所有诊断检查结果
3. 查看容器日志确认 MySQL 配置来源和决策路径
4. 确认达梦连接不再报 -70089
5. 确认 `/api/data/db/routes` 接口不再报 AttributeError

---

## 1Panel 操作指南（给用户）

### A. 修复命名卷缓存旧代码（**必须先做！**）

在 1Panel 宿主机终端执行：

```bash
# 1. 停止容器
docker compose -f /opt/atc_test_platfrom/docker/docker-compose.yml down

# 2. 备份 SQLite 数据（可选但推荐）
docker run --rm -v atc_test_platfrom_utm-database:/source \
  -v /opt/utm-simulator/backup:/backup \
  alpine cp /source/data.db /backup/data.db.$(date +%Y%m%d_%H%M%S)

# 3. 删除命名卷（⚠ 清除旧代码）
docker volume rm atc_test_platfrom_utm-database

# 4. 重新构建镜像（--no-cache 确保完全重建）
docker compose -f /opt/atc_test_platfrom/docker/docker-compose.yml build --no-cache

# 5. 启动容器
docker compose -f /opt/atc_test_platfrom/docker/docker-compose.yml up -d

# 6. 查看日志确认诊断结果
docker logs -f utm-simulator
```

### B. 配置 MySQL 环境变量

在 1Panel 容器编排的 `.env` 文件（或环境变量面板）中设置：

```
UTM_MYSQL_HOST=你的MySQL容器名或IP   # 例如 1panel-mysql-Jdmq 或 10.165.32.147
UTM_MYSQL_PORT=3306
UTM_MYSQL_USER=utm用户名
UTM_MYSQL_PASSWORD=utm密码
UTM_MYSQL_DB=utm_simulator
```

**不要留空！** 留空会回退到 env.py 中的 `127.0.0.1`（本地开发值）。

### C. 如果达梦仍有 -70089 错误

构建日志中检查是否有 `libssl.so.1.1` 安装失败的信息。如果构建时网络不通：
1. 确保 1Panel 宿主机能访问 `mirrors.aliyun.com`
2. 如果阿里云镜像不可达，将 Dockerfile 中的源改为 `http://deb.debian.org/debian`
