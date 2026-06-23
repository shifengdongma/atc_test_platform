# -*- coding: utf-8 -*-
"""
生成航空器数据，基于模板规则,扩展随机5000，
支持从达梦数据库查询真实用户/单位数据填充
"""
import os
import sys
import random
import string
from datetime import datetime, timedelta
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, Border, Side

# ==================== 配置 ====================
#生出数据量
GENERATE_COUNT = 5000  # 配置：每次生成的数据条数

# 无人机名称配置（供 generate_uav_name 使用）
UAV_NAME_PREFIX = "测试导入"
UAV_NAME_MIDDLE_MIN = 1000
UAV_NAME_MIDDLE_MAX = 9999

# uav_info 表字段配置（供 fetch_uav_info 查询去重用）
UAV_INFO_NAME_COLUMN = "uav_name"
UAV_INFO_ORG_COLUMN = "operation_organization_name"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
BASE_DIR = os.path.join(PROJECT_ROOT, 'tmp')
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, 'docs', '航空器数据导入模板.xlsx')

# 导入 dmdbclient（处理跨目录导入）
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from dmdbclient import DmDbClient
except ImportError as e:
    print(f"[警告] 导入 dmdbclient 失败: {e}")
    DmDbClient = None


def get_output_path():
    """生成带日期时分秒的输出文件路径"""
    date_str = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f'5000随机扩展ID航空器{date_str}.xlsx'
    return os.path.join(BASE_DIR, filename)

# ==================== 数据字典 ====================
MANUFACTURERS = [
    "大疆", "极飞", "亿航", "道通", "纵横", "航天彩虹", "中航工业",
    "零度智控", "普洛特", "科卫泰", "飞马", "拓攻", "中航智", "凌云",
    "天宇创新", "华科尔", "哈博森", "臻迪", "傲势", "腾盾"
]

MODELS = [
    "MD-1024", "XF-2000", "EH-216", "DT-EVO", "CW-007", "CH-4",
    "AV-500", "ZT-3V", "PLT-X6", "KWT-X6L", "FM-D20", "TG-26",
    "ZZ-11", "LY-320", "TY-800", "HK-501", "HBS-X4", "ZD-Power",
    "AS-XF", "TD-125", "DJI-M300", "DJI-M30", "DJI-Air3", "DJI-Mini4",
    "XF-P150", "EH-116", "DT-Matrix", "CW-15", "CH-5", "AV-1000"
]

CATEGORIES = ["固定翼", "旋翼航空器", "多桨或多轴航空器", "复合翼航空器", "飞艇", "其他"]
TYPES = ["微型", "轻型", "小型", "中型", "大型"]
OWNER_TYPES = ["个人", "单位"]
PERMIT_STATUS = ["有许可", "无许可"]
CONTROL_MODES = ["自动", "半自动"]
ENV_LIMITS = [
    "禁止结冰环境", "禁止雨中作业", "禁止大风环境", "禁止夜间作业",
    "禁止高海拔环境", "温度限制-10~50℃", "湿度限制<85%", "无特殊限制",
    "禁止沙尘环境", "禁止雷电环境"
]
TAKEOFF_REQS = [
    "平整硬质地面", "起降场风速≤5", "天气晴朗", "视野开阔",
    "跑道长度≥100m", "垂直起飞", "短距起飞", "弹射起飞"
]
LANDING_REQS = [
    "垂直着陆", "着陆坡度≤3°", "平整地面着陆", "伞降回收",
    "撞网回收", "滑跑着陆", "自动返航着陆"
]
SENSE_AVOID = [
    "具备前向毫米波雷达感知", "具备视觉避障系统", "具备红外感知能力",
    "具备超声波避障", "具备激光雷达感知", "具备多传感器融合避障",
    "基础避障能力", "高级自主避让系统"
]
NAV_METHODS = [
    "GNSS", "RTK", "视觉融合", "惯性导航", "北斗导航",
    "GPS+GLONASS", "多星融合定位", "视觉+惯性融合"
]
AUTO_CAPABILITIES = [
    "自主起降", "航线规划", "失控返航", "定点悬停", "自主巡航",
    "编队飞行", "自动避障", "地形跟随", "全自动任务执行"
]
INSURANCE_COMPANIES = [
    "太平洋保险", "中国人保", "中国平安", "国寿财险", "中华联合",
    "大地保险", "阳光保险", "华泰保险", "永安保险", "天安保险"
]
INSURANCE_TYPES = [
    "第三者责任险", "机身一切险", "综合责任险", "组织责任险",
    "公众责任险", "产品责任险", "雇主责任险", "货物运输险"
]
INSURANCE_INFO = [
    "免赔额1000元", "无免赔", "绝对免赔率10%", "每次事故免赔5000元",
    "累计赔偿限额", "单次赔偿限额", "包含精神损害赔偿"
]

