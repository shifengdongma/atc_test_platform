# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

低空空管（ATC/UTM）自动化测试平台，服务于"海豚"（Dolphin）ATC 态势感知 Dashboard（`dkkgsit-test.testdolphin.com`）。通过无人机模拟器向 Redis/Kafka 注入仿真数据，驱动 Dashboard 展示，并对其进行 API 自动化测试、高可用测试和性能测试。

## Python 环境（强制）

- **环境名称**: `utm`（Python 3.11.15）
- **Conda 路径**: `C:\ProgramData\anaconda3\Scripts\conda.exe`
- **运行脚本**: `conda run -n utm python <script>` 或先 `conda activate utm`

## 目录架构

| 目录 | 说明 |
|------|------|
| `utm_simulator/` | 无人机模拟器核心（aka utm_moc52），仿真数千架无人机飞行，向 Redis 写飞行计划、向 Kafka 发实时遥测 |
| `atc_api_autotest/` | IOMP API 自动化测试：JWT 鉴权、服务管理、Redis/Kafka 一致性校验、达梦数据库操作 |
| `atc_ha_test/` | 高可用测试：双集群服务重启、Kafka 积压监控、大规模模拟器发射（3000/5000 架） |
| `docs/` | 中文架构文档、核心原理、环境配置说明 |
| `skills_hub/` | 团队协作工具（子模块） |

## 核心数据流

```
utm_simulator → Redis BIZ_DATA:UAV_ROUTE (飞行计划)    → ATC Dashboard 读取展示航线
utm_simulator → Kafka uav_runtime_data (实时遥测)      → ATC Dashboard 消费展示无人机位置/状态
utm_simulator ← Kafka uav_runtime_trace (轨迹预测)     → 消费下游 UTM 系统的预测结果
ATC_backend  → Redis (预测结果/空域)                   → Dashboard 前端查询
ATC_backend  → Kafka uav_collision_alarm (冲突告警)    → Dashboard 展示告警
```

核心技术原理：模拟器扮演"虚拟无人机群"，通过共享的 Redis/Kafka 基础设施向 ATC 系统注入仿真数据，Dashboard 对数据来源（真实 vs 仿真）完全无感知。

## 常用命令

```bash
# 激活环境
conda activate utm

# 启动模拟器（动态仿真模式）
cd utm_simulator && python main.py

# 安装模拟器依赖
cd utm_simulator && pip install -r requirements.txt

# 运行 API 测试用例
cd atc_api_autotest && python run_testcase.py

# 高可用 — 双集群服务重启
cd atc_ha_test && python ha_iomp_server_reboot.py --service la-atc-biz-backend

# 高可用 — Kafka 积压监控
cd atc_ha_test && python ha_kafka_lag_check.py

# 获取 IOMP JWT Token（独立测试）
cd atc_api_autotest/api_tools && python iomp_api_common.py
```

## 代码规范

- 所有 Python 文件 UTF-8 编码，文件头 `# -*- coding: utf-8 -*-`
- 注释、文档字符串、打印信息使用中文；与外部系统一致的字段名/枚举值使用英文
- 推荐使用 `typing` 类型注解（`List[Dict[str, Any]]`、`Optional[str]` 等）
- 在子目录运行的脚本需将项目根目录加入 `sys.path`，方便无包前缀导入
- JSON 读写：`encoding='utf-8'`，写入 `ensure_ascii=False`
- **修改原则**：聚焦修复实际 bug，不添加防御性预判代码。异常路径的兜底逻辑优先用已有的 fallback 机制（如 MySQL→SQLite 降级），不在每个函数中重复添加相同的 if 判断。保持代码精简，不为"可能发生但从未出现"的场景预先加代码

## 数据库架构（重要：两种数据库职责完全不同）

| 数据库 | 类型 | 职责 | 访问方式 | 配置入口 |
|--------|------|------|----------|----------|
| **达梦 (Dameng)** | 只读 | 外部 ATC 系统数据库，查询飞行航线 (`air_route`) 和飞行计划等业务数据 | `dmPython` 驱动，通过 `dmdbclient.py` → `DmDbClient` 连接 | `atc_api_autotest/env.py` 的 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_SCHEMA` |
| **MySQL** | 读写 | 测试平台主数据库：仿真配置、JSON文件元数据、定时任务、任务日志、告警类型 | `pymysql` → `mysqldbclient.py` → `MysqlDbClient` | `common/config.py` 的 `load_mysql_config()`，环境变量 `UTM_MYSQL_*` |

**关键规则**：
- 达梦和 MySQL **完全独立**，不可混用。达梦是只读的外部数据源，MySQL/SQLite 是测试平台的本地存储。
- 达梦连接失败 ≠ MySQL 连接失败，排查时先确认是哪个数据库报错。
- `mysql_db_manager.py` 只管理 MySQL/SQLite，不涉及达梦。
- `json_data_manager.py` 中的 `_get_dm_client()` 只管理达梦，不涉及 MySQL。
- 修改任一数据库配置时，确认不会影响另一个。

## Redis/Kafka 连接约定

- **配置入口**: `atc_api_autotest/env.py` 和 `atc_ha_test/ha_env.py`
- **Redis Key**: `BIZ_DATA:UAV_ROUTE`（飞行计划 Hash）、`BIZ_DATA:AIRSPACE`（空域 Hash）
- **Kafka Topic**: `uav_runtime_data`（遥测）、`uav_runtime_trace`（轨迹预测）
- 连接配置含敏感信息，勿提交版本库

## 关键依赖

- `kafka-python` — Kafka 生产者/消费者
- `redis` — Redis 客户端
- `requests` — HTTP 接口调用
- `dmPython` — 达梦数据库连接（需单独安装）
- `utm_simulator/pylib/` — C++ UTM 核心库的 Python 封装（数据结构 + 引擎）

## 重要说明

- `utm_simulator/` 有独立的 `CLAUDE.md`，包含模拟器子项目的详细规则和数据格式约定
- 算法对接文档位于 `utm_simulator/_source/算法对接 2026030301.md`，字段/枚举以此为准
- 项目工作流要求**先出方案、用户确认后再改代码**（参见 `.agent/rules.md`）
- HA 测试涉及 A/B 双集群，配置在 `ha_env.py`（不提交仓库）

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