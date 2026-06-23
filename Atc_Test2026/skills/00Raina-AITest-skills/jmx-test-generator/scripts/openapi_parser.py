#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenAPI/Swagger 文档解析器
复用 api-test-case-generator 的解析器
"""

import sys
from pathlib import Path

# 尝试从 api-test-case-generator 导入
api_test_case_path = Path(__file__).parent.parent.parent / "api-test-case-generator" / "scripts"
sys.path.insert(0, str(api_test_case_path))

try:
    from openapi_parser import OpenAPIParser
except ImportError:
    # 如果无法导入，则使用本地实现
    import json
    import yaml
    from typing import Dict, List, Optional, Any
    
    class OpenAPIParser:
        """解析 OpenAPI/Swagger 文档"""
        
        def __init__(self):
            self.spec = None
            self.version = None
        
        def parse(self, file_path: str) -> Dict[str, Any]:
            """解析 OpenAPI/Swagger 文档"""
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
            """从字符串解析 OpenAPI/Swagger 文档"""
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
            """提取所有 API 端点信息"""
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
            """提取参数详细信息"""
            details = {
                'name': parameter.get('name', ''),
                'in': parameter.get('in', 'query'),
                'required': parameter.get('required', False),
                'description': parameter.get('description', ''),
                'schema': parameter.get('schema', {}) if self.version == 'openapi3' else parameter,
                'type': None,
                'format': None,
                'enum': None,
                'default': None
            }
            
            if self.version == 'openapi3':
                schema = details['schema']
                details['type'] = schema.get('type')
                details['format'] = schema.get('format')
                details['enum'] = schema.get('enum')
                details['default'] = schema.get('default')
            elif self.version == 'swagger2':
                details['type'] = parameter.get('type')
                details['format'] = parameter.get('format')
                details['enum'] = parameter.get('enum')
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
