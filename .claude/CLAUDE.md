# Claude 项目上下文

## Python 环境（强制）

- **环境名称**: `utm`（Python 3.11.15）
- **Conda 路径**: `C:\ProgramData\anaconda3\Scripts\conda.exe`
- **运行脚本**: `conda run -n utm python <script>` 或先 `conda activate utm`

## 项目简介

低空空管自动化系统测试项目，包含：

- **无人机模拟器**: 多架无人机轨迹生成与发射
- **航路管理**: 航路规划、偏航检测、冲突预警
- **自动化测试**: API 测试、UI 测试、性能测试
- **高可用测试**: Chaos Mesh 故障注入、Redis/Kafka 同步验证

## 关键模块

| 目录 | 说明 |
|------|------|
| `utm_simulator/` | 无人机模拟器核心代码 |
| `atc_api_autotest/` | 自动化测试框架与用例 |
| `atc_ha_test/` | 高可用与混沌测试 |
| `database/` | 数据库管理层（MySQL/达梦/SQLite） |
| `common/` | 公共配置与工具模块 |
| `docs/` | 项目文档与工作日志 |

## 常用命令

```bash
# 激活环境
conda activate utm

# 运行模拟器
cd utm_simulator && python main.py

# 运行测试
cd atc_api_autotest && python run_testcase.py

# 高可用测试
cd atc_ha_test && python ha_iomp_server_reboot.py
```

## 数据库架构（重要：两种数据库职责完全不同）

| 数据库 | 类型 | 职责 | 实现文件 |
|--------|------|------|----------|
| **达梦 (Dameng)** | 只读 | 外部 ATC 系统，查询飞行航线/计划 | `dmdbclient.py` → `DmDbClient` |
| **MySQL** | 读写 | 测试平台本地持久化 | `mysqldbclient.py` → `MysqlDbClient` |
| **SQLite** | 读写 | MySQL 不可用时的自动降级 | `db_manager.py` |

- 达梦和 MySQL **完全独立**，不可混用。排查日志时先确认是哪个数据库报错。
- `mysql_db_manager.py` 只管理 MySQL/SQLite；`json_data_manager.py` 中的 `_get_dm_client()` 只管理达梦。

## 注意事项

- 所有 Python 脚本使用 `utm` Conda 环境（Python 3.11.15）
- Kafka/Redis 连接配置在 `env.py`
- 测试数据注意清理，避免磁盘占用过大
- 达梦数据库需要 `dmPython` 驱动（需单独安装）
