# 性能优化规范知识库

> 版本: 1.0 | 更新日期: 2026-04-14

## 1. 数据库性能

### N+1查询问题 (NPLUS1)

| 规则ID | 严重程度 | 检查要点 | 优化方案 |
|--------|---------|---------|---------|
| DB-001 | 🟡 High | 循环内执行数据库查询 | 使用JOIN或预加载 |
| DB-002 | 🟡 High | ORM懒加载在循环中触发 | 使用select_related/prefetch_related |

**问题代码示例：**
```python
# ❌ 错误：N+1查询
users = User.objects.all()
for user in users:
    print(user.profile.bio)  # 每次循环都查询profile表

# ✅ 正确：预加载
users = User.objects.select_related('profile').all()
for user in users:
    print(user.profile.bio)
```

### 查询优化 (QUERY)

| 规则ID | 严重程度 | 检查要点 | 优化方案 |
|--------|---------|---------|---------|
| DB-003 | 🟡 High | 查询未使用索引的字段 | 添加索引或优化查询条件 |
| DB-004 | 🟢 Medium | SELECT * 查询大量字段 | 只查询需要的字段 |
| DB-005 | 🟢 Medium | 大数据量查询未分页 | 添加分页限制 |
| DB-006 | 🟢 Medium | 缺少查询结果缓存 | 对热点数据添加缓存 |

## 2. 循环与算法

### 循环优化 (LOOP)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| LOOP-001 | 🟡 High | 循环内包含耗时操作（IO、网络请求） |
| LOOP-002 | 🟢 Medium | 循环内创建不必要的对象 |
| LOOP-003 | 🟢 Medium | 可使用集合操作却使用循环 |

**优化示例：**
```python
# ❌ 错误：循环内查询数据库
for user_id in user_ids:
    user = User.objects.get(id=user_id)  # N次查询

# ✅ 正确：批量查询
users = User.objects.filter(id__in=user_ids)  # 1次查询

# ❌ 错误：低效查找
if item in large_list:  # O(n)

# ✅ 正确：使用集合
if item in large_set:  # O(1)
```

### 算法复杂度 (ALGO)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| ALGO-001 | 🟡 High | 嵌套循环导致高时间复杂度 |
| ALGO-002 | 🟢 Medium | 可使用更高效的数据结构 |

## 3. 内存管理

### 内存泄漏 (MEMORY)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| MEM-001 | 🟡 High | 大对象未释放引用 |
| MEM-002 | 🟢 Medium | 缓存未设置过期时间 |
| MEM-003 | 🟢 Medium | 循环内累积大量数据 |

### 大数据处理 (BIGDATA)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| DATA-001 | 🟡 High | 一次性加载大文件到内存 |
| DATA-002 | 🟢 Medium | 未使用生成器处理大数据流 |

**优化示例：**
```python
# ❌ 错误：一次性加载
with open('large_file.txt') as f:
    lines = f.readlines()  # 占用大量内存

# ✅ 正确：逐行处理
with open('large_file.txt') as f:
    for line in f:  # 迭代器，低内存占用
        process(line)
```

## 4. 并发与异步

### 异步优化 (ASYNC)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| ASYNC-001 | 🟡 High | 阻塞操作在异步函数中 |
| ASYNC-002 | 🟢 Medium | 可并行的任务串行执行 |

### 线程安全 (THREAD)

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| THREAD-001 | 🟡 High | 共享资源访问未加锁 |
| THREAD-002 | 🟢 Medium | 锁粒度太大影响并发 |

## 5. 缓存策略

| 规则ID | 严重程度 | 检查要点 |
|--------|---------|---------|
| CACHE-001 | 🟢 Medium | 热点数据未缓存 |
| CACHE-002 | 🟢 Medium | 缓存键设计不合理 |
| CACHE-003 | 🔵 Low | 缓存过期策略不当 |

## 性能检查清单

```markdown
□ 数据库性能
  □ 无N+1查询问题
  □ 查询使用索引
  □ 大数据量已分页
  □ 热点数据已缓存

□ 循环与算法
  □ 循环内无耗时操作
  □ 算法复杂度合理
  □ 使用合适的数据结构

□ 内存管理
  □ 大文件流式处理
  □ 无内存泄漏风险

□ 并发优化
  □ 异步代码无非阻塞操作
  □ 合理并行化
```
