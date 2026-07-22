# 低空空管（ATC/UTM）仿真数据注入平台

> 服务于"海豚"（Dolphin）ATC 态势感知 Dashboard（`dkkgsit-test.testdolphin.com`）
>
> 通过场景文件注入和 Redis 计划插值向 Redis/Kafka 注入仿真数据，驱动 Dashboard 展示。

---

## 一、项目概述

本项目是一个低空空管仿真数据注入平台，核心能力包括：

- **场景文件注入**：从预生成的 JSON 场景文件向 Kafka 发射实时遥测数据
- **Redis 计划插值**：从 Redis 读取飞行计划航段，线性插值实时生成遥测
- **数据生成面板**：基础/单机/多机/批量四种数据生成模式
- **场景编排调度**：Cron 定时任务，自动执行场景注入
- **Web 可视化控制台**：环境管理、数据管理、数据生成、场景编排、仿真运行、系统日志
- **AI 集成接口**：大模型数据生成，支持 Claude Code / MCP 协议

---

## 二、核心功能

### 2.1 仿真数据注入

| 运行模式 | 入口 | 说明 |
|---------|------|------|
| **场景文件注入** (scene) | `tools/run_kafka_scene.py` | 按指定间隔从 JSON 场景文件发射遥测，支持 replace/align/preserve 三种时间戳模式 |
| **Redis 计划插值** (plan) | `tools/run_plan.py` | 从 Redis 读取飞行计划航段，线性插值实时生成遥测 |

### 2.2 Web 可视化控制台

启动方式：`.\start_web.ps1` 或 `python cli.py server`，浏览器访问 `http://localhost:5000`

- **环境管理**：配置多套 Redis、Kafka、数据库连接环境
- **数据管理**：上传/导入 JSON 数据文件，管理文件元数据
- **数据生成面板**（4 个 Tab）：
  - 基础生成：随机/网格/放射三种算法
  - 单机场景：航线飞行 / 偏离航路 / 状态变更
  - 多机场景：平行飞行 / 偏离(高级) / 碰撞预警 / 状态告警
  - 批量预设：11 个全国区域一键生成
- **场景编排**：Cron 定时场景任务，自动执行与停止
- **地图可视化**：Leaflet + 高德瓦片（国内秒加载）+ WGS-84 → GCJ-02 坐标转换
- **实时监控**：Chart.js 趋势图（无人机数量、Kafka 吞吐、运行时长）
- **系统日志**：运行日志实时捕获与展示

---

## 三、系统架构

### 3.1 分层架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         表示层 (Presentation)                      │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐   │
│  │  web/        │  │  cli.py          │  │  start_web.ps1    │   │
│  │  Flask 后端   │  │  命令行入口       │  │  Windows 启动脚本  │   │
│  │  + HTML/JS   │  │                  │  │                   │   │
│  └──────┬───────┘  └────────┬─────────┘  └───────────────────┘   │
└─────────┼───────────────────┼─────────────────────────────────────┘
          │                   │
