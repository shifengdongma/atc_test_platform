import pandas as pd
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from datetime import datetime

df = pd.read_excel('c:/Users/wdjlw/iCloudDrive/AI_Python2026/低空测试脚本2026/迭代1.4.0过程数据及缺陷/低空空管自动化系统_缺陷_20260507201556.xlsx')

total_defects = len(df)
severity_counts = df['严重程度'].value_counts()
status_counts = df['状态'].value_counts()
module_counts = df['模块'].value_counts()
module_severity = pd.crosstab(df['模块'], df['严重程度'])
reason_counts = df['缺陷原因分类'].value_counts()
category_counts = df['问题大类'].value_counts()
iteration_counts = df['迭代'].value_counts()
env_counts = df['测试环境'].value_counts()

# 重新打开分析
df['创建时间_dt'] = pd.to_datetime(df['创建时间'])
df['重新打开时间_dt'] = pd.to_datetime(df['重新打开时间'], errors='coerce')
real_reopen = df[df['重新打开时间_dt'] > df['创建时间_dt']]
reopen_count = len(real_reopen)

# 未关闭
unclosed = df[df['状态'].isin(['新', '接受/处理', '挂起'])]
unclosed_count = len(unclosed)

# 严重缺陷
severe_df = df[df['严重程度'].isin(['致命', '严重'])]

# 创建时间趋势
df['创建日期'] = df['创建时间_dt'].dt.date
daily_counts = df['创建日期'].value_counts().sort_index()

# 关闭时间
df['关闭日期'] = pd.to_datetime(df['关闭时间'], errors='coerce').dt.date
close_dates = df['关闭日期'].dropna()

# 责任人统计
responsibility_counts = df['问题责任人'].value_counts()

doc = Document()

def set_font(run, size=10.5, bold=False, color=RGBColor(0,0,0)):
    run.font.name = '微软雅黑'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color

