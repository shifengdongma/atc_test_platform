#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XMind Test Case Generator - 根据需求文档生成测试用例 XMind 思维导图

支持生成 XMind 8 格式的思维导图，包含测试用例的层级结构。
"""

import json
import zipfile
import uuid
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import List, Dict, Optional, Any


class XMindGenerator:
    """生成 XMind 格式的思维导图"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化生成器
        
        Args:
            config: 可选的配置字典，包含：
                - precondition_rules: 前置条件规则配置
                - test_step_rules: 测试步骤规则配置
                - expected_result_rules: 预期结果规则配置
        """
        self.workbook_id = str(uuid.uuid4()).replace('-', '')
        self.current_time = int(time.time() * 1000)  # 毫秒时间戳
        self.case_counter = 0  # 用例编号计数器
        self.module_counters = {}  # 按模块存储用例计数器
        
        # 初始化配置规则
        self._init_config(config or {})
    
    def _create_topic_xml(self, parent: ET.Element, title: str, 
                         children: Optional[List[Dict]] = None, 
                         note: Optional[str] = None,
                         fields: Optional[Dict[str, str]] = None,
                         markers: Optional[List[str]] = None) -> ET.Element:
        """
        创建主题节点（XMind 8 XML 格式）
        
        Args:
            parent: 父元素
            title: 主题标题
            children: 子主题列表
            note: 备注内容
            fields: 字段信息字典，包含用例编号、用例名称、测试类型、前置条件、测试步骤、预期结果、优先级、执行结果
            markers: 标记列表（如 ["flag-blue", "priority-1"]）
        
        Returns:
            主题元素
        """
        ns = "urn:xmind:xmap:xmlns:content:2.0"
        topic = ET.SubElement(parent, f"{{{ns}}}topic")
        topic.set("id", str(uuid.uuid4()).replace('-', ''))
        
        # 标题
        title_elem = ET.SubElement(topic, f"{{{ns}}}title")
        title_elem.text = title
        
        # 添加 markers（标记）
        if markers:
            marker_refs = ET.SubElement(topic, f"{{{ns}}}marker-refs")
            for marker_id in markers:
                marker_ref = ET.SubElement(marker_refs, f"{{{ns}}}marker-ref")
                marker_ref.set("marker-id", marker_id)
        
        # 备注
        if note:
            notes = ET.SubElement(topic, f"{{{ns}}}notes")
            plain = ET.SubElement(notes, f"{{{ns}}}plain")
            plain.text = note
        
        # 字段信息作为子节点（层级嵌套结构：前置条件 → 测试步骤 → 预期结果）
        # 注意：用例编号已在标题中显示，此处跳过以避免重复
        if fields:
            if not children:
                children = []
            # 创建字段子节点，按照层级嵌套结构：前置条件 → 测试步骤 → 预期结果
            field_children = []
            
            # 定义字段顺序（从外到内：前置条件 → 测试步骤 → 预期结果）
            # 跳过 case_id，因为标题中已包含用例编号
            field_order = [
                ("preconditions", "前置条件"),
                ("test_steps", "测试步骤"),
                ("expected_result", "预期结果")
            ]
            
            # 从最外层开始构建
            current_node = None
            for field_key, field_label in field_order:
                if field_key in fields and fields[field_key]:
                    field_value = fields[field_key]
                    field_title = f"{field_label}: {field_value}"
                    
                    current_node = {
                        "title": field_title,
                        "children": [current_node] if current_node else []
                    }
            
            # 如果构建了节点，添加到field_children
            if current_node:
                field_children.append(current_node)
            
            # 将字段子节点添加到children前面
            children = field_children + children
        
        # 子主题
        if children:
            children_elem = ET.SubElement(topic, f"{{{ns}}}children")
            topics_elem = ET.SubElement(children_elem, f"{{{ns}}}topics")
            topics_elem.set("type", "attached")
            
            for child in children:
                if isinstance(child, dict):
                    if "title" in child:
                        self._create_topic_xml(
                            topics_elem,
                            child.get("title", ""),
                            children=child.get("children"),
                            note=child.get("note"),
                            fields=child.get("fields"),
                            markers=child.get("markers")
                        )
                else:
                    # 如果是字符串，转换为主题
                    self._create_topic_xml(topics_elem, str(child))
        
        return topic
    
    def create_topic(self, title: str, children: Optional[List[Dict]] = None, 
                     note: Optional[str] = None, markers: Optional[List[str]] = None,
                     fields: Optional[Dict[str, str]] = None) -> Dict:
        """
        创建主题节点（兼容方法，返回字典用于内部处理）
        
        Args:
            title: 主题标题
            children: 子主题列表
            note: 备注内容
            markers: 标记列表（如 ["priority-1"]）
            fields: 字段信息字典，包含用例编号、用例名称、测试类型、前置条件、测试步骤、预期结果、优先级、执行结果
        
        Returns:
            主题字典
        """
        topic = {
            "title": title
        }
        
        if note:
            topic["note"] = note
        
        if children:
            topic["children"] = children
        
        if fields:
            topic["fields"] = fields
        
        if markers:
            topic["markers"] = markers
        
        return topic
    
    
    def generate_xmind(self, output_path: str, root_title: str, 
                      structure: List[Dict], sheet_title: str = "测试用例") -> str:
        """
        生成 XMind 文件（XMind 8 XML 格式）
        
        Args:
            output_path: 输出文件路径
            root_title: 根节点标题
            structure: 结构数据，格式为 [{"title": "...", "children": [...]}]
            sheet_title: 工作表标题
        
        Returns:
            生成的文件路径
        """
        # 重置计数器，确保每次生成新文件时从0开始
        self.case_counter = 0
        self.module_counters = {}
        
        # 创建 XML 根元素（使用正确的命名空间）
        ns = "urn:xmind:xmap:xmlns:content:2.0"
        ET.register_namespace('', ns)
        xmap_content = ET.Element(f"{{{ns}}}xmap-content")
        xmap_content.set("version", "2.0")
        
        # 创建工作表
        sheet = ET.SubElement(xmap_content, "{urn:xmind:xmap:xmlns:content:2.0}sheet")
        sheet.set("id", str(uuid.uuid4()).replace('-', ''))
        sheet.set("theme", "plain")
        
        # 标题
        title_elem = ET.SubElement(sheet, "{urn:xmind:xmap:xmlns:content:2.0}title")
        title_elem.text = sheet_title
        
        # 创建根主题
        topic = ET.SubElement(sheet, "{urn:xmind:xmap:xmlns:content:2.0}topic")
        topic.set("id", str(uuid.uuid4()).replace('-', ''))
        topic_title = ET.SubElement(topic, "{urn:xmind:xmap:xmlns:content:2.0}title")
        topic_title.text = root_title
        
        # 添加子主题
        ns = "urn:xmind:xmap:xmlns:content:2.0"
        if structure:
            children_elem = ET.SubElement(topic, f"{{{ns}}}children")
            topics_elem = ET.SubElement(children_elem, f"{{{ns}}}topics")
            topics_elem.set("type", "attached")
            
            # 处理结构，为测试用例自动生成字段信息（传递初始模块路径为空）
            processed_structure = self._process_structure_with_fields(structure, module_path="")
            
            for item in processed_structure:
                self._create_topic_xml(
                    topics_elem,
                    item.get("title", ""),
                    children=item.get("children"),
                    note=item.get("note"),
                    fields=item.get("fields"),
                    markers=item.get("markers")
                )
        
        # 生成 XML 字符串
        xml_str = self._prettify_xml(xmap_content)
        
        # 创建 ZIP 文件
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 写入 manifest.xml
            zf.writestr('META-INF/manifest.xml', self._create_manifest())
            # 写入 content.xml
            zf.writestr('content.xml', xml_str.encode('utf-8'))
            # 写入 styles.xml（必需）
            zf.writestr('styles.xml', self._create_styles_xml())
            # 写入 meta.xml（可选但推荐）
            zf.writestr('meta.xml', self._create_meta_xml())
        
        return str(output_path)
    
    def _prettify_xml(self, elem: ET.Element) -> str:
        """美化 XML 输出"""
        # 直接生成 XML 字符串，不进行二次解析
        rough_string = ET.tostring(elem, encoding='utf-8', xml_declaration=True)
        # 手动美化（简单版本）
        xml_str = rough_string.decode('utf-8')
        # 添加命名空间声明到根元素
        if 'xmlns=' not in xml_str:
            xml_str = xml_str.replace('<xmap-content', '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0"', 1)
        return xml_str
    
    def _create_manifest(self) -> bytes:
        """创建 manifest.xml（XMind 8 格式）"""
        manifest = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<manifest xmlns="urn:xmind:xmap:xmlns:manifest:1.0">
    <file-entry full-path="content.xml" media-type="text/xml"/>
    <file-entry full-path="META-INF/" media-type=""/>
    <file-entry full-path="META-INF/manifest.xml" media-type="text/xml"/>
    <file-entry full-path="styles.xml" media-type="text/xml"/>
    <file-entry full-path="meta.xml" media-type="text/xml"/>
</manifest>'''
        return manifest.encode('utf-8')
    
    def _create_styles_xml(self) -> bytes:
        """创建 styles.xml（XMind 8 格式）"""
        styles = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<xmap-styles xmlns="urn:xmind:xmap:xmlns:style:2.0" version="2.0">
</xmap-styles>'''
        return styles.encode('utf-8')
    
    def _create_meta_xml(self) -> bytes:
        """创建 meta.xml（XMind 8 格式）"""
        meta = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<meta xmlns="urn:xmind:xmap:xmlns:meta:2.0" version="2.0">
    <Author>
        <Name>XMind Test Case Generator</Name>
    </Author>
    <Create>{self.current_time}</Create>
    <Modified>{self.current_time}</Modified>
</meta>'''
        return meta.encode('utf-8')
    
    def _init_config(self, config: Dict):
        """
        初始化配置规则
        
        Args:
            config: 配置字典
        """
        # 前置条件规则配置
        self.precondition_rules = config.get('precondition_rules', {})
        if not self.precondition_rules:
            # 默认通用规则：基于关键词匹配
            self.precondition_rules = {
                'default': '系统正常运行',
                'keywords': {}  # 用户可以通过配置添加关键词匹配规则
            }
        
        # 测试步骤规则配置
        self.test_step_rules = config.get('test_step_rules', {})
        if not self.test_step_rules:
            # 默认通用模板
            self.test_step_rules = {
                '正向用例': lambda name, parent: f"1. 进入相关功能页面\n2. 执行操作：{name}\n3. 验证操作成功\n4. 验证功能正常",
                '负向用例': lambda name, parent: f"1. 进入相关功能页面\n2. 执行无效操作：{name}\n3. 验证系统提示错误信息\n4. 验证操作被拒绝",
                '边界值用例': lambda name, parent: f"1. 进入相关功能页面\n2. 输入边界值：{name}\n3. 验证系统处理\n4. 验证边界值处理正确",
                '异常用例': lambda name, parent: f"1. 进入相关功能页面\n2. 模拟异常场景：{name}\n3. 验证系统响应\n4. 验证系统不会崩溃",
            }
        
        # 预期结果规则配置
        self.expected_result_rules = config.get('expected_result_rules', {})
        if not self.expected_result_rules:
            # 默认通用模板
            self.expected_result_rules = {
                '正向用例': lambda name, parent: f"操作成功，{name}功能正常，符合预期",
                '负向用例': lambda name, parent: f"系统正确提示错误信息，拒绝无效操作，{name}场景处理正确",
                '边界值用例': lambda name, parent: f"系统正确处理边界值情况：{name}，边界值验证通过",
                '异常用例': lambda name, parent: f"系统正确处理异常情况，不会崩溃，{name}异常场景处理正确",
            }
    
    def parse_requirements_to_structure(self, requirements_text: str) -> List[Dict]:
        """
        解析需求文档文本，转换为思维导图结构
        
        根据需求文档的层级结构（如 2.1, 2.1.1 等）生成层级结构
        
        Args:
            requirements_text: 需求文档文本
        
        Returns:
            结构化的主题列表
        """
        lines = requirements_text.strip().split('\n')
        structure = []
        current_section = None
        current_subsection = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测章节标题（如 "2.1 用户信息展示"）
            if line.startswith(('2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    section_num = parts[0]
                    section_title = parts[1]
                    
                    # 判断是主章节还是子章节
                    if '.' not in section_num.replace('.', '', 1):  # 主章节如 "2."
                        current_section = {
                            "title": f"{section_num} {section_title}",
                            "children": []
                        }
                        structure.append(current_section)
                    elif section_num.count('.') == 1:  # 子章节如 "2.1"
                        if current_section:
                            current_subsection = {
                                "title": f"{section_num} {section_title}",
                                "children": []
                            }
                            current_section["children"].append(current_subsection)
                    elif section_num.count('.') == 2:  # 三级章节如 "2.1.1"
                        if current_subsection:
                            current_subsection["children"].append({
                                "title": f"{section_num} {section_title}",
                                "children": []
                            })
            
            # 检测功能点（通常以特定关键词开头）
            elif line and current_subsection and any(keyword in line for keyword in 
                ['支持', '提供', '规则', '限制', '功能', '显示', '输入', '点击', '上传', '设置']):
                # 添加到当前子章节
                if current_subsection["children"]:
                    current_subsection["children"][-1]["children"].append({
                        "title": line,
                        "children": []
                    })
                else:
                    current_subsection["children"].append({
                        "title": line,
                        "children": []
                    })
        
        return structure
    
    def _process_structure_with_fields(self, structure: List[Dict], 
                                       parent_type: str = "", 
                                       parent_title: str = "",
                                       module_path: str = "") -> List[Dict]:
        """
        处理结构，为测试用例自动生成字段信息
        
        Args:
            structure: 原始结构
            parent_type: 父节点类型（已废弃，保留用于兼容）
            parent_title: 父节点标题
            module_path: 模块路径，用于生成用例编号
        
        Returns:
            处理后的结构
        """
        processed = []
        for item in structure:
            title = item.get("title", "")
            children = item.get("children", [])
            
            # 更新模块路径（提取章节编号）
            new_module_path = module_path
            if title and any(char.isdigit() for char in title):
                # 提取章节编号（如 "2.1 购物车选品与结算 - 测试用例" -> "2.1"）
                parts = title.split(' ', 1)
                if parts and '.' in parts[0]:
                    new_module_path = parts[0]
            
            # 处理子节点
            processed_children = []
            # 定义分类节点列表
            CATEGORY_NODES = ["正向用例", "负向用例", "边界值用例", "异常用例"]
            
            for child in children:
                if isinstance(child, dict):
                    child_title = child.get("title", "")
                    
                    # 检查是否为分类节点
                    if child_title in CATEGORY_NODES:
                        # 跳过分类节点，直接处理其子节点并提升到当前层级
                        test_type = child_title  # 分类节点标题就是测试类型
                        child_children = child.get("children", [])
                        
                        # 处理分类节点的子节点（测试用例）
                        for grandchild in child_children:
                            if isinstance(grandchild, str):
                                # 字符串类型的测试用例
                                fields = self._generate_test_case_fields(
                                    grandchild, test_type, title, new_module_path
                                )
                                case_id = fields.get("case_id", "")
                                case_name = fields.get("case_name", grandchild)
                                combined_title = f"用例编号: {case_id}  {case_name}"
                                markers = self._generate_markers(fields.get("test_type", ""), fields.get("priority", ""))
                                processed_children.append({
                                    "title": combined_title,
                                    "fields": fields,
                                    "markers": markers,
                                    "children": []
                                })
                            elif isinstance(grandchild, dict):
                                # 字典类型的测试用例，递归处理
                                grandchild_title = grandchild.get("title", "")
                                if not grandchild.get("children") or len(grandchild.get("children", [])) == 0:
                                    # 没有子节点，作为测试用例处理
                                    fields = self._generate_test_case_fields(
                                        grandchild_title, test_type, title, new_module_path
                                    )
                                    case_id = fields.get("case_id", "")
                                    case_name = fields.get("case_name", grandchild_title)
                                    combined_title = f"用例编号: {case_id}  {case_name}"
                                    markers = self._generate_markers(fields.get("test_type", ""), fields.get("priority", ""))
                                    processed_children.append({
                                        "title": combined_title,
                                        "fields": fields,
                                        "markers": markers,
                                        "children": []
                                    })
                                else:
                                    # 有子节点，递归处理
                                    processed_children.append({
                                        "title": grandchild_title,
                                        "children": self._process_structure_with_fields(
                                            grandchild.get("children", []), parent_type, title, new_module_path
                                        ),
                                        "note": grandchild.get("note"),
                                        "fields": grandchild.get("fields")
                                    })
                            else:
                                processed_children.append(grandchild)
                    # 如果子节点是测试用例（没有子节点或子节点为空）
                    elif not child.get("children") or len(child.get("children", [])) == 0:
                        # 生成字段信息（使用"正向用例"作为默认测试类型）
                        fields = self._generate_test_case_fields(
                            child_title, "正向用例", title, new_module_path
                        )
                        # 合并用例编号和用例名称到标题
                        case_id = fields.get("case_id", "")
                        case_name = fields.get("case_name", child_title)
                        combined_title = f"用例编号: {case_id}  {case_name}"
                        # 生成 markers（测试类型和优先级）
                        markers = self._generate_markers(fields.get("test_type", ""), fields.get("priority", ""))
                        processed_children.append({
                            "title": combined_title,
                            "fields": fields,
                            "markers": markers,
                            "children": []
                        })
                    else:
                        # 递归处理有子节点的节点（非分类节点）
                        processed_children.append({
                            "title": child_title,
                            "children": self._process_structure_with_fields(
                                child.get("children", []), parent_type, title, new_module_path
                            ),
                            "note": child.get("note"),
                            "fields": child.get("fields")
                        })
                elif isinstance(child, str):
                    # 字符串类型的测试用例，生成字段信息（使用"正向用例"作为默认测试类型）
                    fields = self._generate_test_case_fields(
                        child, "正向用例", parent_title, new_module_path
                    )
                    # 合并用例编号和用例名称到标题
                    case_id = fields.get("case_id", "")
                    case_name = fields.get("case_name", child)
                    combined_title = f"用例编号: {case_id}  {case_name}"
                    # 生成 markers（测试类型和优先级）
                    markers = self._generate_markers(fields.get("test_type", ""), fields.get("priority", ""))
                    processed_children.append({
                        "title": combined_title,
                        "fields": fields,
                        "markers": markers,
                        "children": []
                    })
                else:
                    processed_children.append(child)
            
            processed.append({
                "title": title,
                "children": processed_children,
                "note": item.get("note"),
                "fields": item.get("fields")
            })
        
        return processed
    
    def _generate_case_id(self, module_path: str = "") -> str:
        """
        生成用例编号
        
        Args:
            module_path: 模块路径（如 "2.1.1"）
        
        Returns:
            用例编号（如 TC-001 或 TC-2.1.1-001）
        """
        if module_path:
            # 基于模块路径生成编号
            if module_path not in self.module_counters:
                self.module_counters[module_path] = 0
            self.module_counters[module_path] += 1
            return f"TC-{module_path}-{self.module_counters[module_path]:03d}"
        else:
            # 全局计数器
            self.case_counter += 1
            return f"TC-{self.case_counter:03d}"
    
    def _determine_priority(self, test_type: str, case_name: str, parent_title: str = "") -> str:
        """
        根据测试类型和功能重要性确定优先级
        
        Args:
            test_type: 测试类型（正向用例/负向用例/边界值用例/异常用例）
            case_name: 用例名称
            parent_title: 父节点标题
        
        Returns:
            优先级（P0/P1/P2）
        """
        # P0: 核心功能的正向用例
        if test_type == "正向用例":
            # 判断是否为核心功能
            core_keywords = ["登录", "注册", "支付", "下单", "提交", "保存"]
            if any(keyword in case_name or (parent_title and keyword in parent_title) 
                   for keyword in core_keywords):
                return "P0"
            return "P1"
        
        # P1: 一般功能的正向用例、负向用例
        if test_type == "负向用例":
            return "P1"
        
        # P2: 边界值用例、异常用例
        if test_type in ["边界值用例", "异常用例"]:
            return "P2"
        
        return "P1"
    
    def _generate_test_case_fields(self, case_name: str, test_type: str, 
                                   parent_title: str = "", 
                                   module_path: str = "") -> Dict[str, str]:
        """
        为测试用例生成字段信息（Excel 格式）
        
        Args:
            case_name: 用例名称
            test_type: 测试类型（正向用例/负向用例/边界值用例/异常用例）
            parent_title: 父节点标题，用于生成前置条件
            module_path: 模块路径，用于生成用例编号
        
        Returns:
            字段信息字典，包含：用例编号、用例名称、测试类型、前置条件、测试步骤、预期结果、优先级、执行结果
        """
        # 生成用例编号
        case_id = self._generate_case_id(module_path)
        
        # 根据测试类型确定测试类型字段
        type_mapping = {
            "正向用例": "功能测试",
            "负向用例": "功能测试",
            "边界值用例": "边界值测试",
            "异常用例": "异常测试"
        }
        
        # 生成前置条件（使用可配置规则）
        preconditions = self._generate_preconditions(parent_title)
        
        # 生成测试步骤（使用可配置规则）
        test_steps = self._generate_test_steps(case_name, test_type, parent_title)
        
        # 生成预期结果（使用可配置规则）
        expected_result = self._generate_expected_result(case_name, test_type, parent_title)
        
        # 确定优先级
        priority = self._determine_priority(test_type, case_name, parent_title)
        
        return {
            "case_id": case_id,
            "case_name": case_name,
            "test_type": type_mapping.get(test_type, "功能测试"),
            "preconditions": preconditions,
            "test_steps": test_steps,
            "expected_result": expected_result,
            "priority": priority,
            "execution_result": ""  # 执行结果默认为空
        }
    
    def _generate_preconditions(self, parent_title: str = "") -> str:
        """
        生成前置条件（使用可配置规则）
        
        Args:
            parent_title: 父节点标题
            
        Returns:
            前置条件字符串
        """
        if not parent_title:
            return self.precondition_rules.get('default', '系统正常运行')
        
        # 检查关键词匹配规则
        keywords = self.precondition_rules.get('keywords', {})
        for keyword, precondition in keywords.items():
            if keyword in parent_title:
                return precondition
        
        return self.precondition_rules.get('default', '系统正常运行')
    
    def _generate_markers(self, test_type: str, priority: str) -> List[str]:
        """
        生成 markers（测试类型和优先级）
        
        Args:
            test_type: 测试类型（功能测试/边界值测试/异常测试）
            priority: 优先级（P0/P1/P2）
        
        Returns:
            markers 列表
        """
        markers = []
        
        # 测试类型映射到 markers
        test_type_mapping = {
            "功能测试": "flag-blue",
            "边界值测试": "flag-yellow",
            "异常测试": "flag-red"
        }
        
        # 优先级映射到 markers
        priority_mapping = {
            "P0": "priority-1",
            "P1": "priority-2",
            "P2": "priority-3"
        }
        
        # 添加测试类型 marker
        if test_type and test_type in test_type_mapping:
            markers.append(test_type_mapping[test_type])
        
        # 添加优先级 marker
        if priority and priority in priority_mapping:
            markers.append(priority_mapping[priority])
        
        return markers
    
    def _generate_test_steps(self, case_name: str, test_type: str, 
                             parent_title: str = "") -> str:
        """
        生成测试步骤（使用可配置规则）
        
        Args:
            case_name: 用例名称
            test_type: 测试类型
            parent_title: 父节点标题
            
        Returns:
            测试步骤字符串
        """
        # 优先使用配置的规则
        if test_type in self.test_step_rules:
            rule = self.test_step_rules[test_type]
            if callable(rule):
                return rule(case_name, parent_title)
            elif isinstance(rule, str):
                return rule.format(case_name=case_name, parent_title=parent_title)
            return rule
        
        # 默认通用模板
        return f"1. 执行测试场景：{case_name}\n2. 验证系统响应"
    
    def _generate_expected_result(self, case_name: str, test_type: str, 
                                  parent_title: str = "") -> str:
        """
        生成预期结果（使用可配置规则）
        
        Args:
            case_name: 用例名称
            test_type: 测试类型
            parent_title: 父节点标题
            
        Returns:
            预期结果字符串
        """
        # 优先使用配置的规则
        if test_type in self.expected_result_rules:
            rule = self.expected_result_rules[test_type]
            if callable(rule):
                return rule(case_name, parent_title)
            elif isinstance(rule, str):
                return rule.format(case_name=case_name, parent_title=parent_title)
            return rule
        
        # 默认通用模板
        return f"系统按照预期处理：{case_name}"
    
    def create_test_cases_structure(self, requirements_structure: List[Dict]) -> List[Dict]:
        """
        根据需求结构生成测试用例结构
        
        为每个功能点生成对应的测试用例分类（正向、负向、边界值等）
        注意：字段信息会在 generate_xmind 时自动生成
        
        Args:
            requirements_structure: 需求结构
        
        Returns:
            测试用例结构
        """
        test_cases_structure = []
        
        def process_node(node: Dict, parent_path: str = ""):
            """递归处理节点，生成测试用例"""
            title = node.get("title", "")
            children = node.get("children", [])
            
            # 如果是功能点（包含特定关键词），生成测试用例分类
            if any(keyword in title for keyword in ['设置', '上传', '输入', '显示', '校验', '功能']):
                test_case_node = {
                    "title": f"{title} - 测试用例",
                    "children": [
                        {"title": "正向用例", "children": []},
                        {"title": "负向用例", "children": []},
                        {"title": "边界值用例", "children": []},
                        {"title": "异常用例", "children": []}
                    ]
                }
                test_cases_structure.append(test_case_node)
            
            # 递归处理子节点
            for child in children:
                process_node(child, f"{parent_path} > {title}")
        
        for node in requirements_structure:
            process_node(node)
        
        return test_cases_structure if test_cases_structure else requirements_structure


def main():
    """示例用法"""
    generator = XMindGenerator()
    
    # 示例1：从需求文档生成（自动生成字段信息）
    requirements = """2.1 用户信息展示
