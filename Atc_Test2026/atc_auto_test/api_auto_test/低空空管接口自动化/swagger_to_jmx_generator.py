#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Swagger/OpenAPI 转 JMeter JMX 测试用例生成器
针对低空空管系统接口自动化测试设计

特点：
1. 场景化设计 - 按业务流程组织用例，减少JMX文件数量
2. 环境配置化 - 支持多环境切换
3. 数据驱动 - 动态生成测试数据
4. 断言自动化 - 基于响应结构自动生成断言
"""

import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import os
from datetime import datetime
from typing import Dict, List, Any, Optional


class SwaggerParser:
    """Swagger/OpenAPI 文档解析器"""
    
    def __init__(self, swagger_file: str):
        self.swagger_file = swagger_file
        self.data = self._load_swagger()
        self.base_path = self.data.get('basePath', '/')
        self.host = ""  # 从环境配置获取
        
    def _load_swagger(self) -> dict:
        with open(self.swagger_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_all_apis(self) -> List[Dict]:
        """获取所有API接口列表"""
        apis = []
        paths = self.data.get('paths', {})
        
        for path, methods in paths.items():
            for method, details in methods.items():
                if method in ['get', 'post', 'put', 'delete', 'patch']:
                    api = {
                        'path': path,
                        'method': method.upper(),
                        'summary': details.get('summary', ''),
                        'description': details.get('description', ''),
                        'tags': details.get('tags', ['未分类']),
                        'parameters': details.get('parameters', []),
                        'responses': details.get('responses', {}),
                        'consumes': details.get('consumes', ['application/json']),
                        'produces': details.get('produces', ['application/json'])
                    }
                    apis.append(api)
        
        return apis
    
    def get_apis_by_tag(self, tag: str) -> List[Dict]:
        """按标签获取API列表"""
        all_apis = self.get_all_apis()
        return [api for api in all_apis if tag in api['tags']]
    
    def get_all_tags(self) -> List[str]:
        """获取所有标签"""
        tags = set()
        for api in self.get_all_apis():
            tags.update(api['tags'])
        return sorted(list(tags))


class TestDataGenerator:
    """测试数据生成器"""
    
    # 低空空管业务专用数据模板
    DATA_TEMPLATES = {
        'landing_site_name': '"AUTO起降场${__time(MMddHHmmss)}${__RandomString(1,ABCDEFGHJKLMN,)}"',
        'landing_site_code': '"${__time(MMddHH)}${__RandomString(2,ABCDEFGHJKLMNPQRSTUVWXYZ,)}"',
        'coordinates_lng': '"121.132${__RandomString(3,0123456789,)}"',
        'coordinates_lat': '"38.726${__RandomString(3,0123456789,)}"',
        'uav_identify_code': '"UAV${__time(MMddHHmmss)}${__RandomString(4,0123456789,)}"',
        'flight_task_name': '"FLIGHT_TASK_${__time(MMddHHmmss)}"',
        'flight_plan_name': '"FLIGHT_PLAN_${__time(MMddHHmmss)}"',
        'sector_name': '"SECTOR_${__time(MMddHHmmss)}"',
        'airspace_name': '"AIRSPACE_${__time(MMddHHmmss)}"',
        'air_route_name': '"ROUTE_${__time(MMddHHmmss)}"',
        'phone': '"1${__RandomString(1,3456789,)}${__RandomString(9,0123456789,)}"',
        'email': '"auto_${__time(MMdd)}@test.com"',
        'id_card': '"${__RandomString(1,123456789,)}${__time(yyMMdd)}${__RandomString(4,0123456789,X,)}"',
    }
    
    @classmethod
    def generate_value(cls, param_type: str, param_name: str) -> str:
        """根据参数类型和名称生成测试数据"""
        param_name_lower = param_name.lower()
        
        # 根据参数名匹配业务模板
        if 'sitename' in param_name_lower or 'site_name' in param_name_lower:
            return cls.DATA_TEMPLATES['landing_site_name']
        elif 'code' in param_name_lower and 'landing' in param_name_lower:
            return cls.DATA_TEMPLATES['landing_site_code']
        elif 'uav' in param_name_lower and 'identify' in param_name_lower:
            return cls.DATA_TEMPLATES['uav_identify_code']
        elif 'taskname' in param_name_lower or 'task_name' in param_name_lower:
            return cls.DATA_TEMPLATES['flight_task_name']
        elif 'planname' in param_name_lower or 'plan_name' in param_name_lower:
            return cls.DATA_TEMPLATES['flight_plan_name']
        elif 'sectorname' in param_name_lower or 'sector_name' in param_name_lower:
            return cls.DATA_TEMPLATES['sector_name']
        elif 'airspacename' in param_name_lower or 'airspace_name' in param_name_lower:
            return cls.DATA_TEMPLATES['airspace_name']
        elif 'phonenumber' in param_name_lower or 'phone' in param_name_lower:
            return cls.DATA_TEMPLATES['phone']
        elif 'email' in param_name_lower:
            return cls.DATA_TEMPLATES['email']
        elif 'idcard' in param_name_lower or 'id_card' in param_name_lower:
            return cls.DATA_TEMPLATES['id_card']
        
        # 根据类型生成
        type_generators = {
            'string': '"${__RandomString(10,abcdefghijklmnopqrstuvwxyz,)}"',
            'integer': '${__Random(1,1000)}',
            'number': '${__Random(1,1000)}',
            'boolean': 'true',
            'array': '[]',
            'object': '{}'
        }
        
        return type_generators.get(param_type, '"test_value"')


class JMXGenerator:
    """JMeter JMX 文件生成器"""
    
    # 环境配置模板
    ENVIRONMENTS = {
        'sit': {
            'name': 'SIT测试环境',
            'protocol': 'https',
            'host': 'dkkgsit-test.testdolphin.com',
            'port': '443',
            'base_path_biz': '/la-atc-biz-backend',
            'base_path_ops': '/la-atc-ops-server',
            'description': '系统集成测试环境，用于接口功能验证'
        },
        'uat': {
            'name': 'UAT验收环境',
            'protocol': 'https',
            'host': 'dkkguat-test.testdolphin.com',
            'port': '443',
            'base_path_biz': '/la-atc-biz-backend',
            'base_path_ops': '/la-atc-ops-server',
            'description': '用户验收测试环境'
        }
    }
    
    def __init__(self, output_dir: str = '接口测试用例jmx'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def _create_test_plan(self, name: str, comment: str = '') -> ET.Element:
        """创建测试计划根元素"""
        test_plan = ET.Element('jmeterTestPlan', {
            'version': '1.2',
            'properties': '5.0',
            'jmeter': '5.4.1'
        })
        
        hash_tree = ET.SubElement(test_plan, 'hashTree')
        
        # TestPlan
        plan = ET.SubElement(hash_tree, 'TestPlan', {
            'guiclass': 'TestPlanGui',
            'testclass': 'TestPlan',
            'testname': name,
            'enabled': 'true'
        })
        
        # 添加注释说明
        if comment:
            string_prop = ET.SubElement(plan, 'stringProp', {'name': 'TestPlan.comments'})
            string_prop.text = comment
        
        # 用户定义变量
        args = ET.SubElement(plan, 'elementProp', {
            'name': 'TestPlan.user_defined_variables',
            'elementType': 'Arguments'
        })
        collection = ET.SubElement(args, 'collectionProp', {'name': 'Arguments.arguments'})
        
        # 添加环境变量
        env_vars = [
            ('protocol', '${__P(protocol,https)}'),
            ('host', '${__P(host,dkkgsit-test.testdolphin.com)}'),
            ('port', '${__P(port,443)}'),
            ('jwt-token', '${__P(jwt-token,)}'),
        ]
        for var_name, var_value in env_vars:
            self._add_argument(collection, var_name, var_value)
        
        return test_plan, hash_tree
    
    def _add_argument(self, parent: ET.Element, name: str, value: str):
        """添加参数元素"""
        arg = ET.SubElement(parent, 'elementProp', {
            'name': name,
            'elementType': 'Argument'
        })
        ET.SubElement(arg, 'stringProp', {'name': 'Argument.name'}).text = name
        ET.SubElement(arg, 'stringProp', {'name': 'Argument.value'}).text = value
        ET.SubElement(arg, 'stringProp', {'name': 'Argument.metadata'}).text = '='
    
    def _create_thread_group(self, parent: ET.Element, name: str, comment: str = '') -> ET.Element:
        """创建线程组"""
        tg = ET.SubElement(parent, 'ThreadGroup', {
            'guiclass': 'ThreadGroupGui',
            'testclass': 'ThreadGroup',
            'testname': name,
            'enabled': 'true'
        })
        
        if comment:
            ET.SubElement(tg, 'stringProp', {'name': 'TestPlan.comments'}).text = comment
        
        ET.SubElement(tg, 'stringProp', {'name': 'ThreadGroup.on_sample_error'}).text = 'continue'
        ET.SubElement(tg, 'intProp', {'name': 'ThreadGroup.num_threads'}).text = '1'
        ET.SubElement(tg, 'intProp', {'name': 'ThreadGroup.ramp_time'}).text = '1'
        ET.SubElement(tg, 'longProp', {'name': 'ThreadGroup.delay'}).text = '0'
        ET.SubElement(tg, 'longProp', {'name': 'ThreadGroup.duration'}).text = '0'
        ET.SubElement(tg, 'boolProp', {'name': 'ThreadGroup.scheduler'}).text = 'false'
        
        # Loop Controller
        loop = ET.SubElement(tg, 'elementProp', {
            'name': 'ThreadGroup.main_controller',
            'elementType': 'LoopController',
            'guiclass': 'LoopControlPanel',
            'testclass': 'LoopController',
            'testname': 'LoopController',
            'enabled': 'true'
        })
        ET.SubElement(loop, 'boolProp', {'name': 'LoopController.continue_forever'}).text = 'false'
        ET.SubElement(loop, 'intProp', {'name': 'LoopController.loops'}).text = '1'
        
        hash_tree = ET.SubElement(parent, 'hashTree')
        return hash_tree
    
    def _create_http_sampler(self, parent: ET.Element, api: Dict, base_path: str, 
                             scenario_name: str = '') -> ET.Element:
        """创建HTTP请求采样器"""
        sampler_name = api.get('summary') or f"{api['method']}_{api['path']}"
        if scenario_name:
            sampler_name = f"{scenario_name}_{sampler_name}"
        
        sampler = ET.SubElement(parent, 'HTTPSamplerProxy', {
            'guiclass': 'HttpTestSampleGui',
            'testclass': 'HTTPSamplerProxy',
            'testname': sampler_name[:80],  # JMeter名称长度限制
            'enabled': 'true'
        })
        
        # 构建完整路径
        full_path = base_path + api['path']
        
        # 处理路径参数
        path_params = []
        query_params = []
        body_params = {}
        headers = {'Content-Type': 'application/json'}
        
        for param in api.get('parameters', []):
            param_in = param.get('in', '')
            param_name = param.get('name', '')
            param_type = param.get('type', 'string')
            required = param.get('required', False)
            
            if param_in == 'path':
                # 路径参数使用变量
                full_path = full_path.replace(f'{{{param_name}}}', f'${{{param_name}}}')
                path_params.append(param)
            elif param_in == 'query':
                query_params.append(param)
            elif param_in == 'body':
                # 请求体
                schema = param.get('schema', {})
                if schema:
                    body_params = self._generate_body_from_schema(schema)
            elif param_in == 'header':
                headers[param_name] = param.get('example', '')
        
        # 添加查询参数
        if query_params:
            query_parts = []
            for qp in query_params:
                name = qp.get('name', '')
                example = qp.get('example', '')
                if example:
                    query_parts.append(f"{name}={example}")
                else:
                    query_parts.append(name)
            if query_parts:
                full_path += '?' + '&'.join(query_parts)
        
        # 设置HTTP参数
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.domain'}).text = '${host}'
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.port'}).text = '${port}'
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.protocol'}).text = '${protocol}'
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.path'}).text = full_path
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.method'}).text = api['method']
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.contentEncoding'}).text = 'UTF-8'
        ET.SubElement(sampler, 'boolProp', {'name': 'HTTPSampler.follow_redirects'}).text = 'true'
        ET.SubElement(sampler, 'boolProp', {'name': 'HTTPSampler.use_keepalive'}).text = 'true'
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.connect_timeout'}).text = '60000'
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.response_timeout'}).text = '60000'
        
        # 请求体
        if body_params and api['method'] in ['POST', 'PUT', 'PATCH']:
            args = ET.SubElement(sampler, 'elementProp', {
                'name': 'HTTPsampler.Arguments',
                'elementType': 'Arguments'
            })
            collection = ET.SubElement(args, 'collectionProp', {'name': 'Arguments.arguments'})
            
            arg = ET.SubElement(collection, 'elementProp', {
                'name': '',
                'elementType': 'HTTPArgument'
            })
            ET.SubElement(arg, 'boolProp', {'name': 'HTTPArgument.always_encode'}).text = 'false'
            ET.SubElement(arg, 'stringProp', {'name': 'Argument.value'}).text = json.dumps(body_params, ensure_ascii=False, indent=4)
            ET.SubElement(arg, 'stringProp', {'name': 'Argument.metadata'}).text = '='
            
            ET.SubElement(sampler, 'boolProp', {'name': 'HTTPSampler.postBodyRaw'}).text = 'true'
        
        hash_tree = ET.SubElement(parent, 'hashTree')
        
        # 添加HeaderManager
        if headers:
            self._create_header_manager(hash_tree, headers)
        
        # 添加断言
        self._create_assertions(hash_tree, api)
        
        return hash_tree
    
    def _generate_body_from_schema(self, schema: Dict) -> Dict:
        """根据Schema生成请求体"""
        body = {}
        properties = schema.get('properties', {})
        
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get('type', 'string')
            
            if prop_type == 'string':
                body[prop_name] = TestDataGenerator.generate_value('string', prop_name)
            elif prop_type == 'integer':
                body[prop_name] = 0
            elif prop_type == 'number':
                body[prop_name] = 0.0
            elif prop_type == 'boolean':
                body[prop_name] = True
            elif prop_type == 'array':
                body[prop_name] = []
            elif prop_type == 'object':
                body[prop_name] = self._generate_body_from_schema(prop_schema)
        
        return body
    
    def _create_header_manager(self, parent: ET.Element, headers: Dict):
        """创建Header管理器"""
        manager = ET.SubElement(parent, 'HeaderManager', {
            'guiclass': 'HeaderPanel',
            'testclass': 'HeaderManager',
            'testname': 'HTTP Header Manager',
            'enabled': 'true'
        })
        
        collection = ET.SubElement(manager, 'collectionProp', {'name': 'HeaderManager.headers'})
        
        for name, value in headers.items():
            header = ET.SubElement(collection, 'elementProp', {
                'name': name,
                'elementType': 'Header'
            })
            ET.SubElement(header, 'stringProp', {'name': 'Header.name'}).text = name
            ET.SubElement(header, 'stringProp', {'name': 'Header.value'}).text = value
        
        ET.SubElement(parent, 'hashTree')
    
    def _create_assertions(self, parent: ET.Element, api: Dict):
        """创建响应断言"""
        # status 断言
        status_assertion = ET.SubElement(parent, 'JSONPathAssertion', {
            'guiclass': 'JSONPathAssertionGui',
            'testclass': 'JSONPathAssertion',
            'testname': '断言: status = 200',
            'enabled': 'true'
        })
        ET.SubElement(status_assertion, 'stringProp', {'name': 'JSON_PATH'}).text = '$.status'
        ET.SubElement(status_assertion, 'stringProp', {'name': 'EXPECTED_VALUE'}).text = '200'
        ET.SubElement(status_assertion, 'boolProp', {'name': 'JSONVALIDATION'}).text = 'true'
        ET.SubElement(status_assertion, 'boolProp', {'name': 'ISREGEX'}).text = 'true'
        ET.SubElement(parent, 'hashTree')
        
        # code 断言
        code_assertion = ET.SubElement(parent, 'JSONPathAssertion', {
            'guiclass': 'JSONPathAssertionGui',
            'testclass': 'JSONPathAssertion',
            'testname': '断言: code = 0',
            'enabled': 'true'
        })
        ET.SubElement(code_assertion, 'stringProp', {'name': 'JSON_PATH'}).text = '$.code'
        ET.SubElement(code_assertion, 'stringProp', {'name': 'EXPECTED_VALUE'}).text = '0'
        ET.SubElement(code_assertion, 'boolProp', {'name': 'JSONVALIDATION'}).text = 'true'
        ET.SubElement(code_assertion, 'boolProp', {'name': 'ISREGEX'}).text = 'true'
        ET.SubElement(parent, 'hashTree')
    
    def _prettify_xml(self, elem: ET.Element) -> str:
        """格式化XML输出"""
        rough_string = ET.tostring(elem, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")
    
    def generate_scene_jmx(self, scene_name: str, apis: List[Dict], 
                           base_path: str, env: str = 'sit',
                           description: str = '') -> str:
        """
        生成场景化JMX文件
        
        Args:
            scene_name: 场景名称
            apis: API列表
            base_path: 基础路径
            env: 环境标识
            description: 场景描述
        """
        env_config = self.ENVIRONMENTS.get(env, self.ENVIRONMENTS['sit'])
        
        # 构建注释
        comment = f"""
