---
name: atc-jmx-test-generator
description: 低空空管系统接口测试用例生成器 - 根据 Swagger/OpenAPI 文档自动生成 KTP (MeterSphere) 平台格式的 JSON 测试用例或 Apache JMeter 的 JMX 测试脚本。专门针对低空空管自动化系统和低空运维系统的接口特点设计，支持场景化测试组织、环境配置管理、动态测试数据生成。当用户需要为低空空管系统创建接口测试用例、从 Swagger 文档生成测试文件、或生成包含事务控制器、断言、参数化的完整测试计划时使用。支持 Swagger 2.0 格式，输出 KTP JSON 格式（推荐）或 JMX XML 格式文件。
---

# 低空空管系统接口测试用例生成器

## 概述

本技能使 Claude 能够根据低空空管系统的 Swagger API 文档自动生成 KTP (MeterSphere) 平台格式的 JSON 测试用例或 Apache JMeter 的 JMX 接口测试脚本。专门针对低空空管自动化系统（la-atc-biz-backend）和低空运维系统（la-atc-ops-server）的接口特点设计，支持：

- **双格式输出** - 支持 KTP JSON 格式（推荐）和 JMX XML 格式
- **场景化测试组织** - 按业务流程组织接口（起降场管理、飞行计划、告警管理等）
- **环境配置管理** - 支持 SIT/UAT 环境切换，内置默认 JWT Token
- **动态测试数据生成** - 自动生成起降场编号、无人机编码、坐标等测试数据
- **事务控制器** - 按 HTTP 方法分组管理接口请求
- **完整断言** - 自动添加 status 和 code 的 JSON 路径断言

## 快速开始

### 生成 KTP 格式测试用例（推荐）

当用户请求生成 KTP 平台格式的测试用例时：

1. **确认 Swagger 文件** - 检查 `低空空管自动化系统swaggerApi0422.json` 是否存在
2. **运行 KTP 生成器** - 执行 `ktp_swagger_to_json_generator.py` 生成 JSON 文件
3. **验证生成结果** - 检查 `KTP自动化测试用例/` 目录下的输出文件
4. **导入 KTP 平台** - 将生成的 JSON 文件导入 MeterSphere/KTP 自动化测试平台

```bash
# 生成起降场场景的 KTP 测试用例
python ktp_swagger_to_json_generator.py --swagger "低空空管自动化系统swaggerApi0422.json" --output "KTP自动化测试用例" --scenario landing

# 生成所有场景的 KTP 测试用例
python ktp_swagger_to_json_generator.py --swagger "低空空管自动化系统swaggerApi0422.json" --output "KTP自动化测试用例" --scenario all
```

### 生成 JMX 格式测试用例

当用户请求生成 JMeter JMX 格式的测试用例时：

1. **确认 Swagger 文件** - 检查 Swagger JSON 文件是否存在
2. **运行 JMX 生成器** - 执行 `swagger_to_jmx_generator_v2.py` 生成 JMX 文件
3. **验证生成结果** - 检查 `接口测试用例jmx/` 目录下的输出文件
4. **提供使用说明** - 告知用户如何在 JMeter 中使用生成的文件

```bash
# 生成所有优先级的测试用例（默认）
python swagger_to_jmx_generator_v2.py

# 只生成 P0 优先级的核心场景
python swagger_to_jmx_generator_v2.py sit P0

# 生成 UAT 环境的测试用例
python swagger_to_jmx_generator_v2.py uat
```

## 使用生成器脚本

### 基本用法

```python
from swagger_to_jmx_generator_v2 import SwaggerParser, JMXGeneratorV2

# 解析 Swagger 文档
parser = SwaggerParser('低空空管自动化系统swaggerApi0422.json')
apis = parser.get_all_apis()

# 创建生成器
generator = JMXGeneratorV2(output_dir='接口测试用例jmx')

# 生成场景化测试用例
filepath = generator.generate_scene_jmx(
    scene_name='01_起降场管理场景',
    apis=apis[:6],  # 起降场相关接口
    base_path='/la-atc-biz-backend',
    env='sit',
    description='覆盖起降场的增删改查、状态切换等核心业务流程'
)
```

### 高级用法 - 自定义场景

