# 测试报告生成器 - 详细参考文档

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

2. **数据不上传**
   - 所有输入文件内容仅在本地内存中处理
   - 不会连接到任何远程服务器
   - 不会上传任何数据到后台

3. **输出生成本地**
   - 生成的报告直接保存到本地指定目录
   - 默认输出目录：`F:\下载`
   - 可自定义为任意本地路径

### 使用的本地库

| 库名称 | 用途 | 是否联网 |
|--------|------|----------|
| python-docx | 处理Word文档 | 否，纯本地处理 |
| openpyxl | 处理Excel文件 | 否，纯本地处理 |
| xmindparser | 解析Xmind文件 | 否，纯本地处理 |

---

## 命令行参数详解

### 必需参数

| 参数 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--template` | `-t` | Word模板文件路径（必需） | `--template templates/报告模板.docx` |

### 可选参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--output` | `-o` | 输出目录 | `F:\下载` |
| `--input-excel` | `-e` | 输入Excel文件路径 | - |
| `--input-xmind` | `-x` | 输入Xmind文件路径 | - |
| `--input-word` | `-w` | 输入Word文件路径 | - |
| `--input-data` | `-d` | 文字描述数据 | - |
| `--project-name` | `-p` | 项目名称 | - |
| `--tester` | - | 测试人员姓名 | - |
| `--test-period` | - | 测试周期 | - |
| `--output-filename` | - | 输出文件名 | 自动生成 |

### 使用示例

#### 基础用法

```bash
python scripts/generate_report.py \
  --template templates/标准模板.docx \
  --input-excel "测试用例.xlsx"
```

#### 完整参数

```bash
python scripts/generate_report.py \
  --template templates/详细模板.docx \
  --output "F:\下载" \
  --input-excel "功能测试.xlsx" \
  --input-xmind "测试计划.xmind" \
  --input-data "本次测试覆盖核心功能模块" \
  --project-name "订单管理系统V2.0" \
  --tester "张三" \
  --test-period "2026-04-01 至 2026-04-08" \
  --output-filename "订单系统测试报告.docx"
```

---

## 模板变量完整列表

### 预定义变量

| 变量名 | 说明 | 自动计算 | 数据来源 |
|--------|------|----------|----------|
| `{{report_title}}` | 报告标题 | 否 | 用户设置 |
| `{{report_date}}` | 报告日期 | 是 | 当前日期 |
| `{{test_period}}` | 测试周期 | 否 | 用户设置 |
| `{{tester}}` | 测试人员 | 否 | 用户设置 |
| `{{project_name}}` | 项目名称 | 否 | 用户设置 |

### 统计变量（从Excel自动计算）

| 变量名 | 说明 | 计算规则 |
|--------|------|----------|
| `{{total_cases}}` | 总用例数 | 统计Excel中所有数据行 |
| `{{passed_cases}}` | 通过用例数 | 统计"结果"列包含"通过/Pass/pass"的行 |
| `{{failed_cases}}` | 失败用例数 | 统计"结果"列包含"失败/Fail/fail"的行 |
| `{{blocked_cases}}` | 阻塞用例数 | 统计"结果"列包含"阻塞/Block/block"的行 |
| `{{pass_rate}}` | 通过率 | `(passed_cases / total_cases) * 100%` |

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

**测试用例表：**

| 用例编号 | 用例名称 | 前置条件 | 测试步骤 | 预期结果 | 实际结果 | 结果 | 备注 |
|----------|----------|----------|----------|----------|----------|------|------|
| TC001 | 用户登录 | 账号已注册 | 1.输入用户名 2.输入密码 3.点击登录 | 登录成功 | 登录成功 | 通过 | - |
| TC002 | 密码错误 | 账号已注册 | 1.输入用户名 2.输入错误密码 3.点击登录 | 提示密码错误 | 提示密码错误 | 通过 | - |

#### 注意事项

1. **表头**：第一行必须是表头
2. **结果列**：建议包含"结果"、"状态"或通过/失败标识
3. **合并单元格**：尽量避免，可能导致数据读取异常
4. **多工作表**：支持多工作表，每个工作表会作为独立章节

### Xmind文件格式

#### 支持的格式
- `.xmind` 格式（标准Xmind文件）

#### 推荐结构

