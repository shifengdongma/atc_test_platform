# 修复 Docker 部署中 "文件在磁盘中不存在" 问题

## Context

### 问题现象
在 Docker 容器部署环境中，点击"数据管理"页面查看部分 JSON 文件时，提示**"文件在磁盘中不存在"**。但同样的文件在本地 Windows 环境 (`D:\liyang\code\atc_test_platfrom\data`) 可以正常访问。

### 根因分析

**核心原因：MySQL 数据库中存储的是文件保存时的绝对路径，而 Windows 和 Linux Docker 环境的路径格式完全不同。**

#### 路径计算机制 (`common/config.py:354-357`)
```python
_PROJECT_ROOT = _Path(__file__).parent.parent.resolve()  # 动态计算
MOCK_DIR = str(_PROJECT_ROOT / "data" / "mock")
```
- Windows 本地：`MOCK_DIR` = `D:\liyang\code\atc_test_platfrom\data\mock`
- Linux Docker：`MOCK_DIR` = `/app/data/mock`

#### 文件路径存储 (`json_data_manager.py:326-329`)
```python
fpath = os.path.join(storage_dir, name)  # 拼接出绝对路径
data["file_path"] = fpath                 # 存入数据库
```

#### 文件存在性检查 (`json_data_manager.py:506, 570`)
```python
fpath = record.get("file_path", "")
if not fpath or not os.path.exists(fpath):  # 直接用绝对路径检查
    return {"error": "文件不存在于磁盘"}
```

#### 跨环境共享 MySQL 导致的路径不兼容

| 文件创建环境 | DB 中 `file_path` 值 | Docker 中能否找到 | Windows 本地能否找到 |
|---|---|---|---|
| Windows 本地 | `D:\liyang\code\atc_test_platfrom\data\mock\xxx.json` | ❌ 路径不存在 | ✅ |
| Docker 容器 | `/app/data/mock/xxx.json` | ✅ | ❌ 路径不存在 |

**当同一 MySQL 数据库被 Windows 本地和 Linux Docker 两个环境共享时，各自创建的文件在对方环境中都找不到。**

#### Docker 数据卷映射 (`docker-compose.yml:56`)
```yaml
- /opt/atc_test_platfrom/data:/app/data
```
容器内 `/app/data/mock/` ↔ 宿主机 `/opt/atc_test_platfrom/data/mock/`。Docker 内创建的文件路径 `/app/data/mock/xxx.json` 在容器内是可访问的，但路径存储在 DB 中后，Windows 端无法识别。

### 修复方案

**方案：DB 中仅存文件名，运行时动态拼接 `MOCK_DIR` 路径**

将 `sim_json_files` 表中 `file_path` 的语义从"绝对路径"改为"文件名"，所有读写操作通过 `MOCK_DIR + filename` 动态构建路径。这样无论文件在哪个环境创建，在当前运行时都能通过本环境的 `MOCK_DIR` 正确找到文件。

### 需要修改的文件

#### 1. `database/json_data_manager.py` — 核心修改

- **`save_file()` (line 312-364)**：
  - `data["file_path"]` 从存储绝对路径 `fpath` 改为仅存 `name`（文件名）
  - 同样处理 `_get_storage_dir()` 拼接逻辑

- **`import_from_mock()` (line 391-442)**：
  - 导入时 `file_path` 仅存文件名

- **新增辅助函数 `_resolve_path(record)`**：
  - 从 record 中提取 `file_path`（可能是绝对路径或文件名）
  - 如果是绝对路径且文件存在 → 直接返回（兼容旧数据）
  - 如果是文件名或绝对路径不存在 → 用 `MOCK_DIR + basename` 重建路径
  - 返回实际可用的文件路径

- **`preview_file()` (line 495-539)**：用 `_resolve_path()` 替代 `record.get("file_path")`
- **`read_file_content_partial()` (line 555-584)**：同上
- **`delete_file()` (line 367-377)**：同上
- **`export_to_mock()` (line 445-464)**：同上
- **`get_file_info()` 等所有读取 `file_path` 的地方**：同上

#### 2. `database/mysql_db_manager.py` — 数据库迁移

- 新增迁移逻辑：将表中旧的绝对路径 `file_path` 更新为仅文件名
  ```sql
  -- 对每条记录，提取 file_path 的文件名部分
  UPDATE sim_json_files SET file_path = SUBSTRING_INDEX(file_path, '/', -1)
  WHERE file_path LIKE '/app/%' OR file_path LIKE '_:\\%';
  ```
- 或者在 Python 层做一次性迁移：遍历所有记录，用 `os.path.basename()` 提取文件名后更新

#### 3. `web_server.py` — API 层适配

- `api_db_download_file()` (line 1951-1967)：用 `_resolve_path()` 获取真实路径
- `api_db_list_files()` (line 1812-1840)：列表时不影响（已移除 `file_path` 字段）
- `api_db_get_file()` (line 1844-1864)：获取文件详情时的路径处理

#### 4. `common/config.py` — 可选：增强路径常量

- 确保 `MOCK_DIR` 在 Docker 和本地都能正确创建（已有 `_ensure_mock_dir()` 逻辑）

### 向后兼容策略

由于 `file_path` 字段可能已经存储了绝对路径（旧数据），需要兼容处理：

```python
def _resolve_path(record: dict) -> str:
    """兼容新旧 file_path 格式，返回实际文件路径。"""
    file_path = record.get("file_path", "")
    name = record.get("name", "")
    
    if not file_path:
        # 无路径，用 name 在 MOCK_DIR 下查找
        return os.path.join(MOCK_DIR, name) if name else ""
    
    # 如果绝对路径存在 → 旧格式，直接返回（兼容）
    if os.path.exists(file_path):
        return file_path
    
    # 绝对路径不存在 → 尝试在 MOCK_DIR 下用文件名查找
    basename = os.path.basename(file_path) or name
    resolved = os.path.join(MOCK_DIR, basename)
    if os.path.exists(resolved):
        return resolved
    
    # 都找不到，返回 MOCK_DIR 下的预期路径
    return resolved
```

### 迁移步骤

1. **代码部署前**：在 Docker 容器中执行一次性 SQL 迁移，将 `file_path` 从绝对路径更新为文件名
2. **部署新代码**：包含 `_resolve_path()` 兼容逻辑的新版 `json_data_manager.py`
3. **验证**：新旧文件都能在数据管理页面正常预览和下载

### 验证方式

1. 在 Docker 容器中访问 `/data` 页面，确认所有文件列表正常加载
2. 点击任意文件预览，确认不再出现"文件在磁盘中不存在"
3. 在 Docker 中新建文件 → 确认可正常查看
4. 在本地 Windows 新建文件 → Docker 中也能正常查看（如果共享同一 MySQL）
5. 下载、导出功能正常
