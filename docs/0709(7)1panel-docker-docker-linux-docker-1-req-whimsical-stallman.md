# Docker 容器化部署配置更新计划

## Context

当前项目 Docker 配置存在若干问题，导致无法正确通过 Docker 部署到 Linux 服务器。主要问题包括：环境变量名称与 `common/config.py` 不匹配、pip 安装分两步执行、缺少 `.dockerignore` 和 `.env.example`、数据库未持久化等。用户希望通过 1Panel 面板在 Linux 服务器上以 Docker 容器方式部署该项目。

---

## 修改文件清单（共 8 个文件）

### 1. `utm_simulator/requirements.txt` — 合并所有 Python 依赖

**现状**：只有 7 个核心包，缺少 Web 服务所需的 5 个包 + `requests`
**修改**：追加以下 6 个包到现有文件末尾：

```
flask>=3.0
flask-socketio>=5.3
pydantic>=2.0
pymysql>=1.1
openpyxl>=3.1
requests>=2.28.0
```

### 2. `docker/Dockerfile` — 合并 pip 安装 + 添加 PYTHONPATH

**修改点**：

**2a.** 删除第 28-34 行的第二个 `RUN pip install`（Flask/WebSocket/pydantic/pymysql/openpyxl 的内联安装），只保留第一个 `COPY requirements.txt` + `RUN pip install -r`，注释改为：

```dockerfile
# ── 安装 Python 依赖（一次性从 requirements.txt 安装全部依赖）──
COPY utm_simulator/requirements.txt /app/utm_simulator/requirements.txt
RUN pip install --no-cache-dir -r /app/utm_simulator/requirements.txt
```

**2b.** 在 `ENV FLASK_PORT=5000` 后新增一行：

```dockerfile
ENV PYTHONPATH=/app
```

这确保 Python 解释器能找到 `/app` 下的所有模块（`common/`、`database/`、`services/` 等），作为 `web_server.py` 中 `sys.path` 手动设置的补充保障。

### 3. `docker/docker-compose.yml` — 修复环境变量名、端口、卷映射

**3a. 关键修复：环境变量名 `UTM_REDIS_IP` → `UTM_REDIS_HOST`**

`common/config.py` 第 165 行通过 `_env_str("REDIS_HOST")` 读取环境变量，即查找 `UTM_REDIS_HOST`。当前 docker-compose.yml 设置的 `UTM_REDIS_IP` 不会被 `config.py` 识别，导致配置回退到 `env.py` 默认值。需要改为：

```yaml
- UTM_REDIS_HOST=${UTM_REDIS_HOST}
```

**3b. Redis 端口默认值 `26379` → `21003`**

与 `utm_simulator/env.py` 中的实际部署端口保持一致：

```yaml
- UTM_REDIS_PORT=${UTM_REDIS_PORT:-21003}
```

**3c. 数据库持久化：使用 Docker 命名卷**

当前没有为 `/app/database` 配置卷，容器重建后 `data.db` 会丢失。由于 `database/` 目录同时包含 Python 源文件（`db_manager.py` 等）和运行时数据文件（`data.db`），不能简单用 bind mount（会掩盖容器内的 `.py` 文件）。

**方案**：使用 **Docker 命名卷（named volume）**。命名卷在首次启动时会自动用容器内的内容初始化，既保留 `.py` 文件又持久化 `data.db`。

在 `volumes:` 列表中添加：
```yaml
# SQLite 数据库持久化（命名卷，自动继承容器内 .py 源文件）
- utm-database:/app/database
```

在文件末尾的 `networks:` 之后添加：
```yaml
volumes:
  utm-database:
```

**3d. 增加 `data/` 挂载（JSON 数据文件持久化）**

当前已有 `../data:/app/data`，保持不变。

### 4. `docker/entrypoint.sh` — 修复环境变量名

三处 `UTM_REDIS_IP` 全部改为 `UTM_REDIS_HOST`（第 31、32、40 行），与 `config.py` 保持一致。

### 5. `utm_simulator/web_server.py` — 添加 services/ai/ 到 sys.path

