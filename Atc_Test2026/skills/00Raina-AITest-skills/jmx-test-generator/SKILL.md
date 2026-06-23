---
name: jmx-test-generator
description: JMX 测试脚本生成工具 - 根据 API 接口文档（OpenAPI/Swagger 或 Markdown 格式）自动生成 Apache JMeter 的 JMX 测试脚本。当用户需要为 REST API 创建 JMeter 性能测试脚本、从 API 文档生成 JMX 文件、或生成包含 HTTP 请求、断言、参数化和监听器的完整测试计划时使用。支持 OpenAPI 3.0 和 Swagger 2.0 格式，以及 Markdown 格式的 API 文档，输出标准的 JMX XML 格式文件。
---

# JMX 测试脚本生成工具

## 概述

本技能使 Claude 能够根据 API 接口文档（OpenAPI/Swagger 或 Markdown 格式）自动生成 Apache JMeter 的 JMX 测试脚本。支持生成包含 HTTP 请求、参数、断言、参数化、数据驱动、性能测试配置和监听器的完整测试计划。

## 快速开始

当用户请求生成 JMX 测试脚本时，您应该：

1. **识别输入源**：确定用户提供的是 OpenAPI/Swagger 文档还是 Markdown 格式的 API 文档
2. **解析 API 定义**：使用解析器提取端点、方法、参数等信息
3. **生成测试计划**：创建 JMeter 测试计划结构
4. **添加测试元素**：为每个端点添加 HTTP 请求、断言、监听器等
5. **保存 JMX 文件**：将生成的测试计划保存为 JMX 文件

## 使用生成器脚本

### 从 OpenAPI 文档生成

```python
from scripts.jmx_generator import JMXTestGenerator

generator = JMXTestGenerator()

# 从 OpenAPI 文档生成
xml = generator.generate_from_openapi(
    "openapi.yaml",
    test_plan_name="API Test Plan",
    num_threads=10,
    ramp_time=5,
    loops=1,
    add_listeners=True
)

# 保存为 JMX 文件
generator.save_jmx("test_plan.jmx")
```

### 从 Markdown 文档生成

```python
from scripts.jmx_generator import JMXTestGenerator

generator = JMXTestGenerator()

# 从 Markdown 文档生成
xml = generator.generate_from_markdown(
    "api_doc.md",
    test_plan_name="API Test Plan",
    num_threads=10,
    ramp_time=5,
    loops=1,
    add_listeners=True
)

# 保存为 JMX 文件
generator.save_jmx("test_plan.jmx")
```

## 支持的输入格式

### OpenAPI/Swagger 文档

- **OpenAPI 3.0**：YAML 或 JSON 格式
- **Swagger 2.0**：YAML 或 JSON 格式

支持的文档内容：
- API 端点定义
- HTTP 方法（GET、POST、PUT、DELETE 等）
- 请求参数（Query、Path、Header、Body）
- 响应定义
- 服务器地址

### Markdown API 文档

支持常见的 Markdown API 文档格式：

**格式1：**
```markdown
## 接口名称
**接口地址**:`/api/users`
**请求方式**:`GET`
```

**格式2：**
```markdown
### GET /api/users
```

**格式3：**
```markdown
## API 名称
**URL**: `/api/users`
**Method**: `GET`
```

## 生成的功能

### 基础功能

1. **HTTP 请求**
   - 支持所有 HTTP 方法（GET、POST、PUT、DELETE、PATCH 等）
   - 自动解析 URL（协议、域名、端口、路径）
   - 支持查询参数、路径参数
   - 支持请求体（JSON 格式）

2. **请求参数**
   - Query 参数自动添加到请求中
   - Path 参数自动替换到路径中
   - Header 参数（如 Content-Type）自动添加

3. **响应断言**
   - 响应状态码断言（默认期望 200）
   - JSON 路径断言（如果定义了响应 schema）

### 高级功能

1. **参数化**
   - 测试计划级别的用户定义变量
   - 支持在请求中使用 `${variable_name}` 引用变量

2. **性能测试配置**
   - 线程组配置（并发用户数、启动时间、循环次数）
   - 可配置的线程数和 Ramp-up 时间

3. **监听器**
   - 查看结果树（ViewResultsTree）
   - 聚合报告（SummaryReport）
   - 可根据需要添加更多监听器

