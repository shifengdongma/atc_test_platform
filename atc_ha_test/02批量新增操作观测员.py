# -*- coding: utf-8 -*-
"""
批量新增操作观测员（操控员）
支持自定义数量、接口地址，调用达梦数据库进行重复性验证
"""
import os
import sys
import random
import requests
import urllib3
import time
from datetime import datetime, timedelta

# 抑制 SSL 证书验证警告（内部环境使用自签名证书）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 全局配置区域（按需修改）====================
# 接口基础地址
#BASE_URL = "https://dkkgsit-test.testdolphin.com"
BASE_URL = "https://10.165.26.246/"  # dev环境
# 新增操控员接口路径
API_PATH = "/la-atc-biz-backend/operationPeople"
# JWT Token 动态获取（从 ha_Jwt_Token_get.py 导入，支持缓存复用）
from ha_Jwt_Token_get import get_jwt_token
JWT_TOKEN = get_jwt_token(base_url=BASE_URL.rstrip("/"))
# 批量生成数量
GENERATE_COUNT = 5
# 是否进行数据库重复性验证
ENABLE_DB_CHECK = True
# 仅测试模式：True=只打印生成的数据，不执行接口提交；False=正常提交
DRY_RUN = False
# 请求间隔（秒），防止请求过快
REQUEST_INTERVAL = 0.5
# 接口超时时间（秒）
REQUEST_TIMEOUT = 30
# 操控员执照图片默认URL（若无需上传文件，可配置一个有效图片地址）
DEFAULT_LICENSE_IMAGE_URL = ""
# 操控员执照图片文件路径（如需自动上传，请填写本地图片路径，如 "./license.jpg"）
LICENSE_IMAGE_PATH = ""
# 文件上传接口路径（批量）
UPLOAD_PATH_BATCH = "/la-atc-biz-backend/file/upload/batch"
# 文件上传接口路径（单文件）
UPLOAD_PATH_SINGLE = "/la-atc-biz-backend/file/upload"
# ================================================================

# 目录配置（当前脚本位于 script/ 目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 导入 dm_ha_client（当前目录下已包含双集群配置）
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from dm_ha_client import DmDbClient, DB_CONFIG_A, DB_CONFIG_B
except ImportError as e:
    print(f"[警告] 导入 dm_ha_client 失败: {e}")
    DmDbClient = None
    DB_CONFIG_A = None
    DB_CONFIG_B = None

# 导入集群主节点查询（用于动态选择数据库）
try:
    from cluster_master_query import get_cluster_info
except ImportError as e:
    print(f"[警告] 导入 cluster_master_query 失败: {e}")
    def get_cluster_info():
        return "未知集群"


def get_current_cluster_db_config():
    """根据当前主集群返回对应的数据库配置
    A集群 -> B集群数据库(205), B集群 -> A集群数据库(212)
    """
    cluster = get_cluster_info()
    print(f"[集群] 当前主集群: {cluster}")
    if cluster == "集群A":
        print("[集群] 使用 B集群数据库配置 (205)")
        return DB_CONFIG_B
    elif cluster == "集群B":
        print("[集群] 使用 A集群数据库配置 (212)")
        return DB_CONFIG_A
    else:
        print("[警告] 无法识别当前集群，默认使用 A集群数据库配置 (212)")
        return DB_CONFIG_A


