# Postman Collection 格式说明

## Postman Collection v2.1 格式

Postman Collection 使用 JSON 格式，遵循 v2.1.0 schema。

## 基本结构

```json
{
  "info": {
    "name": "Collection Name",
    "description": "Collection description",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [],
  "variable": []
}
```

## Info 对象

```json
{
  "info": {
    "name": "API Test Cases",
    "description": "自动生成的 API 测试用例集合",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    "_postman_id": "optional-uuid"
  }
}
```

## Item 结构

Item 可以是请求或文件夹（包含子 items）。

### 请求 Item

```json
{
  "name": "GET /users",
  "request": {
    "method": "GET",
    "header": [],
    "url": {
      "raw": "{{base_url}}/users",
      "host": ["{{base_url}}"],
      "path": ["users"]
    }
  },
  "response": []
}
```

### 文件夹 Item（包含子请求）

```json
{
  "name": "GET /users",
  "item": [
    {
      "name": "正向用例 - 正常获取用户列表",
      "request": { ... }
    }
  ]
}
```

## Request 对象

### URL 对象

```json
{
  "url": {
    "raw": "{{base_url}}/users?page=1&limit=10",
    "protocol": "https",
    "host": ["{{base_url}}"],
    "path": ["users"],
    "query": [
      {
        "key": "page",
        "value": "1",
        "description": "页码"
      },
      {
        "key": "limit",
        "value": "10",
        "description": "每页数量"
      }
    ]
  }
}
```

### Header 数组

```json
{
  "header": [
    {
      "key": "Content-Type",
      "value": "application/json"
    },
    {
      "key": "Authorization",
      "value": "Bearer {{token}}"
    }
  ]
}
```

### Body 对象

#### JSON Body

```json
{
  "body": {
    "mode": "raw",
    "raw": "{\n  \"name\": \"test\",\n  \"email\": \"test@example.com\"\n}",
    "options": {
      "raw": {
        "language": "json"
      }
    }
  }
}
```

#### Form-data Body

```json
{
  "body": {
    "mode": "formdata",
    "formdata": [
      {
        "key": "name",
        "value": "test",
        "type": "text"
      }
    ]
  }
}
```

## Event 对象（测试脚本）

```json
{
  "event": [
    {
      "listen": "test",
      "script": {
        "exec": [
          "pm.test('状态码为 200', function () {",
          "    pm.response.to.have.status(200);",
          "});"
        ],
        "type": "text/javascript"
      }
    },
    {
      "listen": "prerequest",
      "script": {
        "exec": [
          "// 预请求脚本"
        ],
        "type": "text/javascript"
      }
    }
  ]
}
```

## Variable 对象（环境变量）

```json
{
  "variable": [
    {
      "key": "base_url",
      "value": "https://api.example.com",
      "type": "string"
    },
    {
      "key": "token",
      "value": "",
      "type": "string"
    }
  ]
}
```

## 完整示例

```json
{
  "info": {
    "name": "User API Test Cases",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "GET /users",
      "item": [
        {
          "name": "正向用例 - 正常获取用户列表",
          "request": {
            "method": "GET",
            "header": [],
            "url": {
              "raw": "{{base_url}}/users?page=1&limit=10",
              "host": ["{{base_url}}"],
              "path": ["users"],
              "query": [
                {
                  "key": "page",
                  "value": "1"
                },
                {
                  "key": "limit",
                  "value": "10"
                }
              ]
            }
          },
          "event": [
            {
              "listen": "test",
              "script": {
                "exec": [
                  "pm.test('状态码为 200', function () {",
                  "    pm.response.to.have.status(200);",
                  "});"
                ],
                "type": "text/javascript"
              }
            }
          ]
        }
      ]
    }
  ],
  "variable": [
    {
      "key": "base_url",
      "value": "https://api.example.com",
      "type": "string"
    }
  ]
}
```

## 测试脚本 API

### pm.test()
定义测试用例

```javascript
pm.test('测试名称', function () {
    // 测试逻辑
});
```

### pm.expect()
断言

```javascript
pm.expect(value).to.equal(expected);
pm.expect(value).to.be.above(min);
pm.expect(value).to.be.below(max);
pm.expect(value).to.include(substring);
```

### pm.response
响应对象

```javascript
pm.response.code          // 状态码
pm.response.responseTime  // 响应时间（毫秒）
pm.response.json()        // JSON 响应体
pm.response.text()        // 文本响应体
pm.response.headers       // 响应头
```

### pm.request
请求对象

```javascript
pm.request.url.toString()  // 请求 URL
pm.request.headers         // 请求头
pm.request.body            // 请求体
```

## 环境变量使用

在 URL、Header、Body 中使用 `{{variable_name}}` 引用变量：

```json
{
  "url": {
    "raw": "{{base_url}}/users"
  },
  "header": [
    {
      "key": "Authorization",
      "value": "Bearer {{token}}"
    }
  ]
}
```

## 最佳实践

1. **使用变量**：将基础 URL、认证 token 等提取为变量
2. **组织结构**：使用文件夹组织相关的请求
3. **命名规范**：使用清晰的命名，便于理解测试意图
4. **测试脚本**：为每个请求添加适当的测试脚本
5. **文档说明**：在 description 字段中添加说明
