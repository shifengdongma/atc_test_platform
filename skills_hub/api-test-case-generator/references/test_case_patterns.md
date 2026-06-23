# API 测试用例设计模式

## 概述

本文档描述了 REST API 测试用例的设计模式和最佳实践，用于指导自动生成全面的测试用例。

## 测试用例分类

### 1. 正向用例（Positive Cases）

正向用例验证 API 在正常情况下的行为。

#### 设计原则
- 使用有效的、符合规范的参数
- 包含所有必需参数
- 可选参数使用合理的默认值或典型值
- 验证成功响应（2xx 状态码）

#### 示例场景
- 正常创建资源（POST）
- 正常获取资源列表（GET）
- 正常更新资源（PUT/PATCH）
- 正常删除资源（DELETE）

### 2. 负向用例（Negative Cases）

负向用例验证 API 的错误处理能力。

#### 设计原则
- 缺失必需参数
- 参数类型错误
- 参数格式错误（如邮箱格式、日期格式）
- 超出允许范围的值
- 无效的认证信息

#### 常见场景
- 缺失必需参数 → 400 Bad Request
- 参数类型错误 → 400 Bad Request
- 未授权访问 → 401 Unauthorized
- 权限不足 → 403 Forbidden
- 资源不存在 → 404 Not Found
- 参数验证失败 → 422 Unprocessable Entity

### 3. 边界值用例（Boundary Cases）

边界值用例测试参数的边界条件。

#### 设计原则
- 字符串长度：最小长度、最大长度、最小长度-1、最大长度+1
- 数值范围：最小值、最大值、最小值-1、最大值+1
- 数组长度：空数组、单元素、最大长度
- 日期范围：最小日期、最大日期

#### 示例
- 字符串参数：minLength=1 → 测试 ""（空字符串）和 "a"（1个字符）
- 整数参数：minimum=1, maximum=100 → 测试 0, 1, 100, 101
- 数组参数：maxItems=10 → 测试 []（空数组）、[1]（1个元素）、[1..10]（10个元素）

### 4. 异常用例（Exception Cases）

异常用例测试安全性和异常情况处理。

#### 设计原则
- 空值/null 值
- 特殊字符注入（SQL 注入、XSS、命令注入）
- 超长字符串
- 特殊 Unicode 字符
- 格式错误的 JSON

#### 安全测试场景
- SQL 注入：`1' OR '1'='1`
- XSS 攻击：`<script>alert('XSS')</script>`
- 命令注入：`; rm -rf /`
- 路径遍历：`../../../etc/passwd`

## 参数类型处理

### 字符串（string）
- 正向：有效字符串
- 负向：类型错误（数字、布尔值）
- 边界：空字符串、最小长度、最大长度
- 异常：超长字符串、特殊字符

### 整数（integer）
- 正向：有效整数
- 负向：类型错误（字符串、浮点数）
- 边界：最小值、最大值、最小值-1、最大值+1
- 异常：负数（如果只允许正数）、零（如果不允许）

### 数字（number）
- 正向：有效数字
- 负向：类型错误（字符串、布尔值）
- 边界：最小值、最大值
- 异常：NaN、Infinity

### 布尔值（boolean）
- 正向：true、false
- 负向：类型错误（字符串、数字）

### 数组（array）
- 正向：有效数组
- 负向：类型错误（对象、字符串）
- 边界：空数组、单元素、最大长度
- 异常：超长数组

### 对象（object）
- 正向：有效对象
- 负向：类型错误（数组、字符串）
- 边界：空对象、必需字段缺失

## HTTP 方法特定测试

### GET
- 查询参数测试
- 分页参数测试
- 排序参数测试
- 过滤参数测试

### POST
- 请求体验证
- 必需字段验证
- 字段类型验证
- 创建资源验证

### PUT
- 完整更新验证
- 必需字段验证
- 资源不存在处理

### PATCH
- 部分更新验证
- 可选字段更新

### DELETE
- 资源删除验证
- 资源不存在处理
- 级联删除验证

## 响应验证

### 状态码验证
- 2xx：成功响应
- 4xx：客户端错误
- 5xx：服务器错误

### 响应体验证
- JSON 格式验证
- 必需字段存在
- 字段类型正确
- 字段值符合预期

### 响应头验证
- Content-Type
- 自定义头部
- 缓存头部

### 性能验证
- 响应时间
- 吞吐量
- 并发处理

## 测试脚本模板

### 成功响应验证
```javascript
pm.test('状态码为 200', function () {
    pm.response.to.have.status(200);
});

pm.test('响应时间小于 2000ms', function () {
    pm.expect(pm.response.responseTime).to.be.below(2000);
});

pm.test('响应包含 JSON', function () {
    pm.response.to.be.json;
});

pm.test('响应包含必需字段', function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('id');
    pm.expect(jsonData).to.have.property('name');
});
```

### 错误响应验证
```javascript
pm.test('状态码为 400', function () {
    pm.response.to.have.status(400);
});

pm.test('响应包含错误信息', function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('error');
    pm.expect(jsonData).to.have.property('message');
});
```

## 最佳实践

1. **覆盖全面**：确保覆盖正向、负向、边界值、异常场景
2. **独立性**：每个测试用例应该独立，不依赖其他用例的执行顺序
3. **可维护性**：使用清晰的命名和描述
4. **可读性**：测试用例名称应该清楚表达测试意图
5. **自动化**：尽可能自动化测试执行和验证
