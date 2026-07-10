# 项目文件架构优化方案 — 第二轮：Python 模块解耦移出

## 背景（Context）

第一轮优化已完成 `web/`（前端）、`data/mock/`（JSON数据）、`data/templates/`（模板）的移出。但对比 `docs/SYSTEM_ARCHITECTURE.md` 中的初始架构，`utm_simulator/` 仍有 ~15 个新增 Python 模块（数据库管理、日志、调度、AI 等）混在其中，与初始的纯仿真核心定位不符。

经过完整耦合分析，识别出以下可安全移出和不可移出的文件：

---

## 一、可移出文件（已确认零核心耦合或仅内部互依赖）

### 集群 A：`database/` — 数据库持久化层（5 文件 + data.db）

这些文件形成一个**自包含的 SQLite 持久化集群**，互依赖链为：
```
env_manager.py → db_manager.py
json_data_manager.py → db_manager.py
scheduler.py → db_manager.py
log_streamer.py → db_manager.py
```
**全部不依赖** `simulation_core`, `redis_client`, `kafka_proc`。

| 文件 | → 新位置 |
|------|----------|
| `db_manager.py` | `database/db_manager.py` |
| `env_manager.py` | `database/env_manager.py` |
| `json_data_manager.py` | `database/json_data_manager.py` |
| `scheduler.py` | `database/scheduler.py` |
| `log_streamer.py` | `database/log_streamer.py` |
| `data.db` | `database/data.db` |

### 集群 B：`common/` — 公共基础设施层（6 文件）

这些文件仅使用 Python 标准库或 pydantic，**零仿真核心依赖**。

| 文件 | → 新位置 | 依赖 |
|------|----------|------|
| `exceptions.py` | `common/exceptions.py` | 无（纯 Python） |
| `log_setup.py` | `common/log_setup.py` | 仅 stdlib `logging` |
| `config.py` | `common/config.py` | 读取 `env.py`（保留在 utm_simulator） |
| `config.json` | `common/config.json` | 纯 JSON 数据 |
| `schemas.py` | `common/schemas.py` | 仅 `typing` |
| `validators.py` | `common/validators.py` | 仅 `pydantic` |

### 集群 C：`schemas/` → `data/schemas/`（4 个 JSON Schema 文件）

纯 JSON 数据文件，零 Python 依赖。

| 文件 | → 新位置 |
|------|----------|
| `schemas/airspace_schema.json` | `data/schemas/airspace_schema.json` |
| `schemas/route_schema.json` | `data/schemas/route_schema.json` |
| `schemas/scenario_schema.json` | `data/schemas/scenario_schema.json` |
| `schemas/telemetry_schema.json` | `data/schemas/telemetry_schema.json` |

### 集群 D：`ai_data_gen.py` — AI 服务（1 文件）

仅使用 `requests` 库调用 LLM API，零仿真核心依赖。

| 文件 | → 新位置 |
|------|----------|
| `ai_data_gen.py` | `services/ai/ai_data_gen.py` |

---

## 二、不可移出文件（深度耦合仿真核心，必须保留）

| 文件 | 不可移出原因 |
|------|-------------|
| `sim_manager.py` | 导入 `RedisClient`, `KafkaProducerClient`, `Simulator`, `UAV_IDENTIFIERS` — **编排核心** |
| `web_server.py` | 导入 `RedisClient`, `KafkaProducerClient`, `sim_manager`, `env` — **Web 入口** |
| `web_data_gen_bridge.py` | 通过命名空间钩子调用 `tools/` 脚本 — **工具桥接** |
| `situation_monitor.py` | 导入 `redis_client`, `env` — **态势监控** |
| `cli.py` | 导入 `sim_manager`, `redis_client`, `kafka_proc` — **CLI 入口** |
| `sim_api_bridge.py` | 导入 `redis_client` + 外部 `atc_api_autotest` — **ATC API 桥接** |
| `ai_integration.py` | 导入 `redis_client`, `kafka_proc` — **AI 集成入口** |
| `test_e2e_sim.py` | 导入 `sim_api_bridge`, `redis_client`, `kafka_proc` — **端到端测试** |
| `simulation_core0609.py` | `simulation_core.py` 的旧版参考副本 |
| `kafka_proc_1.0.py` | `kafka_proc.py` 的旧版参考副本 |

---

## 三、目标目录架构

