# UAV 数据发射器 - 场景化管理版

支持多场景、可选择 UAV、并发发送的 UAV 数据发射工具。

## 目录结构

```
uav_emitter/
├── config.yaml              # 全局配置
├── emitter.py               # 主程序
├── kafka_proc.py            # Kafka 生产者客户端（可选）
├── scenes/                  # 场景文件夹
│   ├── 偏离预设计划类/      # 偏离航线场景
│   │   └── 最低安全高度/    # 最低安全高度测试
│   │       ├── scene.yaml   # 场景配置
│   │       ├── UAV_scene01_normal_safe_flight.json
│   │       └── ...
│   ├── 独立测试用例/        # 独立测试场景
│   │   ├── scene.yaml
│   │   ├── 1.json
│   │   └── 2.json
│   ├── 短期冲突类/          # 冲突检测场景
│   │   ├── 告警趋势解除功能验证/
│   │   ├── 水平并排飞行/
│   │   ├── 水平迎头相撞/
│   │   └── 水平追赶冲突/
│   └── 空域侵入类/          # 空域侵入场景
│       ├── 禁区侵入类/
│       └── 危险区侵入类/
└── logs/
```

## 执行逻辑流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           启动 emitter.py                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  1. main() 主函数                                                        │
│     └── print_banner() 打印启动横幅                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. ConfigManager() 配置管理器                                           │
│     └── 读取 config.yaml                                                │
│         ├── kafka.url / kafka.topic     → Kafka 连接信息                 │
│         ├── scenes_path                 → 场景文件夹路径                  │
│         ├── active_scenes               → 激活的场景列表                  │
│         └── emitter.*                   → 发射器配置                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. SceneLoader() 场景加载器                                             │
│     └── 根据 active_scenes 加载场景                                      │
│         └── _load_scene()                                               │
│             └── 读取 scenes/<场景名>/scene.yaml                          │
│                 └── 解析 UAV 文件列表 (uavs[].file)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. DataLoader() 数据加载器                                              │
│     └── load_uav_data(scene)                                            │
│         └── 遍历 scene.uavs 列表                                         │
│             └── _load_json(file_path)                                   │
│                 └── 读取 scenes/<场景>/<uav文件>.json                    │
│                     └── 解析 UAV 飞行数据数组                            │
│                         └── 提取 uniqueProductIdentificationCode         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  5. 创建 Emitter() 发射器                                                │
│     └── 传入: kafka_config + all_uav_data (UAVData 列表)                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  6. emitter.start() 启动发射                                             │
│     └── 创建后台线程 _emit_loop()                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  7. _emit_loop() 发射循环                                                │
│     └── 定时调用 _emit_once()                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  8. _emit_once() 单次发射                                                │
│     ├── 遍历所有 UAVData                                                │
│     │   └── uav.next() 获取下一条记录                                    │
│     │       └── _process_timestamp() 处理时间戳                          │
│     └── 汇总所有 UAV 的当前记录                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  9. kafka.send_bulk(records, topic)                                      │
│     └── 调用 KafkaProducerClient.send_bulk()                             │
│         └── 发送到 Kafka 服务器 (config.yaml 中配置的 url)               │
│             └── Topic: uav_runtime_data                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流向总结

| 步骤 | 读取文件 | 获取数据 | 处理后传给 | 最终发送给 |
|------|----------|----------|------------|------------|
| 配置加载 | `config.yaml` | Kafka配置、场景列表、发射器配置 | ConfigManager | - |
| 场景加载 | `scenes/<场景>/scene.yaml` | UAV文件列表 | SceneLoader | - |
| 数据加载 | `scenes/<场景>/<uav>.json` | UAV飞行轨迹数据 (经纬度、高度、速度等) | DataLoader → UAVData | - |
| 发射 | - | 处理后的记录 (更新时间戳) | Emitter | KafkaProducerClient |
| 发送 | - | 批量记录 | KafkaProducerClient | **Kafka 服务器** |

### 关键类职责

| 类 | 职责 |
|----|------|
| `ConfigManager` | 管理全局配置 |
| `SceneLoader` | 加载场景配置 |
| `DataLoader` | 加载 UAV JSON 数据文件 |
| `UAVData` | 封装单个 UAV 的数据和状态 |
| `Emitter` | 控制发射循环和时间戳处理 |
| `KafkaProducerClient` | 实际发送数据到 Kafka |

## 快速开始

### 方式一：使用独立测试用例（推荐用于单架无人机测试）

#### 1. 准备 UAV 数据

复制 `scenes/独立测试用例/` 中的 JSON 文件，修改航空器识别码：

```bash
cp scenes/独立测试用例/1.json scenes/独立测试用例/3.json
```

