#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KTP (MeterSphere) 自动化测试用例生成器
从Swagger API文档生成KTP平台格式的JSON测试用例

作者: AI Assistant
日期: 2025-04-22
版本: 1.0.0
"""

import json
import uuid
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class KTPTestDataGenerator:
    """KTP测试数据生成器"""
    
    @staticmethod
    def generate_uuid() -> str:
        """生成UUID"""
        return str(uuid.uuid4())
    
    @staticmethod
    def generate_timestamp() -> int:
        """生成毫秒级时间戳"""
        return int(datetime.now().timestamp() * 1000)
    
    @staticmethod
    def generate_landing_site_name(site_type: str = "起降场") -> str:
        """生成起降场名称"""
        return f"AUTO{site_type}${{__time(MMddHHmmss)}}${{__RandomString(1,ABCDEFGHJKLMN,)}}${{__RandomString(1,0123456789,)}}"
    
    @staticmethod
    def generate_landing_site_code() -> str:
        """生成起降场编号"""
        return "${__time(MMddHH)}${__RandomString(2,ABCDEFGHJKLMNPQRSTUVWXYZ,)}"
    
    @staticmethod
    def generate_coordinates() -> str:
        """生成坐标"""
        return "${__RandomString(3,0123456789,)}"
    
    @staticmethod
    def generate_uav_code() -> str:
        """生成无人机编码"""
        return "${__time(MMddHHmmss)}${__RandomString(4,ABCDEFGHJKLMNPQRSTUVWXYZ0123456789,)}"


class KTPSwaggerParser:
    """Swagger解析器"""
    
    def __init__(self, swagger_file: str):
        self.swagger_file = swagger_file
        self.swagger_data = None
        self.apis = []
        
    def parse(self) -> List[Dict]:
        """解析Swagger文件"""
        with open(self.swagger_file, 'r', encoding='utf-8') as f:
            self.swagger_data = json.load(f)
        
        base_path = self.swagger_data.get('basePath', '/')
        paths = self.swagger_data.get('paths', {})
        
        for path, methods in paths.items():
            for method, details in methods.items():
                if method in ['get', 'post', 'put', 'delete', 'patch']:
                    api_info = {
                        'path': base_path.rstrip('/') + path,
                        'method': method.upper(),
                        'summary': details.get('summary', ''),
                        'description': details.get('description', ''),
                        'tags': details.get('tags', []),
                        'parameters': details.get('parameters', []),
                        'consumes': details.get('consumes', ['application/json']),
                        'produces': details.get('produces', ['application/json']),
                        'responses': details.get('responses', {})
                    }
                    self.apis.append(api_info)
        
        return self.apis
    
    def get_apis_by_tag(self, tag: str) -> List[Dict]:
        """根据标签获取API列表"""
        return [api for api in self.apis if tag in api.get('tags', [])]
    
    def get_all_tags(self) -> List[str]:
        """获取所有标签"""
        tags = set()
        for api in self.apis:
            tags.update(api.get('tags', []))
        return list(tags)


class KTPScenarioGenerator:
    """KTP场景生成器"""
    
    # KTP项目配置
    PROJECT_ID = "a9883328-312b-4951-a037-6eb3c4278859"
    ENVIRONMENT_ID = "93b5122f-20be-4b7e-81ef-52d8a3fb248f"
    VERSION_ID = "bf4726cb01114d11bcdf0da722597329"
    VERSION_NAME = "v1.4.0"
    DEFAULT_USER = "zhangruipo@kedacom.com"
    
    # 场景映射配置
    SCENARIO_MAPPINGS = {
        "起降场": {
            "name": "空域情报_起降场",
            "tags": ["起降场"],
            "module_path": "/未规划场景"
        },
        "扇区管理": {
            "name": "空域情报_扇区管理",
            "tags": ["扇区管理"],
            "module_path": "/未规划场景"
        },
        "航路航线": {
            "name": "空域情报_航路航线管理",
            "tags": ["航路管理"],
            "module_path": "/未规划场景"
        },
        "空域管理": {
            "name": "空域情报_空域管理",
            "tags": ["空域管理"],
            "module_path": "/未规划场景"
        },
        "飞行计划": {
            "name": "飞行服务_飞行计划管理",
            "tags": ["飞行计划"],
            "module_path": "/未规划场景"
        },
        "飞行任务": {
            "name": "飞行服务_飞行任务管理",
            "tags": ["飞行任务"],
            "module_path": "/未规划场景"
        },
        "无人机": {
            "name": "航空器管理_无人机管理",
            "tags": ["无人机管理"],
            "module_path": "/未规划场景"
        },
        "告警管理": {
            "name": "告警管理_告警处理",
            "tags": ["告警管理"],
            "module_path": "/未规划场景"
        },
        "坐席管理": {
            "name": "系统管理_坐席管理",
            "tags": ["坐席管理"],
            "module_path": "/未规划场景"
        },
        "用户权限": {
            "name": "系统管理_用户权限管理",
            "tags": ["用户管理", "统一权限", "操作员管理"],
            "module_path": "/未规划场景"
        },
        "态势大屏": {
            "name": "态势感知_大屏查询",
            "tags": ["态势大屏"],
            "module_path": "/未规划场景"
        },
        "运营人": {
            "name": "运营管理_运营人管理",
            "tags": ["运营人管理"],
            "module_path": "/未规划场景"
        },
        "操作日志": {
            "name": "系统管理_操作日志查询",
            "tags": ["操作日志"],
            "module_path": "/未规划场景"
        },
        "接收机": {
            "name": "设备管理_接收机管理",
            "tags": ["接收机管理"],
            "module_path": "/未规划场景"
        },
        "算法接口": {
            "name": "算法服务_接口管理",
            "tags": ["算法接口管理"],
            "module_path": "/未规划场景"
        }
    }
    
    def __init__(self):
        self.data_gen = KTPTestDataGenerator()
        self.scenario_counter = 100000
        self.step_counter = 100001001
    
    def _generate_scenario_id(self) -> str:
        """生成场景ID"""
        return self.data_gen.generate_uuid()
    
    def _generate_resource_id(self) -> str:
        """生成资源ID"""
        return self.data_gen.generate_uuid()
    
    def _generate_custom_num(self) -> str:
        """生成自定义编号"""
        self.scenario_counter += 1
        return str(self.scenario_counter)
    
    def _generate_step_num(self) -> str:
        """生成步骤编号"""
        self.step_counter += 1
        return str(self.step_counter)
    
    def _create_base_scenario(self, name: str, module_path: str = "/未规划场景") -> Dict:
        """创建基础场景结构"""
        scenario_id = self._generate_scenario_id()
        api_module_id = self._generate_scenario_id()
        custom_num = self._generate_custom_num()
        timestamp = self.data_gen.generate_timestamp()
        
        return {
            "id": scenario_id,
            "projectId": self.PROJECT_ID,
            "name": name,
            "apiScenarioModuleId": api_module_id,
            "modulePath": module_path,
            "customNum": custom_num,
            "num": int(custom_num),
            "order": 5000,
            "createTime": timestamp,
            "updateTime": timestamp,
            "createUser": self.DEFAULT_USER,
            "userId": self.DEFAULT_USER,
            "principal": self.DEFAULT_USER,
            "versionId": self.VERSION_ID,
            "version": 1,
            "status": "Completed",
            "lastResult": "Success",
            "passRate": "100%",
            "executeTimes": 0,
            "stepTotal": 0,
            "tags": "",
            "useUrl": [],
            "environmentMap": {
                self.PROJECT_ID: self.ENVIRONMENT_ID
            }
        }
    
    def _create_scenario_definition(self, name: str) -> Dict:
        """创建场景定义结构"""
        return {
            "name": name,
            "type": "scenario",
            "num": self.scenario_counter,
            "enable": True,
            "active": False,
            "variableEnable": True,
            "variables": [],
            "headers": [],
            "mockEnvironment": False,
            "environmentEnable": False,
            "enableCookieShare": True,
            "loopControllerCsvDataIsolation": False,
            "referenced": "Created",
            "versionId": self.VERSION_ID,
            "versionName": self.VERSION_NAME,
            "environmentMap": {
                self.PROJECT_ID: self.ENVIRONMENT_ID
            },
            "hashTree": [],
            "clazzName": "io.metersphere.api.dto.definition.request.MsScenario",
            "onSampleError": True
        }
    
    def _create_http_sampler(self, api: Dict, name: str, index: int) -> Dict:
        """创建HTTP采样器"""
        resource_id = self._generate_resource_id()
        step_num = self._generate_step_num()
        
        # 处理路径参数
        path = api['path']
        rest_params = []
        path_params = re.findall(r'\{(\w+)\}', path)
        for param in path_params:
            rest_params.append({
                "encode": True,
                "valid": True,
                "valueEncode": False,
                "file": False,
                "enable": True,
                "name": param,
                "type": "text",
                "contentType": "text/plain",
                "urlEncode": False,
                "value": f"${{{param}}}",
                "required": True
            })
        
        # 处理查询参数
        arguments = []
        for param in api.get('parameters', []):
            if param.get('in') == 'query':
                arguments.append({
                    "encode": True,
                    "valid": True,
                    "valueEncode": False,
                    "file": False,
                    "enable": True,
                    "name": param.get('name', ''),
                    "urlEncode": False,
                    "value": self._generate_param_value(param),
                    "required": param.get('required', False)
                })
        
        # 处理请求体
        body = self._create_request_body(api)
        
        # 创建断言
        assertions = self._create_assertions()
        
        sampler = {
            "resourceId": resource_id,
            "num": step_num,
            "refType": "CASE",
            "type": "HTTPSamplerProxy",
            "name": name,
            "enable": True,
            "active": index == 1,
            "index": index,
            "label": "HTTPSamplerProxy",
            "method": api['method'],
            "path": path,
            "protocol": "HTTP",
            "domain": "https://dkkgsit-test.testdolphin.com",
            "url": "",
            "connectTimeout": "60000",
            "responseTimeout": "60000",
            "followRedirects": True,
            "useEnvironment": self.ENVIRONMENT_ID,
            "mockEnvironment": False,
            "customizeReq": False,
            "referenced": "REF",
            "versionId": self.VERSION_ID,
            "versionName": self.VERSION_NAME,
            "projectId": self.PROJECT_ID,
            "body": body,
            "headers": self._create_headers(api),
            "rest": rest_params,
            "arguments": arguments,
            "filePaths": [],
            "doBrowserCompatibleMultipart": True,
            "doMultipartPost": False,
            "hashTree": [assertions],
            "clazzName": "io.metersphere.api.dto.definition.request.sampler.MsHTTPSamplerProxy"
        }
        
        return sampler
    
    def _create_request_body(self, api: Dict) -> Dict:
        """创建请求体"""
        method = api['method']
        consumes = api.get('consumes', [])
        parameters = api.get('parameters', [])
        
        # 检查是否有body参数
        body_params = [p for p in parameters if p.get('in') == 'body']
        
        if method in ['POST', 'PUT', 'PATCH'] and body_params:
            # 生成JSON请求体
            body_data = self._generate_body_data(body_params[0])
            return {
                "valid": True,
                "xml": False,
                "binary": [],
                "json": True,
                "kvs": [],
                "raw": body_data,
                "formData": False,
                "kV": False,
                "oldKV": False,
                "type": "JSON"
            }
        else:
            return {
                "valid": False,
                "xml": False,
                "binary": [],
                "json": False,
                "kvs": [],
                "formData": False,
                "kV": False,
                "oldKV": True,
                "type": "KeyValue"
            }
    
    def _generate_body_data(self, param: Dict) -> str:
        """生成请求体数据"""
        schema = param.get('schema', {})
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        
        data = {}
        for prop_name, prop_def in properties.items():
            prop_type = prop_def.get('type', 'string')
            
            if prop_name in required:
                if prop_type == 'string':
                    if 'description' in prop_def:
                        desc = prop_def['description']
                        if '名称' in desc or 'name' in prop_name.lower():
                            data[prop_name] = f"AUTO测试${{__time(MMddHHmmss)}}"
                        elif '编号' in desc or 'code' in prop_name.lower():
                            data[prop_name] = "${__time(MMddHH)}${__RandomString(2,ABCDEFGHJKLMNPQRSTUVWXYZ,)}"
                        elif 'id' in prop_name.lower():
                            data[prop_name] = f"${{{prop_name}}}"
                        else:
                            data[prop_name] = "test_value"
                    else:
                        data[prop_name] = "test_value"
                elif prop_type == 'integer' or prop_type == 'number':
                    data[prop_name] = 1
                elif prop_type == 'boolean':
                    data[prop_name] = True
                elif prop_type == 'array':
                    data[prop_name] = []
                elif prop_type == 'object':
                    data[prop_name] = {}
        
        return json.dumps(data, ensure_ascii=False, indent=4)
    
    def _generate_param_value(self, param: Dict) -> str:
        """生成参数值"""
        param_type = param.get('type', 'string')
        param_name = param.get('name', '')
        description = param.get('description', '')
        
        if param_name in ['pageSize', 'pageNo']:
            return '10' if param_name == 'pageSize' else '0'
        elif param_name == 'keyword':
            return 'AUTO'
        elif 'status' in param_name.lower():
            return 'ENABLED'
        elif param_type == 'integer' or param_type == 'number':
            return '1'
        elif param_type == 'boolean':
            return 'true'
        else:
            return ''
    
    def _create_headers(self, api: Dict) -> List[Dict]:
        """创建请求头"""
        headers = []
        consumes = api.get('consumes', [])
        
        if 'application/json' in consumes:
            headers.append({
                "encode": True,
                "valid": True,
                "valueEncode": False,
                "file": False,
                "enable": True,
                "name": "Content-Type",
                "urlEncode": False,
                "value": "application/json",
                "required": True
            })
        
        return headers
    
    def _create_assertions(self) -> Dict:
        """创建断言"""
        return {
            "resourceId": self._generate_resource_id(),
            "mockEnvironment": False,
            "type": "Assertions",
            "enable": True,
            "active": False,
            "index": "1",
            "scenarioAss": False,
            "regex": [],
            "xpath": [],
            "xpath2": [],
            "jsr223": [],
            "binary": [],
            "jsonPath": [
                {
                    "valid": True,
                    "expect": "200",
                    "expression": "$.status",
                    "enable": True,
                    "description": "$.status expect: 200",
                    "type": "JSON",
                    "option": "REGEX"
                },
                {
                    "valid": True,
                    "expect": "0",
                    "expression": "$.code",
                    "enable": True,
                    "description": "$.code expect: 0",
                    "type": "JSON",
                    "option": "REGEX"
                }
            ],
            "duration": {
                "type": "Duration",
                "valid": False,
                "enable": True
            },
            "document": {
                "data": {
                    "json": [],
                    "xmlFollowAPI": "false",
                    "xml": [],
                    "jsonFollowAPI": "false"
                },
                "type": "JSON",
                "enable": True
            },
            "id": self._generate_resource_id(),
            "clazzName": "io.metersphere.api.dto.definition.request.assertions.MsAssertions"
        }
    
    def generate_landing_site_scenario(self, apis: List[Dict]) -> Dict:
        """生成起降场场景"""
        scenario_name = "空域情报_起降场"
        
        # 创建基础场景
        scenario = self._create_base_scenario(scenario_name)
        
        # 创建场景定义
        scenario_def = self._create_scenario_definition(scenario_name)
        
        # 过滤起降场相关API
        landing_apis = [api for api in apis if any(tag in api.get('tags', []) for tag in ['起降场'])]
        
        # 按方法分组API
        get_apis = [api for api in landing_apis if api['method'] == 'GET' and 'page' in api['path']]
        post_apis = [api for api in landing_apis if api['method'] == 'POST']
        put_apis = [api for api in landing_apis if api['method'] == 'PUT']
        delete_apis = [api for api in landing_apis if api['method'] == 'DELETE']
        detail_apis = [api for api in landing_apis if api['method'] == 'GET' and '{' in api['path']]
        
        index = 1
        use_urls = []
        
        # 1. 查询列表（默认查询）
        if get_apis:
            sampler = self._create_http_sampler(get_apis[0], "查询起降场列表_默认查询", index)
            scenario_def['hashTree'].append(sampler)
            use_urls.append({"method": "GET", "url": get_apis[0]['path']})
            index += 1
        
        # 2. 查询列表（按关键词查询）
        if get_apis:
            sampler = self._create_http_sampler(get_apis[0], "查询起降场列表_按关键词查询", index)
            # 修改参数
            for arg in sampler['arguments']:
                if arg['name'] == 'keyword':
                    arg['value'] = 'AUTO'
            scenario_def['hashTree'].append(sampler)
            index += 1
        
        # 3. 新增起降场（起降枢纽）
        if post_apis:
            sampler = self._create_http_sampler(post_apis[0], "新增起降场_起降枢纽", index)
            # 设置请求体
            sampler['body']['raw'] = self._create_landing_site_body("起降枢纽", "HUB")
            scenario_def['hashTree'].append(sampler)
            use_urls.append({"method": "POST", "url": post_apis[0]['path']})
            index += 1
        
        # 4. 查看详情
        if detail_apis:
            sampler = self._create_http_sampler(detail_apis[0], "查看起降场详情_起降枢纽", index)
            scenario_def['hashTree'].append(sampler)
            use_urls.append({"method": "GET", "url": detail_apis[0]['path']})
            index += 1
        
        # 5. 新增起降场（起降场）
        if post_apis:
            sampler = self._create_http_sampler(post_apis[0], "新增起降场_起降场", index)
            sampler['body']['raw'] = self._create_landing_site_body("起降场", "SITE")
            scenario_def['hashTree'].append(sampler)
            index += 1
        
        # 6. 新增起降场（起降点）
        if post_apis:
            sampler = self._create_http_sampler(post_apis[0], "新增起降场_起降点", index)
            sampler['body']['raw'] = self._create_landing_site_body("起降点", "POINT")
            scenario_def['hashTree'].append(sampler)
            index += 1
        
        # 7. 编辑起降场
        if put_apis:
            sampler = self._create_http_sampler(put_apis[0], "编辑起降场", index)
            scenario_def['hashTree'].append(sampler)
            use_urls.append({"method": "PUT", "url": put_apis[0]['path']})
            index += 1
        
        # 8. 删除起降场
        if delete_apis:
            sampler = self._create_http_sampler(delete_apis[0], "删除起降场", index)
            scenario_def['hashTree'].append(sampler)
            use_urls.append({"method": "DELETE", "url": delete_apis[0]['path']})
            index += 1
        
        # 更新统计信息
        scenario['stepTotal'] = len(scenario_def['hashTree'])
        scenario['useUrl'] = use_urls
        scenario['scenarioDefinition'] = json.dumps(scenario_def, ensure_ascii=False)
        
        return scenario
    
    def _create_landing_site_body(self, site_name: str, scale: str) -> str:
        """创建起降场请求体"""
        body = {
            "siteName": f"AUTO{site_name}${{__time(MMddHHmmss)}}${{__RandomString(1,ABCDEFGHJKLMN,)}}${{__RandomString(1,0123456789,)}}",
            "code": "${__time(MMddHH)}${__RandomString(2,ABCDEFGHJKLMNPQRSTUVWXYZ,)}",
            "status": "ENABLED",
            "scale": scale,
            "dailyMaxFlightOperations": 50,
            "parkingStandCount": 4,
            "openDegree": "OPEN_TO_PUBLIC",
            "area": 900,
            "takeoffLandingCenterPoints": [
                {
                    "altitude": 50,
                    "coordinates": [
                        "121.132${__RandomString(3,0123456789,)}",
                        "38.726${__RandomString(3,0123456789,)}"
                    ]
                }
            ],
            "waitingAreaPoints": [],
            "enterPoints": [
                {
                    "altitude": 150,
                    "coordinates": [
                        "121.132${__RandomString(3,0123456789,)}",
                        "38.726${__RandomString(3,0123456789,)}"
                    ]
                }
            ],
            "exitPoints": []
        }
        return json.dumps(body, ensure_ascii=False, indent=4)
    
    def generate_generic_scenario(self, apis: List[Dict], scenario_config: Dict) -> Dict:
        """生成通用场景"""
        scenario_name = scenario_config['name']
        
        # 创建基础场景
        scenario = self._create_base_scenario(scenario_name, scenario_config.get('module_path', '/未规划场景'))
        
        # 创建场景定义
        scenario_def = self._create_scenario_definition(scenario_name)
        
        # 过滤相关API
        filtered_apis = [api for api in apis if any(tag in api.get('tags', []) for tag in scenario_config['tags'])]
        
        index = 1
        use_urls = []
        
        for api in filtered_apis[:20]:  # 限制每个场景的API数量
            method = api['method']
            path = api['path']
            summary = api.get('summary', f'{method}_{path}')
            
            # 生成步骤名称
            step_name = f"{summary}_{method}"
            
            sampler = self._create_http_sampler(api, step_name, index)
            scenario_def['hashTree'].append(sampler)
            
            use_urls.append({"method": method, "url": path})
            index += 1
        
        # 更新统计信息
        scenario['stepTotal'] = len(scenario_def['hashTree'])
        scenario['useUrl'] = use_urls
        scenario['scenarioDefinition'] = json.dumps(scenario_def, ensure_ascii=False)
        
        return scenario


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='KTP自动化测试用例生成器')
    parser.add_argument('--swagger', '-s', required=True, help='Swagger JSON文件路径')
    parser.add_argument('--output', '-o', required=True, help='输出目录路径')
    parser.add_argument('--scenario', '-c', default='all', help='场景类型 (all/landing/sector/route/等)')
    
    args = parser.parse_args()
    
    # 解析Swagger
    swagger_parser = KTPSwaggerParser(args.swagger)
    apis = swagger_parser.parse()
    
    print(f"解析到 {len(apis)} 个API接口")
    
    # 创建生成器
    generator = KTPScenarioGenerator()
    
    # 生成场景
    scenarios = []
    
    if args.scenario == 'all' or args.scenario == 'landing':
        print("生成起降场场景...")
        scenario = generator.generate_landing_site_scenario(apis)
        scenarios.append(scenario)
    
    if args.scenario == 'all':
        # 生成其他场景
        for key, config in generator.SCENARIO_MAPPINGS.items():
            if key != "起降场":
                print(f"生成 {config['name']} 场景...")
                scenario = generator.generate_generic_scenario(apis, config)
                if scenario['stepTotal'] > 0:
                    scenarios.append(scenario)
    
    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    if len(scenarios) == 1:
        # 单个场景
        output_file = output_dir / f"KTP_{scenarios[0]['name']}.json"
        result = {
            "data": scenarios,
            "projectId": generator.PROJECT_ID,
            "version": "v1.24.0"
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"已生成测试用例: {output_file}")
    else:
        # 多个场景
        for scenario in scenarios:
            output_file = output_dir / f"KTP_{scenario['name']}.json"
            result = {
                "data": [scenario],
                "projectId": generator.PROJECT_ID,
                "version": "v1.24.0"
            }
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"已生成测试用例: {output_file}")
    
    print(f"\n总共生成 {len(scenarios)} 个场景测试用例")


if __name__ == '__main__':
    main()