```
测试计划
├── 功能测试
│   ├── 用户模块
│   │   ├── 注册功能
│   │   ├── 登录功能
│   │   └── 密码找回
│   └── 订单模块
│       ├── 创建订单
│       └── 订单查询
├── 性能测试
│   ├── 并发测试
│   └── 压力测试
└── 安全测试
    ├── SQL注入
    └── XSS攻击
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

1. **内容整合**：将现有Word文档的内容整合到报告中
2. **格式参考**：提取特定段落的格式
3. **数据追加**：在现有文档基础上追加内容

---

## 输出目录配置

### 默认配置

默认输出目录为：`F:\下载`

### 修改默认输出目录

#### 方法1：命令行参数

```bash
python scripts/generate_report.py \
  --template template.docx \
  --output "D:\我的报告"
```

#### 方法2：修改脚本

编辑 `scripts/generate_report.py`，修改 `DEFAULT_OUTPUT_DIR`：

```python
class TestReportGenerator:
    DEFAULT_OUTPUT_DIR = r"D:\我的报告"  # 修改此处
```

#### 方法3：环境变量

设置环境变量 `TEST_REPORT_OUTPUT_DIR`：

```bash
set TEST_REPORT_OUTPUT_DIR=D:\我的报告
python scripts/generate_report.py --template template.docx
```

### 输出文件名规则

默认文件名格式：`{project_name}_测试报告_{日期}.docx`

示例：`订单管理系统_测试报告_20260409.docx`

---

## 常见问题与解决方案

### 问题1：模板变量未替换

**现象**：生成的文档中仍然显示 `{{变量名}}`

**原因**：
1. 变量名拼写错误
2. 变量格式不正确（缺少大括号）
3. 变量在表格单元格中，格式特殊

**解决**：
1. 检查变量名拼写
2. 确保格式为 `{{variable_name}}`
3. 对于表格中的变量，确保单元格中只有变量，没有其他文本

### 问题2：目录未刷新

**现象**：目录页显示"未找到目录项"或内容为空

**原因**：python-docx无法直接更新Word的目录字段

**解决**：
1. 在Word中打开生成的文档
2. 按 `Ctrl+A` 全选文档
3. 按 `F9` 刷新所有字段
4. 选择"更新整个目录"

### 问题3：Excel数据格式错乱

**现象**：表格数据显示不正确，或列错位

**原因**：
1. Excel中存在合并单元格
2. 数据行中存在空行
3. 列数不一致

**解决**：
1. 取消Excel中的合并单元格
2. 删除数据区域中的空行
3. 确保每行数据列数一致

### 问题4：Xmind解析失败

**现象**：提示"加载Xmind文件失败"

**原因**：
1. 文件格式不正确
2. xmindparser库未安装
3. 文件损坏

**解决**：
1. 确保文件是标准的 `.xmind` 格式
2. 安装依赖：`pip install xmindparser`
3. 尝试用Xmind软件重新保存文件

### 问题5：中文字体显示异常

**现象**：生成的文档中中文显示为方框或乱码

**原因**：模板使用的字体在当前系统不存在

**解决**：
1. 使用通用字体（如宋体、微软雅黑）
2. 在模板中指定常用字体
3. 安装模板使用的字体

---

## 高级用法

### 批量生成报告

```python
import os
from scripts.generate_report import TestReportGenerator

projects = [
    {'name': '项目A', 'excel': '项目A测试用例.xlsx'},
    {'name': '项目B', 'excel': '项目B测试用例.xlsx'},
]

for project in projects:
    generator = TestReportGenerator('templates/模板.docx')
    generator.set_variable('project_name', project['name'])
    generator.load_excel(project['excel'])
    generator.generate()
```

### 自定义数据处理

```python
generator = TestReportGenerator('templates/模板.docx')

# 自定义变量
generator.set_variables({
    'project_name': '自定义项目',
    'custom_field': '自定义值',
    'version': 'v1.2.3'
})

# 自定义统计逻辑
def custom_stats(excel_data):
    # 自定义统计计算
    pass

# 生成报告
generator.generate('自定义报告.docx')
```

### 集成到工作流

可以在CI/CD流程中集成报告生成：

```yaml
# .github/workflows/test-report.yml
- name: Generate Test Report
  run: |
    pip install python-docx openpyxl
    python .lingma/skills/test-report-generator/scripts/generate_report.py \
      --template templates/ci-template.docx \
      --input-excel test-results.xlsx \
      --project-name "${{ github.event.repository.name }}"
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
```

### 完整安装

```bash
pip install python-docx openpyxl xmindparser
```

---

## 更新日志

### v1.0.0
- 基础功能实现
- 支持Excel、Xmind、Word输入
- 支持模板变量替换
- 默认输出到 F:\下载