# ==================== 数据字典 ====================
# 【DDL 字段类型与接口字段映射说明】
# DDL 字段名                  DDL 类型              接口字段名                  接口类型    必填    说明
# -------------------------- -------------------- -------------------------- ---------- ------ ------------------------
# ID                         BIGINT NOT NULL      -                          -          系统    主键，接口不提交
# CREATED_BY                 NVARCHAR(255)        -                          -          系统    创建人，接口不提交
# CREATED_TIME               datetime(6)          -                          -          系统    创建时间，接口不提交
# UPDATED_BY                 NVARCHAR(255)        -                          -          系统    更新人，接口不提交
# UPDATED_TIME               datetime(6)          -                          -          系统    更新时间，接口不提交
# VERSION                    BIGINT DEFAULT '1'   -                          -          系统    版本号，接口不提交
# name                       NVARCHAR(20)         name                       string     是      姓名
# identify_type_code         varchar(50)          identifyTypeCode           string     是      证件类型代码
# identify_number            varchar(50)          identifyNumber             string     是      证件号码
# type                       varchar(20)          type                       string     是      类别(1=操控员,2=观测员)
# civil_uav_license_no       NVARCHAR(100)        civilUavLicenseNo          string     是      民用无人机执照编号
# operation_organization_id  BIGINT               operationOrganizationId    integer    是      归属企业ID
# address                    NVARCHAR(100)        address                    string     是      常住地址
# contact_phone              varchar(50)          contactPhone               string     是      联系电话
# data_code                  NVARCHAR(50)         -                          -          否      数据编码，接口不提交
# is_deleted                 BIT                  -                          -          否      是否删除，接口不提交
# operator_license_validity  DATE                 operatorLicenseValidity    string     是      失效日期(yyyyMMdd)
# operator_license_image     NVARCHAR(500)        operatorLicenseImage       string     是      操控员执照图片URL
# license_type_code          NVARCHAR(50)         licenseTypeCode            string     是      执照类型编码
# violation_record           INT DEFAULT 0        violationRecord            integer    是      违法违规记录
# category_level             NVARCHAR(50)         categoryLevel              string     是      类别等级
# license_category           NVARCHAR(50)         licenseCategory            string     是      执照种类
# level_grade                NVARCHAR(50)         levelGrade                 string     是      级别等级
# beyond_visual_range_grade  NVARCHAR(50)         beyondVisualRangeGrade     string     是      超视距等级
# instructor_grade           NVARCHAR(50)         instructorGrade            string     是      教员等级
# rbac_user_id               NVARCHAR(100)        -                          -          否      RBAC用户ID，接口不提交
# operation_organization_name NVARCHAR(255)       operationOrganizationName  string     是      归属企业名称
# operation_organization_code NVARCHAR(50)         operationOrganizationCode  string     是      归属企业代码
# unified_social_credit_code NVARCHAR(50)         unifiedSocialCreditCode    string     是      归属单位统一社会信用代码
# email                      NVARCHAR(255)        email                      string     是      电子邮箱
# issuance_date              DATE                 issuanceDate               string     是      签发日期(yyyyMMdd)
# org_id                     BIGINT               orgId                      string     是      运营单位ID(与operationOrganizationId一致)
# user_id                    BIGINT               userId                     string     是      用户ID
# ==================== 数据字典 ====================

# 中国常见姓氏
SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "高",
    "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "邓", "曹",
    "彭", "曾", "肖", "田", "董", "袁", "潘", "于", "蒋", "蔡",
    "余", "杜", "叶", "程", "苏", "魏", "吕", "丁", "任", "沈"
]

# 名字常用字
NAME_CHARS = [
    "伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋",
    "勇", "艳", "杰", "娟", "涛", "明", "超", "秀", "霞", "平",
    "刚", "桂", "英", "华", "建", "文", "辉", "玲", "婷", "宇",
    "博", "浩", "然", "昊", "轩", "睿", "梓", "涵", "雨", "欣",
    "诗", "琪", "佳", "怡", "梦", "思", "语", "晨", "曦", "瑶"
]

# 常住地址前缀
ADDRESS_PREFIXES = [
    "江苏省苏州市", "江苏省南京市", "江苏省无锡市", "浙江省杭州市", "浙江省宁波市",
    "上海市", "北京市", "广东省深圳市", "广东省广州市", "四川省成都市",
    "湖北省武汉市", "陕西省西安市", "湖南省长沙市", "山东省青岛市", "福建省厦门市"
]