编辑 `3.json`，修改第3-4行的识别码：
```json
{
  "uniqueProductIdentificationCode": "YOUR_UAV_ID_001",
  "realNameRegistrationSign": "YOUR_UAV_ID_001",
  ...
}
```

#### 2. 配置场景

编辑 `scenes/独立测试用例/scene.yaml`，启用你的文件：

```yaml
name: "独立测试用例"
description: "根据测试实际情况编辑执行"

uavs:
  - file: "3.json"          # 你的测试文件
    enabled: true
```

#### 3. 激活场景

编辑 `config.yaml`，启用独立测试用例场景：

```yaml
active_scenes:
  - "独立测试用例"
```

#### 4. 运行

```bash
python emitter.py
```

---

### 方式二：使用现有场景（推荐用于复杂场景测试）

#### 1. 配置全局设置

编辑 `config.yaml`：

```yaml
kafka:
  url: "10.165.19.213:30011"  # Kafka 服务器地址
  topic: "uav_runtime_data"

# 激活的场景（为空则加载所有场景）
active_scenes:
  - "偏离预设计划类/最低安全高度"
  # - "短期冲突类/水平迎头相撞"
  # - "空域侵入类/禁区侵入类/禁区为长方体"

emitter:
  interval_ms: 1000           # 发射间隔（毫秒）
  timestamp_mode: replace     # 时间戳处理模式
  loop: false                 # 是否循环播放
```

#### 2. 配置场景

编辑对应场景的 `scene.yaml`，例如 `scenes/偏离预设计划类/最低安全高度/scene.yaml`：

```yaml
name: "最低安全高度测试"
description: "测试无人机最低安全高度告警"

uavs:
  - file: "UAV_scene01_normal_safe_flight.json"
    enabled: true             # 启用发射
    
  - file: "UAV_scene02_sustained_low_altitude.json"
    enabled: false            # 禁用（不发射）
```

#### 3. 运行

```bash
python emitter.py
```

## 配置说明

### 全局配置 (config.yaml)

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `kafka.url` | Kafka 服务器地址 | localhost:9092 |
| `kafka.topic` | Kafka Topic | uav_runtime_data |
| `scenes_path` | 场景文件夹路径 | scenes/ |
| `active_scenes` | 激活的场景列表（为空则加载所有） | [] |
| `emitter.interval_ms` | 发射间隔（毫秒） | 1000 |
| `emitter.timestamp_mode` | 时间戳处理模式：replace/align/preserve | replace |
| `emitter.loop` | 是否循环播放 | false |

**active_scenes 配置说明：**
- 填写场景文件夹的相对路径，如 `"独立测试用例"` 或 `"偏离预设计划类/最低安全高度"`
- 空列表 `[]` 表示加载所有场景
- 使用 `#` 注释可临时禁用某个场景

### 场景配置 (scene.yaml)

| 配置项 | 说明 |
|--------|------|
| `name` | 场景名称 |
| `description` | 场景描述 |
| `uavs` | UAV 列表 |
| `uavs[].file` | UAV 数据文件（JSON格式） |
| `uavs[].enabled` | 是否启用发射（true/false） |
| `uavs[].delay_ms` | 延迟发射（毫秒，可选） |

### UAV 数据文件格式 (JSON)

UAV 数据文件为 JSON 数组，每条记录包含：

| 字段 | 说明 | 示例 |
|------|------|------|
| `uniqueProductIdentificationCode` | 航空器唯一识别码 | `"U5RQF0QH2OEIMLNGAI72"` |
| `realNameRegistrationSign` | 实名登记标识 | `"U5RQF0QH2OEIMLNGAI72"` |
| `longitude` | 经度 | `120.735` |
| `latitude` | 纬度 | `31.32` |
| `geodeticAltitude` | 大地高度（米） | `120.7` |
| `speed` | 地速（m/s） | `15.18` |
| `trackAngle` | 航迹角（度） | `90.01` |
| `verticalSpeed` | 垂直速度（m/s） | `0.68` |
| `timestamp` | 时间戳（毫秒） | `1773734986016` |
| `operatingStatus` | 运行状态 | `2` |

## 使用示例

### 示例1：只发送独立测试用例中的特定 UAV

```yaml
# config.yaml
active_scenes:
  - "独立测试用例"

# scenes/独立测试用例/scene.yaml
uavs:
  - file: "1.json"
    enabled: true
  - file: "2.json"
    enabled: false    # 禁用
```

### 示例2：同时发送多个场景

```yaml
# config.yaml
active_scenes:
  - "独立测试用例"
  - "偏离预设计划类/最低安全高度"
```

### 示例3：发送所有场景

```yaml
# config.yaml
active_scenes: []     # 空列表表示加载所有场景
```

### 示例4：延迟发射（多机编队场景）