# ==================== 生成函数 ====================
def random_date(start_year=2024, end_year=2028):
    """生成随机日期字符串 YYYYMMDD"""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = end - start
    random_days = random.randint(0, delta.days)
    date = start + timedelta(days=random_days)
    return date.strftime("%Y%m%d")


def generate_id_number():
    """生成18位身份证号"""
    provinces = ['11', '12', '13', '14', '15', '21', '22', '23', '31', '32', '33',
                 '34', '35', '36', '37', '41', '42', '43', '44', '45', '46', '50',
                 '51', '52', '53', '54', '61', '62', '63', '64', '65']
    province = random.choice(provinces)
    city = f"{random.randint(0, 99):02d}"
    district = f"{random.randint(0, 99):02d}"
    birth_year = random.randint(1970, 2005)
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)
    birthday = f"{birth_year}{birth_month:02d}{birth_day:02d}"
    seq = f"{random.randint(0, 999):03d}"
    id17 = province + city + district + birthday + seq
    # 计算校验码
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
    sum_val = sum(int(id17[i]) * weights[i] for i in range(17))
    return id17 + check_codes[sum_val % 11]


def generate_unified_code():
    """生成18位统一社会信用代码"""
    chars = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    code = random.choice("NY")  # 登记管理部门代码
    code += random.choice("1239")  # 机构类别代码
    code += f"{random.randint(100000, 999999):06d}"  # 登记管理机关行政区划码
    code += ''.join(random.choices(string.ascii_uppercase + string.digits, k=9))
    return code[:18]


def generate_aircraft_code(index):
    """生成20位航空器识别码"""
    prefix = random.choice(["DM", "XH", "EH", "DJ", "CW", "CH", "AV", "ZT"])
    # 补足20位: prefix(2) + 数字(18) = 20
    num_part = f"{index:018d}"
    return (prefix + num_part)[:20]


def generate_registration_no(index=None, used_nos=None):
    """生成13位实名登记号，支持去重

    格式: 前缀(3位) + 月日时(6位) + 序号/随机(4位) = 13位
    示例: XFH0521130001
    """
    prefixes = ["DJH", "XFH", "EHH", "DHH", "CWH", "CHH"]
    time_suffix = datetime.now().strftime("%m%d%H")  # 月日时 6 位
    for _ in range(1000):
        prefix = random.choice(prefixes)
        if index is not None:
            num_part = f"{time_suffix}{index:04d}"
        else:
            num_part = f"{time_suffix}{random.randint(0, 9999):04d}"
        code = (prefix + num_part)[:13]
        if used_nos is None or code not in used_nos:
            return code
    raise RuntimeError("无法生成不重复的实名登记号")


def generate_permit_no():
    """生成适航许可证编号"""
    prefix = random.choice(["XH", "SH", "HH", "AH"])
    return prefix + f"{random.randint(1000000, 9999999):07d}"


def generate_policy_no():
    """生成保单号"""
    return f"{random.randint(1000000000, 9999999999):010d}"


def fetch_personal_users():
    """从 users 表查询独立从业者的真实证件号码"""
    if DmDbClient is None:
        print("[DB] dmdbclient 不可用，跳过个人用户查询")
        return []
    client = DmDbClient()
    try:
        client.connect()
        result = client.query(
            table_name="users",
            columns=["identify_number"],
            where="role_name = '独立从业者' AND identify_number IS NOT NULL"
        )
        ids = [r["identify_number"] for r in result if r.get("identify_number")]
        print(f"[DB] 从 users 表获取到 {len(ids)} 条独立从业者证件号码")
        return ids
    except Exception as e:
        print(f"[DB] 查询 users 表失败: {e}")
        return []
    finally:
        client.close()


