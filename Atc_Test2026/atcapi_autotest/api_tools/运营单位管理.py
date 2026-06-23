# -*- coding: utf-8 -*-
"""
批量新增运营单位
支持自定义数量、接口地址，调用达梦数据库进行重复性验证
"""
import os
import sys
import random
import string
import requests
import time

# ==================== 路径处理 ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from env import BASE_URL
from api_tools.Jwt_Token_get import get_jwt_token

JWT_TOKEN = get_jwt_token()
# =================================================

# ==================== 全局配置区域（按需修改）====================
# 接口基础地址（已从 env.py 自动导入）
# BASE_URL = "https://dkkgsit-test.testdolphin.com" #Test环境
# BASE_URL = "https://dkkgdev.devdolphin.com/"
# 新增运营企业接口路径
API_PATH = "/la-atc-biz-backend/operationOrganization"
# 文件上传接口路径（优先批量上传，失败自动回退单文件上传）
UPLOAD_PATH_BATCH = "/la-atc-biz-backend/file/upload/batch"
UPLOAD_PATH_SINGLE = "/la-atc-biz-backend/file/upload"
# JWT Token（已自动获取，如需指定账号可调用 get_jwt_token() 传参）
# JWT_TOKEN = "..."
# 批量生成数量
GENERATE_COUNT = 100
# 经营许可证图片路径（相对于数据目录 test_data）
LICENSE_IMAGE = "经营许可证.jpg"
# 是否先上传经营许可证获取 URL（True=自动上传，False=使用下方手动配置的URL）
AUTO_UPLOAD_LICENSE = True
# 手动指定文件附件URL（当自动上传失败时作为兜底，多个URL用英文逗号分隔）
MANUAL_FILE_URL = ""
# 是否进行数据库重复性验证
ENABLE_DB_CHECK = True
# 请求间隔（秒），防止请求过快
REQUEST_INTERVAL = 0.5
# 上传/新增接口超时时间（秒）
REQUEST_TIMEOUT = 60
# ================================================================

# 数据目录（输出至 test_data/）
DATA_DIR = os.path.join(PROJECT_ROOT, 'test_data')

# 导入 dmdbclient（SCRIPT_DIR 已在顶部定义）
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from dmdbclient import DmDbClient
except ImportError as e:
    print(f"[警告] 导入 dmdbclient 失败: {e}")
    DmDbClient = None


# ==================== 数据字典 ====================
# 省份/城市前缀（用于单位名称和地址）
REGION_PREFIXES = [
    "苏州", "南京", "无锡", "常州", "徐州", "南通", "连云港", "淮安", "盐城", "扬州",
    "镇江", "泰州", "宿迁", "杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华",
    "上海", "北京", "广州", "深圳", "成都", "武汉", "西安", "重庆", "天津", "长沙",
    "青岛", "大连", "厦门", "昆明", "郑州", "济南", "福州", "合肥", "南昌", "贵阳"
]

# 区县后缀（可选）
DISTRICT_SUFFIXES = [
    "高新区", "工业园区", "经济技术开发区", "滨海新区", "江北新区", "吴中区",
    "相城区", "姑苏区", "虎丘区", "吴江区", "雨花台区", "鼓楼区", "玄武区",
    "建邺区", "秦淮区", "栖霞区", "浦口区", "江宁区", "六合区", "溧水区"
]

# 单位名称中间部分
ORG_MIDDLE_PARTS = [
    "科达民航装备", "无人机", "通用航空", "航空科技", "智慧航空", "低空飞行",
    "航空服务", "飞行培训", "航空物流", "航拍摄影", "农林植保", "电力巡检",
    "应急救援", "地理测绘", "气象监测", "环境监测", "交通巡查", "边防巡逻"
]

# 单位名称后缀
ORG_SUFFIXES = [
    "管理局", "管理部", "服务中心", "科技有限公司", "股份有限公司",
    "集团有限公司", "有限责任公司", "运营公司", "服务公司", "培训公司",
    "研究院", "研究所", "协会", "合作社", "事务所"
]

