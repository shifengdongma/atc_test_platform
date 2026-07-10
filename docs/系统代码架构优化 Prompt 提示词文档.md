# 系统代码架构优化 Prompt 提示词文档

## 一、文档用途

本文档用于指导 AI 编程助手对现有项目进行系统代码架构与目录结构优化。适用于 Claude Code、Cursor、通义灵码、ChatGPT、Copilot Workspace 等具备代码分析和重构能力的 AI 工具。

本次优化目标不是重写系统，也不是替换技术栈，而是在不影响系统正常运行功能的前提下，对现有项目进行渐进式目录整理、代码分层、兼容入口保留、历史代码归档和文档同步更新，使项目结构更符合真实标准项目的前后端架构规范，便于后续维护、交接、扩展和部署。

------

# Prompt 1：系统架构现状分析与重构方案制定

你是一位资深计算机领域系统架构师、Python 后端工程师、Web 全栈架构师和 DevOps 工程师。请基于当前项目的实际文件结构，对项目进行系统性架构分析，并制定一份“不破坏现有功能”的目录与代码架构优化方案。

## 项目背景

当前项目根目录为：

```text
atc_test_platfrom/
```

项目核心系统为：

```text
utm_simulator/
```

该目录是无人机模拟器与 Web 控制台的核心运行目录，包含以下主要内容：

1. 仿真引擎层：
   - simulation_core.py
   - sim_manager.py
   - kafka_proc.py
   - kafka_proc_1.0.py
   - redis_client.py
2. Web 服务层：
   - web_server.py
   - situation_monitor.py
   - log_streamer.py
3. 配置与数据契约层：
   - config.py
   - config.json
   - schemas.py
   - validators.py
   - exceptions.py
   - env.py
   - env.py.example
   - env.md
   - log_setup.py
4. 数据管理层：
   - db_manager.py
   - json_data_manager.py
   - env_manager.py
   - scheduler.py
5. 入口与辅助文件：
   - main.py
   - cli.py
   - simulation_core0609.py
   - test_e2e_sim.py
   - uav_identifiers_extended.py
6. API 桥接与 AI 集成：
   - sim_api_bridge.py
   - ai_data_gen.py
   - ai_integration.py
   - web_data_gen_bridge.py
7. tools 脚本工具集：
   - run_kafka.py
   - run_kafka_alive.py
   - run_kafka_scene.py
   - run_plan.py
   - create_data.py
   - create_data_scenes.py
   - create_data_scene.py
   - nfzs.py
   - transform.py
   - lines_to_redis_route.py
   - trajectory_accuracy.py
   - trajectory_accuracy_json.py
   - kafka_read_latest.py
   - redis_read_lastest.py
   - kafka_uav_counter.py
   - analyze_trajectory.py
   - check_hash_id_collision.py
   - check_uids_in_db.py
   - test_deviation_fix.py
   - test_deviation_fix2.py
8. 前端资源：
   - web/index.html
   - web/pages/config.html
   - web/pages/run.html
   - web/pages/generate.html
   - web/pages/data.html
   - web/pages/env.html
   - web/pages/logs.html
   - web/static/js/common.js
   - web/static/js/config.js
   - web/static/js/run.js
   - web/static/js/map.js
   - web/static/js/charts.js
   - web/static/js/generate.js
   - web/static/js/data.js
   - web/static/js/env.js
   - web/static/js/logs.js
   - web/static/js/app.js
   - web/static/css/style.css
   - web/static/lib/leaflet/