【环境配置】
环境名称: {env_config['name']}
协议: {env_config['protocol']}
主机: {env_config['host']}
端口: {env_config['port']}
基础路径: {base_path}
描述: {env_config['description']}

【场景说明】
{description}

【覆盖接口】
"""
        for i, api in enumerate(apis, 1):
            comment += f"{i}. {api['method']} {api['path']} - {api.get('summary', '')}\n"
        
        comment += f"""
【使用说明】
1. 修改用户定义变量中的 jwt-token 为有效的认证令牌
2. 可通过命令行参数覆盖环境变量，如: jmeter -Jhost=xxx -Jjwt-token=xxx
3. 执行前确保测试环境可访问

【生成时间】
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        # 创建测试计划
        test_plan, hash_tree = self._create_test_plan(scene_name, comment)
        
        # 创建线程组
        tg_hash_tree = self._create_thread_group(hash_tree, scene_name)
        
        # 添加Cookie管理器
        cookie_manager = ET.SubElement(tg_hash_tree, 'CookieManager', {
            'guiclass': 'CookiePanel',
            'testclass': 'CookieManager',
            'testname': 'Cookie Manager',
            'enabled': 'true'
        })
        ET.SubElement(cookie_manager, 'collectionProp', {'name': 'CookieManager.cookies'})
        ET.SubElement(cookie_manager, 'boolProp', {'name': 'CookieManager.clearEachIteration'}).text = 'false'
        ET.SubElement(tg_hash_tree, 'hashTree')
        
        # 添加HTTP请求
        for api in apis:
            self._create_http_sampler(tg_hash_tree, api, base_path, scene_name)
        
        # 保存文件
        filename = f"{scene_name}_{env}.jmx"
        filepath = os.path.join(self.output_dir, filename)
        
        xml_content = self._prettify_xml(test_plan)
        # 移除空行
        xml_content = '\n'.join([line for line in xml_content.split('\n') if line.strip()])
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        return filepath