# 单位类型字典（code与统一社会信用代码前缀对应）
# 统一社会信用代码第1位：1=机构编制 5=民政 9=工商/市场监管
# 第2位：机构类别（1=企业 2=个体工商户 3=农民专业合作社等）
# 单位类型字典（code = 系统类型编码，uscc_prefix = 统一社会信用代码前缀）
ORG_TYPES = [
    {"code": "1", "name": "营利法人", "uscc_prefix": "91"},
    {"code": "2", "name": "事业单位", "uscc_prefix": "39"},
    {"code": "3", "name": "社会团体", "uscc_prefix": "42"},
    {"code": "4", "name": "基金会", "uscc_prefix": "42"},
    {"code": "5", "name": "社会服务机构", "uscc_prefix": "42"},
    {"code": "6", "name": "其他", "uscc_prefix": "11"},
    {"code": "7", "name": "特别法人", "uscc_prefix": "11"},
]
# 从类型名称映射到默认 uscc_prefix（用于数据库查询结果补充）
ORG_TYPE_PREFIX_MAP = {
    "营利法人": "91",
    "事业单位": "39",
    "社会团体": "42",
    "基金会": "42",
    "社会服务机构": "42",
    "其他": "11",
    "特别法人": "11",
}

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

# 行政区划代码（6位）
AREA_CODES = [
    "320500", "320100", "320200", "320400", "320300", "320600", "320700", "320800",
    "320900", "321000", "321100", "321200", "321300", "330100", "330200", "330300",
    "310000", "110000", "440100", "440300", "510100", "420100", "610100", "500000",
    "120000", "430100", "370200", "210200", "350200", "530100", "410100", "370100",
    "350100", "340100", "360100", "520100", "330400", "330500", "330600", "330700"
]

# 具体街道地址
STREET_ADDRESSES = [
    "科技园路88号", "创新中心大厦15楼", "航空产业园A区3号楼",
    "人民中路126号", "软件大道66号", "数字经济产业园B座",
    "太湖大道999号", "金鸡湖大道168号", "长江路555号",
    "黄河路288号", "珠江路100号", "解放路77号",
    "建设大街33号", "和平东路66号", "友谊路198号",
    "胜利路55号", "中山北路200号", "新华大街88号",
    "青年路123号", "文化路456号", "工业大道789号"
]

# 经营范围模板
BUSINESS_SCOPES = [
    "无人驾驶航空器销售、租赁及技术服务；通用航空服务；航空摄影；农林植保服务；电力巡检服务；",
    "通用航空运营服务；无人机系统研发、生产、销售；飞行培训；航拍摄影服务；",
    "无人机技术开发、技术咨询、技术服务；航空器维修；航空电子设备销售；应急救援服务；",
    "低空飞行服务；无人机物流配送；地理信息系统工程；测绘航空摄影；",
    "航空科技领域内的技术开发、技术转让；民用航空器销售；飞行作业服务；气象探测服务；",
    "无人机航拍服务；农业植保服务；环境监测服务；交通巡查服务；边防巡逻服务；",
    "通用航空包机飞行；医疗救护；商用驾驶员执照培训；空中游览；",
    "无人机系统解决方案设计；智能飞行器研发；航空数据服务；空中交通管理咨询；"
]

# 统一社会信用代码生成：前17位为数字，第18位为大写字母
USCC_CHECK_LETTERS = "ABCDEFGHJKLMNPQRTUWXY"  # 不含 I, O, Z, S, V


def generate_uscc(uscc_prefix=None):
    """生成18位统一社会信用代码
    规则：前17位为数字，第18位为大写字母（适配系统校验）
    Args:
        uscc_prefix: 前缀2位（如91=企业 39=事业单位 42=社会团体），不传则随机
    """
    if uscc_prefix:
        prefix = str(uscc_prefix)
    else:
        prefix = random.choice(["91", "39", "42", "11"])
    # 第3-8位：行政区划码（6位数字）
    area_code = random.choice(AREA_CODES)
    # 第9-17位：主体标识码（9位数字）
    body = "".join(random.choice("0123456789") for _ in range(9))
    code17 = prefix + area_code + body
    # 第18位：大写字母
    check = random.choice(USCC_CHECK_LETTERS)
    return code17 + check


