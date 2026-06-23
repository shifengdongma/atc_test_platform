#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试报告生成器
根据输入数据在本地自动生成Word测试报告

隐私说明：
- 所有文件解析均在本地完成
- 使用本地Python库（python-docx, openpyxl, xmindparser）处理文件
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
    from docx.shared import Inches, Pt, RGBColor
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


class TestReportGenerator:
    """测试报告生成器主类"""
    
    # 默认输出目录
    DEFAULT_OUTPUT_DIR = r"F:\下载"
    
    # 模板变量默认值
    DEFAULT_VARS = {
        'report_title': '测试报告',
        'report_date': datetime.now().strftime('%Y-%m-%d'),
        'test_period': '',
        'tester': '',
        'project_name': '',
        'total_cases': '0',
        'passed_cases': '0',
        'failed_cases': '0',
        'blocked_cases': '0',
        'pass_rate': '0%'
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
        加载Excel文件数据
        
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
                
                # 统计测试用例数据
                self._extract_test_stats(sheet_data)
            
            self.excel_data = data
            print(f"已加载Excel文件: {excel_path}，共 {len(data)} 个工作表")
            return data
            
        except Exception as e:
            print(f"加载Excel文件失败: {e}")
            return []
    
    def _extract_test_stats(self, sheet_data: Dict):
        """从Excel数据中提取测试统计信息"""
        headers = sheet_data['headers']
        rows = sheet_data['rows']
        
        # 查找结果列
        result_col = -1
        for i, h in enumerate(headers):
            if h and '结果' in h or '状态' in h or '通过' in h or 'status' in h.lower():
                result_col = i
                break
        
        if result_col >= 0 and rows:
            total = len(rows)
            passed = sum(1 for r in rows if result_col < len(r) and 
                        r[result_col] and ('通过' in r[result_col] or 'Pass' in r[result_col] or 'pass' in r[result_col]))
            failed = sum(1 for r in rows if result_col < len(r) and 
                        r[result_col] and ('失败' in r[result_col] or 'Fail' in r[result_col] or 'fail' in r[result_col]))
            blocked = sum(1 for r in rows if result_col < len(r) and 
                         r[result_col] and ('阻塞' in r[result_col] or 'Block' in r[result_col] or 'block' in r[result_col]))
            
            self.variables['total_cases'] = str(int(self.variables['total_cases']) + total)
            self.variables['passed_cases'] = str(int(self.variables['passed_cases']) + passed)
            self.variables['failed_cases'] = str(int(self.variables['failed_cases']) + failed)
            self.variables['blocked_cases'] = str(int(self.variables['blocked_cases']) + blocked)
            
            if total > 0:
                pass_rate = (passed / total) * 100
                self.variables['pass_rate'] = f"{pass_rate:.2f}%"
    
    def load_xmind(self, xmind_path: str) -> List[Dict]:
        """
        加载Xmind文件数据
        
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
            print(f"已加载Xmind文件: {xmind_path}")
            return data
        except Exception as e:
            print(f"加载Xmind文件失败: {e}")
            return []
    
    def load_word(self, word_path: str) -> Document:
        """
        加载Word文件内容
        
        Args:
            word_path: Word文件路径
            
        Returns:
            Document对象
        """
        try:
            doc = Document(word_path)
            self.word_data.append(doc)
            print(f"已加载Word文件: {word_path}")
            return doc
        except Exception as e:
            print(f"加载Word文件失败: {e}")
            return None
    
    def set_text_data(self, text: str):
        """设置文字描述数据"""
        self.text_data = text
    
    def _replace_variables_in_paragraph(self, paragraph):
        """在段落中替换变量"""
        # 获取段落完整文本
        full_text = paragraph.text
        
        # 查找所有变量占位符 {{variable_name}}
        pattern = r'\{\{(\w+)\}\}'
        matches = re.findall(pattern, full_text)
        
        if matches:
            # 替换变量
            for var_name in matches:
                if var_name in self.variables:
                    placeholder = f'{{{{{var_name}}}}}'
                    full_text = full_text.replace(placeholder, str(self.variables[var_name]))
            
            # 清空段落并重新设置文本
            if paragraph.runs:
                # 保留第一个run的格式
                first_run = paragraph.runs[0]
                font_name = first_run.font.name
                font_size = first_run.font.size
                bold = first_run.font.bold
                
                # 清空所有runs
                for run in paragraph.runs:
                    run.text = ''
                
                # 设置第一个run的文本
                paragraph.runs[0].text = full_text
                
                # 恢复格式
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
            # 添加工作表名称作为小标题
            heading = doc.add_heading(sheet['name'], level=2)
            
            # 创建表格
            if sheet['rows']:
                table = doc.add_table(rows=1, cols=len(sheet['headers']))
                table.style = 'Light Grid Accent 1'
                
                # 设置表头
                hdr_cells = table.rows[0].cells
                for i, header in enumerate(sheet['headers']):
                    if i < len(hdr_cells):
                        hdr_cells[i].text = header
                
                # 添加数据行
                for row_data in sheet['rows']:
                    row_cells = table.add_row().cells
                    for i, value in enumerate(row_data):
                        if i < len(row_cells):
                            row_cells[i].text = value
                
                doc.add_paragraph()  # 添加空行
    
    def _add_xmind_data_to_doc(self, doc: Document):
        """将Xmind数据添加到文档"""
        def add_topic(topic, level=2):
            if isinstance(topic, dict):
                title = topic.get('title', '')
                if title:
                    doc.add_heading(title, level=min(level, 6))
                
                # 添加备注
                note = topic.get('note', '')
                if note:
                    doc.add_paragraph(note)
                
                # 递归添加子主题
                children = topic.get('topics', [])
                for child in children:
                    add_topic(child, level + 1)
        
        for sheet in self.xmind_data:
            if isinstance(sheet, dict) and 'topic' in sheet:
                add_topic(sheet['topic'])
    
    def _add_text_data_to_doc(self, doc: Document):
        """将文字描述添加到文档"""
        if self.text_data:
            # 查找"测试概述"或类似章节
            found = False
            for paragraph in doc.paragraphs:
                if '测试概述' in paragraph.text or '概述' in paragraph.text:
                    # 在概述后添加文字描述
                    p = paragraph._element
                    new_p = doc.add_paragraph(self.text_data)
                    p.addnext(new_p._element)
                    found = True
                    break
            
            if not found:
                # 如果没有找到合适的章节，添加到文档末尾
                doc.add_heading('补充说明', level=2)
                doc.add_paragraph(self.text_data)
    
    def _update_toc(self, doc: Document):
        """
        更新目录
        注意：python-docx无法直接更新Word目录字段，需要在Word中手动刷新
        """
        # 查找目录段落（通常包含 TOC 字段）
        for paragraph in doc.paragraphs:
            if 'TOC' in paragraph.text or '目录' in paragraph.text:
                # 添加提示信息
                print("提示：文档已生成，请手动在Word中按 Ctrl+A 后 F9 刷新目录")
                break
    
    def generate(self, output_filename: str = None) -> str:
        """
        生成测试报告
        
        Args:
            output_filename: 输出文件名，默认为 {project_name}_测试报告_{日期}.docx
            
        Returns:
            生成的文件路径
        """
        # 加载模板
        doc = Document(str(self.template_path))
        print(f"已加载模板: {self.template_path}")
        
        # 替换所有变量
        print("正在替换模板变量...")
        for paragraph in doc.paragraphs:
            self._replace_variables_in_paragraph(paragraph)
        
        for table in doc.tables:
            self._replace_variables_in_table(table)
        
        # 添加Excel数据
        if self.excel_data:
            print("正在添加Excel数据...")
            self._add_excel_data_to_doc(doc)
        
        # 添加Xmind数据
        if self.xmind_data:
            print("正在添加Xmind数据...")
            self._add_xmind_data_to_doc(doc)
        
        # 添加文字描述
        if self.text_data:
            print("正在添加文字描述...")
            self._add_text_data_to_doc(doc)
        
        # 更新目录标记
        self._update_toc(doc)
        
        # 生成输出文件名
        if not output_filename:
            project_name = self.variables.get('project_name', '项目')
            date_str = datetime.now().strftime('%Y%m%d')
            output_filename = f"{project_name}_测试报告_{date_str}.docx"
        
        output_path = self.output_dir / output_filename
        
        # 保存文档
        doc.save(str(output_path))
        print(f"报告已生成: {output_path}")
        
        return str(output_path)


def main():
    parser = argparse.ArgumentParser(description='测试报告生成器')
    parser.add_argument('--template', '-t', required=True, help='Word模板文件路径')
    parser.add_argument('--output', '-o', default=r'F:\下载', help='输出目录')
    parser.add_argument('--input-excel', '-e', help='输入Excel文件路径')
    parser.add_argument('--input-xmind', '-x', help='输入Xmind文件路径')
    parser.add_argument('--input-word', '-w', help='输入Word文件路径')
    parser.add_argument('--input-data', '-d', help='文字描述数据')
    parser.add_argument('--project-name', '-p', help='项目名称')
    parser.add_argument('--tester', help='测试人员')
    parser.add_argument('--test-period', help='测试周期')
    parser.add_argument('--output-filename', help='输出文件名')
    
    args = parser.parse_args()
    
    try:
        # 创建生成器
        generator = TestReportGenerator(args.template, args.output)
        
        # 设置变量
        if args.project_name:
            generator.set_variable('project_name', args.project_name)
        if args.tester:
            generator.set_variable('tester', args.tester)
        if args.test_period:
            generator.set_variable('test_period', args.test_period)
        
        # 加载输入数据
        if args.input_excel:
            generator.load_excel(args.input_excel)
        
        if args.input_xmind:
            generator.load_xmind(args.input_xmind)
        
        if args.input_word:
            generator.load_word(args.input_word)
        
        if args.input_data:
            generator.set_text_data(args.input_data)
        
        # 生成报告
        output_path = generator.generate(args.output_filename)
        print(f"\n生成成功！文件位置: {output_path}")
        
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
