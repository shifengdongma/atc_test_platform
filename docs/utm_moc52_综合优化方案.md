# utm_moc52 综合优化方案

> **版本**: v1.0
> **日期**: 2026-07-05
> **目标**: 在现有代码基础上实现测试接口自动化、测试文档自动生成、AI接入处理三大能力

---

## 一、现状分析

### 1.1 项目概况

utm_moc52 是一个 UTM（无人机交通管理）仿真与数据注入服务，核心功能是通过 Python 仿真多架无人机飞行，将飞行计划写入 Redis、实时遥测写入 Kafka，供下游 ATC Dashboard 和 UTM 算法消费。

| 维度 | 当前状态 |
|------|---------|
| 语言 | Python 3.10+ |
| 消息队列 | Kafka (kafka-python) |
| 缓存 | Redis (redis-py) |
| C++集成 | ctypes 绑定 (pylib/) |
| 部署 | Shell 脚本 + Dolphin K8s 平台 |
| 测试 | **无任何测试文件** |
| API | **无 REST/CLI 接口** |
| 日志 | **全部使用 print()** |
| 配置 | **密码硬编码在 env.py** |
| 文档 | 3 份系统文档 (较完善) |

### 1.2 关键问题清单

| # | 问题 | 影响 | 严重程度 |
|---|------|------|---------|
| 1 | DataSource/DataFlow 在 main.py、run_kafka.py、run_kafka_alive.py 中重复实现 3 次 | 修复 bug 需改 3 处，容易遗漏 | 高 |
| 2 | 零测试基础设施 | 无法进行自动化回归测试 | 高 |
| 3 | 无 REST API 或 CLI | 自动化测试脚本无法控制仿真 | 高 |
| 4 | 全部使用 print() 输出 | 日志无法被程序解析，AI 难以分析 | 中 |
| 5 | 密码硬编码在 env.py | 安全风险，多环境切换需手动改代码 | 中 |
| 6 | 类型注解大量使用 Dict[str, Any] | AI 工具无法推断数据结构 | 中 |
| 7 | 无输入验证 | 错误数据静默写入 Redis/Kafka | 中 |
| 8 | 无监控指标 | 运行状态不透明，排查困难 | 低 |
| 9 | 无自动化文档生成 | 接口变更后文档需手动同步 | 低 |

### 1.3 现有可复用资产

以下模块质量较好，优化时应保留并增强而非重写：

- `simulation_core.py` — DroneAgent 6 状态机、Simulator 仿真引擎、NFZ 生成算法，约 1210 行，逻辑完整
- `kafka_proc.py` — 双集群同步、批量发送、latest-offset 启动策略，设计合理
- `redis_client.py` — `get_value_by_key()` 自动类型检测，设计优雅
- `tools/trajectory_accuracy.py` — 轨迹预测精度评估 (MAE/RMSE/ADE/FDE) + HTML 报告
- `tools/run_plan.py` — Redis 驱动仿真 + 键空间通知，模式成熟
- `pylib/structs.py` + `pylib/engine.py` — ctypes C++ 绑定，二进制兼容良好

---

## 二、优化总体架构

### 2.1 目标架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                          API 层 (新增)                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ FastAPI Server   │  │ CLI (argparse)   │  │ OpenAPI/Swagger  │   │
│  │ (REST 接口)       │  │ (命令行接口)      │  │ (自动文档)        │   │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘   │
│           │                     │                      │             │
│           └─────────────────────┼──────────────────────┘             │
│                                 ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              SimulationManager (新增 - 统一编排)                │   │
│  │  替代 DataSource + DataFlow，统一 main.py / run_kafka_alive   │   │
│  │  生命周期管理、场景注入、状态查询、数据验证                      │   │
│  └──────────────────────────────┬───────────────────────────────┘   │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │
┌─────────────────────────────────┼───────────────────────────────────┐
│                         核心层                                       │
│  ┌──────────────────┐  ┌────────┴──────────┐  ┌──────────────────┐ │
│  │ config.py (新增)  │  │ simulation_core   │  │ schemas.py (新增) │ │
│  │ 配置管理+验证     │  │ (现有 - 增强类型)  │  │ TypedDict 模式   │ │
│  └──────────────────┘  └───────────────────┘  └──────────────────┘ │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ log_setup.py(新增)│  │ validators.py    │  │ exceptions.py    │ │
│  │ 结构化 JSON 日志  │  │ (新增) 数据验证   │  │ (新增) 异常体系  │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼───────────────────────────────────┐
│                         数据接入层 (现有 - 增强)                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ redis_client.py  │  │ kafka_proc.py    │  │ pylib/           │ │
│  │ (增强错误处理)    │  │ (增强日志)        │  │ (不变)           │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────┼───────────────────────────────────┐
│                         测试层 (全新)                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ tests/            │  │ tools/            │  │ docs/ (新增)     │ │
│  │ pytest 测试套件    │  │ generate_docs.py  │  │ 自动生成文档     │ │
│  │ (80%+ 覆盖率)     │  │ data_check.py     │  │ API/数据格式     │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 优化四大支柱