```python
from swagger_to_jmx_generator_v2 import SwaggerParser, JMXGeneratorV2

# 解析两个系统的 Swagger 文档
biz_parser = SwaggerParser('低空空管自动化系统swaggerApi0422.json')
ops_parser = SwaggerParser('低空运维系统swaggerApi0422.json')

# 获取特定标签的 API
landing_apis = biz_parser.get_apis_by_tag('起降场管理')
receiver_apis = ops_parser.get_apis_by_tag('接收机管理')

# 创建生成器
generator = JMXGeneratorV2(output_dir='接口测试用例jmx')

# 生成自定义场景
filepath = generator.generate_scene_jmx(
    scene_name='自定义_起降场与接收机联动场景',
    apis=landing_apis + receiver_apis,
    base_path='/la-atc-biz-backend',
    env='sit'
)
```

## 支持的接口系统

### 低空空管自动化系统 (la-atc-biz-backend)

| 场景编号 | 场景名称 | 优先级 | 接口数量 | 说明 |
|---------|---------|--------|---------|------|
| 01 | 起降场管理场景 | P0 | 6 | 起降场的增删改查、状态切换 |
| 02 | 扇区管理场景 | P0 | 6 | 扇区配置、边界管理 |
| 03 | 航路航线管理场景 | P0 | 8 | 航线规划、航路点管理 |
| 04 | 空域管理场景 | P0 | 10 | 空域划分、使用申请 |
| 05 | 飞行计划管理场景 | P0 | 18 | 飞行计划申报、审批、变更 |
| 06 | 飞行任务管理场景 | P0 | 17 | 任务下发、执行监控 |
| 07 | 无人机管理场景 | P1 | 12 | 无人机注册、状态管理 |
| 08 | 告警管理场景 | P1 | 13 | 告警规则、通知处理 |
| 09 | 坐席管理场景 | P1 | 9 | 坐席配置、状态监控 |
| 10 | 用户权限管理场景 | P1 | 32 | 用户、角色、权限管理 |
| 11 | 态势大屏查询场景 | P2 | 24 | 实时监控数据查询 |
| 12 | 运营人管理场景 | P1 | 5 | 运营人信息、资质管理 |
| 13 | 操作日志查询场景 | P2 | 5 | 系统操作日志查询 |
| 14 | 接收机管理场景 | P1 | 5 | 接收机配置、状态监控 |
| 15 | 其他功能场景 | P3 | 26 | 其他辅助功能接口 |

### 低空运维系统 (la-atc-ops-server)

| 场景编号 | 场景名称 | 优先级 | 接口数量 | 说明 |
|---------|---------|--------|---------|------|
| 21 | 运维接收机管理场景 | P1 | 12 | 接收机运维管理 |
| 22 | 运维告警管理场景 | P1 | 3 | 运维告警处理 |
| 23 | 版本升级管理场景 | P2 | 6 | 系统版本管理 |
| 24 | 网络拓扑管理场景 | P2 | 12 | 网络设备管理 |
| 25 | 运维监控查询场景 | P2 | 6 | 运维数据监控 |
| 26 | 运维公共接口场景 | P3 | 7 | 运维通用接口 |

## 生成的功能

### 环境配置

每个生成的 JMX 文件包含完整的环境配置：

```xml
<!-- TestPlan 级别的用户定义变量 -->
<elementProp name="TestPlan.user_defined_variables">
  <collectionProp name="Arguments.arguments">
    <elementProp name="protocol">
      <stringProp>${__P(protocol,https)}</stringProp>
    </elementProp>
    <elementProp name="host">
      <stringProp>${__P(host,dkkgsit-test.testdolphin.com)}</stringProp>
    </elementProp>
    <elementProp name="port">
      <stringProp>${__P(port,443)}</stringProp>
    </elementProp>
    <elementProp name="basePath">
      <stringProp>${__P(basePath,/la-atc-biz-backend)}</stringProp>
    </elementProp>
    <elementProp name="jwt-token">
      <stringProp>${__P(jwt-token,eyJhbGciOiJSUzI1NiJ9...)}</stringProp>
    </elementProp>
  </collectionProp>
</elementProp>
```

