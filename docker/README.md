# Docker 容器化部署说明

## 目录结构

```
docker/
├── Dockerfile              # 镜像构建文件（Python 3.11-slim + Flask + utm_simulator）
├── docker-compose.yml      # Docker Compose 服务编排
├── .env.example            # 环境变量模板（复制为 .env 后修改）
├── .dockerignore           # 构建排除规则
├── entrypoint.sh           # 容器入口脚本（环境检查 + 优雅退出）
├── env.conf                # [已弃用] 旧版 INI 配置参考
├── data/                   # SQLite 数据持久化目录（自动创建）
└── logs/                   # 日志持久化目录（自动创建）
```

## 快速部署

### 1. 准备环境变量

```bash
cd docker/
cp .env.example .env
# 编辑 .env，填入真实的 Redis/Kafka/MySQL 连接信息
vim .env
```

### 2. 准备 env.py

容器内的 `env.py` 包含敏感凭证，不在代码仓库中。需要从宿主机挂载或通过环境变量注入。

**方式一：挂载宿主机文件**（推荐）

```bash
# 将线上 env.py 拷贝到 docker/ 目录
cp /path/to/your/env.py docker/env.py
```

docker-compose 会自动挂载 `./env.py`（即 `docker/env.py`）到容器内。

**方式二：环境变量注入**

不挂载 env.py，而是在 `.env` 中完整填写 `UTM_*` 变量。代码中的 `config.py` 会优先读取环境变量。

### 3. 构建与启动

```bash
# 在项目根目录执行
docker compose -f docker/docker-compose.yml up -d --build

# 查看日志
docker compose -f docker/docker-compose.yml logs -f

# 停止
docker compose -f docker/docker-compose.yml down
```

### 4. 验证

```bash
# 健康检查
curl http://localhost:5000/api/sim/status

# Web 控制台
open http://localhost:5000
```

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `UTM_REDIS_HOST` | ✅ | — | Redis 服务器地址 |
| `UTM_REDIS_PORT` | — | `21003` | Redis 端口 |
| `UTM_REDIS_PASSWORD` | ✅ | — | Redis 密码 |
| `UTM_KAFKA_URL` | ✅ | — | Kafka bootstrap 地址 |
| `UTM_KAFKA_URL2` | — | 空 | 双集群镜像写入地址 |
| `UTM_MYSQL_HOST` | — | 空 | MySQL 地址（留空仅写 SQLite） |
| `UTM_MYSQL_PORT` | — | `3306` | MySQL 端口 |
| `UTM_MYSQL_USER` | — | 空 | MySQL 用户名 |
| `UTM_MYSQL_PASSWORD` | — | 空 | MySQL 密码 |
| `UTM_MYSQL_DB` | — | `utm_simulator` | MySQL 库名 |
| `UTM_ATC_BASE_URL` | — | `https://dkkgsit-test.testdolphin.com` | ATC 后端地址 |
| `FLASK_PORT` | — | `5000` | 宿主机映射端口 |
| `ENV_PY_PATH` | — | `./env.py` | env.py 挂载路径 |

## 注意事项

1. **构建上下文**：Dockerfile 在项目根目录构建（`context: ..`），允许 COPY 多个子模块
2. **env.py 排除**：`.dockerignore` 排除了所有 `env.py`，敏感配置不进入镜像
3. **数据持久化**：`data/` 和 `logs/` 目录映射到宿主机，容器重建不丢失
4. **时钟同步**：挂载了 `/etc/localtime` 确保容器与宿主机时间一致
5. **优雅退出**：`entrypoint.sh` 捕获 SIGTERM，`docker stop` 10s 内完成关闭
