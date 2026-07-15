# 低空空管（ATC/UTM）自动化测试平台

> 服务于"海豚"（Dolphin）ATC 态势感知 Dashboard（`dkkgsit-test.testdolphin.com`）
>
> 通过无人机模拟器向 Redis/Kafka 注入仿真数据，驱动 Dashboard 展示，并对其进行 API 自动化测试、高可用测试和性能测试。

---

## 一、项目概述

本项目是一个完整的低空空管自动化测试平台，核心能力包括：

- **无人机群仿真**：模拟数百至数千架无人机沿航线飞行，生成逼真的飞行计划与实时遥测数据
- **数据注入**：通过共享的 Redis/Kafka 基础设施向 ATC 系统注入仿真数据，Dashboard 对数据来源（真实 vs 仿真）完全无感知
- **API 自动化测试**：覆盖 IOMP 运维平台和 ATC 业务系统的接口测试，含 JWT 鉴权、服务管理、数据一致性校验
- **高可用测试**：双集群服务重启、Kafka 积压监控、Chaos Mesh 故障注入、大规模模拟器发射（3000/5000 架）
- **Web 可视化控制台**：5 种仿真模式、数据生成面板、实时地图监控（高德瓦片 + GCJ-02 坐标转换）
- **AI 集成接口**：预留 6 个 AI 工具调用集成点，支持 Claude Code / MCP 协议

---

## 二、核心功能

### 2.1 无人机仿真与数据注入

| 运行模式 | 入口 | 说明 |
|---------|------|------|
| **动态仿真** (dynamic) | `main.py` / `cli.py run` | Simulator 引擎实时生成飞行计划 + 动力学遥测，持续维持目标无人机数量 |
| **预生成回放** (replay) | `cli.py replay` / `tools/run_kafka_alive.py` | 从 JSON 文件循环回放预录制遥测数据，适合长期稳定注入 |
| **Redis 计划插值** (plan) | `cli.py plan` / `tools/run_plan.py` | 从 Redis 读取飞行计划航段，线性插值实时生成遥测，无需仿真引擎或预生成文件 |
| **场景文件注入** (scene) | `cli.py run --mode scene` | 按指定间隔从 JSON 场景文件发射遥测，支持 replace/align/preserve 三种时间戳模式 |
| **单次回放** (replay_once) | Web 控制台选择 | 数据耗尽自动停止，输出轨迹精度报告 |

### 2.2 API 自动化测试

- **IOMP 平台测试**：JWT 令牌管理、服务查询/重启/扩缩容、Pod 日志下载、集群命名空间查询
- **ATC 业务测试**：飞行任务查询与管理、航线/空域/起降场 API、操作员/运营单位管理、航空器批量导入
- **数据一致性校验**：
  - Redis A/B 集群数据一致性对比（`BIZ_DATA:UAV_ROUTE`、`BIZ_DATA:AIRSPACE`、告警参数）
  - Kafka 双集群 Topic 新数据到达检测（`uav_runtime_data`、`uav_runtime_trace`）
  - 达梦数据库 A/B 集群表记录数对比
  - Elasticsearch 索引文档数 5 分钟切片一致性检查

### 2.3 高可用测试

- **服务重启测试**：通过 IOMP API 对双集群目标服务执行重启，检测 Pod 恢复状态
- **Kafka 积压监控**：并行查询 A/B 集群多消费者组的消费延迟（lag）
- **缩容切换测试**：将主集群服务副本缩至 0 → 检测主备切换 → 恢复副本 → 验证存储一致性（Redis/ES/达梦）
- **Chaos Mesh 故障注入**：通过 Chaos Mesh Dashboard API 编排 PodKill 实验，自动检测集群切换与恢复时间
- **大规模模拟器发射**：同时向 A/B 集群发射 3000-5000 架无人机模拟器，验证双集群承载能力

### 2.4 Web 可视化控制台

启动方式：`.\start_web.ps1` 或 `python cli.py server`，浏览器访问 `http://localhost:5000`

- **5 种仿真模式**：一键切换 dynamic / replay / replay_once / scene / plan
- **数据生成面板**（4 个 Tab）：
  - 基础生成：随机/网格/放射三种算法
  - 单机场景：航线飞行 / 偏离航路 / 状态变更
  - 多机场景：平行飞行 / 偏离(高级) / 碰撞预警 / 状态告警
  - 批量预设：11 个全国区域一键生成