9. C++ UTM 核心库 Python 封装：
   - pylib/**init**.py
   - pylib/structs.py
   - pylib/engine.py
10. 参考数据、模板、Schema、测试、Mock 和部署文件：

- _source/
- flight_task_templates/
- schemas/
- tests/
- mock/
- packages/
- deploy.sh
- deploy_repeat.sh
- requirements.txt
- lines.json
- data.db
- 使用手册.md

根目录下还存在以下支撑目录：

```text
atc_api_autotest/
atc_ha_test/
test_data_create/
atc_test_cases/
atc_data_factory/
docker/
docs/
atc_api_info/
atc_auto_test/
atc_local_rag/
.agent/
.lingma/
.superpowers/
```

其中部分目录包含历史遗留代码、测试代码、HA 测试代码、性能测试代码、数据工厂脚本、Docker 部署文件、接口文档和工作日志。

## 总体目标

请在不影响系统正常运行的前提下，完成以下架构优化设计：

1. 将核心业务系统与测试、数据工厂、历史代码、部署文件、文档文件分离。
2. 将 `utm_simulator/` 从“脚本集合式目录”优化为标准的前后端项目结构。
3. 保留原有启动入口，避免破坏现有运行命令。
4. 将历史代码、旧版本、备份文件、废弃配置统一归档。
5. 将 Web 前端资源独立成 `frontend/`。
6. 将 Python 后端代码整理为 `backend/`。
7. 将 Kafka、Redis、ATC API、AI、C++ pylib 等外部依赖或集成逻辑统一放入 `integrations/` 或 `native/`。
8. 将配置、Schema、运行数据、参考数据和模板分开管理。
9. 将 API 自动化测试、HA 测试、性能测试、数据工厂脚本统一归入 `qa/` 或 `tests/` 类目录。
10. 更新 README、架构说明、启动说明、迁移说明和目录说明。

## 硬性约束

请严格遵守以下约束：

1. 不允许直接删除任何功能文件。
2. 不允许修改核心业务逻辑。
3. 不允许一次性大规模移动导致 import 全部失效。
4. 不允许破坏以下入口：
   - start_web.ps1
   - utm_simulator/main.py
   - utm_simulator/cli.py
   - utm_simulator/web_server.py
   - utm_simulator/tools/run_kafka_alive.py
   - utm_simulator/tools/run_plan.py
   - deploy.sh
   - deploy_repeat.sh
5. 对于需要移动的核心文件，必须先建立新目录，再保留旧路径兼容入口。
6. 对于旧文件、备份文件、历史代码，只允许移动到 archive，不允许删除。
7. 所有路径调整必须同步更新 import、启动脚本、README 和部署说明。
8. 每一步调整后都要给出验证命令。
9. 如果发现不确定的依赖关系，必须先分析，不要直接改动。
10. 如果某个文件可能被外部系统调用，必须保留兼容 shim。

## 请输出以下内容

请先不要修改代码，只输出完整重构方案：

1. 当前目录结构问题分析。
2. 推荐的新目录结构。
3. 文件迁移映射表。
4. 兼容入口保留方案。
5. 分阶段实施计划。
6. 每阶段风险点。
7. 每阶段回归验证命令。
8. 需要更新的文档清单。
9. 不建议立即改动的文件清单。
10. 最终验收标准。

## 推荐目标目录结构

请以如下结构作为目标方案，但允许根据实际项目情况微调：

```text
atc_test_platform/
│
├── README.md
├── pyproject.toml
├── requirements.txt
├── .gitignore
├── .env.example
├── start_web.ps1
│
├── apps/
│   └── utm_simulator/
│       ├── backend/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── api/
│       │   ├── core/
│       │   ├── integrations/
│       │   ├── persistence/
│       │   ├── schemas/
│       │   ├── config/
│       │   └── native/
│       │
│       ├── frontend/
│       │   ├── index.html
│       │   ├── pages/
│       │   └── static/
│       │
│       ├── data/
│       │   ├── fixtures/
│       │   ├── mock/
│       │   ├── reference/
│       │   ├── templates/
│       │   ├── schemas/
│       │   └── runtime/
│       │
│       ├── scripts/
│       ├── tools/
│       └── tests/
│
├── qa/
│   ├── api_autotest/
│   ├── ha_test/
│   ├── performance/
│   └── data_factory/
│
├── datasets/
│   ├── generated_scenes/
│   ├── trajectory_samples/
│   └── alarm_cases/
│
├── deploy/
│   ├── docker/
│   ├── shell/
│   └── windows/
│
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── deployment/
│   ├── user_manual/
│   ├── work_logs/
│   └── archive/
│
├── archive/
│   ├── old_versions/
│   ├── backups/
│   ├── deprecated_configs/
│   └── legacy_autotest/
│
└── .agent/
    └── rules.md
```

------

# Prompt 2：第一阶段目录整理，不移动核心运行代码

你是一位谨慎的系统重构工程师。现在请执行第一阶段优化：只整理外围目录，不移动核心运行代码，不修改核心业务逻辑。

## 阶段目标

本阶段只完成低风险目录整理，目标是：

1. 新建标准目录骨架。
2. 归档历史代码和备份文件。
3. 整理文档、Docker、测试数据、历史自动化项目。
4. 不移动 `utm_simulator/` 内的核心运行文件。
5. 不影响现有启动方式。

## 请执行以下任务

### 1. 新建目录

请在项目根目录下创建：

```text
apps/
qa/
datasets/
deploy/
archive/
docs/architecture/
docs/api/
docs/deployment/
docs/user_manual/
docs/work_logs/
docs/archive/
archive/old_versions/
archive/backups/
archive/deprecated_configs/
archive/legacy_autotest/
```

### 2. 低风险目录迁移建议

请将以下目录按建议进行整理。如果不确定是否存在，请先检查再操作：

```text
docker/                  -> deploy/docker/
atc_api_autotest/         -> qa/api_autotest/
atc_ha_test/              -> qa/ha_test/
atc_test_cases/           -> qa/performance/
atc_data_factory/         -> qa/data_factory/
test_data_create/         -> datasets/generated_scenes/
atc_auto_test/            -> archive/legacy_autotest/
```

### 3. 文档整理

请将 `docs/` 下内容按类型整理：

```text
系统架构文档.md                         -> docs/architecture/
核心代码原理.md                         -> docs/architecture/
模拟器环境配置.md                       -> docs/deployment/
utm-simulator-data-link.md              -> docs/architecture/
工作总结.md                             -> docs/work_logs/
utm-simulator-optimization-work-log.md   -> docs/work_logs/
070*/                                   -> docs/work_logs/
```

如果文件已经在目标位置，则不要重复移动。

### 4. 保留兼容说明

如果移动了目录，请在原位置保留一个 `README_MOVED.md`，说明：

```text
该目录已迁移至新位置。
迁移时间：当前日期
迁移原因：项目架构规范化整理
原目录：xxx
新目录：xxx
注意：如有历史脚本引用旧路径，请更新为新路径。
```

### 5. 修改 README

请更新根目录 README，增加：

1. 新目录结构说明。
2. 核心运行目录说明。
3. 测试目录说明。
4. 部署目录说明。
5. 历史归档目录说明。
6. 当前阶段未改动核心运行代码的说明。

### 6. 输出结果

完成后请输出：

1. 实际创建的目录列表。
2. 实际移动的目录列表。
3. 未移动的目录及原因。
4. 新增或修改的 README 文件。
5. 需要人工确认的问题。
6. 当前系统启动命令是否保持不变。

## 严格禁止

1. 禁止移动 `utm_simulator/simulation_core.py`。
2. 禁止移动 `utm_simulator/sim_manager.py`。
3. 禁止移动 `utm_simulator/web_server.py`。
4. 禁止移动 `utm_simulator/kafka_proc.py`。
5. 禁止移动 `utm_simulator/redis_client.py`。
6. 禁止修改业务逻辑。
7. 禁止删除文件。

------

# Prompt 3：第二阶段核心后端代码包化

你是一位资深 Python 项目架构师。现在请执行第二阶段优化：将 `utm_simulator/` 内的核心后端代码逐步包化为标准 Python 后端结构。

## 阶段目标

本阶段目标是把核心 Python 后端拆分为清晰的层级结构，但必须保留旧入口兼容。

目标后端结构如下：

```text
apps/utm_simulator/backend/
├── __init__.py
├── main.py
├── api/
├── core/
├── integrations/
├── persistence/
├── schemas/
├── config/
└── native/
```

## 文件迁移映射

请按以下映射进行迁移或复制。优先采用“复制到新结构 + 旧文件保留兼容入口”的方式，确保现有系统不被破坏。

### core 层

```text
utm_simulator/simulation_core.py       -> apps/utm_simulator/backend/core/simulation_core.py
utm_simulator/sim_manager.py           -> apps/utm_simulator/backend/core/sim_manager.py
utm_simulator/scheduler.py             -> apps/utm_simulator/backend/core/scheduler.py
utm_simulator/uav_identifiers_extended.py -> apps/utm_simulator/backend/core/uav_identifiers.py
```

### api 层

```text
utm_simulator/web_server.py            -> apps/utm_simulator/backend/main.py
utm_simulator/situation_monitor.py     -> apps/utm_simulator/backend/api/situation_monitor.py
utm_simulator/log_streamer.py          -> apps/utm_simulator/backend/api/log_streamer.py
```

如果 `web_server.py` 中包含 50+ API 和 Socket.IO 逻辑，请不要一次性重写。先复制到 `backend/main.py`，后续再逐步拆分 routes。

### integrations 层

```text
utm_simulator/kafka_proc.py            -> apps/utm_simulator/backend/integrations/kafka_client.py
utm_simulator/redis_client.py          -> apps/utm_simulator/backend/integrations/redis_client.py
utm_simulator/sim_api_bridge.py        -> apps/utm_simulator/backend/integrations/atc_api_bridge.py
utm_simulator/ai_data_gen.py           -> apps/utm_simulator/backend/integrations/ai/ai_data_gen.py
utm_simulator/ai_integration.py        -> apps/utm_simulator/backend/integrations/ai/ai_integration.py
utm_simulator/web_data_gen_bridge.py   -> apps/utm_simulator/backend/integrations/ai/web_data_gen_bridge.py
```

### persistence 层

```text
utm_simulator/db_manager.py            -> apps/utm_simulator/backend/persistence/db_manager.py
utm_simulator/json_data_manager.py     -> apps/utm_simulator/backend/persistence/json_data_manager.py
utm_simulator/env_manager.py           -> apps/utm_simulator/backend/persistence/env_manager.py
```

### schemas 层

```text
utm_simulator/schemas.py               -> apps/utm_simulator/backend/schemas/models.py
utm_simulator/validators.py            -> apps/utm_simulator/backend/schemas/validators.py
utm_simulator/exceptions.py            -> apps/utm_simulator/backend/schemas/exceptions.py
```

### config 层

```text
utm_simulator/config.py                -> apps/utm_simulator/backend/config/settings.py
utm_simulator/config.json              -> apps/utm_simulator/backend/config/default.json
utm_simulator/log_setup.py             -> apps/utm_simulator/backend/config/logging.py
utm_simulator/env.py.example           -> apps/utm_simulator/backend/config/env.py.example
utm_simulator/env.md                   -> docs/deployment/env.md
```

### native 层

```text
utm_simulator/pylib/                   -> apps/utm_simulator/backend/native/pylib/
```

## 兼容入口要求

迁移后，旧文件不要删除。请将旧文件改为兼容入口，示例：

```python
# utm_simulator/simulation_core.py
from apps.utm_simulator.backend.core.simulation_core import *
# utm_simulator/web_server.py
from apps.utm_simulator.backend.main import app, socketio

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8000)
# utm_simulator/main.py
from apps.utm_simulator.backend.core.sim_manager import main

