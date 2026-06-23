# -*- coding: utf-8 -*-
"""
低空用户信息生成模块
支持生成：身份证号码、手机号、邮箱等信息
可作为独立脚本运行，也可被其他模块导入使用
"""
import random
from datetime import datetime, timedelta

# ==================== 默认配置区域（按需修改）====================
# 默认生成数量
DEFAULT_GENERATE_COUNT = 10
# ================================================================

# -------------------- 身份证号码生成配置 --------------------
# 行政区划代码（地址码，前6位）
ID_AREA_CODES = {
    "110000": "北京市",
    "310000": "上海市",
    "320100": "南京市",
    "320500": "苏州市",
    "320200": "无锡市",
    "330100": "杭州市",
    "330200": "宁波市",
    "440100": "广州市",
    "440300": "深圳市",
    "510100": "成都市",
    "420100": "武汉市",
    "610100": "西安市",
}

# 身份证号权重因子（前17位分别乘以对应权重，求和后对11取模）
ID_CARD_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
# 校验码映射表（余数0-10分别对应）
ID_CARD_CHECKS = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']

# -------------------- 手机号码生成配置 --------------------
# 运营商号段定义
PHONE_PREFIXES = {
    "移动": [
        "134", "135", "136", "137", "138", "139",
        "150", "151", "152", "157", "158", "159",
        "172", "182", "183", "184", "187", "188",
        "195", "196", "197", "198"
    ],
    "联通": [
        "130", "131", "132", "155", "156", "166", "185", "186"
    ],
    "电信": [
        "133", "153", "173", "177", "180", "181", "189", "191", "199"
    ],
}
# 所有号段合并（用于随机选择）
ALL_PHONE_PREFIXES = (
    PHONE_PREFIXES["移动"] +
    PHONE_PREFIXES["联通"] +
    PHONE_PREFIXES["电信"]
)

# -------------------- 邮箱生成配置 --------------------
EMAIL_DOMAINS = [
    "qq.com", "163.com", "126.com", "gmail.com",
    "outlook.com", "sina.com", "sohu.com", "foxmail.com"
]

EMAIL_USERNAME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789._-"


# ==================== 核心生成函数 ====================

def generate_id_card(gender=None, min_age=18, max_age=55, area_code=None):
    """
    生成18位身份证号码（符合GB 11643-1999规范）

    参数:
        gender: 性别，"M"/"男" 或 "F"/"女"，None则随机
        min_age: 最小年龄
        max_age: 最大年龄
        area_code: 指定地址码，None则随机

    返回:
        dict: {
            "id_card": "110000199001011234",
            "area_code": "110000",
            "area_name": "北京市",
            "birth_date": "19900101",
            "gender": "男" / "女",
            "age": 35
        }
    """
    # 地址码
    if area_code and area_code in ID_AREA_CODES:
        selected_area = area_code
    else:
        selected_area = random.choice(list(ID_AREA_CODES.keys()))
    area_name = ID_AREA_CODES.get(selected_area, "未知地区")

    # 出生日期码（第7-14位）
    now = datetime.now()
    birth_date = now - timedelta(days=random.randint(min_age * 365, max_age * 365))
    birth_str = birth_date.strftime("%Y%m%d")

    # 顺序码（第15-17位）：奇数=男性，偶数=女性
    seq_base = random.randint(1, 499)
    if gender is not None:
        if gender in ("M", "男", "m", "male", "1"):
            seq = seq_base * 2 - 1  # 确保为奇数
        else:
            seq = seq_base * 2      # 确保为偶数
    else:
        seq = random.randint(1, 999)
    seq_str = f"{seq:03d}"

    # 性别判定
    determined_gender = "男" if int(seq_str) % 2 == 1 else "女"

    # 前17位
    code17 = selected_area + birth_str + seq_str

    # 计算第18位校验码
    total = sum(int(ch) * ID_CARD_WEIGHTS[i] for i, ch in enumerate(code17))
    check = ID_CARD_CHECKS[total % 11]

    id_card = code17 + check
    age = now.year - birth_date.year - ((now.month, now.day) < (birth_date.month, birth_date.day))

    return {
        "id_card": id_card,
        "area_code": selected_area,
        "area_name": area_name,
        "birth_date": birth_str,
        "gender": determined_gender,
        "age": age
    }