def generate_name():
    """生成中文姓名（2-4个字）"""
    surname = random.choice(SURNAMES)
    length = random.choice([2, 2, 2, 3, 3, 4])  # 2-4字，2字居多
    given_name = "".join(random.choice(NAME_CHARS) for _ in range(length - 1))
    return surname + given_name


def generate_phone():
    """生成中国手机号"""
    prefixes = [
        "130", "131", "132", "133", "134", "135", "136", "137", "138", "139",
        "150", "151", "152", "153", "155", "156", "157", "158", "159",
        "180", "181", "182", "183", "184", "185", "186", "187", "188", "189",
        "191", "198", "199", "166", "135", "147"
    ]
    prefix = random.choice(prefixes)
    suffix = "".join(random.choice("0123456789") for _ in range(8))
    return prefix + suffix


def generate_address():
    """生成注册地址"""
    region = random.choice(REGION_PREFIXES)
    if random.random() < 0.5:
        district = random.choice(DISTRICT_SUFFIXES)
        return f"{region}市{district}{random.choice(STREET_ADDRESSES)}"
    return f"{region}市{random.choice(STREET_ADDRESSES)}"


def generate_org_name():
    """生成单位名称（省/地市/区开头）"""
    region = random.choice(REGION_PREFIXES)
    if random.random() < 0.3:
        # 使用区县前缀
        district = random.choice(DISTRICT_SUFFIXES)
        middle = random.choice(ORG_MIDDLE_PARTS)
        suffix = random.choice(ORG_SUFFIXES)
        return f"{region}市{district}{middle}{suffix}"
    else:
        middle = random.choice(ORG_MIDDLE_PARTS)
        suffix = random.choice(ORG_SUFFIXES)
        return f"{region}市{middle}{suffix}"


def generate_business_license_code():
    """生成无人驾驶航空器经营许可证编号"""
    # 格式参考：民航通（无）企字第 XXXXXXXX 号
    # 或采用更通用的格式
    year = random.randint(2020, 2026)
    seq = random.randint(10000000, 99999999)
    return f"民航通（无）企字第{year}{seq}号"


def generate_uav_certificate_no():
    """生成民用无人驾驶航空器运营合格证编号"""
    # 格式参考：OC-XXXX-XXXXXX 或 UOC-XXXX-XXXXXX
    year = random.randint(2020, 2026)
    seq = random.randint(100000, 999999)
    return f"UOC-{year}-{seq}"


def generate_scope():
    """生成经营范围"""
    base = random.choice(BUSINESS_SCOPES)
    extra = random.choice([
        "货物进出口；技术进出口；",
        "计算机软硬件开发；信息系统集成服务；",
        "会议及展览服务；市场营销策划；",
        "广告设计、代理、发布；"
    ])
    return base + extra


def fetch_existing_organizations():
    """从达梦数据库查询已有的运营单位（用于重复性验证）"""
    if not ENABLE_DB_CHECK or DmDbClient is None:
        return set(), set(), []
    client = DmDbClient()
    names = set()
    codes = set()
    org_types = []
    try:
        client.connect()
        result = client.query(
            table_name="operation_organization",
            columns=["organization_name", "unified_social_credit_code", "organization_type_code", "organization_type_name"]
        )
        type_map = {}
        for row in result:
            name = row.get("organization_name")
            code = row.get("unified_social_credit_code")
            type_code = row.get("organization_type_code")
            type_name = row.get("organization_type_name")
            if name:
                names.add(name)
            if code:
                codes.add(code)
            if type_code and type_name and type_code not in type_map:
                type_map[type_code] = type_name
                # 根据类型名称补充 uscc_prefix
                uscc_prefix = ORG_TYPE_PREFIX_MAP.get(type_name, "91")
                org_types.append({"code": type_code, "name": type_name, "uscc_prefix": uscc_prefix})
        print(f"[DB] 从数据库获取到 {len(names)} 条单位名称，{len(codes)} 条信用代码，{len(org_types)} 种单位类型")
        if org_types:
            print(f"[DB] 系统真实单位类型: {org_types}")
    except Exception as e:
        print(f"[DB] 查询数据库失败: {e}")
    finally:
        client.close()
    return names, codes, org_types


