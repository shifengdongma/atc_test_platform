# 优化方案：数据管理 `/mock` 导入 + 数据生成航线关联

## Context

1. 数据管理模块的 `/mock` 导入功能每次无条件覆盖所有已存在记录，缺乏基于文件大小的跳过逻辑
2. 数据生成脚本查询错误的下游数据库表名（`air_route_element` → 应为 `air_route_segment`），导致航线数据查询失败
3. Docker 环境中 `dmPython` 驱动可能不可用，需确保回退方案

## 下游数据库表结构（已确认）

经由 `飞行任务创建.py` 和 `算法对接2026.md` 确认，下游 ATC 系统达梦数据库 (`ATC_DKWRJ_TEST`) 中航线相关表：

### `air_route` 表 — 航线主表
| 字段 | 说明 |
|------|------|
| `ID` | 航线主键 |
| `NAME` / `route_name` | 航线名称（如"铁门关至吐鲁番"）|
| `polygon` / `POLYGON` | 航线几何 polygon |
| `minimum_safe_altitude` | 最低安全高度（米）|
| `vertical_altitude` | 垂直高度（米）|
| `width` | 航路宽度（米）|

### `air_route_segment` 表 — 航段坐标点（★ 核心：这是正确的表名）
| 字段 | 类型 | 说明 |
|------|------|------|
| `ID` | BIGINT | 主键 |
| `AIR_ROUTE_ID` | BIGINT | 关联 air_route.ID |
| `SEGMENT_SEQ` / `AIR_ROUTE_SEGMENT_SEQ` | VARCHAR | 序号 |
| `TYPE` | INT | 2=航段, 3=作业区 |
| `START_POINT_LON` | DOUBLE | 起点经度 |
| `START_POINT_LAT` | DOUBLE | 起点纬度 |
| `START_POINT_HEIGHT` | DOUBLE | 起点高度 |
| `END_POINT_LON` | DOUBLE | 终点经度 |
| `END_POINT_LAT` | DOUBLE | 终点纬度 |
| `END_POINT_HEIGHT` | DOUBLE | 终点高度 |
| `WIDTH` | DOUBLE | 航段宽度 |
| `PROTECT_HEIGHT` | DOUBLE | 保护区高度 |

### 对比：当前代码的错误
- 当前代码查询：`air_route_element` → 字段 `start_point_lon`, `start_point_lat`, `end_point_lon`, `end_point_lat`, `sequence`, `route_id`, `is_deleted`
- 正确表名应为：`air_route_segment` → 字段 `START_POINT_LON`, `START_POINT_LAT`, `END_POINT_LON`, `END_POINT_LAT`, `SEGMENT_SEQ`, `AIR_ROUTE_ID`

**根因：表名和字段名都不对！** `air_route_element` 可能不存在或结构不同。

## 修改方案

### 修改 1：修复 `import_from_mock()` — 增加文件大小比较

**文件**：`database/json_data_manager.py`

**改动**：在 `import_from_mock()` 中导入每个文件前先查 DB，按 `name + size_bytes` 去重：

```python
existing = query(TABLE, where="name = ?", params=(fname,))
if existing:
    if existing[0].get("size_bytes") == size:
        skipped += 1  # 大小相同，跳过
        continue
    # 大小不同，走 update 逻辑
# 新文件，走 insert 逻辑
```

### 修改 2：修复 `query_route_elements()` — 更正表名和字段名

**涉及文件**（3 个脚本中相同的函数签名）：

| 文件 | 函数 | 行号 |
|------|------|------|
| `utm_simulator/tools/create_data_scenes.py` | `query_route_elements()` | L463-511 |
| `test_data_create/偏离航路数据生成(基于航路).py` | `query_route_elements()` | L518-595 |
| `test_data_create/飞行计划告警轨迹点位生成(基于航路).py` | `query_route_elements()` | L504-581 |

**改动**：
1. 表名从 `["air_route_element", "AIR_ROUTE_ELEMENT"]` 改为 `["air_route_segment", "AIR_ROUTE_SEGMENT"]`
2. 字段名修正：
   - `route_id` → `AIR_ROUTE_ID`
   - `sequence` → `SEGMENT_SEQ` (或 `AIR_ROUTE_SEGMENT_SEQ`)
   - `start_point_lon` → `START_POINT_LON`
   - `start_point_lat` → `START_POINT_LAT`
   - `end_point_lon` → `END_POINT_LON`
   - `end_point_lat` → `END_POINT_LAT`
3. 移除 `is_deleted` 过滤条件（`air_route_segment` 表无此字段）
4. 增加 `TYPE = 2` 过滤（仅取航段，排除作业区 type=3）
5. 增加高度字段读取：`START_POINT_HEIGHT`, `END_POINT_HEIGHT`

### 修改 3：修复 `query_air_route()` — 更正字段名兼容

**涉及文件**：同上 3 个文件中的 `query_air_route()` 函数

**改动**：
1. 确认表名 `air_route`（不变，这是正确的）
2. 字段名增加兼容：`NAME` 和 `route_name` 都尝试
3. `query_air_route()` 中 `route_name` 的 where 条件同时尝试 `route_name =` 和 `NAME =`

### 修改 4：修复 `_build_waypoints()` 中的 polygon 兜底逻辑

**文件**：`utm_simulator/tools/create_data_scenes.py` L917-968

当前 `_build_waypoints()` 先用 `query_air_route()` 查 polygon 字段。如果 `air_route_segment` 查询修复后能正常工作，应优先使用 segment 数据（精度更高），polygon 仅作为兜底。

### 修改 5（可选）：确保 dmPython 在 Docker 中可用

**文件**：`docker/Dockerfile` 或 `docker/requirements.txt`

如果 Docker 中仍需使用 DB 查询，需安装 `dmPython`。但考虑到 dmPython 是 C 扩展，安装困难，可在 `query_air_route()` 中增加 HTTP API 回退（通过调用 ATC 系统的航线查询 API）。

## 实施顺序

1. **修改 1** — `import_from_mock()` 跳过逻辑（独立，无依赖）
2. **修改 2+3+4** — 更正表名和字段名（核心修复）
3. **修改 5** — Docker dmPython 可用性（可选，根据实际需求）

## 验证

1. 运行 `import_from_mock()`，确认等大文件被跳过
2. 运行 `python create_data_scenes.py deviate --route-name "铁门关至吐鲁番"`，确认能正确查询航线数据
3. 运行 `python create_data_scenes.py collision --route-names "跨顺义三河段,三河区航路"`，确认碰撞预警正常
4. 运行 `python create_data_scenes.py batch`，确认批量场景不受影响
5. 检查 Docker 日志，确认不再出现 "无法获取航线" 错误
