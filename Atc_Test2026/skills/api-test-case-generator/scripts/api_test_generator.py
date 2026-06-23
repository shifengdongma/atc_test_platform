#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 测试用例生成器
根据 OpenAPI 文档或 API 描述生成 Postman 测试集合
"""

import json
import sys
from typing import Dict, List, Optional, Any
from pathlib import Path

# 添加当前目录到路径，以便导入 openapi_parser
sys.path.insert(0, str(Path(__file__).parent))
from openapi_parser import OpenAPIParser


class APITestCaseGenerator:
    """API 测试用例生成器"""
    
    def __init__(self):
        self.test_cases = []
        self.base_url = ''
    
    def generate_from_openapi(self, openapi_file: str) -> Dict[str, Any]:
        """
        从 OpenAPI 文档生成测试用例
        
        Args:
            openapi_file: OpenAPI 文档路径
        
        Returns:
            Postman Collection 字典
        """
        parser = OpenAPIParser()
        spec = parser.parse(openapi_file)
        self.base_url = parser.get_base_url()
        
        endpoints = parser.get_endpoints()
        collection_items = []
        
        for endpoint in endpoints:
            # 为每个端点生成测试用例
            endpoint_tests = self._generate_endpoint_test_cases(endpoint, parser)
            if endpoint_tests:
                collection_items.append(endpoint_tests)
        
        return self._create_postman_collection(collection_items)
    
    def generate_from_description(self, api_description: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 API 描述生成测试用例
        
        Args:
            api_description: API 描述字典，包含：
                - base_url: 基础 URL
                - endpoints: 端点列表，每个端点包含：
                    - path: 路径
                    - method: HTTP 方法
                    - parameters: 参数列表
                    - description: 描述
        
        Returns:
            Postman Collection 字典
        """
        self.base_url = api_description.get('base_url', '')
        endpoints = api_description.get('endpoints', [])
        collection_items = []
        
        for endpoint in endpoints:
            endpoint_tests = self._generate_endpoint_test_cases_from_description(endpoint)
            if endpoint_tests:
                collection_items.append(endpoint_tests)
        
        return self._create_postman_collection(collection_items)
    
    def _generate_endpoint_test_cases(self, endpoint: Dict[str, Any], parser: OpenAPIParser) -> Dict[str, Any]:
        """为端点生成测试用例"""
        path = endpoint['path']
        method = endpoint['method']
        parameters = endpoint.get('parameters', [])
        request_body = endpoint.get('requestBody')
        
        # 解析参数
        param_details = []
        for param in parameters:
            param_details.append(parser.get_parameter_details(param))
        
        # 生成测试用例
        test_cases = []
        
        # 正向用例
        test_cases.extend(self._generate_positive_cases(path, method, param_details, request_body))
        
        # 负向用例
        test_cases.extend(self._generate_negative_cases(path, method, param_details, request_body))
        
        # 边界值用例
        test_cases.extend(self._generate_boundary_cases(path, method, param_details, request_body))
        
        # 异常用例
        test_cases.extend(self._generate_exception_cases(path, method, param_details, request_body))
        
        if not test_cases:
            return None
        
        # 构建端点文件夹结构
        return {
            "name": f"{method} {path}",
            "item": test_cases,
            "request": {
                "method": method,
                "header": [],
                "url": {
                    "raw": f"{{{{base_url}}}}{path}",
                    "host": ["{{base_url}}"],
                    "path": path.split('/')[1:] if path.startswith('/') else path.split('/')
                }
            }
        }
    
    def _generate_endpoint_test_cases_from_description(self, endpoint: Dict[str, Any]) -> Dict[str, Any]:
        """从描述生成端点测试用例"""
        path = endpoint['path']
        method = endpoint['method']
        parameters = endpoint.get('parameters', [])
        
        test_cases = []
        test_cases.extend(self._generate_positive_cases(path, method, parameters, None))
        test_cases.extend(self._generate_negative_cases(path, method, parameters, None))
        test_cases.extend(self._generate_boundary_cases(path, method, parameters, None))
        test_cases.extend(self._generate_exception_cases(path, method, parameters, None))
        
        if not test_cases:
            return None
        
        return {
            "name": f"{method} {path}",
            "item": test_cases,
            "request": {
                "method": method,
                "header": [],
                "url": {
                    "raw": f"{{{{base_url}}}}{path}",
                    "host": ["{{base_url}}"],
                    "path": path.split('/')[1:] if path.startswith('/') else path.split('/')
                }
            }
        }
    
    def _generate_positive_cases(self, path: str, method: str, 
                                 parameters: List[Dict], request_body: Optional[Dict]) -> List[Dict]:
        """生成正向用例"""
        cases = []
        
        # 正常请求 - 所有必需参数 + 部分可选参数
        required_params = [p for p in parameters if p.get('required', False)]
        optional_params = [p for p in parameters if not p.get('required', False)]
        
        if required_params or optional_params or request_body:
            case = self._create_test_case(
                f"正向用例 - 正常请求（所有必需参数）",
                path, method, required_params, request_body, True
            )
            cases.append(case)
        
        return cases
    
    def _generate_negative_cases(self, path: str, method: str,
                                parameters: List[Dict], request_body: Optional[Dict]) -> List[Dict]:
        """生成负向用例"""
        cases = []
        required_params = [p for p in parameters if p.get('required', False)]
        
        # 缺失必需参数
        for param in required_params:
            case = self._create_test_case(
                f"负向用例 - 缺失必需参数: {param.get('name', '')}",
                path, method, [p for p in required_params if p != param], request_body, False
            )
            cases.append(case)
        
        # 参数类型错误
        for param in parameters:
            if param.get('type') in ['integer', 'number']:
                case = self._create_test_case(
                    f"负向用例 - 参数类型错误: {param.get('name', '')} (应为数字)",
                    path, method, parameters, request_body, False,
                    override_params={param.get('name', ''): 'invalid_number'}
                )
                cases.append(case)
        
        return cases
    
    def _generate_boundary_cases(self, path: str, method: str,
                                 parameters: List[Dict], request_body: Optional[Dict]) -> List[Dict]:
        """生成边界值用例"""
        cases = []
        
        for param in parameters:
            param_name = param.get('name', '')
            param_type = param.get('type')
            
            # 字符串长度边界
            if param_type == 'string':
                min_length = param.get('minLength')
                max_length = param.get('maxLength')
                
                if min_length is not None:
                    case = self._create_test_case(
                        f"边界值用例 - {param_name} 最小长度 ({min_length})",
                        path, method, parameters, request_body, True,
                        override_params={param_name: 'a' * min_length}
                    )
                    cases.append(case)
                
                if max_length is not None:
                    case = self._create_test_case(
                        f"边界值用例 - {param_name} 最大长度 ({max_length})",
                        path, method, parameters, request_body, True,
                        override_params={param_name: 'a' * max_length}
                    )
                    cases.append(case)
            
            # 数值边界
            elif param_type in ['integer', 'number']:
                minimum = param.get('minimum')
                maximum = param.get('maximum')
                
                if minimum is not None:
                    case = self._create_test_case(
                        f"边界值用例 - {param_name} 最小值 ({minimum})",
                        path, method, parameters, request_body, True,
                        override_params={param_name: minimum}
                    )
                    cases.append(case)
                
                if maximum is not None:
                    case = self._create_test_case(
                        f"边界值用例 - {param_name} 最大值 ({maximum})",
                        path, method, parameters, request_body, True,
                        override_params={param_name: maximum}
                    )
                    cases.append(case)
        
        return cases
    
    def _generate_exception_cases(self, path: str, method: str,
                                 parameters: List[Dict], request_body: Optional[Dict]) -> List[Dict]:
        """生成异常用例"""
        cases = []
        
        for param in parameters:
            param_name = param.get('name', '')
            
            # 空值
            case = self._create_test_case(
                f"异常用例 - {param_name} 为空值",
                path, method, parameters, request_body, False,
                override_params={param_name: ''}
            )
            cases.append(case)
            
            # SQL 注入尝试
            if param.get('type') == 'string':
                case = self._create_test_case(
                    f"异常用例 - {param_name} SQL 注入尝试",
                    path, method, parameters, request_body, False,
                    override_params={param_name: "1' OR '1'='1"}
                )
                cases.append(case)
                
                # XSS 尝试
                case = self._create_test_case(
                    f"异常用例 - {param_name} XSS 尝试",
                    path, method, parameters, request_body, False,
                    override_params={param_name: "<script>alert('XSS')</script>"}
                )
                cases.append(case)
        
        return cases
    
    def _create_test_case(self, name: str, path: str, method: str,
                         parameters: List[Dict], request_body: Optional[Dict],
                         expect_success: bool, override_params: Optional[Dict] = None) -> Dict[str, Any]:
        """创建单个测试用例"""
        override_params = override_params or {}
        
        # 构建 URL
        url_parts = path.split('/')
        query_params = []
        path_vars = []
        
        for param in parameters:
            param_name = param.get('name', '')
            param_in = param.get('in', 'query')
            param_value = override_params.get(param_name, self._get_default_value(param))
            
            if param_in == 'path':
                path_vars.append(param_value)
            elif param_in == 'query':
                query_params.append({
                    "key": param_name,
                    "value": str(param_value),
                    "description": param.get('description', '')
                })
        
        # 构建请求体
        body = None
        if request_body and method in ['POST', 'PUT', 'PATCH']:
            body = {
                "mode": "raw",
                "raw": "{}",
                "options": {
                    "raw": {
                        "language": "json"
                    }
                }
            }
        
        # 构建测试脚本
        test_script = self._generate_test_script(expect_success)
        
        return {
            "name": name,
            "request": {
                "method": method,
                "header": [],
                "url": {
                    "raw": f"{{{{base_url}}}}{path}",
                    "host": ["{{base_url}}"],
                    "path": [p for p in url_parts if p and not p.startswith('{')],
                    "query": query_params
                },
                "body": body
            },
            "event": [
                {
                    "listen": "test",
                    "script": {
                        "exec": test_script,
                        "type": "text/javascript"
                    }
                }
            ]
        }
    
    def _get_default_value(self, param: Dict[str, Any]) -> Any:
        """获取参数的默认值"""
        if param.get('default') is not None:
            return param['default']
        
        param_type = param.get('type')
        if param_type == 'string':
            return 'test_value'
        elif param_type == 'integer':
            return 1
        elif param_type == 'number':
            return 1.0
        elif param_type == 'boolean':
            return True
        elif param_type == 'array':
            return []
        else:
            return ''
    
    def _generate_test_script(self, expect_success: bool) -> List[str]:
        """生成测试脚本"""
        if expect_success:
            return [
                "pm.test('状态码为 200', function () {",
                "    pm.response.to.have.status(200);",
                "});",
                "",
                "pm.test('响应时间小于 2000ms', function () {",
                "    pm.expect(pm.response.responseTime).to.be.below(2000);",
                "});",
                "",
                "pm.test('响应包含 JSON', function () {",
                "    pm.response.to.be.json;",
                "});"
            ]
        else:
            return [
                "pm.test('状态码为 4xx 或 5xx', function () {",
                "    pm.expect(pm.response.code).to.be.oneOf([400, 401, 403, 404, 422, 500]);",
                "});"
            ]
    
    def _create_postman_collection(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建 Postman Collection"""
        return {
            "info": {
                "name": "API Test Cases",
                "description": "自动生成的 API 测试用例集合",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": items,
            "variable": [
                {
                    "key": "base_url",
                    "value": self.base_url or "http://localhost:8080",
                    "type": "string"
                }
            ]
        }
    
    def save_collection(self, collection: Dict[str, Any], output_path: str):
        """保存 Postman Collection 到文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(collection, f, ensure_ascii=False, indent=2)
        print(f"Postman Collection 已保存到: {output_path}")


if __name__ == "__main__":
    # 测试代码
    generator = APITestCaseGenerator()
    
    # 示例：从描述生成
    api_desc = {
        "base_url": "https://api.example.com",
        "endpoints": [
            {
                "path": "/users",
                "method": "GET",
                "parameters": [
                    {
                        "name": "page",
                        "in": "query",
                        "type": "integer",
                        "required": False,
                        "minimum": 1,
                        "default": 1
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "type": "integer",
                        "required": False,
                        "minimum": 1,
                        "maximum": 100,
                        "default": 10
                    }
                ]
            }
        ]
    }
    
    collection = generator.generate_from_description(api_desc)
    generator.save_collection(collection, "test_collection.json")
