import pandas as pd
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from datetime import datetime

# 读取数据
df = pd.read_excel('c:/Users/wdjlw/iCloudDrive/AI_Python2026/低空测试脚本2026/迭代1.4.0过程数据及缺陷/低空空管自动化系统_缺陷_20260507201556.xlsx')

# 计算统计数据
total_defects = len(df)
severity_counts = df['严重程度'].value_counts()
status_counts = df['状态'].value_counts()
priority_counts = df['优先级'].value_counts()
category_counts = df['问题大类'].value_counts()
reason_counts = df['缺陷原因分类'].value_counts()
module_counts = df['模块'].value_counts()
creator_counts = df['创建人'].value_counts()
responsibility_counts = df['问题责任人'].value_counts()
df['创建日期'] = pd.to_datetime(df['创建时间']).dt.date
daily_counts = df['创建日期'].value_counts().sort_index()
severity_status = pd.crosstab(df['严重程度'], df['状态'])
iteration_counts = df['迭代'].value_counts()

# 未关闭缺陷
unclosed = df[df['状态'].isin(['新', '接受/处理', '挂起'])]
unclosed_count = len(unclosed)

# 严重缺陷模块分布
severe_df = df[df['严重程度'].isin(['致命', '严重'])]
severe_module = severe_df['模块'].value_counts()

# 关闭时间
df['关闭日期'] = pd.to_datetime(df['关闭时间'], errors='coerce').dt.date
close_dates = df['关闭日期'].dropna()

# 创建文档
doc = Document()

def set_chinese_font(run, font_name='微软雅黑', font_size=10.5, bold=False, color=RGBColor(0,0,0)):
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color