- **地图可视化**：Leaflet + 高德瓦片（国内秒加载）+ WGS-84 → GCJ-02 坐标转换，实时展示航线/禁飞区/无人机位置
- **实时监控**：Chart.js 趋势图（无人机数量、Kafka 吞吐、运行时长、错误率）
- **配置编辑**：前端直接修改 Redis/Kafka 连接参数并持久化到 `config.json`

---

## 三、系统架构

### 3.1 分层架构

```text
┌──────────────────────────────────────────────────────────────────┐
│                      业务编排层                                   │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │ main.py  │  │run_kafka_alive.py│  │    run_plan.py       │   │
│  │(动态仿真) │  │  (预生成数据注入)  │  │   (Redis计划插值)    │   │
│  └────┬─────┘  └────────┬─────────┘  └──────────┬───────────┘   │
│       │                 │                        │               │
│  ┌────┴─────────────────┴────────────────────────┴──────────┐   │
│  │              sim_manager.py (统一编排层)                   │   │
│  │        动态/回放/计划/场景 四种模式统一入口                    │   │
│  └────────────────────────┬─────────────────────────────────┘   │
└───────────────────────────┼──────────────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────────────┐
│                           │        仿真核心层                      │
│  ┌────────────────────────┴──────────────────────────────────┐   │
│  │               simulation_core.py                          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────────┐    │   │
│  │  │ DroneAgent │  │ Simulator  │  │DynamicNoFlyZone  │    │   │
│  │  │ · 6状态机   │  │ · 计划生成  │  │ · 凸多边形几何    │    │   │
│  │  │ · 动力学    │  │ · 禁飞区   │  │ · 时间窗管理      │    │   │
│  │  └────────────┘  └────────────┘  └──────────────────┘    │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────────────┐
│                           │        数据接入层                      │
│  ┌────────────────────────┴────────┐  ┌──────────────────────┐   │
│  │       redis_client.py           │  │    kafka_proc.py     │   │
│  │  · hset/hget/hgetall            │  │  · 批量发送+双集群同步 │   │
│  │  · get_value_by_key (类型检测)   │  │  · latest-offset消费  │   │
│  └────────────┬────────────────────┘  └──────────┬───────────┘   │
└───────────────┼──────────────────────────────────┼───────────────┘
                │                                  │
       ┌────────┴────────┐              ┌──────────┴──────────┐
       │     Redis       │              │       Kafka         │
       │ BIZ_DATA:       │              │ uav_runtime_data    │
       │   UAV_ROUTE     │              │ uav_runtime_trace   │
       │   AIRSPACE      │              │ uav_collision_alarm │
       └────────┬────────┘              └──────────┬──────────┘
                │                                  │
                └──────────────┬───────────────────┘
                               ▼
                ┌──────────────────────────┐
                │   ATC Dashboard (海豚)    │
                │   读取 Redis 航线/空域     │
                │   消费 Kafka 遥测/告警    │
                │   实时态势感知展示          │
                └──────────────────────────┘
```

### 3.2 核心数据流

```text
                        ┌──────────────┐
                        │  Simulator   │
                        │  生成飞行计划  │
                        └──────┬───────┘
                               │ FlightPlan
                               ▼
               ┌───────────────────────────┐
               │    DataSource             │
               │  _plan_to_route_data()    │
               │  Redis.hset(uid, route)   │
               └───────────┬───────────────┘
                           │ JSON
                           ▼
               ┌───────────────────────────┐
               │  Redis BIZ_DATA:UAV_ROUTE │
               │  (Hash: uid → route JSON) │
               └───────────────────────────┘

                        ┌──────────────┐
                        │  Simulator   │
                        │   step(1.0)  │
                        └──────┬───────┘
                               │ TelemetryData[]
                               ▼
               ┌───────────────────────────┐
               │    DataSource             │
               │  _telemetry_to_kafka_msg()│
               │  producer.send_bulk()     │
               └───────────┬───────────────┘
                           │ JSON 消息
                           ▼
               ┌───────────────────────────┐
               │  Kafka uav_runtime_data   │
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
```

### 3.3 三种运行模式对比

| 维度 | dynamic (动态仿真) | replay (预生成回放) | plan (Redis 插值) |
|------|-------------------|--------------------|--------------------|
| 数据来源 | Simulator 引擎实时生成 | 预录制 JSON 文件回放 | Redis 航段几何插值 |
| 物理模型 | ✅ 真实动力学（加减速/爬升/降落） | ❌ 回放预记录坐标 | ❌ 线性插值（匀速） |
| Redis 写入 | 仿真过程中动态写入 | 启动时写入+循环刷新 | 仅读取+时间平移回写 |
| 数据确定性 | 每次不同（随机生成） | 每次相同（固定 JSON） | 取决于 Redis 当前快照 |
| 适用场景 | 开发调试、动态飞行行为 | 长期稳定注入、精确定点回放 | 仅需飞行计划的轻量注入 |
| 禁飞区 | ✅ 动态生成 | ❌ 不涉及 | ❌ 不涉及 |