def fetch_organizations():
    """从 operation_organization 表查询真实单位信息"""
    if DmDbClient is None:
        print("[DB] dmdbclient 不可用，跳过单位查询")
        return []
    client = DmDbClient()
    try:
        client.connect()
        result = client.query(
            table_name="operation_organization",
            columns=["organization_name", "unified_social_credit_code"]
        )
        orgs = [
            (r.get("organization_name"), r.get("unified_social_credit_code"))
            for r in result
            if r.get("organization_name") and r.get("unified_social_credit_code")
        ]
        print(f"[DB] 从 operation_organization 表获取到 {len(orgs)} 条单位信息")
        return orgs
    except Exception as e:
        print(f"[DB] 查询 operation_organization 表失败: {e}")
        return []
    finally:
        client.close()


def fetch_uav_info():
    """从 uav_info 表查询已有无人机名称（按归属单位分组 + 全局集合）"""
    if DmDbClient is None:
        print("[DB] dmdbclient 不可用，跳过 uav_info 查询")
        return {}, set()
    client = DmDbClient()
    try:
        client.connect()
        result = client.query(
            table_name="uav_info",
            columns=[UAV_INFO_NAME_COLUMN, UAV_INFO_ORG_COLUMN]
        )
        org_uav_names = {}
        all_uav_names = set()
        for r in result:
            org = r.get(UAV_INFO_ORG_COLUMN, "")
            name = r.get(UAV_INFO_NAME_COLUMN, "")
            if name:
                all_uav_names.add(name)
            if org and name:
                if org not in org_uav_names:
                    org_uav_names[org] = set()
                org_uav_names[org].add(name)
        print(f"[DB] 从 uav_info 表获取到 {len(org_uav_names)} 个单位，共 {len(all_uav_names)} 条无人机名称（全局去重用）")
        return org_uav_names, all_uav_names
    except Exception as e:
        print(f"[DB] 查询 uav_info 表失败: {e}")
        return {}, set()
    finally:
        client.close()


def fetch_existing_identify_codes():
    """从 uav_info 表查询已有的航空器识别码（用于去重）

    尝试的字段名: identify_code -> unique_product_identification_code
    如果都查询失败，返回空集合（不阻止生成）
    """
    if DmDbClient is None:
        print("[DB] dmdbclient 不可用，跳过航空器识别码去重")
        return set()

    client = DmDbClient()
    possible_columns = ["identify_code", "unique_product_identification_code"]

    for col in possible_columns:
        try:
            client.connect()
            result = client.query(
                table_name="uav_info",
                columns=[col]
            )
            codes = {r.get(col) for r in result if r.get(col)}
            print(f"[DB] 从 uav_info 表({col})获取到 {len(codes)} 条已有航空器识别码")
            return codes
        except Exception:
            continue
        finally:
            client.close()

    print("[DB] 警告: 无法从 uav_info 表查询航空器识别码（字段名不匹配），跳过去重")
    return set()


def fetch_existing_registration_nos():
    """从 uav_info 表查询已有的实名登记号（用于去重）

    尝试的字段名: registration_no -> registration_number -> real_name_registration_no
    如果都查询失败，返回空集合（不阻止生成）
    """
    if DmDbClient is None:
        print("[DB] dmdbclient 不可用，跳过实名登记号去重")
        return set()

    client = DmDbClient()
    possible_columns = ["registration_no", "registration_number", "real_name_registration_no"]

    for col in possible_columns:
        try:
            client.connect()
            result = client.query(
                table_name="uav_info",
                columns=[col]
            )
            codes = {r.get(col) for r in result if r.get(col)}
            print(f"[DB] 从 uav_info 表({col})获取到 {len(codes)} 条已有实名登记号")
            return codes
        except Exception:
            continue
        finally:
            client.close()

    print("[DB] 警告: 无法从 uav_info 表查询实名登记号（字段名不匹配），跳过去重")
    return set()