def _try_upload(url, file_key, image_path):
    """尝试调用指定上传接口，返回 (success, file_url)"""
    headers = {}
    if JWT_TOKEN:
        headers["jwt-token"] = JWT_TOKEN
    try:
        with open(image_path, "rb") as f:
            files = {file_key: (os.path.basename(image_path), f, "image/jpeg")}
            print(f"[上传] 正在请求: {url} (字段名: {file_key})")
            resp = requests.post(url, headers=headers, files=files, timeout=REQUEST_TIMEOUT)
        print(f"[上传] 响应状态码: {resp.status_code}")
        print(f"[上传] 响应内容: {resp.text[:500]}")
        if resp.status_code == 200:
            data = resp.json()
            status_ok = data.get("code") == "200" or data.get("status") == 200 or data.get("status") == "200"
            if status_ok:
                result = data.get("result", [])
                file_item = None
                if isinstance(result, list) and len(result) > 0:
                    file_item = result[0]
                elif isinstance(result, dict):
                    file_item = result
                if file_item:
                    file_url = file_item.get("url", "")
                    if not file_url:
                        file_url = file_item.get("path", "")
                    if file_url and not file_url.startswith("http"):
                        file_url = f"{BASE_URL}{file_url}"
                    return True, file_url
                else:
                    print(f"[上传] 接口返回 result 为空或格式异常: {result}")
            else:
                print(f"[上传] 接口返回业务异常: code={data.get('code')}, status={data.get('status')}, msg={data.get('message', data)}")
        else:
            print(f"[上传] HTTP 错误 {resp.status_code}: {resp.text[:500]}")
    except requests.exceptions.RequestException as e:
        print(f"[上传] 网络请求失败: {e}")
    except Exception as e:
        print(f"[上传] 上传过程异常: {e}")
    return False, ""


def upload_license_image():
    """上传经营许可证图片，返回文件URL
    优先尝试批量上传接口(fields: files)，失败回退单文件接口(fields: file)
    """
    if not AUTO_UPLOAD_LICENSE:
        return ""
    image_path = os.path.join(DATA_DIR, LICENSE_IMAGE)
    print(f"[上传] 准备上传图片: {image_path}")
    if not os.path.exists(image_path):
        print(f"[警告] 经营许可证图片不存在: {image_path}")
        return ""

    # 尝试 1: 批量上传接口，字段名 files
    success, file_url = _try_upload(f"{BASE_URL}{UPLOAD_PATH_BATCH}", "files", image_path)
    if success and file_url:
        print(f"[上传] 批量接口上传成功: {file_url}")
        return file_url

    # 尝试 2: 单文件上传接口，字段名 file
    print("[上传] 批量接口失败，尝试单文件上传接口...")
    success, file_url = _try_upload(f"{BASE_URL}{UPLOAD_PATH_SINGLE}", "file", image_path)
    if success and file_url:
        print(f"[上传] 单文件接口上传成功: {file_url}")
        return file_url

    print("[上传] 所有上传接口均失败")
    return ""


