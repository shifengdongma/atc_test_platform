# 代码质量标准知识库

> 版本: 1.0 | 更新日期: 2026-04-14

## 1. 代码可读性

### 命名规范 (NAMING)

| 规则ID | 严重程度 | 检查要点 | 示例 |
|--------|---------|---------|------|
| NAME-001 | 🟢 Medium | 变量名有意义 | ✅ `user_count` ❌ `uc` |
| NAME-002 | 🟢 Medium | 函数名使用动词开头 | ✅ `get_user_by_id` |
| NAME-003 | 🟢 Medium | 类名使用名词，大驼峰 | ✅ `UserService` |
| NAME-004 | 🔵 Low | 常量使用全大写 | ✅ `MAX_RETRY_COUNT` |

### 代码组织 (ORG)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| ORG-001 | 🟢 Medium | 函数长度不超过50行 |
| ORG-002 | 🟢 Medium | 类长度不超过300行 |
| ORG-003 | 🟢 Medium | 文件长度不超过500行 |
| ORG-004 | 🔵 Low | 避免深层嵌套（不超过4层） |

## 2. 代码复杂度

### 圈复杂度 (CYCLO)

| 规则ID | 严重程度 | 检查要点 | 阈值 |
|--------|---------|---------|------|
| CYCLO-001 | 🟡 High | 函数圈复杂度过高 | <= 10 |
| CYCLO-002 | 🟢 Medium | 条件分支过多 | <= 5 |

**圈复杂度计算：**
- 1 + 条件语句数(if/while/for/and/or)

**优化示例：**
```python
# ❌ 圈复杂度 = 5
def process_order(order):
    if order.status == 'pending':
        if order.payment_method == 'card':
            if order.amount > 1000:
                return process_large_card_order(order)
            else:
                return process_small_card_order(order)
        elif order.payment_method == 'cash':
            return process_cash_order(order)
    elif order.status == 'completed':
        return process_completed_order(order)

# ✅ 优化后：使用策略模式
ORDER_PROCESSORS = {
    ('pending', 'card', 'large'): process_large_card_order,
    ('pending', 'card', 'small'): process_small_card_order,
    ('pending', 'cash', None): process_cash_order,
    ('completed', None, None): process_completed_order,
}

def process_order(order):
    key = (order.status, order.payment_method, get_size(order.amount))
    processor = ORDER_PROCESSORS.get(key)
    if processor:
        return processor(order)
```

### 认知复杂度 (COGNITIVE)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| COG-001 | 🟢 Medium | 嵌套条件难以阅读 |
| COG-002 | 🟢 Medium | 魔法数字未命名 |

## 3. 代码重复 (DRY)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| DRY-001 | 🟡 High | 代码块重复（超过3行） |
| DRY-002 | 🟢 Medium | 相似逻辑未抽象 |
| DRY-003 | 🔵 Low | 硬编码字符串重复 |

## 4. 注释与文档

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| DOC-001 | 🟢 Medium | 公共API缺少文档字符串 |
| DOC-002 | 🔵 Low | 复杂逻辑缺少注释 |
| DOC-003 | 🔵 Low | 注释与代码不同步 |

**文档字符串规范：**
```python
def calculate_discount(price, discount_rate, user_type):
    """
    计算折扣后价格。
    
    Args:
        price (float): 原始价格，必须大于0
        discount_rate (float): 折扣率，范围0-1
        user_type (str): 用户类型 ('vip', 'normal', 'new')
    
    Returns:
        float: 折扣后价格
    
    Raises:
        ValueError: 价格或折扣率无效
    
    Example:
        >>> calculate_discount(100, 0.8, 'vip')
        80.0
    """
```

## 5. 错误处理

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| ERR-001 | 🟡 High | 空try-except块 |
| ERR-002 | 🟡 High | 捕获所有异常不处理 |
| ERR-003 | 🟢 Medium | 异常信息不明确 |
| ERR-004 | 🟢 Medium | 资源未正确释放 |

**错误处理示例：**
```python
# ❌ 错误：空except块
try:
    process_data()
except:
    pass

# ❌ 错误：捕获所有异常
try:
    process_data()
except Exception as e:
    logger.error(e)

# ✅ 正确：精确捕获，正确处理
try:
    process_data()
except DataValidationError as e:
    logger.warning(f"数据验证失败: {e}")
    raise BusinessError("输入数据有误") from e
except DatabaseError as e:
    logger.error(f"数据库错误: {e}")
    raise ServiceUnavailable() from e
finally:
    connection.close()
```

## 6. 测试覆盖

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| TEST-001 | 🟡 High | 核心逻辑缺少单元测试 |
| TEST-002 | 🟢 Medium | 边界条件未测试 |
| TEST-003 | 🟢 Medium | 异常分支未测试 |

## 代码质量检查清单

```markdown
□ 可读性
  □ 命名清晰有意义
  □ 函数长度适中
  □ 无深层嵌套

□ 复杂度
  □ 圈复杂度 <= 10
  □ 条件分支清晰
  □ 无魔法数字

□ 重复代码
  □ 无重复代码块
  □ 相似逻辑已抽象

□ 文档
  □ 公共API有文档
  □ 复杂逻辑有注释

□ 错误处理
  □ 异常处理完善
  □ 资源正确释放

□ 测试
  □ 核心逻辑有测试
  □ 边界条件覆盖
```
