# Claude 项目上下文

## Python 环境（强制）

- **环境名称**: `utm`（Python 3.11.15）
- **Conda 路径**: `C:\ProgramData\anaconda3\Scripts\conda.exe`
- **运行脚本**: `conda run -n utm python <script>` 或先 `conda activate utm`

## 项目简介

低空空管自动化系统仿真数据注入平台，包含：

- **场景文件注入**: JSON 场景文件 → Kafka 遥测
- **Redis 计划插值**: Redis 飞行计划 → 插值 → Kafka
- **Web 控制台**: 环境管理、数据管理、数据生成、场景编排、系统日志
- **AI 数据生成**: 大模型生成测试数据

## 关键模块

| 目录 | 说明 |
|------|------|
| `core/` | 仿真核心层（编排、Redis/Kafka 客户端、UAV ID） |
| `common/` | 基础设施（配置、日志、Schema、验证、异常） |
| `database/` | 持久化层（MySQL/SQLite、JSON管理、环境管理、编排、日志流） |
| `services/` | 服务层（AI集成、态势监控、网关日志、API桥接） |
| `tools/` | 工具层（数据库客户端、Kafka注入、Redis插值、数据生成） |
| `web/` | 表示层（Flask后端 + 前端页面） |
| `data/` | 数据文件（Schema、模板、Mock） |
| `docker/` | Docker 部署配置 |
| `docs/` | 项目文档与工作日志 |
| `tests/` | 单元测试 |

## 常用命令

```bash
conda activate utm
python cli.py server
python tools/run_kafka_scene.py --file data/mock/scene.json
python tools/run_plan.py
python -m pytest tests/ -v
```

## 数据库架构

| 数据库 | 类型 | 职责 | 实现文件 |
|--------|------|------|----------|
| **达梦 (Dameng)** | 只读 | 外部 ATC 系统 | `tools/dmdbclient.py` |
| **MySQL** | 读写 | 测试平台本地持久化 | `tools/mysqldbclient.py` |
| **SQLite** | 读写 | MySQL 不可用时的降级 | `database/db_manager.py` |

- 达梦和 MySQL 完全独立，不可混用
- 敏感配置勿提交版本库