```yaml
# scenes/编队飞行/scene.yaml
uavs:
  - file: "UAV_leader.json"    # 长机先发射
    enabled: true
    delay_ms: 0
  - file: "UAV_wingman.json"   # 僚机延迟5秒后发射
    enabled: true
    delay_ms: 5000
```

## 时间戳处理模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `replace` | 替换为当前时间（默认） | 实时模拟，每次运行都使用当前时间 |
| `align` | 对齐到当前时间，保持相对间隔 | 保持原始数据的时间间隔关系，但整体对齐到当前 |
| `preserve` | 保留原始时间戳 | 回放历史数据，保持原始时间 |

## 添加新场景

### 步骤1：创建场景文件夹

```bash
mkdir scenes/我的新场景
```

### 步骤2：创建场景配置

创建 `scenes/我的新场景/scene.yaml`：

```yaml
name: "我的新场景"
description: "场景描述说明"

uavs:
  - file: "UAV_001.json"
    enabled: true
```

### 步骤3：准备 UAV 数据文件

从现有场景复制或创建新的 JSON 文件：

```bash
cp scenes/独立测试用例/1.json scenes/我的新场景/UAV_001.json
```

修改识别码为你需要的值：
```json
{
  "uniqueProductIdentificationCode": "MY_UAV_001",
  "realNameRegistrationSign": "MY_UAV_001",
  ...
}
```

### 步骤4：激活场景

编辑 `config.yaml`：

```yaml
active_scenes:
  - "我的新场景"
```

### 步骤5：运行测试

```bash
python emitter.py
```

## 集成 Kafka

### 方式一：使用系统路径（推荐）

确保 `kafka_proc.py` 在 Python 系统路径中，emitter.py 会自动导入：

```python
from kafka_proc import KafkaProducerClient
```

### 方式二：手动指定路径

修改 `emitter.py` 第29行的路径：

```python
KAFKA_PROC_PATH = "/path/to/your/project"  # <-- 修改这里
```

### 方式三：模拟模式（测试用）

如果找不到 `kafka_proc`，会自动切换到模拟模式，数据不会发送到 Kafka，仅在控制台打印：

```
[模拟发送] 1 条到 uav_runtime_data
```

## 输出示例

### 正常启动

```
╔══════════════════════════════════════════════════════════════╗
║           🚁 UAV 数据发射器 - 场景化管理版                    ║
╚══════════════════════════════════════════════════════════════╝

📂 场景列表:
  1. 独立测试用例
     描述: 根据测试实际情况编辑执行
     UAV: 1/2 启用
       ✅ 3.json
       ⏭️ 2.json

📥 加载 UAV 数据...

  📍 独立测试用例:
    ✅ YOUR_UAV_ID_001: 500 条记录

✅ 共加载 1 架 UAV

🚀 发射器启动
   Kafka: 10.165.19.213:30011
   Topic: uav_runtime_data
   间隔: 1000ms
   时间戳模式: replace
📤 ['YOUR_UAV_ID_001'] | 进度: 1/500 (0.2%)
📤 ['YOUR_UAV_ID_001'] | 进度: 2/500 (0.4%)
...
🏁 所有 UAV 数据已耗尽
🛑 发射器已停止
```

### 模拟模式

```
⚠️  警告: 未找到 kafka_proc 模块，使用模拟发送（不会发送到 Kafka）
   [模拟模式] Kafka URL: 10.165.19.213:30011
   [模拟发送] 1 条到 uav_runtime_data
```

## 常见问题

### Q: 如何批量生成多个 UAV 测试文件？

A: 可以编写脚本批量复制和修改 JSON 文件，修改 `uniqueProductIdentificationCode` 字段即可。

### Q: 如何制造偏离航线的数据？

A: 修改 JSON 文件中的 `longitude` 和 `latitude` 字段，使其偏离预定航线坐标。

### Q: 如何调整发射速度？

A: 修改 `config.yaml` 中的 `emitter.interval_ms`，值越小发射越快。

### Q: 如何循环播放数据？

A: 设置 `emitter.loop: true`，数据发送完毕后会重新开始。

## 现有场景说明

| 场景分类 | 子场景 | 用途 |
|----------|--------|------|
| 独立测试用例 | - | 单架无人机基础测试 |
| 偏离预设计划类 | 最低安全高度 | 测试高度偏离告警 |
| 短期冲突类 | 水平迎头相撞 | 测试对头冲突检测 |
| 短期冲突类 | 水平追赶冲突 | 测试追尾冲突检测 |
| 短期冲突类 | 水平并排飞行 | 测试并行飞行场景 |
| 短期冲突类 | 告警趋势解除 | 测试告警解除逻辑 |
| 空域侵入类 | 禁区侵入 | 测试禁飞区告警 |
| 空域侵入类 | 危险区侵入 | 测试危险区告警 |
