# 数据管理与 JSON 文件管理优化方案

## Context

当前系统的 `sim_json_files` 表将完整 JSON 内容存入 `content TEXT` 列，大文件会导致数据库崩溃。Web UI 使用固定高度限制可用性。JSON 文件缺少分类元数据（告警类型、模拟器ID、关联航线）。需要全面优化存储方式、页面布局、预览性能和功能分类。

## 修改范围

### 后端（6个文件）

| 文件 | 操作 | 说明 |
|------|------|------|
| `database/db_manager.py` | 修改 | `sim_json_files` 表 DDL：`content` → `file_path`，新增 `alarm_type`/`simulator_id`/`linked_route`/`source` 列 |
| `database/mysql_db_manager.py` | 修改 | MySQL 对应 `init_tables()` 的 DDL 同步 |
| `database/json_data_manager.py` | 重写 | 核心：路径存储、告警类型检测、模拟器ID提取、航线关联、分页预览 |
| `utm_simulator/web_server.py` | 修改 | API 更新：新增 `/preview` 端点，列表/下载/保存改用 `file_path` 读取 |
| `common/config.py` | 修改 | 新增 `DATA_DIR` 统一路径常量，消除各文件重复计算 `data/mock/` 路径 |
| `.gitignore` | 修改 | 添加 `data/mock/` 排除运行时生成的 JSON 文件 |

### 前端（3个文件）

| 文件 | 操作 | 说明 |
|------|------|------|
| `web/pages/data.html` | 重写 | 全屏布局、新列顺序、告警类型过滤器、"加载更多"按钮 |
| `web/static/js/data.js` | 重写 | 新列渲染、告警类型徽章、分页预览、航线校验展示 |
| `web/static/css/style.css` | 修改 | 全屏数据管理页样式、告警徽章、来源标签样式 |

## 实施方案

### Phase 1: 数据库 Schema 迁移

**`database/db_manager.py` — 修改 `sim_json_files` DDL：**

```sql
-- 旧表（v1）
sim_json_files: id, name, category, content(TEXT), size_bytes, description, tags, created_by, created_at, updated_at

-- 新表（v2）
sim_json_files: id, name, category, alarm_type, file_path, simulator_id, linked_route, size_bytes, source, description, tags, created_at, updated_at
```

关键变更：
- **删除 `content` 列**，替换为 `file_path VARCHAR(1024)` — 存储本地文件路径
- **删除 `created_by` 列**，替换为 `source VARCHAR(32)` — 值：`manual`/`import`/`upload`/`generated`
- **新增 `alarm_type`** — 告警类型（碰撞预警/偏航/最低安全高度/正常遥测/飞行计划）
- **新增 `simulator_id`** — 从 JSON 提取的 `uniqueProductIdentificationCode`
- **新增 `linked_route`** — 关联的航线名称

迁移策略：添加 `PRAGMA user_version = 2`，首次访问时自动迁移。MySQL 通过 `ALTER TABLE` 处理。迁移时保留旧 `content` 列作为过渡。

**`database/mysql_db_manager.py` — 同步更新 `init_tables()` 中的 `_TABLE_DDL`。**

### Phase 2: 后端逻辑重写

**`database/json_data_manager.py` — 核心改动：**

1. **新增工具函数：**
   - `_detect_alarm_type(fname, content_sample)` → 从文件名检测告警类型（碰撞预警/偏航/最低安全高度），回退到内容格式检测
   - `_extract_simulator_id(content)` → 从 JSON 首元素提取 `uniqueProductIdentificationCode`，redis_route 格式提取 `key` 值
   - `_detect_linked_route(fname, content_sample)` → 从文件名模式 `{route_name}_碰撞预警_{uid}.json` 等提取航线名，回退到 `flightTaskName`
   - `_get_file_storage_dir()` → 返回统一的数据存储目录 `data/mock/`

2. **重写 `save_file()`：**
   - 接收 `content` 参数时，写入磁盘 `data/mock/{name}`，设置 `file_path`
   - 自动检测 `alarm_type`/`simulator_id`/`linked_route`（未提供时）
   - 现有去重和更新逻辑不变

3. **重写 `import_from_mock()`：**
   - 扫描 `data/mock/*.json`，读取采样（首 64KB）进行元数据检测
   - 记录 `file_path` 指向已有文件（不再复制内容到数据库）

4. **重写 `export_to_mock()`：**
   - 检查 `file_path` 是否存在，如果在 mock/ 外则 `shutil.copy2` 到 mock/
   - 已存在则直接返回成功

5. **新增 `preview_file(file_id, offset, limit)`：**
   - 按行分页读取磁盘文件
   - 返回 `{lines, total_lines, offset, limit, has_more}`