在第 32 行（`common/` 路径添加之后）新增：

```python
# services/ai/ 模块路径（AI 数据生成器）
_services_ai_path = os.path.join(_root, '..', 'services', 'ai')
if _services_ai_path not in sys.path:
    sys.path.insert(0, _services_ai_path)
```

这修复了 `import ai_data_gen as aig` 时找不到模块的问题（该文件在 `/app/services/ai/ai_data_gen.py`，当前只添加了 `database/` 和 `common/` 到路径）。

### 6. `.dockerignore`（项目根目录，新建）

将 `docker/.dockerignore` 的内容复制到项目根目录 `.dockerignore`。Docker 构建上下文是项目根目录（`context: ..`），只会读取根目录的 `.dockerignore`，`docker/.dockerignore` 不会被自动读取。

内容与 `docker/.dockerignore` 一致，已覆盖版本控制文件、IDE 配置、Python 缓存、敏感配置、归档文件等。

### 7. `docker/.env.example`（新建）

创建环境变量模板文件，供用户复制为 `.env` 后填入真实值：

```properties
# ── 镜像版本 ─────────────────────────────────────
TAG=latest

# ── 服务端口 ─────────────────────────────────────
FLASK_PORT=5000

# ── Redis 连接 ───────────────────────────────────
UTM_REDIS_HOST=dolphin-test.kedacom.com
UTM_REDIS_PORT=21003
UTM_REDIS_PASSWORD=your_redis_password_here

# ── Kafka 连接 ────────────────────────────────────
UTM_KAFKA_URL=10.165.19.213:30011
UTM_KAFKA_URL2=

# ── MySQL 连接 ────────────────────────────────────
UTM_MYSQL_HOST=10.165.32.147
UTM_MYSQL_PORT=3306
UTM_MYSQL_USER=utm
UTM_MYSQL_PASSWORD=your_mysql_password_here
UTM_MYSQL_DB=utm_simulator

# ── ATC 后端 ─────────────────────────────────────
UTM_ATC_BASE_URL=https://dkkgsit-test.testdolphin.com

# ── env.py 挂载路径（可选，不用 env.py 则留空）───
ENV_PY_PATH=
```

### 8. `docker/README.md` — 更新环境变量表

- `UTM_REDIS_IP` → `UTM_REDIS_HOST`
- Redis 端口默认值 `26379` → `21003`
- 新增 `UTM_REDIS_HOST` 行（必填），替换原 `UTM_REDIS_IP` 行

---

## 部署时需要提供的信息

### 环境变量 — 哪些占位符需要替换为真实值

以下变量需要填入你的 Linux 服务器对应的实际连接信息：

| 变量 | 当前值（来自 `utm_simulator/env.py`） | 说明 |
|------|--------------------------------------|------|
| `UTM_REDIS_HOST` | `dolphin-test.kedacom.com` | Redis 地址 |
| `UTM_REDIS_PORT` | `21003` | Redis 端口 |
| `UTM_REDIS_PASSWORD` | （见 env.py） | Redis 密码 |
| `UTM_KAFKA_URL` | `10.165.19.213:30011` | Kafka 地址 |
| `UTM_KAFKA_URL2` | （可选） | 双集群镜像 Kafka |
| `UTM_MYSQL_HOST` | `10.165.32.147` | MySQL 地址 |
| `UTM_MYSQL_PORT` | `3306` | MySQL 端口 |
| `UTM_MYSQL_USER` | `utm` | MySQL 用户名 |
| `UTM_MYSQL_PASSWORD` | （见 env.py） | MySQL 密码 |
| `UTM_MYSQL_DB` | `utm_simulator` | MySQL 数据库名 |
| `FLASK_PORT` | `5000` | 宿主机映射端口 |

### 本地文件夹卷映射

在 Linux 服务器上，建议创建统一的持久化目录：

```bash
sudo mkdir -p /opt/utm-simulator/{data,logs}
```