class SceneBasedTestGenerator:
    """基于场景的测试用例生成器"""
    
    # 场景定义：将相关接口组织到业务场景中
    SCENES = {
        '低空空管自动化系统': {
            'base_path': '/la-atc-biz-backend',
            'scenes': [
                {
                    'name': '01_起降场管理场景',
                    'tags': ['起降场'],
                    'description': '覆盖起降场的增删改查、状态切换等核心业务流程'
                },
                {
                    'name': '02_扇区管理场景',
                    'tags': ['扇区管理'],
                    'description': '覆盖扇区的增删改查、关联查询等操作'
                },
                {
                    'name': '03_航路航线管理场景',
                    'tags': ['航路管理'],
                    'description': '覆盖航路航线的增删改查操作'
                },
                {
                    'name': '04_空域管理场景',
                    'tags': ['空域管理'],
                    'description': '覆盖空域的增删改查、状态管理等操作'
                },
                {
                    'name': '05_飞行计划管理场景',
                    'tags': ['飞行计划'],
                    'description': '覆盖飞行计划的创建、审批、修改、取消等全流程'
                },
                {
                    'name': '06_飞行任务管理场景',
                    'tags': ['飞行任务'],
                    'description': '覆盖飞行任务的创建、放飞申请、变更、完成等流程'
                },
                {
                    'name': '07_无人机管理场景',
                    'tags': ['无人机管理'],
                    'description': '覆盖无人机的注册、查询、修改、状态变更等操作'
                },
                {
                    'name': '08_告警管理场景',
                    'tags': ['告警管理'],
                    'description': '覆盖告警的查询、处理、统计等操作'
                },
                {
                    'name': '09_坐席管理场景',
                    'tags': ['坐席管理'],
                    'description': '覆盖坐席的登录、状态管理、交接班等操作'
                },
                {
                    'name': '10_用户权限管理场景',
                    'tags': ['用户管理', '统一权限'],
                    'description': '覆盖用户的增删改查、角色权限分配等操作'
                },
                {
                    'name': '11_态势大屏查询场景',
                    'tags': ['态势大屏'],
                    'description': '覆盖态势大屏的各类数据查询接口'
                },
                {
                    'name': '12_运营人管理场景',
                    'tags': ['运营人管理'],
                    'description': '覆盖运营人的增删改查操作'
                },
                {
                    'name': '13_操作日志查询场景',
                    'tags': ['操作日志'],
                    'description': '覆盖操作日志的查询、导出等操作'
                },
                {
                    'name': '14_接收机管理场景',
                    'tags': ['接收机管理'],
                    'description': '覆盖接收机的增删改查、状态监控等操作'
                },
                {
                    'name': '15_其他功能场景',
                    'tags': ['系统管理', '消息中心', '工作台', 'License', '算法接口管理', '模拟器', 'ES', '公共接口', '操作员管理'],
                    'description': '覆盖其他辅助功能接口'
                }
            ]
        },
        '低空运维系统': {
            'base_path': '/la-atc-ops-server',
            'scenes': [
                {
                    'name': '21_运维接收机管理场景',
                    'tags': ['接收机管理'],
                    'description': '覆盖运维系统接收机的配置、监控、告警等操作'
                },
                {
                    'name': '22_运维告警管理场景',
                    'tags': ['告警管理'],
                    'description': '覆盖运维告警的查询、处理、统计等操作'
                },
                {
                    'name': '23_版本升级管理场景',
                    'tags': ['版本升级'],
                    'description': '覆盖版本升级的检查、下载、安装等操作'
                },
                {
                    'name': '24_网络拓扑管理场景',
                    'tags': ['平台网络拓扑图管理', '平台网络拓扑图连线管理', '平台网络拓扑设备管理'],
                    'description': '覆盖网络拓扑图的管理、设备配置等操作'
                },
                {
                    'name': '25_运维监控查询场景',
                    'tags': ['海豚运维-指标查询', 'EMQX统计接口'],
                    'description': '覆盖运维监控指标的查询、统计等操作'
                },
                {
                    'name': '26_运维公共接口场景',
                    'tags': ['公共分类'],
                    'description': '覆盖运维系统的公共接口'
                }
            ]
        }
    }
    
    def __init__(self, swagger_file: str, output_dir: str = '接口测试用例jmx'):
        self.parser = SwaggerParser(swagger_file)
        self.jmx_generator = JMXGenerator(output_dir)
        
    def generate_all_scenes(self, env: str = 'sit'):
        """生成所有场景的JMX文件"""
        generated_files = []
        
        # 确定系统类型
        system_type = None
        for sys_name in self.SCENES.keys():
            if sys_name in self.parser.swagger_file:
                system_type = sys_name
                break
        
        if not system_type:
            print(f"警告: 无法识别系统类型，使用默认配置")
            system_type = '低空空管自动化系统'
        
        config = self.SCENES[system_type]
        base_path = config['base_path']
        
        print(f"\n{'='*60}")
        print(f"开始生成 {system_type} 接口测试用例")
        print(f"环境: {env}")
        print(f"输出目录: {self.jmx_generator.output_dir}")
        print(f"{'='*60}\n")
        
        for scene in config['scenes']:
            # 收集该场景的所有API
            scene_apis = []
            for tag in scene['tags']:
                apis = self.parser.get_apis_by_tag(tag)
                scene_apis.extend(apis)
            
            if not scene_apis:
                print(f"跳过: {scene['name']} - 未找到匹配的接口")
                continue
            
            # 去重
            seen = set()
            unique_apis = []
            for api in scene_apis:
                key = f"{api['method']}_{api['path']}"
                if key not in seen:
                    seen.add(key)
                    unique_apis.append(api)
            
            print(f"生成: {scene['name']} - 包含 {len(unique_apis)} 个接口")
            
            # 生成JMX
            filepath = self.jmx_generator.generate_scene_jmx(
                scene_name=scene['name'],
                apis=unique_apis,
                base_path=base_path,
                env=env,
                description=scene['description']
            )
            generated_files.append(filepath)
            print(f"  -> {filepath}\n")
        
        return generated_files


