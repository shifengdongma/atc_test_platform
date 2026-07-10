# 项目文件架构优化方案

## 背景（Context）

当前项目 `atc_test_platfrom` 几乎所有新增功能都堆放在 `utm_simulator/` 目录下，而该目录原始定位是"UTM 无人机仿真核心引擎"（参考 `docs/初始系统架构文档.md`）。经过多轮迭代，`utm_simulator/` 已从 ~20 个文件膨胀到 ~45 个根级文件 + 多个子目录，混合了 Web 前端、数据管理、日志、调度等非仿真核心功能。

### 目标
1. **保持 `utm_simulator/` 接近原始架构**：仅保留仿真核心 + 关键 Python 服务模块
2. **Web 前端独立**：将 `web/` (HTML/CSS/JS) 提升为顶层目录，作为独立前端模块
3. **数据文件独立**：创建顶层 `data/` 目录，存放模拟 JSON、上传文件、模板等
4. **零功能影响**：所有路径引用、导入关系必须完整修正，不能破坏现有功能

---

## 目标目录架构

```
atc_test_platfrom/
├── utm_simulator/                 # 仿真核心 + Python 服务模块（保持现状）
│   ├── main.py                    # [原] 动态仿真入口
│   ├── simulation_core.py         # [原] 仿真引擎
│   ├── redis_client.py            # [原] Redis 客户端
│   ├── kafka_proc.py              # [原] Kafka 客户端
│   ├── pylib/                     # [原] C++ UTM 封装
│   ├── tools/                     # [原] 工具脚本（20+ .py）
│   ├── _source/                   # [原] 规范/源数据
│   ├── schemas/                   # [新] JSON Schema 定义
│   ├── tests/                     # [新] 单元测试
│   ├── packages/                  # [原] wheel 包
│   ├── web_server.py              # [新] Flask Web 服务（不动）
│   ├── sim_manager.py             # [新] 统一编排层（不动）
│   ├── situation_monitor.py       # [新] 态势监控（不动）
│   ├── log_streamer.py            # [新] 日志流（不动）
│   ├── json_data_manager.py       # [新] JSON 数据管理（不动）
│   ├── web_data_gen_bridge.py     # [新] Web API 桥接（不动）
│   ├── db_manager.py              # [新] SQLite 管理（不动）
│   ├── ai_data_gen.py             # [新] AI 数据生成（不动）
│   ├── scheduler.py               # [新] 定时任务（不动）
│   ├── config.py / config.json    # 配置
│   ├── env.py / env.md            # 环境配置
│   ├── data.db                    # SQLite 数据库（不动）
│   ├── deploy.sh / deploy_repeat.sh
│   ├── requirements.txt
│   ├── index.html                 # → 移动到 web/（根级重定向页）
│   ├── mock.html                  # → 移动到 web/
│   ├── multi.html                 # → 移动到 web/
│   └── ...（其余 Python 模块不变）
│
├── web/                           # [新] Web 前端（从 utm_simulator/web/ 移出）
│   ├── index.html                 # SPA 主入口
│   ├── pages/
│   │   ├── config.html
│   │   ├── run.html
│   │   ├── generate.html
│   │   ├── data.html
│   │   ├── env.html
│   │   └── logs.html
│   └── static/
│       ├── css/style.css
│       ├── js/
│       │   ├── app.js
│       │   ├── charts.js
│       │   ├── common.js
│       │   ├── config.js
│       │   ├── data.js
│       │   ├── env.js
│       │   ├── generate.js
│       │   ├── logs.js
│       │   ├── map.js
│       │   └── run.js
│       └── lib/leaflet/
│
├── data/                          # [新] 数据文件目录
│   ├── mock/                      # 模拟生成的 JSON 数据（从 utm_simulator/mock/ 移入）
│   ├── templates/                 # 飞行任务模板（从 utm_simulator/flight_task_templates/ 移入）
│   └── uploads/                   # 用户上传的 JSON 数据（新增子目录）
│
├── atc_api_autotest/              # [不变] API 自动化测试
├── atc_ha_test/                   # [不变] 高可用测试
├── docker/                        # [不变] Docker 部署配置
├── docs/                          # [不变] 文档
│
├── start_web.ps1                  # [不变] Windows 启动脚本
├── README.md                      # [不变]
├── CLAUDE.md                      # [不变]
└── ...（其余顶层目录不变）
```

---

## 实施步骤

### 步骤 1：创建顶层目录

- 创建 `web/` 顶层目录（含 `pages/` 和 `static/` 子目录）
- 创建 `data/` 顶层目录（含 `mock/`、`templates/`、`uploads/` 子目录）