2.1.1 基础信息
头像设置
上传规则：支持JPG/PNG格式，大小≤2MB
昵称与唯一性校验
规则：1-20字符，禁止特殊符号
简介与标签
输入限制：最多100字
粉丝/关注数显示
动态格式化：≥1万显示为"1.2w"
"""
    
    # 解析需求并生成结构
    structure = generator.parse_requirements_to_structure(requirements)
    
    # 生成测试用例结构
    test_cases = generator.create_test_cases_structure(structure)
    
    # 生成 XMind 文件（字段信息会自动生成）
    output = generator.generate_xmind(
        "test_cases.xmind",
        "测试用例",
        test_cases
    )
    
    print(f"XMind 文件已生成: {output}")
    
    # 示例2：手动构建带字段信息的测试用例结构
    print("\n示例2：手动构建带字段信息的测试用例")
    manual_structure = [
        {
            "title": "登录功能 - 测试用例",
            "children": [
                {
                    "title": "正向用例",
                    "children": [
                        {
                            "title": "正常登录",
                            "fields": {
                                "case_name": "正常登录",
                                "test_type": "功能测试",
                                "preconditions": "用户已注册账号",
                                "test_steps": "1. 打开登录页面\n2. 输入正确的用户名和密码\n3. 点击登录按钮",
                                "expected_result": "登录成功，跳转到主页"
                            },
                            "children": []
                        }
                    ]
                },
                {
                    "title": "负向用例",
                    "children": [
                        "错误密码",
                        "不存在的用户名"
                    ]
                }
            ]
        }
    ]
    
    output2 = generator.generate_xmind(
        "manual_test_cases.xmind",
        "手动测试用例",
        manual_structure
    )
    
    print(f"手动构建的 XMind 文件已生成: {output2}")
    print("\n注意：字符串类型的测试用例会自动生成字段信息")


if __name__ == "__main__":
    main()