def create_organization(org_data):
    """调用接口新增运营单位"""
    url = f"{BASE_URL}{API_PATH}"
    headers = {
        "Content-Type": "application/json"
    }
    if JWT_TOKEN:
        headers["jwt-token"] = JWT_TOKEN
    try:
        resp = requests.post(url, headers=headers, json=org_data, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "200" or data.get("status") == 200:
                print(f"[成功] 新增运营单位: {org_data['organizationName']} (ID: {data.get('result')})")
                return True, data
            else:
                print(f"[失败] {org_data['organizationName']}: 接口返回 code={data.get('code')}, msg={data}")
                return False, data
        else:
            print(f"[失败] {org_data['organizationName']}: HTTP {resp.status_code}, {resp.text[:200]}")
            return False, resp.text
    except Exception as e:
        print(f"[失败] {org_data['organizationName']}: 请求异常 {e}")
        return False, str(e)


def generate_unique_org(existing_names, existing_codes):
    """生成不重复的运营单位数据"""
    max_retry = 100
    for _ in range(max_retry):
        org_name = generate_org_name()
        org_type = random.choice(ORG_TYPES)
        # 统一社会信用代码前缀：优先用 uscc_prefix，否则默认91
        uscc_prefix = org_type.get("uscc_prefix", "91")
        uscc = generate_uscc(uscc_prefix)
        if org_name not in existing_names and uscc not in existing_codes:
            return {
                "organizationName": org_name,
                "organizationTypeCode": str(org_type["code"]),
                "organizationTypeName": str(org_type["name"]),
                "businessLicenseCode": generate_business_license_code(),
                "hasOperationPermitted": random.choice([True, False]),
                "contactPerson": generate_name(),
                "contactPhone": generate_phone(),
                "unifiedSocialCreditCode": uscc,
                "legalRepresentativeName": generate_name(),
                "registrant": generate_name(),
                "registeredAddress": generate_address(),
                "businessScope": generate_scope(),
                "uavOperationCertificateNo": generate_uav_certificate_no(),
                "fileAttachmentUrls": ""
            }
    raise RuntimeError("无法生成不重复的数据，请检查数据库中是否已有大量数据")


def main():
    print("=" * 60)
    print("批量新增运营单位")
    print("=" * 60)
    print(f"目标接口: {BASE_URL}{API_PATH}")
    print(f"生成数量: {GENERATE_COUNT}")
    print(f"数据库重复性验证: {'开启' if ENABLE_DB_CHECK else '关闭'}")
    print(f"自动上传经营许可证: {'开启' if AUTO_UPLOAD_LICENSE else '关闭'}")
    print("=" * 60)

    if not JWT_TOKEN:
        print("[警告] JWT_TOKEN 为空，可能导致接口鉴权失败，请在配置区域填入有效的 jwt-token")

    # 1. 获取数据库中已有数据（用于重复性验证）
    existing_names, existing_codes, db_org_types = fetch_existing_organizations()

    # 优先使用数据库中真实的单位类型，否则使用默认值
    if db_org_types:
        global ORG_TYPES
        ORG_TYPES = db_org_types
        print(f"[配置] 使用数据库真实单位类型生成数据")
    else:
        print(f"[配置] 数据库无单位类型数据，使用默认类型字典: {ORG_TYPES}")

    # 2. 获取文件附件URL
    file_url = ""
    if AUTO_UPLOAD_LICENSE:
        file_url = upload_license_image()
    if not file_url and MANUAL_FILE_URL:
        file_url = MANUAL_FILE_URL
        print(f"[配置] 使用手动指定的文件URL: {file_url}")
    if not file_url:
        print("[警告] fileAttachmentUrls 为空，接口可能返回 '文件附件不能为空'")
        print("[提示] 如需继续，请设置 MANUAL_FILE_URL 或确保自动上传成功")
        confirm = input("是否继续执行? (y/n): ").strip().lower()
        if confirm != "y":
            print("已取消执行")
            return

    # 3. 批量生成并提交
    success_count = 0
    fail_count = 0
    generated_names = set()
    generated_codes = set()

    for i in range(GENERATE_COUNT):
        print(f"\n[{i + 1}/{GENERATE_COUNT}] 正在生成...")
        try:
            org_data = generate_unique_org(
                existing_names | generated_names,
                existing_codes | generated_codes
            )
            # 打印生成的关键信息用于调试
            uscc = org_data.get("unifiedSocialCreditCode", "")
            is_digits = uscc[:17].isdigit() if len(uscc) >= 17 else False
            is_letter = uscc[17:].isalpha() and uscc[17:].isupper() if len(uscc) == 18 else False
            print(f"[生成] 单位: {org_data['organizationName']}, 类型: {org_data['organizationTypeName']}({org_data['organizationTypeCode']}), 信用代码: {uscc}, 前17位数字: {is_digits}, 末位大写字母: {is_letter}")
            if file_url:
                org_data["fileAttachmentUrls"] = file_url

            success, result = create_organization(org_data)
            if success:
                success_count += 1
                generated_names.add(org_data["organizationName"])
                generated_codes.add(org_data["unifiedSocialCreditCode"])
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