if __name__ == "__main__":
    main()
```

如果实际模块中没有对应的 `main`、`app`、`socketio`，请根据真实代码调整兼容入口，不要凭空编造。

## import 更新要求

请检查并更新新目录中的 import：

1. 相对同层模块使用包内绝对导入。
2. 外部兼容入口使用从新包导入。
3. 不要在核心代码中反向 import 旧路径。
4. 不要让新代码依赖 `archive/`。
5. 如有循环导入，先报告问题，再提出拆分方案。

## 验证命令

完成后请运行或给出以下验证方式：

```bash
python -m compileall apps/utm_simulator/backend
python utm_simulator/main.py
python utm_simulator/cli.py
python utm_simulator/web_server.py
python utm_simulator/tools/run_kafka_alive.py
python utm_simulator/tools/run_plan.py
```

如当前环境无法连接 Redis、Kafka、MySQL 或外部 ATC API，请至少完成静态编译检查，并说明哪些运行验证因环境缺失无法完成。

## 输出结果

请输出：

1. 新增目录和文件。
2. 已迁移文件。
3. 已保留的兼容入口。
4. import 修改清单。
5. 编译检查结果。
6. 未能验证的功能及原因。
7. 下一阶段建议。

------

# Prompt 4：第三阶段前端资源标准化

你是一位 Web 前端架构师。请对当前原生 HTML/CSS/JS 前端目录进行结构优化，不改变页面功能，不引入新的前端框架。

## 当前前端目录

```text
utm_simulator/web/
├── index.html
├── pages/
│   ├── config.html
│   ├── run.html
│   ├── generate.html
│   ├── data.html
│   ├── env.html
│   └── logs.html
└── static/
    ├── js/
    │   ├── common.js
    │   ├── config.js
    │   ├── run.js
    │   ├── map.js
    │   ├── charts.js
    │   ├── generate.js
    │   ├── data.js
    │   ├── env.js
    │   ├── logs.js
    │   └── app.js
    ├── css/style.css
    └── lib/leaflet/