---

## 四、项目目录结构

```text
atc_test_platfrom/
├── utm_simulator/               # 🚁 无人机模拟器核心（utm_moc52）
│   ├── main.py                  #   主入口：DataSource + DataFlow 双线程
│   ├── simulation_core.py       #   仿真引擎：DroneAgent(6状态机) + Simulator
│   ├── sim_manager.py           #   统一编排层：dynamic/replay/plan 三模式
│   ├── redis_client.py          #   Redis 客户端封装（类型感知读写）
│   ├── kafka_proc.py            #   Kafka 生产者/消费者封装（双集群镜像）
│   ├── cli.py                   #   统一 CLI：7 个子命令
│   ├── web_server.py            #   Flask Web 后端（REST API + WebSocket）
│   ├── web_data_gen_bridge.py   #   API 桥接层（tools 脚本 ↔ Flask 路由）
│   ├── sim_api_bridge.py        #   ATC API 桥接（JWT/任务CRUD/计划申报）
│   ├── ai_integration.py        #   AI 集成点注册中心（6 个工具调用接口）
│   ├── situation_monitor.py     #   态势监控采集器（SockJS+STOMP）
│   ├── tests/                   #   pytest 单元测试（conftest + 3 test 文件）
│   ├── tools/                   #   工具脚本集（~19 个）
│   │   ├── run_kafka_alive.py   #     生产主力：预生成数据循环注入
│   │   ├── run_plan.py          #     Redis 计划插值运行器（PlanRunner）
│   │   ├── run_kafka_scene.py   #     场景文件注入器（SceneEmitter）
│   │   ├── create_data.py       #     基础数据生成（Simulator 引擎）
│   │   ├── create_data_scene.py #     单机场景生成（线性插值+偏离）
│   │   ├── create_data_scenes.py#     综合场景工厂（11 子命令）
│   │   ├── lines_to_redis_route.py#   航线组装+冲突航线生成
│   │   ├── nfzs.py              #     禁飞区/空域数据转换与上传
│   │   ├── transform.py         #     原始计划/遥测格式转换
│   │   ├── trajectory_accuracy.py#    轨迹预测精度评估（HTML 报告）
│   │   ├── kafka_read_latest.py #     Kafka 诊断：消费最新消息导出
│   │   └── redis_read_lastest.py#     Redis 诊断：SCAN 遍历导出
│   ├── pylib/                   #   C++ UTM 核心库 Python 封装
│   │   ├── structs.py           #     ctypes 结构体（与 utm_core.h 兼容）
│   │   └── engine.py            #     引擎封装（轨迹预测/冲突检测/偏航检测）
│   ├── _source/                 #   算法规范与原始数据
│   │   ├── 算法对接2026.md       #     算法对接权威文档
│   │   ├── nfzs.json            #     禁飞区源数据
│   │   └── plans.json           #     飞行计划样例
│   ├── deploy_repeat.sh         #   主部署脚本（run_kafka_alive 模式）
│   ├── deploy.sh                #   备选部署脚本（main.py 模式）
│   └── requirements.txt         #   Python 依赖清单
│
├── web/                          # 🌐 Web 前端（独立目录）
│   ├── pages/                    #   10个功能页面（run/schedule/generate/data/env/logs等）
│   └── static/                   #   CSS/JS/Leaflet 本地副本（11个JS模块）
│
├── common/                       # 📦 公共基础设施（独立目录）
│   ├── config.py                 #   统一配置管理（环境变量>config.json>env.py>默认值）
│   ├── config.json               #   运行时配置（Web前端可修改保存）
│   ├── schemas.py                #   TypedDict 类型定义
│   ├── validators.py             #   Pydantic 数据校验器
│   ├── exceptions.py             #   语义异常层次（9个异常类）
│   └── log_setup.py              #   结构化日志初始化
│
├── database/                     # 🗄️ 数据库持久化（独立目录，MySQL主库）
│   ├── mysql_db_manager.py       #   MySQL 管理器（pymysql 1.x）
│   ├── db_manager.py             #   SQLite 基础操作（遗留兼容）
│   ├── json_data_manager.py      #   JSON 文件管理 + 达梦航线查询
│   ├── env_manager.py            #   多环境配置 CRUD
│   ├── scheduler.py              #   Cron 定时任务调度
│   ├── log_streamer.py           #   实时日志流（内存缓冲+WS+MySQL持久化）
│   ├── migrate_to_mysql.py       #   SQLite → MySQL 迁移工具
│   └── migrate_schema_v2.py      #   表结构迁移 v2
│
├── services/                     # 🤖 独立服务
│   └── ai/                       #   AI 数据生成
│       └── ai_data_gen.py        #     LLM 生成器（OpenAI兼容API）
│
├── data/                         # 📋 统一数据目录
│   ├── mock/                     #   模拟生成的JSON数据
│   ├── templates/                #   飞行任务模板（3个JSON）
│   ├── uploads/                  #   用户上传文件
│   └── schemas/                  #   JSON Schema 定义（4个）
│
├── atc_api_autotest/            # 🧪 API 自动化测试
│   ├── api_tools/               #   核心工具库（20+ 模块）
│   │   ├── iomp_api_common.py   #     IOMP JWT 令牌管理（缓存+自动刷新）
│   │   ├── iomp_api_servers_ops.py#   IOMP 服务管理（查询/重启/扩缩容）
│   │   ├── iomp_core.py         #     IOMP 日志批量下载器
│   │   ├── Jwt_Token_get.py     #     ATC JWT 令牌获取（OAuth2 密码模式）
│   │   ├── dmdbclient.py        #     达梦数据库客户端（连接池+查询）
│   │   ├── kafka_topic_check.py #     Kafka Topic 新数据到达检测
│   │   ├── Redis同步redis_consistency_check.py  # Redis A/B 一致性校验
│   │   ├── network_monitor.py   #     网络可达性监控（Ping+HTTP）
│   │   ├── ha_日志分析.py        #     双集群日志对比分析
│   │   └── 客户端ws无人机数量统计.py  # WebSocket STOMP 无人机实时统计
│   ├── api_test_cases/          #   测试用例脚本
│   └── env.py                   #   环境配置（Redis/Kafka/数据库）
│
├── atc_ha_test/                 # 🔄 高可用测试
│   ├── ha_env.py                #   HA 环境全局配置
│   ├── ha_scale_test.py         #   一键缩容切换测试 V1（完整工作流）
│   ├── ha_scale_test2.py        #   缩容切换测试 V2（CLI+检查点模式）
│   ├── ha_iomp_server_reboot.py #   双集群服务重启
│   ├── ha_kafka_lag_check.py    #   双集群 Kafka 消费延迟监控
│   ├── ha_3000_5000模拟器发射.py  #   大规模无人机模拟器发射（3000-5000架）
│   ├── cluster_master_query.py  #   实时主集群检测
│   ├── redis_sync_check.py      #   Redis A/B 一致性检查
│   ├── es_sync_check_ha.py      #   ES 索引级数据量对比
│   ├── dm_data_snyc_check.py    #   达梦数据库 A/B 一致性检查
│   ├── 高可用集群切换测试case1.py#   批量服务 HA 测试器
│   ├── 高可用集群切换测试case2.py#   精细 HA 计时测试器（毫秒级）
│   ├── 上图时间指标获取.py        #   端到端延迟测量（发射→WS显示）
│   ├── bizws_log_check.py       #   Biz/WS 日志健康循环检查
│   ├── ws_client_check.py       #   WebSocket 多连接监控客户端
│   └── ha-test_chaosmesh/       #   Chaos Mesh 故障注入实验
│       └── atc-ha/scripts/      #     自动集群检测+PodKill+恢复计时
│
├── atc_data_factory/            # 🏭 数据工厂
│   └── script/                  #   飞行任务创建 + 接收机测试数据生成
│
├── test_data_create/            # 📋 测试场景数据集
│   └── scenes_test_data/        #   短期冲突类 / 空域侵入类 / 偏离航路类
│
├── atc_auto_test/               # 🤖 旧版自动化测试
├── atc_api_info/                # 📡 ATC/IOMP API 文档
├── atc_local_rag/               # 🧠 本地 RAG 知识库
├── atc_test_cases/              # 📝 测试用例与场景
├── skills_hub/                  # 🎯 团队协作技能库（子模块）
│   ├── api-test-case-generator/ #   接口测试用例生成
│   ├── excel-test-case-generator/#  Excel 测试用例生成
│   ├── tapd-plus/               #   TAPD 集成增强
│   ├── perf-test/               #   性能测试工具
│   └── ...                      #   其他 20+ 技能模块
├── docker/                      # 🐳 Docker 容器化配置
├── docs/                        # 📚 中文架构文档
│   ├── 系统架构文档.md           #   系统架构详解（9 章）
│   ├── 核心代码原理.md           #   核心算法深度解析（9 章）
│   ├── 模拟器环境配置.md         #   环境配置与对接说明
│   ├── utm-simulator-data-link.md#  数据传输链路完整文档
│   └── utm-simulator-optimization-work-log.md  # 优化工作记录
├── start_web.ps1                # 🚀 Web 控制台一键启动脚本
├── .gitignore                   #   Git 忽略规则
└── README.md                    #   本文件
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
| 达梦数据库 | 可选，只读外部 ATC 系统，用于数据库一致性校验（需 `dmPython`） |
| Docker | 可选，容器化部署（Python 3.11-slim 镜像 + docker-compose） |
| Git | 版本管理 |

### 5.2 安装步骤

```bash
# 1. 克隆仓库
git clone <repo-url>
cd atc_test_platfrom

