# -*- coding: utf-8 -*-
"""
基于扩展的 5000 个无人机标识符生成航空器导入模板

数据源：utm_moc52_develop/uav_identifiers_extended.py（5000 个预置 ID）
输出：test_data/内置5000航空器数据.xlsx
"""
import os
import sys
import re
import random
import string
from datetime import datetime, timedelta
from openpyxl import load_workbook

# ==================== 路径配置 ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), 'tools_expend_test', 'test_data')
LOG_DIR = os.path.join(SCRIPT_DIR, 'log')
TEMPLATE_PATH = os.path.join(BASE_DIR, '航空器数据导入模板.xlsx')


def get_next_version():
    """扫描 log 目录，自动计算下一个版本号（递增0.1）"""
    pattern = re.compile(r'ha_内置5000航空器数据_(\d+\.\d+)\.xlsx')
    max_version = 0.0
    if os.path.exists(LOG_DIR):
        for filename in os.listdir(LOG_DIR):
            match = pattern.match(filename)
            if match:
                version = float(match.group(1))
                if version > max_version:
                    max_version = version
    return round(max_version + 0.1, 1)


def get_output_path():
    """生成带版本迭代的输出文件路径（输出到 log 目录）"""
    version = get_next_version()
    filename = f'ha_内置5000航空器数据_{version:.1f}.xlsx'
    os.makedirs(LOG_DIR, exist_ok=True)
    output_path = os.path.join(LOG_DIR, filename)
    # 如果文件已存在（iCloud 同步延迟等），继续递增直到找到可用文件名
    while os.path.exists(output_path):
        version = round(version + 0.1, 1)
        filename = f'ha_内置5000航空器数据_{version:.1f}.xlsx'
        output_path = os.path.join(LOG_DIR, filename)
    return output_path


# 加载扩展 ID 列表（5000 个）
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ENGINE_DIR)
from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED

# 导入达梦数据库客户端（同目录下 dm_ha_client.py，支持双集群配置）
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    from dm_ha_client import DmDbClient
except ImportError as e:
    print(f"[警告] 导入 dm_ha_client 失败: {e}")
    DmDbClient = None

GENERATE_COUNT = len(UAV_IDENTIFIERS_EXTENDED)  # 5000

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
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
    sum_val = sum(int(id17[i]) * weights[i] for i in range(17))
    return id17 + check_codes[sum_val % 11]


def generate_unified_code():
    """生成18位统一社会信用代码"""
    code = random.choice("NY")
    code += random.choice("1239")
    code += f"{random.randint(100000, 999999):06d}"
    code += ''.join(random.choices(string.ascii_uppercase + string.digits, k=9))
    return code[:18]


def generate_permit_no():
    """生成适航许可证编号"""
    prefix = random.choice(["XH", "SH", "HH", "AH"])
    return prefix + f"{random.randint(1000000, 9999999):07d}"


def generate_policy_no():
    """生成保单号"""
    return f"{random.randint(1000000000, 9999999999):010d}"


def fetch_personal_users():
    """从 operation_people 表查询操控员/观测员的真实证件号码（导入系统校验的是此表）"""
    if DmDbClient is None:
        print("[DB] dm_ha_client 不可用，跳过个人用户查询")
        return []
    client = DmDbClient()
    try:
        client.connect()
        result = client.query(
            table_name="operation_people",
            columns=["identify_number"],
            where="identify_number IS NOT NULL"
        )
        # 去重
        ids = list({r["identify_number"] for r in result if r.get("identify_number")})
        print(f"[DB] 从 operation_people 表获取到 {len(ids)} 条证件号码（去重后）")
        return ids
    except Exception as e:
        print(f"[DB] 查询 operation_people 表失败: {e}")
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
        except Exception as e:
            # 可能是字段名不存在，继续尝试下一个
            continue
        finally:
            client.close()

    print("[DB] 警告: 无法从 uav_info 表查询航空器识别码（字段名不匹配），跳过去重")
    return set()


def generate_uav_name(index):
    """生成无人机名称"""
    prefixes = ["性能", "测试", "demo", "UAV", "Drone"]
    return f"{random.choice(prefixes)}{random.randint(1000, 9999)}-{index:05d}"


