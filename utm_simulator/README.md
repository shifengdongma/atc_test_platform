# utm_moc52

UTM（无人机交通管理）仿真与数据注入服务。通过 Python 仿真多架无人机的飞行过程，将**飞行计划**写入 Redis，将**实时遥测**写入 Kafka，供下游 UTM 系统、态势或算法使用。

## 功能概览

- **多机仿真**：维持约 1000 架活跃无人机，支持航路点轨迹与区域盘旋两种任务类型
- **动力学仿真**：简单无人机动力学（爬升/巡航/降落）、状态机与可选 GPS 噪声
- **Redis 写入**：飞行计划写入 `BIZ_DATA:UAV_ROUTE` Hash，字段为无人机 UID
- **Kafka 推送**：实时遥测批量发送到 `uav_runtime_data` Topic
- **C++ 引擎对接**：`pylib` 提供与 UTM 核心库（轨迹预测、战术/战略冲突检测等）的 Python 封装，可按需接入

## 项目结构

```
utm_moc52/
├── main.py              # 入口：DataSource + 仿真循环线程
├── simulation_core.py   # 无人机仿真核心（DroneAgent、Simulator、禁飞区）
├── kafka_proc.py       # Kafka 生产者/消费者封装
├── redis_client.py     # Redis 客户端封装
├── pylib/
│   ├── structs.py      # 与 C++ UTM 核心一致的数据结构（ctypes）
│   └── engine.py       # UTM 引擎 Python 封装（DLL/.so）
└── README.md
```

## 环境要求

- Python 3.10+
- Redis（存储飞行计划）
- Kafka（接收遥测数据）

## 依赖安装

```bash
pip install kafka-python redis
```

可选：若需调用 C++ UTM 核心（冲突检测、轨迹预测），需在 `pylib/../build/` 下提供 `libutm_core.so`（Linux）或 `utm_core.dll`（Windows）。

## 配置说明

在 `main.py` 中修改以下配置：

| 配置项                                       | 说明                 | 默认示例             |
| -------------------------------------------- | -------------------- | -------------------- |
| `TARGET_DRONES`                              | 维持的活跃无人机数量 | 1000                 |
| `redis_ip` / `redis_port` / `redis_password` | Redis 连接           | 见代码               |
| `kafka_url`                                  | Kafka 集群地址       | 多节点逗号分隔       |
| `kafka_uav_data_topic`                       | 遥测 Topic           | `uav_runtime_data`   |
| `redis_flight_plan_key`                      | 飞行计划 Hash Key    | `BIZ_DATA:UAV_ROUTE` |

## 如何运行并推送数据到 Kafka

### 1. 安装依赖

```bash
pip install kafka-python redis
```

或使用项目中的依赖文件：

```bash
pip install -r requirements.txt
```

### 2. 配置 Kafka 地址

在 `main.py` 顶部修改 `kafka_url` 为你的 Kafka 集群地址（多个节点用英文逗号分隔）：

```python
# 示例：单节点
kafka_url = 'localhost:9092'

# 示例：集群（当前默认）
kafka_url = "10.165.19.227:30094,10.165.19.225:30094,10.165.19.215:30094"
```

Topic 默认为 `uav_runtime_data`，可在同一文件中修改 `kafka_uav_data_topic`。

### 3. 确保 Kafka 可访问

- Kafka 服务已启动
- 本机网络能访问上述地址（防火墙、VPN 等）
- 若 Kafka 未开自动创建 Topic，请先创建 Topic：`uav_runtime_data`

### 4. 启动程序

```bash
python main.py
```

- 若连接成功，终端会打印 **「Kafka 生产者初始化成功」**。
- 随后每秒会打印一次发送统计，例如：`数据大小: xxx, 发送时间:x.xx秒`，即表示数据已在推送到 Kafka。
- 若连接失败，会打印「Kafka 生产者初始化失败」及原因（检查地址、端口、网络）。

### 5. 停止程序

在运行窗口按 **Ctrl+C**，程序会安全退出。

---

## 运行方式（简要）

```bash
python main.py
```

- 启动后会先补足至 `TARGET_DRONES` 架无人机的飞行计划（写入 Redis），并在后台线程中约每 1 秒推进仿真并批量发送遥测到 Kafka。
- 使用 **Ctrl+C** 可安全停止（会等待仿真线程结束，最多 5 秒）。

## 数据流说明

1. **初始化**：按 `TARGET_DRONES` 数量生成飞行计划，每条计划写入 Redis（`BIZ_DATA:UAV_ROUTE`，field 为无人机 UID，value 为航线 JSON）。
2. **仿真循环**：每秒调用 `Simulator.step(1.0)`，更新所有无人机状态，得到遥测列表。
3. **下发**：将遥测转换为业务字段（如 `uniqueProductIdentificationCode`、经纬高、航向、速度、运营状态、时间戳等），通过 Kafka 批量发送到 `uav_runtime_data`。

仿真区域为苏州金鸡湖附近约 5km 半径；支持航路点轨迹与多边形区域盘旋，以及动态 4D 禁飞区生成（当前主循环未调用 C++ 冲突检测，仅做仿真与数据注入）。

## 仿真核心简要说明

- **DroneAgent**：单机状态机（IDLE → TAKEOFF → CRUISE/HOVER → LANDING → FINISHED），支持轨迹飞行与区域盘旋。
- **Simulator**：`generate_plan()` 随机生成航路或区域任务；`generate_nfzs()` 生成动态禁飞区；`step()` 推进仿真并返回遥测列表。
- **pylib/engine.UTMEngine**：若已部署 C++ 库，可调用轨迹预测、战术/战略/预飞冲突检测、偏航检测、双机最小距离等接口。

## 许可证与备注

- 请根据实际环境修改 Redis/Kafka 地址与密钥，勿将生产密码提交版本库。
- 当前主流程仅做仿真与数据注入；如需在循环中启用冲突检测，需在 `main.py` 中实例化 `UTMEngine` 并调用相应接口。
