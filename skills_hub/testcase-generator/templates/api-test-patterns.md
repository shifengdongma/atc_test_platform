# 接口测试模式知识库

> 版本: 1.0 | 更新日期: 2026-04-14

## 1. 接口测试分层模型

```
┌─────────────────────────────────────────┐
│           业务场景层 (E2E)               │
│    完整业务流程验证（多接口串联）         │
├─────────────────────────────────────────┤
│           接口契约层 (Contract)          │
│    单接口功能验证（入参、出参、状态）      │
├─────────────────────────────────────────┤
│           协议规范层 (Protocol)          │
│    HTTP协议验证（方法、头部、状态码）      │
├─────────────────────────────────────────┤
│           数据持久层 (Persistence)       │
│    数据验证（数据库、缓存、消息队列）       │
└─────────────────────────────────────────┘
```

## 2. 接口测试检查清单

### 2.1 请求参数测试

| 检查项 | 测试点 | 示例 |
|--------|--------|------|
| **必填参数** | 缺少必填参数 | 不传username |
| | 必填参数为空 | `username: ""` |
| | 必填参数为null | `username: null` |
| **参数类型** | 类型错误 | 字符串传数字 |
| | 类型边界 | 极大整数、极小整数 |
| **参数长度** | 超过最大长度 | 用户名传100字符 |
| | 恰好最大长度 | 用户名传20字符 |
| | 低于最小长度 | 用户名传1字符 |
| **参数格式** | 格式错误 | 邮箱无@符号 |
| | 特殊字符 | 包含`<script>` |
| **参数取值** | 枚举值之外 | 状态传无效值 |
| | 边界枚举值 | 第一个、最后一个枚举 |

### 2.2 响应结果测试

| 检查项 | 测试点 | 验证内容 |
|--------|--------|----------|
| **响应状态码** | 2xx成功 | 200, 201, 204 |
| | 4xx客户端错误 | 400, 401, 403, 404 |
| | 5xx服务端错误 | 500, 502, 503 |
| **响应格式** | JSON格式 | 结构正确 |
| | 字段完整 | 无缺失字段 |
| | 字段类型 | 类型匹配 |
| **响应数据** | 正确数据 | 业务数据准确 |
| | 错误信息 | 提示清晰友好 |
| | 敏感信息 | 无密码、密钥 |

### 2.3 业务规则测试

| 检查项 | 测试点 | 示例 |
|--------|--------|------|
| **前置条件** | 条件不满足 | 未登录访问需授权接口 |
| **状态约束** | 非法状态操作 | 已取消订单再次取消 |
| **数据一致性** | 关联数据验证 | 创建订单后库存减少 |
| **幂等性** | 重复请求 | 同一请求多次提交 |

### 2.4 安全测试

| 检查项 | 测试点 | 示例 |
|--------|--------|------|
| **认证** | 无Token访问 | 未传Authorization |
| | 无效Token | Token过期、伪造 |
| | 权限不足 | 普通用户访问管理员接口 |
| **注入攻击** | SQL注入 | `' OR 1=1 --` |
| | 命令注入 | `; rm -rf /` |
| **越权访问** | 水平越权 | 访问他人数据 |
| | 垂直越权 | 提升权限操作 |

## 3. HTTP方法测试模式

### 3.1 GET 请求

```yaml
test_patterns:
  - name: "正常查询"
    description: "带有效参数查询"
    
  - name: "空结果"
    description: "查询条件无匹配数据"
    
  - name: "参数缺失"
    description: "缺少必要查询参数"
    
  - name: "分页测试"
    description: "验证分页参数"
    test_points:
      - "page=1, size=10"
      - "page=0"  # 边界
      - "page=-1"  # 无效
      - "size=最大值"
      - "size=超过最大值"
      
  - name: "排序测试"
    description: "验证排序参数"
    test_points:
      - "sort=asc"
      - "sort=desc"
      - "sort=无效字段"
```

### 3.2 POST 请求

```yaml
test_patterns:
  - name: "正常创建"
    description: "提交有效数据创建资源"
    
  - name: "重复创建"
    description: "重复提交相同数据"
    expected: "幂等处理或拒绝重复"
    
  - name: "字段缺失"
    description: "缺少必填字段"
    
  - name: "字段超长"
    description: "字段值超过最大长度"
    
  - name: "关联资源不存在"
    description: "引用的外键资源不存在"
```

### 3.3 PUT/PATCH 请求

```yaml
test_patterns:
  - name: "正常更新"
    description: "更新已有资源"
    
  - name: "更新不存在资源"
    description: "资源ID不存在"
    expected: "返回404"
    
  - name: "部分更新"
    description: "PATCH只传部分字段"
    expected: "未传字段保持不变"
    
  - name: "并发更新"
    description: "同时更新同一资源"
    expected: "有并发控制机制"
```

### 3.4 DELETE 请求

```yaml
test_patterns:
  - name: "正常删除"
    description: "删除已有资源"
    
  - name: "删除不存在资源"
    description: "资源ID不存在"
    expected: "返回404或幂等成功"
    
  - name: "删除已删除资源"
    description: "资源已被删除"
    expected: "幂等处理"
    
  - name: "删除被引用资源"
    description: "资源被其他数据引用"
    expected: "返回409或级联删除"
```