### 步骤 2：移动 `web/` 前端文件（utm_simulator/web/ → web/）

- `utm_simulator/web/index.html` → `web/index.html`
- `utm_simulator/web/pages/*.html` → `web/pages/*.html`（6 个文件）
- `utm_simulator/web/static/css/style.css` → `web/static/css/style.css`
- `utm_simulator/web/static/js/*.js` → `web/static/js/*.js`（10 个文件）
- `utm_simulator/web/static/lib/leaflet/*` → `web/static/lib/leaflet/*`（2 个文件）
- 移动 `utm_simulator/index.html` → `web/index_root.html`（根级重定向页）
- 移动 `utm_simulator/mock.html` → `web/mock.html`
- 移动 `utm_simulator/multi.html` → `web/multi.html`
- 删除空的 `utm_simulator/web/` 目录

### 步骤 3：移动数据文件（utm_simulator/mock/ → data/mock/）

- `utm_simulator/mock/*.json` → `data/mock/*.json`
- `utm_simulator/mock/.last_id_offset` → `data/mock/.last_id_offset`
- 删除空的 `utm_simulator/mock/` 目录

### 步骤 4：移动模板文件（utm_simulator/flight_task_templates/ → data/templates/）

- `utm_simulator/flight_task_templates/*.json` → `data/templates/*.json`（3 个文件）
- 删除空的 `utm_simulator/flight_task_templates/` 目录

### 步骤 5：修正 `web_server.py` 路径引用

这是**最关键的步骤**，涉及多处路径更新：

| 行 | 当前代码 | 更新为 |
|----|---------|--------|
| 65 | `static_folder="web/static"` | `static_folder="../web/static"` |
| 503-533 | `send_from_directory("web/pages", ...)` (6处) | `send_from_directory("../web/pages", ...)` |
| 312-314 | `mock_dir = os.path.join(_root, "mock")` | `mock_dir = os.path.join(_root, "..", "data", "mock")` |
| 741-744 | `mock_dir = os.path.join(_root, "mock")` | `mock_dir = os.path.join(_root, "..", "data", "mock")` |
| 782-787 | `mock_dir = os.path.join(_root, "mock")` | `mock_dir = os.path.join(_root, "..", "data", "mock")` |
| 921-925 | `mock_dir = os.path.join(_root, "mock")` | `mock_dir = os.path.join(_root, "..", "data", "mock")` |
| 956-958 | `mock_dir = os.path.join(_root, "mock")` | `mock_dir = os.path.join(_root, "..", "data", "mock")` |
| 985-987 | `mock_dir = os.path.join(_root, "mock")` | `mock_dir = os.path.join(_root, "..", "data", "mock")` |
| 1370 | 导入路径引用 | 更新为 `../data/mock` |
| 1482-1484 | `mock_dir = os.path.join(os.path.dirname(...), "mock")` | 更新为 `../data/mock` |

### 步骤 6：修正 `json_data_manager.py` 路径引用

| 行 | 当前代码 | 更新为 |
|----|---------|--------|
| 20 | `_MOCK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock")` | `_MOCK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mock")` |

### 步骤 7：修正 `web_data_gen_bridge.py` 路径引用

| 行 | 当前代码 | 更新为 |
|----|---------|--------|
| 28-32 | `mock_dir = os.path.join(_SCRIPT_DIR, "mock")` | `mock_dir = os.path.join(_SCRIPT_DIR, "..", "data", "mock")` |
| 83 | `output = "mock/kafka_data_parallel.json"` | `output = "../data/mock/kafka_data_parallel.json"` |
| 274, 289 | `"mock/kafka_data_*.json"` | `"../data/mock/kafka_data_*.json"` |

### 步骤 8：修正 `sim_manager.py` 路径引用

| 行 | 当前代码 | 更新为 |
|----|---------|--------|
| 350-352 | `mock_dir = os.path.join(_root, "mock")` | `mock_dir = os.path.join(_root, "..", "data", "mock")` |

### 步骤 9：修正 `log_streamer.py` MySQL 导入路径

| 行 | 当前代码 | 更新为 |
|----|---------|--------|
| 22-25 | `os.path.join(os.path.dirname(...), "..", "atc_api_autotest", "api_tools")` | 保持不变（此路径是相对于 `utm_simulator/` 的，`../` 指向项目根目录，不受本次移动影响） |

### 步骤 10：修正 `tools/` 目录下脚本路径

需修改以下文件中硬编码的 `mock/` 路径，统一改为 `../data/mock/`：