┌─────────┼───────────────────┼─────────────────────────────────────┐
│         ▼                   ▼                      服务层          │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │  services/                                               │     │
│  │  ├── ai_integration.py      AI 数据生成集成              │     │
│  │  ├── situation_monitor.py   态势监控 (WebSocket)         │     │
│  │  ├── gateway_log_poller.py  TCP 网关日志轮询            │     │
│  │  ├── web_data_gen_bridge.py Web → 数据生成桥接          │     │
│  │  ├── sim_api_bridge.py      仿真 API 桥接               │     │
│  │  └── ai/ai_data_gen.py      大模型数据生成调用           │     │
│  └──────────────────────────────────────────────────────────┘     │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
┌─────────────────────────────┼─────────────────────────────────────┐
│                             ▼                      核心层          │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │  core/                                                   │     │
│  │  ├── sim_manager.py        仿真编排器 (scene + plan)     │     │
│  │  ├── redis_client.py       Redis 客户端                  │     │
│  │  ├── kafka_proc.py         Kafka 生产者/消费者           │     │
│  │  └── uav_identifiers.py    UAV ID 标识符管理             │     │
│  └──────────────────────────────────────────────────────────┘     │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
┌─────────────────────────────┼─────────────────────────────────────┐
│                             ▼                      持久化层        │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │  database/                                               │     │
│  │  ├── mysql_db_manager.py   MySQL CRUD (主数据库)         │     │
│  │  ├── db_manager.py         SQLite CRUD (降级备用)        │     │
│  │  ├── json_data_manager.py  JSON 文件元数据管理           │     │
│  │  ├── env_manager.py        环境配置 CRUD                 │     │
│  │  ├── orchestrator.py       Cron 场景编排调度器           │     │
│  │  └── log_streamer.py       实时日志流 (WebSocket推送)    │     │
│  └──────────────────────────────────────────────────────────┘     │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
┌─────────────────────────────┼─────────────────────────────────────┐
│                             ▼                      基础设施层      │
│  ┌──────────────────────────┴────────────────────────────────┐    │
│  │  common/                                                  │    │
│  │  ├── config.py            统一配置 (环境变量 + JSON)      │    │
│  │  ├── log_setup.py         结构化日志 (JSON + 控制台)     │    │
│  │  ├── schemas.py           数据模型 (TypedDict)           │    │
│  │  ├── validators.py        Pydantic 数据验证              │    │
│  │  └── exceptions.py        异常层次结构                   │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  tools/                         外部系统适配器            │    │
│  │  ├── dmdbclient.py              达梦数据库客户端         │    │
│  │  ├── mysqldbclient.py           MySQL 连接客户端         │    │
│  │  ├── iomp_api_common.py         IOMP 平台 API            │    │
│  │  ├── Jwt_Token_get.py           JWT 令牌管理             │    │
│  │  ├── iomp_core.py               IOMP 核心                │    │
│  │  ├── run_kafka.py               Kafka 单文件注入         │    │
│  │  ├── run_kafka_scene.py         Kafka 场景注入           │    │
│  │  ├── run_kafka_alive.py         Kafka 循环注入           │    │
│  │  ├── run_plan.py                Redis 计划插值           │    │
│  │  ├── create_data.py             基础数据生成             │    │
│  │  ├── create_data_scene.py       单场景数据生成           │    │
│  │  └── create_data_scenes.py      批量场景数据生成         │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐      ┌──────────────┐      ┌──────────┐
    │  Redis   │      │    Kafka     │      │  MySQL   │
    │  BIZ_DATA│      │ uav_runtime  │      │  utm_sim │
    │  :UAV_   │      │ _data/_trace │      │  ulator  │
    │  ROUTE   │      │              │      │          │
    │  :AIRSPACE│     │              │      │          │
    └──────────┘      └──────────────┘      └──────────┘
```

### 3.2 核心数据流

```
                        ┌──────────────────────┐
                        │  scene 模式           │
                        │  JSON 文件 → Kafka    │
                        └──────────┬───────────┘
                                   │
                        ┌──────────┴───────────┐
                        │  plan 模式            │
                        │  Redis → 插值 → Kafka │
                        └──────────┬───────────┘
                                   │ JSON 消息
                                   ▼
               ┌───────────────────────────┐
               │  Kafka uav_runtime_data   │
               │  (无人机实时遥测)          │
               └───────────┬───────────────┘
                           │ 下游 UTM 消费
                           ▼
               ┌───────────────────────────┐
               │   下游 UTM 引擎             │
               │  轨迹预测 + 冲突检测         │
               └───────────┬───────────────┘
                           │ 预测结果
                           ▼
               ┌───────────────────────────┐
               │  Kafka uav_runtime_trace  │
               │  ← 模拟器消费验证           │
               └───────────────────────────┘

               ┌───────────────────────────┐
               │  Redis BIZ_DATA:UAV_ROUTE │
               │  (Hash: uid → route JSON) │
               │  ← plan 模式读取           │
               └───────────────────────────┘
