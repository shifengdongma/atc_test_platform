# UTM 模拟器数据传输链路文档

> 基于 utm_moc52 代码分析，详细描述仿真数据从创建到消费的完整链路。
>
> 最后更新：2026-07-07

---

## 一、系统架构概览

```
┌──────────────────────────────────────────────────────────────────────┐
│                          数据创建层                                    │
│  create_data.py  │  create_data_scene.py  │  create_data_scenes.py   │
│  (Simulator引擎)  │  (单机场景+偏离)         │  (11子命令综合工厂)         │
└────────┬─────────┴──────────┬─────────────┴───────────┬──────────────┘
         │                    │                         │
         ▼                    ▼                         ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                    JSON 文件 (mock/)                          │
    │  kafka_data.json  │  redis_route.json  │  kafka_data_*.json  │
    └──────────┬──────────────┬────────────────┬───────────────────┘
               │              │                │
    ┌──────────▼──────────────▼────────────────▼───────────────────┐
    │                       仿真运行层                               │
    │                                                              │
    │  ┌──────────────┐  ┌─────────────┐  ┌────────────────────┐   │
    │  │ dynamic 模式  │  │ replay 模式 │  │  plan 模式          │   │
    │  │ (实时仿真)     │  │ (JSON回放)  │  │  (Redis插值)        │   │
    │  │ Simulator    │  │ DataSource  │  │  RoutePlanSim      │   │
    │  │ 引擎驱动       │  │ 游标轮询     │  │ 数学插值             │   │
    │  └──────┬───────┘  └──────┬──────┘  └────────┬───────────┘   │
    │         │                 │                   │               │
    │         └─────────┬───────┴───────────────────┘               │
    │                   │                                           │
    └───────────────────┼───────────────────────────────────────────┘
                        │
          ┌─────────────┴──────────────┐
          ▼                            ▼
    ┌───────────┐              ┌──────────────┐
    │   Redis   │              │    Kafka     │
    │           │              │              │
    │ BIZ_DATA: │              │ uav_runtime_ │
    │ UAV_ROUTE │              │ data (遥测)   │
    │ (飞行计划)  │              │              │
    │           │              │ uav_runtime_ │
    │ BIZ_DATA: │              │ trace (轨迹)  │
    │ AIRSPACE  │              │              │
    │ (空域/NFZ)│              └──────┬───────┘
    └─────┬─────┘                     │
          │                           │
          └──────────┬────────────────┘
                     ▼
          ┌──────────────────┐
          │   ATC Dashboard  │
          │   (海豚态势感知)   │
          │                  │
          │ 读取 Redis 航线   │
          │ 消费 Kafka 遥测   │
          │ 展示实时态势       │
          └──────────────────┘
```

### 核心数据键/主题

| 存储 | 键/主题 | 类型 | 用途 |
|------|---------|------|------|
| Redis | `BIZ_DATA:UAV_ROUTE` | HASH | 飞行计划（航线） |
| Redis | `BIZ_DATA:AIRSPACE` | HASH | 空域/禁飞区 |
| Kafka | `uav_runtime_data` | TOPIC | 无人机实时遥测 |
| Kafka | `uav_runtime_trace` | TOPIC | 下游轨迹预测结果 |

> **硬约束**：这四个数据链路是 ATC Dashboard 的读写入口，**绝对不能修改**键名、主题名或消息格式。

---

## 二、数据创建层：JSON 文件生成

### 2.1 基础生成 (`create_data.py`)

**原理**：调用 `simulation_core.Simulator` 引擎，利用随机航点生成算法生成逼真的飞行计划，然后时间步进仿真产生完整遥测序列。

**输出文件**：
| 文件 | 格式 | 内容 |
|------|------|------|
| `mock/redis_route.json` | `[{key, value}, ...]` | 每条为 `{key: uid, value: {flightPlanList: [...]}}` |
| `mock/kafka_data.json` | `[{record}, ...]` | 扁平数组，每条为一次遥测采样 |

