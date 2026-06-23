---
name: api-test-case-generator
description: API 测试用例生成工具 - 根据 OpenAPI/Swagger 文档或 API 描述自动生成 Postman 测试集合。当用户需要为 REST API 创建测试用例、从 API 文档生成测试集合、或生成包含正向用例、负向用例、边界值用例和异常用例的完整测试套件时使用。支持 OpenAPI 3.0 和 Swagger 2.0 格式，输出 Postman Collection v2.1 格式的测试集合。
---

# API 测试用例生成工具

## 概述

本技能使 Claude 能够根据 OpenAPI/Swagger 文档或手动输入的 API 描述，自动生成包含完整测试场景的 Postman 测试集合。支持生成正向用例、负向用例、边界值用例和异常用例，帮助测试工程师快速创建全面的 API 测试套件。

## 快速开始

当用户请求生成 API 测试用例时，您应该：

1. **识别输入源**：确定用户提供的是 OpenAPI/Swagger 文档还是 API 描述
2. **解析 API 定义**：使用解析器提取端点、方法、参数等信息
3. **生成测试用例**：为每个端点生成完整的测试用例（正向、负向、边界值、异常）
4. **创建 Postman 集合**：生成 Postman Collection v2.1 格式的 JSON 文件
5. **提供文件给用户**：将生成的 .json 文件路径告知用户

## 使用生成器脚本

### 从 OpenAPI 文档生成

```python
from scripts.api_test_generator import APITestCaseGenerator

generator = APITestCaseGenerator()

# 从 OpenAPI 文档生成
collection = generator.generate_from_openapi("openapi.yaml")
generator.save_collection(collection, "api_test_collection.json")
```

### 从 API 描述生成

```python
from scripts.api_test_generator import APITestCaseGenerator

generator = APITestCaseGenerator()

# 手动定义 API
api_description = {
    "base_url": "https://api.example.com",
    "endpoints": [
        {
            "path": "/users",
            "method": "GET",
            "parameters": [
                {
                    "name": "page",
                    "in": "query",
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "default": 1
                },
                {
                    "name": "limit",
                    "in": "query",
                    "type": "integer",
                    "required": False,
                    "minimum": 1,
                    "maximum": 100,
                    "default": 10
                }
            ]
        }
    ]
}

collection = generator.generate_from_description(api_description)
generator.save_collection(collection, "api_test_collection.json")
```

## 测试用例生成规则

### 正向用例
- 正常参数请求
- 所有必需参数
- 可选参数使用默认值或典型值
- 验证成功响应（2xx 状态码）

### 负向用例
- 缺失必需参数
- 参数类型错误
- 参数格式错误
- 超出范围的值
- 验证错误响应（4xx/5xx 状态码）

### 边界值用例
- 字符串长度边界（最小/最大）
- 数值边界（最小值/最大值）
- 数组长度边界
- 验证边界值处理

### 异常用例
- 空值/null 值
- SQL 注入尝试
- XSS 攻击尝试
- 特殊字符注入
- 验证安全性和异常处理

## 工作流程

### 1. 分析 API 定义

识别 API 端点、HTTP 方法、参数类型和约束：
- 路径参数（path parameters）
- 查询参数（query parameters）
- 请求头（headers）
- 请求体（request body）
- 响应定义（responses）

### 2. 生成测试用例

为每个端点生成四类测试用例：
- **正向用例**：验证正常功能
- **负向用例**：验证错误处理
- **边界值用例**：验证边界条件
- **异常用例**：验证安全性和异常处理

### 3. 构建 Postman 集合

将测试用例组织为 Postman Collection 结构：
- 按端点分组
- 每个端点包含多个测试用例
- 包含测试脚本和断言
- 使用环境变量（base_url 等）

### 4. 输出文件

生成 Postman Collection v2.1 格式的 JSON 文件，可直接导入 Postman。

## 参考文档

**加载 [测试用例设计模式](./references/test_case_patterns.md) 获取详细的测试用例设计原则和最佳实践。**

**加载 [Postman 格式说明](./references/postman_format.md) 获取 Postman Collection 格式的详细说明。**

## 资源

### scripts/api_test_generator.py
主生成器类，提供：
- `generate_from_openapi()` - 从 OpenAPI 文档生成
- `generate_from_description()` - 从 API 描述生成
- `save_collection()` - 保存 Postman 集合

### scripts/openapi_parser.py
OpenAPI/Swagger 文档解析器，支持：
- OpenAPI 3.0 格式
- Swagger 2.0 格式
- 端点、参数、响应信息提取

### references/test_case_patterns.md
详细的测试用例设计模式，包括：
- 测试用例分类和设计原则
- 参数类型处理规则
- HTTP 方法特定测试
- 响应验证策略

### references/postman_format.md
Postman Collection 格式说明，包括：
- Collection 结构
- Request 对象格式
- 测试脚本编写
- 环境变量使用

## 使用示例

### 示例 1：从 OpenAPI 文档生成

用户提供 `openapi.yaml` 文件：

```yaml
openapi: 3.0.0
info:
  title: User API
  version: 1.0.0
servers:
  - url: https://api.example.com
paths:
  /users:
    get:
      parameters:
        - name: page
          in: query
          schema:
            type: integer
            minimum: 1
```

生成包含该端点所有测试用例的 Postman 集合。

### 示例 2：从描述生成

用户描述 API：
- GET /users?page=1&limit=10
- page: 整数，可选，最小值 1
- limit: 整数，可选，范围 1-100

自动生成包含正向、负向、边界值、异常用例的测试集合。

## 注意事项

1. **OpenAPI 文档格式**：支持 YAML 和 JSON 格式
2. **参数类型**：支持 string、integer、number、boolean、array、object
3. **测试脚本**：自动生成基本的响应验证脚本
4. **环境变量**：base_url 自动提取并设置为环境变量
5. **文件编码**：输出文件使用 UTF-8 编码
