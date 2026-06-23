#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试方案生成器
根据输入信息在本地自动生成Word测试方案文档

隐私说明：
- 所有文件解析均在本地完成
- 使用本地Python库（python-docx, openpyxl, xmindparser, pillow）处理文件
- 不会上传任何数据到后台或服务器
- 所有数据仅在本地内存中处理，生成后保存到指定输出目录
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    print("错误：未安装 python-docx。请运行: pip install python-docx")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    from xmindparser import xmind_to_dict
except ImportError:
    xmind_to_dict = None

try:
    from PIL import Image
except ImportError:
    Image = None


class TestPlanGenerator:
    """测试方案生成器主类"""
    
    # 默认输出目录
    DEFAULT_OUTPUT_DIR = r"F:\下载"
    
    # 模板变量默认值
    DEFAULT_VARS = {
        'plan_title': '测试方案',
        'plan_date': datetime.now().strftime('%Y-%m-%d'),
        'project_name': '',
        'version': 'V1.0',
        'author': '',
        'reviewer': '',
        'approve_date': '',
        'total_requirements': '0',
        'total_modules': '0',
        'test_types': '功能测试',
        'estimated_duration': ''
    }
    
    def __init__(self, template_path: str, output_dir: str = None):
        """
        初始化生成器
        
        Args:
            template_path: Word模板文件路径
            output_dir: 输出目录，默认为 F:\下载
        """
        self.template_path = Path(template_path)
        self.output_dir = Path(output_dir or self.DEFAULT_OUTPUT_DIR)
        self.variables = self.DEFAULT_VARS.copy()
        self.excel_data = []
        self.xmind_data = []
        self.word_data = []
        self.text_data = ""
        self.image_paths = []
        
        # 验证模板文件
        if not self.template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def set_variable(self, name: str, value: str):
        """设置模板变量"""
        self.variables[name] = value
    
    def set_variables(self, variables: Dict[str, str]):
        """批量设置模板变量"""
        self.variables.update(variables)
    
    def load_excel(self, excel_path: str) -> List[Dict]:
        """
        在本地加载Excel文件数据
        
        Args:
            excel_path: Excel文件路径
            
        Returns:
            工作表数据列表
        """
        if openpyxl is None:
            print("警告：未安装 openpyxl，无法处理Excel文件")
            return []
        
        try:
            wb = openpyxl.load_workbook(excel_path, data_only=True)
            data = []
            
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                sheet_data = {
                    'name': sheet_name,
                    'headers': [],
                    'rows': []
                }
                
                # 读取表头（第一行）
                for cell in sheet[1]:
                    sheet_data['headers'].append(str(cell.value) if cell.value else '')
                
                # 读取数据行
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    row_data = [str(cell) if cell is not None else '' for cell in row]
                    if any(row_data):  # 跳过空行
                        sheet_data['rows'].append(row_data)
                
                data.append(sheet_data)
                
                # 统计数据
                self._extract_stats(sheet_data)
            
            self.excel_data = data
            print(f"已在本地加载Excel文件: {excel_path}，共 {len(data)} 个工作表")
            return data
            
        except Exception as e:
            print(f"加载Excel文件失败: {e}")
            return []
    
    def _extract_stats(self, sheet_data: Dict):
        """从Excel数据中提取统计信息"""
        headers = sheet_data['headers']
        rows = sheet_data['rows']
        
        # 统计需求数量
        if rows:
            current_total = int(self.variables['total_requirements'])
            self.variables['total_requirements'] = str(current_total + len(rows))
        
        # 统计模块数量（如果有模块/功能列）
        module_col = -1
        for i, h in enumerate(headers):
            if h and ('模块' in h or '功能' in h or '模块名称' in h):
                module_col = i
                break
        
        if module_col >= 0 and rows:
            modules = set()
            for row in rows:
                if module_col < len(row) and row[module_col]:
                    modules.add(row[module_col])
            self.variables['total_modules'] = str(len(modules))
    
    def load_xmind(self, xmind_path: str) -> List[Dict]:
        """
        在本地加载Xmind文件数据
        
        Args:
            xmind_path: Xmind文件路径
            
        Returns:
            主题数据列表
        """
        if xmind_to_dict is None:
            print("警告：未安装 xmindparser，无法处理Xmind文件")
            return []
        
        try:
            data = xmind_to_dict(xmind_path)
            self.xmind_data = data
            print(f"已在本地加载Xmind文件: {xmind_path}")
            
            # 统计模块数
            self._count_modules_from_xmind(data)
            
            return data
        except Exception as e:
            print(f"加载Xmind文件失败: {e}")
            return []
    
    def _count_modules_from_xmind(self, data: List[Dict]):
        """从Xmind数据统计模块数量"""
        def count_topics(topics, count=0):
            if isinstance(topics, list):
                for topic in topics:
                    count += 1
                    if isinstance(topic, dict):
                        children = topic.get('topics', [])
                        count = count_topics(children, count)
            elif isinstance(topics, dict):
                count += 1
                children = topics.get('topics', [])
                count = count_topics(children, count)
            return count
        
        total = 0
        for sheet in data:
            if isinstance(sheet, dict):
                topic = sheet.get('topic', {})
                children = topic.get('topics', [])
                total += count_topics(children)
        
        if total > 0:
            self.variables['total_modules'] = str(total)
    
    def load_word(self, word_path: str) -> Document:
        """
        在本地加载Word文件内容
        
        Args:
            word_path: Word文件路径
            
        Returns:
            Document对象
        """
        try:
            doc = Document(word_path)
            self.word_data.append(doc)
            print(f"已在本地加载Word文件: {word_path}")
            return doc
        except Exception as e:
            print(f"加载Word文件失败: {e}")
            return None
    
    def load_image(self, image_path: str):
        """
        在本地加载图片文件
        
        Args:
            image_path: 图片文件路径
        """
        if Image is None:
            print("警告：未安装 Pillow，无法处理图片文件")
            return
        
        try:
            img = Image.open(image_path)
            self.image_paths.append(image_path)
            print(f"已在本地加载图片: {image_path}")
        except Exception as e:
            print(f"加载图片失败: {e}")
    
    def set_text_data(self, text: str):
        """设置文字描述数据"""
        self.text_data = text
    
    def _replace_variables_in_paragraph(self, paragraph):
        """在段落中替换变量"""
        full_text = paragraph.text
        
        # 查找所有变量占位符 {{variable_name}}
        pattern = r'\{\{(\w+)\}\}'
        matches = re.findall(pattern, full_text)
        
        if matches:
            for var_name in matches:
                if var_name in self.variables:
                    placeholder = f'{{{{{var_name}}}}}'
                    full_text = full_text.replace(placeholder, str(self.variables[var_name]))
            
            if paragraph.runs:
                first_run = paragraph.runs[0]
                font_name = first_run.font.name
                font_size = first_run.font.size
                bold = first_run.font.bold
                
                for run in paragraph.runs:
                    run.text = ''
                
                paragraph.runs[0].text = full_text
                
                if font_name:
                    paragraph.runs[0].font.name = font_name
                if font_size:
                    paragraph.runs[0].font.size = font_size
                if bold is not None:
                    paragraph.runs[0].font.bold = bold
    
    def _replace_variables_in_table(self, table):
        """在表格中替换变量"""
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    self._replace_variables_in_paragraph(paragraph)
    
    def _add_excel_data_to_doc(self, doc: Document):
        """将Excel数据添加到文档"""
        for sheet in self.excel_data:
            heading = doc.add_heading(sheet['name'], level=2)
            
            if sheet['rows']:
                table = doc.add_table(rows=1, cols=len(sheet['headers']))
                table.style = 'Light Grid Accent 1'
                
                hdr_cells = table.rows[0].cells
                for i, header in enumerate(sheet['headers']):
                    if i < len(hdr_cells):
                        hdr_cells[i].text = header
                
                for row_data in sheet['rows']:
                    row_cells = table.add_row().cells
                    for i, value in enumerate(row_data):
                        if i < len(row_cells):
                            row_cells[i].text = value
                
                doc.add_paragraph()
    
    def _add_xmind_data_to_doc(self, doc: Document):
        """将Xmind数据添加到文档"""
        def add_topic(topic, level=2):
            if isinstance(topic, dict):
                title = topic.get('title', '')
                if title:
                    doc.add_heading(title, level=min(level, 6))
                
                note = topic.get('note', '')
                if note:
                    doc.add_paragraph(note)
                
                children = topic.get('topics', [])
                for child in children:
                    add_topic(child, level + 1)
        
        for sheet in self.xmind_data:
            if isinstance(sheet, dict) and 'topic' in sheet:
                add_topic(sheet['topic'])
    
    def _add_text_data_to_doc(self, doc: Document):
        """将文字描述添加到文档"""
        if self.text_data:
            found = False
            for paragraph in doc.paragraphs:
                if '测试范围' in paragraph.text or '测试目标' in paragraph.text:
                    p = paragraph._element
                    new_p = doc.add_paragraph(self.text_data)
                    p.addnext(new_p._element)
                    found = True
                    break
            
            if not found:
                doc.add_heading('测试范围说明', level=2)
                doc.add_paragraph(self.text_data)
    
    def _add_images_to_doc(self, doc: Document):
        """将图片添加到文档"""
        if self.image_paths:
            doc.add_heading('参考图片', level=2)
            for img_path in self.image_paths:
                try:
                    doc.add_picture(img_path, width=Inches(6))
                    doc.add_paragraph()
                except Exception as e:
                    print(f"插入图片失败 {img_path}: {e}")
    
    def generate(self, output_filename: str = None) -> str:
        """
        生成测试方案
        
        Args:
            output_filename: 输出文件名
            
        Returns:
            生成的文件路径
        """
        doc = Document(str(self.template_path))
        print(f"已在本地加载模板: {self.template_path}")
        
        print("正在替换模板变量...")
        for paragraph in doc.paragraphs:
            self._replace_variables_in_paragraph(paragraph)
        
        for table in doc.tables:
            self._replace_variables_in_table(table)
        
        if self.excel_data:
            print("正在添加Excel数据...")
            self._add_excel_data_to_doc(doc)
        
        if self.xmind_data:
            print("正在添加Xmind数据...")
            self._add_xmind_data_to_doc(doc)
        
        if self.text_data:
            print("正在添加文字描述...")
            self._add_text_data_to_doc(doc)
        
        if self.image_paths:
            print("正在添加图片...")
            self._add_images_to_doc(doc)
        
        if not output_filename:
            project_name = self.variables.get('project_name', '项目')
            date_str = datetime.now().strftime('%Y%m%d')
            output_filename = f"{project_name}_测试方案_{date_str}.docx"
        
        output_path = self.output_dir / output_filename
        
        doc.save(str(output_path))
        print(f"测试方案已生成: {output_path}")
        
        return str(output_path)