# 街道地址
STREET_ADDRESSES = [
    "科技园路88号", "人民中路126号", "软件大道66号", "太湖大道999号",
    "金鸡湖大道168号", "长江路555号", "解放路77号", "建设大街33号",
    "和平东路66号", "友谊路198号", "中山北路200号", "青年路123号"
]

# 证件类型字典（默认值，数据库查询失败时使用）
# identify_type_code 规则：0=身份证, 1=护照, 2=军官证, 3=港澳居民来往内地通行证, 4=台湾居民来往大陆通行证
#                       5=外国人永久居留身份证, 6=港澳居民居住证, 7=台湾居民居住证, 8=其他, 9=组织机构代码证
IDENTIFY_TYPES = [
    {"code": "0", "name": "身份证"},
    {"code": "1", "name": "护照"},
    {"code": "2", "name": "军官证"},
    {"code": "3", "name": "港澳居民来往内地通行证"},
    {"code": "4", "name": "台湾居民来往大陆通行证"},
    {"code": "5", "name": "外国人永久居留身份证"},
    {"code": "6", "name": "港澳居民居住证"},
    {"code": "7", "name": "台湾居民居住证"},
    {"code": "8", "name": "其他"},
    {"code": "9", "name": "组织机构代码证"},
]

# 操控员类别（type字段）：1=操控员, 2=观测员
OPERATOR_TYPES = ["1", "2"]

# 执照类型字典（默认值，数据库查询失败时使用）
LICENSE_TYPES = [
    {"code": "01", "name": "多旋翼"},
    {"code": "02", "name": "固定翼"},
    {"code": "03", "name": "直升机"},
    {"code": "04", "name": "垂起固定翼"},
]

# 类别等级（对应接口字段 categoryLevel，1~8 分别对应以下类别）
# 1=飞机, 2=垂直起降飞机, 3=旋翼机, 4=倾转旋翼机, 5=飞艇, 6=自由气球, 7=滑翔机, 8=特殊类
CATEGORY_LEVELS = [1, 2, 3, 4, 5, 6, 7, 8]

# 执照种类（对应接口字段 licenseCategory）
# 说明：执照种类映射到规范编码，小型/中型统一为 RPL_M，大型为 RPL_L
#   小型无人机操作员执照 -> RPL_M
#   中型无人机操作员执照 -> RPL_M
#   大型无人机操作员执照 -> RPL_L
LICENSE_CATEGORIES = [
    {"name": "小型无人机操作员执照", "code": "RPL_M"},
    {"name": "中型无人机操作员执照", "code": "RPL_M"},
    {"name": "大型无人机操作员执照", "code": "RPL_L"},
]

# 等级级别（对应接口字段 levelGrade，1~4 分别对应以下等级）
# 1=旋翼机--多旋翼, 2=旋翼机--自传多旋翼, 3=旋翼机--直升机, 4=特殊类
LEVEL_GRADES = [1, 2, 3, 4]

# 超视距等级（对应接口字段 beyondVisualRangeGrade，1~7 分别对应以下等级）
# 1=超视距-飞机, 2=超视距-直起降飞机, 3=超视距-多旋翼, 4=超视距-自转旋翼机, 5=超视距-直升机, 6=超视距-倾转旋翼机, 7=超视距-飞艇
BVLOS_GRADES = [1, 2, 3, 4, 5, 6, 7]

# 教员等级（对应接口字段 instructorGrade，1~7）
INSTRUCTOR_GRADES = [1, 2, 3, 4, 5, 6, 7]

# 证件类型 code -> name 映射（用于数据库查询结果补充名称）
IDENTIFY_TYPE_NAME_MAP = {
    "0": "身份证",
    "1": "护照",
    "2": "军官证",
    "3": "港澳居民来往内地通行证",
    "4": "台湾居民来往大陆通行证",
    "5": "外国人永久居留身份证",
    "6": "港澳居民居住证",
    "7": "台湾居民居住证",
    "8": "其他",
    "9": "组织机构代码证",
}