**生成流程**：

```
Simulator.generate_plan() × N
  ├── 随机航点序列（10-30个航点）
  │   ├── Waypoint 0: 起点 (alt=0, 起飞)
  │   ├── Waypoint 1: 同位置 (alt=cruise_alt, 爬升)
  │   ├── Waypoints 2..N-1: 随机游走
  │   │   ├── 段长: 90-3000m
  │   │   ├── 航向变化: ±90°
  │   │   └── 高度浮动: cruise_alt ± random(-50, 200)
  │   └── Waypoint N: 终点 (alt=0, 降落)
  └── planTakeoffTime=now, planLandTime=now+5400s (1.5小时)

Simulator.step(1.0) × (planLandTime - planTakeoffTime)秒
  └── 每个Agent.update() 沿航点推进，生成位置/速度/航向
      └── 输出 TelemetryData: {lon, lat, alt, speed, heading, ...}
```

### 2.2 单机场景 (`create_data_scene.py`)

**原理**：不依赖 Simulator 引擎，直接对航点序列做**线性插值**生成轨迹。支持偏离航路和状态变更。

**输入方式（三种，按优先级）**：
1. 数据库查询航线（`--route-name` 查 `air_route` 表）
2. 手动指定途经点（`--points "lon,lat,alt;lon,lat,alt;..."`）
3. 起终点坐标（`--start-lon/lat --end-lon/lat`）

**生成流程**：

```
build_waypoints(args) → [{lon, lat, alt}, ...]   # 构建航点列表
  │
  ▼
generate_trajectory(waypoints, uid, speed, interval)
  ├── 逐段线性插值: lerp(lon1, lon2, t), lerp(lat1, lat2, t), lerp(alt1, alt2, t)
  ├── 段内点数 = max(1, flight_sec * 1000 / interval_ms)
  ├── 垂直速度 = (alt2 - alt1) / flight_sec
  └── 终点: speed=0, 最后一个航点位置
  │
  ▼
apply_deviation(trajectory, offset_deg, start_index)  # 可选：坐标叠加偏移
  └── trajectory[i].longitude += offset_deg
      trajectory[i].latitude  += offset_deg             # 从 start_index 开始偏移
```

### 2.3 综合场景工厂 (`create_data_scenes.py`)

**原理**：11 个子命令的综合生成器，覆盖平行飞行、偏离航路、碰撞预警、状态告警等场景。

**关键子命令算法**：

| 子命令 | 算法 | 关键参数 |
|--------|------|----------|
| `parallel` | 六边形网格 / 直线编队，每条直线飞行 1200 点，ID 碰撞避让 | count, spacing, layout, heading |
| `deviate` | 沿航线中心线插值 → 基于平滑航向的**垂直偏移** → 平滑过渡渐变 | deviate_offset(m), deviate_mode |
| `collision` | 两航线交汇点检测 → 同步到达计算 → 区域标记(zone:1/2/3) | route_names, meeting_threshold |
| `status` | 多阶段轨迹: 地面(status=1)→爬升(2)→巡航(2)→告警(3或5) | scene3/scene5/scene3-5 |
| `scale` | 读取模板 JSON → 蜂窝网格分布 → 生成新 UID | source, count, spacing |
| `batch` | 迭代 11 个 BATCH_CONFIGS 预设（全国不同区域） | config_index |

---

## 三、仿真运行层：四种模式

### 3.1 Dynamic 模式（实时仿真）

**核心类**：`SimulationManager._tick_dynamic()` + `simulation_core.Simulator`

**数据流**：

