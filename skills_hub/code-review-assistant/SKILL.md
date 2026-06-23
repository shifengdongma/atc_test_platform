---
name: code-review-assistant
description: 基于本地知识库进行代码评审，支持自定义评审规则和检查清单。当用户需要代码评审、质量检查、合规性检查时使用。
---

# 代码评审助手

基于本地知识库执行标准化的代码评审流程，支持安全、性能、代码质量等多维度检查。

## 知识库结构

本技能使用以下知识库文件（位于 `templates/` 目录）：

| 知识库文件 | 用途 | 调用方式 |
|-----------|------|---------|
| `security-rules.md` | 安全编码规范 | @templates/security-rules.md |
| `performance-rules.md` | 性能优化规范 | @templates/performance-rules.md |
| `quality-standards.md` | 代码质量标准 | @templates/quality-standards.md |
| `review-checklist.md` | 评审检查清单 | @templates/review-checklist.md |

## 使用方法

### 方式1：引用知识库进行评审（推荐）

```
请根据以下知识库对代码进行评审：
- 安全规范：@templates/security-rules.md
- 性能规范：@templates/performance-rules.md
- 质量规范：@templates/quality-standards.md

待评审代码：
[粘贴代码]
```

### 方式2：使用检查清单

```
请按照 @templates/review-checklist.md 的检查清单，对以下代码进行逐项检查：

[粘贴代码]
```

### 方式3：全面评审报告

```
请执行完整的代码评审：
1. 读取所有知识库文件
2. 对代码进行多维度分析
3. 按严重程度分类问题
4. 提供修复建议
5. 输出评审报告

代码文件：[文件路径或内容]
```

## 评审输出格式

评审结果将按以下格式输出：

```markdown
## 代码评审报告

### 概览
- 评审文件：xxx
- 代码行数：xxx
- 发现问题：X个（Critical: X, High: X, Medium: X, Low: X）
- 综合评分：XX/100

### 详细发现

#### 🔴 Critical Issues
1. **[规则ID]** 问题描述
   - 位置：文件:行号
   - 风险：xxx
   - 建议：xxx

#### 🟡 High Issues
...

### 修复建议
...

### 正面评价
...
```

## 知识库扩展

如需添加自定义规则：
1. 在 `templates/` 目录创建新的 `.md` 文件
2. 按照现有格式定义规则
3. 在评审时通过 `@templates/文件名.md` 引用