# 2. 创建并激活 Conda 环境
conda create -n utm python=3.11.15
conda activate utm

# 3. 安装模拟器依赖
cd utm_simulator
pip install -r requirements.txt

# 4. 配置连接信息
# 编辑 utm_simulator/env.py，填写实际 Redis/Kafka 地址与密码
# 或通过 Web 控制台环境管理页直接配置（保存到 common/config.json）

# 5. 配置 MySQL（如使用 Docker 部署则通过环境变量注入）
# 设置环境变量：UTM_MYSQL_HOST, UTM_MYSQL_PORT, UTM_MYSQL_USER, UTM_MYSQL_PASSWORD, UTM_MYSQL_DB

# 6. 验证安装
python cli.py check   # 检查 Redis/Kafka 连通性
python cli.py status  # 查看 Redis 中飞行计划/空域数据量
```

### 5.3 Docker 部署（推荐生产环境）

```bash
cd /opt/atc_test_platfrom

# 首次构建并启动
docker compose -f docker/docker-compose.yml build --no-cache
docker compose -f docker/docker-compose.yml up -d

# 查看日志
docker logs -f utm-simulator

# 更新部署（代码变更后）
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml build --no-cache
docker compose -f docker/docker-compose.yml up -d
```

> 详细 Docker 部署与 MySQL 排障命令参见 `docs/命令手册.md`

### 5.4 关键依赖

```text
kafka-python>=2.0.2       # Kafka 生产者/消费者
redis>=4.5.0,<5.0.0       # Redis 客户端
requests                  # HTTP 接口调用
Flask                     # Web 后端
Flask-SocketIO            # WebSocket 推送
pydantic                  # 数据校验（可选，validators.py 需要）
pymysql==1.1.0            # MySQL 连接（严格锁定 1.x）
cryptography              # TLS/SSL 支持（MySQL caching_sha2_password 认证所需）
pytest / pytest-cov       # 单元测试
dmPython                  # 达梦数据库连接（可选，需单独安装）
```

---

## 六、快速开始

### 6.1 启动模拟器

```bash
cd utm_simulator
conda activate utm