```
启动 _init_dynamic_mode()
├── 创建 Simulator(origin_lat, origin_lon, sim_radius_m)
├── 循环 generate_plan() × target_drones
│   ├── 随机航点序列生成
│   ├── 注册 DroneAgent
│   └── _plan_to_route_json(plan) → Redis HSET BIZ_DATA:UAV_ROUTE
│       格式: {uid: {"uniqueProductIdentificationCode":..., "flightPlanList":[...]}}
├── generate_nfzs(count=3) → _nfz_to_json() → Redis HSET BIZ_DATA:AIRSPACE
│   格式: {airspaceId: {"airspaceId":..., "name":..., "polygon":...}}
└── 启动 _consume_trace() 线程（消费 uav_runtime_trace）

每秒 _tick_dynamic()
├── simulator.step(1.0) → [{"current": TelemetryData, "history": [...]}, ...]
│   └── 每个 Agent.update(): 航点跟踪、速度插值、状态机 (IDLE→TAKEOFF→CRUISE→LANDING→FINISHED)
├── _telemetry_list_to_kafka(telemetry_list) → List[Dict]
│   └── TELEMETRY_DEFAULTS + 动态字段(lon, lat, alt, speed, heading, ...)
├── kafka_producer.send_bulk(msgs, "uav_runtime_data")
│   ├── Key: uid.encode('utf-8')
│   ├── Value: json.dumps(msg).encode('utf-8')
│   └── 同时发送到主集群和镜像集群 (kafka_url2)
├── 移除已完成无人机，补充新无人机
└── _push_status() → WebSocket 推送前端
```

### 3.2 Replay 模式（JSON 回放）

#### 循环回放 (`replay`)

**核心类**：`SimulationManager._tick_replay()`

**数据流**：

```
启动 _init_replay_mode()
├── 加载 mock/redis_route.json → _shift_plan_times() → Redis HSET
│   时间平移: diff = now - planTakeoffTime
│            planTakeoffTime = now
│            planLandTime = landTime + diff      # 保持飞行时长不变
├── 加载 mock/kafka_data.json → 按 UID 建立索引
│   self._replay_index = {uid: [msg1, msg2, ...], ...}
│   self._replay_cursors = {uid: 0, ...}
└── 启动 _consume_trace() 线程

每秒 _tick_replay() — 轮询逻辑:
├── 对每个 UID:
│   ├── cursor = self._replay_cursors[uid]
│   ├── msg = copy(self._replay_index[uid][cursor])
│   ├── msg["timestamp"] = int(time.time() * 1000)   # 覆盖为当前时间
│   ├── batch.append(msg)
│   └── cursor += 1
├── kafka.send_bulk(batch, "uav_runtime_data")
└── 当 cursor >= len(messages):
    ├── cursor = 0                    # 重置 → 循环
    └── _refresh_single_redis_route(uid)
        └── 重新时间平移航线 → Redis HSET  # 触发下游系统重新激活追踪
```

#### 单次回放 (`replay_once`)

**核心类**：`run_kafka.DataSource`

与循环回放的区别：
- 数据耗尽后**自动停止**（不循环）
- 停止时调用 `trajectory_accuracy.py` 输出精度报告
- 可指定自定义文件路径（覆盖默认 `mock/kafka_data.json`）

**关键索引结构**：

```python
# DataSource 内部数据结构
self.kafka_data_list: List[Dict]          # 原始 JSON 数组（全部遥测记录）
self._uid_record_indices: Dict[str, List[int]]   # uid → 在数组中的位置列表
# 示例: {"UAV_00001": [0, 3, 7, 11, ...], "UAV_00002": [1, 4, 8, 12, ...]}
self._uid_cursor: Dict[str, int]                 # uid → 当前读取位置
# 示例: {"UAV_00001": 5, "UAV_00002": 3, ...}
self.data_exhausted: bool                        # 所有游标到达末尾
```

### 3.3 Plan 模式（Redis 计划插值）

**核心类**：`run_plan.PlanRunner` + `RoutePlanSim`

**原理**：不重放预录制数据，而是从 Redis 读取飞行计划的**航线段**，在每个时刻 `t` 通过**数学插值**合成逼真的遥测数据。

**数据流**：