## 4. 接口测试用例模板

### 4.1 单接口测试用例

```yaml
# 接口信息
api:
  path: "/api/v1/users"
  method: "POST"
  description: "创建用户"

# 测试用例
test_cases:
  - id: "TC-API-USER-001"
    title: "创建用户-正常流程"
    priority: P0
    type: 接口测试
    
    preconditions:
      - 数据库连接正常
      - 用户表无同名用户
    
    request:
      headers:
        Content-Type: "application/json"
        Authorization: "Bearer {valid_token}"
      body:
        username: "testuser"
        email: "test@example.com"
        password: "Test@123"
    
    expected:
      status_code: 201
      response_body:
        id: "{generated_id}"
        username: "testuser"
        email: "test@example.com"
        created_at: "{timestamp}"
      database:
        - table: "users"
          action: "insert"
          data:
            username: "testuser"
    
    cleanup:
      - "DELETE FROM users WHERE username='testuser'"

  - id: "TC-API-USER-002"
    title: "创建用户-用户名已存在"
    priority: P1
    type: 接口测试
    
    preconditions:
      - 数据库已存在用户名为"existinguser"的用户
    
    request:
      body:
        username: "existinguser"
        email: "new@example.com"
        password: "Test@123"
    
    expected:
      status_code: 409
      response_body:
        error_code: "USER_EXISTS"
        message: "用户名已存在"
```

### 4.2 接口流程测试

```yaml
# 业务流程：登录 -> 获取用户信息 -> 更新信息
flow_test:
  name: "用户完整操作流程"
  
  steps:
    - step: 1
      name: "用户登录"
      api:
        path: "/api/v1/auth/login"
        method: "POST"
      request:
        body:
          username: "testuser"
          password: "Test@123"
      extract:
        - name: "token"
          path: "$.data.token"
      
    - step: 2
      name: "获取用户信息"
      api:
        path: "/api/v1/users/me"
        method: "GET"
      request:
        headers:
          Authorization: "Bearer {{token}}"
      extract:
        - name: "user_id"
          path: "$.data.id"
      
    - step: 3
      name: "更新用户信息"
      api:
        path: "/api/v1/users/{{user_id}}"
        method: "PUT"
      request:
        headers:
          Authorization: "Bearer {{token}}"
        body:
          nickname: "新昵称"
```

## 5. 错误码规范

### 5.1 HTTP状态码

| 状态码 | 含义 | 使用场景 |
|--------|------|----------|
| 200 | OK | GET、PUT、PATCH成功 |
| 201 | Created | POST创建成功 |
| 204 | No Content | DELETE成功 |
| 400 | Bad Request | 请求参数错误 |
| 401 | Unauthorized | 未认证 |
| 403 | Forbidden | 无权限 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突 |
| 422 | Unprocessable | 业务规则校验失败 |
| 429 | Too Many Requests | 限流 |
| 500 | Internal Error | 服务器内部错误 |

### 5.2 业务错误码

```yaml
error_codes:
  USER:
    - code: "USER_NOT_FOUND"
      message: "用户不存在"
      http_status: 404
    - code: "USER_EXISTS"
      message: "用户已存在"
      http_status: 409
    - code: "USER_DISABLED"
      message: "用户已被禁用"
      http_status: 403
      
  AUTH:
    - code: "INVALID_CREDENTIALS"
      message: "用户名或密码错误"
      http_status: 401
    - code: "TOKEN_EXPIRED"
      message: "登录已过期"
      http_status: 401
    - code: "INSUFFICIENT_PERMISSIONS"
      message: "权限不足"
      http_status: 403
      
  VALIDATION:
    - code: "INVALID_PARAMETER"
      message: "参数格式错误"
      http_status: 400
    - code: "MISSING_PARAMETER"
      message: "缺少必要参数"
      http_status: 400
```

## 6. 接口测试工具推荐

| 工具 | 用途 | 特点 |
|------|------|------|
| Postman | 手动测试 | 图形界面，易用 |
| JMeter | 性能测试 | 支持高并发 |
| REST Assured | 自动化测试 | Java生态 |
| pytest + requests | 自动化测试 | Python生态 |
| Hoppscotch | 手动测试 | 开源，轻量 |

## 7. 接口测试检查清单

```markdown
□ 请求参数
  □ 必填参数验证
  □ 参数类型验证
  □ 参数长度验证
  □ 参数格式验证
  □ 特殊字符处理

□ 响应验证
  □ 状态码正确
  □ 响应格式正确
  □ 字段类型正确
  □ 敏感信息过滤

□ 业务逻辑
  □ 正常流程
  □ 异常流程
  □ 边界条件
  □ 幂等性

□ 安全
  □ 认证验证
  □ 权限验证
  □ 注入攻击防护
  □ 越权访问防护

□ 性能
  □ 响应时间
  □ 并发处理
  □ 大数据量处理
```