```
atc_test_platfrom/
├── utm_simulator/                 # 仿真核心（接近原始架构）
│   ├── main.py                    # [原] 动态仿真入口
│   ├── simulation_core.py         # [原] 仿真引擎
│   ├── redis_client.py            # [原] Redis 客户端
│   ├── kafka_proc.py              # [原] Kafka 客户端
│   ├── env.py                     # [原] 连接配置
│   ├── pylib/                     # [原] C++ UTM 封装
│   ├── tools/                     # [原] 工具脚本集
│   ├── _source/                   # [原] 数据规范
│   ├── packages/                  # [原] wheel 包
│   ├── tests/                     # [新] 单元测试（保留）
│   │
│   ├── sim_manager.py             # [不可移] 统一编排层
│   ├── web_server.py              # [不可移] Flask Web 入口
│   ├── web_data_gen_bridge.py     # [不可移] Web→tools 桥接
│   ├── situation_monitor.py       # [不可移] 态势监控
│   ├── cli.py                     # [不可移] CLI 入口
│   ├── sim_api_bridge.py          # [不可移] ATC API 桥接
│   ├── ai_integration.py          # [不可移] AI 集成入口
│   ├── test_e2e_sim.py            # [不可移] E2E 测试
│   ├── simulation_core0609.py     # [旧] 参考副本
│   ├── kafka_proc_1.0.py          # [旧] 参考副本
│   │
│   ├── uav_identifiers_extended.py
│   ├── lines.json
│   ├── deploy.sh / deploy_repeat.sh
│   ├── requirements.txt / pytest.ini
│   ├── env.md / env.py.example
│   ├── .gitignore / .cursorrules
│   └── README.md / CLAUDE.md / AGENTS.md / 使用手册.md
│
├── database/                      # [新] 数据持久化模块
│   ├── __init__.py                # 统一导出
│   ├── db_manager.py              # SQLite CRUD
│   ├── env_manager.py             # 多环境配置管理
│   ├── json_data_manager.py       # JSON文件管理（DB + data/mock/ 同步）
│   ├── scheduler.py               # Cron 定时任务调度
│   ├── log_streamer.py            # 实时日志流（内存 + MySQL）
│   └── data.db                    # SQLite 数据库文件
│
├── common/                        # [新] 公共基础设施
│   ├── __init__.py                # 统一导出
│   ├── exceptions.py              # 语义化异常层次
│   ├── log_setup.py               # 结构化日志初始化
│   ├── config.py                  # 配置管理（dataclass 层次）
│   ├── config.json                # 运行时配置
│   ├── schemas.py                 # TypedDict 类型定义
│   └── validators.py              # Pydantic 数据校验
│
├── web/                           # [第一轮] 前端资源（不变）
├── data/                          # [本轮扩展] JSON数据 + Schema 统一管理
│   ├── mock/                      # [第一轮] 模拟 JSON
│   ├── templates/                 # [第一轮] 任务模板
│   ├── uploads/                   # [第一轮] 上传文件
│   └── schemas/                   # [本轮] JSON Schema 定义（从 utm_simulator/schemas/ 移入）
│
├── services/                      # [新] 独立服务模块
│   └── ai/
│       └── ai_data_gen.py         # LLM AI 数据生成器
│
├── docker/                        # [不变]
├── docs/                          # [不变]
├── atc_api_autotest/              # [不变]
├── atc_ha_test/                   # [不变]
└── ...
```

---

## 四、实施步骤

### 步骤 1：创建新目录结构
- `database/` 目录 + `__init__.py`
- `common/` 目录 + `__init__.py`
- `services/ai/` 目录 + `__init__.py`
- `data/schemas/` 目录

### 步骤 2：移动 `database/` 集群（git mv）
- `utm_simulator/db_manager.py` → `database/db_manager.py`
- `utm_simulator/env_manager.py` → `database/env_manager.py`
- `utm_simulator/json_data_manager.py` → `database/json_data_manager.py`
- `utm_simulator/scheduler.py` → `database/scheduler.py`
- `utm_simulator/log_streamer.py` → `database/log_streamer.py`
- `utm_simulator/data.db` → `database/data.db`

### 步骤 3：移动 `common/` 集群（git mv）
- `utm_simulator/exceptions.py` → `common/exceptions.py`
- `utm_simulator/log_setup.py` → `common/log_setup.py`
- `utm_simulator/config.py` → `common/config.py`
- `utm_simulator/config.json` → `common/config.json`
- `utm_simulator/schemas.py` → `common/schemas.py`
- `utm_simulator/validators.py` → `common/validators.py`

### 步骤 4：移动 `schemas/` JSON 文件（git mv）
- `utm_simulator/schemas/*.json` → `data/schemas/*.json`（4 文件）
- 删除空的 `utm_simulator/schemas/` 目录

### 步骤 5：移动 `ai_data_gen.py`（git mv）
- `utm_simulator/ai_data_gen.py` → `services/ai/ai_data_gen.py`

### 步骤 6：创建 `__init__.py` 统一导出文件

**`database/__init__.py`**：重导出所有 database 模块
**`common/__init__.py`**：重导出所有 common 模块
**`services/__init__.py`** + **`services/ai/__init__.py`**

### 步骤 7：修正 `utm_simulator/` 内所有导入路径

这是最关键步骤。以下文件需要更新导入路径（通过在 utm_simulator 脚本开头将 `../database/` 和 `../common/` 加入 `sys.path`）：