```
启动 PlanRunner
├── merge_from_redis()
│   ├── Redis HGETALL BIZ_DATA:UAV_ROUTE → 解析所有飞行计划
│   ├── 过滤: planLandTime > now（未过期的计划）
│   ├── _shift_and_write_plan(): 时间平移航线 → 写回 Redis
│   │   duration = planLandTime - planTakeoffTime
│   │   planTakeoffTime = now
│   │   planLandTime = now + duration
│   └── 为每个有效计划创建 RoutePlanSim 实例
├── 启动 _watch_redis_loop()  # Redis keyspace 通知 + 60s 轮询
├── 启动 _tick_loop()         # 每秒插值发射
└── 启动 _consume_uav_runtime_trace()

每秒 _tick_loop() → tick_send()
├── _remove_expired(): 删除 planLandTime < now 的计划
├── 对每个活动计划:
│   ├── RoutePlanSim.sample(now)  → {lon, lat, alt, heading, speed, v_speed, operating_status}
│   │   ├── t < takeoff:  返回起点, speed=0, status=1 (未起飞)
│   │   ├── t >= land:    返回终点, speed=0, status=0 (已降落)
│   │   └── takeoff ≤ t < land: 插值
│   │       u = (t - takeoff) / (land - takeoff)      # 归一化进度 [0,1]
│   │       dist_target = u × total_horizontal_dist    # 沿路径的距离
│   │       定位所在航线段 → 段内插值 lon/lat/alt
│   │       speed = seg_h / seg_time                   # 地速 = 段距离 / 段时间
│   │       heading = bearing(段起点, 段终点)           # 航向角
│   │       v_speed = (end_alt - start_alt) / seg_time # 垂直速度
│   └── _telemetry_dict(): 将采样结果格式化为 Kafka 消息
└── kafka.send_bulk(batch, "uav_runtime_data")
```

**RoutePlanSim 核心数学**：

```
航线段解析:
  segment_i:
    h_len = sqrt(mx² + my²)                           # 水平距离
    其中 mx = (elon - slon) * cos(rad((slat+elat)/2)) * 111320.0
         my = (elat - slat) * 110540.0
  total_h = sum(seg_hlen)                             # 总路径长度

插值采样 (时间 t):
  u = (t - takeoff) / (land - takeoff)                # [0, 1]
  dist_target = u * total_h                           # 目标距离

  找到 dist_target 所在的航线段 i:
  if acc_h + seg_hlen[i] >= dist_target:
      seg_idx = i
      local = (dist_target - acc_h) / seg_hlen[i]     # 段内比例 [0, 1]
      lon = lerp(start_lon, end_lon, local)
      lat = lerp(start_lat, end_lat, local)
      alt = lerp(start_alt, end_alt, local)
```

### 3.4 Scene 模式（场景文件注入）

**核心类**：`run_kafka_scene.SceneEmitter`

**数据流**：

```
启动
├── _load_from_files() / _load_from_scene_dir()
│   └── 按 UID 分组 → {uid: [record1, record2, ...]}
│       创建 UAVData(uid, records) → 游标管理
├── _build_redis_route(): 从遥测点合成航线
│   └── 连续点对组成 routeList 段 → HSET BIZ_DATA:UAV_ROUTE
├── start() → 启动 _emit_loop() 线程
└── 可选: 启动 _consume_trace_loop() 线程

每 interval_ms 发射 _emit_once():
├── 遍历所有 UAVData:
│   ├── uav.next() → _process_timestamp() → 批量收集
│   └── 游标到达末尾:
│       ├── loop=True:  reset() 重置游标
│       └── loop=False: 结束
├── kafka.send_bulk(batch, topic)

三种时间戳模式:
├── replace:  msg["timestamp"] = int(time.time() * 1000) - 1000
├── align:    保持记录间相对偏移，首条对齐到首次发射时间
│              offset = record_ts - first_record_ts
│              return first_emit_time + offset
└── preserve: 保留原始时间戳不变
```

---

## 四、Redis 数据结构

### 4.1 飞行计划 (`BIZ_DATA:UAV_ROUTE`)

