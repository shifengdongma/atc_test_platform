#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAPI/Swagger 文档解析器
解析 OpenAPI 3.0 和 Swagger 2.0 格式的 API 文档
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any


class OpenAPIParser:
    """解析 OpenAPI/Swagger 文档"""
    
    def __init__(self):
        self.spec = None
        self.version = None
    
    def parse(self, file_path: str) -> Dict[str, Any]:
        """
        解析 OpenAPI/Swagger 文档
        
        Args:
            file_path: OpenAPI 文档路径（YAML 或 JSON）
        
        Returns:
            解析后的 API 规范字典
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix in ['.yaml', '.yml']:
                self.spec = yaml.safe_load(f)
            else:
                self.spec = json.load(f)
        
        # 检测版本
        if 'openapi' in self.spec:
            self.version = 'openapi3'
        elif 'swagger' in self.spec:
            self.version = 'swagger2'
        else:
            raise ValueError("无法识别 OpenAPI/Swagger 版本")
        
        return self.spec
    
    def parse_from_string(self, content: str, format: str = 'yaml') -> Dict[str, Any]:
        """
        从字符串解析 OpenAPI/Swagger 文档
        
        Args:
            content: 文档内容
            format: 格式 ('yaml' 或 'json')
        
        Returns:
            解析后的 API 规范字典
        """
        if format.lower() == 'yaml':
            self.spec = yaml.safe_load(content)
        else:
            self.spec = json.loads(content)
        
        # 检测版本
        if 'openapi' in self.spec:
            self.version = 'openapi3'
        elif 'swagger' in self.spec:
            self.version = 'swagger2'
        else:
            raise ValueError("无法识别 OpenAPI/Swagger 版本")
        
        return self.spec
    
    def get_endpoints(self) -> List[Dict[str, Any]]:
        """
        提取所有 API 端点信息
        
        Returns:
            端点列表，每个端点包含：path, method, parameters, requestBody, responses
        """
        if not self.spec:
            raise ValueError("请先解析 OpenAPI 文档")
        
        endpoints = []
        
        if self.version == 'openapi3':
            paths = self.spec.get('paths', {})
            for path, path_item in paths.items():
                for method, operation in path_item.items():
                    if method in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
                        endpoint = {
                            'path': path,
                            'method': method.upper(),
                            'operationId': operation.get('operationId', ''),
                            'summary': operation.get('summary', ''),
                            'description': operation.get('description', ''),
                            'parameters': operation.get('parameters', []),
                            'requestBody': operation.get('requestBody'),
                            'responses': operation.get('responses', {}),
                            'tags': operation.get('tags', [])
                        }
                        endpoints.append(endpoint)
        
        elif self.version == 'swagger2':
            paths = self.spec.get('paths', {})
            for path, path_item in paths.items():
                for method, operation in path_item.items():
                    if method in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
                        endpoint = {
                            'path': path,
                            'method': method.upper(),
                            'operationId': operation.get('operationId', ''),
                            'summary': operation.get('summary', ''),
                            'description': operation.get('description', ''),
                            'parameters': operation.get('parameters', []),
                            'responses': operation.get('responses', {}),
                            'tags': operation.get('tags', [])
                        }
                        endpoints.append(endpoint)
        
        return endpoints
    
    def get_parameter_details(self, parameter: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取参数详细信息
        
        Args:
            parameter: 参数定义
        
        Returns:
            参数详细信息
        """
        details = {
            'name': parameter.get('name', ''),
            'in': parameter.get('in', 'query'),  # query, path, header, cookie
            'required': parameter.get('required', False),
            'description': parameter.get('description', ''),
            'schema': parameter.get('schema', {}) if self.version == 'openapi3' else parameter,
            'type': None,
            'format': None,
            'enum': None,
            'minLength': None,
            'maxLength': None,
            'minimum': None,
            'maximum': None,
            'default': None
        }
        
        # OpenAPI 3.0
        if self.version == 'openapi3':
            schema = details['schema']
            details['type'] = schema.get('type')
            details['format'] = schema.get('format')
            details['enum'] = schema.get('enum')
            details['minLength'] = schema.get('minLength')
            details['maxLength'] = schema.get('maxLength')
            details['minimum'] = schema.get('minimum')
            details['maximum'] = schema.get('maximum')
            details['default'] = schema.get('default')
        
        # Swagger 2.0
        elif self.version == 'swagger2':
            details['type'] = parameter.get('type')
            details['format'] = parameter.get('format')
            details['enum'] = parameter.get('enum')
            details['minLength'] = parameter.get('minLength')
            details['maxLength'] = parameter.get('maxLength')
            details['minimum'] = parameter.get('minimum')
            details['maximum'] = parameter.get('maximum')
            details['default'] = parameter.get('default')
        
        return details
    
    def get_base_url(self) -> str:
        """获取基础 URL"""
        if not self.spec:
            return ''
        
        if self.version == 'openapi3':
            servers = self.spec.get('servers', [])
            if servers:
                return servers[0].get('url', '')
        
        elif self.version == 'swagger2':
            schemes = self.spec.get('schemes', ['http'])
            host = self.spec.get('host', '')
            base_path = self.spec.get('basePath', '')
            return f"{schemes[0]}://{host}{base_path}"
        
        return ''


if __name__ == "__main__":
    # 测试代码
    parser = OpenAPIParser()
    # 示例：解析 OpenAPI 文档
    # spec = parser.parse("openapi.yaml")
    # endpoints = parser.get_endpoints()
    # print(f"找到 {len(endpoints)} 个端点")