```

## 目标结构

```text
apps/utm_simulator/frontend/
├── index.html
├── pages/
│   ├── config.html
│   ├── run.html
│   ├── generate.html
│   ├── data.html
│   ├── env.html
│   └── logs.html
└── static/
    ├── js/
    │   ├── api/
    │   │   ├── client.js
    │   │   └── ws.js
    │   ├── pages/
    │   │   ├── config.js
    │   │   ├── run.js
    │   │   ├── generate.js
    │   │   ├── data.js
    │   │   ├── env.js
    │   │   └── logs.js
    │   ├── components/
    │   │   ├── map.js
    │   │   └── charts.js
    │   ├── utils/
    │   │   └── common.js
    │   └── app.js
    ├── css/
    │   └── style.css
    └── lib/
        └── leaflet/
```

## 执行要求

1. 保留 `utm_simulator/web/` 作为兼容目录。
2. 优先复制文件到新目录，不立即删除旧目录。
3. 检查 HTML 中的 CSS、JS、Leaflet 引用路径。
4. 如后端 Flask 当前通过 `web/` 提供静态文件，需要同步更新后端静态路径配置。
5. 如果不确定后端是否依赖旧路径，请保留旧路径。
6. 不要改页面样式和业务交互逻辑。
7. 不要引入 Vue、React、Vite、Webpack 等新构建工具。
8. 不要修改 WebSocket 协议和 API 路径。

## 兼容方案

如果 Flask 当前写死了：

```python
static_folder="web/static"
template_folder="web"
```

请改成优先使用新路径：

```python
frontend_dir = Path("apps/utm_simulator/frontend")
legacy_frontend_dir = Path("utm_simulator/web")
```

逻辑要求：

1. 如果新路径存在，使用新路径。
2. 如果新路径不存在，回退旧路径。
3. 不影响旧部署环境运行。

## 输出结果

请输出：

1. 前端文件迁移清单。
2. HTML 引用路径修改清单。
3. 后端静态路径兼容修改说明。
4. 页面功能未变更说明。
5. 验证方式：
   - 打开首页
   - 打开配置页
   - 打开运行页
   - 打开生成页
   - 打开数据页
   - 打开环境页
   - 打开日志页
   - 验证 WebSocket 连接
   - 验证地图 Leaflet 加载
   - 验证 Chart.js 图表加载

------

# Prompt 5：第四阶段数据、配置、Schema 规范化

你是一位后端配置管理和数据治理工程师。请对项目中的配置文件、运行数据、参考数据、模板数据和 Schema 文件进行目录规范化，不改变数据内容。

## 当前相关文件

```text
utm_simulator/config.py
utm_simulator/config.json
utm_simulator/env.py
utm_simulator/env.py.example
utm_simulator/env.md
utm_simulator/log_setup.py
utm_simulator/lines.json
utm_simulator/data.db
utm_simulator/mock/
utm_simulator/_source/
utm_simulator/flight_task_templates/
utm_simulator/schemas/
```

## 目标结构

```text
apps/utm_simulator/backend/config/
├── settings.py
├── default.json
├── logging.py
└── env.py.example

apps/utm_simulator/data/
├── reference/
│   ├── lines.json
│   └── _source/
├── templates/
│   └── flight_task_templates/
├── schemas/
│   ├── route_schema.json
│   ├── telemetry_schema.json
│   ├── airspace_schema.json
│   └── scenario_schema.json
├── mock/
└── runtime/
    └── data.db
```

## 执行要求

1. 配置文件只迁移路径，不改变配置含义。
2. 不要将真实凭证写入代码。
3. 如果 `env.py` 中存在真实 Redis、Kafka、MySQL、API 地址或密码，请不要提交到新目录，应改为 `.env.example` 或配置模板。
4. `data.db` 属于运行时文件，应移动到 `data/runtime/`，并加入 `.gitignore`。
5. mock 数据应放入 `data/mock/`。
6. 参考规范文档和 JSON 放入 `data/reference/`。
7. 飞行任务模板放入 `data/templates/`。
8. JSON Schema 文件放入 `data/schemas/`。
9. 所有读取路径必须改为通过统一配置或路径工具获取，不要散落硬编码路径。
10. 如果暂时不能修改所有路径，请保留旧路径 fallback。

## 建议新增路径工具

请新增：

```text
apps/utm_simulator/backend/config/paths.py
```

内容负责统一管理项目路径，例如：

```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = PROJECT_ROOT / "apps" / "utm_simulator"
BACKEND_ROOT = APP_ROOT / "backend"
FRONTEND_ROOT = APP_ROOT / "frontend"
DATA_ROOT = APP_ROOT / "data"

REFERENCE_DIR = DATA_ROOT / "reference"
TEMPLATES_DIR = DATA_ROOT / "templates"
SCHEMAS_DIR = DATA_ROOT / "schemas"
MOCK_DIR = DATA_ROOT / "mock"
RUNTIME_DIR = DATA_ROOT / "runtime"

