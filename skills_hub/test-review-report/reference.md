# Reference: 迭代缺陷分析与报告生成

## 目录
1. [数据分析脚本模板](#数据分析脚本模板)
2. [报告生成脚本模板](#报告生成脚本模板)
3. [关键代码片段](#关键代码片段)
4. [低空空管系统问题模式映射](#低空空管系统问题模式映射)

---

## 数据分析脚本模板

```python
import pandas as pd
from datetime import datetime

def analyze_defects(excel_path):
    df = pd.read_excel(excel_path)
    total = len(df)

    # 基础统计
    severity = df['严重程度'].value_counts()
    status = df['状态'].value_counts()
    priority = df['优先级'].value_counts()
    category = df['问题大类'].value_counts()
    reason = df['缺陷原因分类'].value_counts()
    module = df['模块'].value_counts()
    creator = df['创建人'].value_counts()
    responsibility = df['问题责任人'].value_counts()

    # 时间分析
    df['创建时间_dt'] = pd.to_datetime(df['创建时间'])
    df['创建日期'] = df['创建时间_dt'].dt.date
    daily = df['创建日期'].value_counts().sort_index()

    # 重新打开（严格判断：重新打开时间 > 创建时间）
    df['重新打开时间_dt'] = pd.to_datetime(df['重新打开时间'], errors='coerce')
    real_reopen = df[df['重新打开时间_dt'] > df['创建时间_dt']]
    reopen_count = len(real_reopen)

    # 模块×严重程度交叉
    module_severity = pd.crosstab(df['模块'], df['严重程度'])

    # 未关闭缺陷
    unclosed = df[df['状态'].isin(['新', '接受/处理', '挂起'])]

    # 严重缺陷
    severe_df = df[df['严重程度'].isin(['致命', '严重'])]

    # 测试环境
    env = df['测试环境'].value_counts()

    # 迭代归属
    iteration = df['迭代'].value_counts()

    return {
        'total': total,
        'severity': severity,
        'status': status,
        'priority': priority,
        'category': category,
        'reason': reason,
        'module': module,
        'module_severity': module_severity,
        'creator': creator,
        'responsibility': responsibility,
        'daily': daily,
        'reopen': real_reopen,
        'reopen_count': reopen_count,
        'unclosed': unclosed,
        'severe_df': severe_df,
        'env': env,
        'iteration': iteration,
    }
```

---

## 报告生成脚本模板

```python
import pandas as pd
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from datetime import datetime

def set_font(run, size=10.5, bold=False, color=RGBColor(0,0,0)):
    run.font.name = '微软雅黑'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color

def create_table(doc, headers, data_rows):
    """创建统一格式的表格"""
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.style = 'Light Grid Accent 1'
    for i, h in enumerate(headers):
        set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
        tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for row_data in data_rows:
        row = tbl.add_row().cells
        for i, val in enumerate(row_data):
            set_font(row[i].paragraphs[0].add_run(str(val)))
            row[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    return tbl

def generate_report(excel_path, output_path, project_name='XXX系统', iteration='Vx.x.x'):
    df = pd.read_excel(excel_path)
    total = len(df)
    severity = df['严重程度'].value_counts()
    status = df['状态'].value_counts()
    module = df['模块'].value_counts()

    # 重新打开
    df['创建时间_dt'] = pd.to_datetime(df['创建时间'])
    df['重新打开时间_dt'] = pd.to_datetime(df['重新打开时间'], errors='coerce')
    real_reopen = df[df['重新打开时间_dt'] > df['创建时间_dt']]

    # 未关闭
    unclosed = df[df['状态'].isin(['新', '接受/处理', '挂起'])]

    # 模块×严重
    module_severity = pd.crosstab(df['模块'], df['严重程度'])

    doc = Document()

    # 标题
    title = doc.add_heading(f'{project_name}迭代{iteration}集成测试总结报告', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        set_font(run, size=22, bold=True)

    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(info.add_run(f'报告生成日期：{datetime.now().strftime("%Y年%m月%d日")}  |  缺陷总数：{total}条'), size=10)

    # ===== 后续章节按 SKILL.md 结构填充 =====
    # ...

    doc.save(output_path)
    print(f'报告已保存：{output_path}')
```

---

## 关键代码片段

### 1. 模块严重交叉表格生成

```python
def module_severity_table(doc, module_counts, module_severity, total):
    headers = ['模块', '总数', '致命', '严重', '一般', '占比']
    rows = []
    for mod in module_counts.index:
        cnt = module_counts[mod]
        fatal = module_severity.loc[mod, '致命'] if '致命' in module_severity.columns else 0
        sev = module_severity.loc[mod, '严重'] if '严重' in module_severity.columns else 0
        normal = module_severity.loc[mod, '一般'] if '一般' in module_severity.columns else 0
        rows.append([mod, cnt, fatal, sev, normal, f'{cnt/total*100:.1f}%'])
    create_table(doc, headers, rows)
```

### 2. 重新打开缺陷明细表

```python
def reopen_detail_table(doc, real_reopen_df):
    headers = ['ID', '模块', '严重程度', '标题摘要', '重新打开时间']
    rows = []
    for _, r in real_reopen_df.iterrows():
        title_short = str(r['标题'])[:35] + '...' if len(str(r['标题'])) > 35 else str(r['标题'])
        rows.append([
            r['ID'],
            r['模块'] if pd.notna(r['模块']) else '未分类',
            r['严重程度'],
            title_short,
            str(r['重新打开时间'])[:19]
        ])
    create_table(doc, headers, rows)
```

### 3. 未关闭缺陷明细表

```python
def unclosed_detail_table(doc, unclosed_df):
    headers = ['ID', '状态', '严重程度', '模块', '标题摘要']
    rows = []
    for _, r in unclosed_df.iterrows():
        title_short = str(r['标题'])[:40] + '...' if len(str(r['标题'])) > 40 else str(r['标题'])
        rows.append([
            r['ID'],
            r['状态'],
            r['严重程度'],
            r['模块'] if pd.notna(r['模块']) else '未分类',
            title_short
        ])
    create_table(doc, headers, rows)
```

### 4. 趋势表格生成

```python
def trend_table(doc, daily_counts):
    headers = ['日期', '新增缺陷数', '累计缺陷数']
    rows = []
    cumulative = 0
    for date, count in daily_counts.items():
        cumulative += count
        rows.append([str(date), count, cumulative])
    create_table(doc, headers, rows)
```

### 5. 版本号自增

```python
import os
import re

def get_next_version_path(base_path):
    """
    若目标文件已存在，自动递增版本号。
    规则：report.docx -> report_V2.0.docx -> report_V3.0.docx
    """
    if not os.path.exists(base_path):
        return base_path

    dir_name = os.path.dirname(base_path) or '.'
    file_name = os.path.basename(base_path)
    name, ext = os.path.splitext(file_name)

    # 尝试提取现有版本号，如 _V3.0
    match = re.search(r'_V(\d+)\.0$', name)
    if match:
        current_ver = int(match.group(1))
        new_name = re.sub(r'_V\d+\.0$', f'_V{current_ver + 1}.0', name)
    else:
        new_name = f'{name}_V2.0'

    new_path = os.path.join(dir_name, new_name + ext)

    # 递归处理，直到找到不存在的文件名
    if os.path.exists(new_path):
        return get_next_version_path(new_path)
    return new_path


# 使用示例
output_path = 'report.docx'
output_path = get_next_version_path(output_path)
doc.save(output_path)
print(f'报告已保存：{output_path}')
```

---

## 低空空管系统问题模式映射

当从缺陷标题中识别典型问题时，使用以下关键词模式：

### 接收机管理模块
| 问题类型 | 关键词模式 |
|----------|-----------|
| 批量导入 | 批量导入、模板、空文件、实景图、导入失败 |
| 配置下发 | 配置下发、离线设备、下发成功、设备选择、卡死 |
| 注册/升级 | 注册失败、升级结果、升级成功、注册成功、互斥 |
| 设备状态 | 在线状态、离线数量、统计卡片、状态变更 |
| 详情查看 | 密码无法查看、安装时间、运维信息、查询报错 |

### 态势监视模块
| 问题类型 | 关键词模式 |
|----------|-----------|
| 大数据量性能 | 3000架、轨迹预测、WS无数据、缓冲区、内存 |
| 静态回放 | 静态回放、24H、请求超时、选择接收机 |
| Kafka消费 | Kafka超时、消费者组、无小飞机、页面无数据 |
| 航迹展示 | 航迹颜色、航迹展示、多边形、hover提示 |
| 最小探测线 | 最小探测线、ADS-B、选择飞行器、取消选择 |

### 告警管理模块
| 问题类型 | 关键词模式 |
|----------|-----------|
| 状态机震荡 | 趋势取消、频繁产生、关闭告警、反复震荡 |
| 配置不生效 | 设置关闭、仍收到、弹框、设置不生效 |
| 数据冗余 | 每秒产生、数据冗余、最低安全高度 |
| 抑制逻辑 | 抑制区、仍产生告警、抑制逻辑 |
| 详情报错 | 查看告警详情、报错 |

### 任务计划模块
| 问题类型 | 关键词模式 |
|----------|-----------|
| 状态流转错误 | 审批通过、审批不通过、待审批、状态显示、状态变更 |
| 航线冲突 | 航线冲突、自身校验、不应与自身 |
| 字段处理 | 按延迟排序、字段、导入按钮、权限控制 |
| 飞行记录 | 飞行记录、列表、排序、基本信息 |

### 数字孪生模块
| 问题类型 | 关键词模式 |
|----------|-----------|
| 3D地图性能 | 浏览器缩放、地图卡顿、视角切换 |
| 图层显示 | 起降场、建筑物、图层、显示/不显示 |
| 登录/加载 | 重新登录、页面内容、无法加载 |

---

## 报告章节内容模板

### 测试概述模板

```
本次迭代{iteration}集成测试主要针对{project_name}的功能完善、缺陷修复及性能优化进行验证。
测试覆盖{模块列表}等核心模块。
测试周期为{开始日期}至{结束日期}，共记录缺陷{总数}条，其中归属迭代{iteration}的缺陷{归属数}条。
整体缺陷关闭率{关闭率}%，严重级别以上缺陷{严重数}条，占比{严重占比}%。
本轮测试暴露出{高风险模块1}、{高风险模块2}、{高风险模块3}、{高风险模块4}四个方面的系统性质量风险，测试工作达到预期目标。
```

### 重点问题剖析模板（每个模块）

```
{模块名称}（{缺陷总数}条缺陷，严重{严重数}条）

典型问题：
   • {典型问题1}
   • {典型问题2}
   • {典型问题3}
   • {典型问题4}

根因分析：{基于缺陷原因分类和缺陷定位说明归纳的根因}
```

### 过程问题反思模板

```
4.1 需求管理薄弱
需求不明确/变更/理解偏差类缺陷合计占比约{占比}%，如{典型场景1}、{典型场景2}、{典型场景3}等。
部分缺陷根因是需求描述错误（蓝湖描述与实际不符）。
需求评审阶段缺乏"异常场景 & 边界条件"评审checklist，导致开发阶段才发现交互缺失。
建议：需求评审增加异常场景专项环节，建立需求变更影响评估机制。

4.2 代码质量与逻辑错误
功能实现逻辑错误类缺陷占{占比}%，大量标记为"cd"（代码问题），
说明状态流转、数据同步、并发处理等核心逻辑缺乏代码评审（CR）。
单元测试覆盖率不足，尤其是对Redis、Kafka、WebSocket等中间件的异常分支。
{严重缺陷高发模块}严重缺陷高达{数量}条，建议对该模块进行专项代码走查，引入状态机框架替代硬编码判断。

4.3 缺陷根因分析不规范
"其他/其他"根因分类占{占比}%（{数量}条），部分根因标记为"cd"或未填写，
技术复盘深度不足，不利于长期质量改进。
建议：建立缺陷根因必填规范，技术负责人定期review根因分类质量。

4.4 修复验证不充分
{重新打开数}条缺陷被重新打开，部分缺陷在关闭后3~7天内被重新打开，说明：
（1）开发人员修复后自测场景单一，未覆盖边界条件；
（2）测试人员回归验证未覆盖原触发条件，尤其是跨模块联调场景；
（3）缺乏修复checklist和回归测试用例的强制关联。

4.5 性能与大数据场景验证不足
{大数据场景1}、{大数据场景2}、{大数据场景3}等场景均出现性能或稳定性问题。
当前测试以功能验证为主，缺乏容量测试基线。
建议：建立核心功能的容量测试基线（1000/3000/5000量级），在集成测试阶段引入压测环节。
```

### 改进建议模板

```
五、改进建议

5.1 开发过程改进
   （1）加强代码评审，特别是功能逻辑复杂、边界条件多的模块（如{模块1}、{模块2}、{模块3}）；
   （2）提升单元测试覆盖率，功能实现逻辑错误类缺陷占比{占比}%，通过单测可有效降低此类缺陷；
   （3）规范缺陷根因分类，当前{占比}%的缺陷根因为"其他/其他"，不利于后续质量分析和改进；
   （4）{严重缺陷高发模块}严重缺陷高达{数量}条，建议对该模块进行专项代码走查和重构评估。

5.2 测试过程改进
   （1）加强缺陷提交规范，所有缺陷均已归属具体模块，相较上一版本有明显改善；
   （2）增加接口自动化测试覆盖，减少回归测试人力投入；
   （3）在集成测试前增加冒烟测试环节，提前拦截严重级别缺陷；
   （4）{新功能模块}作为新功能，建议补充专项测试方案，避免挂起缺陷过多（当前{数量}条）。

5.3 需求管理改进
   （1）加强需求评审参与度，需求问题相关缺陷占比约{占比}%，部分缺陷根因是需求不明确或需求描述错误；
   （2）建立需求变更影响评估机制，避免变更引入新的缺陷；
   （3）对于"需求问题|功能问题"复合类型缺陷，建议建立需求-开发联调机制，确保需求理解一致性。
```

### 测试结论模板

```
六、测试结论

1. 缺陷密度与质量评估
   本次迭代共记录缺陷{总数}条，严重及以上缺陷{严重数}条，占比{严重占比}%。
   缺陷整体关闭率{关闭率}%，剩余未关闭{未关闭数}条。
   {重新打开数}条缺陷被重新打开，反映出修复验证环节存在疏漏。
   从缺陷趋势看，{趋势描述}，系统质量趋于稳定。
   关闭时间跨度为{最早关闭}至{最晚关闭}，修复验证工作持续有效。

2. 模块质量评估
   {模块1}缺陷密度最高（{占比}%），是重点风险模块。
   {模块2}严重缺陷占比最高（{严重数}条），需重点关注审批流程和状态变更逻辑。
   {模块3}（{占比}%）涉及大数据量场景下的性能和稳定性。
   {模块4}（{占比}%）状态机逻辑复杂，抑制与推送机制不完善。
   {新功能模块}作为新功能模块引入{数量}条缺陷，其中{挂起数}条挂起，风险需持续关注。

3. 发布建议
   综合考虑缺陷数量、严重程度分布、关闭率、缺陷趋势及遗留风险，建议：
   （1）{致命数}条致命缺陷和{严重数}条严重缺陷已基本修复关闭，系统核心功能风险可控；
   （2）剩余{新状态数}条"新"状态缺陷和{接受处理数}条"接受/处理"缺陷必须在发布前完成修复验证；
   （3）{挂起数}条挂起缺陷（{挂起模块分布}）需明确处理方案，建议延期或专项修复；
   （4）{转需求数}条转需求缺陷和{延期数}条延期缺陷需产品侧确认后续迭代安排；
   （5）建议在发布前进行高风险模块（{模块列表}）全量回归测试，并执行性能基线验证。

4. 下一步核心任务
   （1）{日期}前清零遗留缺陷，确保严重级问题不带入生产环境；
   （2）{日期}前完成{模块1}、{模块2}、{模块3}专项重构，补齐异常场景和性能测试；
   （3）建立需求评审 + 代码评审 + 缺陷根因度量 + 容量测试的四层质量门禁，防止同类问题重复发生。
```