| 文件 | 需更新的导入 |
|------|------------|
| `web_server.py` | `db_manager`→`database.db_manager`, `env_manager`→`database.env_manager`, `json_data_manager`→`database.json_data_manager`, `log_streamer`→`database.log_streamer`, `config`→`common.config`, `schemas`→`common.schemas`, `validators`→`common.validators` |
| `sim_manager.py` | `config`→`common.config`, `log_setup`→`common.log_setup`, `exceptions`→`common.exceptions` |
| `cli.py` | `config`→`common.config`, `log_setup`→`common.log_setup` |
| `log_streamer.py` | `db_manager`→`database.db_manager` (同目录省略前缀) |
| `json_data_manager.py` | `db_manager`→`database.db_manager` |
| `env_manager.py` | `db_manager`→`database.db_manager` |
| `scheduler.py` | `db_manager`→`database.db_manager` |
| `sim_api_bridge.py` | （检查是否需要更新） |
| `ai_integration.py` | （检查是否需要更新） |
| `test_e2e_sim.py` | （检查是否需要更新） |
| `tests/conftest.py` | （检查是否需要更新） |
| `tests/test_config.py` | `config`→`common.config` |
| `tests/test_schemas.py` | `schemas`→`common.schemas` |
| `tests/test_validators.py` | `validators`→`common.validators` |

### 步骤 8：修正 `database/` 模块间的内部导入

`database/` 目录内模块相互导入时，使用同包相对路径（`from .db_manager import ...` 或直接 `from db_manager import ...`）。

### 步骤 9：修正 `start_web.ps1`
保持不变（工作目录仍是 `utm_simulator/`，sys.path 在代码中追加）。

### 步骤 10：更新 Docker 配置
- Dockerfile：增加 `COPY database/ /app/database/`、`COPY common/ /app/common/`、`COPY services/ /app/services/`
- docker-compose.yml：更新 `data.db` 卷挂载路径（如有）
- .dockerignore：确保 `database/` 和 `common/` 不被排除

### 步骤 11：更新文档
- `docs/系统架构文档.md`：反映新目录结构
- `docs/utm-simulator-optimization-work-log.md`：追加本轮记录
- `docs/工作总结.md`：追加本轮记录

---

## 五、风险点与注意事项

1. **`log_streamer.py` 的 MySQL 路径**：它目前通过 `os.path.join(os.path.dirname(__file__), "..", "atc_api_autotest", "api_tools")` 引用外部模块。移动到 `database/` 后，`__file__` 位置变化，`../` 需要调整为 `../../`。

2. **`config.py` 读取 `env.py`**：`config.py` 通过 `load_config()` 读取 `env.py` 中的连接配置。移动到 `common/` 后，需确保能找到 `utm_simulator/env.py`。

3. **`json_data_manager.py` 的 `_MOCK_DIR`**：使用 `os.path.dirname(__file__)` 推导 `data/mock/` 路径。移动到 `database/` 后需调整为 `../data/mock/`。

4. **`schemas.py`/`validators.py` 类型引用**：`web_server.py` 和其他文件可能直接引用 `schemas.py` 中的 TypedDict 类型。迁移后需在 `common/__init__.py` 中重新导出。

5. **pytest 测试路径**：`tests/` 目录在 `utm_simulator/` 内，测试代码导入 `config`、`schemas`、`validators` 等模块。需在 `conftest.py` 中添加 `common/` 到 sys.path。

6. **所有 `_root` / `sys.path.insert` 模式**：`utm_simulator/` 内大量脚本使用 `_root = os.path.dirname(os.path.abspath(__file__))` + `sys.path.insert(0, _root)` 来导入同级模块。移出后，这些模块不再在同一目录，需追加 `../database` 和 `../common` 到 sys.path。

---

## 六、验证方案

1. **目录存在性验证**：确认所有新目录已创建，旧位置已清空
2. **导入测试**：`cd utm_simulator && python -c "from web_server import app; from sim_manager import SimulationManager"`
3. **单元测试**：`cd utm_simulator && python -m pytest tests/ -v`
4. **路径解析测试**：验证 `database/` 和 `common/` 模块中的相对路径正确
5. **Docker 构建测试**：确认镜像内新目录结构完整

---

## 七、改动文件统计

| 操作 | 数量 | 涉及内容 |
|------|------|---------|
| 新建目录 | 4 | `database/`, `common/`, `services/ai/`, `data/schemas/` |
| 移动文件 | 14 | 5个database模块 + 6个common模块 + 4个JSON schema + 1个AI + data.db |
| 创建 `__init__.py` | 3 | database, common, services/ai |
| 修改 Python（导入路径） | ~10 | web_server, sim_manager, cli, log_streamer等 + tests/ |
| 修改配置 | 2 | Dockerfile, docker-compose.yml |
| 修改文档 | 3 | 系统架构, work-log, 工作总结 |
