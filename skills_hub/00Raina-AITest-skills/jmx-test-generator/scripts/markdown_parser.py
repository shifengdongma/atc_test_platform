#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown 格式的 API 文档解析器
解析常见的 Markdown API 文档格式
"""

import re
from typing import Dict, List, Optional, Any
from pathlib import Path


class MarkdownAPIParser:
    """解析 Markdown 格式的 API 文档"""
    
    def __init__(self):
        self.content = ''
        self.endpoints = []
    
    def parse(self, file_path: str) -> List[Dict[str, Any]]:
        """
        解析 Markdown API 文档
        
        Args:
            file_path: Markdown 文件路径
        
        Returns:
            端点列表
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            self.content = f.read()
        
        return self._extract_endpoints()
    
    def parse_from_string(self, content: str) -> List[Dict[str, Any]]:
        """
        从字符串解析 Markdown API 文档
        
        Args:
            content: Markdown 内容
        
        Returns:
            端点列表
        """
        self.content = content
        return self._extract_endpoints()
    
    def _extract_endpoints(self) -> List[Dict[str, Any]]:
        """提取所有 API 端点"""
        endpoints = []
        
        # 匹配常见的 API 文档格式
        # 格式1: ## 接口名称\n**接口地址**:`/api/xxx`\n**请求方式**:`GET`
        pattern1 = r'##\s+(.+?)\n.*?\*\*接口地址\*\*[：:]\s*`([^`]+)`.*?\*\*请求方式\*\*[：:]\s*`([^`]+)`'
        
        # 格式2: ### GET /api/xxx
        pattern2 = r'###\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+([^\s\n]+)'
        
        # 格式3: ## API 名称\n**URL**: `/api/xxx`\n**Method**: `GET`
        pattern3 = r'##\s+(.+?)\n.*?\*\*URL\*\*[：:]\s*`([^`]+)`.*?\*\*Method\*\*[：:]\s*`([^`]+)`'
        
        # 格式4: ### 接口名称\n**接口URL**\n> /api/xxx\n**请求方式**\n> POST
        pattern4 = r'###\s+(.+?)\n.*?\*\*接口URL\*\*.*?>\s*([^\n]+).*?\*\*请求方式\*\*.*?>\s*([^\n]+)'
        
        # 尝试匹配格式1
        matches1 = re.finditer(pattern1, self.content, re.DOTALL | re.IGNORECASE)
        for match in matches1:
            # 提取完整的接口章节（从当前匹配到下一个接口或文档结束）
            section = self._extract_section(match.start(), match.end())
            endpoint = {
                'name': match.group(1).strip(),
                'path': match.group(2).strip(),
                'method': match.group(3).strip().upper(),
                'summary': match.group(1).strip(),
                'description': self._extract_description(section),
                'parameters': self._extract_parameters(section),
                'requestBody': self._extract_request_body(section),
                'responses': self._extract_responses(section),
                'tags': []
            }
            endpoints.append(endpoint)
        
        # 如果格式1没有匹配到，尝试格式2
        if not endpoints:
            matches2 = re.finditer(pattern2, self.content, re.IGNORECASE)
            for match in matches2:
                method = match.group(1).upper()
                path = match.group(2).strip()
                
                # 提取该接口的详细信息
                section = self._extract_section(match.start(), match.end())
                
                endpoint = {
                    'name': f"{method} {path}",
                    'path': path,
                    'method': method,
                    'summary': f"{method} {path}",
                    'description': self._extract_description(section),
                    'parameters': self._extract_parameters(section),
                    'requestBody': self._extract_request_body(section),
                    'responses': self._extract_responses(section),
                    'tags': []
                }
                endpoints.append(endpoint)
        
        # 如果格式2也没有匹配到，尝试格式3
        if not endpoints:
            matches3 = re.finditer(pattern3, self.content, re.DOTALL | re.IGNORECASE)
            for match in matches3:
                endpoint = {
                    'name': match.group(1).strip(),
                    'path': match.group(2).strip(),
                    'method': match.group(3).strip().upper(),
                    'summary': match.group(1).strip(),
                    'description': '',
                    'parameters': self._extract_parameters(match.group(0)),
                    'requestBody': self._extract_request_body(match.group(0)),
                    'responses': self._extract_responses(match.group(0)),
                    'tags': []
                }
                endpoints.append(endpoint)
        
        # 如果格式3也没有匹配到，尝试格式4（支持引用块格式）
        if not endpoints:
            matches4 = re.finditer(pattern4, self.content, re.DOTALL | re.IGNORECASE)
            for match in matches4:
                section = self._extract_section(match.start(), match.end())
                endpoint = {
                    'name': match.group(1).strip(),
                    'path': match.group(2).strip(),
                    'method': match.group(3).strip().upper(),
                    'summary': match.group(1).strip(),
                    'description': self._extract_description(section),
                    'parameters': self._extract_parameters(section),
                    'requestBody': self._extract_request_body(section),
                    'responses': self._extract_responses(section),
                    'tags': []
                }
                endpoints.append(endpoint)
        
        return endpoints
    
    def _extract_section(self, start: int, end: int) -> str:
        """提取接口章节内容"""
        # 找到下一个 ## 或 ### 标题的位置
        next_section = re.search(r'\n##', self.content[end:])
        if next_section:
            return self.content[start:end + next_section.start()]
        return self.content[start:]
    
    def _extract_description(self, section: str) -> str:
        """提取接口描述"""
        # 查找描述文本（通常在接口定义之后）
        desc_pattern = r'(?:接口描述|描述|Description)[：:]\s*(.+?)(?:\n\*\*|\n###|\n##|$)'
        match = re.search(desc_pattern, section, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ''
    
    def _extract_parameters(self, section: str) -> List[Dict[str, Any]]:
        """提取请求参数"""
        parameters = []
        
        # 分别匹配 Header、Body、Query 参数表格
        param_types = [
            ('请求Header参数', 'header'),
            ('请求Body参数', 'body'),
            ('请求参数', 'query')
        ]
        
        for param_type_name, param_in in param_types:
            # 匹配参数表格标题
            title_pattern = rf'\*\*{param_type_name}\*\*[：:]?\s*\n'
            title_match = re.search(title_pattern, section, re.IGNORECASE)
            if not title_match:
                continue
            
            # 从标题位置开始，查找第一个表格
            start_pos = title_match.end()
            # 跳过可能的代码块
            remaining_section = section[start_pos:]
            # 查找表格：| 参数名 | ...
            table_pattern = r'(\|[^\n]+\n\|[^\n]+\n)((?:\|[^\n]+\n?)+)'
            table_match = re.search(table_pattern, remaining_section, re.IGNORECASE)
            if not table_match:
                continue
            
            # 跳过表头行，处理数据行
            data_rows = table_match.group(2).strip().split('\n')
            for row in data_rows:
                if not row.strip() or not row.startswith('|'):
                    continue
                cols = [col.strip() for col in row.split('|')[1:-1]]  # 去掉首尾空元素
                if len(cols) >= 1 and cols[0] and cols[0] != '暂无参数':  # 至少要有参数名称，且不是"暂无参数"
                    # 根据表格列数判断格式
                    # 格式1: | 参数名 | 示例值 | 参数类型 | 是否必填 | 参数描述 | (5列)
                    # 格式2: | 参数名称 | 参数说明 | 请求类型 | 是否必须 | 数据类型 | (5列)
                    if len(cols) >= 5:
                        # 检查表头来确定格式
                        header_row = table_match.group(1)
                        if '示例值' in header_row or '参数类型' in header_row:
                            # 格式1: 参数名 | 示例值 | 参数类型 | 是否必填 | 参数描述
                            param_name = cols[0]
                            param_default = cols[1] if len(cols) > 1 and cols[1] != '-' else ''
                            param_type = cols[2] if len(cols) > 2 else 'string'
                            param_required = '是' in str(cols[3]) if len(cols) > 3 else False
                            param_desc = cols[4] if len(cols) > 4 else ''
                        else:
                            # 格式2: 参数名称 | 参数说明 | 请求类型 | 是否必须 | 数据类型
                            param_name = cols[0]
                            param_desc = cols[1] if len(cols) > 1 else ''
                            # param_in 已经在循环外定义
                            param_required = 'true' in str(cols[3]).lower() or '是' in str(cols[3]) if len(cols) > 3 else False
                            param_type = cols[4] if len(cols) > 4 else 'string'
                            param_default = ''
                    else:
                        # 简单格式
                        param_name = cols[0]
                        param_type = cols[1] if len(cols) > 1 else 'string'
                        param_required = False
                        param_desc = ''
                        param_default = ''
                    
                    # 解析数据类型
                    if '(' in param_type:
                        param_type = param_type.split('(')[0]
                    
                    param = {
                        'name': param_name,
                        'description': param_desc,
                        'in': param_in,
                        'required': param_required,
                        'type': param_type,
                        'schema': {'type': param_type},
                        'default': param_default
                    }
                    parameters.append(param)
        
        return parameters
    
    def _extract_request_body(self, section: str) -> Optional[Dict[str, Any]]:
        """提取请求体"""
        # 查找请求体示例（JSON 代码块）
        json_pattern = r'```(?:json|javascript)\s*\n(.*?)\n```'
        match = re.search(json_pattern, section, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                import json
                body_content = json.loads(match.group(1))
                return {
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'example': body_content
                            }
                        }
                    }
                }
            except:
                pass
        return None
    
    def _extract_responses(self, section: str) -> Dict[str, Any]:
        """提取响应信息"""
        responses = {}
        
        # 匹配响应状态码表格
        response_table_pattern = r'\*\*响应状态\*\*[：:]?\s*\n\|[^\n]+\n\|[^\n]+\n((?:\|[^\n]+\n?)+)'
        match = re.search(response_table_pattern, section, re.IGNORECASE | re.DOTALL)
        
        if match:
            rows = match.group(1).strip().split('\n')
            for row in rows:
                if not row.strip() or not row.startswith('|'):
                    continue
                cols = [col.strip() for col in row.split('|')[1:-1]]
                if len(cols) >= 1:
                    status_code = cols[0]
                    responses[status_code] = {
                        'description': cols[1] if len(cols) > 1 else '',
                        'content': {}
                    }
        
        # 如果没有找到表格，尝试查找响应示例
        if not responses:
            json_pattern = r'```(?:json|javascript)\s*\n(.*?)\n```'
            matches = re.finditer(json_pattern, section, re.DOTALL | re.IGNORECASE)
            for i, match in enumerate(matches):
                if i == 0:  # 第一个 JSON 代码块通常是请求体，跳过
                    continue
                responses['200'] = {
                    'description': 'Success',
                    'content': {
                        'application/json': {
                            'example': match.group(1)
                        }
                    }
                }
                break
        
        # 默认响应
        if not responses:
            responses['200'] = {
                'description': 'Success'
            }
        
        return responses
    
    def get_base_url(self) -> str:
        """获取基础 URL（从文档中提取）"""
        # 查找 base_url 或 baseUrl
        base_url_pattern = r'(?:base[_\s]?url|baseUrl|服务器地址)[：:]\s*`?([^`\n]+)`?'
        match = re.search(base_url_pattern, self.content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return 'http://localhost:8080'


if __name__ == "__main__":
    # 测试代码
    parser = MarkdownAPIParser()
    # 示例：解析 Markdown API 文档
    # endpoints = parser.parse("api_doc.md")
    # print(f"找到 {len(endpoints)} 个端点")
