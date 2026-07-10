# UTM MOC52 系统架构文档

> **项目名称**：utm_moc52 — UTM（无人机交通管理）仿真与数据注入服务  
> **技术栈**：Python 3.10+ / Redis / Kafka / C++ UTM 核心库（可选）  
> **文档版本**：v1.0  
> **生成日期**：2026-07-09

---

## 目录

1. [系统概述](#1-系统概述)
2. [总体架构](#2-总体架构)
3. [模块详解](#3-模块详解)
4. [数据流设计](#4-数据流设计)
5. [核心数据结构](#5-核心数据结构)
6. [线程模型](#6-线程模型)
7. [部署架构](#7-部署架构)
8. [运行模式](#8-运行模式)
9. [配置管理](#9-配置管理)
10. [工具脚本生态](#10-工具脚本生态)
11. [关键设计决策](#11-关键设计决策)
12. [文件目录图谱](#12-文件目录图谱)

---

## 1. 系统概述

### 1.1 项目定位

utm_moc52 是一个 **UTM（Unmanned Traffic Management）仿真与数据注入服务**。它通过 Python 仿真多架无人机的飞行过程，将**飞行计划**写入 Redis、将**实时遥测**写入 Kafka，供下游 UTM 系统、态势感知模块或算法引擎消费使用。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **无人机飞行仿真** | 支持航路点轨迹（Trajectory）和区域盘旋（Loiter/Polygon）两种任务模式 |
| **动力学仿真** | 含起飞/巡航/悬停/降落状态机，支持加减速平滑过渡、简单风扰动 |
| **飞行计划注入** | 将飞行计划写入 Redis Hash `BIZ_DATA:UAV_ROUTE` |
| **实时遥测注入** | 遥测数据按秒写入 Kafka Topic `uav_runtime_data` |
| **禁飞区管理** | 动态 4D 禁飞区（含时间窗），可写入 Redis `BIZ_DATA:AIRSPACE` |
| **C++ 算法引擎** | 可选加载 C++ 动态库，提供轨迹预测、冲突检测、偏航检测等能力 |
| **数据回放/预生成** | 支持预先生成 mock 数据（JSON 文件），再通过工具脚本注入 Redis/Kafka |

### 1.3 依赖组件

| 组件 | 用途 | 版本要求 |
|------|------|----------|
| Redis | 存储飞行计划（Hash）、空域数据（Hash） | Redis 4.5+ |
| Kafka | 实时遥测流（`uav_runtime_data`）、追踪流（`uav_runtime_trace`） | kafka-python 2.0.2+ |
| C++ UTM Core（可选） | 轨迹预测、冲突检测、偏航检测 | 通过 ctypes 调用 .so/.dll |

---

## 2. 总体架构

### 2.1 架构分层图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          【应用层】                                      │
│                                                                         │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │   main.py    │  │ tools/run_kafka  │  │ tools/run_kafka_alive    │  │
│  │  (实时仿真)   │  │   (Mock 注入)     │  │   (持续循环注入)          │  │
│  └──────┬───────┘  └────────┬─────────┘  └────────────┬─────────────┘  │
│         │                   │                          │                │
│         └───────────────────┼──────────────────────────┘                │
│                             │                                           │
│                    ┌────────▼────────┐                                  │
│                    │   DataFlow      │  ← 编排层：线程管理、生命周期      │
│                    └────────┬────────┘                                  │
│                             │                                           │
│                    ┌────────▼────────┐                                  │
│                    │   DataSource    │  ← 数据层：仿真调度、格式转换      │
│                    └────────┬────────┘                                  │
│                             │                                           │
├─────────────────────────────┼───────────────────────────────────────────┤
│                        【核心仿真层】                                     │
│                             │                                           │
│         ┌───────────────────┼───────────────────┐                       │
│         │                   │                   │                       │
│  ┌──────▼──────┐   ┌───────▼────────┐   ┌──────▼──────────┐           │
│  │  Simulator  │   │  DroneAgent    │   │  DynamicNoFlyZone│          │
│  │ (仿真管理器) │   │  (单机代理)     │   │  (4D 禁飞区)     │          │
│  └──────┬──────┘   └───────┬────────┘   └─────────────────┘           │
│         │                  │                                           │
│         │    ┌─────────────▼──────────────┐                            │
│         │    │  状态机: IDLE→TAKEOFF→     │                             │
│         │    │  CRUISE→HOVER→LANDING→     │                             │
│         │    │  FINISHED                  │                             │
│         │    └────────────────────────────┘                            │
│         │                                                              │
│  ┌──────▼──────────────────────────────────┐                           │
│  │  pylib/structs.py (ctypes 结构体定义)     │   ← 与 C++ 二进制兼容     │
│  └──────┬──────────────────────────────────┘                           │
│         │                                                              │
│  ┌──────▼──────────────┐                                               │
│  │  pylib/engine.py    │   ← C++ UTM 引擎 Python 封装（可选）            │
│  │  UTMEngine          │                                               │
│  └─────────────────────┘                                               │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                        【基础设施层】                                     │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐             │
│  │ redis_client │  │  kafka_proc  │  │     env.py       │             │
│  │  RedisClient │  │ KafkaProducer│  │  (连接配置中心)    │             │
│  │              │  │ KafkaConsumer│  │                   │             │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘             │
│         │                 │                                             │
├─────────┼─────────────────┼─────────────────────────────────────────────┤
│         │                 │              【外部中间件】                    │
│    ┌────▼─────┐     ┌─────▼──────┐                                     │
│    │  Redis   │     │   Kafka    │                                     │
│    │Hash/Sets │     │ Topics:    │                                     │
│    │          │     │ uav_rt_data│                                     │
│    │          │     │ uav_rt_trace│                                    │
│    └──────────┘     └────────────┘                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件关系图

```
                    ┌─────────────────┐
                    │     main.py     │
                    │  (程序入口)      │
                    └────────┬────────┘
                             │ 实例化
                    ┌────────▼────────┐
                    │    DataFlow     │
                    │                 │
                    │ ┌─────────────┐ │
                    │ │ 仿真线程      │ │  1Hz 定时循环
                    │ │ _simulation  │ │
                    │ │ _loop()     │ │
                    │ └──────┬──────┘ │
                    │        │        │
                    │ ┌──────▼──────┐ │
                    │ │trace消费线程 │ │  轮询 Kafka
                    │ │_consume_    │ │
                    │ │trace()      │ │
                    │ └─────────────┘ │
                    └────────┬────────┘
                             │ 持有
                    ┌────────▼────────┐
                    │   DataSource    │
                    │                 │
                    │ ┌─────────────┐ │
                    │ │ RedisClient  │ │  → Redis
                    │ ├─────────────┤ │
                    │ │KafkaProducer │ │  → Kafka (写)
                    │ ├─────────────┤ │
                    │ │KafkaConsumer │ │  → Kafka (读)
                    │ ├─────────────┤ │
                    │ │  Simulator   │ │  → 仿真核心
                    │ └─────────────┘ │
                    └─────────────────┘
```

---

## 3. 模块详解

### 3.1 `main.py` — 主入口（实时仿真模式）

**定位**：生产级实时仿真主程序。启动后持续运行，每秒步进一次仿真，动态生成飞行计划并补充到活跃无人机池。

**核心流程**：

```
启动 → DataFlow.__init__()
        ├── 创建 DataSource（连接 Redis/Kafka，初始化 Simulator）
        ├── 启动仿真线程 _simulation_loop()  → 每 1s 调用 step()
        └── 启动 trace 消费线程 _consume_uav_runtime_trace()

仿真线程每步执行:
  1. Simulator.step(1.0)        — 推进所有无人机状态
  2. 清理已落地的 DroneAgent
  3. _maintain_traffic()        — 若活跃数 < target_drones，生成新计划写 Redis
  4. _telemetry_to_kafka_message() — 遥测格式转换
  5. KafkaProducer.send_bulk()  — 批量发送到 uav_runtime_data

trace 消费线程:
  1. KafkaConsumer.poll()       — 拉取 uav_runtime_trace 消息
  2. 解析 redisKey，从 Redis 查询追踪数据
  3. 过滤只保留仿真器中活跃的无人机
```

**关键参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `target_drones` | 10 | 维持的活跃无人机数量 |
| `origin_lat` | 40.818724 | 仿真中心纬度 |
| `origin_lon` | 85.070136 | 仿真中心经度 |
| `sim_radius_m` | 100000 | 仿真有效半径（米） |
| `uid_start_offset` | 0 | 预置 ID 起始偏移量 |

### 3.2 `simulation_core.py` — 仿真核心引擎（v3.0）

**定位**：独立的无人机飞行仿真库。可被 `main.py` 和 `tools/create_data.py` 共用。

#### 3.2.1 全局配置

模块级可配置参数（通过 `set_simulation_params()` 动态修改）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ORIGIN_LAT` | 40.818724 | 仿真原点纬度 |
| `ORIGIN_LON` | 85.070136 | 仿真原点经度 |
| `SIM_RADIUS_M` | 100000.0 | 仿真区域半径（米） |
| `CRUISE_SPEED` | 30.0 m/s | 默认巡航速度 |
| `CLIMB_RATE` | 15.0 m/s | 爬升/下降率 |
| `MAX_HORIZ_ACCEL` | 5.0 m/s² | 最大水平加速度 |
| `MAX_VERT_ACCEL` | 5.0 m/s² | 最大垂直加速度 |
| `MIN_CRUISE_ALT` | 50.0 m | 最小巡航高度 |
| `MAX_CRUISE_ALT` | 200.0 m | 最大巡航高度 |

#### 3.2.2 DroneAgent — 单机仿真代理

**状态机**：

```
                  ┌──────────────────────────────────────┐
                  │                                      │
                  ▼                                      │
  ┌────┐    ┌─────────┐    ┌────────┐    ┌─────────┐    │
  │IDLE│───▶│ TAKEOFF │───▶│ CRUISE │───▶│ LANDING │    │
  │ 0  │    │    1    │    │   2    │    │    4    │    │
  └────┘    └─────────┘    └───┬────┘    └────┬────┘    │
                               │              │         │
                               │    ┌──────┐  │         │
                               └───▶│HOVER │──┘         │
                                    │  3   │            │
                                    └──────┘            │
                                                        │
                               ┌──────────┐             │
                               │ FINISHED │◄────────────┘
                               │    5     │  (降落完成)
                               └──────────┘
```

**两种任务模式**：

| 模式 | plan.type | 说明 |
|------|-----------|------|
| **TRAJ（航路点）** | 0 | 按航路点序列飞行，支持悬停等待（stay_duration） |
| **POLY（区域盘旋）** | 1 | 在凸多边形区域内圆形盘旋，按结束时间降落 |

**TRAJ 模式关键行为**：
- 起飞阶段：斜向加速，同时爬升并飞向第一个航路点
- 巡航阶段：按航路点序列依次飞行，接近目标时平滑减速（制动距离 = 4×v²/(2a)）
- 悬停阶段：到达悬停点后等待 `stay_duration` 秒
- 降落阶段：水平减速到零，垂直以 `CLIMB_RATE/2` 平滑降落

**POLY 模式关键行为**：
- 以区域中心为圆心，200m 为半径做圆周运动
- 根据 `plan.end_time` 判断是否降落

**动力学特性**：
- 使用 `_lerp_vel()` 实现加速度限制的速度平滑过渡
- 垂直/水平速度独立控制，各有加速度上限
- 历史轨迹缓存（`history_buffer`）：最近 10 帧 TelemetrySnapshot，供 C++ 卡尔曼滤波使用

#### 3.2.3 Simulator — 仿真管理器

**核心职责**：

1. **飞行计划生成**（`generate_plan()`）：
   - 50% 概率：多边形区域航路（闭合形状，4~30 边）
   - 50% 概率：随机漫游航路（10~30 个随机航点）
   - 从预置的 430 个无人机标识符列表中按序分配 UID
   - 超出预置列表后随机生成 20 位唯一识别码

2. **禁飞区生成**（`generate_nfzs()`）：
   - 生成随机凸多边形禁飞区（3~10 个顶点）
   - 支持 4 种类型：noDrone、limited、danger、segregated
   - 随机时间窗：未来 0~60 秒开始，持续 30~60 分钟

3. **仿真步进**（`step()`）：
   - 清理已落地无人机（state == 5）
   - 逐个调用 `agent.update()` 推进状态
   - 收集活跃无人机的遥测数据包

4. **外部计划加载**（`add_plans()`）：
   - 从 JSON 格式的航线数据创建 FlightPlan 和 DroneAgent
   - 支持动态追加或替换已有无人机

**无人机标识符体系**：

预置 430 条 `(uniqueProductIdentificationCode, realNameRegistrationSign)` 二元组，按序号循环分配给生成的无人机。支持通过 `env.ids_index` 切换标识表。

### 3.3 `kafka_proc.py` — Kafka 客户端封装

#### KafkaProducerClient

**能力**：
- 单条发送（`send_message`）
- 批量发送（`send_bulk` / `send_batch`），分批确认
- **双集群同步写入**：配置 `bootstrap_servers_mirror` 后，消息同时发往主备两个 Kafka 集群
- Flush 超时保护：默认 1s，可配置，防止主线程永久阻塞
- 优雅关闭：先 close 再退出，避免 atexit 冲突

**关键配置**：

| 常量 | 值 | 说明 |
|------|-----|------|
| `_KAFKA_FLUSH_TIMEOUT_SEC` | 1.0s | 单次 flush 超时 |
| `_KAFKA_PRODUCER_CLOSE_TIMEOUT_SEC` | 5.0s | 生产者关闭超时 |

#### KafkaConsumerClient

**能力**：
- 订阅 Topic 后消费消息
- `consume_from_latest_on_start=True`：跳过历史积压，仅消费新消息
- 独立 group_id（`utm_demo_group_{pid}`），支持多实例并行消费
- JSON 自动反序列化
- 优雅关闭（忽略析构阶段常见异常）

### 3.4 `redis_client.py` — Redis 客户端封装

**核心方法**：

| 方法 | 对应 Redis 命令 | 用途 |
|------|-----------------|------|
| `hset(key, field, value)` | HSET | 写入飞行计划/空域数据 |
| `hget(key, field)` | HGET | 查询单条飞行计划 |
| `hgetall(key)` | HGETALL | 获取全部飞行计划 |
| `hkeys(key)` | HKEYS | 获取所有 field 名称 |
| `get(key)` | GET | 获取字符串值 |
| `get_value_by_key(key)` | TYPE + 自适应读取 | **智能读取**：自动识别 key 类型（string/hash/list/set/zset）并解析 |

**智能读取特点**（`get_value_by_key`）：
1. 先用 `TYPE` 命令判断 key 类型
2. 根据类型选择对应读取命令
3. 自动尝试 JSON 反序列化
4. 支持 hash/list/set/zset 的嵌套 JSON 解析

### 3.5 `pylib/` — C++ UTM 核心库封装（可选）

#### `pylib/structs.py` — ctypes 结构体定义

使用 Python `ctypes` 定义了与 C++ 核心库二进制兼容的全部数据结构：

| 结构体 | 用途 |
|--------|------|
| `GeoPoint` | 三维地理坐标 (lon, lat, alt) |
| `Vec3` | 三维速度向量 |
| `Waypoint` | 航路点（含保护高度/宽度） |
| `FlightPlan` | 飞行计划（含 union：traj/area） |
| `TelemetryData` | 实时遥测数据 |
| `TelemetrySnapshot` | 历史轨迹快照 |
| `AircraftStateInput` | 飞机状态输入（current + history） |
| `DynamicNoFlyZone` | 动态禁飞区 |
| `ConflictInfo` | 冲突检测结果 |
| `DeviationInfo` | 偏航检测结果 |
| `TrajectoryPoint` | 预测轨迹点 |
| `SystemConfig` | 系统规则配置 |
| `RuleThreshold` | 单条规则阈值 |

**枚举映射**：

| 枚举 | 值范围 | 说明 |
|------|--------|------|
| `UAVClassification` | 0~4 | MICRO/LIGHT/SMALL/MEDIUM/LARGE |
| `NFZ_TYPE_MAP` | 0~7 | controlled/restrictedUse/fusion/noDrone/limited/danger/segregated/suppression |
| `NFZ_STATUS_MAP` | 0~2 | PERMANENT/TEMPORARY_ACTIVE/INACTIVE |
| `ALARM_TYPE_MAP` | 0~9 | 碰撞/空域/偏航 × (告警/预警) + 战略/预估类型 |

#### `pylib/engine.py` — UTMEngine 引擎封装

**C++ 函数接口对照**：

| Python 方法 | C++ 函数 | 功能 |
|-------------|----------|------|
| `predict_trajectory()` | `PredictTrajectory` | 预测未来轨迹（含卡尔曼滤波） |
| `detect_tactical_conflicts()` | `DetectTacticalConflict` | 短期战术冲突检测 |
| `detect_strategic()` | `DetectStrategicConflict` | 战略冲突检测（飞行前） |
| `detect_pre_flight_conflicts()` | `DetectPreFlightConflict` | 起飞前冲突预检 |
| `check_deviation()` | `CheckDeviation` | 偏航检测 |
| `calculate_pairwise_distance()` | `CalculatePairwiseMinDistance` | 两机最小间距计算 |
| `apply_business_rules()` | `UpdateSystemConfig` | 热更新安全规则配置 |
| `init_default_config()` | `InitDefaultSystemConfig` | 初始化默认规则 |

**关键设计**：
- 使用 `ctypes.byref()` 传递结构体引用
- 通过 `self._keep_alive` / `self._history_keep_alive` 持有 ctypes 数组引用，防止 Python GC 回收导致 C++ 端访问野指针
- `apply_business_rules()` 支持从 JSON 配置热更新机间碰撞、空域入侵、偏航等全部安全规则

### 3.6 `env.py` — 连接配置中心

集中管理 Redis/Kafka 连接参数，支持多环境配置切换（通过注释切换）：

```python
# atctest 环境
redis_ip = "dolphin-test.kedacom.com"
redis_port = "21103"
redis_password = "s4^dJ5^xM6^e"
kafka_url = "10.165.19.213:30092"

# dkkgsit 环境
# redis_ip = "dolphin-test.kedacom.com"
# redis_port = "21003"
# kafka_url = "10.165.19.213:30011"
# kafka_url2 = ""  # 高可用集群地址（可选）
```

---

## 4. 数据流设计

### 4.1 主数据流（实时仿真模式）

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Simulator   │     │  DataSource │     │    Redis    │
│             │     │             │     │             │
│ generate    │────▶│ add_redis   │────▶│ HSET        │
│ _plan()     │     │ _plan()     │     │ BIZ_DATA:   │
│             │     │             │     │ UAV_ROUTE   │
│             │     │             │     │  {uid: json}│
│             │     │             │     └─────────────┘
│ step()      │────▶│ _telemetry  │
│             │     │ _to_kafka   │
│             │     │ _message()  │
│             │     │             │
│             │     │ send_bulk() │     ┌─────────────┐
│             │     └─────────────┘────▶│   Kafka     │
│             │                         │             │
│             │                         │ Topic:      │
│             │                         │ uav_runtime │
│             │                         │ _data       │
└─────────────┘                         └──────┬──────┘
                                               │
                                               │ 下游消费
                                               ▼
                                        ┌─────────────┐
                                        │  UTM 算法   │
                                        │  引擎处理   │
                                        │             │
                                        │ 轨迹预测    │
                                        │ 冲突检测    │
                                        └──────┬──────┘
                                               │
                                               │ 结果写入
                                               ▼
                                        ┌─────────────┐
                                        │   Kafka     │
                                        │ Topic:      │
                                        │ uav_runtime │
                                        │ _trace      │
                                        └──────┬──────┘
                                               │
                                               │ 回读验证
                                               ▼
                                        ┌─────────────┐
                                        │ DataSource  │
                                        │ trace消费线程│
                                        │             │
                                        │ 按 redisKey │
                                        │ 查 Redis    │
                                        └─────────────┘
```

### 4.2 Mock 数据注入流（离线回放模式）

```
┌───────────────┐     ┌─────────────────┐     ┌──────────────┐
│ create_data.py│     │   mock/*.json   │     │ tools/run    │
│               │     │                 │     │ _kafka.py    │
│ 1. 仿真跑一遍  │────▶│ redis_route.json│────▶│              │
│ 2. 生成航线    │     │                 │     │ 1. 读 JSON   │
│ 3. 生成遥测    │     │ kafka_data.json │     │ 2. 写 Redis  │
│ 4. 输出 JSON   │     │                 │     │ 3. 写 Kafka  │
└───────────────┘     └─────────────────┘     └──────────────┘
```

### 4.3 Redis Key 约定

| Key | 类型 | 内容 | 写入方 |
|-----|------|------|--------|
| `BIZ_DATA:UAV_ROUTE` | Hash | field=UID, value=单机航线JSON | main.py / run_kafka.py / nfzs.py |
| `BIZ_DATA:AIRSPACE` | Hash | field=airspaceId, value=空域JSON | tools/nfzs.py |

### 4.4 Kafka Topic 约定

| Topic | 消息格式 | 写入方 | 消费方 |
|-------|---------|--------|--------|
| `uav_runtime_data` | UTM 遥测数据（算法对接格式） | main.py / run_kafka.py | UTM 算法引擎 |
| `uav_runtime_trace` | 含 redisKey 的追踪消息 | UTM 算法引擎 | main.py trace 消费线程 |

### 4.5 遥测数据格式（uav_runtime_data 单条消息）

```json
{
  "uniqueProductIdentificationCode": "DJI1MAV101A2B3C4D5E6",
  "realNameRegistrationSign": "UAS01DJI1MAV001",
  "uasOperationCategory": 1,
  "classification": 1,
  "rpsLocationType": 1,
  "rpsLongitude": 0,
  "rpsLatitude": 0,
  "rpsAltitude": 0,
  "longitude": 85.070136,
  "latitude": 40.818724,
  "trackAngle": 45.0,
  "speed": 30.0,
  "geodeticAltitude": 120.0,
  "verticalSpeed": 0.0,
  "relativeAltitude": 120.0,
  "ressureAltitude": 120.0,
  "operatingStatus": 2,
  "coordinateSystemType": 1,
  "horizontalAccuracy": 1,
  "verticalAccuracy": 1,
  "speedAccuracy": 1,
  "timestamp": 1752000000000,
  "timestampAccuracy": 0,
  "sourceType": 1,
  "addInf": {}
}
```

---

## 5. 核心数据结构

### 5.1 FlightPlan（飞行计划）

```
FlightPlan
├── task_name: char[64]          # 任务名称
├── task_id: int64               # 任务 ID
├── plan_id: int64               # 计划 ID
├── type: int                    # 0=TRAJ（航路点）, 1=POLY（区域）
├── start_time: double           # 起飞时间（Unix 时间戳）
├── end_time: double             # 降落时间
├── priority: int                # 优先级 (1-10)
├── aircraft: AircraftProfile
│   ├── uid: char[64]           # 无人机唯一标识
│   ├── classification: int     # 机型分类
│   ├── longitudinal_threshold  # 纵向保护阈值
│   ├── lateral_threshold       # 横向保护阈值
│   ├── v_threshold             # 垂直保护阈值
│   └── max_speed               # 最大速度
└── data: PlanDataUnion          # C Union
    ├── [TRAJ] traj:
    │   ├── wps: Waypoint[]     # 航路点数组
    │   └── count: int          # 航路点数量
    └── [POLY] area:
        ├── vertices: GeoPoint[] # 多边形顶点
        ├── vertex_count: int   # 顶点数量
        ├── min_alt: double     # 最低高度
        └── max_alt: double     # 最高高度
```

### 5.2 DroneAgent（无人机代理）

```
DroneAgent
├── plan: FlightPlan            # 飞行计划引用
├── uid: str                    # 无人机 UID
├── state: int                  # 状态机 (0-5)
├── current_wp_idx: int         # 当前目标航路点索引
├── lat/lon/alt: float          # 真实位置（无噪声）
├── vn/ve/vd: float             # 速度分量 (N-E-D)
├── heading: float              # 航向（度，北向0°顺时针）
├── cruise_speed: float         # 巡航速度（随机微调）
├── climb_rate: float           # 爬升率
├── target_alt: float           # 目标巡航高度
├── hover_timer: float          # 悬停倒计时
├── history_buffer: deque(10)   # 历史轨迹（TelemetrySnapshot ×10）
├── sourceType: int             # 1=无人机, 2=ADS-B
└── addInf: dict                # ADS-B 附加信息
```

### 5.3 Waypoint（航路点）

```
Waypoint
├── point: GeoPoint             # 三维坐标 (lon, lat, alt)
├── eta: double                 # 预计到达时间
├── stay_duration: double       # 悬停时长（秒）
├── segmentWidth: double        # 航段保护宽度（米）
├── segmentProtectHeightType: int  # 保护高度类型
└── segmentVerticalleight: double  # 垂直保护高度（米）
```

### 5.4 DynamicNoFlyZone（动态禁飞区）

```
DynamicNoFlyZone
├── uid: char[64]               # 禁飞区 ID (如 NFZ_001)
├── type: int                   # 类型 (0-7, NFZ_TYPE_MAP)
├── status: int                 # 状态 (0-2, NFZ_STATUS_MAP)
├── geometry: AreaGeometry
│   ├── vertices: GeoPoint[]   # 凸多边形顶点
│   ├── vertex_count: int      # 顶点数 (3-10)
│   ├── min_alt: double        # 高度下限
│   └── max_alt: double        # 高度上限
├── start_time: double          # 生效时间
├── end_time: double            # 失效时间
├── priority: int               # 优先级
└── reason: char[64]            # 原因说明
```

---

## 6. 线程模型

### 6.1 线程布局

```
┌─────────────────────────────────────────────────────┐
│                    主线程 (Main)                     │
│  - 创建 DataFlow                                    │
│  - 启动子线程                                        │
│  - 等待 Ctrl+C / data_exhausted                     │
│  - 调用 stop() 清理                                  │
└─────────────────────────────────────────────────────┘
          │                          │
          │ 创建                      │ 创建
          ▼                          ▼
┌──────────────────┐    ┌──────────────────────────┐
│  仿真线程 (daemon)│    │ trace 消费线程 (daemon)    │
│                  │    │                          │
│ 每 1s 执行:      │    │ 每 0.1s / 0.05s 轮询:    │
│ 1. step(1.0)    │    │ 1. consumer.poll()       │
│ 2. 清理落地机    │    │ 2. 解析 redisKey          │
│ 3. 补充新机      │    │ 3. redis.get_value()     │
│ 4. 格式转换      │    │ 4. 过滤打印               │
│ 5. send_bulk()  │    │                          │
└──────────────────┘    └──────────────────────────┘
```

### 6.2 线程安全

- **DroneAgent 字典**（`self.agents`）：仅在仿真线程中读写，无并发访问
- **Kafka Producer**：仅在仿真线程中写入（send_bulk），线程安全由 kafka-python 内部保证
- **Kafka Consumer**：仅在 trace 消费线程中拉取，独立线程安全
- **Redis 连接**：仿真线程写入，trace 消费线程读取，Redis 自身保证原子性
- **数据竞争**：`active_plans` / `kafka_data_list` 等对象仅在所属线程中修改

### 6.3 优雅关闭

```
stop()
├── running = False
├── 仿真线程 join(timeout=5)      # 等待最后一帧发送完成
├── trace 消费线程 join(timeout=5) # 等待最后一轮 poll 结束
├── kafka_producer.close()        # 关闭生产者（触发 atexit unregister）
└── 清理日志 / 输出文件
```

---

## 7. 部署架构

```
┌──────────────────────────────────────────────────────────┐
│                    仿真节点（单机/多机）                    │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐          │
│  │ main.py  │  │run_kafka │  │run_kafka_alive│         │
│  │(实时仿真) │  │(Mock注入) │  │(持续循环注入)  │          │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘          │
│       │              │               │                   │
│       └──────────────┼───────────────┘                   │
│                      │                                   │
└──────────────────────┼───────────────────────────────────┘
                       │
            ┌──────────┴──────────┐
            │                     │
     ┌──────▼──────┐      ┌──────▼──────┐
     │    Redis    │      │    Kafka    │
     │  (dolphin)  │      │  Cluster   │
     │             │      │             │
     │ BIZ_DATA:   │      │ uav_runtime │
     │ UAV_ROUTE   │      │ _data       │
     │ AIRSPACE    │      │ uav_runtime │
     │             │      │ _trace      │
     └──────┬──────┘      └──────┬──────┘
            │                    │
            │                    │
     ┌──────▼────────────────────▼──────┐
     │         UTM 算法引擎节点           │
     │  - 消费 uav_runtime_data          │
     │  - 查询 Redis 飞行计划             │
     │  - 轨迹预测 / 冲突检测             │
     │  - 写入 uav_runtime_trace         │
     └───────────────────────────────────┘
```

### 7.1 多实例部署

- 每个进程使用独立 group_id（`utm_demo_group_{pid}`），确保多实例都能收到全部消息
- 通过 `consume_from_latest_on_start=True` 跳过历史消息
- `uid_start_offset` 参数支持不同实例使用不同批次的无人机标识符

### 7.2 高可用 Kafka 配置

- 主集群：`kafka_url`
- 镜像集群：`kafka_url2`（可选）
- 每条消息同时写入两个集群，flush 超时独立

---

## 8. 运行模式

### 8.1 模式对比

| 维度 | main.py | tools/run_kafka.py | tools/run_kafka_alive.py |
|------|---------|-------------------|--------------------------|
| **仿真方式** | 实时仿真生成 | 预生成 JSON 回放 | 预生成 JSON 循环回放 |
| **数据来源** | Simulator 实时生成 | mock/*.json 预生成文件 | mock/*.json 预生成文件 |
| **循环策略** | 持续补充新机 | 一轮跑完自动停止 | 单机独立循环，永不停止 |
| **Redis 刷新** | 每架新机写入一次 | 启动时全部写入 | 启动写入 + 单机重飞时刷新 |
| **适用场景** | 生产级实时注入 | 历史数据回放/测试 | 长期压力测试 |
| **依赖 C++ 库** | 否（可选加载） | 否 | 否 |

### 8.2 数据预生成流程

```
create_data.py --count 20
  │
  ├── 1. 创建 Simulator，生成 N 个 FlightPlan
  ├── 2. 可选加载 redis_route_custom.json 追加自定义航线
  ├── 3. 输出 mock/redis_route.json（飞行计划）
  ├── 4. 用仿真时间一次性跑完全部飞行过程
  └── 5. 输出 mock/kafka_data.json（全部遥测记录）

然后:
  tools/run_kafka.py          → 按秒回放 kafka_data.json
  tools/run_kafka_alive.py    → 循环回放，永不停止
```

---

## 9. 配置管理

### 9.1 配置来源优先级

```
1. 代码硬编码默认值 (simulation_core.py 模块级常量)
2. env.py 环境变量（Redis/Kafka 连接）
3. 构造函数参数覆盖（origin_lat/origin_lon/sim_radius_m 等）
4. set_simulation_params() 运行时热更新
```

### 9.2 关键配置项速查

| 配置项 | 位置 | 说明 |
|--------|------|------|
| Redis 连接 | `env.py` | ip/port/password，支持多环境切换 |
| Kafka 连接 | `env.py` | bootstrap_servers，可选 mirror |
| 仿真原点 | `simulation_core.py` / 构造参数 | 默认 (40.818724, 85.070136) |
| 仿真半径 | `simulation_core.py` / 构造参数 | 默认 100km |
| 无人机数量 | `main.py` DataFlow(target_drones=N) | 默认 10 |
| 安全规则 | `pylib/engine.py` apply_business_rules() | JSON 配置热更新 |
| 标识表选择 | `env.py` ids_index | 1=主表, 2=备用表 |

---

## 10. 工具脚本生态

### 10.1 核心工具

| 脚本 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `tools/create_data.py` | 预生成 mock 数据 | 仿真参数（--count 等） | `mock/redis_route.json` + `mock/kafka_data.json` |
| `tools/run_kafka.py` | Mock 数据注入 Redis/Kafka（一轮） | `mock/redis_route.json` + `mock/kafka_data.json` | Redis + Kafka + `mock/redis_trace.json` |
| `tools/run_kafka_alive.py` | Mock 数据注入（持续循环） | 同上 | Redis + Kafka（永不停止） |
| `tools/run_kafka_scene.py` | 场景化注入 | 场景配置 | Redis + Kafka |
| `tools/run_plan.py` | 飞行计划专用上传 | 航线数据 | Redis |
| `tools/nfzs.py` | 禁飞区→标准空域格式→Redis | `_source/nfzs.json` | `mock/nfzs.json` + Redis |
| `tools/create_data_scene.py` | 场景化数据生成 | 场景定义 | mock JSON |
| `tools/create_data_scenes.py` | 多场景批量生成 | 场景列表 | mock JSON |

### 10.2 分析与验证工具

| 脚本 | 功能 |
|------|------|
| `tools/trajectory_accuracy.py` | 航迹准确度计算（比较 Kafka 发送值与 Redis trace 回查值） |
| `tools/trajectory_accuracy_json.py` | 航迹准确度（JSON 输入版本） |
| `tools/analyze_trajectory.py` | 轨迹分析 |
| `tools/kafka_read_latest.py` | 读取 Kafka 最新消息 |
| `tools/kafka_uav_counter.py` | 统计 Kafka 中无人机数量 |
| `tools/redis_read_lastest.py` | 读取 Redis 最新数据 |
| `tools/check_uids_in_db.py` | 检查数据库中 UID 存在性 |
| `tools/check_hash_id_collision.py` | 检查 Hash ID 碰撞 |
| `tools/test_deviation_fix.py` | 偏航检测修复测试 |
| `tools/test_deviation_fix2.py` | 偏航检测修复测试 v2 |
| `tools/transform.py` | 坐标/格式转换工具 |
| `tools/lines_to_redis_route.py` | 航线数据→Redis 格式转换 |

### 10.3 数据与规范文件

| 文件 | 说明 |
|------|------|
| `_source/算法对接2026.md` | 算法对接文档（数据格式、字段含义、枚举值—最高权威） |
| `_source/plans.json` | 飞行计划源数据 |
| `_source/telemetries.json` | 遥测源数据 |
| `_source/nfzs.json` | 禁飞区原始数据（key 式：NFZ_001 等） |
| `_source/conflicts.json` | 冲突检测样本数据 |
| `_source/conflicts_类型说明.md` | 冲突类型说明 |
| `_source/航线冲突-数据库表及关系.md` | 航线冲突数据库设计 |
| `mock/` | 运行时生成的 mock 数据输出目录 |

---

## 11. 关键设计决策

### 11.1 ctypes 而非 Cython/pybind11

**决策**：使用 Python 内置 `ctypes` 封装 C++ 核心库。

**理由**：
- 零额外编译依赖，纯 Python 环境即可运行
- 结构体定义（`structs.py`）与 C++ 头文件 `utm_core.h` 严格对齐
- 手动管理内存引用（`_keep_alive`）防止 GC 导致的野指针

### 11.2 C Union 模拟

`FlightPlan.data` 在 C++ 中是 union，Python ctypes 通过 `PlanDataUnion(ctypes.Union)` 支持，TRAJ 和 POLY 两种模式共用同一块内存。

### 11.3 预置标识符 + 随机兜底

无人机 UID 优先从预置的 430 条标识符列表按序分配（保证可追溯性），超出后自动随机生成 20 位大写字母+数字组合（保证唯一性）。

### 11.4 双 Kafka 集群写入

支持主备 Kafka 集群同步写入，通过 `bootstrap_servers_mirror` 配置启用。flush 超时独立处理，主集群失败不影响镜像集群写入。

### 11.5 仿真时间 vs 系统时间

- `step()` 支持传入 `sim_time` 参数实现"离线仿真时间"，用于预生成数据（`create_data.py`）
- 实时模式下使用 `time.time()` 浮点值，避免 `int()` 截断导致起飞时间误判

### 11.6 速度平滑过渡

`DroneAgent._lerp_vel()` 实现的加速度限制速度过渡，避免速度突变：
- 水平加速度上限：`MAX_HORIZ_ACCEL` (5.0 m/s²)
- 垂直加速度上限：`MAX_VERT_ACCEL` (5.0 m/s²)
- 制动距离预估：4×v²/(2a)，提前减速防止过冲

### 11.7 sourceType 分配策略

sourceType（1=无人机, 2=ADS-B）通过 uid 的 MD5 哈希低位决定，保证同一 uid 始终相同、不同 uid 近似各半分布。当前代码中 `sourceType_for_uid()` 实际固定返回 1，保留哈希分配逻辑供后续使用。

---

## 12. 文件目录图谱

```
utm_simulator/
├── main.py                    # 【主入口】实时仿真模式
├── simulation_core.py         # 【核心】仿真引擎 v3.0
├── kafka_proc.py              # 【基础设施】Kafka 生产者/消费者封装
├── redis_client.py            # 【基础设施】Redis 客户端封装
├── env.py                     # 【配置】连接参数与运行环境
├── requirements.txt           # Python 依赖
│
├── pylib/                     # 【可选】C++ UTM 核心库封装
│   ├── __init__.py
│   ├── structs.py             #   ctypes 结构体定义（与 C++ 二进制对齐）
│   └── engine.py              #   UTMEngine：C++ 函数高级封装
│
├── tools/                     # 【工具脚本集】
│   ├── create_data.py         #   预生成 mock 航线与遥测 JSON
│   ├── create_data_scene.py   #   场景化数据生成
│   ├── create_data_scenes.py  #   多场景批量生成
│   ├── run_kafka.py           #   Mock JSON → Redis + Kafka（一轮）
│   ├── run_kafka_alive.py     #   Mock JSON → Redis + Kafka（持续循环）
│   ├── run_kafka_scene.py     #   场景化数据注入
│   ├── run_plan.py            #   飞行计划专用上传
│   ├── nfzs.py                #   禁飞区→空域格式→Redis
│   ├── transform.py           #   坐标/格式转换
│   ├── lines_to_redis_route.py#   航线→Redis 格式
│   ├── trajectory_accuracy.py #   航迹准确度计算
│   ├── trajectory_accuracy_json.py
│   ├── analyze_trajectory.py  #   轨迹分析
│   ├── kafka_read_latest.py   #   Kafka 最新消息读取
│   ├── kafka_uav_counter.py   #   Kafka 无人机统计
│   ├── redis_read_lastest.py  #   Redis 最新数据读取
│   ├── check_uids_in_db.py    #   数据库 UID 检查
│   ├── check_hash_id_collision.py
│   ├── test_deviation_fix.py  #   偏航检测测试
│   └── test_deviation_fix2.py
│
├── _source/                   # 【数据与规范】
│   ├── 算法对接2026.md        #   算法对接文档（数据格式权威来源）
│   ├── plans.json             #   飞行计划源数据
│   ├── telemetries.json       #   遥测源数据
│   ├── nfzs.json              #   禁飞区原始数据
│   ├── conflicts.json         #   冲突样例数据
│   ├── conflicts_类型说明.md  #   冲突类型文档
│   └── 航线冲突-数据库表及关系.md
│
├── mock/                      # 【运行时输出】
│   ├── redis_route.json       #   生成的航线 JSON
│   ├── kafka_data.json        #   生成的遥测 JSON
│   ├── redis_trace.json       #   追踪回查数据
│   └── *.json                 #   场景/碰撞预警等输出
│
├── packages/                  # 【离线依赖包】(.whl)
│
├── deploy.sh                  # 部署脚本
├── deploy_repeat.sh           # 重复部署脚本
├── index.html / mock.html / multi.html  # 可视化页面
├── lines.json                 # 航线定义
├── uav_identifiers_extended.py# 扩展无人机标识符
├── env.md                     # 环境说明
├── CLAUDE.md                  # AI 辅助规则
├── AGENTS.md                  # Agent 配置
├── README.md                  # 项目说明
└── 使用手册.md                # 用户使用手册
```

---

## 附录 A：技术术语映射

| 缩写/术语 | 全称 | 说明 |
|-----------|------|------|
| UTM | Unmanned Traffic Management | 无人机交通管理 |
| UAS | Unmanned Aircraft System | 无人驾驶航空器系统 |
| NFZ | No-Fly Zone | 禁飞区 |
| TRAJ | Trajectory | 航路点轨迹模式 |
| POLY | Polygon | 区域盘旋模式 |
| ADS-B | Automatic Dependent Surveillance–Broadcast | 广播式自动相关监视 |
| RPS | Remote Pilot Station | 远程驾驶站 |

## 附录 B：状态码速查

### DroneAgent 状态

| 状态码 | 名称 | 说明 |
|--------|------|------|
| 0 | IDLE | 等待起飞时间 |
| 1 | TAKEOFF | 爬升阶段 |
| 2 | CRUISE | 巡航/任务飞行 |
| 3 | HOVER | 定点悬停等待 |
| 4 | LANDING | 降落阶段 |
| 5 | FINISHED | 任务完成已落地 |

### UAV 运营状态（operatingStatus）

| 值 | 说明 |
|----|------|
| 1 | 已落地/停机 |
| 2 | 飞行中 |

### 空域类型（typeCode / NFZ Type）

| 值 | 代码 | 说明 |
|----|------|------|
| 0 | controlled | 管制空域 |
| 1 | restrictedUse | 限制使用空域 |
| 2 | fusion | 融合空域 |
| 3 | noDrone | 空中禁区 |
| 4 | limited | 限制区 |
| 5 | danger | 危险区 |
| 6 | segregated | 隔离空域 |
| 7 | suppression | 压制区 |

### 告警类型

| 值 | 类型 | 时间尺度 |
|----|------|----------|
| 0 | COLLISION_ALERT | 短期（战术） |
| 1 | COLLISION_WARN | 短期（战术） |
| 2 | AIRSPACE_ALERT | 短期（战术） |
| 3 | AIRSPACE_WARN | 短期（战术） |
| 4 | DEVIATION_ALERT | 实时 |
| 5 | DEVIATION_WARN | 实时 |
| 6 | STRATEGIC_AIRSPACE_WARN | 长期（战略/预估） |
| 7 | STRATEGIC_COLLISION_WARN | 长期（战略/预估） |
| 8 | ESTIMATE_AIRSPACE_WARN | 预估 |
| 9 | ESTIMATE_COLLISION_WARN | 预估 |