def main():
    """主函数"""
    import sys
    
    # 默认配置
    env = 'sit'
    
    # 解析命令行参数
    if len(sys.argv) > 1:
        env = sys.argv[1]
    
    print("="*60)
    print("低空空管系统接口测试用例生成器")
    print("="*60)
    print(f"目标环境: {env}")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 生成低空空管自动化系统用例
    biz_file = '低空空管自动化系统swaggerApi0422.json'
    if os.path.exists(biz_file):
        generator = SceneBasedTestGenerator(biz_file)
        biz_files = generator.generate_all_scenes(env)
        print(f"\n低空空管自动化系统生成完成: {len(biz_files)} 个场景文件")
    else:
        print(f"\n警告: 未找到文件 {biz_file}")
        biz_files = []
    
    # 生成低空运维系统用例
    ops_file = '低空运维系统swaggerApi0422.json'
    if os.path.exists(ops_file):
        generator = SceneBasedTestGenerator(ops_file)
        ops_files = generator.generate_all_scenes(env)
        print(f"\n低空运维系统生成完成: {len(ops_files)} 个场景文件")
    else:
        print(f"\n警告: 未找到文件 {ops_file}")
        ops_files = []
    
    # 汇总
    total_files = len(biz_files) + len(ops_files)
    print("\n" + "="*60)
    print("生成汇总")
    print("="*60)
    print(f"总场景文件数: {total_files}")
    print(f"输出目录: 接口测试用例jmx/")
    print("="*60)
    print("\n使用说明:")
    print("1. 打开 JMeter，导入生成的 .jmx 文件")
    print("2. 修改 TestPlan -> User Defined Variables 中的 jwt-token")
    print("3. 可通过命令行参数覆盖环境变量:")
    print("   jmeter -Jhost=xxx -Jjwt-token=xxx -n -t xxx.jmx -l result.jtl")
    print("="*60)


if __name__ == '__main__':
    main()
