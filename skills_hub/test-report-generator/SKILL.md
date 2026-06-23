---
name: test-report-generator
description: 根据输入数据（文字描述、Excel、Xmind、Word文件）在本地自动生成格式化的Word测试报告。所有文件解析均在本地完成，不上传任何数据到后台。使用当用户需要基于测试数据生成报告、填写测试报告模板、或处理测试相关文档时。
---

# 测试报告生成器

根据多种输入源自动生成格式化的Word测试报告。

## 功能概述

- **本地处理**：所有文件解析均在本地完成，数据不上传后台
- 支持输入：文字描述、Excel文件、Xmind文件、Word文件
- 基于Word模板生成报告
- 自动刷新目录、保持模板格式
- 默认输出到 `F:\下载` 目录

## 使用方法

### 1. 准备模板

将Word模板文件放入以下目录之一：
- **技能模板目录**：`.lingma/skills/test-report-generator/templates/`
- **用户自定义目录**：用户指定的任意目录

### 2. 提供输入数据

支持以下输入方式（可组合使用），**所有文件均在本地解析，不会上传**：
- **文字描述**：直接提供测试内容、结果、结论等
- **Excel文件**：本地解析测试用例、测试数据、统计结果
- **Xmind文件**：本地提取测试计划、测试用例结构、思维导图
- **Word文件**：本地读取现有文档内容进行整合

### 3. 生成报告

运行生成脚本，指定模板和输入文件：

```bash
python .lingma/skills/test-report-generator/scripts/generate_report.py \
  --template templates/测试报告模板.docx \
  --output "F:\下载" \
  --input-data "测试数据描述" \
  --input-excel "测试用例.xlsx" \
  --input-xmind "测试计划.xmind"
```

## 报告结构（可定制）

以下是一级标题的预留位置，可在模板中定制：

```
1. 测试概述
   - 测试目的
   - 测试范围
   - 测试环境

2. 测试执行情况
   - 测试用例执行情况
   - 测试进度
   - 资源使用情况

3. 测试结果统计
   - 用例通过率
   - 缺陷统计
   - 覆盖率分析

4. 缺陷分析
   - 缺陷分布
   - 严重级别分析
   - 趋势分析

5. 测试结论与建议
   - 质量评估
   - 风险评估
   - 改进建议

6. 附录
   - 测试用例清单
   - 详细测试数据
   - 其他参考资料
```

## 模板变量

在Word模板中使用以下占位符，将被自动替换：

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `{{report_title}}` | 报告标题 | 系统功能测试报告 |
| `{{report_date}}` | 报告日期 | 2026-04-09 |
| `{{test_period}}` | 测试周期 | 2026-04-01 至 2026-04-08 |
| `{{tester}}` | 测试人员 | 张三 |
| `{{project_name}}` | 项目名称 | 订单管理系统 |
| `{{total_cases}}` | 总用例数 | 150 |
| `{{passed_cases}}` | 通过用例数 | 142 |
| `{{failed_cases}}` | 失败用例数 | 5 |
| `{{blocked_cases}}` | 阻塞用例数 | 3 |
| `{{pass_rate}}` | 通过率 | 94.67% |

## 输入文件处理规则（本地解析）

> **隐私说明**：所有输入文件均在本地使用Python库解析，不会上传到任何服务器或后台。

### Excel文件（本地解析）
- 使用 `openpyxl` 库在本地读取Excel文件
- 自动识别工作表名称作为章节标题
- 支持多工作表合并
- 保留表格格式和样式

### Xmind文件（本地解析）
- 使用 `xmindparser` 库在本地解析Xmind文件
- 提取主题结构作为报告大纲
- 支持多级主题嵌套
- 保留备注和标签信息

### Word文件（本地解析）
- 使用 `python-docx` 库在本地读取Word文件
- 提取指定章节内容
- 保留原有格式
- 支持内容追加或替换

## 输出规范

- **默认输出目录**：`F:\下载`
- **文件名格式**：`{项目名}_测试报告_{日期}.docx`
- **目录自动刷新**：生成后自动更新目录页
- **格式保持**：完全遵循模板格式

## 示例

### 示例1：基于Excel测试用例生成报告

```bash
python scripts/generate_report.py \
  --template templates/标准测试报告模板.docx \
  --output "F:\下载" \
  --input-excel "接口测试用例.xlsx" \
  --project-name "订单接口测试" \
  --tester "李四"
```

### 示例2：组合多种输入

```bash
python scripts/generate_report.py \
  --template templates/详细测试报告模板.docx \
  --output "F:\下载" \
  --input-data "本次测试覆盖核心业务流程" \
  --input-excel "功能测试用例.xlsx" \
  --input-xmind "测试范围.xmind" \
  --input-word "补充说明.docx" \
  --project-name "电商系统V2.0测试"
```

## 依赖安装

首次使用前安装依赖：

```bash
pip install python-docx openpyxl xmindparser
```

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| 模板变量未替换 | 检查占位符格式是否为 `{{变量名}}` |
| 目录未刷新 | 手动在Word中按 `Ctrl+A` 后 `F9` 刷新 |
| Excel格式错乱 | 确保Excel中合并单元格已取消 |
| Xmind解析失败 | 确保文件为.xmind格式（非.xmind.zip） |

## 参考文档

- 详细配置说明：[reference.md](reference.md)
- 模板制作指南：参见 `templates/` 目录下的示例模板