def generate_uav_name(org_key, existing_uav_names, seq_index, global_names=None):
    """生成无人机名称，确保同单位下不重复，且全局不重复
    格式: 测试导入XXXX-XXXXX (前缀+4位数字-5位序号)
    """
    existing_names = existing_uav_names.get(org_key, set()) if existing_uav_names else set()
    global_set = global_names if global_names else set()
    middle_num = random.randint(UAV_NAME_MIDDLE_MIN, UAV_NAME_MIDDLE_MAX)
    base_prefix = f"{UAV_NAME_PREFIX}{middle_num}-"
    for seq in range(seq_index, 99999):
        name = f"{base_prefix}{seq:05d}"
        if name not in existing_names and name not in global_set:
            return name
    for _ in range(100):
        middle_num = random.randint(UAV_NAME_MIDDLE_MIN, UAV_NAME_MIDDLE_MAX)
        name = f"{UAV_NAME_PREFIX}{middle_num}-{seq_index:05d}"
        if name not in existing_names and name not in global_set:
            return name
    raise RuntimeError(f"无法为单位 [{org_key}] 生成不重复的无人机名称")


def generate_row(index, personal_ids=None, organizations=None, existing_uav_names=None, org_seq_map=None, aircraft_code=None, registration_no=None, global_uav_names=None):
    """生成单条航空器数据"""
    idx = index + 1
    aircraft_type = random.choice(TYPES)
    owner_type = random.choice(OWNER_TYPES)
    permit_status = random.choice(PERMIT_STATUS)

    # 中型、大型必须有适航许可证编号
    permit_no = ""
    if aircraft_type in ["中型", "大型"] and permit_status == "有许可":
        permit_no = generate_permit_no()
    elif permit_status == "有许可":
        permit_no = generate_permit_no()

    # 个人必填身份证号，单位必填统一社会信用代码
    id_card = ""
    unified_code = ""
    org_name = ""
    if owner_type == "个人":
        if personal_ids:
            id_card = random.choice(personal_ids)
        else:
            id_card = generate_id_number()
    else:
        if organizations:
            org_name, unified_code = random.choice(organizations)
        else:
            unified_code = generate_unified_code()

    # 生成无人机名称（同单位下不重复 + 全局不重复）
    org_key = org_name if org_name else unified_code
    if org_key:
        seq = org_seq_map.get(org_key, 1)
        uav_name = generate_uav_name(org_key, existing_uav_names, seq, global_names=global_uav_names)
        org_seq_map[org_key] = seq + 1
    else:
        uav_name = f"{UAV_NAME_PREFIX}{random.randint(UAV_NAME_MIDDLE_MIN, UAV_NAME_MIDDLE_MAX)}-{idx:05d}"

    # 生成有效期
    start_date = random_date(2024, 2027)
    end_date = random_date(2027, 2030)
    valid_period = f"{start_date}-{end_date}"

    # 航空器识别码：优先使用传入值，否则生成
    code = aircraft_code if aircraft_code else generate_aircraft_code(idx)
    # 实名登记号：优先使用传入值，否则生成
    reg_no = registration_no if registration_no else generate_registration_no(idx)

    row = [
        uav_name,  # 航空器名称
        code,  # 航空器识别码
        reg_no,  # 实名登记号
        random.choice(MANUFACTURERS),  # 厂商
        random.choice(MODELS),  # 型号
        random.choice(CATEGORIES),  # 类别
        aircraft_type,  # 类型
        owner_type,  # 拥有者类型
        id_card,  # 证件号码
        unified_code,  # 统一社会信用代码
        permit_status,  # 适航许可状态
        permit_no,  # 适航许可证编号
        random.randint(5, 200),  # 巡航速度
        random.randint(15, 300),  # 平均续航时间
        round(random.uniform(0.5, 150), 2),  # 空机重量
        round(random.uniform(1, 300), 2),  # 最大起飞重量
        round(random.uniform(1, 25), 2),  # 典型爬升率
        round(random.uniform(2, 30), 2),  # 最大爬升率
        round(random.uniform(1, 20), 2),  # 典型下降率
        round(random.uniform(2, 25), 2),  # 最大下降率
        round(random.uniform(5, 60), 2),  # 典型转弯率
        round(random.uniform(10, 90), 2),  # 最大转弯率
        f"{random.randint(3, 12)}级",  # 抗风等级
        random.choice(ENV_LIMITS),  # 环境限制
        random.randint(15, 300),  # 最大续航能力
        random.choice(TAKEOFF_REQS),  # 起飞要求
        random.choice(LANDING_REQS),  # 着陆要求
        round(random.uniform(0.1, 50), 2),  # 载重限制
        random.randint(30, 90),  # 最大噪音
        random.choice(CONTROL_MODES),  # 控制模式
        random.choice(SENSE_AVOID),  # 感知与避让能力
        random.choice(NAV_METHODS),  # 导航方式
        random.choice(AUTO_CAPABILITIES),  # 自主能力
        generate_policy_no(),  # 保单号
        random.choice(INSURANCE_COMPANIES),  # 保险公司
        random.choice(INSURANCE_TYPES),  # 险种
        random.randint(50000, 5000000),  # 保额
        valid_period,  # 有效期
        random.choice(INSURANCE_INFO),  # 责任保险信息
    ]
    return row