def generate_row(index, aircraft_code, registration_no, personal_ids, organizations):
    """生成单条航空器数据"""
    idx = index + 1
    aircraft_type = random.choice(TYPES)
    owner_type = random.choice(OWNER_TYPES)
    permit_status = random.choice(PERMIT_STATUS)

    permit_no = ""
    if permit_status == "有许可":
        permit_no = generate_permit_no()

    # 个人必填身份证号，单位必填统一社会信用代码（优先使用数据库真实数据）
    id_card = ""
    unified_code = ""
    if owner_type == "个人":
        if personal_ids:
            id_card = personal_ids[index % len(personal_ids)]
        else:
            id_card = generate_id_number()
    else:
        if organizations:
            _, unified_code = organizations[index % len(organizations)]
        else:
            unified_code = generate_unified_code()

    start_date = random_date(2024, 2027)
    end_date = random_date(2027, 2030)
    valid_period = f"{start_date}-{end_date}"

    row = [
        generate_uav_name(idx),
        aircraft_code,
        registration_no,
        random.choice(MANUFACTURERS),
        random.choice(MODELS),
        random.choice(CATEGORIES),
        aircraft_type,
        owner_type,
        id_card,
        unified_code,
        permit_status,
        permit_no,
        random.randint(5, 200),
        random.randint(15, 300),
        round(random.uniform(0.5, 150), 2),
        round(random.uniform(1, 300), 2),
        round(random.uniform(1, 25), 2),
        round(random.uniform(2, 30), 2),
        round(random.uniform(1, 20), 2),
        round(random.uniform(2, 25), 2),
        round(random.uniform(5, 60), 2),
        round(random.uniform(10, 90), 2),
        f"{random.randint(3, 12)}级",
        random.choice(ENV_LIMITS),
        random.randint(15, 300),
        random.choice(TAKEOFF_REQS),
        random.choice(LANDING_REQS),
        round(random.uniform(0.1, 50), 2),
        random.randint(30, 90),
        random.choice(CONTROL_MODES),
        random.choice(SENSE_AVOID),
        random.choice(NAV_METHODS),
        random.choice(AUTO_CAPABILITIES),
        generate_policy_no(),
        random.choice(INSURANCE_COMPANIES),
        random.choice(INSURANCE_TYPES),
        random.randint(50000, 5000000),
        valid_period,
        random.choice(INSURANCE_INFO),
    ]
    return row


# ==================== 主程序 ====================
def main():
    print("正在加载模板...")
    wb = load_workbook(TEMPLATE_PATH)
    ws = wb.active

    print(f"模板当前行数: {ws.max_row}")

    # 保留模板前两行（说明+表头），清空示例数据
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
        for cell in row:
            cell.value = None

    print(f"\n开始生成 {GENERATE_COUNT} 条航空器数据...")

    # 从达梦数据库获取真实数据
    print("\n--- 从达梦数据库查询真实数据 ---")
    personal_ids = fetch_personal_users()
    organizations = fetch_organizations()

    if not personal_ids:
        print("[提示] 未获取到个人用户数据，将使用模拟身份证号（可能导致导入失败）")
    elif len(personal_ids) < 1000:
        print(f"[警告] 数据库中仅有 {len(personal_ids)} 条个人用户数据，建议先运行 '02批量新增操作观测员.py' 生成更多个人用户")
    if not organizations:
        print("[提示] 未获取到单位数据，将使用模拟统一社会信用代码")

    # 从数据库查询已有航空器识别码，过滤已存在的ID
    print("\n--- 航空器识别码去重检查 ---")
    existing_codes = fetch_existing_identify_codes()
    if existing_codes:
        original_count = len(UAV_IDENTIFIERS_EXTENDED)
        filtered_identifiers = [
            item for item in UAV_IDENTIFIERS_EXTENDED
            if item[0] not in existing_codes
        ]
        filtered_count = len(filtered_identifiers)
        skipped = original_count - filtered_count
        print(f"[去重] 原ID总数: {original_count}, 已存在: {skipped}, 剩余可导入: {filtered_count}")
        if filtered_count == 0:
            print("[警告] 所有航空器识别码均已存在于数据库中，无需生成")
            return
    else:
        filtered_identifiers = UAV_IDENTIFIERS_EXTENDED

    # 生成带版本号的输出路径
    output_path = get_output_path()

    for i in range(len(filtered_identifiers)):
        aircraft_code, registration_no = filtered_identifiers[i]
        row_data = generate_row(i, aircraft_code, registration_no, personal_ids, organizations)
        row_num = i + 3
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=row_num, column=col_idx, value=value)

        if (i + 1) % 500 == 0:
            print(f"  已生成 {i + 1} 条...")

    print("保存文件...")
    wb.save(output_path)
    print(f"完成！文件保存至: {output_path}")
    print(f"共生成 {len(filtered_identifiers)} 条航空器数据")
    if personal_ids:
        print(f"  - 个人用户: 使用数据库真实证件号码 ({len(personal_ids)} 条)")
    if organizations:
        print(f"  - 运营单位: 使用数据库真实统一社会信用代码 ({len(organizations)} 条)")


if __name__ == "__main__":
    main()
