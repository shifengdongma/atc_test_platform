# 低空空管系统 JMX 接口测试用例生成器 Skill

## 概述

本 Skill 用于根据低空空管系统的 Swagger API 文档自动生成 Apache JMeter 的 JMX 接口测试脚本。

## 目录结构

```
skills/
├── README.md                      # 本文件
├── SKILL.md                       # Skill 主文档（使用说明）
├── scripts/                       # 脚本目录
│   └── swagger_to_jmx_generator_v2.py  # 主生成器脚本
├── references/                    # 参考文档目录
│   ├── jmx_format.md             # JMX 文件格式说明
│   ├── test_data_patterns.md     # 测试数据生成模式
│   └── usage_guide.md            # 详细使用指南
└── examples/                      # 示例文件目录
    ├── 空域情报_起降场.jmx       # 人工编写的参考用例
    ├── KTP_1_Environments.json   # 环境配置参考
    └── 低空空管自动化系统-空域情报接口.json  # 接口定义示例
```

## 快速开始

### 1. 准备 Swagger 文件

将 Swagger API 文档放置在工作目录：
- `低空空管自动化系统swaggerApi0422.json`
- `低空运维系统swaggerApi0422.json`

### 2. 运行生成器

```bash
cd scripts
python swagger_to_jmx_generator_v2.py
```

### 3. 查看生成结果

生成的 JMX 文件将位于 `接口测试用例jmx/` 目录。

## 命令行参数

```bash
python swagger_to_jmx_generator_v2.py [环境] [优先级]
```

- **环境**: `sit` (默认) 或 `uat`
- **优先级**: `P0`, `P1`, `P2`, `P3` (默认生成全部)

### 使用示例

```bash
# 生成所有测试用例
python swagger_to_jmx_generator_v2.py

# 只生成 SIT 环境 P0 优先级的核心场景
python swagger_to_jmx_generator_v2.py sit P0

# 生成 UAT 环境的测试用例
python swagger_to_jmx_generator_v2.py uat
```

## 生成的场景

### 低空空管自动化系统 (15个场景)

| 编号 | 场景名称 | 优先级 | 接口数 |
|-----|---------|--------|-------|
| 01 | 起降场管理场景 | P0 | 6 |
| 02 | 扇区管理场景 | P0 | 6 |
| 03 | 航路航线管理场景 | P0 | 8 |
| 04 | 空域管理场景 | P0 | 10 |
| 05 | 飞行计划管理场景 | P0 | 18 |
| 06 | 飞行任务管理场景 | P0 | 17 |
| 07 | 无人机管理场景 | P1 | 12 |
| 08 | 告警管理场景 | P1 | 13 |
| 09 | 坐席管理场景 | P1 | 9 |
| 10 | 用户权限管理场景 | P1 | 32 |
| 11 | 态势大屏查询场景 | P2 | 24 |
| 12 | 运营人管理场景 | P1 | 5 |
| 13 | 操作日志查询场景 | P2 | 5 |
| 14 | 接收机管理场景 | P1 | 5 |
| 15 | 其他功能场景 | P3 | 26 |

### 低空运维系统 (6个场景)

| 编号 | 场景名称 | 优先级 | 接口数 |
|-----|---------|--------|-------|
| 21 | 运维接收机管理场景 | P1 | 12 |
| 22 | 运维告警管理场景 | P1 | 3 |
| 23 | 版本升级管理场景 | P2 | 6 |
| 24 | 网络拓扑管理场景 | P2 | 12 |
| 25 | 运维监控查询场景 | P2 | 6 |
| 26 | 运维公共接口场景 | P3 | 7 |

## 在 JMeter 中使用

### GUI 模式

1. 启动 JMeter
2. 文件 -> 打开 -> 选择生成的 JMX 文件
3. 在 TestPlan 的 `User Defined Variables` 中更新 `jwt-token`
4. 点击启动按钮执行测试

### 非 GUI 模式（推荐）

```bash
# 基本执行
jmeter -n -t 接口测试用例jmx/01_起降场管理场景_sit.jmx -l result.jtl

# 覆盖环境变量
jmeter -Jhost=dkkguat-test.testdolphin.com -Jjwt-token=新的token值 -n -t 接口测试用例jmx/01_起降场管理场景_sit.jmx -l result.jtl

# 生成 HTML 报告
jmeter -g result.jtl -o report/
```

## 参考文档

- [SKILL.md](./SKILL.md) - 完整的 Skill 使用文档
- [references/jmx_format.md](./references/jmx_format.md) - JMX 文件格式详细说明
- [references/test_data_patterns.md](./references/test_data_patterns.md) - 测试数据生成规则
- [references/usage_guide.md](./references/usage_guide.md) - 详细使用指南和最佳实践

## 示例文件

- [examples/空域情报_起降场.jmx](./examples/空域情报_起降场.jmx) - 人工编写的完整参考用例
- [examples/KTP_1_Environments.json](./examples/KTP_1_Environments.json) - 环境配置参考

## 注意事项

1. **JWT Token**: 默认 token 可能过期，执行前请更新为有效的认证令牌
2. **环境可访问性**: 执行前确保测试环境可访问
3. **数据清理**: 测试用例会创建测试数据，建议定期清理
4. **JMeter 版本**: 生成的 JMX 文件兼容 JMeter 5.0+ 版本

## 故障排除

### JMeter 无法打开 JMX 文件

确保 JMX 文件结构正确，ThreadGroup 必须位于根 hashTree 下，与 TestPlan 同级。

### 接口返回 401 未授权

更新 `User Defined Variables` 中的 `jwt-token` 为有效的认证令牌。

### 接口返回 404 未找到

检查 `host` 和 `basePath` 变量是否正确配置。

## 版本历史

- **v2.0** (2026-04-22)
  - 场景化测试组织
  - 环境配置管理（SIT/UAT）
  - 动态测试数据生成
  - 事务控制器支持
  - 完整的 JSON Path 断言
