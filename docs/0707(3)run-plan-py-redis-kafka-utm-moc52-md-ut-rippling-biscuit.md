# UTM 模拟器第三轮优化：工具脚本集成到前端

## Context

用户需要将 `tools/` 目录中的两类脚本能力集成到 Web 前端：

1. **数据创建脚本**（`create_data.py` / `create_data_scene.py` / `create_data_scenes.py`）：三个脚本功能差异大，需在前端分别体现，支持可视化数据创建
2. **仿真模拟脚本**（`run_kafka_alive.py` / `run_kafka_scene.py` / `run_kafka.py` / `run_plan.py`）：四种仿真模式差异大，需在模式选择器中区分并附带说明

### 脚本差异关键发现

**数据创建三类**：
- `create_data.py`（178行）：基础随机生成，依赖 Simulator 引擎，唯一同时输出 routes + telemetry
- `create_data_scene.py`（745行）：单机场景，线性插值，支持偏离航路 + 状态变更，可查数据库航线
- `create_data_scenes.py`（2065行）：11 子命令的综合工厂，平行飞行/偏离/碰撞/状态告警/模板扩展/批量预设

**仿真模式四类**：
- `run_kafka.py`：预生成回放(单次)，数据耗尽自动停止，自动调用精度校验
- `run_kafka_alive.py`：预生成回放(循环)，永不停止，每轮刷新 Redis 航线实现持续数据流
- `run_kafka_scene.py`：场景文件注入，三种时间戳模式(replace/align/preserve)，可配置间隔
- `run_plan.py`：Redis 计划插值，从路线段数学插值生成遥测，持续监听 Redis 计划变更

### 硬约束
- 不修改现有 Redis/Kafka 数据链路（`BIZ_DATA:UAV_ROUTE`、`uav_runtime_data`、`uav_runtime_trace`）
- 不修改 `sim_manager.py`、`redis_client.py`、`kafka_proc.py`、`simulation_core.py` 核心逻辑
- 保持现有暗色主题 UI 风格

---

## 实施方案

### 一、数据创建 UI 重组

将当前扁平表单改为分类 Tab 结构：

| Tab | 子项 | 对应脚本 |
|-----|------|----------|
| **基础生成** | 随机散点 / 网格分布 / 放射状（增强现有） | `create_data.py` |
| **单机场景** | 航线飞行 / 偏离航路 / 状态变更 | `create_data_scene.py` |
| **多机场景** | 平行飞行 / 偏离航路(高级) / 碰撞预警 / 状态告警 | `create_data_scenes.py` |
| **批量预设** | 一键批量生成（11个区域预设） | `create_data_scenes.py batch` |

#### 各 Tab 参数设计

**基础生成**（复用现有表单，微调）：
- 架数、中心经纬度、半径(m)、分布模式、飞行时长(min)
- 后端改为调用 `create_data.py` 的 Simulator 引擎（唯一能同时生成 routes + telemetry 的方式）

**单机场景 > 航线飞行**：
- UID（文本）、航线名（文本，可选查数据库）、途经点（`lon,lat,alt;lon,lat,alt` 格式）
- 或：起点经纬度 + 终点经纬度（替代途经点）
- 高度(m) 默认30、速度(m/s) 默认15、采样间隔(ms) 默认1000

**单机场景 > 偏离航路**：
- 以上所有航线参数 +
- 启用偏离（复选框）、偏离量(度)、偏离起始点序号
- 运行状态（下拉：已落地/飞行中）

**单机场景 > 状态变更**：
- 初始运行状态、状态变更时间(ms)、变更后状态

**多机场景 > 平行飞行**：
- 架数(默认30)、中心经纬度、高度(m) 默认50、速度(m/s) 默认15
- 航向角(度，0=北，90=东)、间距(m) 默认2000、布局(hex/line)
- 每机轨迹点数(默认1200)、采样间隔(ms) 默认1000

**多机场景 > 偏离航路(高级)**：
- 航线名（必填）、偏离量(m) 默认3000、偏离起始秒数 默认20
- 过渡时长(s，自动计算)、偏离模式(水平/垂直/同时)
- 垂直偏离量(m)、速度(m/s)、高度(m)

**多机场景 > 碰撞预警**：
- 航线名(逗号分隔2条)、无人机UID(逗号分隔2个)
- 相遇阈值(m) 默认10、碰撞时间(s) 默认300

**多机场景 > 状态告警**：
- 架数、中心经纬度、高度、速度、飞行时长(min)
- 紧急恢复(复选框)、失联(复选框)、紧急→失联(复选框)

**批量预设**：
- 11 个按钮，每个对应一个 BATCH_CONFIGS 预设
- 点击后一次生成对应区域的平行飞行数据

### 二、仿真模式选择器重组

将 `<select>` 从 3 个选项扩展到 5 个，选中时显示说明文字：

| 值 | 标签 | 说明 | 对应脚本 |
|----|------|------|----------|
| `dynamic` | 🎮 动态仿真 | 实时生成飞行计划，Simulator引擎计算遥测，持续运行 | main.py |
| `replay` | 🔁 预生成回放(循环) | 读取mock目录JSON循环发射，每轮刷新Redis航线，永不停止 | run_kafka_alive.py |
| `replay_once` | ▶️ 预生成回放(单次) | 读取mock目录JSON回放一次，数据耗尽自动停止并输出精度报告 | run_kafka.py |
| `scene` | 🎬 场景文件注入 | 选择场景JSON文件，按配置间隔发射，可控时间戳模式 | run_kafka_scene.py |
| `plan` | 📐 Redis计划插值 | 从Redis读取飞行计划，沿路线段数学插值生成平滑遥测 | run_plan.py |

