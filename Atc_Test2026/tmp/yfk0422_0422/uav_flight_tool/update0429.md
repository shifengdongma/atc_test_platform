# UAV 飞行数据工具 - 整合设计文档

## 一、项目背景与整合目的

### 1.1 原有两个项目

| 项目 | 路径 | 核心功能 | 优势 | 不足 |
|------|------|----------|------|------|
| `uav_emitter` | `uav_emitter/` | 加载预定义 JSON 轨迹文件，场景化管理发送 | 自定义轨迹、场景配置灵活、时间戳模式多样 | 无物理仿真、单线程、无法批量性能测试 |
| `utm_随机模拟飞行数据` | `utm_随机模拟飞行数据/` | 随机生成飞行计划，物理仿真后发送 | 多线程3000架并发、动力学仿真、动态流量维持、Redis航线写入 | 无法自定义轨迹、配置分散在代码中 |

### 1.2 整合目标

将两个项目整合为统一的 **`uav_flight_tool`**，通过配置文件切换运行模式：

1. **场景模式** (`scene`)：原 `uav_emitter` 功能，加载自定义 JSON 轨迹
2. **仿真模式** (`simulation`)：原 `main_multi.py` 功能，随机生成+物理仿真
3. **压力测试模式** (`stress_test`)：原 `main_multi2.py` 功能，3000架高性能测试

## 二、整合架构设计

### 2.1 目录结构

```
uav_flight_tool/
├── main.py                          # 统一入口脚本
├── config.yaml                      # 统一配置文件
├── update0429.md                    # 本设计文档
├── requirements.txt                 # Python依赖
├── core/                            # 核心模块
│   ├── __init__.py
│   ├── config_manager.py            # 配置管理器（统一读取config.yaml）
│   ├── kafka_client.py              # Kafka客户端（支持kafka-python/confluent切换）
│   ├── redis_client.py              # Redis客户端
│   └── aircraft_name_generator.py   # 航空器名称生成器（预留扩展）
├── modes/                           # 运行模式
│   ├── __init__.py
│   ├── base_mode.py                 # 模式抽象基类
│   ├── scene_mode.py                # 场景模式（自定义轨迹）
│   ├── simulation_mode.py           # 仿真模式（随机仿真）
│   └── stress_test_mode.py          # 压力测试模式（3000架）
├── simulation/                      # 仿真引擎
│   ├── __init__.py
│   ├── structs.py                   # ctypes结构定义
│   └── simulation_core.py           # 物理仿真核心
├── utils/                           # 工具
│   ├── __init__.py
│   └── logger.py                    # 日志工具
└── scenes/                          # 场景目录（从uav_emitter复制）
    └── ...
```

### 2.2 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│                    (统一运行入口)                                 │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────────┐
        │场景模式   │   │仿真模式   │   │压力测试模式   │
        │scene_mode│   │simulation│   │stress_test   │
        └────┬─────┘   └────┬─────┘   └──────┬───────┘
             │              │                │
             ▼              ▼                ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐
    │场景加载器    │  │仿真核心      │  │仿真核心+发送解耦 │
    │数据加载器    │  │多线程Worker  │  │Sender线程       │
    └──────┬──────┘  └──────┬──────┘  └────────┬────────┘
           │                │                   │
           └────────────────┴───────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │Kafka客户端│   │Redis客户端 │   │名称生成器 │
    │(可切换)   │   │           │   │(预留)     │
    └──────────┘   └──────────┘   └──────────┘
