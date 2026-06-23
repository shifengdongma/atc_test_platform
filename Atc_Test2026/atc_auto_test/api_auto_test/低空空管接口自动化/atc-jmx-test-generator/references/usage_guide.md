# 使用指南

## 概述

本文档提供低空空管系统 JMX 接口测试用例生成器的详细使用说明。

## 环境准备

### 系统要求

- Python 3.7+
- Apache JMeter 5.0+
- 足够的磁盘空间（每个 JMX 文件约 50-200KB）

### Python 依赖

生成器脚本使用 Python 标准库，无需额外安装依赖。

### JMeter 配置

1. 下载并安装 Apache JMeter 5.0 或更高版本
2. 确保 `jmeter` 命令在系统 PATH 中可用
3. 建议安装以下插件：
   - JSON Path Extractor（通常已内置）
   - JSON Path Assertion（通常已内置）

## 快速开始

### 1. 准备 Swagger 文件

确保以下文件存在于工作目录：
- `低空空管自动化系统swaggerApi0422.json` - 空管系统 API 定义
- `低空运维系统swaggerApi0422.json` - 运维系统 API 定义

### 2. 运行生成器

```bash
python swagger_to_jmx_generator_v2.py
```

### 3. 查看生成结果

生成的 JMX 文件位于 `接口测试用例jmx/` 目录。

### 4. 在 JMeter 中打开

1. 启动 JMeter GUI
2. 选择 `文件` -> `打开`
3. 选择生成的 JMX 文件
4. 查看测试计划结构

## 生成器脚本参数

### 命令行参数

```bash
python swagger_to_jmx_generator_v2.py [环境] [优先级]
```

**参数说明：**

| 参数 | 可选值 | 默认值 | 说明 |
|-----|--------|--------|------|
| 环境 | sit, uat | sit | 目标测试环境 |
| 优先级 | P0, P1, P2, P3 | 全部 | 只生成指定优先级的场景 |

### 使用示例

```bash
# 生成 SIT 环境所有测试用例（默认）
python swagger_to_jmx_generator_v2.py

# 生成 UAT 环境所有测试用例
python swagger_to_jmx_generator_v2.py uat

# 只生成 SIT 环境 P0 优先级的核心场景
python swagger_to_jmx_generator_v2.py sit P0

# 生成 UAT 环境 P0 和 P1 优先级的场景
python swagger_to_jmx_generator_v2.py uat P0
```

## 场景优先级说明

### P0 - 核心业务流程（最高优先级）

包含系统最核心的业务功能，必须保证 100% 通过：
- 起降场管理
- 扇区管理
- 航路航线管理
- 空域管理
- 飞行计划管理
- 飞行任务管理

### P1 - 重要业务功能（高优先级）

包含重要的业务功能，建议保证 95% 以上通过：
- 无人机管理
- 告警管理
- 坐席管理
- 用户权限管理
- 运营人管理
- 接收机管理
- 运维相关功能

### P2 - 辅助查询功能（中优先级）

包含查询和统计功能，建议保证 90% 以上通过：
- 态势大屏查询
- 操作日志查询
- 运维监控查询
- 版本升级管理
- 网络拓扑管理

### P3 - 其他功能（低优先级）

包含其他辅助功能，建议保证 80% 以上通过：
- 其他功能场景
- 运维公共接口

## 在 JMeter 中使用

### GUI 模式

1. **打开 JMX 文件**
   - 启动 JMeter
   - 文件 -> 打开 -> 选择 JMX 文件

2. **更新环境变量**
   - 在 TestPlan 下找到 `User Defined Variables`
   - 更新 `jwt-token` 为有效的认证令牌
   - 根据需要更新 `host`、`port`、`basePath`

3. **执行测试**
   - 点击工具栏的 `启动` 按钮
   - 查看 `查看结果树` 监听器

### 非 GUI 模式（推荐用于性能测试）

```bash
# 基本执行
jmeter -n -t 接口测试用例jmx/01_起降场管理场景_sit.jmx -l result.jtl

# 指定结果文件
jmeter -n -t 接口测试用例jmx/01_起降场管理场景_sit.jmx -l result.jtl -j jmeter.log

# 覆盖环境变量
jmeter -Jhost=dkkguat-test.testdolphin.com -Jjwt-token=新的token值 -n -t 接口测试用例jmx/01_起降场管理场景_sit.jmx -l result.jtl

# 生成 HTML 报告
jmeter -g result.jtl -o report/
```

### 批量执行多个场景

```bash
# 创建批量执行脚本
for file in 接口测试用例jmx/*.jmx; do
    echo "执行: $file"
    jmeter -n -t "$file" -l "results/$(basename $file .jmx).jtl"
done
```

## 环境变量配置

### 默认环境变量

每个 JMX 文件包含以下用户定义变量：