选择 `replay_once` / `replay` 时：显示数据源文件选择器（从 mock/ 目录选 kafka_data + redis_route）
选择 `scene` 时：显示场景文件选择器 + 间隔(ms) + 时间戳模式(replace/align/preserve) + 是否循环

### 三、后端 API 新增

#### 3.1 桥接层（新文件 `web_data_gen_bridge.py`）

创建独立桥接文件，导入 tools 脚本的内部函数并包装为 API 友好的调用接口，避免直接 `main()` 调用导致的 `sys.exit()` 问题：

```python
# 包装函数示例
def gen_parallel(count, center_lng, center_lat, ...):
    """平行飞行数据生成"""
    ns = argparse.Namespace(count=count, ...)
    from tools.create_data_scenes import run_parallel
    run_parallel(ns)
    return {"file": ns.output, "count": count}
```

#### 3.2 新增 API 端点（在 `web_server.py`）

| 端点 | 功能 |
|------|------|
| `POST /api/data/scene/single` | 单机航线飞行生成 |
| `POST /api/data/scene/deviate` | 单机偏离航路生成 |
| `POST /api/data/scene/parallel` | 多机平行飞行生成 |
| `POST /api/data/scene/deviate-adv` | 高级偏离航路（平滑过渡） |
| `POST /api/data/scene/collision` | 碰撞预警场景 |
| `POST /api/data/scene/status` | 状态告警场景 |
| `POST /api/data/scene/scale` | 模板扩展 |
| `POST /api/data/batch` | 批量预设（指定 config_index 或全部） |

#### 3.3 SimulationRunner 新增模式

在 `web_server.py` 的 `_sim_loop()` 中增加：
- `replay_once` 分支：导入 `run_kafka.py` 的 `DataSource`，逐 tick 调用 `get_next_batch()`，数据耗尽自动停止
- `scene` 分支：导入 `run_kafka_scene.py` 的 `SceneEmitter`，传入文件列表和参数，线程化发射

#### 3.4 `run_kafka.py` 微调

给 `DataSource` 类新增 `get_next_batch()` 方法（不改原有行为，纯增量）。

### 四、涉及文件

| 文件 | 操作 | 改动内容 |
|------|------|----------|
| `web_data_gen_bridge.py` | **新建** | 桥接层，包装 tools 脚本函数为 API 友好接口 |
| `web_server.py` | 修改 | +8 个数据生成 API 端点；`_sim_loop()` 增加 `replay_once`/`scene` 分支 |
| `tools/run_kafka.py` | 微调 | `DataSource` 新增 `get_next_batch()` 方法 |
| `web/index.html` | 修改 | 数据面板改为分类 Tab；模式选择器扩展到 5 选项 + 说明区；场景文件选择器 |
| `web/static/js/app.js` | 修改 | ~10 个新 handler；Tab 切换逻辑；模式说明更新；文件选择器联动 |
| `web/static/css/style.css` | 修改 | 新增 Tab/子Tab/批量按钮/模式说明/表单增强样式 |

**不修改的文件**：`sim_manager.py`、`redis_client.py`、`kafka_proc.py`、`simulation_core.py`、`config.py`

### 五、实施顺序

```
Phase 1: 后端基础（~3 个文件）
├── 1a. 创建 web_data_gen_bridge.py 桥接层
├── 1b. 给 run_kafka.py DataSource 添加 get_next_batch()
├── 1c. web_server.py 增加 8 个数据生成 API 端点
└── 1d. web_server.py SimulationRunner 增加 replay_once/scene 模式

Phase 2: 前端核心（~3 个文件）
├── 2a. index.html: 数据面板改为 Tab 结构 + 平行飞行表单
├── 2b. index.html: 模式选择器扩展 + 说明文字
├── 2c. app.js: Tab 切换 + 新表单 handler + 模式联联动
└── 2d. style.css: Tab/子Tab/表单/批量按钮样式

Phase 3: 高级功能
├── 3a. 单机场景三个子表单（航线飞行/偏离/状态变更）
├── 3b. 多机场景其余子表单（偏离高级/碰撞/状态告警/模板扩展）
├── 3c. 批量预设 Tab（11 个一键按钮）
└── 3d. 场景文件选择器联动

Phase 4: 验证
├── 4a. 每个 API 端点参数正确性验证
├── 4b. 前端 Tab 切换和表单提交流程验证
├── 4c. 确认不破坏现有 Redis/Kafka 数据链路
└── 4d. 更新 work-log 文档
```

### 六、注意事项

1. `create_data_scenes.py` 的 `deviate`/`collision`/`route` 依赖 `dmdbclient`（达梦数据库），如果数据库不可用则返回友好提示，引导用户使用基于坐标的方式
2. 大批量生成（>500 架）可能超时，需设置合理超时（120s+）并在前端显示加载状态
3. 桥接层绕过 `main()` 直接调用 `run_*()` 函数，避开 `sys.exit()`
4. 所有生成的文件输出到 `mock/` 目录，前端刷新文件列表可见
5. 模式选择器切换时实时显示对应模式的说明文字