# 标题
title = doc.add_heading('低空空管自动化系统迭代1.4.0集成测试总结报告', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
for run in title.runs:
    set_chinese_font(run, font_size=22, bold=True)

# 副标题
subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run('（V2.0 更新版）')
set_chinese_font(run, font_size=14, bold=True, color=RGBColor(128,128,128))

info_para = doc.add_paragraph()
info_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
info_run = info_para.add_run(f'报告生成日期：{datetime.now().strftime("%Y年%m月%d日")}  |  数据来源：缺陷管理系统导出')
set_chinese_font(info_run, font_size=10)

doc.add_paragraph()

# ===== 1. 测试概述 =====
doc.add_heading('一、测试概述', level=1)
p = doc.add_paragraph()
run = p.add_run(
    f'本次迭代1.4.0（迭代五）集成测试主要针对低空空管自动化系统的功能完善、缺陷修复及性能优化进行验证。'
    f'测试覆盖运维监控子系统（接收机管理）、空管自动化平台（态势监视、告警管理、任务计划、数字孪生、系统管理）等核心模块。'
    f'测试周期为2026年4月13日至2026年5月7日，共发现缺陷{total_defects}条，其中归属迭代五（V1.4.0）的缺陷{iteration_counts.iloc[0]}条。'
    f'整体缺陷关闭率{(status_counts.get("已关闭", 0) + status_counts.get("已解决", 0))/total_defects*100:.1f}%，'
    f'严重级别以上缺陷关闭率{(severity_status.loc[severity_status.index.isin(["致命","严重"]), ["已关闭","已解决"]].sum().sum() / max(severe_df.shape[0], 1))*100:.1f}%，'
    f'测试工作基本达到预期目标。'
)
set_chinese_font(run, font_size=10.5)

# ===== 2. 缺陷总体统计 =====
doc.add_heading('二、缺陷总体统计', level=1)

# 2.1 缺陷总数与状态分布
doc.add_heading('2.1 缺陷总数与状态分布', level=2)
p = doc.add_paragraph()
run = p.add_run(f'本次迭代测试共记录缺陷 {total_defects} 条，各状态分布如下：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['状态', '数量', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for status, count in status_counts.items():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(status))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

closed_count = status_counts.get("已关闭", 0)
resolved_count = status_counts.get("已解决", 0)
pending_count = status_counts.get("新", 0) + status_counts.get("接受/处理", 0) + status_counts.get("挂起", 0)
p = doc.add_paragraph()
run = p.add_run(
    f'缺陷关闭率：{(closed_count+resolved_count)/total_defects*100:.1f}%'
    f'（已关闭{closed_count}条 + 已解决{resolved_count}条），'
    f'剩余未关闭缺陷{pending_count}条（新{status_counts.get("新", 0)}条、接受/处理{status_counts.get("接受/处理", 0)}条、挂起{status_counts.get("挂起", 0)}条）。'
)
set_chinese_font(run, font_size=10.5)

# 2.2 严重程度分布
doc.add_heading('2.2 严重程度分布', level=2)
p = doc.add_paragraph()
run = p.add_run('缺陷按严重程度分布统计如下：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=4)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['严重程度', '数量', '占比', '状态说明']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

severity_order = ['致命', '严重', '一般', '提示', '建议']
for sev in severity_order:
    count = severity_counts.get(sev, 0)
    sev_status = severity_status.loc[sev] if sev in severity_status.index else pd.Series()
    unclosed_sev = sev_status.get('新', 0) + sev_status.get('接受/处理', 0) + sev_status.get('挂起', 0)
    status_desc = f'未关闭{unclosed_sev}条' if unclosed_sev > 0 else '全部关闭'
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(sev)
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    run = row_cells[3].paragraphs[0].add_run(status_desc)
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

severe_total = severity_counts.get("致命", 0) + severity_counts.get("严重", 0)
p = doc.add_paragraph()
run = p.add_run(
    f'关键说明：致命缺陷{severity_counts.get("致命", 0)}条，严重缺陷{severity_counts.get("严重", 0)}条，'
    f'严重及以上缺陷占比{severe_total/total_defects*100:.1f}%。'
    f'严重级别缺陷主要集中在功能实现逻辑错误和边界场景处理异常，其中空管自动化平台-任务计划模块严重缺陷最多（27条）。'
)
set_chinese_font(run, font_size=10.5)

# 2.3 优先级分布
doc.add_heading('2.3 优先级分布', level=2)
p = doc.add_paragraph()
run = p.add_run('缺陷按优先级分布统计如下：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['优先级', '数量', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for priority, count in priority_counts.items():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(priority))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# ===== 3. 缺陷分析 =====
doc.add_heading('三、缺陷分析', level=1)

# 3.1 迭代归属分析
doc.add_heading('3.1 迭代归属分析', level=2)
p = doc.add_paragraph()
run = p.add_run('缺陷按迭代归属分布：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['迭代', '数量', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for iteration, count in iteration_counts.head(5).items():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(iteration))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# 3.2 问题类型分析
doc.add_heading('3.2 问题类型分析', level=2)
p = doc.add_paragraph()
run = p.add_run('按问题大类统计，缺陷分布如下：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['问题大类', '数量', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for cat, count in category_counts.head(6).items():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(cat))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
run = p.add_run(
    '分析结论：功能问题占比最高（46.7%），是本次迭代的主要问题类型，主要集中在功能实现逻辑错误、边界条件处理不完善等方面。'
    '界面问题和需求问题分别占5.8%和4.9%，提示前端交互和需求理解方面仍有改进空间。'
    '值得注意的是有3条缺陷为"需求问题|功能问题"的复合类型，说明需求与实现的关联性需要加强。'
)
set_chinese_font(run, font_size=10.5)

# 3.3 缺陷根因分析
doc.add_heading('3.3 缺陷根因分析', level=2)
p = doc.add_paragraph()
run = p.add_run('按缺陷原因分类统计TOP10：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['缺陷原因分类', '数量', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for reason, count in reason_counts.head(10).items():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(reason))
    set_chinese_font(run, font_size=9)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
run = p.add_run(
        '分析结论：功能实现逻辑错误（16.4%）和功能实现其他问题（10.2%）合计占比26.6%，是缺陷产生的首要原因。'
        '其次为"其他/其他"分类（21.8%），说明部分缺陷的根因归类不够明确，需要加强缺陷根因分析规范性。'
        '需求问题相关缺陷合计占比约15%，建议在需求评审阶段加强参与度和评审深度。'
    )
set_chinese_font(run, font_size=10.5)

# 3.4 模块分布分析
doc.add_heading('3.4 模块分布分析', level=2)
p = doc.add_paragraph()
run = p.add_run('缺陷按模块分布统计如下：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=4)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['模块', '缺陷总数', '严重+致命', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for module, count in module_counts.head(9).items():
    severe_cnt = severe_module.get(module, 0)
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(module))
    set_chinese_font(run, font_size=10)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(str(severe_cnt))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[3].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
run = p.add_run(
    '分析结论：运维监控子系统-接收机管理模块缺陷最多（71条，31.6%），是本次迭代的重点关注模块，主要涉及设备注册、配置下发、升级管理、日志下载等功能。'
    '空管自动化平台-任务计划模块（53条，23.6%）和态势监视模块（56条，24.9%）次之，'
    '其中任务计划模块严重缺陷占比最高（27条），需要重点关注审批流程、状态变更等核心逻辑。'
    '数字孪生模块新增16条缺陷，作为新功能模块风险需持续关注。'
)
set_chinese_font(run, font_size=10.5)

# 3.5 严重级别与状态交叉分析
doc.add_heading('3.5 严重级别与状态交叉分析', level=2)
p = doc.add_paragraph()
run = p.add_run('严重级别与当前状态交叉统计：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=len(severity_status.columns)+1)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
run = hdr_cells[0].paragraphs[0].add_run('严重程度\\状态')
set_chinese_font(run, font_size=10.5, bold=True)
hdr_cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for i, col in enumerate(severity_status.columns):
    run = hdr_cells[i+1].paragraphs[0].add_run(str(col))
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i+1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for idx, row in severity_status.iterrows():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(idx))
    set_chinese_font(run, font_size=10.5)
    row_cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for i, val in enumerate(row):
        run = row_cells[i+1].paragraphs[0].add_run(str(int(val)))
        set_chinese_font(run, font_size=10.5)
        row_cells[i+1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
run = p.add_run(
    '分析结论：致命缺陷1条、严重缺陷58条中，仅1条严重缺陷（任务计划模块）转为需求处理，'
    '其余均已关闭或已解决。高优先级缺陷处理情况良好，但仍有7条一般级别缺陷处于挂起状态、3条处于新状态，'
    '需要开发团队及时响应处理。'
)
set_chinese_font(run, font_size=10.5)

# 3.6 缺陷趋势分析
doc.add_heading('3.6 缺陷创建趋势分析', level=2)
p = doc.add_paragraph()
run = p.add_run('按日期统计缺陷创建趋势：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['日期', '新增缺陷数', '累计缺陷数']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

cumulative = 0
for date, count in daily_counts.items():
    cumulative += count
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(date))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(str(cumulative))
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
run = p.add_run(
    '分析结论：缺陷发现高峰期集中在4月16日（28条）和4月23日（32条），这与集成测试全面验证及回归测试阶段有关。'
    '4月23日后缺陷数量明显下降，4月29日后仅新增8条，说明系统质量趋于稳定。'
    f'关闭时间跨度为{close_dates.min()}至{close_dates.max()}，修复验证工作持续跟进中。'
)
set_chinese_font(run, font_size=10.5)

# 3.7 人员分析
doc.add_heading('3.7 缺陷创建与责任人分析', level=2)
p = doc.add_paragraph()
run = p.add_run('缺陷创建人分布TOP3：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['创建人', '提交缺陷数', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for creator, count in creator_counts.head(3).items():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(creator))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
run = p.add_run('问题责任人分布TOP5：')
set_chinese_font(run, font_size=10.5)

table = doc.add_table(rows=1, cols=3)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['问题责任人', '负责缺陷数', '占比']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for resp, count in responsibility_counts.head(5).items():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(resp))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[1].paragraphs[0].add_run(str(count))
    set_chinese_font(run, font_size=10.5)
    run = row_cells[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%')
    set_chinese_font(run, font_size=10.5)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# 3.8 未关闭缺陷清单
doc.add_heading('3.8 未关闭缺陷清单（重点关注）', level=2)
p = doc.add_paragraph()
run = p.add_run(f'当前未关闭缺陷共{unclosed_count}条，明细如下：')
set_chinese_font(run, font_size=10.5, bold=True)

table = doc.add_table(rows=1, cols=5)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ['ID', '状态', '严重程度', '模块', '标题摘要']
for i, header in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(header)
    set_chinese_font(run, font_size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for _, row_data in unclosed.iterrows():
    row_cells = table.add_row().cells
    run = row_cells[0].paragraphs[0].add_run(str(row_data['ID']))
    set_chinese_font(run, font_size=9)
    run = row_cells[1].paragraphs[0].add_run(str(row_data['状态']))
    set_chinese_font(run, font_size=9)
    run = row_cells[2].paragraphs[0].add_run(str(row_data['严重程度']))
    set_chinese_font(run, font_size=9)
    run = row_cells[3].paragraphs[0].add_run(str(row_data['模块']) if pd.notna(row_data['模块']) else '未分类')
    set_chinese_font(run, font_size=9)
    title_short = str(row_data['标题'])[:40] + '...' if len(str(row_data['标题'])) > 40 else str(row_data['标题'])
    run = row_cells[4].paragraphs[0].add_run(title_short)
    set_chinese_font(run, font_size=9)
    for cell in row_cells:
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# ===== 4. 测试结论 =====
doc.add_heading('四、测试结论', level=1)
p = doc.add_paragraph()

run = p.add_run('1. 缺陷密度与质量评估\n')
set_chinese_font(run, font_size=10.5, bold=True)
run = p.add_run(
    f'   本次迭代共发现缺陷{total_defects}条，其中严重及以上缺陷{severe_total}条，占比{severe_total/total_defects*100:.1f}%。'
    f'缺陷整体关闭率达{(closed_count+resolved_count)/total_defects*100:.1f}%，'
    f'剩余未关闭缺陷{pending_count}条（新{status_counts.get("新", 0)}条、接受/处理{status_counts.get("接受/处理", 0)}条、挂起{status_counts.get("挂起", 0)}条、转需求{status_counts.get("转需求", 0)}条、延期{status_counts.get("延期", 0)}条）。'
    f'从缺陷趋势看，4月23日后缺陷数量明显下降，4月29日后仅新增8条，系统质量趋于稳定。'
    f'关闭时间跨度为{close_dates.min()}至{close_dates.max()}，修复验证工作持续有效。\n\n'
)
set_chinese_font(run, font_size=10.5)

run = p.add_run('2. 模块质量评估\n')
set_chinese_font(run, font_size=10.5, bold=True)
run = p.add_run(
    '   运维监控子系统-接收机管理模块缺陷密度最高（31.6%），是该迭代的重点风险模块，建议后续加强该模块的代码评审和单元测试覆盖。'
    '空管自动化平台-任务计划模块（23.6%）严重缺陷占比最高（27条），需重点关注审批流程和状态变更逻辑。'
    '态势监视模块（24.9%）涉及数据处理逻辑和边界场景。数字孪生作为新功能模块引入16条缺陷，风险需持续关注。\n\n'
)
set_chinese_font(run, font_size=10.5)

run = p.add_run('3. 测试充分性评估\n')
set_chinese_font(run, font_size=10.5, bold=True)
run = p.add_run(
    '   本次测试覆盖了运维监控、态势监视、告警管理、任务计划、数字孪生、系统管理等核心功能模块，功能问题占比46.7%，说明测试对功能逻辑的验证较为充分。'
    '界面问题和需求问题合计占比约10.7%，说明在UI交互和需求符合性方面也有较好的覆盖。'
    f'缺陷发生阶段全部为"内部研发阶段"，说明问题均在测试环节发现，未流入客户现场。\n\n'
)
set_chinese_font(run, font_size=10.5)

run = p.add_run('4. 发布建议\n')
set_chinese_font(run, font_size=10.5, bold=True)
run = p.add_run('   综合考虑缺陷数量、严重程度分布、关闭率及缺陷趋势，建议：\n')
set_chinese_font(run, font_size=10.5)
run = p.add_run(f'   （1）{severity_counts.get("致命", 0)}条致命缺陷和{severity_counts.get("严重", 0)}条严重缺陷已基本修复关闭，系统核心功能风险可控；\n')
set_chinese_font(run, font_size=10.5)
run = p.add_run(f'   （2）剩余{status_counts.get("新", 0)}条"新"状态缺陷和{status_counts.get("接受/处理", 0)}条"接受/处理"缺陷建议在发布前完成修复验证；\n')
set_chinese_font(run, font_size=10.5)
run = p.add_run(f'   （3）{status_counts.get("挂起", 0)}条挂起缺陷需明确处理方案（其中数字孪生模块4条、态势监视3条、告警管理1条、接收机管理1条），避免遗留至生产环境；\n')
set_chinese_font(run, font_size=10.5)
run = p.add_run(f'   （4）{status_counts.get("转需求", 0)}条转需求缺陷和{status_counts.get("延期", 0)}条延期缺陷需产品侧确认后续迭代安排；\n')
set_chinese_font(run, font_size=10.5)
run = p.add_run(f'   （5）建议在发布前进行一次全量回归测试，重点验证接收机管理、任务计划、态势监视等高风险模块。\n')
set_chinese_font(run, font_size=10.5)

# ===== 5. 改进建议 =====
doc.add_heading('五、改进建议', level=1)
p = doc.add_paragraph()

run = p.add_run('1. 开发过程改进\n')
set_chinese_font(run, font_size=10.5, bold=True)
run = p.add_run(
    '   （1）加强代码评审，特别是功能逻辑复杂、边界条件多的模块（如接收机管理、任务计划审批流、态势数据处理）；\n'
    '   （2）提升单元测试覆盖率，功能实现逻辑错误类缺陷占比16.4%，通过单测可有效降低此类缺陷；\n'
    '   （3）规范缺陷根因分类，当前21.8%的缺陷根因为"其他/其他"，不利于后续质量分析和改进；\n'
    '   （4）任务计划模块严重缺陷高达27条，建议对该模块进行专项代码走查和重构评估。\n\n'
)
set_chinese_font(run, font_size=10.5)

run = p.add_run('2. 测试过程改进\n')
set_chinese_font(run, font_size=10.5, bold=True)
run = p.add_run(
    '   （1）加强缺陷提交规范，所有缺陷均已归属具体模块，相较上一版本有明显改善；\n'
    '   （2）增加接口自动化测试覆盖，减少回归测试人力投入；\n'
    '   （3）在集成测试前增加冒烟测试环节，提前拦截严重级别缺陷；\n'
    '   （4）数字孪生模块作为新功能，建议补充专项测试方案，避免挂起缺陷过多（当前4条）。\n\n'
)
set_chinese_font(run, font_size=10.5)

run = p.add_run('3. 需求管理改进\n')
set_chinese_font(run, font_size=10.5, bold=True)
run = p.add_run(
    '   （1）加强需求评审参与度，需求问题相关缺陷占比约15%，部分缺陷根因是需求不明确或需求描述错误；\n'
    '   （2）建立需求变更影响评估机制，避免变更引入新的缺陷；\n'
    '   （3）对于"需求问题|功能问题"复合类型缺陷，建议建立需求-开发联调机制，确保需求理解一致性。\n'
)
set_chinese_font(run, font_size=10.5)

# 保存文档
output_path = 'c:/Users/wdjlw/iCloudDrive/AI_Python2026/低空测试脚本2026/迭代1.4.0过程数据及缺陷/低空空管自动化系统_迭代1.4.0集成测试总结报告_V2.0.docx'
doc.save(output_path)
print(f'报告已生成：{output_path}')
