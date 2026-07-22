# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

低空空管（ATC/UTM）仿真数据注入平台，服务于"海豚"（Dolphin）ATC 态势感知 Dashboard（`dkkgsit-test.testdolphin.com`）。通过向 Redis/Kafka 注入仿真数据，驱动 Dashboard 展示。

## Python 环境（强制）

- **环境名称**: `utm`（Python 3.11.15）
- **Conda 路径**: `C:\ProgramData\anaconda3\Scripts\conda.exe`
- **运行脚本**: `conda run -n utm python <script>` 或先 `conda activate utm`

## 目录架构

| 目录 | 说明 |
|------|------|
| `core/` | 仿真核心层：仿真编排（scene + plan 模式）、Redis/Kafka 客户端、UAV 标识符 |
| `common/` | 基础设施层：统一配置管理（环境变量 + JSON）、结构化日志、数据模型、Pydantic 验证、异常层次 |
| `database/` | 持久化层：MySQL/SQLite CRUD、JSON 文件管理、多环境配置管理、Cron 场景编排调度、实时日志流 |
| `services/` | 服务层：AI 数据生成集成、态势监控 (WebSocket STOMP)、TCP 网关日志轮询、Web 数据生成桥接、ATC API 桥接 |
| `tools/` | 工具层：达梦/MySQL 数据库客户端、IOMP API/JWT 工具、Kafka 注入脚本、Redis 计划插值、数据生成脚本 |
| `web/` | 表示层：Flask WebSocket 后端 + 前端页面 (HTML/JS/CSS) |
| `data/` | 数据文件：JSON Schema、场景模板、Mock 数据 |
| `docker/` | Docker 部署配置 |
| `docs/` | 中文架构文档、核心原理、环境配置说明 |
| `tests/` | 单元测试 |
| `skills_hub/` | 团队协作工具（子模块） |

## 核心数据流

```
仿真注入（scene/plan 模式）
  ├── scene: JSON 场景文件 → tools/run_kafka_scene.py → Kafka uav_runtime_data
  └── plan:  Redis BIZ_DATA:UAV_ROUTE → tools/run_plan.py → 插值 → Kafka uav_runtime_data

ATC Dashboard 消费:
  Redis BIZ_DATA:UAV_ROUTE (飞行计划)  → Dashboard 展示航线
  Kafka uav_runtime_data (实时遥测)    → Dashboard 展示无人机位置/状态
  Kafka uav_runtime_trace (轨迹预测)   ← 下游 UTM 系统产出的预测结果
  Kafka uav_collision_alarm (冲突告警) → Dashboard 展示告警
```

核心技术原理：通过共享的 Redis/Kafka 基础设施向 ATC 系统注入仿真数据，Dashboard 对数据来源（真实 vs 仿真）完全无感知。

## 常用命令

```bash
# 激活环境
conda activate utm

# 启动 Web 可视化控制台
python cli.py server
# 或 PowerShell: .\start_web.ps1

# 安装依赖
pip install -r requirements.txt

# 场景文件注入（scene 模式）
python tools/run_kafka_scene.py --file data/mock/scene.json

# Redis 计划插值（plan 模式）
python tools/run_plan.py

# 数据生成
python tools/create_data_scene.py --help
python tools/create_data_scenes.py --help

# 运行单元测试
python -m pytest tests/ -v
```

## 数据库架构（重要：两种数据库职责完全不同）

| 数据库 | 类型 | 职责 | 访问方式 | 配置入口 |
|--------|------|------|----------|----------|
| **达梦 (Dameng)** | 只读 | 外部 ATC 系统数据库，查询飞行航线 (`air_route`) 和飞行计划等业务数据 | `dmPython` 驱动，通过 `tools/dmdbclient.py` → `DmDbClient` 连接 | 根目录 `env.py` 的 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_SCHEMA` |
| **MySQL** | 读写 | 测试平台主数据库：仿真配置、JSON文件元数据、定时任务、任务日志、告警类型 | `pymysql` → `tools/mysqldbclient.py` → `MysqlDbClient` | `common/config.py` 的 `load_mysql_config()`，环境变量 `UTM_MYSQL_*` |

**关键规则**：
- 达梦和 MySQL **完全独立**，不可混用。达梦是只读的外部数据源，MySQL/SQLite 是测试平台的本地存储。
- 达梦连接失败 ≠ MySQL 连接失败，排查时先确认是哪个数据库报错。
- `database/mysql_db_manager.py` 只管理 MySQL/SQLite，不涉及达梦。
- `database/json_data_manager.py` 中的 `_get_dm_client()` 只管理达梦，不涉及 MySQL。
- 修改任一数据库配置时，确认不会影响另一个。

## Redis/Kafka 连接约定

- **配置入口**: 根目录 `env.py` 和 `common/config.py`
- **Redis Key**: `BIZ_DATA:UAV_ROUTE`（飞行计划 Hash）、`BIZ_DATA:AIRSPACE`（空域 Hash）
- **Kafka Topic**: `uav_runtime_data`（遥测）、`uav_runtime_trace`（轨迹预测）
- 连接配置含敏感信息，勿提交版本库

## 代码规范

- 所有 Python 文件 UTF-8 编码，文件头 `# -*- coding: utf-8 -*-`
- 注释、文档字符串、打印信息使用中文；与外部系统一致的字段名/枚举值使用英文
- 推荐使用 `typing` 类型注解（`List[Dict[str, Any]]`、`Optional[str]` 等）
- JSON 读写：`encoding='utf-8'`，写入 `ensure_ascii=False`
- **修改原则**：聚焦修复实际 bug，不添加防御性预判代码。异常路径的兜底逻辑优先用已有的 fallback 机制（如 MySQL→SQLite 降级），不在每个函数中重复添加相同的 if 判断。

## 仿真模式

| 模式 | 入口 | 数据流 |
|------|------|--------|
| scene (场景文件注入) | `tools/run_kafka_scene.py` | JSON 文件 → Kafka `uav_runtime_data` |
| plan (Redis 计划插值) | `tools/run_plan.py` | Redis `BIZ_DATA:UAV_ROUTE` → 插值 → Kafka |

## 工作日志维护规则

**每次计划执行后涉及到系统代码的优化更新内容，都必须按照 `docs/utm-simulator-optimization-work-log.md` 的内容格式补充更新到该文档中。**

- 按日期和时间顺序追加，不删减以前的工作日志
- 每条记录包含：日期、文件、操作（新建/修改/重写）、状态、验证方式
- 每次优化汇总新建/修改文件数
- 引用来源计划文档（如有）

## 工作总结维护规则

**每次完成任务后，必须参考 `docs/工作总结.md` 前面的内容格式，实时更新工作总结内容。**

- 按日期和时间顺序在文件末尾追加，保留历史记录不删减
- 每条记录包含：完成时间、修改的文件列表（含操作类型和关键改动说明）、核心成果描述
- 使用与已有内容一致的 Markdown 表格格式
- 涉及多个子任务时，汇总列出所有改动文件及关键变更点
