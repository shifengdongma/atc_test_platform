#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import xml.etree.ElementTree as ET

def analyze_jmx(filepath, label):
    print(f'\n=== {label} ===')
    tree = ET.parse(filepath)
    root = tree.getroot()
    
    # 找到根hashTree
    for ht in root:
        if ht.tag == 'hashTree':
            for i, child in enumerate(ht):
                tag = child.tag
                name = child.get('testname', '')
                display = name[:40] if name else '(empty)'
                print(f'{i}: {tag} = {display}')

# 分析两个文件
analyze_jmx('01_起降场管理场景_sit.jmx', '修改后的文件')
analyze_jmx('../用例demo/空域情报_起降场.jmx', 'Demo原始文件')
