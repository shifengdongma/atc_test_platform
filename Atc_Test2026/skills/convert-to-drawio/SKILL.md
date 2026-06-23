---
name: convert-to-drawio
description: 将文本描述、手绘流程图图片、文档等内容转换为 Draw.io 可编辑的图表格式。支持流程图、架构图、UML图等多种图表类型。当用户需要将描述性内容、手绘草图或文档转换为专业图表时使用。
---

# 转换为 Draw.io 格式

将各种输入（文本描述、手绘图、文档）转换为 Draw.io 可编辑的 XML 格式。

## 快速开始

当用户要求转换为 Draw.io 格式时：

1. **分析输入内容**，提取关键元素和关系
2. **生成 XML 内容**，构建 Draw.io 格式的图表
3. **执行脚本生成文件**：`python scripts/generate_drawio.py --output "F:\下载\图表名.drawio" --content "生成的XML内容"`

## 支持输入类型

- **文本描述**：自然语言描述的系统架构、流程等
- **手绘流程图**：手绘草图的照片或扫描件
- **文档**：包含图表需求的 Word、PDF、Markdown 等

## 输出格式

生成 `.drawio` 文件，可直接在 [draw.io](https://app.diagrams.net/) 或本地 Draw.io 桌面版中打开编辑。

## 转换流程

### 1. 分析输入内容

根据输入类型提取关键信息：

| 输入类型 | 提取内容 |
|---------|---------|
| 文本描述 | 实体、关系、流程步骤 |
| 手绘图 | 节点、连线、布局结构 |
| 文档 | 章节结构、关键概念、关系 |

### 2. 确定图表类型

根据内容特征选择最合适的图表类型：

- **流程图**：有明确的步骤和决策点
- **架构图**：展示系统组件和交互
- **UML类图**：展示类结构和关系
- **时序图**：展示对象间交互顺序
- **思维导图**：展示层级概念结构

### 3. 生成 Draw.io XML

使用以下结构生成 XML：

```xml
<mxfile host="app.diagrams.net">
  <diagram name="Page-1">
    <mxGraphModel dx="1422" dy="762" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        
        <!-- 节点示例 -->
        <mxCell id="2" value="节点文本" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="120" y="80" width="120" height="60" as="geometry" />
        </mxCell>
        
        <!-- 连线示例 -->
        <mxCell id="3" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="2" target="4">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

### 常用样式模板

**矩形节点（默认）**：
```
style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
```

**圆形节点**：
```
style="ellipse;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;"
```

**菱形（决策）**：
```
style="rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;"
```

**圆柱（数据库）**：
```
style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;fillColor=#e1d5e7;strokeColor=#9673a6;"
```

**云形（外部系统）**：
```
style="ellipse;shape=cloud;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;"
```

## 布局原则

1. **从左到右**或**从上到下**排列主要流程
2. **同级节点**保持垂直或水平对齐
3. **间距**：节点之间保持 40-60px 间距
4. **连线**：使用正交连线（`edgeStyle=orthogonalEdgeStyle`）

## 脚本使用说明

### 生成 Draw.io 文件

**基本用法**：
```bash
python scripts/generate_drawio.py --output "F:\下载\图表名.drawio" --content "XML内容"
```

**从文件读取 XML**：
```bash
python scripts/generate_drawio.py --output "F:\下载\图表名.drawio" --file "xml_content.txt"
```

**指定图表名称**：
```bash
python scripts/generate_drawio.py --output "F:\下载\图表名.drawio" --content "XML内容" --diagram-name "流程图"
```

### 脚本参数

| 参数 | 说明 | 必需 |
|------|------|------|
| `--output` | 输出文件路径 | 是 |
| `--content` | XML 内容字符串 | 与 --file 二选一 |
| `--file` | 包含 XML 内容的文件路径 | 与 --content 二选一 |
| `--diagram-name` | 图表名称（默认: Page-1） | 否 |
| `--encoding` | 文件编码（默认: utf-8） | 否 |

## 完整示例

### 输入：文本描述
```
用户登录流程：
1. 用户输入用户名密码
2. 系统验证
3. 如果验证通过，跳转到首页
4. 如果验证失败，显示错误信息
```

### 执行步骤

1. **生成 XML 内容**（按上述模板构建）

2. **执行脚本生成文件**：
```bash
python scripts/generate_drawio.py --output "F:\下载\登录流程.drawio" --content "<mxfile>...</mxfile>"
```

3. **告知用户**：文件已生成，可直接在 draw.io 打开编辑

## 注意事项

- 保持 XML 格式正确，特别是标签闭合
- 为每个节点和连线分配唯一 ID
- 使用相对坐标，便于后续手动调整
- 添加适当的颜色区分不同类型的节点
- 默认输出目录为 `F:\下载`，可根据用户需求调整
