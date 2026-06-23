#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw.io 文件生成器
将 XML 内容保存为 .drawio 文件
"""

import argparse
import os
import sys
from pathlib import Path


def generate_drawio_file(output_path: str, xml_content: str, encoding: str = 'utf-8') -> str:
    """
    生成 Draw.io 文件
    
    Args:
        output_path: 输出文件路径
        xml_content: XML 内容
        encoding: 文件编码
    
    Returns:
        生成的文件路径
    """
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"创建目录: {output_dir}")
    
    # 确保文件扩展名为 .drawio
    if not output_path.endswith('.drawio'):
        output_path += '.drawio'
    
    # 写入文件
    with open(output_path, 'w', encoding=encoding) as f:
        f.write(xml_content)
    
    return output_path


def read_xml_from_file(file_path: str, encoding: str = 'utf-8') -> str:
    """
    从文件读取 XML 内容
    
    Args:
        file_path: XML 文件路径
        encoding: 文件编码
    
    Returns:
        XML 内容
    """
    with open(file_path, 'r', encoding=encoding) as f:
        return f.read()


def validate_xml(xml_content: str) -> bool:
    """
    简单验证 XML 格式
    
    Args:
        xml_content: XML 内容
    
    Returns:
        是否有效
    """
    # 检查基本标签
    required_tags = ['<mxfile', '</mxfile>', '<diagram', '</diagram>']
    for tag in required_tags:
        if tag not in xml_content:
            print(f"警告: 缺少必要的标签 {tag}")
            return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description='生成 Draw.io 图表文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 从字符串生成
  python generate_drawio.py --output "F:\\下载\\图表.drawio" --content "<mxfile>...</mxfile>"
  
  # 从文件生成
  python generate_drawio.py --output "F:\\下载\\图表.drawio" --file "content.xml"
  
  # 指定图表名称
  python generate_drawio.py --output "F:\\下载\\图表.drawio" --content "<mxfile>...</mxfile>" --diagram-name "流程图"
        """
    )
    
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='输出文件路径（例如: F:\\\\下载\\\\图表.drawio）'
    )
    
    content_group = parser.add_mutually_exclusive_group(required=True)
    content_group.add_argument(
        '--content', '-c',
        help='XML 内容字符串'
    )
    content_group.add_argument(
        '--file', '-f',
        help='包含 XML 内容的文件路径'
    )
    
    parser.add_argument(
        '--diagram-name', '-n',
        default='Page-1',
        help='图表名称（默认: Page-1）'
    )
    
    parser.add_argument(
        '--encoding', '-e',
        default='utf-8',
        help='文件编码（默认: utf-8）'
    )
    
    args = parser.parse_args()
    
    # 获取 XML 内容
    if args.file:
        if not os.path.exists(args.file):
            print(f"错误: 文件不存在 {args.file}")
            sys.exit(1)
        xml_content = read_xml_from_file(args.file, args.encoding)
        print(f"从文件读取 XML: {args.file}")
    else:
        xml_content = args.content
        print("使用命令行传入的 XML 内容")
    
    # 验证 XML
    if not validate_xml(xml_content):
        print("警告: XML 格式可能不正确，继续生成...")
    
    # 替换图表名称（如果指定）
    if args.diagram_name != 'Page-1' and 'name="Page-1"' in xml_content:
        xml_content = xml_content.replace('name="Page-1"', f'name="{args.diagram_name}"')
        print(f"设置图表名称: {args.diagram_name}")
    
    # 生成文件
    try:
        output_file = generate_drawio_file(args.output, xml_content, args.encoding)
        file_size = os.path.getsize(output_file)
        print(f"成功生成 Draw.io 文件:")
        print(f"   路径: {os.path.abspath(output_file)}")
        print(f"   大小: {file_size} 字节")
    except Exception as e:
        print(f"生成文件失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