def get_identify_type_name(code):
    """根据证件类型编码获取名称"""
    return IDENTIFY_TYPE_NAME_MAP.get(str(code), "身份证")


# 身份证号权重因子
ID_CARD_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
ID_CARD_CHECKS = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']

# 行政区划代码（用于身份证号前6位）
ID_AREA_CODES = [
    "320500", "320100", "320200", "330100", "330200", "310000", "110000",
    "440300", "440100", "510100", "420100", "610100", "430100", "370200", "350200"
]


def generate_id_card():
    """生成18位身份证号码（符合GB 11643-1999规范）"""
    # 前6位：地址码
    area_code = random.choice(ID_AREA_CODES)
    # 第7-14位：出生日期码（18-55岁之间）
    birth_date = datetime.now() - timedelta(days=random.randint(18*365, 55*365))
    birth_str = birth_date.strftime("%Y%m%d")
    # 第15-17位：顺序码（3位数字）
    seq = random.randint(1, 999)
    seq_str = f"{seq:03d}"
    # 前17位
    code17 = area_code + birth_str + seq_str
    # 计算第18位校验码
    total = 0
    for i, ch in enumerate(code17):
        total += int(ch) * ID_CARD_WEIGHTS[i]
    check = ID_CARD_CHECKS[total % 11]
    return code17 + check


def generate_name():
    """生成中文姓名（2-3个字）"""
    surname = random.choice(SURNAMES)
    length = random.choice([2, 2, 3])
    given_name = "".join(random.choice(NAME_CHARS) for _ in range(length - 1))
    return surname + given_name


def generate_phone():
    """生成中国手机号"""
    prefixes = [
        "130", "131", "132", "133", "134", "135", "136", "137", "138", "139",
        "150", "151", "152", "153", "155", "156", "157", "158", "159",
        "180", "181", "182", "183", "184", "185", "186", "187", "188", "189",
        "191", "198", "199", "166"
    ]
    prefix = random.choice(prefixes)
    suffix = "".join(random.choice("0123456789") for _ in range(8))
    return prefix + suffix


def generate_email(name):
    """根据姓名生成邮箱"""
    domains = ["163.com", "qq.com", "126.com", "sina.com", "gmail.com", "outlook.com"]
    prefix = "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8))
    return f"{prefix}@{random.choice(domains)}"


def generate_address():
    """生成常住地址"""
    prefix = random.choice(ADDRESS_PREFIXES)
    street = random.choice(STREET_ADDRESSES)
    return f"{prefix}{street}"


def generate_civil_uav_license_no():
    """生成民用无人机执照编号"""
    # 格式：UAS-XXXX-XXXXX
    year = random.randint(2020, 2026)
    seq = random.randint(10000, 99999)
    return f"UAS-{year}-{seq}"