# ==================== 主程序 ====================
def main():
    print("正在加载模板...")
    wb = load_workbook(TEMPLATE_PATH)
    ws = wb.active

    print(f"模板当前行数: {ws.max_row}")

    # 保留模板前两行（说明+表头），清空示例数据
    # 模板数据从第3行开始
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
        for cell in row:
            cell.value = None

    # 从达梦数据库获取真实数据
    print("\n--- 从达梦数据库查询真实数据 ---")
    personal_ids = fetch_personal_users()
    organizations = fetch_organizations()
    existing_uav_names, global_uav_names = fetch_uav_info()

    # 查询已有航空器识别码，用于去重
    print("\n--- 航空器识别码去重检查 ---")
    existing_codes = fetch_existing_identify_codes()

    # 查询已有实名登记号，用于去重
    print("\n--- 实名登记号去重检查 ---")
    existing_reg_nos = fetch_existing_registration_nos()

    if not personal_ids:
        print("[提示] 未获取到个人用户数据，将使用模拟身份证号")
    if not organizations:
        print("[提示] 未获取到单位数据，将使用模拟统一社会信用代码")

    # 用于追踪每个单位当前的序号
    org_seq_map = {}

    # 预生成 5000 个与数据库不重复的航空器识别码
    print(f"\n--- 预生成 {GENERATE_COUNT} 个不重复识别码 ---")
    generated_codes = []
    used_codes = set(existing_codes)
    for i in range(GENERATE_COUNT):
        idx = i + 1
        code = generate_aircraft_code(idx)
        attempts = 0
        while code in used_codes and attempts < 100:
            # 换前缀重试
            code = generate_aircraft_code(idx + attempts * 10000)
            attempts += 1
        used_codes.add(code)
        generated_codes.append(code)
    print(f"[完成] 已生成 {len(generated_codes)} 个唯一识别码")

    # 预生成 5000 个与数据库不重复的实名登记号（使用随机数字降低碰撞概率）
    print(f"\n--- 预生成 {GENERATE_COUNT} 个不重复实名登记号 ---")
    generated_reg_nos = []
    used_reg_nos = set(existing_reg_nos)
    for i in range(GENERATE_COUNT):
        reg = generate_registration_no(index=i, used_nos=used_reg_nos)
        used_reg_nos.add(reg)
        generated_reg_nos.append(reg)
    print(f"[完成] 已生成 {len(generated_reg_nos)} 个唯一实名登记号")

    print(f"\n开始生成 {GENERATE_COUNT} 条数据...")

    # 从第3行开始写入数据
    for i in range(GENERATE_COUNT):
        row_data = generate_row(
            i, personal_ids, organizations, existing_uav_names, org_seq_map,
            aircraft_code=generated_codes[i],
            registration_no=generated_reg_nos[i],
            global_uav_names=global_uav_names
        )
        row_num = i + 3  # Excel行号从1开始，第3行是第一条数据
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=row_num, column=col_idx, value=value)

        if (i + 1) % 500 == 0:
            print(f"  已生成 {i + 1} 条...")

    output_path = get_output_path()
    print("保存文件...")
    wb.save(output_path)
    print(f"完成！文件保存至: {output_path}")
    print(f"共生成 {GENERATE_COUNT} 条航空器数据")

    # 打印删除 SQL（便于测试后清理）
    print("\n--- 删除 SQL（如需清理这 5000 条测试数据）---")
    print(f"DELETE FROM uav_info WHERE uav_name LIKE '{UAV_NAME_PREFIX}%';")
    print("--- SQL 结束 ---")


if __name__ == "__main__":
    main()