```
类型: HASH
键:   BIZ_DATA:UAV_ROUTE
字段: 无人机 UID (如 "DJI1MAV101A2B3C4D5E6")
值:   JSON 字符串
```

**值格式**：

```json
{
  "uniqueProductIdentificationCode": "DJI1MAV101A2B3C4D5E6",
  "flightPlanList": [
    {
      "flightPlanId": 1,
      "planTakeoffTime": 1751900000.123,
      "planLandTime": 1751905400.123,
      "flightTaskId": 1,
      "flightTaskName": "test",
      "routeList": [
        {
          "sequence": 0,
          "type": 2,
          "segmentStartLon": 120.665,
          "segmentStartLat": 31.315,
          "segmentEndLon": 120.672,
          "segmentEndLat": 31.320,
          "segmentStartHeight": 0.0,
          "segmentEndHeight": 120.5,
          "segmentProtectHeight": 50.0,
          "segmentProtectHeightType": 1,
          "segmentWidth": 100.0
        }
      ]
    }
  ]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `uniqueProductIdentificationCode` | string | 无人机唯一标识 |
| `flightPlanList` | array | 飞行计划列表（通常 1 个） |
| `flightPlanId` | int | 计划 ID |
| `planTakeoffTime` | float | 起飞时间（UNIX 秒） |
| `planLandTime` | float | 降落时间（UNIX 秒） |
| `routeList` | array | 航线段列表 |
| `sequence` | int | 航段序号（从 0 开始） |
| `type` | int | 航段类型（2=直线段） |
| `segmentStartLon/Lat` | float | 航段起点经纬度 |
| `segmentEndLon/Lat` | float | 航段终点经纬度 |
| `segmentStart/EndHeight` | float | 航段起止高度（米） |
| `segmentProtectHeight` | float | 保护高度（米） |
| `segmentProtectHeightType` | int | 保护高度类型（1=相对） |
| `segmentWidth` | float | 航段宽度（米） |

**读写操作**：

```python
# 写入航线（Python）
redis_client = RedisClient(host, port, password)
json_str = json.dumps(route_obj, ensure_ascii=False)
redis_client.hset("BIZ_DATA:UAV_ROUTE", uid, json_str)

# 读取全部航线（Python）
all_routes = redis_client.hgetall("BIZ_DATA:UAV_ROUTE")
# 返回: {"UAV_001": "{...json...}", "UAV_002": "{...json...}", ...}
for uid, raw in all_routes.items():
    plan = json.loads(raw)