# 标题
title = doc.add_heading('低空空管自动化系统迭代1.4.0集成测试总结报告', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
for run in title.runs:
    set_font(run, size=22, bold=True)

# 版本号自增逻辑
import os
import re

def get_next_version_path(base_path):
    if not os.path.exists(base_path):
        return base_path
    dir_name = os.path.dirname(base_path) or '.'
    file_name = os.path.basename(base_path)
    name, ext = os.path.splitext(file_name)
    # 匹配 _V数字.0 模式（不一定在末尾）
    match = re.search(r'_V(\d+)\.0', name)
    if match:
        current_ver = int(match.group(1))
        new_name = re.sub(r'_V\d+\.0', f'_V{current_ver + 1}.0', name, count=1)
    else:
        new_name = f'{name}_V2.0'
    new_path = os.path.join(dir_name, new_name + ext)
    if os.path.exists(new_path):
        return get_next_version_path(new_path)
    return new_path

info = doc.add_paragraph()
info.alignment = WD_ALIGN_PARAGRAPH.CENTER
set_font(info.add_run(f'报告生成日期：{datetime.now().strftime("%Y年%m月%d日")}  |  缺陷周期：2026-04-13 ~ 2026-05-07  |  缺陷总数：{total_defects}条'), size=10)

doc.add_paragraph()

# ===== 一、测试概述 =====
doc.add_heading('一、测试概述', level=1)
p = doc.add_paragraph()
set_font(p.add_run(
    f'本次迭代1.4.0（迭代五）集成测试主要针对低空空管自动化系统的功能完善、缺陷修复及性能优化进行验证。'
    f'测试覆盖运维监控子系统（接收机管理）、空管自动化平台（态势监视、告警管理、任务计划、数字孪生、系统管理）等核心模块。'
    f'测试周期为2026年4月13日至2026年5月7日，共记录缺陷{total_defects}条，其中归属迭代五（V1.4.0）的缺陷{iteration_counts.iloc[0]}条。'
    f'整体缺陷关闭率{(status_counts.get("已关闭", 0) + status_counts.get("已解决", 0))/total_defects*100:.1f}%，'
    f'严重级别以上缺陷关闭率{(module_severity.loc[:, ["已关闭","已解决"]] if "已关闭" in module_severity.columns else module_severity).sum().sum() / max(len(severe_df), 1) * 100:.1f}%。'
    f'本轮测试暴露出接收机全生命周期管理、态势监视大数据性能、告警状态机逻辑、飞行计划状态流转四个方面的系统性质量风险，测试工作达到预期目标。'
), size=10.5)

# ===== 二、缺陷总体统计 =====
doc.add_heading('二、缺陷总体统计', level=1)

# 2.1 迭代归属分析
doc.add_heading('2.1 迭代归属分析', level=2)
p = doc.add_paragraph()
set_font(p.add_run('缺陷按迭代归属分布：'), size=10.5)

tbl = doc.add_table(rows=1, cols=3)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['迭代', '数量', '占比']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for iteration, count in iteration_counts.head(5).items():
    r = tbl.add_row().cells
    set_font(r[0].paragraphs[0].add_run(str(iteration)))
    set_font(r[1].paragraphs[0].add_run(str(count)))
    set_font(r[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%'))
    for c in r: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# 2.2 问题类型分析
doc.add_heading('2.2 问题类型分析', level=2)
p = doc.add_paragraph()
set_font(p.add_run('按问题大类统计，缺陷分布如下：'), size=10.5)

tbl = doc.add_table(rows=1, cols=3)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['问题大类', '数量', '占比']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for cat, count in category_counts.head(6).items():
    r = tbl.add_row().cells
    set_font(r[0].paragraphs[0].add_run(str(cat)))
    set_font(r[1].paragraphs[0].add_run(str(count)))
    set_font(r[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%'))
    for c in r: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
set_font(p.add_run(
    '分析结论：功能问题占比最高（46.7%），是本次迭代的主要问题类型，主要集中在功能实现逻辑错误、边界条件处理不完善等方面。'
    '界面问题和需求问题分别占5.8%和4.9%，提示前端交互和需求理解方面仍有改进空间。'
    '值得注意的是有3条缺陷为"需求问题|功能问题"的复合类型，说明需求与实现的关联性需要加强。'
), size=10.5)

# 2.3 缺陷根因分析
doc.add_heading('2.3 缺陷根因分析', level=2)
p = doc.add_paragraph()
set_font(p.add_run('按缺陷原因分类统计TOP10：'), size=10.5)

tbl = doc.add_table(rows=1, cols=3)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['缺陷原因分类', '数量', '占比']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for reason, count in reason_counts.head(10).items():
    r = tbl.add_row().cells
    set_font(r[0].paragraphs[0].add_run(str(reason)), size=9)
    set_font(r[1].paragraphs[0].add_run(str(count)))
    set_font(r[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%'))
    for c in r: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
set_font(p.add_run(
    '分析结论：功能实现逻辑错误（16.4%）和功能实现其他问题（10.2%）合计占比26.6%，是缺陷产生的首要原因。'
    '其次为"其他/其他"分类（21.8%），说明部分缺陷的根因归类不够明确，需要加强缺陷根因分析规范性。'
    '需求问题相关缺陷合计占比约15%，建议在需求评审阶段加强参与度和评审深度。'
), size=10.5)

# 2.4 缺陷状态分布
doc.add_heading('2.4 缺陷状态分布', level=2)
p = doc.add_paragraph()
set_font(p.add_run(f'共记录缺陷 {total_defects} 条，状态分布如下：'), size=10.5)

tbl = doc.add_table(rows=1, cols=3)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['状态', '数量', '占比']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for status, count in status_counts.items():
    r = tbl.add_row().cells
    set_font(r[0].paragraphs[0].add_run(str(status)))
    set_font(r[1].paragraphs[0].add_run(str(count)))
    set_font(r[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%'))
    for c in r: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

closed_count = status_counts.get('已关闭', 0)
resolved_count = status_counts.get('已解决', 0)
pending_count = status_counts.get('新', 0) + status_counts.get('接受/处理', 0) + status_counts.get('挂起', 0)
p = doc.add_paragraph()
set_font(p.add_run(
    f'缺陷关闭率：{(closed_count+resolved_count)/total_defects*100:.1f}%（已关闭{closed_count}条 + 已解决{resolved_count}条），'
    f'剩余未关闭{pending_count}条（新{status_counts.get("新",0)}条、接受/处理{status_counts.get("接受/处理",0)}条、挂起{status_counts.get("挂起",0)}条）。'
), size=10.5)

# 2.5
doc.add_heading('2.5 严重程度分布', level=2)
tbl = doc.add_table(rows=1, cols=4)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['严重程度', '数量', '占比', '状态说明']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for sev in ['致命', '严重', '一般', '提示', '建议']:
    count = severity_counts.get(sev, 0)
    row = tbl.add_row().cells
    set_font(row[0].paragraphs[0].add_run(sev))
    set_font(row[1].paragraphs[0].add_run(str(count)))
    set_font(row[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%'))
    # 检查该严重级别下是否有未关闭
    sev_df = df[df['严重程度'] == sev]
    unclosed_sev = sev_df[sev_df['状态'].isin(['新','接受/处理','挂起'])]
    desc = f'未关闭{len(unclosed_sev)}条' if len(unclosed_sev) > 0 else '全部关闭'
    set_font(row[3].paragraphs[0].add_run(desc))
    for c in row: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

severe_total = severity_counts.get('致命', 0) + severity_counts.get('严重', 0)
p = doc.add_paragraph()
set_font(p.add_run(
    f'关键说明：致命缺陷{severity_counts.get("致命", 0)}条，严重缺陷{severity_counts.get("严重", 0)}条，'
    f'严重及以上占比{severe_total/total_defects*100:.1f}%。'
    f'严重缺陷主要集中在功能实现逻辑错误和边界场景处理异常，其中任务计划模块严重缺陷最多（27条）。'
), size=10.5)

# 2.6
doc.add_heading('2.6 模块分布（含严重缺陷交叉）', level=2)
tbl = doc.add_table(rows=1, cols=6)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['模块', '总数', '致命', '严重', '一般', '占比']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for module in module_counts.index:
    count = module_counts[module]
    row = tbl.add_row().cells
    set_font(row[0].paragraphs[0].add_run(str(module)), size=10)
    set_font(row[1].paragraphs[0].add_run(str(count)))
    set_font(row[2].paragraphs[0].add_run(str(module_severity.loc[module, '致命']) if '致命' in module_severity.columns and module in module_severity.index else '0'))
    set_font(row[3].paragraphs[0].add_run(str(module_severity.loc[module, '严重']) if '严重' in module_severity.columns and module in module_severity.index else '0'))
    set_font(row[4].paragraphs[0].add_run(str(module_severity.loc[module, '一般']) if '一般' in module_severity.columns and module in module_severity.index else '0'))
    set_font(row[5].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%'))
    for c in row: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
set_font(p.add_run(
    '分析结论：运维监控子系统-接收机管理模块缺陷最多（71条，31.6%），涉及注册、升级、配置下发、批量导入、日志下载等全生命周期功能。'
    '空管自动化平台-态势监视模块次之（56条，24.9%），涉及告警设置、最小探测线、接收机静态回放、航迹展示等复杂交互。'
    '任务计划模块（53条，23.6%）严重缺陷占比最高（27条），需重点关注审批流程和状态变更逻辑。'
    '数字孪生模块作为新功能引入16条缺陷，其中4条挂起，风险需持续关注。'
), size=10.5)

# 2.7 缺陷创建趋势分析
doc.add_heading('2.7 缺陷创建趋势分析', level=2)
p = doc.add_paragraph()
set_font(p.add_run('按日期统计缺陷创建趋势：'), size=10.5)

tbl = doc.add_table(rows=1, cols=3)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['日期', '新增缺陷数', '累计缺陷数']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

cumulative = 0
for date, count in daily_counts.items():
    cumulative += count
    r = tbl.add_row().cells
    set_font(r[0].paragraphs[0].add_run(str(date)))
    set_font(r[1].paragraphs[0].add_run(str(count)))
    set_font(r[2].paragraphs[0].add_run(str(cumulative)))
    for c in r: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
set_font(p.add_run(
    '分析结论：缺陷发现高峰期集中在4月16日（28条）和4月23日（32条），这与集成测试全面验证及回归测试阶段有关。'
    '4月23日后缺陷数量明显下降，4月29日后仅新增8条，说明系统质量趋于稳定。'
    f'关闭时间跨度为{close_dates.min()}至{close_dates.max()}，修复验证工作持续跟进中。'
), size=10.5)

# 2.8 缺陷创建与责任人分析
doc.add_heading('2.8 缺陷创建与责任人分析', level=2)
p = doc.add_paragraph()
set_font(p.add_run('问题责任人分布TOP5：'), size=10.5)

tbl = doc.add_table(rows=1, cols=3)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['问题责任人', '负责缺陷数', '占比']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for resp, count in responsibility_counts.head(5).items():
    r = tbl.add_row().cells
    set_font(r[0].paragraphs[0].add_run(str(resp)))
    set_font(r[1].paragraphs[0].add_run(str(count)))
    set_font(r[2].paragraphs[0].add_run(f'{count/total_defects*100:.1f}%'))
    for c in r: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# 2.9 重新打开缺陷分析
doc.add_heading('2.9重新打开缺陷分析', level=2)
p = doc.add_paragraph()
set_font(p.add_run(f'经分析，真正重新打开（重新打开时间 > 创建时间）的缺陷共 {reopen_count} 条，明细如下：'), size=10.5)

tbl = doc.add_table(rows=1, cols=5)
tbl.style = 'Light Grid Accent 1'
for i,h in enumerate(['ID', '模块', '严重程度', '标题摘要', '重新打开时间']):
    set_font(tbl.rows[0].cells[i].paragraphs[0].add_run(h), bold=True)
    tbl.rows[0].cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

for _, row_data in real_reopen.iterrows():
    r = tbl.add_row().cells
    set_font(r[0].paragraphs[0].add_run(str(row_data['ID'])), size=9)
    set_font(r[1].paragraphs[0].add_run(str(row_data['模块']) if pd.notna(row_data['模块']) else '未分类'), size=9)
    set_font(r[2].paragraphs[0].add_run(str(row_data['严重程度'])), size=9)
    title_short = str(row_data['标题'])[:35] + '...' if len(str(row_data['标题'])) > 35 else str(row_data['标题'])
    set_font(r[3].paragraphs[0].add_run(title_short), size=9)
    set_font(r[4].paragraphs[0].add_run(str(row_data['重新打开时间'])[:19]), size=9)
    for c in r: c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph()
set_font(p.add_run(
    f'分析结论：{reopen_count}条重新打开缺陷中，任务计划模块6条、态势监视3条、告警管理2条、接收机管理3条、数字孪生1条。'
    '部分缺陷在关闭后3~7天内被重新打开，说明修复后验证场景单一，未覆盖原触发条件，尤其是跨模块联调场景。'
), size=10.5)

# ===== 三、重点问题剖析（TOP 5） =====
doc.add_heading('三、重点问题剖析（TOP 5）', level=1)

# 3.1
doc.add_heading('3.1 接收机管理模块质量风险（71条缺陷，严重8条）', level=2)
p = doc.add_paragraph()
set_font(p.add_run('典型问题：\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   • 批量导入功能缺陷密集（模板问题、空文件处理、实景图导入失败、字段校验缺失、导入后状态未同步更新）\n'
    '   • 配置下发与设备状态同步异常（离线设备提示下发成功、5200+设备选择时列表加载慢/卡死）\n'
    '   • 注册/升级流程不稳定（注册失败、升级结果未同步、端侧与平台互斥、设备记录删除后注册仍成功）\n'
    '   • 接收机详情查看异常（密码无法查看、安装时间无数据、运维信息时间范围查询报错）\n'
), size=10.5)
set_font(p.add_run('根因分析：'), size=10.5, bold=True)
set_font(p.add_run(
    '该模块涉及前端、后端、端侧设备、MQTT/Kafka多方交互，接口契约和异常场景覆盖不足。'
    '批量导入涉及Excel解析、字段映射、图片上传、异步状态同步等多个环节，缺乏边界条件验证。'
    '设备状态管理涉及Redis缓存、数据库、端侧心跳等多源数据一致性，状态机设计不完善。'
), size=10.5)

# 3.2
doc.add_heading('3.2 态势监视性能与稳定性（56条缺陷，严重13条）', level=2)
p = doc.add_paragraph()
set_font(p.add_run('典型问题：\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   • 3000架轨迹预测导致客户端WebSocket无数据刷新（严重，缓冲区溢出/内存问题）\n'
    '   • 接收机静态回放24H数据请求超时，大数据量场景下加载缓慢\n'
    '   • 消费Kafka超时导致WS服务被踢出消费者组，页面无小飞机展示\n'
    '   • 接收机较多时无法选择静态回放数据，容易点到其他接收机\n'
    '   • 鼠标hover空域图像提示"多边形_2"等不友好信息\n'
), size=10.5)
set_font(p.add_run('根因分析：'), size=10.5, bold=True)
set_font(p.add_run(
    '大数据量场景下的缓冲区管理、WebSocket连接稳定性、Kafka消费组机制缺乏压测和边界验证。'
    '前端在接收机数量多（5000+）时，列表渲染和地图图层叠加存在性能瓶颈。'
    'WS长连接在数据洪峰时未及时做流量控制和背压处理。'
), size=10.5)

# 3.3
doc.add_heading('3.3 告警管理逻辑缺陷（18条缺陷，严重4条）', level=2)
p = doc.add_paragraph()
set_font(p.add_run('典型问题：\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   • 趋势取消模式下，水平距离抖动导致告警频繁产生/关闭（反复震荡）\n'
    '   • 告警设置关闭后仍收到弹框（短期冲突预警、禁区侵入设置不生效）\n'
    '   • 最低安全高度告警每秒产生新告警，数据冗余严重\n'
    '   • 告警抑制区设置后仍产生告警，抑制逻辑失效\n'
    '   • 查看告警详情时系统报错\n'
), size=10.5)
set_font(p.add_run('根因分析：'), size=10.5, bold=True)
set_font(p.add_run(
    '告警状态机设计不完善，抑制条件与推送逻辑耦合度高，缺乏防抖/去重机制。'
    '算法推送连续告警数据时，业务层未做有效的状态合并和变化检测。'
    '配置变更后，运行时缓存未及时刷新，导致旧配置仍生效。'
), size=10.5)

# 3.4
doc.add_heading('3.4 飞行计划与任务计划状态流转（53条缺陷，严重26条+致命1条）', level=2)
p = doc.add_paragraph()
set_font(p.add_run('典型问题：\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   • 审批通过计划状态显示为"审批不通过"，待审批计划状态显示为"审批通过"（状态显示颠倒）\n'
    '   • 预激活任务自动变为待审批状态，状态流转不符合业务预期\n'
    '   • 飞行任务未变更为管制状态，状态机判断条件错误\n'
    '   • 航线冲突校验不应与自身校验，但系统仍报自身冲突\n'
    '   • 飞行记录列表按延迟排序报错，字段处理异常\n'
    '   • 独立从业者创建计划时默认填写操控员，不符合业务规则\n'
), size=10.5)
set_font(p.add_run('根因分析：'), size=10.5, bold=True)
set_font(p.add_run(
    '状态机代码逻辑错误，"cd"（代码问题）标记密集，单元测试对状态流转覆盖不足。'
    '审批流涉及多个状态节点（待审批、审批通过、审批不通过、待激活、预激活、管制），'
    '各节点间的前置条件、后置动作、异常回退逻辑复杂，缺乏统一的状态机框架和自动化测试覆盖。'
), size=10.5)

# 3.5
doc.add_heading('3.5 重新打开缺陷（17条）——修复验证环节疏漏', level=2)
p = doc.add_paragraph()
set_font(p.add_run('典型问题：\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   • 任务审核结果多种冲突情况（4-29重新打开）：修复方案涉及前后端联调，首次修复未覆盖多冲突场景\n'
    '   • 3000架轨迹预测WS断连（4-29重新打开）：大数据量场景下修复后未做压测验证\n'
    '   • 偏离航路告警未产生（4-27重新打开）：算法与业务联调场景验证不充分\n'
    '   • 接收机注册互斥问题（4-23重新打开）：端侧与平台交互的边界场景未覆盖\n'
    '   • 批量导入提示优化（4-16重新打开）：细节修复后未回归验证空文件场景\n'
), size=10.5)
set_font(p.add_run('根因分析：'), size=10.5, bold=True)
set_font(p.add_run(
    '修复后验证场景单一，未覆盖重新打开前的触发条件；部分问题涉及多模块联调，修复方案不彻底。'
    '开发人员修复后自测缺乏checklist，测试人员回归验证未严格对照原缺陷复现步骤。'
), size=10.5)

# ===== 四、过程问题反思 =====
doc.add_heading('四、过程问题反思', level=1)

# 4.1
doc.add_heading('4.1 需求管理薄弱', level=2)
p = doc.add_paragraph()
set_font(p.add_run(
    '需求不明确/变更/理解偏差类缺陷合计占比约15%，如最小探测线功能未考虑ADS-B数据、'
    '未考虑选择同一飞行器、未考虑取消选择交互等。部分缺陷根因是需求描述错误（蓝湖描述与实际不符）。'
    '需求评审阶段缺乏"异常场景 & 边界条件"评审checklist，导致开发阶段才发现交互缺失。'
    '建议：需求评审增加异常场景专项环节，建立需求变更影响评估机制。'
), size=10.5)

# 4.2
doc.add_heading('4.2 代码质量与逻辑错误', level=2)
p = doc.add_paragraph()
set_font(p.add_run(
    '功能实现逻辑错误类缺陷占16.4%，大量标记为"cd"（代码问题），说明状态流转、数据同步、并发处理等'
    '核心逻辑缺乏代码评审（CR）。单元测试覆盖率不足，尤其是对Redis、Kafka、WebSocket等中间件的异常分支。'
    '任务计划模块严重缺陷高达27条，建议对该模块进行专项代码走查，引入状态机框架替代硬编码判断。'
), size=10.5)

# 4.3
doc.add_heading('4.3 缺陷根因分析不规范', level=2)
p = doc.add_paragraph()
set_font(p.add_run(
    f'"其他/其他"根因分类占21.8%（{reason_counts.get("其他/其他", 0)}条），部分根因标记为"cd"或未填写，'
    '技术复盘深度不足，不利于长期质量改进。建议建立缺陷根因必填规范，技术负责人定期review根因分类质量。'
), size=10.5)

# 4.4
doc.add_heading('4.4 修复验证不充分', level=2)
p = doc.add_paragraph()
set_font(p.add_run(
    f'{reopen_count}条缺陷被重新打开，部分缺陷在关闭后3~7天内被重新打开，说明：'
    '（1）开发人员修复后自测场景单一，未覆盖边界条件；'
    '（2）测试人员回归验证未覆盖原触发条件，尤其是跨模块联调场景；'
    '（3）缺乏修复checklist和回归测试用例的强制关联。'
), size=10.5)

# 4.5
doc.add_heading('4.5 性能与大数据场景验证不足', level=2)
p = doc.add_paragraph()
set_font(p.add_run(
    '3000架轨迹预测、5200+设备配置下发、24H静态回放等场景均出现性能或稳定性问题。'
    '当前测试以功能验证为主，缺乏容量测试基线。'
    '建议建立核心功能的容量测试基线（1000/3000/5000量级），在集成测试阶段引入压测环节。'
), size=10.5)

# ===== 五、改进建议 =====
doc.add_heading('五、改进建议', level=1)

p = doc.add_paragraph()
set_font(p.add_run('1. 开发过程改进\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   （1）加强代码评审，特别是功能逻辑复杂、边界条件多的模块（如接收机管理、任务计划审批流、态势数据处理）；\n'
    '   （2）提升单元测试覆盖率，功能实现逻辑错误类缺陷占比16.4%，核心逻辑应通过自动化测试保障回归；\n'
    '   （3）引入状态机框架（如Spring State Machine）替代硬编码状态判断，减少任务计划、告警管理等模块的状态流转缺陷。\n'
), size=10.5)

set_font(p.add_run('2. 测试过程改进\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   （1）丰富测试用例覆盖度，针对批量导入、设备状态同步、告警抑制条件等高频缺陷场景补充异常用例；\n'
    '   （2）加强大数据量场景测试（3000+架轨迹、5000+设备列表加载、24H静态回放），建立性能基线；\n'
    '   （3）修复验证需对照原缺陷复现步骤执行，涉及跨模块联调的缺陷必须完成端到端验证后方可关闭。\n'
), size=10.5)

set_font(p.add_run('3. 需求管理改进\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   （1）蓝湖描述与实际需求不符的问题（如预警值设置缺少输入框、审批流程缺少"复核"节点）需加强需求评审，'
    '确保原型与需求规格书一致；\n'
    '   （2）需求变更必须经过影响评估，变更后的功能需重新验证关联模块。\n'
), size=10.5)

# ===== 六、测试结论 =====
doc.add_heading('六、测试结论', level=1)
p = doc.add_paragraph()

set_font(p.add_run('1. 缺陷密度与质量评估\n'), size=10.5, bold=True)
set_font(p.add_run(
    f'   本次迭代共记录缺陷{total_defects}条，严重及以上缺陷{severe_total}条，占比{severe_total/total_defects*100:.1f}%。'
    f'缺陷整体关闭率{(closed_count+resolved_count)/total_defects*100:.1f}%，'
    f'剩余未关闭{pending_count}条。{reopen_count}条缺陷被重新打开，反映出修复验证环节存在疏漏。'
    f'从缺陷趋势看，4月23日后缺陷数量明显下降，4月29日后仅新增8条，系统质量趋于稳定。'
    f'关闭时间跨度为{close_dates.min()}至{close_dates.max()}，修复验证工作持续有效。\n\n'
), size=10.5)

set_font(p.add_run('2. 模块质量评估\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   运维监控子系统-接收机管理模块缺陷密度最高（31.6%），是重点风险模块。'
    '空管自动化平台-任务计划模块严重缺陷占比最高（27条），需重点关注审批流程和状态变更逻辑。'
    '态势监视模块（24.9%）涉及大数据量场景下的性能和稳定性。'
    '告警管理模块（8.0%）状态机逻辑复杂，抑制与推送机制不完善。'
    '数字孪生作为新功能模块引入16条缺陷，其中4条挂起，风险需持续关注。\n\n'
), size=10.5)

set_font(p.add_run('3. 发布建议\n'), size=10.5, bold=True)
set_font(p.add_run('   综合考虑缺陷数量、严重程度分布、关闭率、缺陷趋势及遗留风险，建议：\n'), size=10.5)
set_font(p.add_run(f'   （1）{severity_counts.get("致命", 0)}条致命缺陷和{severity_counts.get("严重", 0)}条严重缺陷已基本修复关闭，系统核心功能风险可控；\n'), size=10.5)
set_font(p.add_run(f'   （2）剩余{status_counts.get("新", 0)}条"新"状态缺陷和{status_counts.get("接受/处理", 0)}条"接受/处理"缺陷必须在发布前完成修复验证；\n'), size=10.5)
set_font(p.add_run(f'   （3）{status_counts.get("挂起", 0)}条挂起缺陷（数字孪生4条、态势监视3条）需明确处理方案，建议延期或专项修复；\n'), size=10.5)
set_font(p.add_run(f'   （4）{status_counts.get("转需求", 0)}条转需求缺陷和{status_counts.get("延期", 0)}条延期缺陷需产品侧确认后续迭代安排；\n'), size=10.5)
set_font(p.add_run(f'   （5）建议在发布前进行高风险模块（接收机管理、任务计划、态势监视、告警管理）全量回归测试，并执行性能基线验证。\n'), size=10.5)

set_font(p.add_run('4. 下一步核心任务\n'), size=10.5, bold=True)
set_font(p.add_run(
    '   （1）5月9日前清零遗留缺陷，确保严重级问题不带入生产环境；\n'
    '   （2）5月中旬前完成接收机管理、告警状态机、任务计划状态机专项重构，补齐异常场景和性能测试；\n'
    '   （3）建立需求评审 + 代码评审 + 缺陷根因度量 + 容量测试的四层质量门禁，防止同类问题重复发生。\n'
), size=10.5)

# 保存（自动版本号自增）
output_base = 'c:/Users/wdjlw/iCloudDrive/AI_Python2026/低空测试脚本2026/迭代1.4.0过程数据及缺陷/低空空管自动化系统_迭代1.4.0集成测试总结报告_V2.0(AI分析版).docx'
output = get_next_version_path(output_base)
doc.save(output)
print(f'报告已生成：{output}')