| 变量名 | 默认值 | 说明 |
|-------|--------|------|
| protocol | https | 通信协议 |
| host | dkkgsit-test.testdolphin.com | 服务器地址 |
| port | 443 | 端口号 |
| basePath | /la-atc-biz-backend | API 基础路径 |
| jwt-token | eyJhbGciOiJSUzI1NiJ9... | JWT 认证令牌 |

### 覆盖环境变量

#### 方式 1：在 JMeter GUI 中修改

1. 打开 JMX 文件
2. 在 TestPlan 下找到 `User Defined Variables`
3. 修改变量值

#### 方式 2：通过命令行参数

```bash
jmeter -Jhost=新的服务器地址 -Jjwt-token=新的token值 -n -t xxx.jmx
```

#### 方式 3：使用 JMeter 属性文件

创建 `user.properties` 文件：
```properties
host=dkkguat-test.testdolphin.com
jwt-token=新的token值
```

执行时加载：
```bash
jmeter -p user.properties -n -t xxx.jmx
```

## 测试数据管理

### 识别测试数据

生成的测试数据使用 `AUTO` 前缀，便于识别：
- 起降场名称：`AUTO起降场...`
- 无人机编码：`UAV...`

### 清理测试数据

#### 方式 1：通过接口清理

使用 `查询 -> 删除` 的流程清理：
1. 调用查询接口获取测试数据 ID
2. 调用删除接口删除数据

#### 方式 2：数据库清理

直接操作数据库清理（需要数据库权限）：
```sql
-- 示例：清理起降场测试数据
DELETE FROM landing_site WHERE site_name LIKE 'AUTO%';
```

### 避免数据冲突

1. **使用唯一标识**：测试数据包含时间戳和随机字符
2. **分环境测试**：不同环境使用不同的数据库
3. **定时清理**：设置定时任务清理过期数据

## 常见问题

### Q1: JMeter 无法打开 JMX 文件

**现象：** JMeter 报错或无法识别文件

**解决：**
1. 检查 JMX 文件是否为有效的 XML 格式
2. 确保 JMeter 版本为 5.0+
3. 检查文件编码是否为 UTF-8

### Q2: 接口返回 401 未授权

**现象：** 所有请求返回 401 状态码

**解决：**
1. 更新 `jwt-token` 变量为有效的认证令牌
2. 检查 token 是否过期
3. 确认 token 格式正确（包含 Bearer 前缀如果需要）

### Q3: 接口返回 404 未找到

**现象：** 请求返回 404 状态码

**解决：**
1. 检查 `host` 和 `basePath` 变量是否正确
2. 确认测试环境服务已启动
3. 检查接口路径是否正确

### Q4: 生成的数据重复导致失败

**现象：** 第二次执行时某些接口失败

**解决：**
1. 清理之前的测试数据
2. 检查数据唯一性约束
3. 使用更精确的时间戳格式

### Q5: 如何添加自定义断言

**解决：**
1. 在 JMeter GUI 中打开 JMX 文件
2. 找到需要添加断言的请求
3. 右键 -> 添加 -> 断言 -> JSON Path Assertion
4. 配置断言规则
5. 保存 JMX 文件

## 最佳实践

### 测试计划组织

1. **按场景执行**：一次执行一个场景的测试用例
2. **分优先级测试**：优先测试 P0 场景
3. **环境隔离**：不同环境使用不同的 JMX 文件

### 数据管理

1. **定期清理**：测试后及时清理测试数据
2. **数据备份**：重要测试数据提前备份
3. **唯一标识**：使用 AUTO 前缀便于识别

### 性能测试

1. **使用非 GUI 模式**：性能测试使用 `-n` 参数
2. **禁用监听器**：生产环境禁用 ViewResultsTree
3. **合理设置线程数**：根据服务器性能设置

### 持续集成

1. **自动化执行**：将 JMeter 测试集成到 CI/CD 流程
2. **结果分析**：自动生成测试报告
3. **失败通知**：测试失败时发送通知

## 进阶用法

### 自定义测试数据生成

修改 `swagger_to_jmx_generator_v2.py` 中的 `TestDataGenerator` 类：

```python
class TestDataGenerator:
    DATA_TEMPLATES = {
        'your_custom_data': '"PREFIX_${__time(MMddHHmmss)}"',
        # ...
    }
```

### 添加自定义场景

在 `SCENE_DEFINITIONS` 中添加新场景：

```python
SCENE_DEFINITIONS = [
    {
        'id': '99',
        'name': '自定义场景',
        'priority': 'P1',
        'system': 'biz',
        'tags': ['自定义标签'],
        'description': '场景描述'
    },
    # ...
]
```

### 集成到测试平台

```python
import subprocess

# 生成测试用例
subprocess.run(['python', 'swagger_to_jmx_generator_v2.py', 'sit', 'P0'])

# 执行测试
subprocess.run([
    'jmeter', '-n', '-t', '接口测试用例jmx/01_起降场管理场景_sit.jmx',
    '-l', 'results/result.jtl'
])

# 解析结果
# ...
```