```

### 4.2 空域/禁飞区 (`BIZ_DATA:AIRSPACE`)

```
类型: HASH
键:   BIZ_DATA:AIRSPACE
字段: 空域 ID (如 "NFZ_001")
值:   JSON 字符串
```

**值格式**：

```json
{
  "airspaceId": "NFZ_001",
  "spcNo": "",
  "name": "动态禁飞区",
  "typeCode": 1,
  "status": 1,
  "times": [],
  "usagePurpose": "",
  "lowestHeight": 0.0,
  "highestHeight": 500.0,
  "capacity": 0,
  "monitorAbility": 1,
  "polygon": {
    "type": "Polygon",
    "coordinates": [[[120.66, 31.31], [120.67, 31.32], [120.68, 31.31], [120.66, 31.31]]]
  }
}
```

---

## 五、Kafka 消息格式

### 5.1 无人机遥测 (`uav_runtime_data`)

```
主题:   uav_runtime_data
Key:    无人机 UID (bytes, UTF-8 编码)
Value:  JSON 字符串 (UTF-8 编码)
```

**完整消息格式**：

```json
{
  "uniqueProductIdentificationCode": "DJI1MAV101A2B3C4D5E6",
  "realNameRegistrationSign": "UAS01DJI1MAV001",
  "uasOperationCategory": 1,
  "classification": 1,
  "rpsLocationType": 1,
  "rpsLongitude": 0.0,
  "rpsLatitude": 0.0,
  "rpsAltitude": 0.0,
  "longitude": 120.6723,
  "latitude": 31.3185,
  "trackAngle": 45.2,
  "speed": 28.5,
  "geodeticAltitude": 125.3,
  "verticalSpeed": 0.0,
  "relativeAltitude": 0.0,
  "ressureAltitude": 0.0,
  "operatingStatus": 2,
  "coordinateSystemType": 0,
  "horizontalAccuracy": 1.0,
  "verticalAccuracy": 1.0,
  "speedAccuracy": 1.0,
  "timestamp": 1751900123123,
  "timestampAccuracy": 0,
  "sourceType": 1,
  "active": 1,
  "addInf": {}
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `uniqueProductIdentificationCode` | string | 无人机 UID — 作为 Kafka Key |
| `realNameRegistrationSign` | string | 实名登记号 |
| `uasOperationCategory` | int | 运行类别 |
| `classification` | int | 机型分类 (0=微型,1=轻型,2=小型,3=中型,4=大型) |
| `longitude` | float | 经度 (WGS-84) |
| `latitude` | float | 纬度 (WGS-84) |
| `trackAngle` | float | 航迹角 (度, 0=北, 顺时针) |
| `speed` | float | 地速 (m/s) |
| `geodeticAltitude` | float | 大地高 (米) |
| `verticalSpeed` | float | 垂直速度 (m/s) |
| `operatingStatus` | int | 运行状态 (0=已降落,1=未起飞,2=飞行中) |
| `timestamp` | int | 时间戳 (毫秒) |
| `active` | int | 是否活跃 (1=活跃, 0=停用) |
| `rps*` | float | 起降点位置（Remote Pilot Station） |
| `sourceType` | int | 数据来源类型 |
| `addInf` | object | 附加信息 |
| `coordinateSystemType` | int | 坐标系类型 (0=WGS-84) |
| `horizontalAccuracy` | float | 水平精度 (米) |
| `verticalAccuracy` | float | 垂直精度 (米) |
| `speedAccuracy` | float | 速度精度 (m/s) |

**各模式的时间戳行为**：

| 模式 | timestamp 来源 |
|------|---------------|
| dynamic | `int(time.time() * 1000)` — 实时毫秒 |
| replay (循环) | `int(time.time() * 1000)` — 实时毫秒覆盖 |
| replay (单次) | `int(time.time() * 1000)` — 实时毫秒覆盖 |
| plan | `int(time.time() * 1000)` — 实时毫秒覆盖 |
| scene (replace) | `int(time.time() * 1000) - 1000` — 实时毫秒 |
| scene (align) | `first_emit_time + (record_ts - first_record_ts)` — 保持相对偏移 |
| scene (preserve) | 原始时间戳不变 |

### 5.2 轨迹预测 (`uav_runtime_trace`)

```
主题:   uav_runtime_trace
来源:   下游 UTM 系统（非模拟器产生）
消费:   模拟器 trace 消费线程
```

**消息格式**：

```json
{
  "redisKey": "uav_runtime_trace:some_key",
  "uniqueProductIdentificationCode": "DJI1MAV101A2B3C4D5E6",
  "timestamp": 1751900500000,
  "longitude": 120.68,
  "latitude": 31.33,
  "geodeticAltitude": 55.0,
  "speed": 14.5,
  "trackAngle": 46.0
}
```

**消费逻辑**：
1. 从 Kafka 消费消息 → 提取 `redisKey`
2. `RedisClient.get_value_by_key(redisKey)` 回查 Redis 获取完整数据
3. 按活跃 UID 过滤
4. 记录到日志 / 保存到 `mock/redis_trace.json`

---

## 六、Web 前端与后端的数据交互

### 6.1 前端读取链路

```
Frontend (app.js)
  │
  ├── GET /api/sim/plans?limit=100
  │   └── Redis HGETALL BIZ_DATA:UAV_ROUTE → JSON → map.js 绘制航线
  │       每个路线段坐标经 wgs84ToGcj02() 转换后叠加到高德地图
  │
  ├── GET /api/sim/nfzs
  │   └── Redis HGETALL BIZ_DATA:AIRSPACE → JSON → map.js 绘制禁飞区
  │
  ├── WebSocket: status (每秒推送)
  │   └── {running, mode, active_drones, kafka_msg_per_sec, uptime_sec, ...}
  │
  └── GET /api/sim/config
      └── {mode, target_drones, redis_ip, redis_port, kafka_url, ...}
```

### 6.2 前端写入链路

```
Frontend (app.js)
  │
  ├── POST /api/sim/start {mode, target_drones, ...}
  │   └── SimulationRunner.start() → _sim_loop() → [dynamic/replay/plan/scene]
  │       └── 写入 Redis + Kafka（由后端仿真线程驱动）
  │
  ├── POST /api/data/files/generate {count, pattern, ...}
  │   └── 调用 Simulator 引擎生成 → 保存到 mock/ 目录
  │
  ├── POST /api/data/scene/parallel {count, spacing, ...}
  │   └── web_data_gen_bridge.gen_parallel() → create_data_scenes.run_parallel()
  │       └── 输出到 mock/kafka_data_parallel.json
  │
  └── POST /api/data/scene/collision {route_names, uids, ...}
      └── web_data_gen_bridge.gen_collision() → create_data_scenes.run_collision()
```

### 6.3 后端数据生成 API 与 tools 脚本的桥接

```
web_server.py (Flask 路由)
  │
  └── web_data_gen_bridge.py (桥接层)
      │
      ├── gen_parallel()    → tools/create_data_scenes.run_parallel()
      ├── gen_deviate_adv() → tools/create_data_scenes.run_deviate()
      ├── gen_collision()   → tools/create_data_scenes.run_collision()
      ├── gen_status()      → tools/create_data_scenes.run_status()
      ├── gen_scale()       → tools/create_data_scenes.run_scale()
      ├── gen_batch()       → tools/create_data_scenes.run_batch()
      ├── gen_single_route()   → tools/create_data_scene.generate_trajectory()
      └── gen_single_deviate() → tools/create_data_scene.generate_trajectory()
                                  + apply_deviation()
```

> 桥接层绕过 tools 脚本的 `main()` 入口（会调用 `sys.exit()`），直接调用内部 `run_*()` 函数，构造 `argparse.Namespace` 传参。

---

## 七、完整数据链路时间线

以 **Dynamic 模式**为例，从启动到 Dashboard 展示的完整时间线：

```
T+0s     前端 POST /api/sim/start → web_server.SimulationRunner.start()
T+0.1s   _init_dynamic_mode()
         ├── Simulator 创建 → 随机生成 N 架无人机飞行计划
         ├── _plan_to_route_json() × N → Redis HSET BIZ_DATA:UAV_ROUTE
         ├── generate_nfzs(3) → Redis HSET BIZ_DATA:AIRSPACE
         └── 启动 trace 消费线程
T+0.2s   WebSocket 推送: "仿真已启动"
         前端 setRunningState(true)

T+1s     _tick_dynamic()
         ├── simulator.step(1.0) → N 条 TelemetryData
         ├── _telemetry_list_to_kafka() → N 条 JSON 消息
         ├── kafka.send_bulk(N, "uav_runtime_data") ─────────┐
         └── _push_status() → WebSocket 推送状态              │
                                                              │
T+2s     _tick_dynamic() → 同上                                │
         ...                                                  │
                                                              ▼
                                              ┌─────────────────────────┐
                                              │  Kafka uav_runtime_data │
                                              │  每条消息 {uid, lon,     │
                                              │  lat, alt, speed, ...}  │
                                              └───────────┬─────────────┘
                                                          │
                                                          ▼
                                              ┌─────────────────────────┐
                                              │  ATC Dashboard 消费      │
                                              │  - 实时位置标注           │
                                              │  - 轨迹回放              │
                                              │  - 冲突检测              │
                                              └─────────────────────────┘

同时，Dashboard 定时读取:
  Redis HGETALL BIZ_DATA:UAV_ROUTE → 航线渲染
  Redis HGETALL BIZ_DATA:AIRSPACE → 禁飞区渲染

下游 UTM 系统:
  消费 uav_runtime_data → 轨迹预测 → 写入 uav_runtime_trace
  模拟器 trace 线程消费 → 回查 Redis → 记录/校验
```

---

## 八、关键技术细节

### 8.1 时间平移算法

所有回放/计划模式都需要将历史数据的时间平移到当前时刻，保证 Dashboard 看到的始终是"正在进行"的飞行：

```python
# 方案 A: 偏移法 (run_kafka.py)
diff = time.time() - planTakeoffTime
plan["planTakeoffTime"] = time.time()
plan["planLandTime"] = planLandTime + diff

# 方案 B: 重算法 (run_plan.py)
duration = planLandTime - planTakeoffTime
plan["planTakeoffTime"] = time.time()
plan["planLandTime"] = time.time() + duration

# 两种方案等价:
# B: time.time() + (planLandTime - planTakeoffTime)
#  = planLandTime + (time.time() - planTakeoffTime)
#  = planLandTime + diff
#  = A
```

### 8.2 Kafka 双集群镜像

```python
# kafka_proc.py KafkaProducerClient
def __init__(self, bootstrap_servers, bootstrap_servers_mirror=None):
    self.producer = KafkaProducer(bootstrap_servers=bootstrap_servers, ...)
    if bootstrap_servers_mirror:
        self.producer_mirror = KafkaProducer(bootstrap_servers=bootstrap_servers_mirror, ...)

def send_bulk(self, records, topic):
    for record in records:
        key = record.get("uniqueProductIdentificationCode").encode('utf-8')
        value = json.dumps(record).encode('utf-8')
        self.producer.send(topic, key=key, value=value)
        if self.producer_mirror:
            self.producer_mirror.send(topic, key=key, value=value)
```

### 8.3 ID 碰撞避让

`create_data_scenes.py parallel` 模式支持 Java `hashCode` 模拟的时间偏移计算：

```python
def compute_java_hash_code(s):
    h = 0
    for c in s:
        h = (31 * h + ord(c)) & 0xFFFFFFFF
        if h > 0x7FFFFFFF:
            h -= 0x100000000
    return abs(h)

# 不同 UID 产生不同 hashCode → 时间戳偏移不同 → 避免 ID 碰撞
```

---

## 九、文件索引

| 文件 | 职责 |
|------|------|
| `simulation_core.py` | Simulator 引擎 + DroneAgent 物理模型 |
| `sim_manager.py` | 统一编排层（dynamic/replay/plan 三模式） |
| `redis_client.py` | Redis Hash/List/Set/ZSet 读写封装 |
| `kafka_proc.py` | Kafka Producer/Consumer 封装（双集群镜像） |
| `tools/run_kafka.py` | 预生成数据回放（DataSource + DataFlow） |
| `tools/run_kafka_alive.py` | 预生成数据循环回放（SimulationManager 封装） |
| `tools/run_plan.py` | Redis 计划插值（PlanRunner + RoutePlanSim） |
| `tools/run_kafka_scene.py` | 场景文件注入（SceneEmitter + UAVData） |
| `tools/create_data.py` | 基础数据生成（Simulator 引擎） |
| `tools/create_data_scene.py` | 单机场景生成（线性插值 + 偏离） |
| `tools/create_data_scenes.py` | 综合场景工厂（11 子命令） |
| `web_server.py` | Web 后端（Flask + SocketIO + SimulationRunner） |
| `web_data_gen_bridge.py` | API 桥接层（tools 脚本 ↔ Flask 路由） |
| `config.py` | 统一配置（dataclass，env.py/config.json/环境变量） |
| `schemas.py` | 数据契约（TypedDict 定义） |
| `validators.py` | 数据校验（Pydantic 边界检查） |
