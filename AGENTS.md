# Codex 项目上下文

## 项目简介

低空空管自动化系统测试项目，包含：

- **无人机模拟器**: 多架无人机轨迹生成与发射
- **航路管理**: 航路规划、偏航检测、冲突预警
- **自动化测试**: API 测试、UI 测试、性能测试
- **高可用测试**: Chaos Mesh 故障注入、Redis/Kafka 同步验证

## 关键模块

| 目录 | 说明 |
|------|------|
| `utm_moc52_develop/` | 无人机模拟器核心代码 |
| `atc_auto_test/` | 自动化测试框架与用例 |
| `ha_test/` | 高可用与混沌测试 |
| `utm_test_cases/` | 测试场景与用例管理 |

## 常用命令

```bash
# 激活环境
conda activate utm

# 运行模拟器
python main.py

# 运行测试
pytest atc_auto_test/
```

## 注意事项

- 所有 Python 脚本使用 `utm` Conda 环境
- Kafka/Redis 连接配置在 `env.py`
- 测试数据注意清理，避免磁盘占用过大