```

---

## 四、项目目录结构

```
atc_test_platfrom/
├── core/                          # 🚁 仿真核心层
│   ├── sim_manager.py             #   统一编排（scene + plan 模式）
│   ├── redis_client.py            #   Redis 客户端封装
│   ├── kafka_proc.py              #   Kafka 生产者/消费者封装
│   └── uav_identifiers.py         #   5000 架 UAV ID 标识符列表
│
├── common/                        # 📦 基础设施层
│   ├── config.py                  #   统一配置管理（环境变量 > JSON > env.py > 默认值）
│   ├── log_setup.py               #   结构化日志初始化
│   ├── schemas.py                 #   TypedDict 类型定义
│   ├── validators.py              #   Pydantic 数据校验器
│   └── exceptions.py              #   语义异常层次
│
├── database/                      # 🗄️ 持久化层
│   ├── mysql_db_manager.py        #   MySQL 管理器（pymysql 1.x + DBUtils 连接池）
│   ├── db_manager.py              #   SQLite 降级操作
│   ├── json_data_manager.py       #   JSON 文件管理 + 达梦航线查询
│   ├── env_manager.py             #   多环境配置 CRUD
│   ├── orchestrator.py            #   Cron 场景编排调度器
│   └── log_streamer.py            #   实时日志流（内存缓冲 + WS + MySQL 持久化）
│
├── services/                      # 🤖 服务层
│   ├── ai_integration.py          #   AI 集成点注册中心
│   ├── situation_monitor.py       #   态势监控采集器（SockJS + STOMP）
│   ├── gateway_log_poller.py      #   TCP 网关日志轮询
│   ├── web_data_gen_bridge.py     #   Web API → tools 脚本桥接
│   ├── sim_api_bridge.py          #   ATC API 桥接（JWT / 任务CRUD / 计划申报）
│   └── ai/                        #   AI 数据生成
│       └── ai_data_gen.py         #     大模型生成器（OpenAI 兼容 API）
│
├── tools/                         # 🔧 工具层（外部系统适配器 + 注入脚本）
│   ├── dmdbclient.py              #   达梦数据库客户端
│   ├── mysqldbclient.py           #   MySQL 连接客户端
│   ├── iomp_api_common.py         #   IOMP API 通用工具
│   ├── Jwt_Token_get.py           #   JWT 令牌获取
│   ├── iomp_core.py               #   IOMP 日志下载器
│   ├── run_kafka.py               #   Kafka 单文件注入器
│   ├── run_kafka_scene.py         #   Kafka 场景文件注入器（SceneEmitter）
│   ├── run_kafka_alive.py         #   Kafka 循环注入器
│   ├── run_plan.py                #   Redis 计划插值运行器（PlanRunner）
│   ├── create_data.py             #   基础数据生成
│   ├── create_data_scene.py       #   单机场景生成（线性插值 + 偏离）
│   └── create_data_scenes.py      #   综合场景工厂（11 子命令）
│
├── web/                           # 🌐 表示层
│   ├── server.py                  #   Flask + WebSocket 后端
│   ├── index.html                 #   主页
│   ├── pages/                     #   8 个功能页面
│   │   ├── env.html               #     环境管理
│   │   ├── data.html              #     数据管理
│   │   ├── generate.html          #     数据生成
│   │   ├── scene.html             #     场景编排
│   │   ├── run.html               #     仿真运行
│   │   ├── logs.html              #     系统日志
│   │   ├── config.html            #     配置管理
│   │   └── basicdata.html         #     基础数据
│   └── static/                    #   JS/CSS/Leaflet
│
├── data/                          # 📋 数据文件
│   ├── schemas/                   #   JSON Schema 定义（4 个）
│   ├── templates/                 #   场景模板（3 个 JSON）
│   ├── mock/                      #   运行时生成数据
│   └── uploads/                   #   用户上传
│
├── docker/                        # 🐳 Docker 容器化配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── entrypoint.sh
│
├── tests/                         # 🧪 单元测试
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_schemas.py
│   └── test_validators.py
│
├── docs/                          # 📚 文档
├── skills_hub/                    # 🎯 团队协作技能库（子模块）
├── cli.py                         # 🚀 统一 CLI 入口
├── env.py.example                 #   环境配置模板
├── requirements.txt               #   Python 依赖清单
├── start_web.ps1                  #   Windows 启动脚本
├── CLAUDE.md                      #   AI 编程规则
└── README.md                      #   本文件
```

---

## 五、环境要求与安装

### 5.1 基础环境

| 组件 | 版本/说明 |
|------|----------|
| Python | 3.11.15（`utm` Conda 环境） |
| Conda | `C:\ProgramData\anaconda3\Scripts\conda.exe` |
| Redis | 用于飞行计划（`BIZ_DATA:UAV_ROUTE`）和空域（`BIZ_DATA:AIRSPACE`）存储 |
| Kafka | 用于遥测数据（`uav_runtime_data`）和轨迹预测（`uav_runtime_trace`） |
| MySQL | 测试平台主数据库（`utm_simulator` 库），存储配置/文件/任务/日志 |
| 达梦数据库 | 可选，只读外部 ATC 系统，用于航线查询（需 `dmPython`） |
| Docker | 可选，容器化部署 |

### 5.2 安装步骤

```bash
# 1. 克隆仓库
git clone https://szgitlab.kedacom.com/atc_test/utm-simulator-develop.git
cd utm-simulator-develop

# 2. 创建并激活 Conda 环境
conda create -n utm python=3.11.15
conda activate utm

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置连接信息
# 复制模板并编辑 env.py，填写实际 Redis/Kafka 地址与密码
cp env.py.example env.py
# 或通过 Web 控制台环境管理页直接配置（保存到 common/config.json）

# 5. 配置 MySQL（如使用 Docker 部署则通过环境变量注入）
# 设置环境变量：UTM_MYSQL_HOST, UTM_MYSQL_PORT, UTM_MYSQL_USER, UTM_MYSQL_PASSWORD, UTM_MYSQL_DB

# 6. 验证安装
python cli.py check   # 检查 Redis/Kafka 连通性
python cli.py status  # 查看 Redis 中飞行计划数据量
```

### 5.3 Docker 部署（推荐生产环境）

```bash
cd /opt/utm-simulator-develop

# 首次构建并启动
docker compose -f docker/docker-compose.yml build --no-cache
docker compose -f docker/docker-compose.yml up -d