**环境变量说明：**
- `protocol` - 协议（https/http）
- `host` - 服务器地址
- `port` - 端口号
- `basePath` - API 基础路径
- `jwt-token` - 认证令牌（默认从 KTP_1_Environments.json 提取）

### 动态测试数据生成

自动生成符合业务规则的测试数据：

| 数据类型 | 生成规则 | 示例 |
|---------|---------|------|
| 起降场名称 | AUTO起降场 + 时间戳 + 随机字符 | `AUTO起降场0422203840A1` |
| 起降场编号 | 时间戳 + 2位随机大写字母 | `042220AB` |
| 无人机编码 | UAV + 时间戳 + 4位随机数字 | `UAV04222038401234` |
| 坐标经度 | 121.132 + 3位随机数字 | `121.132456` |
| 坐标纬度 | 38.726 + 3位随机数字 | `38.726789` |
| 飞行任务名称 | FLIGHT_TASK_ + 时间戳 | `FLIGHT_TASK_0422203840` |
| 手机号码 | 1 + 随机位 + 9位随机数字 | `13812345678` |

### HTTP 请求配置

每个接口自动生成完整的 HTTP 请求配置：

```xml
<HTTPSamplerProxy>
  <!-- 服务器配置（使用变量） -->
  <stringProp name="HTTPSampler.domain">${host}</stringProp>
  <stringProp name="HTTPSampler.port">${port}</stringProp>
  <stringProp name="HTTPSampler.protocol">${protocol}</stringProp>
  <stringProp name="HTTPSampler.path">${basePath}/landingSite</stringProp>
  
  <!-- 请求方法 -->
  <stringProp name="HTTPSampler.method">POST</stringProp>
  
  <!-- 超时配置 -->
  <stringProp name="HTTPSampler.connect_timeout">60000</stringProp>
  <stringProp name="HTTPSampler.response_timeout">60000</stringProp>
  
  <!-- 请求体（JSON格式） -->
  <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
  <elementProp name="HTTPsampler.Arguments">
    <collectionProp name="Arguments.arguments">
      <elementProp name="">
        <stringProp name="Argument.value">{"siteName": "AUTO起降场..."}</stringProp>
      </elementProp>
    </collectionProp>
  </elementProp>
</HTTPSamplerProxy>
```

### HeaderManager

每个请求包含独立的 HeaderManager：

```xml
<HeaderManager testname="01_起降场管理场景_新增_HeaderManager">
  <collectionProp name="HeaderManager.headers">
    <elementProp name="Content-Type">
      <stringProp name="Header.name">Content-Type</stringProp>
      <stringProp name="Header.value">application/json</stringProp>
    </elementProp>
    <elementProp name="jwt-token">
      <stringProp name="Header.name">jwt-token</stringProp>
      <stringProp name="Header.value">${jwt-token}</stringProp>
    </elementProp>
  </collectionProp>
</HeaderManager>
```

### 响应断言

自动添加 JSON 路径断言：

```xml
<!-- status 断言 -->
<JSONPathAssertion testname="断言: status = 200">
  <stringProp name="JSON_PATH">$.status</stringProp>
  <stringProp name="EXPECTED_VALUE">200</stringProp>
  <boolProp name="JSONVALIDATION">true</boolProp>
</JSONPathAssertion>

<!-- code 断言 -->
<JSONPathAssertion testname="断言: code = 0">
  <stringProp name="JSON_PATH">$.code</stringProp>
  <stringProp name="EXPECTED_VALUE">0</stringProp>
  <boolProp name="JSONVALIDATION">true</boolProp>
</JSONPathAssertion>
```

### 事务控制器

按 HTTP 方法分组组织接口：

```xml
<TransactionController testname="POST请求组">
  <!-- POST /landingSite - 新增起降场 -->
  <!-- POST /landingSite/batch - 批量导入 -->
</TransactionController>

<TransactionController testname="GET请求组">
  <!-- GET /landingSite/page - 分页查询 -->
  <!-- GET /landingSite/{id} - 获取详情 -->
</TransactionController>
```

## 环境配置

### 预定义环境

生成器内置 SIT 和 UAT 环境配置：