# 方式一：统一 CLI（推荐）
python cli.py run --mode dynamic --count 100    # 动态仿真 100 架
python cli.py run --mode replay --data-file mock/kafka_data.json  # 预生成回放
python cli.py plan                               # Redis 计划插值模式

# 方式二：直接运行
python main.py                                   # 动态仿真（默认 10 架）
python tools/run_kafka_alive.py --count 60       # 预生成数据循环注入

# 方式三：场景文件注入
python cli.py run --mode scene --scene-dir mock/
```

### 6.2 启动 Web 可视化控制台

```bash
# 方式一：PowerShell 一键启动
.\start_web.ps1

# 方式二：CLI 启动
python cli.py server

# 浏览器访问
# http://localhost:5000
```

Web 控制台提供：
- 可视化配置 Redis/Kafka 连接参数
- 5 种仿真模式一键切换
- 数据生成面板（基础/单机/多机/批量 4 个 Tab）
- 实时 Leaflet 地图 + Chart.js 趋势图
- 仿真日志实时查看与导出

### 6.3 运行 API 测试

```bash
cd atc_api_autotest
conda activate utm

# 执行单个测试用例
python api_test_cases/飞行任务列表查询.py

# 获取 JWT Token
python api_tools/Jwt_Token_get.py

# Redis 一致性检查
python api_tools/Redis同步redis_consistency_check.py

# 网络监控
python api_tools/network_monitor.py
```

### 6.4 运行 HA 测试

```bash
cd atc_ha_test
conda activate utm

# 双集群服务重启
python ha_iomp_server_reboot.py --service la-atc-biz-backend