4. **数据驱动**（可通过手动添加）
   - CSV 数据集配置
   - 支持从 CSV 文件读取测试数据

## 输出格式

生成的 JMX 文件是标准的 XML 格式，可以直接在 Apache JMeter 中打开和执行。

**文件结构：**
```
TestPlan
└── ThreadGroup (每个 API 端点一个线程组)
    └── HTTPSamplerProxy (HTTP 请求)
        ├── HeaderManager (请求头)
        ├── ResponseAssertion (响应断言)
        └── Listeners (监听器)
```

## 参考文档

**加载 [JMX 格式说明](./references/jmx_format.md) 获取详细的 JMX 文件格式和元素说明。**

**加载 [测试模式说明](./references/test_patterns.md) 获取测试用例生成规则和最佳实践。**

## 资源

### scripts/jmx_generator.py
主生成器类，提供：
- `generate_from_openapi()` - 从 OpenAPI 文档生成
- `generate_from_markdown()` - 从 Markdown 文档生成
- `save_jmx()` - 保存 JMX 文件

### scripts/openapi_parser.py
OpenAPI/Swagger 文档解析器，支持：
- OpenAPI 3.0 和 Swagger 2.0 格式
- 端点、参数、响应信息提取

### scripts/markdown_parser.py
Markdown API 文档解析器，支持：
- 多种 Markdown API 文档格式
- 自动提取接口信息

### scripts/jmx_builder.py
JMX XML 构建器，提供：
- `create_test_plan()` - 创建测试计划
- `add_thread_group()` - 添加线程组
- `add_http_request()` - 添加 HTTP 请求
- `add_response_assertion()` - 添加响应断言
- `add_json_path_assertion()` - 添加 JSON 路径断言
- `add_listener()` - 添加监听器
- `add_csv_data_set_config()` - 添加 CSV 数据集配置

### references/jmx_format.md
JMX 格式说明文档，包括：
- JMX 文件结构
- 主要元素说明
- 配置参数说明

### references/test_patterns.md
测试模式说明文档，包括：
- 测试用例类型（正向、负向、边界值、异常）
- 参数化模式
- 性能测试配置
- 断言模式
- 最佳实践

## 使用示例

### 示例 1：从 OpenAPI 文档生成基础测试脚本

```python
from scripts.jmx_generator import JMXTestGenerator

generator = JMXTestGenerator()
xml = generator.generate_from_openapi("openapi.yaml")
generator.save_jmx("api_test.jmx")
```

### 示例 2：生成性能测试脚本

```python
from scripts.jmx_generator import JMXTestGenerator

generator = JMXTestGenerator()
xml = generator.generate_from_openapi(
    "openapi.yaml",
    test_plan_name="Performance Test",
    num_threads=50,  # 50 个并发用户
    ramp_time=30,     # 30 秒启动
    loops=5,          # 每个用户执行 5 次
    add_listeners=True
)
generator.save_jmx("performance_test.jmx")
```

### 示例 3：从 Markdown 文档生成

```python
from scripts.jmx_generator import JMXTestGenerator

generator = JMXTestGenerator()
xml = generator.generate_from_markdown("api_doc.md")
generator.save_jmx("api_test.jmx")
```

## 注意事项

1. **JMeter 版本**：生成的 JMX 文件兼容 JMeter 5.0+ 版本
2. **依赖库**：需要安装 `pyyaml` 库用于解析 YAML 格式的 OpenAPI 文档（`pip install pyyaml`）
3. **文件路径**：确保 API 文档文件路径正确
4. **URL 解析**：如果 API 文档中没有服务器地址，将使用默认值（http://localhost:8080）
5. **请求体**：POST/PUT 请求的请求体需要根据 API 文档中的 schema 生成，如果没有示例数据，将生成基本结构
6. **断言**：默认添加响应状态码断言（期望 200），可根据需要手动添加更多断言
7. **监听器**：生产环境性能测试时建议禁用 ViewResultsTree 监听器以提高性能

## 后续操作

生成 JMX 文件后，您可以：

1. **在 JMeter 中打开**：使用 Apache JMeter GUI 打开生成的 JMX 文件
2. **自定义配置**：根据需要调整线程组、断言、监听器等配置
3. **添加数据驱动**：使用 CSV 数据集配置添加数据驱动测试
4. **执行测试**：在 JMeter 中运行测试计划
5. **分析结果**：使用监听器查看测试结果和性能指标