```python
ENVIRONMENTS = {
    'sit': {
        'name': 'SIT测试环境',
        'protocol': 'https',
        'host': 'dkkgsit-test.testdolphin.com',
        'port': '443',
        'base_path_biz': '/la-atc-biz-backend',
        'base_path_ops': '/la-atc-ops-server',
        'description': '系统集成测试环境，用于接口功能验证'
    },
    'uat': {
        'name': 'UAT验收环境',
        'protocol': 'https',
        'host': 'dkkguat-test.testdolphin.com',
        'port': '443',
        'base_path_biz': '/la-atc-biz-backend',
        'base_path_ops': '/la-atc-ops-server',
        'description': '用户验收测试环境'
    }
}
```

### 切换环境

通过命令行参数切换环境：

```bash
# SIT 环境（默认）
python swagger_to_jmx_generator_v2.py sit

# UAT 环境
python swagger_to_jmx_generator_v2.py uat
```

或在 JMeter 中通过命令行覆盖：

```bash
# 切换主机
jmeter -Jhost=dkkguat-test.testdolphin.com -n -t 01_起降场管理场景_sit.jmx

# 更新 token
jmeter -Jjwt-token=新的token值 -n -t 01_起降场管理场景_sit.jmx

# 同时覆盖多个变量
jmeter -Jhost=dkkguat-test.testdolphin.com -JbasePath=/la-atc-biz-backend -Jjwt-token=xxx -n -t xxx.jmx
```

## 文件结构

```
低空空管接口自动化/
├── swagger_to_jmx_generator_v2.py         # JMX 生成器脚本
├── ktp_swagger_to_json_generator.py       # KTP JSON 生成器脚本（新增）
├── 低空空管自动化系统swaggerApi0422.json  # 空管系统 Swagger
├── 低空运维系统swaggerApi0422.json        # 运维系统 Swagger
├── 接口测试用例jmx/                       # 生成的 JMX 文件目录
│   ├── 01_起降场管理场景_sit.jmx
│   ├── 02_扇区管理场景_sit.jmx
│   ├── ...
│   └── 26_运维公共接口场景_sit.jmx
├── KTP自动化测试用例/                     # 生成的 KTP JSON 文件目录（新增）
│   ├── KTP_空域情报_起降场.json
│   └── ...
├── 用例demo/                              # 参考用例目录
│   ├── 空域情报_起降场.jmx               # 人工编写的参考用例
│   ├── KTP_1_Environments.json           # 环境配置参考
│   └── KTP_Scenario_低空空管自动化系统.json  # KTP 格式参考
├── 接口测试用例计划.md                    # 测试计划文档
└── SKILL.md                               # 本技能文档
```

## 参考文档

### 人工编写用例参考

**加载 [空域情报_起降场.jmx](./用例demo/空域情报_起降场.jmx) 获取人工编写的完整测试用例参考**，包含：
- 条件控制器（IfController）使用
- 循环控制器（ForeachController）使用
- JSON 提取器（JSONPostProcessor）配置
- 前置处理器（JSR223Sampler）使用
- 计数器（CounterConfig）配置
- 定时器（ConstantTimer）配置

### 环境配置参考

**加载 [KTP_1_Environments.json](./用例demo/KTP_1_Environments.json) 获取环境配置参考**，包含：
- JWT Token 格式
- 服务器配置信息
- 请求头配置

## 使用示例

### 示例 1：生成所有测试用例

```bash
python swagger_to_jmx_generator_v2.py
```

输出：
```
============================================================
低空空管系统接口测试用例生成器 V2
============================================================

生成: 01_起降场管理场景 [P0] - 包含 6 个接口
  -> 接口测试用例jmx\01_起降场管理场景_sit.jmx

生成: 02_扇区管理场景 [P0] - 包含 6 个接口
  -> 接口测试用例jmx\02_扇区管理场景_sit.jmx

...

============================================================
生成汇总
============================================================
总场景文件数: 21
按优先级统计:
  P0: 6 个场景
  P1: 8 个场景
  P2: 5 个场景
  P3: 2 个场景
```

### 示例 2：只生成核心场景（P0）

```bash
python swagger_to_jmx_generator_v2.py sit P0
```

生成 6 个 P0 优先级的核心场景文件。

### 示例 3：在 JMeter 中执行

