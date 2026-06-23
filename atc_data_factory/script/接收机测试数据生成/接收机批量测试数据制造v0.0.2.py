#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接收机批量测试数据生成脚本（插入图片版本，开关控制）

功能：
1. 读取批量导入模板，获取字段结构和必填要求
2. 读取已测试文件，了解数据格式和实景图
3. 生成100条不重复的测试数据
4. 保持原文件格式、列宽等不变
5. 实景图使用已有图片复制填充

输出：F:\下载\接收机批量测试数据_{日期}_V0.1.xlsx
"""

import os
import sys
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# 生成数据数量配置（可在文件顶部修改此值，或通过命令行参数、环境变量设置）
DEFAULT_GENERATION_COUNT = 2  # 默认生成100条数据

# 实景图配置路径（可配置，支持jpg/png格式）
# 可通过环境变量 SCENE_IMAGE_PATH 覆盖，或修改下方默认值
DEFAULT_SCENE_IMAGE_PATH = r"C:\Users\wdjlw\Pictures"  # 默认图片路径

# 图片插入开关（默认True插入图片，False不插入图片）
# 可通过环境变量 INSERT_SCENE_IMAGE 覆盖，或修改下方默认值
# 环境变量值: "true"/"1"/"yes" 表示插入，其他值表示不插入
DEFAULT_INSERT_SCENE_IMAGE = False  # 默认插入图片，False表示不插入图片

# 输出目录配置（默认F:\下载）
# 可通过环境变量 OUTPUT_DIR 覆盖，或修改下方默认值
DEFAULT_OUTPUT_DIR = r"F:\下载"

# 经纬度坐标生成开关（默认True生成经纬度，False不生成经纬度）
# 可通过环境变量 GENERATE_COORDINATES 覆盖，或修改下方默认值
# 环境变量值: "true"/"1"/"yes" 表示生成，其他值表示不生成
DEFAULT_GENERATE_COORDINATES = False  # True表示默认生成经纬度坐标，False表示不生成经纬度坐标


# 尝试导入openpyxl
try:
    from openpyxl import load_workbook, Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.drawing.image import Image as XLImage
except ImportError:
    print("请先安装openpyxl: pip install openpyxl")
    sys.exit(1)

# 尝试导入PIL用于图片处理
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("警告: 未安装PIL，图片处理功能可能受限。建议安装: pip install Pillow")


class ReceiverDataGenerator:
    """接收机批量测试数据生成器"""
    
    # 生成参数 - 可通过环境变量或配置文件修改
    # 注意：DEFAULT_COUNT在__init__中动态获取，以支持修改DEFAULT_GENERATION_COUNT后即时生效
    START_INDEX = 10001  # 从10001开始，避免与已有数据重复
    
    # 数据生成规则 - 按模板字段定义
    # 必填字段（*）
    # 设备ID与扇区关联：若选择yfksq2-1，则扇区按照序号规则自增
    SECTORS = ["北京周边扇区", "yfksq2-1", "yfksq2-2", "yfksq3", "yfksq4", "盐城扇区(西)", "盐城扇区(东)", "新疆扇区", "suhou"]
    
    AREA_TYPES = ["其他", "历史文化保护", "危险品防护", "特殊监管类", "政务服务类", "重大基础设施", "正常航路"]
    
    DEVICE_TYPES = ["通感设备", "网络式接收节点", "低空ADS-B", "广播式接收机"]
    
    # 非必填字段
    FUNCTION_TYPES = ["ADS-B", "雷达采集", "4/5G采集", "WiFi&蓝牙采集", "WIFI采集"]
    
    MANUFACTURERS = ["海康", "蓝天使", "苏州科达", "科达航宇", "华为", "中兴", "大疆", "航天科工"]
    
    MODELS = ["MPD200-WG", "RX-1000", "ADS-B-001", "TK-500", "UAV-RX200", "SKY-EYE-01"]
    
    ADDRESSES = [
        "楼顶平台", "塔台顶部", "地面基站", 
        "山顶观测点", "机场跑道旁", "控制中心屋顶",
        "通信塔中部", "气象站旁边", "导航台顶部"
    ]
    
    RESPONSIBLE_PERSONS = ["吴卫彬", "张瑞坡", "姚福坤", "尼格买提", "海来阿木", "哪吒", "杨幂", "刘诗诗", "郑观音", "王十二"]
    
    MAINTENANCE_UNITS = ["苏州科达", "科达航宇", "维保公司C", "原厂维保", "第三方维保"]
    
    MANAGEMENT_UNITS = ["管理单位A", "管理单位B", "管理单位C", "空管局", "机场集团", "蓝天使"]
    
    PROTOCOLS = ["其他", "MQTT"]
    
    CONNECTION_TYPES = ["间接接入", "直连"]
    
    # 坐标范围（根据实际情况调整）
    LNG_RANGE = (113.0, 121.0)  # 经度范围（扩大范围覆盖更多区域）
    LAT_RANGE = (22.0, 40.0)    # 纬度范围（扩大范围覆盖更多区域）
    ALT_RANGE = (0, 500)        # 海拔范围
    DETECTION_RANGE = (1, 50)   # 探测距离范围：1~50公里
    TARGET_COUNT_RANGE = (10, 200)  # 最大可探测目标数量：10~200
    
    def __init__(self, count: int = None):
        """
        初始化生成器
        
        Args:
            count: 需要生成的数据条数，默认使用DEFAULT_GENERATION_COUNT或环境变量
        """
        # 动态获取数量：参数 > 环境变量 > 默认值
        if count is not None:
            self.count = count
        else:
            self.count = int(os.environ.get("RECEIVER_DATA_COUNT", DEFAULT_GENERATION_COUNT))
        
        # 动态获取当前脚本所在目录（确保路径正确）
        # 使用多种方式确保获取正确的脚本目录
        try:
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            # 如果 __file__ 未定义（某些IDE环境），使用当前工作目录
            self.script_dir = os.getcwd()
        
        # 验证脚本目录是否存在模板文件，如果不存在则尝试当前工作目录
        template_path = os.path.join(self.script_dir, "批量导入模板.xlsx")
        if not os.path.exists(template_path):
            # 尝试当前工作目录
            cwd_template = os.path.join(os.getcwd(), "批量导入模板.xlsx")
            if os.path.exists(cwd_template):
                self.script_dir = os.getcwd()
                template_path = cwd_template
        
        self.template_file = template_path
        
        # 输出目录配置（环境变量 > 默认值）
        self.output_dir = os.environ.get("OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
        
        # 实景图路径配置（环境变量 > 默认值）
        self.scene_image_path = os.environ.get("SCENE_IMAGE_PATH", DEFAULT_SCENE_IMAGE_PATH)
        
        # 图片插入开关（环境变量 > 默认值）
        env_insert = os.environ.get("INSERT_SCENE_IMAGE", "").lower()
        if env_insert in ("true", "1", "yes"):
            self.insert_scene_image = True
        elif env_insert in ("false", "0", "no"):
            self.insert_scene_image = False
        else:
            self.insert_scene_image = DEFAULT_INSERT_SCENE_IMAGE
        
        # 经纬度坐标生成开关（环境变量 > 默认值）
        env_generate_coords = os.environ.get("GENERATE_COORDINATES", "").lower()
        if env_generate_coords in ("true", "1", "yes"):
            self.generate_coordinates = True
        elif env_generate_coords in ("false", "0", "no"):
            self.generate_coordinates = False
        else:
            self.generate_coordinates = DEFAULT_GENERATE_COORDINATES
        
        self.scene_images = []  # 存储找到的图片路径列表
        
        self.current_date = datetime.now()
        self.date_str = self.current_date.strftime("%m%d")  # 月日格式，如0421
        self.date_str_full = self.current_date.strftime("%Y%m%d")  # 年月日格式
        
        # 存储已使用的值（用于去重）
        self.used_device_names = set()
        self.used_device_ids = set()
        self.used_coordinates = set()
        
        # 存储生成的数据
        self.generated_data: List[Dict[str, Any]] = []
        
        # 扇区批次管理
        self.current_sector_index = 0  # 当前扇区索引
        self.current_sector_remaining = 0  # 当前扇区剩余生成数量
        
        # Excel相关
        self.wb = None
        self.ws = None
        self.output_path = None
        self.column_mapping: Dict[str, int] = {}
        self.scene_images: List[Any] = []  # 存储源文件中的实景图
        
    def _generate_device_name(self, index: int) -> str:
        """
        生成设备名称
        
        规则: 接收机-{当前日期（月日）}-{5位序号}
        示例: 接收机-0421-10001
        """
        return f"接收机-{self.date_str}-{index:05d}"
    
    def _get_next_sector_and_count(self) -> tuple:
        """
        获取下一个扇区和该扇区需要生成的数据条数
        
        规则:
        - 每个扇区连续生成10~30条数据
        - 按扇区列表顺序循环
        
        Returns:
            (sector, count): 扇区名称和该扇区的生成数量
        """
        if self.current_sector_remaining <= 0:
            # 需要选择新扇区
            sector = self.SECTORS[self.current_sector_index]
            # 随机生成10~30条
            self.current_sector_remaining = random.randint(10, 30)
            # 移动到下一个扇区索引
            self.current_sector_index = (self.current_sector_index + 1) % len(self.SECTORS)
            return sector, self.current_sector_remaining
        else:
            # 继续使用当前扇区（索引-1因为已经移动过了）
            prev_index = (self.current_sector_index - 1) % len(self.SECTORS)
            sector = self.SECTORS[prev_index]
            return sector, self.current_sector_remaining
    
    def _generate_device_id_and_sector(self, index: int) -> tuple:
        """
        生成设备ID和所属扇区（关联）
        
        规则: 
        - 先选择扇区，在该扇区下连续生成10~30条数据
        - 设备ID为7位纯数字序号
        - 扇区与设备ID序号关联
        
        示例: 
        - 全国扇区: 设备ID 0000001 ~ 0000020 (20条)
        - 北京扇区: 设备ID 0000021 ~ 0000045 (25条)
        - yfksq2-1: 设备ID 0000046 ~ 0000060 (15条)
        """
        seq_num = index - self.START_INDEX + 1  # 从0000001开始
        device_id = f"{seq_num:07d}"
        
        # 获取当前扇区（并减少剩余计数）
        sector, _ = self._get_next_sector_and_count()
        self.current_sector_remaining -= 1
        
        return device_id, sector
    
    def _generate_sector(self) -> str:
        """生成所属扇区（独立调用时使用）"""
        return random.choice(self.SECTORS)
    
    def _generate_area_type(self) -> str:
        """生成区域类型"""
        return random.choice(self.AREA_TYPES)
    
    def _generate_device_type(self) -> str:
        """生成设备类型"""
        return random.choice(self.DEVICE_TYPES)
    
    def _generate_function_type(self) -> str:
        """生成功能类型"""
        return random.choice(self.FUNCTION_TYPES)
    
    def _generate_manufacturer(self) -> str:
        """生成厂商"""
        return random.choice(self.MANUFACTURERS)
    
    def _generate_model(self) -> str:
        """生成型号"""
        return random.choice(self.MODELS)
    
    def _generate_ipv4(self) -> str:
        """生成IPv4地址"""
        # 随机选择内网段
        if random.random() < 0.7:
            return f"192.168.{random.randint(0, 255)}.{random.randint(1, 254)}"
        else:
            return f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
    
    def _generate_ipv6(self) -> str:
        """生成IPv6地址（可为空）"""
        if random.random() < 0.3:  # 30%概率生成
            return f"2001:0db8:85a3:{random.randint(0, 9999):04x}::{random.randint(0, 9999):04x}:{random.randint(0, 9999):04x}"
        return ""
    
    def _generate_detection_range(self) -> int:
        """生成探测距离"""
        return random.randint(self.DETECTION_RANGE[0], self.DETECTION_RANGE[1])
    
    def _generate_max_targets(self) -> int:
        """生成最大可探测目标数量"""
        return random.randint(self.TARGET_COUNT_RANGE[0], self.TARGET_COUNT_RANGE[1])
    
    # 固件版本号固定值（根据模板示例）
    FIRMWARE_VERSION_DEFAULT = "8.1.23.25"
    
    def _generate_firmware_version(self) -> str:
        """生成固件版本号 - 固定值"""
        return self.FIRMWARE_VERSION_DEFAULT
    
    def _generate_sn(self, index: int) -> str:
        """
        生成序列号
        
        规则: SN2026002101 格式
        - SN + 年份(2026) + 月份(00) + 日期(21) + 序号(01)
        """
        seq_num = index - self.START_INDEX + 1
        return f"SN{self.current_date.strftime('%Y')}00{self.date_str}{seq_num:02d}"
    
    def _generate_install_height(self) -> float:
        """生成安装高度"""
        return round(random.uniform(0, 100), 1)
    
    def _generate_install_datetime(self) -> str:
        """
        生成安装时间
        
        规则: 2026-01-01 ~ 当前日期
        """
        # 基准日期 2026-01-01
        base_date = datetime(2026, 1, 1)
        # 计算从基准日期到当前日期的天数差
        days_diff = (self.current_date - base_date).days
        if days_diff < 0:
            days_diff = 0  # 如果当前日期早于2026-01-01，则使用基准日期
        
        # 在范围内随机选择一天
        random_days = random.randint(0, days_diff)
        install_date = base_date + timedelta(days=random_days)
        hour = random.randint(8, 18)
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        return install_date.strftime(f"%Y-%m-%d {hour:02d}:{minute:02d}:{second:02d}")
    
    def _generate_maintenance_unit(self) -> str:
        """生成维保单位"""
        return random.choice(self.MAINTENANCE_UNITS)
    
    def _generate_management_unit(self) -> str:
        """生成管理单位"""
        return random.choice(self.MANAGEMENT_UNITS)
    
    def _generate_protocol(self) -> str:
        """生成接入协议"""
        return random.choice(self.PROTOCOLS)
    
    def _generate_connection_type(self) -> str:
        """生成连接类型"""
        return random.choice(self.CONNECTION_TYPES)
    
    # MQTT相关字段固定值配置（根据模板示例）
    MQTT_DEFAULTS = {
        "mqtt_version": "3.1.1",
        "mqtt_broker": "mqtt.example.com",
        "mqtt_port": 1883,
        "topic_prefix": "/device",
        "heartbeat_interval": 60,
        "login_url": "http://device.example.com",
        "password": "Lts2026#LSSR001"
    }
    
    def _generate_mqtt_version(self) -> str:
        """生成MQTT协议版本 - 固定值"""
        return self.MQTT_DEFAULTS["mqtt_version"]
    
    def _generate_mqtt_broker(self) -> str:
        """生成MQTT代理地址 - 固定值"""
        return self.MQTT_DEFAULTS["mqtt_broker"]
    
    def _generate_mqtt_port(self) -> int:
        """生成MQTT代理端口 - 固定值"""
        return self.MQTT_DEFAULTS["mqtt_port"]
    
    def _generate_topic_prefix(self) -> str:
        """生成Topic前缀 - 固定值"""
        return self.MQTT_DEFAULTS["topic_prefix"]
    
    def _generate_heartbeat_interval(self) -> int:
        """生成心跳间隔 - 固定值"""
        return self.MQTT_DEFAULTS["heartbeat_interval"]
    
    def _generate_login_url(self) -> str:
        """生成登录地址 - 固定值"""
        return self.MQTT_DEFAULTS["login_url"]
    
    def _generate_password(self) -> str:
        """生成密码 - 固定值"""
        return self.MQTT_DEFAULTS["password"]
    
    def _generate_coordinate(self, range_val: Tuple[float, float], decimals: int = 6) -> float:
        """生成坐标值"""
        value = random.uniform(range_val[0], range_val[1])
        return round(value, decimals)
    
    def _generate_longitude(self) -> float:
        """生成经度"""
        return self._generate_coordinate(self.LNG_RANGE)
    
    def _generate_latitude(self) -> float:
        """生成纬度"""
        return self._generate_coordinate(self.LAT_RANGE)
    
    def _generate_altitude(self) -> int:
        """生成海拔高度"""
        return random.randint(self.ALT_RANGE[0], self.ALT_RANGE[1])
    
    def _generate_address(self, index: int) -> str:
        """生成安装地址"""
        location = random.choice(self.ADDRESSES)
        return f"测试地址-{index:05d}-{location}"
    
    def _generate_device_status(self) -> str:
        """生成设备状态"""
        rand = random.random()
        cumulative = 0
        for status, prob in self.DEVICE_STATUSES:
            cumulative += prob
            if rand <= cumulative:
                return status
        return "在线"
    
    def _generate_install_date(self) -> str:
        """生成安装日期（过去1年内）"""
        days_ago = random.randint(0, 365)
        install_date = self.current_date - timedelta(days=days_ago)
        return install_date.strftime("%Y-%m-%d")
    
    def _generate_maintenance_cycle(self) -> int:
        """生成维护周期"""
        return random.randint(30, 365)
    
    def _generate_responsible_person(self) -> str:
        """生成负责人"""
        return random.choice(self.RESPONSIBLE_PERSONS)
    
    def _generate_phone(self) -> str:
        """生成联系电话"""
        prefixes = ["138", "139", "137", "136", "135", "150", "151", "152", "157", "158", "159"]
        prefix = random.choice(prefixes)
        suffix = ''.join([str(random.randint(0, 9)) for _ in range(8)])
        return f"{prefix}{suffix}"
    
    def _generate_remark(self) -> str:
        """生成备注"""
        return random.choice(self.REMARKS)
    
    def _ensure_unique(self, generator_func, index: int, used_set: set, max_attempts: int = 100):
        """
        确保生成的值唯一
        
        Args:
            generator_func: 生成函数
            index: 序号
            used_set: 已使用值的集合
            max_attempts: 最大尝试次数
        """
        for _ in range(max_attempts):
            value = generator_func(index)
            if value not in used_set:
                used_set.add(value)
                return value
        # 如果无法生成唯一值，添加随机后缀
        value = f"{generator_func(index)}-{random.randint(1000, 9999)}"
        used_set.add(value)
        return value
    
    def generate_single_record(self, index: int) -> Dict[str, Any]:
        """
        生成单条记录
        
        Args:
            index: 记录序号（从START_INDEX开始）
        """
        # 生成唯一值
        device_name = self._ensure_unique(self._generate_device_name, index, self.used_device_names)
        
        # 生成设备ID和扇区（关联）
        device_id, sector = self._generate_device_id_and_sector(index)
        if device_id not in self.used_device_ids:
            self.used_device_ids.add(device_id)
        
        # 生成坐标并确保唯一（根据开关决定是否生成）
        if self.generate_coordinates:
            lng = self._generate_longitude()
            lat = self._generate_latitude()
            coord_key = (round(lng, 4), round(lat, 4))  # 保留4位小数检查唯一性
            attempts = 0
            while coord_key in self.used_coordinates and attempts < 50:
                lng = self._generate_longitude()
                lat = self._generate_latitude()
                coord_key = (round(lng, 4), round(lat, 4))
                attempts += 1
            self.used_coordinates.add(coord_key)
        else:
            lng = ""
            lat = ""
        
        # 按模板列顺序生成所有字段
        # 先生成所有需要的值
        area_type = self._generate_area_type()
        device_type = self._generate_device_type()
        
        record = {
            # 必填字段（*）
            "device_name": device_name,           # 1. 设备名称
            "device_id": device_id,               # 2. 设备ID
            "sector": sector,                     # 3. 所属扇区（与设备ID关联）
            "area_type": area_type,               # 4. 区域类型
            "device_type": device_type,           # 5. 设备类型
            # 非必填字段
            "function_type": self._generate_function_type(),      # 6. 功能类型
            "manufacturer": self._generate_manufacturer(),        # 7. 厂商
            "model": self._generate_model(),                      # 8. 型号
            "ipv4": self._generate_ipv4(),                        # 9. IPv4
            "ipv6": self._generate_ipv6(),                        # 10. IPv6
            "detection_range": self._generate_detection_range(),  # 11. 探测距离：1~50
            "max_targets": self._generate_max_targets(),          # 12. 最大可探测目标数量：10~200
            "firmware_version": self._generate_firmware_version(), # 13. 固件版本号
            "sn": self._generate_sn(index),                       # 14. 序列号SN：SN2026002101格式
            # 必填字段
            "address": self._generate_address(index),             # 15. 安装地址
            # 非必填字段
            "longitude": lng,                                     # 16. 经度
            "latitude": lat,                                      # 17. 纬度
            "install_height": self._generate_install_height(),    # 18. 安装高度
            "install_datetime": self._generate_install_datetime(), # 19. 安装时间
            "maintenance_unit": self._generate_maintenance_unit(), # 20. 维保单位
            "management_unit": self._generate_management_unit(),   # 21. 管理单位
            "contact_person": self._generate_responsible_person(), # 22. 管理单位联系人
            "contact_phone": self._generate_phone(),              # 23. 管理单位电话
            "scene_image": None,                                  # 24. 实景图
            "protocol": self._generate_protocol(),                # 25. 接入协议
            "connection_type": self._generate_connection_type(),  # 26. 连接类型
            "mqtt_version": self._generate_mqtt_version(),        # 27. MQTT协议版本
            "mqtt_broker": self._generate_mqtt_broker(),          # 28. MQTT代理地址
            "mqtt_port": self._generate_mqtt_port(),              # 29. MQTT代理端口
            "topic_prefix": self._generate_topic_prefix(),        # 30. Topic前缀
            "heartbeat_interval": self._generate_heartbeat_interval(), # 31. 心跳间隔
            "login_url": self._generate_login_url(),              # 32. 登录地址
            "password": self._generate_password(),                # 33. 密码
        }
        
        return record
    
    def generate_all_data(self):
        """生成所有测试数据"""
        print(f"开始生成 {self.count} 条测试数据...")
        
        for i in range(self.count):
            index = self.START_INDEX + i
            record = self.generate_single_record(index)
            self.generated_data.append(record)
            
            if (i + 1) % 10 == 0:
                print(f"  已生成 {i + 1}/{self.count} 条数据")
        
        print(f"✅ 数据生成完成，共 {len(self.generated_data)} 条")
    
    def load_template_structure(self) -> bool:
        """
        从模板文件加载结构
        
        Returns:
            bool: 是否成功加载
        """
        if not os.path.exists(self.template_file):
            print(f"⚠️ 模板文件不存在: {self.template_file}")
            print("将使用默认列结构")
            return False
        
        try:
            wb = load_workbook(self.template_file)
            ws = wb.active
            
            # 读取表头（第一行），去掉*标记
            headers = []
            for col_idx, cell in enumerate(ws[1], 1):
                if cell.value:
                    header = str(cell.value).strip()
                    headers.append(header)
                    # 去掉*标记后存储
                    clean_header = header.replace('*', '')
                    self.column_mapping[clean_header] = col_idx
            
            print(f"从模板加载的列: {headers}")
            wb.close()
            return True
            
        except Exception as e:
            print(f"⚠️ 加载模板失败: {e}")
            return False
    
    def _get_available_output_path(self) -> str:
        """
        获取可用的输出文件路径
        
        如果文件已存在，则自动递增版本号（V0.1 -> V0.2 -> V0.3...）
        """
        base_filename = f"接收机批量测试数据_{self.date_str_full}"
        version = 1
        max_attempts = 100  # 防止无限循环
        
        while version <= max_attempts:
            output_filename = f"{base_filename}_V0.{version}.xlsx"
            output_path = os.path.join(self.output_dir, output_filename)
            
            if not os.path.exists(output_path):
                return output_path
            
            version += 1
        
        # 如果超过最大尝试次数，使用时间戳
        import time
        timestamp = int(time.time())
        output_filename = f"{base_filename}_{timestamp}.xlsx"
        return os.path.join(self.output_dir, output_filename)
    
    def create_excel_file(self):
        """创建Excel文件"""
        # 获取可用的输出路径（自动处理文件已存在的情况）
        output_path = self._get_available_output_path()
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 如果模板存在，复制模板；否则创建新文件
        if os.path.exists(self.template_file):
            shutil.copy(self.template_file, output_path)
            self.wb = load_workbook(output_path)
            self.ws = self.wb.active
            print(f"✅ 基于模板创建文件: {output_path}")
        else:
            self.wb = Workbook()
            self.ws = self.wb.active
            self.ws.title = "接收机数据"
            # 创建默认表头
            self._create_default_headers()
            print(f"✅ 创建新文件: {output_path}")
        
        self.output_path = output_path
    
    def _create_default_headers(self):
        """创建默认表头（按模板顺序）"""
        headers = [
            "设备名称", "设备ID", "所属扇区", "区域类型", "设备类型",
            "功能类型", "厂商", "型号", "IPv4", "IPv6",
            "探测距离", "最大可探测目标数量", "固件版本号", "序列号SN", "安装地址",
            "经度", "纬度", "安装高度", "安装时间", "维保单位",
            "管理单位", "管理单位联系人", "管理单位电话", "实景图", "接入协议",
            "连接类型", "MQTT协议版本", "MQTT代理地址", "MQTT代理端口", "Topic前缀",
            "心跳间隔", "登录地址", "密码"
        ]
        
        for col_idx, header in enumerate(headers, 1):
            cell = self.ws.cell(row=1, column=col_idx)
            cell.value = header
            cell.font = Font(bold=True, size=11)
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # 记录列映射
        for col_idx, header in enumerate(headers, 1):
            self.column_mapping[header] = col_idx
    
    def _get_column_index(self, field_name: str) -> Optional[int]:
        """
        获取字段对应的列索引
        
        支持多种字段名变体（按模板顺序）
        模板中的列名可能带有*标记（必填字段）
        """
        # 直接匹配（去掉*后的列名）
        if field_name in self.column_mapping:
            return self.column_mapping[field_name]
        
        # 模糊匹配 - 按模板33个字段
        field_mapping = {
            # 必填字段（模板中带*）
            "device_name": ["设备名称", "名称", "设备名"],
            "device_id": ["设备ID", "设备编号", "ID", "编号"],
            "sector": ["所属扇区", "扇区"],
            "area_type": ["区域类型"],
            "device_type": ["设备类型"],
            "address": ["安装地址", "地址"],
            # 非必填字段
            "function_type": ["功能类型"],
            "manufacturer": ["厂商"],
            "model": ["型号"],
            "ipv4": ["IPv4"],
            "ipv6": ["IPv6"],
            "detection_range": ["探测距离"],
            "max_targets": ["最大可探测目标数量", "最大探测目标"],
            "firmware_version": ["固件版本号", "固件版本"],
            "sn": ["序列号SN", "序列号", "SN"],
            "longitude": ["经度", "经度(°)", "经度°"],
            "latitude": ["纬度", "纬度(°)", "纬度°"],
            "install_height": ["安装高度", "高度"],
            "install_datetime": ["安装时间", "安装日期"],
            "maintenance_unit": ["维保单位"],
            "management_unit": ["管理单位"],
            "contact_person": ["管理单位联系人", "联系人"],
            "contact_phone": ["管理单位电话", "联系电话", "电话"],
            "scene_image": ["实景图", "图片", "照片"],
            "protocol": ["接入协议", "协议"],
            "connection_type": ["连接类型"],
            "mqtt_version": ["MQTT协议版本"],
            "mqtt_broker": ["MQTT代理地址"],
            "mqtt_port": ["MQTT代理端口"],
            "topic_prefix": ["Topic前缀"],
            "heartbeat_interval": ["心跳间隔"],
            "login_url": ["登录地址"],
            "password": ["密码"]
        }
        
        possible_names = field_mapping.get(field_name, [field_name])
        for name in possible_names:
            if name in self.column_mapping:
                return self.column_mapping[name]
        
        return None
    
    def fill_data_to_excel(self):
        """将生成的数据填充到Excel"""
        if not self.ws:
            raise ValueError("工作表未创建")
        
        # 如果没有列映射，从第一行读取
        if not self.column_mapping:
            for col_idx, cell in enumerate(self.ws[1], 1):
                if cell.value:
                    # 去掉*标记和空白字符
                    header = str(cell.value).strip().replace('*', '')
                    self.column_mapping[header] = col_idx
        
        print("开始填充数据到Excel...")
        
        start_row = 2  # 从第2行开始（第1行是表头）
        
        for idx, record in enumerate(self.generated_data):
            row = start_row + idx
            
            # 按模板顺序填充所有33个字段
            field_mapping = {
                # 必填字段（*）
                "device_name": record["device_name"],
                "device_id": record["device_id"],
                "sector": record["sector"],
                "area_type": record["area_type"],
                "device_type": record["device_type"],
                # 非必填字段
                "function_type": record["function_type"],
                "manufacturer": record["manufacturer"],
                "model": record["model"],
                "ipv4": record["ipv4"],
                "ipv6": record["ipv6"],
                "detection_range": record["detection_range"],
                "max_targets": record["max_targets"],
                "firmware_version": record["firmware_version"],
                "sn": record["sn"],
                "address": record["address"],
                "longitude": record["longitude"],
                "latitude": record["latitude"],
                "install_height": record["install_height"],
                "install_datetime": record["install_datetime"],
                "maintenance_unit": record["maintenance_unit"],
                "management_unit": record["management_unit"],
                "contact_person": record["contact_person"],
                "contact_phone": record["contact_phone"],
                "protocol": record["protocol"],
                "connection_type": record["connection_type"],
                "mqtt_version": record["mqtt_version"],
                "mqtt_broker": record["mqtt_broker"],
                "mqtt_port": record["mqtt_port"],
                "topic_prefix": record["topic_prefix"],
                "heartbeat_interval": record["heartbeat_interval"],
                "login_url": record["login_url"],
                "password": record["password"]
            }
            
            for field_name, value in field_mapping.items():
                col = self._get_column_index(field_name)
                if col:
                    cell = self.ws.cell(row=row, column=col)
                    cell.value = value
                    cell.alignment = Alignment(vertical="center")
            
            # 处理实景图（仅在开启图片插入时处理）
            if self.insert_scene_image and self.scene_images:
                self._fill_scene_image(row, idx)
            
            if (idx + 1) % 10 == 0:
                print(f"  已填充 {idx + 1}/{len(self.generated_data)} 行")
        
        # 显示图片插入情况
        if self.insert_scene_image and self.scene_images:
            # openpyxl 3.0+ 使用 _images，旧版本使用 _charts 或其他属性
            image_count = 0
            if hasattr(self.ws, '_images'):
                image_count = len(self.ws._images)
            elif hasattr(self.ws, 'images'):
                image_count = len(self.ws.images)
            print(f"✅ 数据填充完成，共插入 {image_count} 张图片")
        else:
            print(f"✅ 数据填充完成（无实景图）")
    
    def load_scene_images(self) -> bool:
        """
        从配置路径加载实景图
        
        读取路径下的 jpg/png 图片文件
        
        Returns:
            bool: 是否成功加载图片
        """
        print(f"🔍 正在查找实景图，路径: {self.scene_image_path}")
        
        if not os.path.exists(self.scene_image_path):
            print(f"⚠️ 实景图路径不存在: {self.scene_image_path}")
            return False
        
        try:
            # 支持的图片格式
            supported_extensions = ('.jpg', '.jpeg', '.png')
            
            # 遍历目录查找图片
            self.scene_images = []
            all_files = os.listdir(self.scene_image_path)
            print(f"   目录中共有 {len(all_files)} 个文件/文件夹")
            
            for filename in all_files:
                if filename.lower().endswith(supported_extensions):
                    full_path = os.path.join(self.scene_image_path, filename)
                    if os.path.isfile(full_path):
                        self.scene_images.append(full_path)
                        print(f"   ✓ 找到图片: {filename}")
            
            if self.scene_images:
                print(f"✅ 共找到 {len(self.scene_images)} 张实景图")
                return True
            else:
                print(f"⚠️ 在 {self.scene_image_path} 中未找到 jpg/png 图片")
                return False
                
        except Exception as e:
            print(f"⚠️ 加载实景图失败: {e}")
            return False
    
    def _fill_scene_image(self, row: int, data_index: int):
        """
        填充实景图到Excel单元格
        
        随机选择1-3张图片插入到单元格中，调整图片大小适配行高
        """
        col = self._get_column_index("scene_image")
        if not col:
            print(f"   行{row}: 未找到实景图列")
            return
        
        # 如果没有图片，留空
        if not self.scene_images:
            print(f"   行{row}: 无可用图片")
            return
        
        try:
            # 随机选择1-3张图片
            num_images = random.randint(1, min(3, len(self.scene_images)))
            selected_images = random.sample(self.scene_images, num_images)
            print(f"   行{row}: 准备插入 {num_images} 张图片")
            
            # 设置行高以容纳图片（每张图片约60像素高度）
            self.ws.row_dimensions[row].height = 60 * num_images
            
            # 插入图片
            for idx, img_path in enumerate(selected_images):
                try:
                    # 直接插入原图，但调整显示大小以适应行高
                    xl_img = XLImage(img_path)
                    
                    # 获取原图尺寸（用于计算显示比例）
                    if HAS_PIL:
                        pil_img = PILImage.open(img_path)
                        orig_width, orig_height = pil_img.size
                    else:
                        # 没有PIL时使用默认尺寸
                        orig_width, orig_height = 200, 150
                    
                    # 设置图片锚点
                    col_letter = get_column_letter(col)
                    xl_img.anchor = f'{col_letter}{row}'
                    
                    # 计算显示尺寸：根据行高调整，保持原图比例
                    # 行高单位是点（1点 ≈ 1.33像素），设置行高为60像素约等于45点
                    target_height = 60  # 每张图片目标显示高度（像素）
                    
                    # 按高度比例缩放
                    if orig_height > target_height:
                        scale_ratio = target_height / orig_height
                        display_width = int(orig_width * scale_ratio)
                        display_height = target_height
                    else:
                        # 原图高度小于目标高度，按原图显示
                        display_width = orig_width
                        display_height = orig_height
                    
                    # 限制最大宽度（避免太宽）
                    max_display_width = 200
                    if display_width > max_display_width:
                        scale_ratio = max_display_width / display_width
                        display_width = max_display_width
                        display_height = int(display_height * scale_ratio)
                    
                    # 设置显示尺寸（只影响显示，不改变原图文件）
                    xl_img.width = display_width
                    xl_img.height = display_height
                    
                    # 添加到工作表
                    self.ws.add_image(xl_img)
                    print(f"     ✓ 已插入: {os.path.basename(img_path)} ({display_width}x{display_height})")
                        
                except Exception as e:
                    print(f"⚠️ 插入图片失败 {img_path}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                    
        except Exception as e:
            print(f"⚠️ 填充实景图失败: {e}")
            import traceback
            traceback.print_exc()
    
    def adjust_column_widths(self):
        """调整列宽（保持与模板一致）"""
        # 按模板33个字段设置列宽
        default_widths = {
            "设备名称": 18,
            "设备ID": 15,
            "所属扇区": 18,
            "区域类型": 15,
            "设备类型": 15,
            "功能类型": 15,
            "厂商": 12,
            "型号": 15,
            "IPv4": 15,
            "IPv6": 25,
            "探测距离": 12,
            "最大可探测目标数量": 18,
            "固件版本号": 15,
            "序列号SN": 15,
            "安装地址": 30,
            "经度": 12,
            "纬度": 12,
            "安装高度": 12,
            "安装时间": 20,
            "维保单位": 15,
            "管理单位": 15,
            "管理单位联系人": 15,
            "管理单位电话": 15,
            "实景图": 15,
            "接入协议": 12,
            "连接类型": 12,
            "MQTT协议版本": 15,
            "MQTT代理地址": 20,
            "MQTT代理端口": 15,
            "Topic前缀": 15,
            "心跳间隔": 12,
            "登录地址": 25,
            "密码": 20
        }
        
        for header, width in default_widths.items():
            col = self._get_column_index(header)
            if col:
                col_letter = get_column_letter(col)
                self.ws.column_dimensions[col_letter].width = width
        
        print("✅ 列宽调整完成")
    
    def save_file(self):
        """保存Excel文件"""
        try:
            self.wb.save(self.output_path)
            print(f"✅ 文件已保存: {self.output_path}")
            return self.output_path
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
            raise
    
    def run(self):
        """执行完整生成流程"""
        print("=" * 60)
        print("接收机批量测试数据生成工具")
        print("=" * 60)
        
        # 打印路径信息
        print(f"📁 脚本目录: {self.script_dir}")
        print(f"📄 模板文件: {self.template_file}")
        print(f"📂 输出目录: {self.output_dir}")
        print(f"🖼️  实景图路径: {self.scene_image_path}")
        print(f"🔘 图片插入开关: {'开启' if self.insert_scene_image else '关闭'}")
        print(f"📍 经纬度生成开关: {'开启' if self.generate_coordinates else '关闭'}")
        print("-" * 60)
        
        # 验证输出目录是否存在
        if not os.path.exists(self.output_dir):
            print(f"⚠️  输出目录不存在，将尝试创建: {self.output_dir}")
        
        # 1. 加载模板结构
        self.load_template_structure()
        
        # 2. 加载实景图（仅在开启图片插入时加载）
        if self.insert_scene_image:
            self.load_scene_images()
        else:
            print("⏭️  跳过实景图加载（图片插入已关闭）")
        
        # 3. 生成数据
        self.generate_all_data()
        
        # 4. 创建Excel文件
        self.create_excel_file()
        
        # 5. 填充数据
        self.fill_data_to_excel()
        
        # 6. 调整列宽
        self.adjust_column_widths()
        
        # 7. 保存文件
        output_path = self.save_file()
        
        print("=" * 60)
        print("生成完成！")
        print(f"输出文件: {output_path}")
        print(f"生成数量: {self.count} 条")
        print("=" * 60)
        
        return output_path


def main():
    """主函数"""
    # 支持多种方式指定生成数量（优先级：命令行参数 > 环境变量 > 默认值）
    # 默认生成数量由 DEFAULT_GENERATION_COUNT 常量定义，可通过以下方式修改：
    # 1. 修改文件顶部的 DEFAULT_GENERATION_COUNT 常量
    # 2. 命令行参数: python 接收机批量测试数据制造.py 5000
    # 3. 环境变量: set RECEIVER_DATA_COUNT=10000
    
    # 动态获取默认数量（与__init__保持一致）
    default_count = int(os.environ.get("RECEIVER_DATA_COUNT", DEFAULT_GENERATION_COUNT))
    count = default_count
    
    # 从命令行参数读取
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
            if count <= 0:
                print(f"警告: 参数必须为正整数，使用默认值 {default_count}")
                count = default_count
            elif count > 50000:
                print(f"警告: 生成数量过大({count})，建议分批生成")
        except ValueError:
            print(f"警告: 无效的参数 '{sys.argv[1]}'，使用默认值 {default_count}")
            count = default_count
    
    print(f"📊 计划生成数据条数: {count}")
    print(f"   (可通过命令行参数修改，如: python 接收机批量测试数据制造.py 5000)")
    print()
    
    generator = ReceiverDataGenerator(count=count)
    
    try:
        output_path = generator.run()
        print(f"\n🎉 成功生成测试数据文件: {output_path}")
    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
