---
name: xmind-test-case-generator
description: 根据需求文档生成测试用例 XMind 思维导图。当用户需要从需求文档创建测试用例思维导图、将需求转换为测试用例结构、或生成测试用例的 XMind 文件时使用。支持自动识别需求文档的层级结构，生成包含正向用例、负向用例、边界值用例和异常用例的思维导图。
---

# XMind 测试用例生成工具

## 概述

本技能使 Claude 能够根据需求文档自动生成 XMind 格式的测试用例思维导图。支持识别需求文档的层级结构，自动生成测试用例分类（正向、负向、边界值、异常），并输出为标准的 XMind 文件。

## 快速开始

当用户请求生成测试用例 XMind 文件时，您应该：

1. **读取需求文档**：分析用户提供的需求文档内容
2. **解析需求结构**：识别需求文档的层级结构（章节、功能点等）
3. **生成测试用例结构**：为每个功能点创建测试用例分类
4. **生成 XMind 文件**：使用生成器脚本创建 XMind 文件
5. **提供文件给用户**：将生成的 .xmind 文件路径告知用户

## 使用生成器脚本

### 基本用法

使用 `scripts/xmind_generator.py` 生成 XMind 文件：

```python
from scripts.xmind_generator import XMindGenerator

generator = XMindGenerator()

# 方法1：从需求文档文本生成
requirements_text = """
2.1 用户信息展示
2.1.1 基础信息
头像设置
上传规则：支持JPG/PNG格式
"""

structure = generator.parse_requirements_to_structure(requirements_text)
test_cases = generator.create_test_cases_structure(structure)

output_path = generator.generate_xmind(
    "test_cases.xmind",
    "测试用例",
    test_cases
)
```

### 手动构建结构

如果需求文档格式不标准，可以手动构建结构：

```python
from scripts.xmind_generator import XMindGenerator

generator = XMindGenerator()

# 手动构建测试用例结构
structure = [
    {
        "title": "登录功能",
        "children": [
            {
                "title": "登录功能 - 测试用例",
                "children": [
                    {"title": "正向用例", "children": [
                        {"title": "正常登录"},
                        {"title": "记住密码登录"}
                    ]},
                    {"title": "负向用例", "children": [
                        {"title": "错误密码"},
                        {"title": "不存在的用户名"}
                    ]},
                    {"title": "边界值用例", "children": [
                        {"title": "空用户名"},
                        {"title": "超长密码"}
                    ]}
                ]
            }
        ]
    }
]

output_path = generator.generate_xmind(
    "login_test_cases.xmind",
    "登录功能测试用例",
    structure
)
```

## 测试用例结构设计

### 标准分类

为每个功能点生成以下测试用例分类：

- **正向用例**：正常、预期的用户流程
- **负向用例**：错误处理、无效输入
- **边界值用例**：边界情况、限制条件
- **异常用例**：异常场景、错误处理

### 结构层级

典型的测试用例思维导图结构：

```
测试用例（根节点）
├── 功能模块1
│   ├── 功能点1 - 测试用例
│   │   ├── 正向用例
│   │   ├── 负向用例
│   │   ├── 边界值用例
│   │   └── 异常用例
│   └── 功能点2 - 测试用例
│       └── ...
└── 功能模块2
    └── ...
```

## 需求文档解析

生成器会自动识别以下格式的需求文档：

- 章节编号：`2.1`, `2.1.1`, `2.1.1.1` 等
- 功能描述：包含"设置"、"上传"、"输入"、"显示"、"校验"、"功能"等关键词
- 规则描述：包含"规则"、"限制"、"支持"等关键词

如果需求文档格式不标准，建议手动构建结构。

## 高级用法

### 添加备注

为主题添加备注信息：

```python
topic = generator.create_topic(
    "登录功能",
    note="测试用户登录功能的各项场景",
    children=[...]
)
```

### 添加标记

为主题添加优先级标记：

```python
topic = generator.create_topic(
    "关键功能测试",
    markers=["priority-1"],
    children=[...]
)
```

## 参考文档

**加载 [使用指南](./references/usage_guide.md) 获取详细的使用说明和最佳实践。**

使用指南包含：
- 需求文档格式要求
- 测试用例设计原则
- 完整工作流程
- 最佳实践和常见问题

## 资源

### scripts/xmind_generator.py
用于生成 XMind 格式文件的 Python 类，支持：
- 解析需求文档文本
- 构建测试用例层级结构
- 生成标准 XMind Zen 格式文件

### references/usage_guide.md
详细的使用指南，包括需求文档格式、测试用例设计原则、工作流程和最佳实践。

### 文件格式说明

XMind 文件是 ZIP 压缩包，包含：
- `content.json` - 思维导图的内容结构（JSON 格式）
- `META-INF/manifest.xml` - 元数据清单

生成的文件可以在 XMind 软件中正常打开和编辑。
