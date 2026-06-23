#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YAML to XMind Converter
将 YAML 格式的测试用例文件（case_model.yaml 格式）转换为 XMind 思维导图。

用法:
    python3 yaml_to_xmind.py <yaml_file> [output_xmind_file]

示例:
    python3 yaml_to_xmind.py case_workspace/TestCases.yaml

支持的 YAML schema（参见 templates/case_model.yaml）：
    - precondition / steps / expected：字符串 或 列表（列表自动拼接为 "1、... 2、..." 格式）
    - req_source / fp_source：字符串 或 列表（列表以 ", " 连接）
    - tags：列表，渲染为 XMind 标签（AI-GEN / FundLoss / 基线 / accept 等）
    - [基线] 前缀的 function_point title：E2E 生命周期场景，用例强制 P0
"""

import os
import re
import sys
import json
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Any, Union
from datetime import datetime

# ── 尝试导入 PyYAML ───────────────────────────────────────────────────────────
try:
    import yaml
except ImportError:
    print("错误: 需要安装 PyYAML。请运行: pip3 install pyyaml")
    sys.exit(1)


# =============================================================================
# 数据模型（与 md_to_xmind.py 保持一致）
# =============================================================================

TEST_TYPE_PREFIXES = [
    '功能测试', '场景测试', '接口测试', '异常测试', '边界测试',
    '权限测试', '幂等性测试', '并发测试', '可观测性测试', '兼容性测试',
]


def extract_test_type(title: str):
    """从标题中提取测试类型前缀，返回 (test_type, clean_title)。"""
    for prefix in TEST_TYPE_PREFIXES:
        if title.startswith(prefix + '_'):
            return prefix, title[len(prefix) + 1:]
        if title == prefix:
            return prefix, prefix
    return None, title


class MarkdownNode:
    """通用树节点，兼容 md_to_xmind.py 的节点模型。"""

    def __init__(self, title: str, level: int, parent: Optional['MarkdownNode'] = None):
        self.title = title
        self.level = level
        self.parent = parent
        self.children: List['MarkdownNode'] = []
        self.case_id: Optional[str] = None        # Case ID（用于统计）
        self.req_source: Optional[str] = None     # 需求来源（用于 XMind 笔记 + 统计）
        self.tags: List[str] = []                 # 标签列表（渲染为 XMind label）

    def add_child(self, child: 'MarkdownNode'):
        child.parent = self
        self.children.append(child)


# =============================================================================
# YAML 解析：将 YAML 文档转换为 MarkdownNode 树
# =============================================================================

def _to_numbered_str(value: Union[str, list, None]) -> str:
    """
    将字符串或列表统一转换为 "1、... 2、..." 格式字符串。
    若已为字符串且含 "1、" 则直接返回。
    """
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    # list
    parts = [str(item).strip() for item in value if str(item).strip()]
    return " ".join(f"{i + 1}、{p}" for i, p in enumerate(parts))


def _to_joined_str(value: Union[str, list, None], sep: str = ", ") -> str:
    """将字符串或列表统一转换为以 sep 连接的字符串。"""
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    return sep.join(str(v).strip() for v in value if str(v).strip())


def _make_chain(tc_node: MarkdownNode,
                precondition: str,
                steps: str,
                expected: str,
                priority: str,
                case_id: str,
                req_source: str,
                fp_source: str):
    """
    在 tc_node 下按 Tab 深度构建字段链：
      前置条件(4) → 测试步骤(5) → 预期结果(6) → 用例等级(7)
          → Case ID(8) → 需求来源(9) → 功能点来源(10)
    """
    base = tc_node.level + 1  # 4

    def node(title, lvl):
        n = MarkdownNode(title, lvl)
        return n

    pre = node(f"前置条件: {precondition}", base)
    stp = node(f"测试步骤: {steps}", base + 1)
    exp = node(f"预期结果: {expected}", base + 2)
    pri = node(f"用例等级: {priority}", base + 3)
    cid = node(f"Case ID: {case_id}", base + 4)
    req = node(f"需求来源: {req_source}", base + 5)
    fps = node(f"功能点来源: {fp_source}", base + 6)

    tc_node.add_child(pre)
    pre.add_child(stp)
    stp.add_child(exp)
    exp.add_child(pri)
    pri.add_child(cid)
    cid.add_child(req)
    req.add_child(fps)


def _build_analysis_node(analysis: dict) -> MarkdownNode:
    """构建「项目分析」Tab-1 节点。"""
    root = MarkdownNode("项目分析", 1)

    def section(name: str, level: int = 2) -> MarkdownNode:
        n = MarkdownNode(name, level)
        root.add_child(n)
        return n

    def leaf(parent: MarkdownNode, text: str):
        if text:
            parent.add_child(MarkdownNode(str(text).strip(), parent.level + 1))

    # 需求背景
    bg = section("需求背景")
    leaf(bg, analysis.get("background", ""))

    # 需求PRD
    prd_list = analysis.get("prd", [])
    if prd_list:
        prd_sec = section("需求PRD")
        for item in prd_list:
            if isinstance(item, dict):
                leaf(prd_sec, f"{item.get('label', '')}{item.get('url', '')}")
            else:
                leaf(prd_sec, str(item))

    # 概要设计
    design_list = analysis.get("design", [])
    if design_list:
        design_sec = section("概要设计")
        for item in design_list:
            if isinstance(item, dict):
                leaf(design_sec, f"{item.get('label', '')}{item.get('url', '')}")
            else:
                leaf(design_sec, str(item))

    # 测试方案
    tp = analysis.get("test_plan", "")
    if tp:
        tp_sec = section("测试方案")
        leaf(tp_sec, tp)

    # 关键改造点
    kc_list = analysis.get("key_changes", [])
    if kc_list:
        kc_sec = section("关键改造点")
        for item in kc_list:
            leaf(kc_sec, item)

    # 测试关注点
    tf = analysis.get("test_focus", "")
    if tf:
        tf_sec = section("测试关注点")
        leaf(tf_sec, tf)

    # 测试策略
    ts_list = analysis.get("test_strategy", [])
    if ts_list:
        ts_sec = section("测试策略")
        for item in ts_list:
            leaf(ts_sec, item)

    # 测试准备&效率分析
    prep = analysis.get("test_preparation", "")
    if prep:
        prep_sec = section("测试准备&效率分析")
        leaf(prep_sec, prep)

    return root


def parse_yaml_to_tree(yaml_path: str) -> MarkdownNode:
    """
    解析 YAML 测试用例文件，构建 MarkdownNode 树。

    树结构：
      Root(0)
        项目分析(1)
          需求背景(2) → 内容(3)
          ...
        Module(1)
          FP title(2)
            TC-XXX: title(3)
              前置条件:(4)
                测试步骤:(5)
                  预期结果:(6)
                    用例等级:(7)
                      Case ID:(8)
                        需求来源:(9)
                          功能点来源:(10)
    """
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"YAML 文件为空或解析失败: {yaml_path}")

    project = data.get("project", {})
    name = project.get("name", Path(yaml_path).stem)
    total = project.get("total_cases", "N")

    root = MarkdownNode(f"{name} ({total}条用例)", 0)

    # 项目分析节点
    analysis = data.get("project_analysis", {})
    if analysis:
        root.add_child(_build_analysis_node(analysis))

    # 业务场景模块
    for module in data.get("modules", []):
        m_name = module.get("name", "")
        m_count = module.get("total_cases", "N")
        module_node = MarkdownNode(f"{m_name} ({m_count}条用例)", 1)
        root.add_child(module_node)

        for fp in module.get("function_points", []):
            fp_title = fp.get("title", "")
            fp_node = MarkdownNode(fp_title, 2)
            module_node.add_child(fp_node)

            for case in fp.get("cases", []):
                case_id_key = case.get("id", "")      # TC-XXX-正向
                case_title = case.get("title", "")
                tc_label = f"{case_id_key}: {case_title}" if case_id_key else case_title

                tc_node = MarkdownNode(tc_label, 3)
                # 设置到 MarkdownNode 元数据（用于统计和 XMind 笔记）
                tc_node.case_id = case.get("case_id", "")
                tc_node.req_source = _to_joined_str(case.get("req_source", ""), ", ")
                tc_node.tags = [t.strip() for t in (case.get("tags") or []) if str(t).strip()]
                fp_node.add_child(tc_node)

                # 构建字段链
                _make_chain(
                    tc_node=tc_node,
                    precondition=_to_numbered_str(case.get("precondition", "")),
                    steps=_to_numbered_str(case.get("steps", "")),
                    expected=_to_numbered_str(case.get("expected", "")),
                    priority=str(case.get("priority", "")),
                    case_id=str(case.get("case_id", "")),
                    req_source=_to_joined_str(case.get("req_source", ""), ", "),
                    fp_source=_to_joined_str(case.get("fp_source", ""), ", "),
                )

    return root


# =============================================================================
# XMind 生成（完整实现，与 md_to_xmind.py 保持逻辑一致）
# =============================================================================

def indent_xml(elem, level=0, indent_str='  '):
    """手动格式化 XML（兼容 Python 3.8 及以下版本）。"""
    i = "\n" + level * indent_str
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + indent_str
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            indent_xml(child, level + 1, indent_str)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def _add_label(topic_elem: ET.Element, label_text: str):
    """为 topic 元素添加 XMind label。"""
    labels = topic_elem.find('labels')
    if labels is None:
        labels = ET.SubElement(topic_elem, 'labels')
    label = ET.SubElement(labels, 'label')
    label.text = label_text


_DETAIL_PREFIXES = (
    '前置条件:', '测试步骤:', '预期结果:', '用例等级:',
    'Case ID:', '需求来源:', '功能点来源:',
)


def create_topic_xml(node: MarkdownNode, parent_element,
                     propagate_label: str = None) -> ET.Element:
    """递归创建 topic XML 元素，携带标签、笔记等元数据。"""
    topic = ET.Element('topic')
    topic.set('id', f'topic_{id(node)}')

    test_type, clean_title = extract_test_type(node.title)
    title_elem = ET.SubElement(topic, 'title')
    title_elem.text = clean_title if test_type else node.title

    # 测试类型 label（传播一层）
    node_label = test_type or propagate_label
    if node_label and not node.title.startswith(_DETAIL_PREFIXES):
        _add_label(topic, node_label)

    # tags → XMind label（AI-GEN / FundLoss / 基线 / accept …）
    if node.tags and not node.title.startswith(_DETAIL_PREFIXES):
        for tag in node.tags:
            _add_label(topic, tag)

    # req_source → XMind 笔记
    if node.req_source:
        notes = ET.SubElement(topic, 'notes')
        plain = ET.SubElement(notes, 'plain')
        formatted = node.req_source.replace('), REQ-', ')\n\nREQ-')
        plain.text = f"【需求来源】\n\n{formatted}"

    # 子节点
    if node.children:
        children_elem = ET.SubElement(topic, 'children')
        topics_elem = ET.SubElement(children_elem, 'topics')
        topics_elem.set('type', 'attached')
        child_propagate = test_type if test_type else None
        for child in node.children:
            child_topic = create_topic_xml(child, topics_elem, child_propagate)
            topics_elem.append(child_topic)

    return topic


def generate_content_xml(root_node: MarkdownNode) -> str:
    root = ET.Element('xmap-content')
    root.set('xmlns', 'urn:xmind:xmap:xmlns:content:2.0')
    sheet = ET.SubElement(root, 'sheet', id='sheet1')
    root_topic = create_topic_xml(root_node, sheet)
    root_topic.set('structure-class', 'org.xmind.ui.logic.right')
    sheet.append(root_topic)
    indent_xml(root)
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + ET.tostring(root, encoding='unicode')


def generate_meta_xml() -> str:
    root = ET.Element('meta')
    root.set('xmlns', 'urn:xmind:xmap:xmlns:meta:2.0')
    author = ET.SubElement(root, 'author')
    author.text = 'yaml_to_xmind'
    indent_xml(root)
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + ET.tostring(root, encoding='unicode')


def generate_manifest_xml() -> str:
    root = ET.Element('manifest')
    root.set('xmlns', 'urn:xmind:xmap:xmlns:manifest:1.0')
    for path, mtype in [
        ('content.xml', 'text/xml'),
        ('meta.xml', 'text/xml'),
        ('META-INF/', ''),
        ('META-INF/manifest.xml', 'text/xml'),
    ]:
        fe = ET.SubElement(root, 'file-entry')
        fe.set('full-path', path)
        fe.set('media-type', mtype)
    indent_xml(root)
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + ET.tostring(root, encoding='unicode')


# =============================================================================
# 统计与报告（与 md_to_xmind.py 一致）
# =============================================================================

class XMindStats:
    def __init__(self):
        self.root_title = ""
        self.modules: List[str] = []
        self.features: List[str] = []
        self.test_cases: List[dict] = []
        self.priority_count = {'P0': 0, 'P1': 0, 'P2': 0, '未标注': 0}
        self.req_sources: set = set()
        self.module_features: Dict[str, list] = {}
        self.module_case_count: Dict[str, int] = {}
        self.tag_count: Dict[str, int] = {}


def _find_priority(node: MarkdownNode) -> Optional[str]:
    """在节点子树中查找用例等级值。"""
    if node.title.startswith('用例等级:'):
        return node.title.replace('用例等级:', '').strip()
    for child in node.children:
        found = _find_priority(child)
        if found:
            return found
    return None


def analyze_tree(node: MarkdownNode, stats: XMindStats,
                 current_module: str = "", depth: int = 0):
    """递归分析节点树，收集统计信息。"""
    skip = ('前置条件:', '测试步骤:', '预期结果:', '用例等级:', 'Case ID:', '需求来源:', '功能点来源:')
    if node.title.startswith(skip):
        return

    if depth == 0:
        stats.root_title = node.title
    elif depth == 1 and node.title != "项目分析":
        stats.modules.append(node.title)
        stats.module_features[node.title] = []
        stats.module_case_count[node.title] = 0
        current_module = node.title
    elif depth == 2 and current_module:
        stats.features.append(node.title)
        stats.module_features.setdefault(current_module, []).append(node.title)

    # 识别测试用例节点
    if node.req_source or node.case_id:
        priority_val = _find_priority(node) or ""
        if 'P0' in priority_val:
            stats.priority_count['P0'] += 1
        elif 'P1' in priority_val:
            stats.priority_count['P1'] += 1
        elif 'P2' in priority_val:
            stats.priority_count['P2'] += 1
        else:
            stats.priority_count['未标注'] += 1

        if current_module and current_module in stats.module_case_count:
            stats.module_case_count[current_module] += 1

        stats.test_cases.append({
            'title': node.title,
            'module': current_module,
            'case_id': node.case_id,
            'req_source': node.req_source,
            'priority': priority_val,
        })

        for m in re.finditer(r'REQ-[\d\.\-]+', node.req_source or ''):
            stats.req_sources.add(m.group())

        for tag in node.tags:
            stats.tag_count[tag] = stats.tag_count.get(tag, 0) + 1

    for child in node.children:
        analyze_tree(child, stats, current_module, depth + 1)


def generate_report(stats: XMindStats, output_file: str) -> str:
    lines = []
    sep = "=" * 70
    lines += [sep, "                    XMind 生成报告 (YAML → XMind)", sep, ""]

    lines += ["【基本信息】",
              f"  根节点: {stats.root_title}",
              f"  输出文件: {output_file}",
              f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]

    total = len(stats.test_cases)
    lines += ["【统计概览】",
              f"  模块数量: {len(stats.modules)}",
              f"  功能点数量: {len(stats.features)}",
              f"  测试用例数量: {total}",
              f"  覆盖需求数量: {len(stats.req_sources)}", ""]

    lines.append("【用例优先级分布】")
    for pri, cnt in stats.priority_count.items():
        if cnt > 0:
            pct = cnt / total * 100 if total else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"  {pri}: {cnt:3d} 条  {bar} {pct:.1f}%")
    lines.append("")

    if stats.tag_count:
        lines.append("【标签分布】")
        for tag, cnt in sorted(stats.tag_count.items(), key=lambda x: -x[1]):
            lines.append(f"  {tag}: {cnt} 条")
        lines.append("")

    lines.append("【模块用例分布】")
    for mod, cnt in stats.module_case_count.items():
        fp_cnt = len(stats.module_features.get(mod, []))
        lines += [f"  ├─ {mod}", f"  │    功能点: {fp_cnt}, 用例数: {cnt}"]
    lines.append("")

    if stats.req_sources:
        lines.append("【覆盖需求列表】")
        sorted_reqs = sorted(stats.req_sources)
        for i in range(0, len(sorted_reqs), 5):
            lines.append(f"  {', '.join(sorted_reqs[i:i+5])}")
    lines.append("")
    lines.append(sep)
    return "\n".join(lines)


# =============================================================================
# 主转换入口
# =============================================================================

def convert_yaml_to_xmind(yaml_file: str, output_file: str = None) -> bool:
    """
    将 YAML 格式的测试用例文件转换为 XMind 文件。

    Args:
        yaml_file:   输入 YAML 文件路径
        output_file: 输出 XMind 文件路径（可选，默认同目录同名 .xmind）

    Returns:
        True 表示成功
    """
    yaml_path = Path(yaml_file)
    if not yaml_path.exists():
        print(f"错误: 文件不存在: {yaml_file}")
        return False

    if output_file is None:
        output_file = yaml_path.with_suffix('.xmind')
    else:
        output_file = Path(output_file)

    print(f"正在解析 YAML 文件: {yaml_file}")
    try:
        root_node = parse_yaml_to_tree(yaml_file)
    except Exception as e:
        print(f"错误: 解析 YAML 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    stats = XMindStats()
    analyze_tree(root_node, stats)

    print(f"正在生成 XMind 文件: {output_file}")
    try:
        temp_dir = tempfile.mkdtemp()

        content_path = os.path.join(temp_dir, 'content.xml')
        with open(content_path, 'w', encoding='utf-8') as f:
            f.write(generate_content_xml(root_node))

        meta_path = os.path.join(temp_dir, 'meta.xml')
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write(generate_meta_xml())

        manifest_dir = os.path.join(temp_dir, 'META-INF')
        os.makedirs(manifest_dir, exist_ok=True)
        manifest_path = os.path.join(manifest_dir, 'manifest.xml')
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(generate_manifest_xml())

        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(content_path, 'content.xml')
            zf.write(meta_path, 'meta.xml')
            zf.write(manifest_path, 'META-INF/manifest.xml')

        shutil.rmtree(temp_dir)
        print(f"✓ 成功生成 XMind 文件: {output_file}\n")
        print(generate_report(stats, str(output_file)))
        return True

    except Exception as e:
        print(f"错误: 生成 XMind 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# md_to_xmind 兼容辅助：将已有 Markdown TestCases 转为 YAML 格式（反向工具）
# =============================================================================

def md_tree_to_yaml(md_file: str, output_yaml: str = None) -> bool:
    """
    将已有 Tab 缩进 Markdown 测试用例文件解析后导出为 YAML 格式（辅助迁移工具）。

    依赖同目录的 md_to_xmind.py 中的 parse_markdown_file 函数。
    """
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        from md_to_xmind import parse_markdown_file
    except ImportError:
        print("错误: 无法导入 md_to_xmind.parse_markdown_file，请确保文件在同目录下。")
        return False

    md_path = Path(md_file)
    if not md_path.exists():
        print(f"错误: 文件不存在: {md_file}")
        return False

    if output_yaml is None:
        output_yaml = md_path.with_suffix('.yaml')
    else:
        output_yaml = Path(output_yaml)

    print(f"正在解析 Markdown 文件: {md_file}")
    root = parse_markdown_file(md_file)
    if root is None:
        print("错误: 解析失败，文件可能为空。")
        return False

    # 构建 YAML 数据结构
    def _strip_field(title: str, prefix: str) -> str:
        if title.startswith(prefix):
            return title[len(prefix):].strip()
        return title.strip()

    _FIELDS = {
        '前置条件: ': 'precondition',
        '测试步骤: ': 'steps',
        '预期结果: ': 'expected',
        '用例等级: ': 'priority',
        'Case ID: ': 'case_id',
        '需求来源: ': 'req_source',
        '功能点来源: ': 'fp_source',
    }

    def _collect_case_fields(tc_node) -> dict:
        """从 tc_node 的子节点链中提取字段值。"""
        fields = {}

        def _walk(n):
            for pref, key in _FIELDS.items():
                if n.title.startswith(pref.rstrip()):
                    fields[key] = n.title[len(pref.rstrip()):].strip()
                    break
            for c in n.children:
                _walk(c)

        for child in tc_node.children:
            _walk(child)
        fields['tags'] = tc_node.tags if tc_node.tags else []
        fields['req_source'] = fields.get('req_source', tc_node.req_source or '')
        fields['case_id'] = fields.get('case_id', tc_node.case_id or '')
        return fields

    def _parse_tc_id_title(raw: str):
        """从 "TC-XXX-正向: 标题" 中分离 id 和 title。"""
        m = re.match(r'^((?:TC-|【[^】]+】)\S+?):\s*(.+)$', raw)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return raw.strip(), ""

    # 组装 YAML 数据
    project_analysis = {}
    modules = []
    project_name = root.title
    total_re = re.search(r'\((\d+)条用例\)', project_name)
    total_cases = int(total_re.group(1)) if total_re else "N"
    project_name_clean = re.sub(r'\s*\(\d+条用例\)', '', project_name).strip()

    for tab1 in root.children:
        if tab1.title == "项目分析":
            for tab2 in tab1.children:
                key = tab2.title
                values = [c.title for c in tab2.children if c.title]
                if key == "需求背景":
                    project_analysis['background'] = values[0] if values else ""
                elif key == "需求PRD":
                    project_analysis['prd'] = [{'label': '', 'url': v} for v in values]
                elif key == "概要设计":
                    project_analysis['design'] = [{'label': '', 'url': v} for v in values]
                elif key == "测试方案":
                    project_analysis['test_plan'] = values[0] if values else ""
                elif key == "关键改造点":
                    project_analysis['key_changes'] = values
                elif key == "测试关注点":
                    project_analysis['test_focus'] = values[0] if values else ""
                elif key == "测试策略":
                    project_analysis['test_strategy'] = values
                elif key == "测试准备&效率分析":
                    project_analysis['test_preparation'] = values[0] if values else ""
        else:
            m_raw = tab1.title
            m_cnt_re = re.search(r'\((\d+)条用例\)', m_raw)
            m_count = int(m_cnt_re.group(1)) if m_cnt_re else "N"
            m_name = re.sub(r'\s*\(\d+条用例\)', '', m_raw).strip()

            fps = []
            for tab2 in tab1.children:
                fp_cases = []
                for tab3 in tab2.children:
                    tc_id, tc_title = _parse_tc_id_title(tab3.title)
                    fields = _collect_case_fields(tab3)

                    def _split_numbered(s: str) -> list:
                        parts = re.split(r'\s*\d+、', s)
                        return [p.strip() for p in parts if p.strip()]

                    fp_cases.append({
                        'id': tc_id,
                        'title': tc_title,
                        'precondition': _split_numbered(fields.get('precondition', '')),
                        'steps': _split_numbered(fields.get('steps', '')),
                        'expected': _split_numbered(fields.get('expected', '')),
                        'priority': fields.get('priority', ''),
                        'case_id': fields.get('case_id', ''),
                        'req_source': fields.get('req_source', ''),
                        'fp_source': fields.get('fp_source', ''),
                        'tags': fields.get('tags', []),
                    })

                fps.append({'title': tab2.title, 'cases': fp_cases})

            modules.append({'name': m_name, 'total_cases': m_count, 'function_points': fps})

    doc = {
        'project': {
            'name': project_name_clean,
            'version': '',
            'jira': '',
            'total_cases': total_cases,
        },
        'project_analysis': project_analysis,
        'modules': modules,
    }

    with open(output_yaml, 'w', encoding='utf-8') as f:
        yaml.dump(doc, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, indent=2)

    print(f"✓ 已将 Markdown 转换为 YAML: {output_yaml}")
    return True


# =============================================================================
# CLI 入口
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="YAML 测试用例文件 → XMind 思维导图转换工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # YAML → XMind（主功能）
  python3 yaml_to_xmind.py case_workspace/LOAN_v7.0.21_20260313/XXXX-86427/testcases/Price-Lock-Module_TestCases.yaml

  # YAML → 指定输出路径
  python3 yaml_to_xmind.py input.yaml output.xmind

  # Markdown → YAML（辅助迁移）
  python3 yaml_to_xmind.py --md2yaml case_workspace/.../testcases/Price-Lock-Module_TestCases.md
        """)

    parser.add_argument('input_file', help='输入文件路径（YAML 格式）')
    parser.add_argument('output_file', nargs='?', default=None,
                        help='输出 XMind 文件路径（可选，默认同目录同名 .xmind）')
    parser.add_argument('--md2yaml', action='store_true',
                        help='反向模式：将 Markdown 测试用例文件转换为 YAML 格式')

    args = parser.parse_args()

    if args.md2yaml:
        success = md_tree_to_yaml(args.input_file, args.output_file)
    else:
        success = convert_yaml_to_xmind(args.input_file, args.output_file)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