LEGACY_UTM_DIR = PROJECT_ROOT / "utm_simulator"
```

要求支持旧路径 fallback，例如：

```python
def resolve_existing_path(*candidates):
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]
```

## .gitignore 更新要求

请增加：

```gitignore
.env
*.db
*.sqlite
*.sqlite3
*.log
data/runtime/
apps/utm_simulator/data/runtime/
archive/
*.bak_*
__pycache__/
.pytest_cache/
```

注意：如果 `archive/` 需要入库用于历史追踪，则不要忽略整个 archive，只忽略大型临时文件和敏感文件。

## 输出结果

请输出：

1. 配置文件迁移清单。
2. 数据文件迁移清单。
3. Schema 文件迁移清单。
4. 新增路径工具说明。
5. 修改了哪些硬编码路径。
6. 旧路径 fallback 说明。
7. `.gitignore` 修改说明。
8. 验证命令和验证结果。

------

# Prompt 6：第五阶段 tools、scripts、diagnostics 分类

你是一位 Python 工具链架构师。请对 `utm_simulator/tools/` 中的脚本进行分类整理，使运行脚本、数据生成工具、格式转换工具、诊断工具和分析工具边界清晰。

## 当前 tools 文件

```text
run_kafka.py
run_kafka_alive.py
run_kafka_scene.py
run_plan.py
create_data.py
create_data_scenes.py
create_data_scene.py
nfzs.py
transform.py
lines_to_redis_route.py
trajectory_accuracy.py
trajectory_accuracy_json.py
kafka_read_latest.py
redis_read_lastest.py
kafka_uav_counter.py
analyze_trajectory.py
check_hash_id_collision.py
check_uids_in_db.py
test_deviation_fix.py
test_deviation_fix2.py
```

## 目标结构

```text
apps/utm_simulator/scripts/
├── run_kafka.py
├── run_kafka_alive.py
├── run_kafka_scene.py
├── run_plan.py
└── diagnostics/
    ├── kafka_read_latest.py
    ├── redis_read_latest.py
    ├── kafka_uav_counter.py
    ├── check_hash_id_collision.py
    └── check_uids_in_db.py

apps/utm_simulator/tools/
├── data_generation/
│   ├── create_data.py
│   ├── create_data_scene.py
│   └── create_data_scenes.py
├── transform/
│   ├── transform.py
│   └── lines_to_redis_route.py
├── airspace/
│   └── nfzs.py
├── trajectory_analysis/
│   ├── trajectory_accuracy.py
│   ├── trajectory_accuracy_json.py
│   └── analyze_trajectory.py
└── experiments/
    ├── test_deviation_fix.py
    └── test_deviation_fix2.py
```

## 兼容要求

保留旧目录：

```text
utm_simulator/tools/
```

旧脚本改为兼容入口，示例：

```python
from apps.utm_simulator.scripts.run_kafka_alive import main

if __name__ == "__main__":
    main()
```

如果原脚本没有 `main()`，不要强行假设，请先分析脚本入口逻辑，再提取或封装。

## 执行要求

1. 运行脚本放入 `scripts/`。
2. 可复用工具放入 `tools/`。
3. 诊断脚本放入 `scripts/diagnostics/`。
4. 实验性测试脚本放入 `tools/experiments/`。
5. 保留旧路径兼容。
6. 修复 import 路径。
7. 更新 README 中的脚本使用方式。
8. 不要删除旧脚本。
9. 不要改变脚本行为。
10. 不要改变 Kafka、Redis、ATC API 的消息格式。

## 验证命令

请验证：

```bash
python utm_simulator/tools/run_kafka_alive.py --help
python utm_simulator/tools/run_plan.py --help
python apps/utm_simulator/scripts/run_kafka_alive.py --help
python apps/utm_simulator/scripts/run_plan.py --help
python -m compileall apps/utm_simulator/scripts
python -m compileall apps/utm_simulator/tools
```

如果脚本不支持 `--help`，请说明并改用静态编译验证。

------

# Prompt 7：第六阶段测试体系整理

你是一位测试架构师。请把项目中的单元测试、集成测试、端到端测试、API 自动化测试、HA 测试和性能测试进行体系化整理。

## 当前测试相关目录

```text
utm_simulator/tests/
utm_simulator/test_e2e_sim.py
atc_api_autotest/
atc_ha_test/
atc_test_cases/
atc_data_factory/
test_data_create/
```

## 目标结构

```text
apps/utm_simulator/tests/
├── unit/
│   ├── test_config.py
│   ├── test_schemas.py
│   ├── test_validators.py
│   └── test_simulation_core.py
├── integration/
│   ├── test_redis_client.py
│   ├── test_kafka_client.py
│   └── test_sim_manager.py
├── e2e/
│   └── test_e2e_sim.py
├── fixtures/
└── conftest.py

qa/
├── api_autotest/
├── ha_test/
├── performance/
└── data_factory/

datasets/
├── generated_scenes/
├── trajectory_samples/
└── alarm_cases/
```

## 执行要求

1. 单元测试只测试核心模块，不依赖 Redis、Kafka、外部 API。
2. 集成测试可以依赖 Redis、Kafka，但必须支持跳过。
3. E2E 测试放入 `e2e/`。
4. API 自动化测试放入 `qa/api_autotest/`。
5. HA 测试放入 `qa/ha_test/`。
6. 性能压测放入 `qa/performance/`。
7. 数据制造脚本放入 `qa/data_factory/`。
8. 测试数据样本放入 `datasets/`。
9. 不要删除历史测试。
10. 为 pytest 添加清晰的 marker。

## pytest 配置建议

请更新或新增：

```ini
[pytest]
testpaths = apps/utm_simulator/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: unit tests without external dependencies
    integration: tests requiring Redis/Kafka/API
    e2e: end-to-end simulation tests
    slow: slow tests