```

### 2.3 设计原则

1. **单一入口**：`python main.py` 根据 `config.yaml` 中的 `mode` 自动选择运行模式
2. **配置驱动**：所有参数集中到 `config.yaml`，禁止代码中写死关键参数
3. **模式隔离**：三种模式独立实现，互不干扰，通过基类统一接口
4. **组件复用**：Kafka/Redis/名称生成器等核心组件三种模式共用
5. **预留扩展**：WebUI/GUI/名称生成器等通过配置预留接口，后续可无缝接入

## 三、运行模式详细设计

### 3.1 场景模式 (scene_mode)

**来源**：原 `uav_emitter/emitter.py`

**功能**：
- 从 `scenes/` 目录加载场景配置 (`scene.yaml`)
- 读取场景中的 UAV JSON 轨迹文件
- 按配置的时间戳模式和发射间隔发送到 Kafka
- 支持循环播放、延迟发射、部分 UAV 禁用

**核心组件**：
- `SceneLoader`：场景加载器
- `DataLoader`：JSON 数据加载器
- `Emitter`：发射控制器

**时间戳模式**：
| 模式 | 说明 |
|------|------|
| `replace` | 替换为当前时间（默认，减1000ms偏移） |
| `align` | 对齐到当前时间，保持相对间隔 |
| `preserve` | 保留原始时间戳 |

### 3.2 仿真模式 (simulation_mode)

**来源**：原 `utm_随机模拟飞行数据/main_multi.py`

**功能**：
- 多线程随机生成飞行计划
- 物理仿真（动力学、状态机）
- 动态维持目标无人机数量（落地后自动补充）
- 航线写入 Redis
- 消费 `uav_runtime_trace` topic
- 后台定时 flush Kafka

**核心组件**：
- `WorkerDataSource`：单个 Worker 的数据源
- `MultiDataFlow`：多线程数据流管理器
- `Simulator` / `DroneAgent`：仿真核心

**关键优化（已继承）**：
- Worker 启动错开 50ms + 循环随机抖动
- `_maintain_traffic()` 每轮最多补充 5 架
- 去掉强制 flush，改为后台 5 秒定时 flush

### 3.3 压力测试模式 (stress_test_mode)

**来源**：原 `utm_随机模拟飞行数据/main_multi2.py`

**功能**：
- P3：仿真与发送解耦，Worker 只负责仿真，数据入队列
- P4：使用 `confluent-kafka` (librdkafka) 替代 `kafka-python`
- 2 个独立 Sender 线程竞争消费队列
- 支持 3000 架无人机稳定 TPS

**核心组件**：
- `KafkaSenderThread`：独立发送线程
- `WorkerDataSource`：去掉 Kafka producer，改为 queue.put()
- `MultiDataFlow`：增加发送队列和 Sender 线程管理

## 四、配置说明

### 4.1 模式切换

```yaml
mode: "simulation"  # scene | simulation | stress_test
```

### 4.2 Kafka 客户端切换

```yaml
kafka:
  client_type: "kafka-python"  # kafka-python | confluent
```

### 4.3 航空器名称生成（预留）

```yaml
aircraft_name:
  enabled: false
  format: "UAV_{seq:05d}"
  start_seq: 1
```

### 4.4 WebUI / GUI 预留

```yaml
webui:
  enabled: false
  host: "0.0.0.0"
  port: 8080

gui:
  enabled: false
  theme: "dark"
```

## 五、后续开发计划

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| P0 | 航空器名称生成器实现（按格式生成、去重） | 高 |
| P1 | WebUI 实现（Flask/FastAPI + 前端页面） | 中 |
| P2 | GUI 实现（PyQt5/WebView） | 中 |
| P3 | 场景可视化（轨迹预览地图） | 低 |
| P4 | 实时监控面板（TPS、活跃数量图表） | 低 |

## 六、文件对照表

| 新文件 | 来源文件 | 说明 |
|--------|----------|------|
| `core/kafka_client.py` | `kafka_proc.py` + `kafka_proc2.py` | 合并两种客户端，支持切换 |
| `core/redis_client.py` | `redis_client.py` | 直接复用 |
| `simulation/structs.py` | `pylib/structs.py` | 直接复用 |
| `simulation/simulation_core.py` | `simulation_core.py` | 直接复用 |
| `modes/scene_mode.py` | `emitter.py` | 模块化封装 |
| `modes/simulation_mode.py` | `main_multi.py` | 模块化封装 |
| `modes/stress_test_mode.py` | `main_multi2.py` | 模块化封装 |

