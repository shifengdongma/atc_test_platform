# 测试方案生成器 - 详细参考文档

> **隐私与安全**：本工具所有文件解析均在本地完成，使用本地Python库处理数据，不会上传任何信息到后台或服务器。

## 目录

1. [隐私说明](#隐私说明)
2. [命令行参数详解](#命令行参数详解)
3. [模板变量完整列表](#模板变量完整列表)
4. [输入文件格式要求](#输入文件格式要求)
5. [输出目录配置](#输出目录配置)
6. [常见问题与解决方案](#常见问题与解决方案)
7. [高级用法](#高级用法)

---

## 隐私说明

### 本地处理原则

本工具严格遵循**本地处理**原则：

1. **文件解析本地完成**
   - Excel文件使用 `openpyxl` 库本地读取
   - Xmind文件使用 `xmindparser` 库本地解析
   - Word文件使用 `python-docx` 库本地处理
   - 图片文件使用 `Pillow` 库本地处理

2. **数据不上传**
   - 所有输入文件内容仅在本地内存中处理
   - 不会连接到任何远程服务器
   - 不会上传任何数据到后台

3. **输出生成本地**
   - 生成的方案直接保存到本地指定目录
   - 默认输出目录：`F:\下载`
   - 可自定义为任意本地路径

### 使用的本地库

| 库名称 | 用途 | 是否联网 |
|--------|------|----------|
| python-docx | 处理Word文档 | 否，纯本地处理 |
| openpyxl | 处理Excel文件 | 否，纯本地处理 |
| xmindparser | 解析Xmind文件 | 否，纯本地处理 |
| pillow | 处理图片文件 | 否，纯本地处理 |

---

## 命令行参数详解

### 必需参数

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--template` | `-t` | Word模板文件路径（必需） | `--template templates/方案模板.docx` |

### 可选参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--output` | `-o` | 输出目录 | `F:\下载` |
| `--input-excel` | `-e` | 输入Excel文件路径 | - |
| `--input-xmind` | `-x` | 输入Xmind文件路径 | - |
| `--input-word` | `-w` | 输入Word文件路径 | - |
| `--input-image` | `-i` | 输入图片文件路径（可多次使用） | - |
| `--input-data` | `-d` | 文字描述数据 | - |
| `--project-name` | `-p` | 项目名称 | - |
| `--author` | - | 编写人 | - |
| `--reviewer` | - | 审核人 | - |
| `--version` | `-v` | 版本号 | `V1.0` |
| `--estimated-duration` | - | 预计工期 | - |
| `--output-filename` | - | 输出文件名 | 自动生成 |

### 使用示例

#### 基础用法

```bash
python scripts/generate_plan.py \
  --template templates/标准模板.docx \
  --input-excel "需求清单.xlsx"
```

#### 完整参数

```bash
python scripts/generate_plan.py \
  --template templates/详细模板.docx \
  --output "F:\下载" \
  --input-excel "需求清单.xlsx" \
  --input-xmind "功能结构.xmind" \
  --input-word "需求规格说明书.docx" \
  --input-image "原型图1.png" \
  --input-image "原型图2.png" \
  --project-name "订单管理系统" \
  --author "张三" \
  --reviewer "李四" \
  --version "V1.0" \
  --estimated-duration "30人天"
```

---

## 模板变量完整列表

### 预定义变量

| 变量名 | 说明 | 自动计算 | 数据来源 |
|--------|------|----------|----------|
| `{{plan_title}}` | 方案标题 | 否 | 用户设置 |
| `{{plan_date}}` | 方案日期 | 是 | 当前日期 |
| `{{project_name}}` | 项目名称 | 否 | 用户设置 |
| `{{version}}` | 版本号 | 否 | 用户设置 |
| `{{author}}` | 编写人 | 否 | 用户设置 |
| `{{reviewer}}` | 审核人 | 否 | 用户设置 |
| `{{approve_date}}` | 批准日期 | 否 | 用户设置 |

### 统计变量（从Excel/Xmind自动计算）

| 变量名 | 说明 | 计算规则 |
|--------|------|----------|
| `{{total_requirements}}` | 需求总数 | 统计Excel中所有数据行或Xmind主题数 |
| `{{total_modules}}` | 功能模块数 | 统计模块列的唯一值或Xmind分支数 |
| `{{test_types}}` | 测试类型 | 用户设置 |
| `{{estimated_duration}}` | 预计工期 | 用户设置 |

### 自定义变量

你可以在模板中使用任意自定义变量，只要在生成时通过代码设置即可：

```python
generator.set_variable('custom_var', '自定义值')
```

---

## 输入文件格式要求

### Excel文件格式

#### 支持的格式
- `.xlsx` 格式（推荐）
- `.xls` 格式（部分支持）

#### 推荐结构

**需求清单表：**

| 序号 | 模块 | 功能点 | 需求描述 | 优先级 | 验收标准 |
|------|------|--------|----------|--------|----------|
| 1 | 用户管理 | 用户注册 | 支持手机号注册 | 高 | 注册成功发送短信 |
| 2 | 用户管理 | 用户登录 | 支持密码登录 | 高 | 登录成功跳转首页 |

#### 注意事项

1. **表头**：第一行必须是表头
2. **模块列**：建议包含"模块"、"功能"或"模块名称"列，用于统计模块数
3. **合并单元格**：尽量避免，可能导致数据读取异常
4. **多工作表**：支持多工作表，每个工作表会作为独立章节

### Xmind文件格式

#### 支持的格式
- `.xmind` 格式（标准Xmind文件）

#### 推荐结构

```
测试方案
├── 功能模块
│   ├── 用户管理
│   │   ├── 注册功能
│   │   ├── 登录功能
│   │   └── 密码找回
│   └── 订单管理
│       ├── 创建订单
│       └── 订单查询
├── 测试策略
│   ├── 功能测试
│   ├── 接口测试
│   └── 性能测试
└── 风险评估
    ├── 进度风险
    └── 人员风险
```

#### 数据提取规则

- 中心主题 → 章节标题
- 一级分支 → 二级标题
- 二级分支 → 三级标题
- 备注 → 正文内容

### Word文件格式

#### 支持的格式
- `.docx` 格式

#### 使用场景

1. **需求规格说明书**：提取需求内容
2. **产品文档**：提取功能描述
3. **参考文档**：提取测试要点

### 图片文件格式

#### 支持的格式
- `.png`、`.jpg`、`.jpeg`、`.bmp`、`.gif`

#### 使用场景

1. **原型图**：展示界面设计
2. **流程图**：展示业务流程
3. **架构图**：展示系统架构

---

## 输出目录配置

### 默认配置

默认输出目录为：`F:\下载`

### 修改默认输出目录

#### 方法1：命令行参数

```bash
python scripts/generate_plan.py \
  --template template.docx \
  --output "D:\我的文档"
```

#### 方法2：修改脚本

编辑 `scripts/generate_plan.py`，修改 `DEFAULT_OUTPUT_DIR`：

```python
class TestPlanGenerator:
    DEFAULT_OUTPUT_DIR = r"D:\我的文档"  # 修改此处
```

### 输出文件名规则

默认文件名格式：`{project_name}_测试方案_{日期}.docx`

示例：`订单管理系统_测试方案_20260409.docx`

---

## 常见问题与解决方案

### 问题1：模板变量未替换

**现象**：生成的文档中仍然显示 `{{变量名}}`

**原因**：
1. 变量名拼写错误
2. 变量格式不正确
3. 变量在表格单元格中

**解决**：
1. 检查变量名拼写
2. 确保格式为 `{{variable_name}}`
3. 对于表格中的变量，确保单元格中只有变量

### 问题2：目录未刷新

**现象**：目录页显示"未找到目录项"

**解决**：
1. 在Word中打开生成的文档
2. 按 `Ctrl+A` 全选
3. 按 `F9` 刷新所有字段
4. 选择"更新整个目录"

### 问题3：Excel数据格式错乱

**解决**：
1. 取消Excel中的合并单元格
2. 删除数据区域中的空行
3. 确保每行数据列数一致

### 问题4：图片无法插入

**解决**：
1. 确保图片格式受支持（png/jpg/jpeg/bmp/gif）
2. 检查图片路径是否正确
3. 安装Pillow库：`pip install pillow`

---

## 高级用法

### 批量生成方案

```python
import os
from scripts.generate_plan import TestPlanGenerator

projects = [
    {'name': '项目A', 'excel': '项目A需求.xlsx'},
    {'name': '项目B', 'excel': '项目B需求.xlsx'},
]

for project in projects:
    generator = TestPlanGenerator('templates/模板.docx')
    generator.set_variable('project_name', project['name'])
    generator.load_excel(project['excel'])
    generator.generate()
```

### 自定义数据处理

```python
generator = TestPlanGenerator('templates/模板.docx')

# 自定义变量
generator.set_variables({
    'project_name': '自定义项目',
    'custom_field': '自定义值',
    'department': '测试部'
})

generator.generate('自定义方案.docx')
```

---

## 依赖安装

### 必需依赖

```bash
pip install python-docx
```

### 可选依赖

```bash
# Excel支持
pip install openpyxl

# Xmind支持
pip install xmindparser

# 图片支持
pip install pillow
```

### 完整安装

```bash
pip install python-docx openpyxl xmindparser pillow
```

---

## 更新日志

### v1.0.0
- 基础功能实现
- 支持Excel、Xmind、Word、图片输入
- 支持模板变量替换
- 默认输出到 F:\下载
- 纯本地处理，数据不上传