# Kafka 积压监控
python ha_kafka_lag_check.py

# 一键缩容切换测试
python ha_scale_test2.py --service la-atc-biz-backend --rounds 3

# 大规模模拟器发射（3000 架）
python ha_3000_5000模拟器发射.py

# 集群主节点实时监控
python cluster_master_query.py
```

---

## 七、配置管理

### 7.1 配置优先级

`config.py` 采用多层配置加载策略（高→低）：

1. **环境变量**：`UTM_REDIS_HOST`、`UTM_KAFKA_URL` 等 `UTM_*` 前缀变量
2. **config.json**：Web 前端保存的持久化配置
3. **env.py**：兼容旧部署的 Python 配置文件
4. **代码默认值**：`127.0.0.1:6379` 等

### 7.2 环境变量列表

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `UTM_REDIS_HOST` | Redis 主机地址 | `127.0.0.1` |
| `UTM_REDIS_PORT` | Redis 端口 | `6379` |
| `UTM_REDIS_PASSWORD` | Redis 密码 | 空 |
| `UTM_REDIS_DB` | Redis 数据库编号 | `0` |
| `UTM_KAFKA_URL` | Kafka Bootstrap 服务器 | `127.0.0.1:9092` |
| `UTM_KAFKA_URL2` | Kafka 镜像集群地址（双写容灾） | 空 |
| `UTM_KAFKA_FLUSH_TIMEOUT` | Kafka Flush 超时（秒） | `1.0` |
| `UTM_SIM_TARGET_DRONES` | 默认仿真无人机数量 | `10` |
| `UTM_SIM_CENTER_LAT` | 仿真中心纬度 | `31.315` |
| `UTM_SIM_CENTER_LON` | 仿真中心经度 | `120.665` |
| `UTM_SIM_RADIUS_M` | 仿真区域半径（米） | `800` |
| `UTM_SIM_CRUISE_SPEED` | 巡航速度（m/s） | `30` |
| `UTM_LOG_LEVEL` | 日志级别 | `INFO` |

### 7.3 多环境对照

| 环境 | Redis 地址 | Kafka 地址 | 用途 |
|------|-----------|-----------|------|
| dkkgdev | `10.165.78.1:21002` | `10.165.77.69:30012` | 开发环境 |
| 24 | `10.165.32.24:26379` | `10.165.32.24:29092` | 24 号环境 |
| 25 | `10.165.32.25:26379` | `10.165.32.25:29092` | 25 号环境 |
| atc | `10.165.18.1:22204` | `10.165.19.215:30318` | ATC 测试 |
| atctest | `redis-atc:6379` | kafka-atctest (3节点) | ATC K8s |
| 实验局 | `redis-atc:6379` | `dol-kafka-0:9092` | 实验局 |

---

## 八、Redis/Kafka 数据约定

### 8.1 核心 Key/Topic

| 存储 | Key/Topic | 类型 | 用途 | 写入方 | 消费方 |
|------|----------|------|------|--------|--------|
| Redis | `BIZ_DATA:UAV_ROUTE` | Hash | 飞行计划（航线） | 模拟器 | ATC Dashboard |
| Redis | `BIZ_DATA:AIRSPACE` | Hash | 空域/禁飞区 | 模拟器 | ATC Dashboard |
| Kafka | `uav_runtime_data` | Topic | 无人机实时遥测 | 模拟器 | ATC Dashboard |
| Kafka | `uav_runtime_trace` | Topic | 下游轨迹预测结果 | UTM 引擎 | 模拟器（验证） |
| Kafka | `uav_collision_alarm` | Topic | 冲突告警 | UTM 引擎 | ATC Dashboard |

> ⚠️ **硬约束**：以上 Key/Topic 名和消息格式不可修改，它们是 ATC Dashboard 的固定读写入口。

### 8.2 飞行计划格式（Redis `BIZ_DATA:UAV_ROUTE`）

```json
{
  "uniqueProductIdentificationCode": "DJI1MAV101A2B3C4D5E6",
  "flightPlanList": [{
    "flightPlanId": 1,
    "planTakeoffTime": 1751900000.123,
    "planLandTime": 1751905400.123,
    "flightTaskId": 1,
    "flightTaskName": "test",
    "routeList": [{
      "sequence": 0,
      "type": 2,
      "segmentStartLon": 120.665, "segmentStartLat": 31.315,
      "segmentEndLon": 120.672,   "segmentEndLat": 31.320,
      "segmentStartHeight": 0.0,  "segmentEndHeight": 120.5,
      "segmentProtectHeight": 50.0,
      "segmentProtectHeightType": 1,
      "segmentWidth": 100.0
    }]
  }]
}
```

### 8.3 遥测数据格式（Kafka `uav_runtime_data`）

```json
{
  "uniqueProductIdentificationCode": "DJI1MAV101A2B3C4D5E6",
  "realNameRegistrationSign": "UAS01DJI1MAV001",
  "longitude": 120.6723,
  "latitude": 31.3185,
  "trackAngle": 45.2,
  "speed": 28.5,
  "geodeticAltitude": 125.3,
  "verticalSpeed": 0.0,
  "operatingStatus": 2,
  "sourceType": 1,
  "active": 1,
  "timestamp": 1751900123123,
  "horizontalAccuracy": 1.0,
  "verticalAccuracy": 1.0,
  "speedAccuracy": 1.0,
  "coordinateSystemType": 0
}
```

> 完整字段说明（~22 个字段）参见 `docs/utm-simulator-data-link.md` 第五章

---

## 九、Web 可视化控制台详解

### 9.1 五种仿真模式

| 模式 | 标识 | 数据来源 | 停止条件 |
|------|------|---------|---------|
| 🎮 动态仿真 | `dynamic` | Simulator 引擎实时生成 | 手动停止 |
| 🔁 预生成回放(循环) | `replay` | JSON 文件循环读取 | 手动停止 |
| ▶️ 预生成回放(单次) | `replay_once` | JSON 文件单次读取 | 数据耗尽自动停止 |
| 🎬 场景文件注入 | `scene` | JSON 按间隔发射 | 数据耗尽/手动停止 |
| 📐 Redis 计划插值 | `plan` | Redis 航段几何插值 | 手动停止 |

### 9.2 数据生成面板

| Tab | 功能 | 输出 |
|-----|------|------|
| 基础生成 | 随机/网格/放射 三种模式 | `mock/kafka_data.json` |
| 单机场景 | 航线飞行 / 偏离航路 / 状态变更 | `mock/kafka_data_scene.json` |
| 多机场景 | 平行飞行 / 偏离(高级) / 碰撞预警 / 状态告警 | `mock/kafka_data_*.json` |
| 批量预设 | 11 个全国区域一键生成 | 多个 JSON 文件 |

### 9.3 地图可视化

- **瓦片源**：高德地图（国内秒加载，无需 API Key），备选 CartoDB
- **坐标转换**：WGS-84 → GCJ-02 自动转换（中国境外自动跳过）
- **图层**：航线（彩色轨迹线）、禁飞区（半透明多边形）、图例
- **容器检测**：自动等待 Flex 布局完成，防止初始化时尺寸为 0

---

## 十、自动化测试

### 10.1 API 测试架构

```
┌─────────────────────────────────────────────┐
│            api_tools/ (核心库)                │
│  ┌───────────┐ ┌──────────┐ ┌────────────┐  │
│  │ JWT 认证   │ │ IOMP API │ │  数据库     │  │
│  │ (token缓存 │ │ (服务管理 │ │ (达梦/dm   │  │
│  │  自动刷新) │ │  日志下载)│ │  Python)   │  │
│  └───────────┘ └──────────┘ └────────────┘  │
│  ┌───────────┐ ┌──────────┐ ┌────────────┐  │
│  │ Kafka检查  │ │ Redis检查│ │  网络监控   │  │
│  └───────────┘ └──────────┘ └────────────┘  │
└─────────────────────────────────────────────┘
         │                │                │
         ▼                ▼                ▼