# 查看日志
docker logs -f utm-simulator
```

### 5.4 关键依赖

```
kafka-python>=2.0.2       # Kafka 生产者/消费者
redis>=4.5.0,<5.0.0       # Redis 客户端
Flask                     # Web 后端
Flask-SocketIO            # WebSocket 推送
pymysql==1.1.0            # MySQL 连接（严格锁定 1.x）
cryptography              # TLS/SSL 支持
pydantic                  # 数据校验
```

---

## 六、快速开始

### 6.1 启动 Web 控制台

```bash
conda activate utm

# 方式一：PowerShell 一键启动
.\start_web.ps1

# 方式二：CLI 启动
python cli.py server

# 浏览器访问 http://localhost:5000
```

### 6.2 场景文件注入

```bash
# 命令行直接注入
python tools/run_kafka_scene.py --file data/mock/scene.json --topic uav_runtime_data

# 场景目录批量注入
python tools/run_kafka_scene.py --scene data/mock/
```

### 6.3 Redis 计划插值

```bash
python tools/run_plan.py
```

### 6.4 数据生成

```bash
# 基础数据生成
python tools/create_data.py --count 60

# 单场景数据生成
python tools/create_data_scene.py --mode route --route-name "三河区航路"

# 批量场景数据生成
python tools/create_data_scenes.py --help
```

---

## 七、配置管理

### 7.1 配置优先级

`common/config.py` 采用多层配置加载策略（高→低）：

1. **环境变量**：`UTM_REDIS_HOST`、`UTM_KAFKA_URL` 等 `UTM_*` 前缀变量
2. **config.json**：Web 前端保存的持久化配置
3. **env.py**：兼容旧部署的 Python 配置文件
4. **代码默认值**：`127.0.0.1:6379` 等

### 7.2 核心环境变量

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `UTM_REDIS_HOST` | Redis 主机地址 | `127.0.0.1` |
| `UTM_REDIS_PORT` | Redis 端口 | `6379` |
| `UTM_REDIS_PASSWORD` | Redis 密码 | 空 |
| `UTM_KAFKA_URL` | Kafka Bootstrap 服务器 | `127.0.0.1:9092` |
| `UTM_MYSQL_HOST` | MySQL 主机 | `127.0.0.1` |
| `UTM_MYSQL_PORT` | MySQL 端口 | `3306` |
| `UTM_MYSQL_USER` | MySQL 用户 | `root` |
| `UTM_MYSQL_PASSWORD` | MySQL 密码 | 空 |
| `UTM_MYSQL_DB` | MySQL 数据库名 | `utm_simulator` |

---

## 八、Redis/Kafka 数据约定

### 8.1 核心 Key/Topic

| 存储 | Key/Topic | 类型 | 用途 |
|------|----------|------|------|
| Redis | `BIZ_DATA:UAV_ROUTE` | Hash | 飞行计划（航线） |
| Redis | `BIZ_DATA:AIRSPACE` | Hash | 空域/禁飞区 |
| Kafka | `uav_runtime_data` | Topic | 无人机实时遥测 |
| Kafka | `uav_runtime_trace` | Topic | 下游轨迹预测结果 |
| Kafka | `uav_collision_alarm` | Topic | 冲突告警 |

> ⚠️ **硬约束**：以上 Key/Topic 名和消息格式不可修改，它们是 ATC Dashboard 的固定读写入口。

---

## 九、开发规范

| 规则 | 说明 |
|------|------|
| UTF-8 编码 | 所有 Python 文件头 `# -*- coding: utf-8 -*-` |
| 中文注释 | 注释、文档字符串使用中文；外部字段名使用英文 |
| 类型注解 | 推荐使用 `typing`（`List[Dict[str, Any]]` 等） |
| JSON 编码 | `ensure_ascii=False` 正确保存中文 |
| 敏感信息 | `env.py` 等连接配置文件**不提交版本库** |


## 附录

### A. 常用命令速查

```bash
conda activate utm

# Web 控制台
python cli.py server

# 场景注入
python tools/run_kafka_scene.py --file data/mock/scene.json

# Redis 计划插值
python tools/run_plan.py

# 连通性检查
python cli.py check

# 数据量统计
python cli.py status

# 单元测试
python -m pytest tests/ -v
```

### B. 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 系统架构文档 | `docs/系统架构文档.md` | 架构分层、数据流 |
| 环境配置 | `docs/模拟器环境配置.md` | 多环境对照 |
| 优化工作记录 | `docs/utm-simulator-optimization-work-log.md` | 历史优化记录 |
| 算法对接规范 | `docs/reference/算法对接2026.md` | 数据格式参考 |
| 命令手册 | `docs/命令手册.md` | 诊断命令参考 |

---

> 📅 最后更新：2026-07-22
>
> 👤 维护者：李洋