```

## 验证命令

```bash
pytest apps/utm_simulator/tests/unit
pytest apps/utm_simulator/tests -m "not integration and not e2e"
pytest apps/utm_simulator/tests -m integration
pytest apps/utm_simulator/tests -m e2e
```

如当前环境没有外部依赖，请跳过 integration 和 e2e，并说明原因。

------

# Prompt 8：第七阶段部署与启动脚本整理

你是一位 DevOps 工程师。请整理项目的部署文件、Docker 文件、Windows 启动脚本、Linux 启动脚本，并确保旧命令可用。

## 当前部署相关文件

```text
start_web.ps1
utm_simulator/deploy.sh
utm_simulator/deploy_repeat.sh
utm_simulator/requirements.txt
docker/
```

## 目标结构

```text
deploy/
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── .dockerignore
│   ├── entrypoint.sh
│   └── README.md
├── shell/
│   ├── deploy.sh
│   └── deploy_repeat.sh
└── windows/
    └── start_web.ps1
```

## 执行要求

1. 保留根目录 `start_web.ps1`。
2. 根目录 `start_web.ps1` 可以转调 `deploy/windows/start_web.ps1`。
3. 保留 `utm_simulator/deploy.sh` 和 `utm_simulator/deploy_repeat.sh` 作为兼容入口。
4. Docker 文件移动到 `deploy/docker/`。
5. 更新 Dockerfile 中的路径。
6. 更新 docker-compose.yml 中的挂载路径。
7. 更新 .dockerignore。
8. 更新部署 README。
9. 不要改变服务端口，除非原配置明确要求。
10. 不要删除旧部署文件。

## 验证命令

```bash
powershell -ExecutionPolicy Bypass -File start_web.ps1
bash deploy/shell/deploy.sh
docker compose -f deploy/docker/docker-compose.yml config
docker compose -f deploy/docker/docker-compose.yml up --build
```

如果当前环境无法运行 Docker 或 PowerShell，请至少完成配置校验和路径检查。

------

# Prompt 9：第八阶段历史代码与归档治理

你是一位代码仓库治理专家。请将项目中的历史代码、旧版本、备份文件、废弃配置、临时文件和旧自动化项目进行归档治理。

## 需要关注的文件和目录类型

```text
*_old/
*_1.0.py
*.bak_*
back/
simulation_core0609.py
kafka_proc_1.0.py
dkkgsit_atc主要服务配置文件_old/
低空空管接口自动_old/
atc_auto_test/
env.conf
tmp/
```

## 目标结构

```text
archive/
├── old_versions/
├── backups/
├── deprecated_configs/
├── legacy_autotest/
└── tmp/
```

## 执行要求

1. 历史文件只移动，不删除。
2. 旧版本 Python 文件放入 `archive/old_versions/`。
3. 备份文件放入 `archive/backups/`。
4. 废弃配置放入 `archive/deprecated_configs/`。
5. 历史自动化测试项目放入 `archive/legacy_autotest/`。
6. 临时抓包、日志、Pod 下载文件放入 `archive/tmp/` 或加入 `.gitignore`。
7. 如果某个旧文件仍被 import，不能移动，必须先报告。
8. 移动后创建 `archive/README.md`。

## archive README 内容要求

请生成：

```text
# Archive 归档目录说明

本目录用于存放历史代码、旧版本、备份文件、废弃配置和临时材料。

## 使用规则

1. archive 下内容不参与生产运行。
2. 核心代码不得 import archive 下模块。
3. 如需恢复历史逻辑，请复制到 active 目录并补充测试。
4. archive 中可能包含旧接口、旧配置或历史实验脚本，仅用于追溯。
5. 严禁在 archive 中保存真实密钥、密码、Token 或生产凭证。
```

## 输出结果

请输出：

1. 已归档文件清单。
2. 未归档文件及原因。
3. 是否发现核心代码引用旧文件。
4. 是否发现疑似敏感配置。
5. archive/README.md 内容。
6. 后续清理建议。

------

# Prompt 10：最终验收与架构文档更新

你是一位系统架构评审专家。请对本次目录与代码架构优化结果进行最终验收，并更新系统架构文档。

## 验收目标

请确认以下内容：

1. 核心系统仍可运行。
2. 原有启动入口仍可用。
3. 新目录结构清晰。
4. 后端、前端、数据、配置、测试、部署、文档、归档边界明确。
5. import 路径无明显错误。
6. 历史文件已归档。
7. README 和系统架构文档已更新。
8. Docker 和启动脚本路径已更新。
9. `.gitignore` 已覆盖运行时文件和临时文件。
10. 项目符合真实标准项目的前后端架构形式。

## 请执行或检查以下命令

```bash
python -m compileall apps/utm_simulator/backend
python -m compileall apps/utm_simulator/scripts
python -m compileall apps/utm_simulator/tools
pytest apps/utm_simulator/tests/unit
python utm_simulator/main.py
python utm_simulator/cli.py
python utm_simulator/web_server.py
docker compose -f deploy/docker/docker-compose.yml config
```

如部分命令因环境依赖无法运行，请说明：

1. 缺失什么依赖。
2. 哪些验证已完成。
3. 哪些验证需要人工在目标环境执行。

## 请更新系统架构文档

请在 `docs/architecture/系统架构文档.md` 中更新“三、目录与文件架构”章节，替换为优化后的目录结构。

更新内容应包括：

1. 根目录结构说明。
2. `apps/utm_simulator/` 核心系统说明。
3. `backend/` 后端结构说明。
4. `frontend/` 前端结构说明。
5. `data/` 数据目录说明。
6. `scripts/` 运行脚本说明。
7. `tools/` 工具脚本说明。
8. `qa/` 测试支撑体系说明。
9. `datasets/` 数据集说明。
10. `deploy/` 部署目录说明。
11. `docs/` 文档目录说明。
12. `archive/` 归档目录说明。
13. 兼容入口说明。
14. 迁移注意事项。
15. 后续优化计划。

## 输出最终报告

请输出一份最终报告，包含：

```text
# 系统文件架构优化验收报告