def upload_license_image(file_path=None):
    """上传操控员执照图片，返回图片URL"""
    # 如果配置了默认URL，直接返回
    if DEFAULT_LICENSE_IMAGE_URL:
        return DEFAULT_LICENSE_IMAGE_URL

    # 如果没有指定文件路径，返回空（由调用方处理）
    if not file_path or not os.path.exists(file_path):
        return ""

    url_batch = f"{BASE_URL}{UPLOAD_PATH_BATCH}"
    url_single = f"{BASE_URL}{UPLOAD_PATH_SINGLE}"
    headers = {}
    if JWT_TOKEN:
        headers["jwt-token"] = JWT_TOKEN

    # 先尝试批量上传接口
    try:
        with open(file_path, "rb") as f:
            files = {"files": (os.path.basename(file_path), f, "image/jpeg")}
            resp = requests.post(url_batch, headers=headers, files=files, timeout=REQUEST_TIMEOUT, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "200" or data.get("status") == 200:
                result = data.get("result", [])
                if result and len(result) > 0:
                    img_url = result[0].get("url", "")
                    if img_url and not img_url.startswith("http"):
                        img_url = f"{BASE_URL}{img_url}"
                    print(f"[上传] 执照图片上传成功: {img_url}")
                    return img_url
    except Exception as e:
        print(f"[上传] 批量上传失败: {e}")

    # 批量失败，回退单文件上传
    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "image/jpeg")}
            resp = requests.post(url_single, headers=headers, files=files, timeout=REQUEST_TIMEOUT, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "200" or data.get("status") == 200:
                result = data.get("result", {})
                img_url = result.get("url", "") if isinstance(result, dict) else ""
                if img_url and not img_url.startswith("http"):
                    img_url = f"{BASE_URL}{img_url}"
                print(f"[上传] 执照图片上传成功(单文件): {img_url}")
                return img_url
    except Exception as e:
        print(f"[上传] 单文件上传失败: {e}")

    return ""


def generate_date_str(start_year=2020, end_year=2026):
    """生成 yyyyMMdd 格式日期字符串"""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    days = (end - start).days
    date = start + timedelta(days=random.randint(0, days))
    return date.strftime("%Y%m%d")


def fetch_existing_people():
    """从达梦数据库查询已有的操控员（用于重复性验证）"""
    if not ENABLE_DB_CHECK or DmDbClient is None:
        return set(), set(), []
    db_config = get_current_cluster_db_config()
    if db_config is None:
        print("[DB] 无可用数据库配置，跳过数据库查询")
        return set(), set(), []
    client = DmDbClient(**db_config)
    names = set()
    id_numbers = set()
    identify_types = []
    try:
        client.connect()
        result = client.query(
            table_name="operation_people",
            columns=["name", "identify_number", "identify_type_code"]
        )
        type_map = {}
        for row in result:
            name = row.get("name")
            id_num = row.get("identify_number")
            type_code = row.get("identify_type_code")
            if name:
                names.add(name)
            if id_num:
                id_numbers.add(id_num)
            # 收集数据库中真实的证件类型编码
            if type_code and type_code not in type_map:
                type_map[type_code] = True
                identify_types.append({"code": type_code, "name": get_identify_type_name(type_code)})
        print(f"[DB] 从数据库获取到 {len(names)} 条姓名，{len(id_numbers)} 条证件号，{len(identify_types)} 种证件类型")
        if identify_types:
            print(f"[DB] 系统真实证件类型: {identify_types}")
    except Exception as e:
        print(f"[DB] 查询 operation_people 表失败: {e}")
    finally:
        client.close()
    return names, id_numbers, identify_types


def fetch_organizations():
    """从达梦数据库查询运营单位（用于归属单位关联）"""
    if not ENABLE_DB_CHECK or DmDbClient is None:
        return []
    db_config = get_current_cluster_db_config()
    if db_config is None:
        print("[DB] 无可用数据库配置，跳过数据库查询")
        return []
    client = DmDbClient(**db_config)
    orgs = []
    try:
        client.connect()
        result = client.query(
            table_name="operation_organization",
            columns=["id", "organization_name", "unified_social_credit_code"]
        )
        for row in result:
            org_id = row.get("id")
            org_name = row.get("organization_name")
            org_code = row.get("unified_social_credit_code")
            if org_id and org_name and org_code:
                orgs.append({
                    "id": org_id,
                    "name": org_name,
                    "unifiedSocialCreditCode": org_code
                })
        print(f"[DB] 从数据库获取到 {len(orgs)} 条运营单位信息用于归属单位关联")
    except Exception as e:
        print(f"[DB] 查询 operation_organization 表失败: {e}")
    finally:
        client.close()
    return orgs


def create_operator(operator_data):
    """调用接口新增操控员"""
    url = f"{BASE_URL}{API_PATH}"
    headers = {
        "Content-Type": "application/json"
    }
    if JWT_TOKEN:
        headers["jwt-token"] = JWT_TOKEN
    try:
        resp = requests.post(url, headers=headers, json=operator_data, timeout=REQUEST_TIMEOUT, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "200" or data.get("status") == 200:
                print(f"[成功] 新增操控员: {operator_data['name']} (ID: {data.get('result')})")
                return True, data
            else:
                print(f"[失败] {operator_data['name']}: 接口返回 code={data.get('code')}, msg={data}")
                return False, data
        else:
            print(f"[失败] {operator_data['name']}: HTTP {resp.status_code}, {resp.text[:200]}")
            return False, resp.text
    except Exception as e:
        print(f"[失败] {operator_data['name']}: 请求异常 {e}")
        return False, str(e)


def generate_unique_operator(existing_names, existing_id_numbers, organizations, license_image_url=""):
    """生成不重复的操控员数据"""
    max_retry = 100
    for _ in range(max_retry):
        name = generate_name()
        id_card = generate_id_card()
        if name not in existing_names and id_card not in existing_id_numbers:
            # 随机选择一个归属单位
            org = random.choice(organizations) if organizations else {
                "id": random.randint(1, 1000),
                "name": "苏州科达科技有限公司",
                "unifiedSocialCreditCode": "91320500" + "".join(random.choice("0123456789") for _ in range(9)) + random.choice("ABCDEFGHJKLMNPQRTUWXY")
            }
            # 证件类型：身份证 98%，其他类型合计 2%
            if random.random() < 0.98:
                id_type = next(t for t in IDENTIFY_TYPES if t["code"] == "0")
            else:
                other_types = [t for t in IDENTIFY_TYPES if t["code"] != "0"]
                id_type = random.choice(other_types)
            # 执照类型
            license_type = random.choice(LICENSE_TYPES)
            # 签发日期和失效日期（失效日期至少在当前日期一年后）
            issuance = generate_date_str(2020, 2024)
            current_year = datetime.now().year
            validity = generate_date_str(current_year + 1, current_year + 5)
            # 类别：1=操控员(95%), 2=观测员(5%)
            op_type = random.choices(OPERATOR_TYPES, weights=[95, 5])[0]
            # 执照种类决定是否需要教员等级
            license_category_info = random.choice(LICENSE_CATEGORIES)
            license_category = license_category_info["code"]
            # 教员等级（1~7）
            instructor = random.choice(INSTRUCTOR_GRADES)

            return {
                "name": name,
                "orgId": str(org["id"]),
                "userId": str(random.randint(1000000000000000, 9999999999999999)),
                "unifiedSocialCreditCode": org["unifiedSocialCreditCode"],
                "email": generate_email(name),
                "issuanceDate": issuance,
                "identifyTypeCode": id_type["code"],
                "identifyNumber": id_card,
                "type": op_type,
                "civilUavLicenseNo": generate_civil_uav_license_no(),
                "operationOrganizationId": int(org["id"]),
                "operationOrganizationName": org["name"],
                "operationOrganizationCode": org["unifiedSocialCreditCode"],
                "address": generate_address(),
                "contactPhone": generate_phone(),
                "operatorLicenseValidity": validity,
                "operatorLicenseImage": None,
                "licenseTypeCode": None,
                "violationRecord": "",
                "categoryLevel": random.choice(CATEGORY_LEVELS),
                "licenseCategory": license_category,
                "levelGrade": random.choice(LEVEL_GRADES),
                "beyondVisualRangeGrade": random.choice(BVLOS_GRADES),
                "instructorGrade": instructor,
                "isDeleted": 0,
            }
    raise RuntimeError("无法生成不重复的数据，请检查数据库中是否已有大量数据")


def main():
    print("=" * 60)
    print("批量新增操作观测员（操控员）")
    print("=" * 60)
    print(f"目标接口: {BASE_URL}{API_PATH}")
    print(f"生成数量: {GENERATE_COUNT}")
    print(f"数据库重复性验证: {'开启' if ENABLE_DB_CHECK else '关闭'}")
    print(f"仅测试模式(不提交): {'开启' if DRY_RUN else '关闭'}")
    print("=" * 60)

    if not JWT_TOKEN:
        print("[警告] JWT_TOKEN 为空，可能导致接口鉴权失败，请在配置区域填入有效的 jwt-token")

    # 1. 获取数据库中已有操控员数据（用于重复性验证）
    existing_names, existing_id_numbers, db_identify_types = fetch_existing_people()

    # 优先使用数据库中真实的证件类型
    if db_identify_types:
        global IDENTIFY_TYPES
        IDENTIFY_TYPES = db_identify_types
        print(f"[配置] 使用数据库真实证件类型生成数据")
    else:
        print(f"[配置] 数据库无证件类型数据，使用默认类型字典: {IDENTIFY_TYPES}")

    # 2. 获取运营单位数据（用于归属单位关联）
    organizations = fetch_organizations()
    if not organizations:
        print("[警告] 未从数据库获取到运营单位数据，将使用默认模拟数据")
        # 创建默认模拟单位
        organizations = [
            {"id": 1, "name": "苏州科达科技有限公司", "unifiedSocialCreditCode": "913205001234567890A"},
            {"id": 2, "name": "南京无人机研究院", "unifiedSocialCreditCode": "913201001234567890B"},
        ]

    # 3. 预上传执照图片（如需）
    license_image_url = ""
    if LICENSE_IMAGE_PATH and os.path.exists(LICENSE_IMAGE_PATH):
        print(f"[上传] 正在上传执照图片: {LICENSE_IMAGE_PATH}")
        license_image_url = upload_license_image(LICENSE_IMAGE_PATH)
        if license_image_url:
            print(f"[上传] 图片URL: {license_image_url}")
        else:
            print("[警告] 执照图片上传失败，operatorLicenseImage 将使用空字符串")
    elif DEFAULT_LICENSE_IMAGE_URL:
        license_image_url = DEFAULT_LICENSE_IMAGE_URL
        print(f"[配置] 使用默认执照图片URL: {license_image_url}")
    else:
        print("[提示] 未配置执照图片，operatorLicenseImage 将为空字符串（接口可能校验失败）")

    # 4. 批量生成并提交
    success_count = 0
    fail_count = 0
    generated_names = set()
    generated_id_numbers = set()

    for i in range(GENERATE_COUNT):
        print(f"\n[{i + 1}/{GENERATE_COUNT}] 正在生成...")
        try:
            operator_data = generate_unique_operator(
                existing_names | generated_names,
                existing_id_numbers | generated_id_numbers,
                organizations,
                license_image_url
            )
            print(f"[生成] 姓名: {operator_data['name']}, 证件号: {operator_data['identifyNumber']}, 归属单位: {operator_data['operationOrganizationName']}")

            if DRY_RUN:
                print(f"[测试模式] 数据预览: {operator_data}")
                success_count += 1
                generated_names.add(operator_data["name"])
                generated_id_numbers.add(operator_data["identifyNumber"])
                continue

            success, result = create_operator(operator_data)
            if success:
                success_count += 1
                generated_names.add(operator_data["name"])
                generated_id_numbers.add(operator_data["identifyNumber"])
            else:
                fail_count += 1

            if i < GENERATE_COUNT - 1:
                time.sleep(REQUEST_INTERVAL)
        except RuntimeError as e:
            print(f"[错误] {e}")
            break
        except Exception as e:
            print(f"[错误] 第 {i + 1} 条数据处理异常: {e}")
            fail_count += 1

    print("\n" + "=" * 60)
    print("执行完成")
    print(f"成功: {success_count} 条")
    print(f"失败: {fail_count} 条")
    print("=" * 60)


if __name__ == "__main__":
    main()
