# Docker 容器化部署说明

## 目录结构

```
docker/
├── Dockerfile              # 镜像构建文件（Python 3.11-slim + Flask）
├── docker-compose.yml      # Docker Compose 服务编排
├── .env.example            # 环境变量模板（复制为 .env 后修改）
├── .dockerignore           # 构建排除规则
├── entrypoint.sh           # 容器入口脚本（环境检查 + 优雅退出）
├── env.conf                # [已弃用] 旧版 INI 配置参考
├── README.md               # 本文件
├── data/                   # JSON 数据文件目录（容器运行时不使用此占位目录）
└── logs/                   # 日志目录（容器运行时不使用此占位目录）
```

## 容器内目录结构

```
/app/
├── web/server.py           # Flask 主服务入口
├── env.py                  # 敏感配置（运行时挂载，不进镜像）
├── core/                   # 仿真核心（Kafka/Redis 客户端）
├── common/                 # 基础设施（配置、日志、模型）
├── database/               # 持久化层（MySQL/SQLite ORM）
├── services/               # 服务层（态势监控、API 桥接）
├── tools/                  # 工具层（数据生成、数据库客户端）
├── data/                   # JSON 数据文件（挂载宿主机目录）
├── data/db/                # SQLite 数据库文件（挂载宿主机目录）
├── logs/                   # 应用日志（挂载宿主机目录）
└── requirements.txt        # Python 依赖清单
```

## 快速部署

### 1. 创建宿主机目录

```bash
mkdir -p /opt/utm-simulator/{data,db,logs}
```

### 2. 准备 env.py

容器内 `env.py` 包含敏感凭证，通过卷挂载注入。确保宿主机 `/opt/atc_test_platfrom/env.py` 存在，或在 `.env` 中设置 `ENV_PY_PATH` 指向实际路径。

如果不想挂载 env.py，也可以在 `.env` 中完整填写所有 `UTM_*` 环境变量。

### 3. 配置环境变量

```bash
cd docker/
cp .env.example .env
vim .env  # 填入真实的 Redis/Kafka/MySQL/达梦 连接信息
```

### 4. 构建与启动

```bash
# 在项目根目录执行
docker compose -f docker/docker-compose.yml up -d --build

# 查看日志
docker compose -f docker/docker-compose.yml logs -f utm-simulator

# 停止
docker compose -f docker/docker-compose.yml down
```

### 5. 验证

```bash
# 健康检查
curl http://localhost:5000/api/sim/status

# 调度器状态
curl http://localhost:5000/api/scenes/health

# Web 控制台
open http://localhost:5000
```

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| **Redis** | | | |
| `UTM_REDIS_HOST` | ✅ | — | Redis 服务器地址 |
| `UTM_REDIS_PORT` | — | `21003` | Redis 端口 |
| `UTM_REDIS_PASSWORD` | ✅ | — | Redis 密码 |
| **Kafka** | | | |
| `UTM_KAFKA_URL` | ✅ | — | Kafka bootstrap 地址 |
| `UTM_KAFKA_URL2` | — | 空 | 双集群镜像写入地址 |
| **MySQL** | | | |
| `UTM_MYSQL_HOST` | — | 空 | MySQL 地址（留空仅写 SQLite） |
| `UTM_MYSQL_PORT` | — | `3306` | MySQL 端口 |
| `UTM_MYSQL_USER` | — | 空 | MySQL 用户名 |
| `UTM_MYSQL_PASSWORD` | — | 空 | MySQL 密码 |
| `UTM_MYSQL_DB` | — | `utm_simulator` | MySQL 库名 |
| **达梦** | | | |
| `UTM_DM_HOST` | — | `10.165.32.217` | 达梦数据库地址 |
| `UTM_DM_PORT` | — | `5236` | 达梦端口 |
| `UTM_DM_USER` | — | `SYSDBA` | 达梦用户名 |
| `UTM_DM_PASSWORD` | — | 空 | 达梦密码 |
| `UTM_DM_SCHEMA` | — | `ATC_DKWRJ_TEST` | 达梦模式名 |
| **ATC** | | | |
| `UTM_ATC_BASE_URL` | — | `https://dkkgsit-test.testdolphin.com` | ATC 后端地址 |
| **服务** | | | |
| `FLASK_PORT` | — | `5000` | 宿主机映射端口 |
| `UTM_LOG_FORMAT` | — | `simple` | 日志格式（simple/json/空=双输出） |
| `UTM_VERBOSE` | — | `0` | 详细日志开关（调试时设为 1） |
| **路径** | | | |
| `ENV_PY_PATH` | — | `/opt/atc_test_platfrom/env.py` | env.py 挂载路径 |
| `DATA_PATH` | — | `/opt/utm-simulator/data` | JSON 数据文件路径 |
| `DB_PATH` | — | `/opt/utm-simulator/db` | SQLite 数据库路径 |
| `LOG_PATH` | — | `/opt/utm-simulator/logs` | 日志持久化路径 |

## 数据持久化

| 宿主机路径 | 容器路径 | 内容 |
|-----------|---------|------|
| `${DATA_PATH}` | `/app/data` | JSON 场景文件、模板 |
| `${DB_PATH}` | `/app/data/db` | SQLite 数据库文件 |
| `${LOG_PATH}` | `/app/logs` | 应用日志 |

## 升级注意事项

1. **更新代码**：`docker compose -f docker/docker-compose.yml up -d --build` 即可重建镜像
2. **env.py 变更**：修改宿主机 env.py 后重启容器生效
3. **数据不丢失**：data/ db/ logs/ 目录映射到宿主机，镜像重建不影响数据
4. **代码和SQLite数据已分离**：SQLite 存储在 `/app/data/db/`（挂载宿主机），Python 代码在镜像层，不再有命名卷缓存问题