```bash
# 非 GUI 模式执行
jmeter -n -t 接口测试用例jmx/01_起降场管理场景_sit.jmx -l result.jtl

# 生成 HTML 报告
jmeter -g result.jtl -o report/
```

## 注意事项

1. **JMeter 版本**：生成的 JMX 文件兼容 JMeter 5.0+ 版本
2. **文件编码**：输出文件使用 UTF-8 编码
3. **JWT Token**：默认 token 可能过期，执行前请更新为有效的认证令牌
4. **环境可访问性**：执行前确保测试环境可访问
5. **数据清理**：测试用例会创建测试数据，建议定期清理
6. **并发执行**：多个 JMX 文件同时执行时，注意避免数据冲突

## 后续操作

生成 JMX 文件后，您可以：

1. **在 JMeter GUI 中打开**：查看和编辑测试计划
2. **更新 JWT Token**：修改 User Defined Variables 中的 jwt-token
3. **调整线程配置**：根据测试需求修改 ThreadGroup 的线程数和循环次数
4. **添加监听器**：根据需要添加查看结果树、聚合报告等监听器
5. **执行测试**：使用 JMeter GUI 或命令行模式执行测试
6. **分析结果**：使用监听器查看测试结果和性能指标

## KTP 格式说明

### KTP JSON 格式特点

KTP (Kedacom Test Platform) 基于 MeterSphere 自动化测试平台，使用 JSON 格式存储测试场景。与 JMX 格式相比，KTP 格式具有以下优势：

| 特性 | KTP JSON | JMX XML |
|------|----------|---------|
| 可读性 | 高，结构化 JSON | 中，XML 嵌套 |
| 导入导出 | 支持平台直接导入 | 需通过 JMeter 打开 |
| 版本控制 | 易于 Git 管理 | 合并冲突较多 |
| 编辑方式 | 平台可视化编辑 | JMeter GUI 编辑 |
| 团队协作 | 支持多人协作 | 单人编辑为主 |

### KTP 文件结构

```json
{
  "data": [
    {
      "id": "场景唯一ID",
      "name": "场景名称",
      "scenarioDefinition": "JSON字符串，包含详细步骤",
      "stepTotal": 8,
      "useUrl": [{"method": "GET", "url": "/api/path"}],
      ...
    }
  ],
  "projectId": "项目ID",
  "version": "v1.24.0"
}
```

### 使用 KTP 生成器

```python
from ktp_swagger_to_json_generator import KTPSwaggerParser, KTPScenarioGenerator

# 解析 Swagger
parser = KTPSwaggerParser('低空空管自动化系统swaggerApi0422.json')
apis = parser.parse()

# 创建生成器
generator = KTPScenarioGenerator()

# 生成起降场场景
scenario = generator.generate_landing_site_scenario(apis)

# 保存为 JSON
import json
with open('KTP_空域情报_起降场.json', 'w', encoding='utf-8') as f:
    json.dump({"data": [scenario], "projectId": generator.PROJECT_ID, "version": "v1.24.0"}, f)
```

### 导入 KTP 平台

1. 登录 MeterSphere/KTP 自动化测试平台
2. 进入【接口测试】->【场景测试】
3. 点击【导入】按钮
4. 选择生成的 JSON 文件
5. 确认导入的场景和步骤

## 故障排除

### JMeter 无法打开 JMX 文件

**问题**：JMeter 报错 `ClassCastException: org.apache.jmeter.threads.ThreadGroup cannot be cast to org.apache.jorphan.collections.HashTree`

**解决**：确保 JMX 文件结构正确，ThreadGroup 必须位于根 hashTree 下，与 TestPlan 同级。

### 请求返回 401 未授权

**问题**：接口返回 401 状态码

**解决**：更新 User Defined Variables 中的 jwt-token 为有效的认证令牌。

### 请求返回 404 未找到

**问题**：接口返回 404 状态码

**解决**：检查 host 和 basePath 变量是否正确配置。

### KTP 导入失败

**问题**：导入 KTP 平台时提示格式错误

**解决**：
1. 检查 JSON 文件格式是否完整
2. 确认 `scenarioDefinition` 字段为有效的 JSON 字符串
3. 验证 `projectId` 和 `versionId` 与目标项目匹配