def generate_phone(carrier=None):
    """
    生成中国手机号码

    参数:
        carrier: 运营商，"移动"/"联通"/"电信"，None则随机

    返回:
        dict: {
            "phone": "13800138000",
            "carrier": "移动"
        }
    """
    if carrier and carrier in PHONE_PREFIXES:
        prefixes = PHONE_PREFIXES[carrier]
        selected_carrier = carrier
    else:
        selected_carrier = random.choice(list(PHONE_PREFIXES.keys()))
        prefixes = PHONE_PREFIXES[selected_carrier]

    prefix = random.choice(prefixes)
    suffix = "".join(random.choice("0123456789") for _ in range(8))

    return {
        "phone": prefix + suffix,
        "carrier": selected_carrier
    }


def generate_email(username=None, domain=None):
    """
    生成邮箱地址

    参数:
        username: 指定用户名，None则随机生成
        domain: 指定域名，None则随机选择

    返回:
        dict: {
            "email": "abc123@qq.com",
            "username": "abc123",
            "domain": "qq.com"
        }
    """
    if username:
        user = username
    else:
        # 随机生成6-12位用户名
        length = random.randint(6, 12)
        user = "".join(random.choice(EMAIL_USERNAME_CHARS) for _ in range(length))

    selected_domain = domain if domain else random.choice(EMAIL_DOMAINS)

    return {
        "email": f"{user}@{selected_domain}",
        "username": user,
        "domain": selected_domain
    }


def generate_user_info(count=1, gender=None, carrier=None, domain=None):
    """
    批量生成完整的用户信息

    参数:
        count: 生成数量，默认1
        gender: 性别筛选，None则随机
        carrier: 运营商筛选，None则随机
        domain: 邮箱域名筛选，None则随机

    返回:
        list: 用户信息字典列表
    """
    results = []
    for _ in range(count):
        id_info = generate_id_card(gender=gender)
        phone_info = generate_phone(carrier=carrier)
        email_info = generate_email(domain=domain)

        results.append({
            "id_card": id_info["id_card"],
            "area_code": id_info["area_code"],
            "area_name": id_info["area_name"],
            "birth_date": id_info["birth_date"],
            "gender": id_info["gender"],
            "age": id_info["age"],
            "phone": phone_info["phone"],
            "carrier": phone_info["carrier"],
            "email": email_info["email"],
            "email_username": email_info["username"],
            "email_domain": email_info["domain"],
        })
    return results


def validate_id_card(id_card):
    """
    校验身份证号码是否合法

    参数:
        id_card: 待校验的身份证号码

    返回:
        bool: 是否合法
    """
    if not id_card or len(id_card) != 18:
        return False
    if not id_card[:17].isdigit():
        return False

    code17 = id_card[:17]
    total = sum(int(ch) * ID_CARD_WEIGHTS[i] for i, ch in enumerate(code17))
    expected_check = ID_CARD_CHECKS[total % 11]
    return id_card[17].upper() == expected_check


# ==================== 脚本入口 ====================

def main():
    print("=" * 70)
    print("低空用户信息生成工具")
    print("=" * 70)

    # 可通过修改 DEFAULT_GENERATE_COUNT 调整默认数量
    count = DEFAULT_GENERATE_COUNT

    print(f"生成数量: {count}")
    print("-" * 70)

    users = generate_user_info(count=count)

    for i, user in enumerate(users, 1):
        print(f"\n【第 {i} 条】")
        print(f"  身份证号 : {user['id_card']}  (校验: {'通过' if validate_id_card(user['id_card']) else '失败'})")
        print(f"  地址信息 : {user['area_name']} ({user['area_code']})")
        print(f"  出生日期 : {user['birth_date']} (年龄: {user['age']}岁)")
        print(f"  性别     : {user['gender']}")
        print(f"  手机号码 : {user['phone']} ({user['carrier']})")
        print(f"  电子邮箱 : {user['email']}")

    print("\n" + "=" * 70)
    print(f"共计生成 {count} 条用户信息")
    print("=" * 70)


if __name__ == "__main__":
    main()
