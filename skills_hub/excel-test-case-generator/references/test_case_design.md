# Test Case Design Guide

## Table of Contents

1. [Test Case Design Principles](#test-case-design-principles)
2. [Test Scenario Identification](#test-scenario-identification)
3. [Test Case Patterns](#test-case-patterns)
4. [Coverage Strategies](#coverage-strategies)
5. [Common Testing Scenarios](#common-testing-scenarios)
6. [Best Practices](#best-practices)

## Test Case Design Principles

### 1. Clear and Unambiguous

Each test case should have:
- **Clear objective**: What is being tested
- **Specific steps**: Detailed, executable actions
- **Defined expected results**: Measurable outcomes

### 2. Independent and Repeatable

- Test cases should not depend on execution order
- Each test case should be executable in isolation
- Results should be consistent across multiple runs

### 3. Complete and Traceable

- All steps necessary for execution should be included
- Test cases should map to requirements/user stories
- Maintain traceability matrix for coverage tracking

### 4. Maintainable

- Use consistent naming conventions
- Follow standard structure and format
- Document assumptions and dependencies

## Test Scenario Identification

### Requirement Analysis

When analyzing requirements, identify:

1. **Functional Requirements**
   - Core features and functionality
   - Business rules and validations
   - User workflows and interactions

2. **Non-Functional Requirements**
   - Performance criteria
   - Security requirements
   - Usability standards

3. **Constraints and Assumptions**
   - System limitations
   - Environmental dependencies
   - Data requirements

### Scenario Breakdown

Break down each requirement into:

- **Positive Scenarios**: Normal, expected user flows
- **Negative Scenarios**: Error handling, invalid inputs
- **Boundary Scenarios**: Edge cases, limits, boundaries
- **Integration Scenarios**: Interactions with other components

## Test Case Patterns

### Pattern 1: Positive Flow Testing

**Purpose**: Verify normal, expected functionality

**Structure**:
- Precondition: System in normal state
- Steps: Standard user workflow
- Expected: Successful completion

**Example**:
```
Name: 用户注册-正常注册流程
Preconditions: 系统正常运行，注册页面可访问
Steps:
  1. 打开注册页面
  2. 输入有效的用户名、邮箱、密码
  3. 确认密码
  4. 点击注册按钮
Expected Result: 注册成功，显示成功提示，用户已登录
Priority: P0
```

### Pattern 2: Negative Flow Testing

**Purpose**: Verify error handling and validation

**Structure**:
- Precondition: System in normal state
- Steps: Invalid input or incorrect operation
- Expected: Appropriate error message/behavior

**Example**:
```
Name: 用户注册-重复邮箱注册
Preconditions: 系统正常运行，邮箱已存在
Steps:
  1. 打开注册页面
  2. 输入已注册的邮箱地址
  3. 输入其他有效信息
  4. 点击注册按钮
Expected Result: 显示错误提示："该邮箱已被注册"
Priority: P1
```

### Pattern 3: Boundary Value Testing

**Purpose**: Test limits and boundaries

**Structure**:
- Precondition: System in normal state
- Steps: Input at boundary values (min, max, just inside/outside)
- Expected: Correct handling of boundary conditions

**Example**:
```
Name: 密码设置-最小长度验证
Preconditions: 系统正常运行，注册页面可访问
Steps:
  1. 打开注册页面
  2. 输入用户名和邮箱
  3. 输入密码长度为7个字符（最小要求8个字符）
  4. 点击注册按钮
Expected Result: 显示错误提示："密码长度至少8个字符"
Priority: P1
```

### Pattern 4: Business Rule Testing

**Purpose**: Verify business logic and rules

**Structure**:
- Precondition: System in specific state
- Steps: Operation that triggers business rule
- Expected: Rule correctly applied

**Example**:
```
Name: 订单结算-满减优惠规则
Preconditions: 用户已登录，购物车有商品，存在满100减10优惠活动
Steps:
  1. 添加商品到购物车，总金额为99元
  2. 进入结算页面
  3. 查看优惠信息
Expected Result: 不显示满减优惠
Steps (continued):
  4. 添加商品使总金额达到100元
  5. 查看优惠信息
Expected Result: 显示满减优惠10元，实际支付90元
Priority: P0
```

## Coverage Strategies

### Equivalence Partitioning

Group inputs into equivalent classes:
- **Valid inputs**: Test representative values from each valid class
- **Invalid inputs**: Test representative values from each invalid class

### Decision Table Testing

For complex business rules with multiple conditions:
- List all conditions and their possible values
- Create test cases for each combination
- Focus on critical combinations

### State Transition Testing

For systems with multiple states:
- Identify all states
- Map valid transitions
- Test each transition path
- Test invalid transitions

### Error Guessing

Based on experience, test:
- Common mistakes users might make
- System vulnerabilities
- Edge cases that might cause failures

## Common Testing Scenarios

### User Authentication

**Scenarios to cover**:
- Valid login credentials
- Invalid username
- Invalid password
- Empty fields
- Special characters in input
- SQL injection attempts
- Session timeout
- Remember me functionality
- Password reset flow

### Form Validation

**Scenarios to cover**:
- Required field validation
- Format validation (email, phone, date)
- Length validation (min/max)
- Special character handling
- XSS prevention
- CSRF protection

### Data Operations

**Scenarios to cover**:
- Create new record
- Read/View record
- Update existing record
- Delete record
- Bulk operations
- Search and filter
- Sorting
- Pagination

### File Operations

**Scenarios to cover**:
- File upload (valid types, sizes)
- File download
- File deletion
- Large file handling
- Invalid file types
- File size limits
- Concurrent file access

## Best Practices

### Test Case Naming

**Format**: `功能模块-测试场景-具体条件`

**Examples**:
- `用户登录-正常登录-有效账号密码`
- `用户登录-错误密码-密码错误`
- `订单创建-正常流程-单个商品`
- `订单创建-异常流程-库存不足`

### Test Steps Writing

1. **Be Specific**: Use exact UI element names, button labels
2. **Number Steps**: Sequential numbering (1, 2, 3...)
3. **Include Test Data**: Specify exact values when relevant
4. **One Action Per Step**: Keep steps atomic
5. **Include Verification**: Add verification points in steps

**Good Example**:
```
Steps:
1. 打开浏览器，访问 https://example.com/login
2. 在"用户名"输入框输入 "testuser"
3. 在"密码"输入框输入 "Test123!"
4. 点击"登录"按钮
5. 验证页面跳转到 https://example.com/dashboard
6. 验证页面右上角显示用户名 "testuser"
```

**Bad Example**:
```
Steps:
1. 登录系统
2. 检查结果
```

### Expected Results

**Guidelines**:
- Be specific about what should happen
- Include UI changes, messages, data updates
- Specify exact values when applicable
- Include both positive and negative outcomes

**Good Example**:
```
Expected Result:
- 显示成功提示消息："订单创建成功，订单号：ORD-20240119-001"
- 页面跳转到订单详情页
- 订单状态显示为"待支付"
- 订单金额显示为 ¥299.00
```

**Bad Example**:
```
Expected Result: 订单创建成功
```

### Priority Assignment

**P0 (High Priority)**:
- Core functionality
- Critical user flows
- Security features
- Data integrity
- Payment processing

**P1 (Medium Priority)**:
- Important features
- Common user scenarios
- Business-critical workflows
- Integration points

**P2 (Low Priority)**:
- Nice-to-have features
- Edge cases
- Minor enhancements
- Cosmetic issues

### Test Case Organization

**By Feature/Module**:
- Group related test cases together
- Use consistent naming within module
- Maintain feature-based test suites

**By Priority**:
- Organize for test execution planning
- Execute P0 cases first
- Ensure critical coverage early

**By Test Type**:
- Separate functional, integration, regression tests
- Maintain test type-specific suites

## Advanced Patterns

### Parameterized Test Cases

For similar test cases with different data:
- Create template test case
- Use data-driven approach
- Maintain test data separately

### Test Case Chaining

For complex workflows:
- Break into multiple test cases
- Define dependencies clearly
- Use preconditions to link cases

### Exploratory Testing Support

While maintaining structured test cases:
- Document exploratory paths
- Capture ad-hoc findings
- Convert findings to formal test cases
