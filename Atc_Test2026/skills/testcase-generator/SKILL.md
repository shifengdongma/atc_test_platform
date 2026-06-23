---
name: testcase-generator
description: 基于本地知识库生成测试用例，支持功能测试、接口测试、性能测试等多种类型。当用户需要根据需求生成测试用例、设计测试方案时使用。
---

# 测试用例生成器

基于本地知识库执行标准化的测试用例设计流程，支持从需求到测试用例的完整转换。

## 知识库结构

本技能使用以下知识库文件（位于 `templates/` 目录）：

| 知识库文件 | 用途 | 调用方式 |
|-----------|------|---------|
| `testcase-standards.md` | 测试用例设计规范 | @templates/testcase-standards.md |
| `atc-testcase-standards.md` | 低空空管系统测试用例规范 | @templates/atc-testcase-standards.md |
| `testcase-templates.yaml` | 测试用例结构模板 | @templates/testcase-templates.yaml |
| `boundary-analysis.md` | 边界值分析方法 | @templates/boundary-analysis.md |
| `equivalence-partition.md` | 等价类划分方法 | @templates/equivalence-partition.md |
| `scenario-design.md` | 场景设计方法 | @templates/scenario-design.md |
| `api-test-patterns.md` | 接口测试模式 | @templates/api-test-patterns.md |

## 使用方法

### 方式1：基于需求生成测试用例

```
请根据以下知识库，为以下需求生成测试用例：
- 测试规范：@templates/testcase-standards.md
- 边界分析：@templates/boundary-analysis.md
- 等价类划分：@templates/equivalence-partition.md

需求描述：
[粘贴需求]

输出要求：
1. 按功能点拆分测试用例
2. 包含正向、负向、边界场景
3. 使用标准测试用例格式
4. 标注优先级
```

### 方式2：接口测试用例生成

```
请根据 @templates/api-test-patterns.md 中的接口测试模式，为以下API生成测试用例：

API信息：
- 路径：/api/v1/users
- 方法：POST
- 参数：{name, email, age}
- 响应：{id, name, email, created_at}

要求：
1. 覆盖参数校验
2. 覆盖业务规则
3. 覆盖错误场景
```

### 方式3：场景化测试设计

```
请根据 @templates/scenario-design.md 的方法，设计以下业务流程的测试场景：

业务流程：用户下单 → 支付 → 发货 → 收货 → 评价

要求：
1. 主流程场景
2. 异常分支场景
3. 边界场景
```

## 测试用例输出格式

```yaml
test_cases:
  - id: "TC-{模块}-{序号}"
    title: "测试用例标题"
    priority: P0/P1/P2/P3
    type: 功能/接口/性能/兼容性/安全
    
    # 前置条件
    preconditions:
      - "前置条件1"
      - "前置条件2"
    
    # 测试数据
    test_data:
      input:
        field1: "value1"
        field2: "value2"
      expected:
        status: "success"
        data:
          field: "expected_value"
    
    # 测试步骤
    steps:
      - step: 1
        action: "执行操作"
        expected: "预期结果"
      - step: 2
        action: "执行操作"
        expected: "预期结果"
    
    # 测试场景标签
    tags:
      - "正向场景"
      - "边界值"
    
    # 关联信息
    traceability:
      requirement_id: "REQ-001"
      function_point_id: "FP-001.1"
```

## 测试用例设计原则

1. **MECE原则**：相互独立，完全穷尽
2. **正交覆盖**：每个维度至少一个测试点
3. **风险导向**：高风险功能优先覆盖
4. **可追溯性**：每个用例关联到需求

## 知识库扩展

如需添加自定义测试方法：
1. 在 `templates/` 目录创建新的 `.md` 文件
2. 定义测试方法和检查清单
3. 在生成用例时引用
