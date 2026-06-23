#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调整JMX文件结构以适应MeterSphere平台
- 移除TransactionController分组
- 将HTTP请求直接放在ThreadGroup下，使每个请求成为独立步骤
"""

import xml.etree.ElementTree as ET
import shutil
from pathlib import Path

def fix_jmx_for_metersphere(input_file, output_file):
    """
    调整JMX文件结构：
    1. 保留 TestPlan 和 ThreadGroup 结构
    2. 移除 TransactionController 分组
    3. 将 HTTPSamplerProxy 直接放在 ThreadGroup 的 hashTree 下
    4. 保留每个请求的子元素（断言、HeaderManager等）
    """
    tree = ET.parse(input_file)
    root = tree.getroot()
    
    # 注册命名空间
    ET.register_namespace('', '')
    
    # 找到 ThreadGroup 下的 hashTree
    # 结构: jmeterTestPlan -> hashTree -> TestPlan -> hashTree -> ThreadGroup -> hashTree
    jmeter_test_plan = root
    root_hash_tree = None
    test_plan = None
    test_plan_hash_tree = None
    thread_group = None
    thread_group_hash_tree = None
    
    for child in jmeter_test_plan:
        if child.tag == 'hashTree':
            root_hash_tree = child
            break
    
    if root_hash_tree is None:
        print("错误：找不到根hashTree")
        return False
    
    # 根hashTree下: TestPlan, hashTree, ThreadGroup, hashTree
    # ThreadGroup 在根hashTree下，和TestPlan同级
    children = list(root_hash_tree)
    for i, child in enumerate(children):
        if child.tag == 'TestPlan':
            test_plan = child
        elif child.tag == 'ThreadGroup':
            thread_group = child
            # ThreadGroup 后面的 hashTree 就是 thread_group_hash_tree
            if i + 1 < len(children) and children[i + 1].tag == 'hashTree':
                thread_group_hash_tree = children[i + 1]
    
    if thread_group_hash_tree is None:
        print("错误：找不到ThreadGroup的hashTree")
        print(f"  test_plan: {test_plan is not None}")
        print(f"  thread_group: {thread_group is not None}")
        return False
    
    print(f"找到 ThreadGroup: {thread_group.get('testname', '')}")
    
    # 收集所有需要保留的元素
    # 1. CookieManager (如果有)
    # 2. 所有 HTTPSamplerProxy 及其子元素
    
    elements_to_keep = []
    
    # 遍历 ThreadGroup 的 hashTree 子元素
    i = 0
    children = list(thread_group_hash_tree)
    while i < len(children):
        child = children[i]
        
        # 保留 CookieManager
        if child.tag == 'CookieManager':
            elements_to_keep.append((child, None))  # (元素, 子hashTree)
            if i + 1 < len(children) and children[i + 1].tag == 'hashTree':
                elements_to_keep.append((children[i + 1], None))
                i += 1
        
        # 处理 TransactionController - 提取其中的 HTTPSamplerProxy
        elif child.tag == 'TransactionController':
            tc_name = child.get('testname', '')
            print(f"  处理 TransactionController: {tc_name}")
            
            # 获取 TransactionController 的 hashTree
            if i + 1 < len(children) and children[i + 1].tag == 'hashTree':
                tc_hash_tree = children[i + 1]
                
                # 提取其中的所有 HTTPSamplerProxy
                tc_children = list(tc_hash_tree)
                j = 0
                while j < len(tc_children):
                    tc_child = tc_children[j]
                    if tc_child.tag == 'HTTPSamplerProxy':
                        # 保留这个请求及其子hashTree
                        elements_to_keep.append((tc_child, None))
                        if j + 1 < len(tc_children) and tc_children[j + 1].tag == 'hashTree':
                            elements_to_keep.append((tc_children[j + 1], None))
                            j += 1
                    j += 1
                
                i += 1  # 跳过 TransactionController 的 hashTree
        
        # 直接保留其他元素（如 DebugSampler）
        elif child.tag not in ['TransactionController', 'hashTree']:
            elements_to_keep.append((child, None))
            if i + 1 < len(children) and children[i + 1].tag == 'hashTree':
                elements_to_keep.append((children[i + 1], None))
                i += 1
        
        i += 1
    
    # 创建 GenericController 来包裹所有请求
    # 这是 MeterSphere 识别 CASE 的关键
    generic_controller = ET.Element('GenericController', {
        'guiclass': 'LogicControllerGui',
        'testclass': 'GenericController',
        'testname': f"Generic_{thread_group.get('testname', 'Scene')}",
        'enabled': 'true'
    })
    
    # 创建 GenericController 的 hashTree
    generic_hash_tree = ET.Element('hashTree')
    
    # 将所有 HTTP 请求添加到 GenericController 的 hashTree 中
    for elem, _ in elements_to_keep:
        if elem.tag == 'HTTPSamplerProxy':
            generic_hash_tree.append(elem)
            # 同时添加一个空的 hashTree 作为占位（保持结构完整）
            placeholder = ET.Element('hashTree')
            generic_hash_tree.append(placeholder)
    
    # 清空 ThreadGroup 的 hashTree
    for child in list(thread_group_hash_tree):
        thread_group_hash_tree.remove(child)
    
    # 添加 CookieManager（如果有）
    for elem, _ in elements_to_keep:
        if elem.tag == 'CookieManager':
            thread_group_hash_tree.append(elem)
            # 添加对应的 hashTree
            cookie_hash = ET.Element('hashTree')
            thread_group_hash_tree.append(cookie_hash)
    
    # 添加 GenericController 及其 hashTree
    thread_group_hash_tree.append(generic_controller)
    thread_group_hash_tree.append(generic_hash_tree)
    
    print(f"GenericController 包含请求数: {len(list(generic_hash_tree)) // 2}")
    
    # 保存修改后的文件
    tree.write(output_file, encoding='UTF-8', xml_declaration=True)
    print(f"已保存到: {output_file}")
    
    return True

if __name__ == '__main__':
    input_file = '01_起降场管理场景_sit.jmx'
    output_file = '01_起降场管理场景_sit.jmx'
    
    # 备份原文件
    backup_file = '01_起降场管理场景_sit.jmx.backup'
    if not Path(backup_file).exists():
        shutil.copy(input_file, backup_file)
        print(f"已创建备份: {backup_file}")
    
    fix_jmx_for_metersphere(input_file, output_file)
    print("\n修改完成！")