| 支柱 | 目标 | 核心交付物 |
|------|------|-----------|
| **配置与基础设施** | 安全可切换的配置、可解析的日志、统一的异常处理 | config.py, log_setup.py, exceptions.py |
| **测试接口自动化** | REST API 控制仿真、CLI 命令行、数据验证框架 | api/server.py, cli.py, validators.py, SimulationManager |
| **测试文档自动生成** | OpenAPI 文档、数据格式文档、测试用例文档、Mermaid 图表 | tools/generate_docs.py, mkdocs.yml, schemas/ |
| **AI 接入处理** | 类型化模式、语义代码注释、JSON Schema、结构化提示规则 | schemas.py, schemas/*.json, CLAUDE.md 增强 |

---

## 三、阶段一：基础设施优化 (预计 3-4 天)

### 3.1 配置管理重构 — `config.py` [新建]

**问题**: 当前 `env.py` 是纯 Python 文件，密码硬编码，多环境切换需手动修改代码。

**方案**: 创建 `config.py`，支持多层配置加载（YAML → 环境变量 → env.py 回退）。

```python
# config.py 核心结构
@dataclass
class RedisConfig:
    host: str = "10.165.78.1"
    port: int = 21002
    password: str = ""       # 优先从环境变量 UTM_REDIS_PASSWORD 读取
    db: int = 0

@dataclass
class KafkaConfig:
    bootstrap_servers: str = "10.165.77.69:30012"
    bootstrap_servers_mirror: Optional[str] = None
    producer_flush_timeout: float = 1.0

@dataclass
class SimulationConfig:
    target_drones: int = 10
    sim_center_lat: float = 40.0196
    sim_center_lon: float = 116.5641
    sim_radius_m: float = 800.0
    cruise_speed: float = 30.0
    climb_rate: float = 15.0
    ids_index: int = 1

@dataclass
class AppConfig:
    env: str = "dev"
    log_level: str = "INFO"
    redis: RedisConfig = field(default_factory=RedisConfig)
    kafka: KafkaConfig = field(default_factory=KafkaConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)

def load_config(env_name: Optional[str] = None) -> AppConfig:
    """优先级: 参数 > 环境变量 UTM_ENV > env.py 兼容"""
```

**涉及文件**:
- [新建] `config.py` — 约 150 行
- [新建] `config/default.yaml` — 默认配置模板
- [修改] `env.py` — 保留兼容但标记 deprecated

### 3.2 结构化日志 — `log_setup.py` [新建]

**问题**: 全项目使用 `print()`，AI 无法解析，日志难以过滤和聚合。

**方案**: 创建集中式日志配置，支持控制台可读格式 + JSON 结构化格式双输出。

```python
# log_setup.py 核心结构
class JsonFormatter(logging.Formatter):
    """输出 AI 友好 JSON 日志"""
    def format(self, record):
        return json.dumps({
            "ts": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "module": record.module,
            "line": record.lineno,
            "msg": record.getMessage(),
            "thread": record.threadName,
        }, ensure_ascii=False)

def setup_logging(config: AppConfig) -> logging.Logger:
    """根据配置设置根日志器"""
```

**涉及文件**:
- [新建] `log_setup.py` — 约 80 行
- [修改] `main.py`, `simulation_core.py`, `kafka_proc.py`, `redis_client.py`, 所有 `tools/*.py` — 将 `print()` 替换为 `logger.info/warning/error/debug`

### 3.3 语义异常体系 — `exceptions.py` [新建]

**问题**: 代码中大量使用 `except Exception` 裸捕获，AI 无法根据异常类型给出针对性建议。

**方案**: 建立清晰的异常层次结构。

```python
class UTMSimulationError(Exception): pass
class ConfigError(UTMSimulationError): pass
class ConnectionError(UTMSimulationError): pass
    class RedisConnectionError(ConnectionError): pass
    class KafkaConnectionError(ConnectionError): pass
class DataError(UTMSimulationError): pass
    class ValidationError(DataError): pass
    class SchemaError(DataError): pass
class SimulationError(UTMSimulationError): pass
    class StateError(SimulationError): pass
    class StepError(SimulationError): pass
```

**涉及文件**:
- [新建] `exceptions.py` — 约 60 行

---

## 四、阶段二：测试接口自动化 (预计 6-8 天)

### 4.1 统一仿真管理器 — `sim_manager.py` [新建]

**问题**: `DataSource` + `DataFlow` 逻辑在 `main.py`(228行)、`run_kafka_alive.py`(248行)、`run_kafka.py`(271行) 中重复实现，仅细节不同。

**方案**: 提取为 `SimulationManager` 类，统一动态仿真、预生成注入、Redis 驱动三种模式。

```python
class SimulationManager:
    """
    统一仿真编排器。
    替代 main.py、run_kafka.py、run_kafka_alive.py 中的 DataSource+DataFlow。
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.redis = RedisClient(...)
        self.kafka_producer = KafkaProducerClient(...)
        self.kafka_consumer = KafkaConsumerClient(...)
        self.simulator = Simulator()
        self._stats = SimulationStats()

    # === 生命周期 ===
    def start(self, mode: str = "dynamic", target_drones: int = None): ...
    def stop(self, timeout: float = 5.0): ...
    def pause(self): ...
    def resume(self): ...

    # === 场景管理 ===
    def inject_scenario(self, scenario: dict) -> int: ...
    def inject_drone_plan(self, uid: str, plan: dict) -> bool: ...

    # === 状态查询 ===
    def get_status(self) -> SimulationStatus: ...
    def get_drones(self) -> List[DroneInfo]: ...
    def get_drone(self, uid: str) -> Optional[DroneInfo]: ...

    # === 数据验证 ===
    def verify_redis_data(self) -> List[str]: ...     # 返回错误列表
    def verify_kafka_message(self, topic: str) -> List[str]: ...
```

**涉及文件**:
- [新建] `sim_manager.py` — 约 350 行
- [重写] `main.py` — 简化为 SimulationManager 的薄包装 (~40 行)
- [重写] `tools/run_kafka_alive.py` — 使用 SimulationManager(mode="replay")
- [重写] `tools/run_kafka.py` — 使用 SimulationManager(mode="oneshot")

### 4.2 REST API 服务器 — `api/server.py` [新建]

**问题**: 无接口可调用，自动化测试脚本无法控制仿真器。

**方案**: 基于 FastAPI 构建 REST API，自动生成 OpenAPI 文档。

```python
# api/server.py 端点设计
app = FastAPI(title="utm_moc52 Control API", version="2.0.0")

# ---- 仿真控制 ----
POST   /api/v1/simulation/start          # 启动仿真 (参数: count, mode)
POST   /api/v1/simulation/stop           # 停止仿真
POST   /api/v1/simulation/pause          # 暂停仿真
POST   /api/v1/simulation/resume         # 恢复仿真
GET    /api/v1/simulation/status          # 运行状态 (活跃机数/运行时间/消息数)

# ---- 无人机管理 ----
GET    /api/v1/drones                     # 列出所有无人机 UID 和状态
GET    /api/v1/drones/{uid}               # 单架无人机详情 (位置/速度/航线)
POST   /api/v1/drones/{uid}/plan          # 为指定无人机注入飞行计划
DELETE /api/v1/drones/{uid}               # 移除指定无人机

# ---- 场景管理 ----
POST   /api/v1/scenarios                  # 加载测试场景 (多机+航线+禁飞区)
GET    /api/v1/scenarios/current          # 查看当前加载的场景

# ---- 数据查询 (测试验证用) ----
GET    /api/v1/data/redis/{key}           # 读取 Redis 任意键
GET    /api/v1/data/redis/route/{uid}     # 查询指定无人机 Redis 航线
GET    /api/v1/data/kafka/{topic}?n=10    # 消费 Kafka 最新 N 条消息
POST   /api/v1/data/kafka/{topic}         # 向 Kafka 发送测试消息

# ---- 数据验证 (测试自动化关键) ----
POST   /api/v1/validate/scenario          # 验证场景 JSON 格式
POST   /api/v1/validate/telemetry         # 验证遥测数据格式
GET    /api/v1/validate/redis-integrity   # 检查 Redis 数据完整性
```

**端点分组与用途**:

| 端点组 | 用途 | 典型调用方 |
|--------|------|-----------|
| `/simulation/*` | 仿真生命周期控制 | CI/CD 流水线、自动化测试框架 |
| `/drones/*` | 单机操作与查询 | 测试用例注入特定无人机场景 |
| `/scenarios/*` | 批量场景加载 | 回归测试、压力测试 |
| `/data/*` | 下游数据验证 | 断言 Redis/Kafka 数据正确性 |
| `/validate/*` | 数据格式检查 | 预提交钩子、CI 检查 |

**涉及文件**:
- [新建] `api/__init__.py`
- [新建] `api/server.py` — FastAPI 应用 (~200 行)
- [新建] `api/models.py` — Pydantic 请求/响应模型 (~150 行)
- [新建] `api/routes_simulation.py` — 仿真控制路由
- [新建] `api/routes_drones.py` — 无人机管理路由
- [新建] `api/routes_scenarios.py` — 场景管理路由
- [新建] `api/routes_data.py` — 数据查询路由

### 4.3 CLI 命令行接口 — `cli.py` [新建]

**问题**: 无 API 环境（如生产容器内）也需要可编程控制。

**方案**: 基于 argparse 构建 CLI，与 API 共享同一个 SimulationManager 后端。

```bash
# CLI 命令一览
python cli.py start --count 50 --mode dynamic
python cli.py stop
python cli.py status --json                          # JSON 输出便于脚本解析
python cli.py drone list
python cli.py drone get DJI1MAV101A2B3C4D5E6
python cli.py drone inject DJI1MAV101A2B3C4D5E6 --plan plan.json
python cli.py scenario load scenario.json
python cli.py redis get BIZ_DATA:UAV_ROUTE
python cli.py kafka send uav_runtime_data --file msg.json
python cli.py kafka consume uav_runtime_trace --count 10 --timeout 30
python cli.py validate scenario.json                 # 验证场景文件
python cli.py check redis --key BIZ_DATA:UAV_ROUTE   # 数据完整性检查
```

**涉及文件**:
- [新建] `cli.py` — 约 200 行

### 4.4 数据验证框架 — `validators.py` [新建]

**问题**: 注入的数据无格式校验，错误数据静默写入导致下游异常。

**方案**: 基于 Pydantic 构建数据验证器，覆盖所有数据格式。

```python
# validators.py 核心
class RouteSegmentValidator(BaseModel):
    sequence: int = Field(ge=0)
    type: int = Field(ge=1, le=3)
    segmentStartLon: float = Field(ge=-180, le=180)
    segmentStartLat: float = Field(ge=-90, le=90)
    # ... 所有必要字段

class TelemetryValidator(BaseModel):
    uniqueProductIdentificationCode: str = Field(min_length=1, max_length=64)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    geodeticAltitude: float = Field(ge=-500, le=20000)  # 无人机高度范围
    speed: float = Field(ge=0, le=500)                   # m/s
    operatingStatus: int = Field(ge=0, le=5)
    # ... 22+ 字段完整校验

def validate_redis_route(data: dict) -> Tuple[bool, List[str]]: ...
def validate_telemetry(data: dict) -> Tuple[bool, List[str]]: ...
def validate_scenario(data: dict) -> Tuple[bool, List[str]]: ...
```

**涉及文件**:
- [新建] `validators.py` — 约 200 行
- [新建] `tools/data_check.py` — 独立数据完整性检查脚本 (~100 行)

### 4.5 测试套件 — `tests/` [新建]

**问题**: 项目零测试，无法进行回归验证。

**方案**: 建立完整 pytest 测试体系，分层覆盖。

```
tests/
├── conftest.py                    # pytest fixtures (mock Redis/Kafka 客户端)
├── test_drone_agent.py            # DroneAgent 状态机 (~30 用例)
├── test_simulator.py              # Simulator 计划生成/步进 (~20 用例)
├── test_kafka_proc.py             # Kafka 生产者/消费者 (~15 用例)
├── test_redis_client.py           # Redis 客户端 (~10 用例)
├── test_sim_manager.py            # SimulationManager 生命周期 (~15 用例)
├── test_validators.py             # 数据验证器 (~15 用例)
├── test_data_flow.py              # 端到端数据流 (~10 用例)
└── test_api_endpoints.py          # API 端点集成测试 (~20 用例)
```

**测试覆盖策略**:

| 模块 | 覆盖重点 | 预期覆盖率 |
|------|---------|-----------|
| DroneAgent | 6 状态转换、速度平滑、制动距离 | 90%+ |
| Simulator | 计划生成、步进、禁飞区 | 85%+ |
| kafka_proc | 双集群发送、超时、latest-offset | 85%+ |
| redis_client | 类型检测、JSON 解析 | 85%+ |
| validators | 边界值、异常格式 | 95%+ |
| SimulationManager | 启停、pause/resume、场景注入 | 80%+ |
| API Endpoints | 请求/响应格式、错误码 | 80%+ |

**涉及文件**:
- [新建] `tests/conftest.py` — pytest 配置 + fixtures (~80 行)
- [新建] 8 个测试文件 — 共约 1000 行
- [新建] `pytest.ini` — pytest 配置

---

## 五、阶段三：AI 接入处理优化 (预计 5-6 天)

### 5.1 类型化数据模式 — `schemas.py` [新建]

**问题**: 大量 `Dict[str, Any]` 使 AI 工具无法推断数据结构。

**方案**: 用 TypedDict 定义所有共享数据结构。

```python
# schemas.py 核心
from typing import TypedDict, List, Optional, Literal

class RouteSegmentDict(TypedDict):
    sequence: int
    type: int
    segmentStartLon: float
    segmentStartLat: float
    segmentEndLon: float
    segmentEndLat: float
    segmentStartHeight: float
    segmentEndHeight: float
    segmentProtectHeight: float
    segmentProtectHeightType: int
    segmentWidth: float

class FlightPlanEntryDict(TypedDict):
    flightPlanId: int
    planTakeoffTime: float
    planLandTime: float
    flightTaskId: int
    flightTaskName: str
    routeList: List[RouteSegmentDict]

class DroneRouteDict(TypedDict):
    uniqueProductIdentificationCode: str
    flightPlanList: List[FlightPlanEntryDict]

class TelemetryDict(TypedDict):
    uniqueProductIdentificationCode: str
    realNameRegistrationSign: str
    longitude: float
    latitude: float
    geodeticAltitude: float
    speed: float
    trackAngle: float
    verticalSpeed: float
    operatingStatus: int
    sourceType: int
    timestamp: int
    # ... 所有 22+ 字段

# 枚举类型
OperatingStatus = Literal[0, 1, 2, 3, 4, 5]  # IDLE..FINISHED
SourceType = Literal[1, 2]                      # 1=无人机, 2=ADS-B
NFZType = Literal["noDrone", "limited", "danger", "segregated"]
```

**涉及文件**:
- [新建] `schemas.py` — 约 200 行
- [修改] `main.py`, `simulation_core.py`, 所有 `tools/*.py` — 导入并使用 TypedDict

### 5.2 JSON Schema 定义 — `schemas/` [新建]

**问题**: 下游系统和 AI 工具需要标准化的数据格式描述。

**方案**: 生成 JSON Schema 文件，兼容各种 AI/工具生态。

```
schemas/
├── route_schema.json           # 飞行计划 JSON Schema
├── telemetry_schema.json       # 遥测数据 JSON Schema
├── airspace_schema.json        # 空域数据 JSON Schema
└── scenario_schema.json        # 测试场景 JSON Schema
```

**涉及文件**:
- [新建] `schemas/route_schema.json`
- [新建] `schemas/telemetry_schema.json`
- [新建] `schemas/airspace_schema.json`
- [新建] `schemas/scenario_schema.json`

### 5.3 语义代码注释增强

**任务**: 为核心模块添加完整的 Google 风格文档字符串。

**重点模块**:
- `simulation_core.py` — DroneAgent、Simulator 的所有公共方法
- `kafka_proc.py` — KafkaProducerClient、KafkaConsumerClient
- `redis_client.py` — RedisClient
- `sim_manager.py` — SimulationManager (新建时即带文档)

**文档字符串标准格式**:
```python
def step(self, step_size_sec: float = 1.0,
         sim_time: Optional[float] = None) -> List[TelemetryPayload]:
    """
    将仿真推进一步。

    Args:
        step_size_sec: 时间步长(秒)，默认1.0。典型值0.5-5.0。
        sim_time: 仿真当前时间戳。None则使用系统时间。
            用于确定性重放测试。

    Returns:
        所有非IDLE代理的遥测列表。空仿真返回空列表。

    Raises:
        StepError: 仿真步执行异常时抛出。

    Example:
        >>> sim = Simulator()
        >>> sim.generate_plan()
        >>> payloads = sim.step(1.0, sim_time=1000000.0)
        >>> len(payloads) > 0
        True
    """
```

### 5.4 AI 编码规则增强 — `CLAUDE.md` 更新

在现有 `CLAUDE.md` 中添加 AI 协作规则：

```markdown
## AI 编码协作规则

### 数据模式
- 所有数据结构必须定义为 TypedDict 或 Pydantic 模型，禁止裸 dict
- 字段增删必须同步更新 schemas.py 和对应的 JSON Schema 文件

### 错误处理
- 从 exceptions.py 引发语义化异常，禁止裸 raise Exception
- 日志使用 logging.getLogger(__name__)，禁止 print()

### 接口变更
- API 端点变更必须同步更新 api/models.py 中的 Pydantic 模型
- OpenAPI 文档自动生成，无需手动维护

### 测试要求
- 新增 public 方法必须有对应的 pytest 用例
- 数据验证逻辑必须有边界值测试
- PR 前运行 pytest --cov 确保覆盖率不下降

### 配置
- 所有环境差异通过 config.py + 环境变量控制
- 密码/密钥禁止写入代码文件
```

---

## 六、阶段四：测试文档自动生成 (预计 4-5 天)

### 6.1 文档自动生成工具 — `tools/generate_docs.py` [新建]

**功能**:
1. 从 TypedDict 生成 JSON Schema → Markdown 表格
2. 从 FastAPI 路由生成 API 文档
3. 从 pytest 测试文件生成测试用例索引
4. 生成 Mermaid 流程图 (数据流、状态机、部署流程)
5. 自动更新 CLAUDE.md 中的项目统计

```bash
# 用法
python tools/generate_docs.py --output-dir docs/
python tools/generate_docs.py --api-only         # 仅生成 API 文档
python tools/generate_docs.py --schemas-only     # 仅生成数据格式文档
python tools/generate_docs.py --tests-only       # 仅生成测试用例文档
```

**涉及文件**:
- [新建] `tools/generate_docs.py` — 约 300 行

### 6.2 自动生成文档类型

| 文档 | 触发方式 | 输出 | 用途 |
|------|---------|------|------|
| API 参考 | 读取 FastAPI OpenAPI schema | `docs/api_reference.md` | 测试人员查阅接口 |
| 数据格式 | 读取 schemas.py + JSON Schema | `docs/data_formats.md` | 对接方查阅字段定义 |
| 测试用例 | 扫描 tests/ 目录 + pytest --co | `docs/test_cases.md` | 了解测试覆盖情况 |
| 消息流图 | 硬编码 Mermaid 模板 | `docs/message_flow.md` | 新人理解数据流 |
| 状态机图 | 从代码注释提取 | `docs/state_machine.md` | 理解 DroneAgent 行为 |

### 6.3 FastAPI 自动文档 (零成本)

FastAPI 自带 OpenAPI/Swagger 文档，启动 API 后即可访问：
- `http://host:8000/docs` — Swagger UI (可交互测试)
- `http://host:8000/redoc` — ReDoc UI (更美观的文档)
- `http://host:8000/openapi.json` — 原始 OpenAPI Schema (AI 工具可直接消费)

这些文档无需额外开发，**仅需启动 API 服务器即可获得**。

---

## 七、实施路线图

```
第 1-3 天  ████████ 阶段一: 基础设施
           ├── config.py (配置管理)
           ├── log_setup.py (结构化日志)
           └── exceptions.py (异常体系)

第 4-11 天 ████████████████████ 阶段二: 测试接口自动化
           ├── 第 4-5 天: schemas.py + validators.py
           ├── 第 6-8 天: sim_manager.py + 重写 main.py/工具
           ├── 第 9-10 天: api/server.py + cli.py
           └── 第 11 天: tests/ 测试套件

第 12-16 天 ████████████ 阶段三: AI 接入处理
            ├── 第 12-13 天: schemas/*.json (JSON Schema)
            ├── 第 14-15 天: 代码文档字符串增强
            └── 第 16 天: CLAUDE.md AI 规则更新

第 17-20 天 ████████████ 阶段四: 文档自动生成
            ├── 第 17-18 天: tools/generate_docs.py
            ├── 第 19 天: docs/ 文档生成 + 验证
            └── 第 20 天: 端到端集成测试 + 示例场景
```

---

## 八、验证方案

### 8.1 测试接口自动化验证

```bash
# 1. 启动 API 服务器
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000 &

# 2. API 健康检查
curl http://localhost:8000/health

# 3. 通过 API 加载测试场景
curl -X POST http://localhost:8000/api/v1/scenarios \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/sample_scenario.json

# 4. 启动仿真
curl -X POST "http://localhost:8000/api/v1/simulation/start?count=5"

# 5. 验证 Redis 数据
curl http://localhost:8000/api/v1/data/redis/BIZ_DATA:UAV_ROUTE

# 6. 验证 Kafka 消息
curl "http://localhost:8000/api/v1/data/kafka/uav_runtime_data?n=5"

# 7. CLI 等效操作
python cli.py status --json
python cli.py check redis --key BIZ_DATA:UAV_ROUTE

# 8. 运行测试套件
pytest tests/ -v --cov=. --cov-report=html
```

### 8.2 文档自动生成验证

```bash
# 生成全部文档
python tools/generate_docs.py --output-dir docs/

# 验证 OpenAPI 文档可访问
curl http://localhost:8000/openapi.json | python -m json.tool

# 验证 Swagger UI
open http://localhost:8000/docs
```

### 8.3 AI 接入验证

```bash
# 验证 JSON Schema 合法性
pip install check-jsonschema
check-jsonschema --schemafile schemas/route_schema.json mock/redis_route.json
check-jsonschema --schemafile schemas/telemetry_schema.json mock/kafka_data.json

# 验证 TypedDict 与 JSON Schema 一致性
python -c "from schemas import DroneRouteDict; print(DroneRouteDict.__annotations__)"

# 验证日志 JSON 格式
python main.py 2>&1 | head -5 | python -c "import sys,json; [json.loads(l) for l in sys.stdin]"
```

---

## 九、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 重构 DataSource 破坏生产部署 | 高 | SimulationManager 与旧代码并行运行，通过 mode 参数切换 |
| ctypes 内存问题测试难复现 | 中 | 纯 Python 逻辑用单元测试，ctypes 相关用集成测试+标记 skip |
| FastAPI 增加新依赖 | 低 | API 服务器可选启动，核心仿真独立运行无需 FastAPI |
| 文档字符串增强引入不一致 | 低 | 制定模板，通过 code review 保证一致性 |
| 线上容器不支持 YAML | 低 | config.py 以 env.py 为回退，YAML 是增强非替代 |

---

## 十、关键交付物汇总

| # | 文件 | 类型 | 行数(估) | 优先级 |
|---|------|------|---------|--------|
| 1 | `config.py` | 新建 | 150 | P0 |
| 2 | `log_setup.py` | 新建 | 80 | P0 |
| 3 | `exceptions.py` | 新建 | 60 | P0 |
| 4 | `schemas.py` | 新建 | 200 | P0 |
| 5 | `sim_manager.py` | 新建 | 350 | P0 |
| 6 | `api/server.py` | 新建 | 200 | P1 |
| 7 | `api/models.py` | 新建 | 150 | P1 |
| 8 | `api/routes_*.py` | 新建(4个) | 300 | P1 |
| 9 | `cli.py` | 新建 | 200 | P1 |
| 10 | `validators.py` | 新建 | 200 | P1 |
| 11 | `tests/*.py` | 新建(8个) | 1000 | P1 |
| 12 | `schemas/*.json` | 新建(4个) | 200 | P2 |
| 13 | `tools/generate_docs.py` | 新建 | 300 | P2 |
| 14 | `tools/data_check.py` | 新建 | 100 | P2 |
| 15 | `main.py` | 重写 | ~40 | P0 |
| 16 | `tools/run_kafka_alive.py` | 重写 | ~100 | P0 |
| 17 | `tools/run_kafka.py` | 重写 | ~80 | P1 |
| 18 | `CLAUDE.md` | 更新 | +30 | P2 |
| 19 | 全部 `*.py` | 修改 | - | P1 |
| 20 | `pytest.ini` | 新建 | 20 | P1 |

**总预计新增代码**: ~3500 行 (含测试)
**总预计修改代码**: ~200 行 (重写 main.py 等入口)
**总工期**: 约 20 个工作日