| 文件 | 当前路径变量 |
|------|-------------|
| `tools/create_data.py:17-19` | `MOCK_DIR = os.path.join(_ROOT, "mock")` |
| `tools/run_kafka.py:22-25` | `MOCK_DIR = os.path.join(_root, "mock")` |
| `tools/run_kafka_alive.py:22-24` | `MOCK_DIR = os.path.join(_root, "mock")` |
| `tools/nfzs.py:21` | `MOCK_DIR = os.path.join(_root, "mock")` |
| `tools/check_hash_id_collision.py:40` | `MOCK_DIR = os.path.join(os.path.dirname(__file__), '..', 'mock')` |
| `tools/create_data_scenes.py` | 多处 `mock/` 默认值路径 |
| `tools/lines_to_redis_route.py` | 注释/文档中的 `mock/` 路径 |
| `tools/transform.py` | 注释/文档中的 `mock/` 路径 |

### 步骤 11：修正 `start_web.ps1`

`start_web.ps1:177` 的 `Push-Location "$ScriptDir\utm_simulator"` 保持不变（web_server.py 仍在 `utm_simulator/` 内运行）。

### 步骤 12：更新 Docker 配置

**Dockerfile 修改：**
- 增加 `COPY web/ /app/web/`
- 增加 `COPY data/ /app/data/`
- 保持 `WORKDIR /app/utm_simulator`

**docker-compose.yml 修改：**
- 增加 `data/` 目录的卷挂载（持久化 JSON 数据）

### 步骤 13：更新 `.dockerignore`

- 确认 `web/` 和 `data/` 不在排除列表中（它们需要被 COPY 进镜像）

### 步骤 14：更新文档

- 更新 `docs/系统架构文档.md` "三、目录与文件架构" 章节
- 更新 `docs/utm-simulator-optimization-work-log.md`
- 更新 `docs/工作总结.md`

---

## 风险点与注意事项

1. **`web_server.py` 的 `static_folder` 路径**：Flask 的 `static_folder` 参数支持相对路径，`../web/static` 在 `utm_simulator/` 为工作目录时能正确解析到顶层 `web/static/`。

2. **`send_from_directory` 路径**：同样使用 `../web/pages` 相对路径。

3. **IDE/编辑器配置**：`.cursorrules` 等文件不受影响，仍保持在 `utm_simulator/` 下。

4. **Git 历史保留**：使用 `git mv` 移动文件以保留历史追踪。

5. **tools/ 脚本向后兼容**：`tools/` 下的脚本可能在服务器上独立运行，需确保 `../data/mock/` 路径在脚本工作目录为 `utm_simulator/tools/` 时也能正确解析（`_ROOT` 通常指向 `utm_simulator/`）。

6. **不影响原有仿真核心功能**：`simulation_core.py`、`redis_client.py`、`kafka_proc.py`、`pylib/`、`main.py` 零改动。

---

## 验证方案

1. **路径验证**：
   - 在 `utm_simulator/` 目录下运行 `python -c "import os; print(os.path.exists('../web/static')); print(os.path.exists('../data/mock'))"` 确认路径可达
   
2. **Web 服务启动测试**：
   - 运行 `start_web.ps1` 或 `cd utm_simulator && python web_server.py`
   - 访问 `http://localhost:5000` 验证所有页面正常加载
   - 检查浏览器控制台无 404 错误（CSS/JS 资源加载）
   
3. **数据生成功能测试**：
   - 通过 Web UI 触发数据生成，确认 JSON 文件写入 `data/mock/`
   - 上传 JSON 文件，确认保存到 `data/uploads/`
   
4. **Docker 构建测试**：
   - `docker build -f docker/Dockerfile -t utm-simulator:test .` 确认构建成功
   - 检查镜像内 `/app/web/` 和 `/app/data/` 目录存在
   
5. **导入测试**：
   - `cd utm_simulator && python -c "from web_server import app; print('OK')"` 确认无导入错误
   - 运行 `python -m pytest tests/` 确认测试通过

---

## 改动文件统计

| 操作 | 数量 | 涉及内容 |
|------|------|---------|
| 新建目录 | 3 | `web/`, `data/mock/`, `data/templates/`, `data/uploads/` |
| 移动文件 | ~25 | web/ 前端全部文件 + mock/ JSON + templates |
| 修改 Python | ~10 | web_server.py, json_data_manager.py, web_data_gen_bridge.py, sim_manager.py, tools/*.py |
| 修改配置 | 3 | Dockerfile, docker-compose.yml, .dockerignore |
| 修改文档 | 3 | 系统架构文档, work-log, 工作总结 |