def main():
    parser = argparse.ArgumentParser(description='测试方案生成器（本地处理）')
    parser.add_argument('--template', '-t', required=True, help='Word模板文件路径')
    parser.add_argument('--output', '-o', default=r'F:\下载', help='输出目录')
    parser.add_argument('--input-excel', '-e', help='输入Excel文件路径')
    parser.add_argument('--input-xmind', '-x', help='输入Xmind文件路径')
    parser.add_argument('--input-word', '-w', help='输入Word文件路径')
    parser.add_argument('--input-image', '-i', action='append', help='输入图片文件路径（可多次使用）')
    parser.add_argument('--input-data', '-d', help='文字描述数据')
    parser.add_argument('--project-name', '-p', help='项目名称')
    parser.add_argument('--author', help='编写人')
    parser.add_argument('--reviewer', help='审核人')
    parser.add_argument('--version', '-v', default='V1.0', help='版本号')
    parser.add_argument('--estimated-duration', help='预计工期')
    parser.add_argument('--output-filename', help='输出文件名')
    
    args = parser.parse_args()
    
    try:
        generator = TestPlanGenerator(args.template, args.output)
        
        if args.project_name:
            generator.set_variable('project_name', args.project_name)
        if args.author:
            generator.set_variable('author', args.author)
        if args.reviewer:
            generator.set_variable('reviewer', args.reviewer)
        if args.version:
            generator.set_variable('version', args.version)
        if args.estimated_duration:
            generator.set_variable('estimated_duration', args.estimated_duration)
        
        if args.input_excel:
            generator.load_excel(args.input_excel)
        
        if args.input_xmind:
            generator.load_xmind(args.input_xmind)
        
        if args.input_word:
            generator.load_word(args.input_word)
        
        if args.input_image:
            for img_path in args.input_image:
                generator.load_image(img_path)
        
        if args.input_data:
            generator.set_text_data(args.input_data)
        
        output_path = generator.generate(args.output_filename)
        print(f"\n生成成功！文件位置: {output_path}")
        print("提示：请在Word中按 Ctrl+A 后 F9 刷新目录")
        
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