┌─────────────────────────────────────────────┐
│          api_test_cases/ (测试用例)           │
│  飞行任务查询 / 操作员管理 / 运营单位管理      │
└─────────────────────────────────────────────┘
```

### 10.2 HA 测试架构

典型工作流：

```text
1. 健康预检  →  验证 A/B 集群目标服务状态
2. 故障注入  →  主集群服务缩容至 0 / Chaos Mesh PodKill
3. 切换检测  →  轮询 cluster.txt / daemon WebSocket / 日志解析
4. 恢复      →  自动恢复副本数 / 等待 Pod Ready
5. 验证      →  Redis 一致性 + ES 切片对比 + 达梦表计数 + 服务状态
6. 报告      →  TXT/HTML 报告（切换指标 + 一致性状态 + 通过/失败）
```

### 10.3 测试场景分类

| 类别 | 场景 | 说明 |
|------|------|------|
| **短期冲突** | 垂直碰撞、水平迎头相撞、水平追赶冲突、三架无人机飞行、告警趋势解除 | 验证冲突检测算法 |
| **空域侵入** | 禁区侵入（长方体）、危险区侵入（圆柱体） | 验证空域告警 |
| **偏离航路** | 偏离预设计划、最低安全高度 | 验证偏航检测 |

---

## 十一、开发与贡献

### 11.1 代码规范

| 规则 | 说明 |
|------|------|
| UTF-8 编码 | 所有 Python 文件头 `# -*- coding: utf-8 -*-` |
| 中文注释 | 注释、文档字符串、打印信息使用中文；与外部系统一致的字段名/枚举值使用英文 |
| 类型注解 | 推荐使用 `typing`（`List[Dict[str, Any]]`、`Optional[str]` 等） |
| 根路径处理 | `tools/` 下脚本将项目根目录加入 `sys.path` |
| JSON 编码 | `ensure_ascii=False` 正确保存中文 |
| 敏感信息 | `env.py`、`ha_env.py` 等连接配置文件**不提交版本库** |