## 1. 优化目标
## 2. 优化前主要问题
## 3. 优化后目录结构
## 4. 核心文件迁移说明
## 5. 兼容入口保留说明
## 6. 测试与验证结果
## 7. 未完成事项
## 8. 风险与回滚方案
## 9. 后续优化建议
```

------

# Prompt 11：一键总控提示词

如果需要让 AI 编程助手从头到尾规划并执行，请使用以下总控提示词。

你是一位资深计算机领域系统架构师、Python 后端工程师、Web 全栈工程师和 DevOps 工程师。请基于当前项目的实际目录结构，对项目进行一次“低风险、渐进式、可回滚”的系统文件架构优化。

本项目是一个无人机模拟器与 Web 控制台系统，核心目录是 `utm_simulator/`，其中包含仿真核心、Flask Web 后端、Socket.IO WebSocket、Kafka/Redis 客户端、ATC API 桥接、AI 数据生成、JSON 数据管理、SQLite 数据库、前端 HTML/CSS/JS 页面、Leaflet 地图、Chart.js 图表、C++ UTM 核心库 Python 封装、工具脚本、测试、Mock 数据和部署脚本。

根目录下还包含 API 自动化测试、高可用测试、性能测试、数据工厂、Docker 部署、接口文档、历史自动化项目、本地 RAG 文档和工作流配置。

## 总体目标

请将项目优化为更符合真实标准项目的结构：

```text
atc_test_platform/
├── apps/utm_simulator/
│   ├── backend/
│   ├── frontend/
│   ├── data/
│   ├── scripts/
│   ├── tools/
│   └── tests/
├── qa/
├── datasets/
├── deploy/
├── docs/
└── archive/
```

## 必须遵守

1. 不破坏现有功能。
2. 不删除任何文件。
3. 不直接重写业务逻辑。
4. 保留旧入口兼容。
5. 每一步都要可回滚。
6. 每阶段完成后进行编译或运行验证。
7. 更新 README 和系统架构文档。
8. 对不确定依赖先分析再处理。
9. 对历史代码只归档不删除。
10. 对敏感配置只模板化，不写入真实凭证。

## 执行顺序

请严格按以下阶段执行：

1. 分析当前目录和依赖关系，输出方案。
2. 创建新目录骨架。
3. 整理外围目录：qa、datasets、deploy、docs、archive。
4. 包化核心后端代码。
5. 标准化前端目录。
6. 整理配置、数据、Schema、Mock、运行时文件。
7. 分类 tools、scripts、diagnostics。
8. 整理测试体系。
9. 整理 Docker 和启动脚本。
10. 归档历史代码。
11. 更新 README 和系统架构文档。
12. 执行最终验收。

## 每阶段输出格式

每个阶段结束后，请输出：

~~~text
## 阶段名称

### 已完成
- ...

### 修改文件
- ...

### 新增文件
- ...

### 移动文件
- ...

### 保留兼容入口
- ...

### 验证命令
```bash
...
~~~

### 验证结果

- ...

### 风险说明

- ...

### 下一步

- ...

```
## 最终输出

请最终输出：

1. 优化后的目录树。
2. 文件迁移映射表。
3. 兼容入口清单。
4. 验证结果。
5. 回滚方案。
6. 后续建议。

---

# Prompt 12：只生成文档、不改代码的安全提示词

如果当前只想让 AI 生成方案和文档，不希望它动代码，请使用以下提示词。

你是一位专业的系统架构师。请只阅读当前项目文件结构和系统架构文档，不要修改任何代码、不要移动任何文件、不要删除任何文件。

请基于当前系统架构文档中的“三、目录与文件架构”，生成一份《系统文件架构优化方案》，要求包括：

1. 当前目录结构分析。
2. 核心运行链路识别。
3. 测试、数据、文档、历史代码边界分析。
4. 现有目录问题。
5. 推荐目标目录结构。
6. 文件迁移映射表。
7. 兼容入口设计。
8. 分阶段实施计划。
9. 每阶段风险点。
10. 每阶段验证命令。
11. README 更新建议。
12. 系统架构文档更新建议。
13. 回滚方案。
14. 后续优化建议。

请用中文输出，内容要专业、完整、可直接作为项目重构设计文档使用。

---

# Prompt 13：代码重构前的依赖扫描提示词

你是一位代码依赖分析专家。请在任何目录迁移前，先扫描项目中的 Python import、Shell 脚本路径、PowerShell 脚本路径、HTML 静态资源路径、Dockerfile 路径、docker-compose 挂载路径和 README 中的命令路径。

## 请重点扫描

1. Python import：
   - import simulation_core
   - from simulation_core import
   - import sim_manager
   - import kafka_proc
   - import redis_client
   - import web_server
   - import db_manager
   - import json_data_manager

2. 脚本路径：
   - utm_simulator/
   - tools/
   - web/
   - mock/
   - schemas/
   - _source/
   - flight_task_templates/

3. 启动命令：
   - python main.py
   - python cli.py
   - python web_server.py
   - start_web.ps1
   - deploy.sh
   - deploy_repeat.sh

4. Docker 路径：
   - COPY
   - WORKDIR
   - volumes
   - command
   - entrypoint

5. 前端资源路径：
   - static/js
   - static/css
   - lib/leaflet
   - pages/

## 输出

请输出：

1. 依赖扫描结果。
2. 路径引用清单。
3. 高风险引用。
4. 可直接迁移文件。
5. 需要保留兼容入口的文件。
6. 需要先改配置再移动的文件。
7. 不建议移动的文件。
8. 迁移顺序建议。

在输出该报告前，不要修改任何文件。

---

# Prompt 14：兼容入口生成提示词

你是一位 Python 兼容层设计专家。项目正在进行目录重构，请为被移动的旧 Python 文件生成兼容入口，确保旧路径仍可运行。

## 要求

1. 旧文件路径保持存在。
2. 旧文件内部转发到新模块。
3. 如果旧文件原本可直接运行，则保留 `if __name__ == "__main__"`。
4. 如果新模块提供 `main()`，则调用 `main()`。
5. 如果新模块没有 `main()`，请保留原入口逻辑或报告需要人工处理。
6. 不要让新模块反向依赖旧模块。
7. 在兼容入口顶部添加迁移说明注释。

## 注释模板

```python
"""
兼容入口说明：
该文件为历史路径兼容入口。
真实实现已迁移至：<new_module_path>
保留该文件是为了兼容旧启动脚本、外部调用和历史文档命令。
后续新代码请直接引用新模块。
"""
```

## 示例

```python
"""
兼容入口说明：
该文件为历史路径兼容入口。
真实实现已迁移至：apps.utm_simulator.backend.core.simulation_core
保留该文件是为了兼容旧启动脚本、外部调用和历史文档命令。
后续新代码请直接引用新模块。
"""

