# AGENTS.md - AI 编码助手指南

## 项目概述

UTM MOC52 - 无人机交通管理系统仿真项目，将飞行计划写入 Redis，将遥测数据写入 Kafka。

## 构建与运行命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行主仿真程序
python main.py

# 运行 Mock 数据注入
python tools/run_kafka.py

# 运行特定工具脚本
python tools/lines_to_redis_route.py --input lines.json
python tools/nfzs.py

# 暂无正式测试套件 - 通过手动运行脚本验证
```

## 代码风格指南

### 文件头
所有 Python 文件必须以以下内容开头：
```python
# -*- coding: utf-8 -*-
```

### 语言规范
- **注释和文档字符串：中文（中文）**
- **对外接口的字段名/枚举：英文**（按算法对接规范）
- **打印信息：中文**

### 导入规范
```python
# 标准库优先
import sys
import time
import json
from typing import Dict, List, Any, Optional

# 第三方包
import redis
from kafka import KafkaProducer

# 项目模块（tools/ 脚本需添加项目根目录到 sys.path）
from redis_client import RedisClient
from kafka_proc import KafkaProducerClient
```

tools/ 目录下的脚本需添加项目根目录到路径：
```python
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
```

### 类型注解
函数签名使用 typing：
```python
def process_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """处理数据并返回结果列表"""
    pass
```

### 命名规范
- 函数和变量：`snake_case`
- 类名：`PascalCase`
- 常量：`UPPER_CASE`
- Redis 键：`BIZ_DATA:UAV_ROUTE`, `BIZ_DATA:AIRSPACE`
- Kafka 主题：`uav_runtime_data`, `uav_runtime_trace`

### JSON 处理
```python
# 读取
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 写入 - ensure_ascii=False 以正确保存中文
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

### 错误处理
```python
try:
    result = operation()
except Exception as e:
    print(f"操作失败: {e}")
    # 优雅处理
```

### Redis 操作
```python
from redis_client import RedisClient

redis_client = RedisClient(redis_ip, redis_port, redis_password)
redis_client.hset("BIZ_DATA:UAV_ROUTE", uid, json.dumps(data, ensure_ascii=False))
```

## 架构说明

| 模块 | 用途 |
|------|------|
| `main.py` | 主仿真循环，包含 DataSource/DataFlow |
| `simulation_core.py` | 无人机代理、仿真器、禁飞区 |
| `kafka_proc.py` | Kafka 生产者/消费者封装 |
| `redis_client.py` | Redis 封装（hset/hget/hgetall） |
| `pylib/` | C++ UTM 核心数据结构 |
| `tools/` | 工具脚本（run_kafka.py、nfzs.py 等） |

## 数据格式参考

始终遵循 `_source/算法对接2026.md` 中的规范：
- 飞行计划结构（flightPlanId、routeList 等）
- 遥测消息格式
- 空域（禁飞区）结构
- 枚举值和字段含义

## Git 提交规范（来自 .cursorrules）

格式：`<类型>: <中文描述>`

类型：`feat:`、`fix:`、`refactor:`、`chore:`、`style:`、`docs:`、`revert:`

示例：`feat: 添加航线起始线和降落线生成`