### 11.2 开发工作流

1. **先方案，后执行**：修改代码前先展示方案（修改文件列表、改动说明、预期效果），用户确认后再操作
2. **不破坏核心链路**：`redis_client.py` / `kafka_proc.py` / `simulation_core.py` 核心逻辑不随意修改
3. **保持数据兼容**：Redis Key / Kafka Topic / 消息格式不改变
4. **向后兼容**：新功能优先采用新增文件方式，旧脚本保持可独立运行

### 11.3 AI 辅助开发

项目预留了 AI 集成接口：

- **6 个工具调用集成点**（`ai_integration.py`）：`validate_scenario`、`check_redis_data`、`check_kafka_topic`、`run_simulation`、`generate_test_report`、`query_drone_state`
- **MCP 配置**（`.claude/mcp.json`）：Redis / Filesystem MCP 服务器
- **Agent 定义**（`.claude/agents/`）：`utm-tester`、`data-analyst`
- **集成指南**：`skills_hub/AI_INTEGRATION_GUIDE.md`

### 11.4 工作日志维护

每次优化后必须在 `docs/utm-simulator-optimization-work-log.md` 中补充更新内容（按日期时间顺序）：

- 每条记录包含：日期、文件、操作（新建/修改/重写）、状态、验证方式
- 每次优化汇总新建/修改文件数
- 不删减以前的工作日志

---

## 附录

### A. 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 系统架构文档 | `docs/系统架构文档.md` | 架构分层、数据流、部署架构 |
| 核心代码原理 | `docs/核心代码原理.md` | 仿真引擎算法、坐标转换、数据生成工具链 |
| 数据链路文档 | `docs/utm-simulator-data-link.md` | Redis/Kafka 数据结构、四种模式完整链路 |
| 环境配置 | `docs/模拟器环境配置.md` | 多环境对照、对接原理 |
| 优化工作记录 | `docs/utm-simulator-optimization-work-log.md` | 历史优化记录 |
| 算法对接规范 | `utm_simulator/_source/算法对接2026.md` | 数据格式权威参考 |
| 模拟器 CLAUDE.md | `utm_simulator/CLAUDE.md` | 模拟器子项目 AI 编程规则 |

### B. 常用命令速查

```bash
conda activate utm                              # 激活 Python 环境
cd utm_simulator

# 仿真
python cli.py run --mode dynamic --count 100    # 动态仿真 100 架
python cli.py replay --data-file mock/kafka_data.json  # JSON 回放
python cli.py plan                              # Redis 计划插值
python cli.py server                            # 启动 Web 控制台
python cli.py check                             # 检查 Redis/Kafka 连通性
python cli.py validate --file mock/scene.json   # 校验 JSON 数据格式
python cli.py status                            # 查看 Redis 数据量

# 测试
python -m pytest utm_simulator/tests/ -v         # 运行模拟器单元测试
cd atc_ha_test && python ha_scale_test2.py       # HA 缩容切换测试
cd atc_ha_test && python ha_kafka_lag_check.py   # Kafka 积压监控
```

### C. 常见问题

**Q: 地图加载不出来？**
A: 项目已内置高德瓦片源，国内可秒加载。如仍无法加载，打开浏览器开发者工具查看网络请求是否被拦截。

**Q: Redis/Kafka 连接失败？**
A: 确认 `env.py` 中的地址和密码与目标环境一致；或通过 Web 控制台配置面板直接修改保存到 `config.json`。

**Q: `dmPython` 导入失败？**
A: 达梦数据库驱动需单独安装，仅数据库相关工具需要，不影响模拟器核心功能。

---

> 📅 最后更新：2026-07-15
>
> 👤 维护者：李洋