from apps.utm_simulator.backend.core.simulation_core import *
```

请根据实际迁移映射，为每个旧文件生成对应兼容入口。

------

# Prompt 15：README 更新提示词

你是一位技术文档工程师。请根据项目优化后的目录结构，更新根目录 README.md。

## README 必须包含

1. 项目简介。
2. 核心功能。
3. 优化后的目录结构。
4. 快速启动。
5. 后端结构说明。
6. 前端结构说明。
7. 数据目录说明。
8. 配置说明。
9. 脚本工具说明。
10. 测试说明。
11. 部署说明。
12. 历史归档说明。
13. 兼容入口说明。
14. 常见问题。
15. 开发规范。

## 快速启动示例

请保留旧启动方式：

```powershell
.\start_web.ps1
```

同时增加新启动方式：

```bash
python -m apps.utm_simulator.backend.main
```

如果新启动方式暂未完全实现，请标注“推荐后续迁移使用”，不要误导用户。

## 文档风格

1. 中文。
2. 结构清晰。
3. 面向新开发者。
4. 不夸大功能。
5. 保留必要的注意事项。
6. 明确哪些目录是核心运行目录，哪些目录是测试支撑目录，哪些目录是历史归档目录。

------

# Prompt 16：回滚方案提示词

你是一位发布与回滚方案专家。请为本次系统文件架构优化生成回滚方案。

## 回滚目标

如果目录重构后出现启动失败、import 错误、Docker 构建失败、前端资源加载失败、Kafka/Redis 数据注入失败，需要能快速恢复到重构前状态。

## 请输出

1. 回滚前提。
2. 回滚触发条件。
3. Git 分支策略。
4. 目录移动回滚清单。
5. 兼容入口回滚方案。
6. 配置文件回滚方案。
7. Docker 回滚方案。
8. 前端路径回滚方案。
9. 数据文件回滚方案。
10. 验证命令。
11. 回滚后检查表。

## 推荐策略

请建议使用：

```bash
git checkout -b refactor/project-structure
git status
git add .
git commit -m "chore: backup before project structure refactor"
```

每个阶段单独提交：

```bash
git commit -m "refactor: organize qa and archive directories"
git commit -m "refactor: package utm simulator backend"
git commit -m "refactor: organize frontend assets"
git commit -m "refactor: normalize config and data directories"
```

如果失败，可按阶段回滚。

------

# Prompt 17：最终提交说明生成提示词

你是一位资深 Git 提交说明撰写专家。请根据本次项目文件架构优化内容，生成规范的 Git commit message 和变更说明。

## 输出内容

1. 总提交标题。
2. 分阶段 commit message。
3. Pull Request 描述。
4. 变更范围。
5. 风险说明。
6. 测试结果。
7. 回滚方案。
8. Reviewer 重点关注点。

## commit message 风格

请使用 Conventional Commits，例如：

```text
refactor: reorganize project structure with backward compatibility
docs: update architecture documentation for new layout
chore: archive legacy scripts and deprecated configs
test: reorganize simulator tests and qa assets
build: update docker deployment paths
```

------

# 附：推荐执行顺序

建议不要一次性使用“一键总控提示词”直接让 AI 修改整个项目。更稳妥的方式是：

1. 先使用 Prompt 12，只生成方案，不改代码。
2. 再使用 Prompt 13，做依赖扫描。
3. 使用 Prompt 2，整理外围目录。
4. 使用 Prompt 3，包化核心后端。
5. 使用 Prompt 4，整理前端。
6. 使用 Prompt 5，整理配置和数据。
7. 使用 Prompt 6，整理工具脚本。
8. 使用 Prompt 7，整理测试体系。
9. 使用 Prompt 8，整理部署。
10. 使用 Prompt 9，归档历史代码。
11. 使用 Prompt 10，做最终验收。
12. 使用 Prompt 15，更新 README。
13. 使用 Prompt 16，生成回滚方案。
14. 使用 Prompt 17，生成提交说明。

每完成一个阶段，都应先提交一次 Git 版本，确保可回滚。