#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMX 测试脚本生成器
根据 API 文档生成 Apache JMeter 测试脚本
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import re

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))
from openapi_parser import OpenAPIParser
from markdown_parser import MarkdownAPIParser
from jmx_builder import JMXBuilder


class JMXTestGenerator:
    """JMX 测试脚本生成器"""
    
    def __init__(self):
        self.builder = JMXBuilder()
        self.base_url = ""
        self.endpoints = []
    
    def generate_from_openapi(self, openapi_file: str, 
                             test_plan_name: str = "API Test Plan",
                             num_threads: int = 1,
                             ramp_time: int = 1,
                             loops: int = 1,
                             add_listeners: bool = True) -> str:
        """
        从 OpenAPI 文档生成 JMX 测试脚本
        
        Args:
            openapi_file: OpenAPI 文档路径
            test_plan_name: 测试计划名称
            num_threads: 线程数
            ramp_time: 启动时间（秒）
            loops: 循环次数
            add_listeners: 是否添加监听器
        
        Returns:
            JMX XML 字符串
        """
        # 解析 OpenAPI 文档
        parser = OpenAPIParser()
        parser.parse(openapi_file)
        self.endpoints = parser.get_endpoints()
        self.base_url = parser.get_base_url()
        
        # 解析 base_url
        url_parts = self._parse_url(self.base_url)
        
        # 创建测试计划
        self.builder.create_test_plan(test_plan_name, {
            'base_url': self.base_url
        })
        
        # 为每个端点创建线程组和请求
        for endpoint in self.endpoints:
            thread_group_name = f"{endpoint['method']} {endpoint['path']}"
            thread_group, thread_group_hash_tree = self.builder.add_thread_group(
                thread_group_name, num_threads, ramp_time, loops
            )
            
            # 添加 HTTP 请求
            path = endpoint['path']
            method = endpoint['method']
            
            # 提取路径参数
            path_params = [p for p in endpoint.get('parameters', []) if p.get('in') == 'path']
            query_params = [p for p in endpoint.get('parameters', []) if p.get('in') == 'query']
            
            # 替换路径参数
            for param in path_params:
                param_name = param.get('name', '')
                path = path.replace(f"{{{param_name}}}", str(param.get('default', param_name)))
            
            # 准备请求体
            request_body = None
            if endpoint.get('requestBody'):
                request_body = self._extract_request_body(endpoint['requestBody'])
            
            # 只有 POST/PUT/PATCH 等有请求体的方法才需要 Content-Type 头
            headers = None
            if request_body and method.upper() in ['POST', 'PUT', 'PATCH']:
                headers = {'Content-Type': 'application/json'}
            
            # 添加 HTTP 请求（返回 http_sampler 和它的 hashTree）
            http_sampler, http_sampler_hash_tree = self.builder.add_http_request(
                thread_group_hash_tree,
                name=f"{method} {path}",
                domain=url_parts.get('domain', 'localhost'),
                path=path,
                method=method,
                port=url_parts.get('port', 80),
                protocol=url_parts.get('protocol', 'http'),
                parameters=query_params,
                headers=headers,
                body=request_body
            )
            
            # 添加断言（放在 http_sampler 的 hashTree 中）
            self._add_assertions(http_sampler_hash_tree, endpoint)
            
            # 添加监听器（放在 thread_group 的 hashTree 中，与 HTTP 请求同级）
            # 注意：由于 JMeter 5.6.3 中监听器的反序列化问题，暂时不自动添加监听器
            # 用户可以在 JMeter GUI 中手动添加所需的监听器（如 View Results Tree、Summary Report 等）
            # if add_listeners:
            #     self.builder.add_listener(thread_group_hash_tree, "SummaryReport")
        
        return self.builder.to_xml_string()
    
    def generate_from_markdown(self, markdown_file: str,
                              test_plan_name: str = "API Test Plan",
                              num_threads: int = 1,
                              ramp_time: int = 1,
                              loops: int = 1,
                              add_listeners: bool = True) -> str:
        """
        从 Markdown API 文档生成 JMX 测试脚本
        
        Args:
            markdown_file: Markdown 文件路径
            test_plan_name: 测试计划名称
            num_threads: 线程数
            ramp_time: 启动时间（秒）
            loops: 循环次数
            add_listeners: 是否添加监听器
        
        Returns:
            JMX XML 字符串
        """
        # 解析 Markdown 文档
        parser = MarkdownAPIParser()
        self.endpoints = parser.parse(markdown_file)
        self.base_url = parser.get_base_url()
        
        # 解析 base_url
        url_parts = self._parse_url(self.base_url)
        
        # 创建新的 builder 实例（每次生成都创建新的）
        self.builder = JMXBuilder()
        
        # 创建测试计划
        self.builder.create_test_plan(test_plan_name, {
            'base_url': self.base_url
        })
        
        # 为每个端点创建线程组和请求
        for endpoint in self.endpoints:
            thread_group_name = f"{endpoint['method']} {endpoint['path']}"
            thread_group, thread_group_hash_tree = self.builder.add_thread_group(
                thread_group_name, num_threads, ramp_time, loops
            )
            
            # 添加 HTTP 请求
            path = endpoint['path']
            method = endpoint['method']
            
            # 提取参数（区分 path、query、header 参数）
            path_params = [p for p in endpoint.get('parameters', []) if p.get('in') == 'path']
            query_params = [p for p in endpoint.get('parameters', []) if p.get('in') == 'query']
            header_params = [p for p in endpoint.get('parameters', []) if p.get('in') == 'header']
            
            # 替换路径参数
            for param in path_params:
                param_name = param.get('name', '')
                path = path.replace(f"{{{param_name}}}", str(param.get('default', param_name)))
            
            # 准备请求体
            request_body = None
            if endpoint.get('requestBody'):
                request_body = self._extract_request_body(endpoint['requestBody'])
            
            # 构建请求头
            headers = {}
            # 添加 Header 参数
            for param in header_params:
                param_name = param.get('name', '')
                param_value = param.get('default', '')
                if param_name and param_value:
                    headers[param_name] = param_value
            # 如果是 POST/PUT/PATCH 且有请求体，添加 Content-Type
            if request_body and method.upper() in ['POST', 'PUT', 'PATCH']:
                if 'Content-Type' not in headers:
                    headers['Content-Type'] = 'application/json'
            
            # 如果没有 headers，设置为 None
            if not headers:
                headers = None
            
            # 添加 HTTP 请求（返回 http_sampler 和它的 hashTree）
            http_sampler, http_sampler_hash_tree = self.builder.add_http_request(
                thread_group_hash_tree,
                name=f"{method} {path}",
                domain=url_parts.get('domain', 'localhost'),
                path=path,
                method=method,
                port=url_parts.get('port', 80),
                protocol=url_parts.get('protocol', 'http'),
                parameters=query_params,
                headers=headers,
                body=request_body
            )
            
            # 添加断言（放在 http_sampler 的 hashTree 中）
            self._add_assertions(http_sampler_hash_tree, endpoint)
            
            # 添加监听器（放在 thread_group 的 hashTree 中，与 HTTP 请求同级）
            # 注意：由于 JMeter 5.6.3 中监听器的反序列化问题，暂时不自动添加监听器
            # 用户可以在 JMeter GUI 中手动添加所需的监听器（如 View Results Tree、Summary Report 等）
            # if add_listeners:
            #     self.builder.add_listener(thread_group_hash_tree, "SummaryReport")
        
        return self.builder.to_xml_string()
    
    def _parse_url(self, url: str) -> Dict[str, Any]:
        """解析 URL"""
        if not url:
            return {'protocol': 'http', 'domain': 'localhost', 'port': 80}
        
        # 移除末尾的斜杠
        url = url.rstrip('/')
        
        # 解析协议
        protocol = 'http'
        if url.startswith('https://'):
            protocol = 'https'
            url = url[8:]
        elif url.startswith('http://'):
            protocol = 'http'
            url = url[7:]
        
        # 解析域名和端口
        parts = url.split('/')
        domain_part = parts[0]
        
        if ':' in domain_part:
            domain, port = domain_part.split(':')
            port = int(port)
        else:
            domain = domain_part
            port = 443 if protocol == 'https' else 80
        
        return {
            'protocol': protocol,
            'domain': domain,
            'port': port
        }
    
    def _extract_request_body(self, request_body: Dict[str, Any]) -> Optional[str]:
        """提取请求体"""
        if not request_body:
            return None
        
        # OpenAPI 3.0 格式
        if 'content' in request_body:
            content = request_body['content']
            if 'application/json' in content:
                json_content = content['application/json']
                schema = json_content.get('schema', {})
                # 优先使用 example（可能在 schema 中，也可能在 content 中）
                example = json_content.get('example') or schema.get('example')
                if example:
                    return json.dumps(example, ensure_ascii=False)
                # 如果没有 example，尝试从 schema 生成
                return json.dumps(self._generate_example_from_schema(schema), ensure_ascii=False)
        
        return None
    
    def _generate_example_from_schema(self, schema: Dict[str, Any]) -> Any:
        """从 schema 生成示例数据"""
        schema_type = schema.get('type', 'object')
        
        if schema_type == 'object':
            example = {}
            properties = schema.get('properties', {})
            for prop_name, prop_schema in properties.items():
                example[prop_name] = self._generate_example_from_schema(prop_schema)
            return example
        elif schema_type == 'array':
            items = schema.get('items', {})
            return [self._generate_example_from_schema(items)]
        elif schema_type == 'string':
            return schema.get('example', 'string')
        elif schema_type == 'integer':
            return schema.get('example', 0)
        elif schema_type == 'number':
            return schema.get('example', 0.0)
        elif schema_type == 'boolean':
            return schema.get('example', True)
        else:
            return None
    
    def _add_assertions(self, parent_hash_tree, endpoint: Dict[str, Any]):
        """添加断言"""
        # 添加响应状态码断言（期望 200）
        self.builder.add_response_assertion(
            parent_hash_tree,
            name="Response Code Assertion",
            field_to_test="Assertion.response_code",
            test_type="2",  # 等于
            pattern="200"
        )
        
        # 如果有响应定义，添加 JSON 路径断言
        responses = endpoint.get('responses', {})
        if '200' in responses:
            response_200 = responses['200']
            if 'content' in response_200:
                content = response_200['content']
                if 'application/json' in content:
                    # 可以添加 JSON 路径断言
                    # 这里简化处理，实际可以根据响应 schema 添加更多断言
                    pass
    
    def save_jmx(self, file_path: str, pretty: bool = True):
        """
        保存 JMX 文件
        
        Args:
            file_path: 文件路径
            pretty: 是否格式化输出
        """
        self.builder.save(file_path, pretty)
        print(f"JMX 文件已保存: {file_path}")


if __name__ == "__main__":
    # 测试代码
    generator = JMXTestGenerator()
    # 示例：从 OpenAPI 文档生成
    # xml = generator.generate_from_openapi("openapi.yaml")
    # generator.save_jmx("test_plan.jmx")
    
    # 示例：从 Markdown 文档生成
    # xml = generator.generate_from_markdown("api_doc.md")
    # generator.save_jmx("test_plan.jmx")