| 容器内路径 | 用途 | 持久化方式 |
|-----------|------|-----------|
| `/app/database` | SQLite 数据文件（data.db + Python 源文件） | **Docker 命名卷** `utm-database`（自动管理，无需手动创建目录） |
| `/app/utm_simulator/data` | Web 运行时数据 | 宿主目录 `/opt/utm-simulator/data` |
| `/app/data` | JSON 数据文件 | 宿主目录 `/opt/utm-simulator/app-data` 或使用默认的相对路径 |
| `/app/utm_simulator/logs` | 应用日志 | 宿主目录 `/opt/utm-simulator/logs` |
| `/app/utm_simulator/env.py` | 敏感配置文件（可选） | 如果不用环境变量，挂载宿主机上的 env.py 文件 |

---

## 1Panel 操作指南

### 方式一：编排模板（推荐，最简单）

1. 登录 1Panel，进入 **容器** → **编排** → **创建编排模板**
2. 将修改后的 `docker/docker-compose.yml` 全部内容粘贴到编辑器中
3. 在编排模板的**环境变量**区域，填写上述表格中的所有变量和值
4. 在**卷**配置区域，将相对路径改为绝对路径：
   - `./data` → `/opt/utm-simulator/data`
   - `../data` → `/opt/utm-simulator/app-data`
   - `./logs` → `/opt/utm-simulator/logs`
   - `utm-database`（命名卷，保持不动）
   - 如果不使用 env.py 文件挂载，删除 `ENV_PY_PATH` 对应的那行卷映射
5. 点击**部署**

### 方式二：单容器创建

如果不想用编排模板，也可以直接创建容器：

1. 先在服务器上构建镜像：
   ```bash
   cd /path/to/project
   docker build -t utm-simulator:latest -f docker/Dockerfile .
   ```
2. 在 1Panel 进入 **容器** → **创建容器**
3. 镜像选择 `utm-simulator:latest`
4. 端口映射：`5000:5000`
5. 在**环境变量**中逐一添加上述表格中的变量
6. 在**卷**中添加挂载关系
7. **命令**设置为：`python web_server.py`
8. 点击**确认**

### 1Panel 注意事项

- 1Panel 的编排模板本质上就是 `docker compose`，会自动处理命名卷的创建
- 数据库命名卷 `utm-database` 由 Docker 自动管理，在 1Panel 的**容器 → 卷**页面可以看到
- 如果你的 Linux 服务器无法直接访问 `dolphin-test.kedacom.com` 这类内网地址，需要确认服务器网络可达
- 容器日志可以在 1Panel 的**容器**列表中找到 `utm-simulator`，点击**日志**查看
- 首次部署后访问 `http://<服务器IP>:5000` 验证 Web 控制台是否正常

---

## 实施顺序

1. `utm_simulator/requirements.txt` — 追加 6 个包
2. `utm_simulator/web_server.py` — 添加 `services/ai/` 到 sys.path
3. `docker/Dockerfile` — 删除第二个 pip install + 添加 PYTHONPATH
4. `docker/docker-compose.yml` — 修复环境变量名、端口、添加命名卷
5. `docker/entrypoint.sh` — 修复 `UTM_REDIS_IP` → `UTM_REDIS_HOST`
6. `.dockerignore`（项目根，新建）— 复制 docker/.dockerignore 内容
7. `docker/.env.example`（新建）— 创建环境变量模板
8. `docker/README.md` — 更新文档中的变量名和默认值

## 验证方式

修改完成后，在本地执行构建测试：

```bash
# 在项目根目录构建镜像（不会真正启动，只验证构建过程无错误）
docker build -t utm-simulator:test -f docker/Dockerfile .

# 如果本地有 Docker，验证容器能启动
docker run --rm -p 5000:5000 -e UTM_REDIS_HOST=dolphin-test.kedacom.com -e UTM_REDIS_PORT=21003 -e UTM_REDIS_PASSWORD=xxx -e UTM_KAFKA_URL=10.165.19.213:30011 utm-simulator:test

# 验证健康检查
curl http://localhost:5000/api/sim/status
```