6. **新增 `validate_route_correlation(linked_route)`：**
   - 调用 `create_data_scenes.query_air_route_single()` 校验航线在数据库中存在
   - 返回 `{valid: bool, message: str}`

7. **更新 `list_files()`：**
   - 新增 `alarm_type` 过滤参数
   - 返回结果不包含 `content` 字段，包含新元数据字段
   - 根据 `file_path` 读取首 64KB 用于格式检测

8. **更新 `download_file()`：**
   - 返回 `file_path` 指向的文件内容（不再从数据库读）

### Phase 3: Web API 更新

**`utm_simulator/web_server.py` — API 端点调整：**

| 路由 | 变更 |
|------|------|
| `GET /api/data/db/files` | 返回新字段（alarm_type/simulator_id/linked_route/source），不返回 content/file_path；新增 `alarm_type` 查询参数 |
| `GET /api/data/db/files/<id>` | 默认返回元数据（不含 content）；支持 `?include_content=true` 加载首 100KB |
| `GET /api/data/db/files/<id>/preview` | **新增**：分页预览，参数 `offset`/`limit`，返回 `{lines, total_lines, has_more}` |
| `GET /api/data/db/files/<id>/download` | 改用 `flask.send_file()` 从磁盘流式传输 |
| `POST /api/data/db/files` | 接受新可选字段，content 写入磁盘 |
| `GET /api/data/db/files/<id>/validate-route` | **新增**：校验关联航线是否在数据库中存在 |

调度器回调（`scheduler.py`）：更新为从 `file_path` 读取文件而非 `content`。

### Phase 4: 前端重设计

**`web/pages/data.html` — 布局与列顺序：**

1. **全屏布局**：移除 `max-height:380px`/`max-height:350px`，改用 `flex:1; overflow-y:auto; min-height:0`
2. **新工具栏**：添加告警类型过滤下拉框（与分类过滤器并列）
3. **表头新顺序**：`ID | 告警类型 | 操作 | 模拟器ID | 关联航线 | 文件名 | 大小 | 来源 | 更新时间`
4. **预览区**：添加"加载更多"按钮（`#btn-preview-load-more`）

**`web/static/js/data.js` — 渲染逻辑：**

1. **列渲染**：按新顺序渲染，告警类型使用彩色徽章，模拟器ID 使用等宽字体
2. **`getAlarmTypeBadge(type)`**：颜色映射 — 碰撞预警=红、偏航=橙、最低安全高度=深橙、正常遥测=绿、飞行计划=蓝
3. **分页预览**：`previewFile()` 调用 `/preview` API，首 500 行；`loadMorePreview()` 追加后续行
4. **航线校验**：对有 `linked_route` 的行，调用 `/validate-route` API 显示校验图标（✓/✗/?）
5. **编辑弹窗**：大文件（>1MB）显示警告，仅加载首 5000 行
6. **告警类型过滤**：`#data-alarm-type` 下拉框变更时重新加载列表

**`web/static/css/style.css` — 新增样式：**
- `.page-data` 全屏弹性布局
- `.alarm-badge` 告警类型徽章
- `.source-label` 来源标签（manual/import/upload/generated 各不同颜色）

### Phase 5: 路径统一

**`common/config.py` — 新增：**
```python
from pathlib import Path
_PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = str(_PROJECT_ROOT / "data")
MOCK_DIR = str(_PROJECT_ROOT / "data" / "mock")
TEMPLATES_DIR = str(_PROJECT_ROOT / "data" / "templates")
SCHEMAS_DIR = str(_PROJECT_ROOT / "data" / "schemas")
```

后续所有文件统一从 `common.config` 导入路径常量，消除 10+ 处重复的 `os.path.join(dirname, "..", "data", "mock")`。

**`.gitignore` — 添加：**
```
data/mock/
!data/mock/.gitkeep
```

## 验证步骤

1. **Schema 验证**：查询 `PRAGMA table_info(sim_json_files)` 确认新列存在
2. **导入验证**：点击"导入 mock/" → 检查列表显示 alarm_type/simulator_id/linked_route 正确填充
3. **上传验证**：上传 JSON 文件 → 确认写入 `data/mock/` 磁盘，数据库仅存路径
4. **预览验证**：点击大文件（>1MB）→ 预览逐页加载，"加载更多"正常追加
5. **航线校验**：有 `linked_route` 的行显示校验状态图标
6. **全屏布局**：页面填满视口，表格和预览区无固定高度截断
7. **列顺序**：确认表头为 ID → 告警类型 → 操作 → 模拟器ID → 关联航线 → 文件名 → 大小 → 来源 → 更新时间
