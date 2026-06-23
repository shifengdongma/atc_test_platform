# UTM MOC52 项目说明（CLAUDE 规则）

本文件为 AI 辅助编码时的**最高优先级**规则与上下文，生成或修改代码时请严格遵循。

## 项目概述

- **名称**：utm_moc52
- **用途**：UTM（无人机交通管理）仿真与数据注入服务。通过 Python 仿真多架无人机飞行过程，将**飞行计划**写入 Redis，将**实时遥测**写入 Kafka，供下游 UTM 系统、态势或算法使用。
- **技术栈**：Python 3.10+、Redis、Kafka；可选 C++ UTM 核心库（pylib 封装）。

## 目录与文件约定

| 路径                 | 说明                                                                                                                        |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `main.py`            | 主入口：DataSource + 仿真循环，Redis/Kafka 读写                                                                             |
| `simulation_core.py` | 无人机仿真核心（DroneAgent、Simulator、禁飞区等）                                                                           |
| `kafka_proc.py`      | Kafka 生产者/消费者封装                                                                                                     |
| `redis_client.py`    | Redis 客户端封装（hset/hget/hgetall 等）                                                                                    |
| `pylib/`             | 与 C++ UTM 核心一致的数据结构（structs.py）及引擎封装（engine.py）                                                          |
| `_source/`           | **数据与规范**：算法对接文档、nfzs.json、plans.json、telemetries.json 等原始或规范数据                                      |
| `tools/`             | **脚本工具**：run_kafka.py（Mock 数据注入）、nfzs.py（空域上传）、transform.py、create_data.py、trajectory_accuracy\*.py 等 |
| `mock/`、`json/`     | 运行时生成的 Mock 数据或输出 JSON（如 redis_route.json、kafka_data.json、redis_trace.json）                                 |

- 新增「从 JSON 读入并写入 Redis/Kafka」类脚本时，**优先参考 `tools/run_kafka.py`**（路径处理、Redis hset、编码等）。
- 数据格式、字段含义、枚举值等以 **`_source/算法对接 2026030301.md`** 为准；新增或修改与算法对接相关的结构时，必须与该文档一致。

## 代码风格与规范

1. **编码与头部**：所有 Python 文件使用 UTF-8，文件头写 `# -*- coding: utf-8 -*-`。
2. **中文**：注释、文档字符串、打印信息统一使用**中文**；与外部系统一致的字段名、枚举值按文档使用英文。
3. **类型注解**：新代码推荐使用 `typing`（如 `List[Dict[str, Any]]`、`Optional[str]`、`-> None`），与现有代码风格保持一致。
4. **项目根路径**：在 `tools/` 下运行的脚本，应把项目根目录加入 `sys.path`，便于 `from redis_client import RedisClient` 等无包前缀导入：
   ```python
   _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
   if _root not in sys.path:
       sys.path.insert(0, _root)
   ```
5. **JSON 读写**：使用 `json.load`/`json.dump` 时统一 `encoding='utf-8'`，写入时使用 `ensure_ascii=False`，以正确保存中文。

## Redis / Kafka 约定

- **Redis**
  - 飞行计划 Hash：`BIZ_DATA:UAV_ROUTE`，field 为无人机 UID，value 为单机航线 JSON。
  - 空域 Hash：`BIZ_DATA:AIRSPACE`，field 为空域 ID（如 1、2、3），value 为单条空域 JSON（结构见算法对接文档「空域数据」小节）。
  - 写入使用 `RedisClient.hset(key, field, value)`，其中 `value` 为已序列化的 JSON 字符串。
- **Kafka**
  - 遥测 Topic：`uav_runtime_data`（无人机上报数据格式见算法对接文档）。
  - 追踪 Topic：`uav_runtime_trace`（下游消费后可能按 redisKey 再查 Redis）。
- 连接配置（ip/port/password、bootstrap_servers）与 `main.py` 或 `tools/run_kafka.py` 中保持一致即可；敏感信息勿提交版本库。

## 数据格式与转换

- **空域（AIRSPACE）**：标准字段包括 `airspaceId`、`spcNo`、`name`、`typeCode`、`status`、`times`、`usagePurpose`、`lowestHeight`、`highestHeight`、`capacity`、`monitorAbility`、`polygon`（GeoJSON Polygon）等，详见 `_source/算法对接 2026030301.md` 第 677–774 行附近。
- **禁飞区/空域来源**：`_source/nfzs.json` 为 key 式对象（如 NFZ_001），需转换为上述标准空域格式后再写入 `BIZ_DATA:AIRSPACE`；转换逻辑见 `tools/nfzs.py`。
- **时间格式**：业务时间使用字符串 `yyyy-MM-dd HH:mm:ss`；Kafka/内部可沿用时间戳（秒或毫秒），写入 Redis 前按文档转成字符串。

## 新增脚本或功能时

1. 若在 `tools/` 下新增脚本，沿用 `run_kafka.py` 的路径与 Redis/Kafka 用法，并从 `_source/` 读取所需 JSON 或规范。
2. 涉及算法接口、Redis key、Kafka topic、字段名或枚举时，以 `_source/算法对接 2026030301.md` 为准，不臆造字段。
3. 保持与现有代码一致的风格（UTF-8、中文注释、类型注解、根路径插入）。

遵循以上规则可保证与现有 UTM 仿真、Redis/Kafka 数据流及算法对接文档一致。
