"""
simulation_core.py
工业级 UTM（无人机交通管理）仿真核心 (v3.0)
主要功能：
- 真实感无人机动力学仿真（带简单风扰动）
- 支持轨迹飞行（Trajectory）和区域盘旋（Loiter/Polygon）两种任务类型
- 模拟含噪声的GPS位置观测
- 保留最近10帧历史位置（供后续C++卡尔曼滤波平滑/回放使用）
- 动态生成4D禁飞区（带起止时间）
"""

import time
import math
import random
import string
import ctypes
import hashlib
from collections import deque
from typing import List, Dict, Any, Optional

import env as _env

# 假设这些结构体已在 pylib.structs 中定义
from pylib.structs import (
    GeoPoint, Vec3, Waypoint, FlightPlan, TelemetryData, TelemetrySnapshot,
    DynamicNoFlyZone, AreaGeometry
)
from pylib.structs import *

# ==============================
#          全局常量（含默认值，支持外部传参覆盖）
# ==============================

# ---- 默认配置（首次加载时生效）----
_DEFAULT_ORIGIN_LAT = 40.818724
_DEFAULT_ORIGIN_LON = 85.070136
_DEFAULT_RE_EARTH = 6371000.0
_DEFAULT_SIM_RADIUS_M = 100000.0
_DEFAULT_CLIMB_RATE = 15.0
_DEFAULT_CRUISE_SPEED = 30.0
_DEFAULT_MAX_HORIZ_ACCEL = 5.0
_DEFAULT_MAX_VERT_ACCEL = 5.0
_DEFAULT_MIN_CRUISE_ALT = 50.0
_DEFAULT_MAX_CRUISE_ALT = 200.0

# ---- 当前活动配置（外部可通过 set_simulation_params 修改）----
ORIGIN_LAT = _DEFAULT_ORIGIN_LAT
ORIGIN_LON = _DEFAULT_ORIGIN_LON
RE_EARTH = _DEFAULT_RE_EARTH
SIM_RADIUS_M = _DEFAULT_SIM_RADIUS_M
CLIMB_RATE = _DEFAULT_CLIMB_RATE
CRUISE_SPEED = _DEFAULT_CRUISE_SPEED
MAX_HORIZ_ACCEL = _DEFAULT_MAX_HORIZ_ACCEL
MAX_VERT_ACCEL = _DEFAULT_MAX_VERT_ACCEL
MIN_CRUISE_ALT = _DEFAULT_MIN_CRUISE_ALT
MAX_CRUISE_ALT = _DEFAULT_MAX_CRUISE_ALT


def set_simulation_params(
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
    re_earth: Optional[float] = None,
    sim_radius_m: Optional[float] = None,
    climb_rate: Optional[float] = None,
    cruise_speed: Optional[float] = None,
    max_horiz_accel: Optional[float] = None,
    max_vert_accel: Optional[float] = None,
    min_cruise_alt: Optional[float] = None,
    max_cruise_alt: Optional[float] = None,
) -> None:
    """
    供外部脚本调用，动态修改仿真核心参数。
    未传入的参数保持当前值不变；不传参时所有参数均为模块加载时的默认值。

    使用示例：
        import simulation_core as sim
        sim.set_simulation_params(origin_lat=39.9042, origin_lon=116.4074, cruise_speed=20.0)
    """
    global ORIGIN_LAT, ORIGIN_LON, RE_EARTH, SIM_RADIUS_M
    global CLIMB_RATE, CRUISE_SPEED, MAX_HORIZ_ACCEL, MAX_VERT_ACCEL
    global MIN_CRUISE_ALT, MAX_CRUISE_ALT

    if origin_lat is not None:
        ORIGIN_LAT = origin_lat
    if origin_lon is not None:
        ORIGIN_LON = origin_lon
    if re_earth is not None:
        RE_EARTH = re_earth
    if sim_radius_m is not None:
        SIM_RADIUS_M = sim_radius_m
    if climb_rate is not None:
        CLIMB_RATE = climb_rate
    if cruise_speed is not None:
        CRUISE_SPEED = cruise_speed
    if max_horiz_accel is not None:
        MAX_HORIZ_ACCEL = max_horiz_accel
    if max_vert_accel is not None:
        MAX_VERT_ACCEL = max_vert_accel
    if min_cruise_alt is not None:
        MIN_CRUISE_ALT = min_cruise_alt
    if max_cruise_alt is not None:
        MAX_CRUISE_ALT = max_cruise_alt


def geo_kwargs_from_env(env_module=None) -> Dict[str, float]:
    """从 env 读取 ORIGIN_LAT/ORIGIN_LON/SIM_RADIUS_M（支持大小写别名），未设置则返回空 dict。"""
    if env_module is None:
        env_module = _env
    out: Dict[str, float] = {}
    for param, names in (
        ("origin_lat", ("ORIGIN_LAT", "origin_lat")),
        ("origin_lon", ("ORIGIN_LON", "origin_lon")),
        ("sim_radius_m", ("SIM_RADIUS_M", "sim_radius_m")),
    ):
        for name in names:
            val = getattr(env_module, name, None)
            if val is not None:
                out[param] = float(val)
                break
    return out


# 无人机标识符列表：(uniqueProductIdentificationCode, realNameRegistrationSign)
# 第一列为20位唯一产品识别码，第二列为实名登记标识，按顺序循环分配给生成的无人机
UAV_IDENTIFIERS = [
    ("DJI1MAV101A2B3C4D5E6", "UAS01DJI1MAV001"),
    ("DJI1MAV1F7G8H9J0K1L2", "UAS01DJI1MAV002"),
    ("DJI1MAV2M3N4P5Q6R7S8", "UAS01DJI1MAV003"),
    ("DJI1MAV2T9U0V1W2X3Y4", "UAS01DJI1MAV004"),
    ("DJI1MAV3Z5A6B7C8D9E0", "UAS01DJI1MAV005"),
    ("DJI1PHN4F1G2H3J4K5L6", "UAS01DJI1PHN001"),
    ("DJI1PHN4M7N8P9Q0R1S2", "UAS01DJI1PHN002"),
    ("DJI1PHN4T3U4V5W6X7Y8", "UAS01DJI1PHN003"),
    ("DJI1AIR5Z9A0B1C2D3E4", "UAS01DJI1AIR001"),
    ("DJI1AIR5F5G6H7J8K9L0", "UAS01DJI1AIR002"),
    ("DJI1AIR5M1N2P3Q4R5S6", "UAS01DJI1AIR003"),
    ("DJI1M3P0T7U8V9W0X1Y2", "UAS01DJI1M3P001"),
    ("DJI1M3P0Z3A4B5C6D7E8", "UAS01DJI1M3P002"),
    ("DJI1M3P0F9G0H1J2K3L4", "UAS01DJI1M3P003"),
    ("DJI1M3P0M5N6P7Q8R9S0", "UAS01DJI1M3P004"),
    ("DJI1M3P0T1U2V3W4X5Y6", "UAS01DJI1M3P005"),
    ("DJI1M3P0Z7A8B9C0D1E2", "UAS01DJI1M3P006"),
    ("DJI1M3P0F3G4H5J6K7L8", "UAS01DJI1M3P007"),
    ("DJI1M3P0M9N0P1Q2R3S4", "UAS01DJI1M3P008"),
    ("DJI1M3P0T5U6V7W8X9Y0", "UAS01DJI1M3P009"),
    ("DJI1M3P0Z1A2B3C4D5E6", "UAS01DJI1M3P010"),
    ("DJI1M3P0F7G8H9J0K1L2", "UAS01DJI1M3P011"),
    ("DJI1M3P0M3N4P5Q6R7S8", "UAS01DJI1M3P012"),
    ("DJI1M3P0T9U0V1W2X3Y4", "UAS01DJI1M3P013"),
    ("DJI1M3P0Z5A6B7C8D9E0", "UAS01DJI1M3P014"),
    ("DJI1M3P0F1G2H3J4K5L6", "UAS01DJI1M3P015"),
    ("DJI1M3P0M7N8P9Q0R1S2", "UAS01DJI1M3P016"),
    ("DJI1M3P0T3U4V5W6X7Y8", "UAS01DJI1M3P017"),
    ("DJI1M3P0Z9A0B1C2D3E4", "UAS01DJI1M3P018"),
    ("DJI1M3P0F5G6H7J8K9L0", "UAS01DJI1M3P019"),
    ("EH18S216M1N2P3Q4R5S6", "UAS02EH18S21601"),
    ("EH18S216T7U8V9W0X1Y2", "UAS02EH18S21602"),
    ("EH18S216Z3A4B5C6D7E8", "UAS02EH18S21603"),
    ("EH18S216F9G0H1J2K3L4", "UAS02EH18S21604"),
    ("EH18S216M5N6P7Q8R9S0", "UAS02EH18S21605"),
    ("EH18S216T1U2V3W4X5Y6", "UAS02EH18S21606"),
    ("EH18S216Z7A8B9C0D1E2", "UAS02EH18S21607"),
    ("EH18S216F3G4H5J6K7L8", "UAS02EH18S21608"),
    ("EH18S216M9N0P1Q2R3S4", "UAS02EH18S21609"),
    ("EH18S216T5U6V7W8X9Y0", "UAS02EH18S21610"),
    ("EH18S216Z1A2B3C4D5E6", "UAS02EH18S21611"),
    ("EH18S216F7G8H9J0K1L2", "UAS02EH18S21612"),
    ("EH18S216M3N4P5Q6R7S8", "UAS02EH18S21613"),
    ("EH18S216T9U0V1W2X3Y4", "UAS02EH18S21614"),
    ("EH18S216Z5A6B7C8D9E0", "UAS02EH18S21615"),
    ("EH18S216F1G2H3J4K5L6", "UAS02EH18S21616"),
    ("EH18S216M7N8P9Q0R1S2", "UAS02EH18S21617"),
    ("EH18S216T3U4V5W6X7Y8", "UAS02EH18S21618"),
    ("EH18S216Z9A0B1C2D3E4", "UAS02EH18S21619"),
    ("EH18S216F5G6H7J8K9L0", "UAS02EH18S21620"),
    ("AVICWJ01Z1A2B3C4D5E6", "UAS02EH18S21621"),
    ("AVICWJ01F7G8H9J0K1L2", "UAS02EH18S21622"),
    ("AVICWJ01M3N4P5Q6R7S8", "UAS02EH18S21623"),
    ("AVICWJ01T9U0V1W2X3Y4", "UAS02EH18S21624"),
    ("AVICWJ01Z5A6B7C8D9E0", "UAS02EH18S21625"),
    ("AVICWJ01F1G2H3J4K5L6", "UAS02EH18S21626"),
    ("AVICWJ01M7N8P9Q0R1S2", "UAS02EH18S21627"),
    ("AVICWJ01T3U4V5W6X7Y8", "UAS02EH18S21628"),
    ("AVICWJ01Z9A0B1C2D3E4", "UAS02EH18S21629"),
    ("AVICWJ01F5G6H7J8K9L0", "UAS02EH18S21630"),
    ("AVICWJ01M1N2P3Q4R5S6", "UAS03AVICWJ0101"),
    ("AVICWJ01T7U8V9W0X1Y2", "UAS03AVICWJ0102"),
    ("AVICWJ01Z3A4B5C6D7E8", "UAS03AVICWJ0103"),
    ("AVICWJ01F9G0H1J2K3L4", "UAS03AVICWJ0104"),
    ("AVICWJ01M5N6P7Q8R9S0", "UAS03AVICWJ0105"),
    ("AVICWJ01T1U2V3W4X5Y6", "UAS03AVICWJ0106"),
    ("AVICWJ01Z7A8B9C0D1E2", "UAS03AVICWJ0107"),
    ("AVICWJ01F3G4H5J6K7L8", "UAS03AVICWJ0108"),
    ("AVICWJ01M9N0P1Q2R3S4", "UAS03AVICWJ0109"),
    ("AVICWJ01T5U6V7W8X9Y0", "UAS03AVICWJ0110"),
    ("0A9ZVA01M1N2P3Q4R5S6", "UAS03AVICWJ0111"),
    ("0A9ZVA01T7U8V9W0X1Y2", "UAS03AVICWJ0112"),
    ("0A9ZVA01Z3A4B5C6D7E8", "UAS03AVICWJ0113"),
    ("0A9ZVA01F9G0H1J2K3L4", "UAS03AVICWJ0114"),
    ("0A9ZVA01M5N6P7Q8R9S0", "UAS03AVICWJ0115"),
    ("0A9ZVA01T1U2V3W4X5Y6", "UAS03AVICWJ0116"),
    ("0A9ZVA01Z7A8B9C0D1E2", "UAS03AVICWJ0117"),
    ("0A9ZVA01F3G4H5J6K7L8", "UAS03AVICWJ0118"),
    ("0A9ZVA01M9N0P1Q2R3S4", "UAS03AVICWJ0119"),
    ("0A9ZVA01T5U6V7W8X9Y0", "UAS03AVICWJ0120"),
    ("0A9ZVA01Z1A2B3C4D5E6", "UAS03AVICWJ0121"),
    ("0A9ZVA01F7G8H9J0K1L2", "UAS03AVICWJ0122"),
    ("0A9ZVA01M3N4P5Q6R7S8", "UAS03AVICWJ0123"),
    ("0A9ZVA01T9U0V1W2X3Y4", "UAS03AVICWJ0124"),
    ("0A9ZVA01Z5A6B7C8D9E0", "UAS03AVICWJ0125"),
    ("0A9ZVA01F1G2H3J4K5L6", "UAS03AVICWJ0126"),
    ("0A9ZVA01M7N8P9Q0R1S2", "UAS03AVICWJ0127"),
    ("0A9ZVA01T3U4V5W6X7Y8", "UAS03AVICWJ0128"),
    ("0A9ZVA01Z9A0B1C2D3E4", "UAS03AVICWJ0129"),
    ("0A9ZVA01F5G6H7J8K9L0", "UAS03AVICWJ0130"),
    ("B3C8AG10Z1A2B3C4D5E6", "UAS040A9ZVA0101"),
    ("B3C8AG10F7G8H9J0K1L2", "UAS040A9ZVA0102"),
    ("B3C8AG10M3N4P5Q6R7S8", "UAS040A9ZVA0103"),
    ("B3C8AG10T9U0V1W2X3Y4", "UAS040A9ZVA0104"),
    ("B3C8AG10Z5A6B7C8D9E0", "UAS040A9ZVA0105"),
    ("B3C8AG10F1G2H3J4K5L6", "UAS040A9ZVA0106"),
    ("B3C8AG10M7N8P9Q0R1S2", "UAS040A9ZVA0107"),
    ("B3C8AG10T3U4V5W6X7Y8", "UAS040A9ZVA0108"),
    ("B3C8AG10Z9A0B1C2D3E4", "UAS040A9ZVA0109"),
    ("B3C8AG10F5G6H7J8K9L0", "UAS040A9ZVA0110"),
    ("B3C8AG10M1N2P3Q4R5S6", "UAS040A9ZVA0111"),
    ("B3C8AG10T7U8V9W0X1Y2", "UAS040A9ZVA0112"),
    ("B3C8AG10Z3A4B5C6D7E8", "UAS040A9ZVA0113"),
    ("B3C8AG10F9G0H1J2K3L4", "UAS040A9ZVA0114"),
    ("B3C8AG10M5N6P7Q8R9S0", "UAS040A9ZVA0115"),
    ("B3C8AG10T1U2V3W4X5Y6", "UAS040A9ZVA0116"),
    ("B3C8AG10Z7A8B9C0D1E2", "UAS040A9ZVA0117"),
    ("B3C8AG10F3G4H5J6K7L8", "UAS040A9ZVA0118"),
    ("B3C8AG10M9N0P1Q2R3S4", "UAS040A9ZVA0119"),
    ("B3C8AG10T5U6V7W8X9Y0", "UAS040A9ZVA0120"),
    ("XPLRSVY2M1N2P3Q4R5S6", "UAS040A9ZVA0121"),
    ("XPLRSVY2T7U8V9W0X1Y2", "UAS040A9ZVA0122"),
    ("XPLRSVY2Z3A4B5C6D7E8", "UAS040A9ZVA0123"),
    ("XPLRSVY2F9G0H1J2K3L4", "UAS040A9ZVA0124"),
    ("XPLRSVY2M5N6P7Q8R9S0", "UAS040A9ZVA0125"),
    ("XPLRSVY2T1U2V3W4X5Y6", "UAS040A9ZVA0126"),
    ("XPLRSVY2Z7A8B9C0D1E2", "UAS040A9ZVA0127"),
    ("XPLRSVY2F3G4H5J6K7L8", "UAS040A9ZVA0128"),
    ("XPLRSVY2M9N0P1Q2R3S4", "UAS040A9ZVA0129"),
    ("XPLRSVY2T5U6V7W8X9Y0", "UAS040A9ZVA0130"),
    ("XPLRSVY2Z1A2B3C4D5E6", "UAS05B3C8AG1001"),
    ("XPLRSVY2F7G8H9J0K1L2", "UAS05B3C8AG1002"),
    ("XPLRSVY2M3N4P5Q6R7S8", "UAS05B3C8AG1003"),
    ("XPLRSVY2T9U0V1W2X3Y4", "UAS05B3C8AG1004"),
    ("XPLRSVY2Z5A6B7C8D9E0", "UAS05B3C8AG1005"),
    ("XPLRSVY2F1G2H3J4K5L6", "UAS05B3C8AG1006"),
    ("XPLRSVY2M7N8P9Q0R1S2", "UAS05B3C8AG1007"),
    ("XPLRSVY2T3U4V5W6X7Y8", "UAS05B3C8AG1008"),
    ("XPLRSVY2Z9A0B1C2D3E4", "UAS05B3C8AG1009"),
    ("XPLRSVY2F5G6H7J8K9L0", "UAS05B3C8AG1010"),
    ("5GDRNC01Z1A2B3C4D5E6", "UAS05B3C8AG1011"),
    ("5GDRNC01F7G8H9J0K1L2", "UAS05B3C8AG1012"),
    ("5GDRNC01M3N4P5Q6R7S8", "UAS05B3C8AG1013"),
    ("5GDRNC01T9U0V1W2X3Y4", "UAS05B3C8AG1014"),
    ("5GDRNC01Z5A6B7C8D9E0", "UAS05B3C8AG1015"),
    ("5GDRNC01F1G2H3J4K5L6", "UAS05B3C8AG1016"),
    ("5GDRNC01M7N8P9Q0R1S2", "UAS05B3C8AG1017"),
    ("5GDRNC01T3U4V5W6X7Y8", "UAS05B3C8AG1018"),
    ("5GDRNC01Z9A0B1C2D3E4", "UAS05B3C8AG1019"),
    ("5GDRNC01F5G6H7J8K9L0", "UAS05B3C8AG1020"),
    ("5GDRNC01M1N2P3Q4R5S6", "UAS05B3C8AG1021"),
    ("5GDRNC01T7U8V9W0X1Y2", "UAS05B3C8AG1022"),
    ("5GDRNC01Z3A4B5C6D7E8", "UAS05B3C8AG1023"),
    ("5GDRNC01F9G0H1J2K3L4", "UAS05B3C8AG1024"),
    ("5GDRNC01M5N6P7Q8R9S0", "UAS05B3C8AG1025"),
    ("5GDRNC01T1U2V3W4X5Y6", "UAS05B3C8AG1026"),
    ("5GDRNC01Z7A8B9C0D1E2", "UAS05B3C8AG1027"),
    ("5GDRNC01F3G4H5J6K7L8", "UAS05B3C8AG1028"),
    ("5GDRNC01M9N0P1Q2R3S4", "UAS05B3C8AG1029"),
    ("5GDRNC01T5U6V7W8X9Y0", "UAS05B3C8AG1030"),
    ("KSTKLOG3M1N2P3Q4R5S6", "UAS06XPLRSVY201"),
    ("KSTKLOG3T7U8V9W0X1Y2", "UAS06XPLRSVY202"),
    ("KSTKLOG3Z3A4B5C6D7E8", "UAS06XPLRSVY203"),
    ("KSTKLOG3F9G0H1J2K3L4", "UAS06XPLRSVY204"),
    ("KSTKLOG3M5N6P7Q8R9S0", "UAS06XPLRSVY205"),
    ("KSTKLOG3T1U2V3W4X5Y6", "UAS06XPLRSVY206"),
    ("KSTKLOG3Z7A8B9C0D1E2", "UAS06XPLRSVY207"),
    ("KSTKLOG3F3G4H5J6K7L8", "UAS06XPLRSVY208"),
    ("KSTKLOG3M9N0P1Q2R3S4", "UAS06XPLRSVY209"),
    ("KSTKLOG3T5U6V7W8X9Y0", "UAS06XPLRSVY210"),
    ("KSTKLOG3Z1A2B3C4D5E6", "UAS06XPLRSVY211"),
    ("KSTKLOG3F7G8H9J0K1L2", "UAS06XPLRSVY212"),
    ("KSTKLOG3M3N4P5Q6R7S8", "UAS06XPLRSVY213"),
    ("KSTKLOG3T9U0V1W2X3Y4", "UAS06XPLRSVY214"),
    ("KSTKLOG3Z5A6B7C8D9E0", "UAS06XPLRSVY215"),
    ("KSTKLOG3F1G2H3J4K5L6", "UAS06XPLRSVY216"),
    ("KSTKLOG3M7N8P9Q0R1S2", "UAS06XPLRSVY217"),
    ("KSTKLOG3T3U4V5W6X7Y8", "UAS06XPLRSVY218"),
    ("KSTKLOG3Z9A0B1C2D3E4", "UAS06XPLRSVY219"),
    ("KSTKLOG3F5G6H7J8K9L0", "UAS06XPLRSVY220"),
    ("7H9FSEC4Z1A2B3C4D5E6", "UAS06XPLRSVY221"),
    ("7H9FSEC4F7G8H9J0K1L2", "UAS06XPLRSVY222"),
    ("7H9FSEC4M3N4P5Q6R7S8", "UAS06XPLRSVY223"),
    ("7H9FSEC4T9U0V1W2X3Y4", "UAS06XPLRSVY224"),
    ("7H9FSEC4Z5A6B7C8D9E0", "UAS06XPLRSVY225"),
    ("7H9FSEC4F1G2H3J4K5L6", "UAS06XPLRSVY226"),
    ("7H9FSEC4M7N8P9Q0R1S2", "UAS06XPLRSVY227"),
    ("7H9FSEC4T3U4V5W6X7Y8", "UAS06XPLRSVY228"),
    ("7H9FSEC4Z9A0B1C2D3E4", "UAS06XPLRSVY229"),
    ("7H9FSEC4F5G6H7J8K9L0", "UAS06XPLRSVY230"),
    ("7H9FSEC4M1N2P3Q4R5S6", "UAS075GDRNC0101"),
    ("7H9FSEC4T7U8V9W0X1Y2", "UAS075GDRNC0102"),
    ("7H9FSEC4Z3A4B5C6D7E8", "UAS075GDRNC0103"),
    ("7H9FSEC4F9G0H1J2K3L4", "UAS075GDRNC0104"),
    ("7H9FSEC4M5N6P7Q8R9S0", "UAS075GDRNC0105"),
    ("7H9FSEC4T1U2V3W4X5Y6", "UAS075GDRNC0106"),
    ("7H9FSEC4Z7A8B9C0D1E2", "UAS075GDRNC0107"),
    ("7H9FSEC4F3G4H5J6K7L8", "UAS075GDRNC0108"),
    ("7H9FSEC4M9N0P1Q2R3S4", "UAS075GDRNC0109"),
    ("7H9FSEC4T5U6V7W8X9Y0", "UAS075GDRNC0110"),
    ("ZKJXVT05M1N2P3Q4R5S6", "UAS075GDRNC0111"),
    ("ZKJXVT05T7U8V9W0X1Y2", "UAS075GDRNC0112"),
    ("ZKJXVT05Z3A4B5C6D7E8", "UAS075GDRNC0113"),
    ("ZKJXVT05F9G0H1J2K3L4", "UAS075GDRNC0114"),
    ("ZKJXVT05M5N6P7Q8R9S0", "UAS075GDRNC0115"),
    ("ZKJXVT05T1U2V3W4X5Y6", "UAS075GDRNC0116"),
    ("ZKJXVT05Z7A8B9C0D1E2", "UAS075GDRNC0117"),
    ("ZKJXVT05F3G4H5J6K7L8", "UAS075GDRNC0118"),
    ("ZKJXVT05M9N0P1Q2R3S4", "UAS075GDRNC0119"),
    ("ZKJXVT05T5U6V7W8X9Y0", "UAS075GDRNC0120"),
    ("ZKJXVT05Z1A2B3C4D5E6", "UAS075GDRNC0121"),
    ("ZKJXVT05F7G8H9J0K1L2", "UAS075GDRNC0122"),
    ("ZKJXVT05M3N4P5Q6R7S8", "UAS075GDRNC0123"),
    ("ZKJXVT05T9U0V1W2X3Y4", "UAS075GDRNC0124"),
    ("ZKJXVT05Z5A6B7C8D9E0", "UAS075GDRNC0125"),
    ("ZKJXVT05F1G2H3J4K5L6", "UAS075GDRNC0126"),
    ("ZKJXVT05M7N8P9Q0R1S2", "UAS075GDRNC0127"),
    ("ZKJXVT05T3U4V5W6X7Y8", "UAS075GDRNC0128"),
    ("ZKJXVT05Z9A0B1C2D3E4", "UAS075GDRNC0129"),
    ("ZKJXVT05F5G6H7J8K9L0", "UAS075GDRNC0130"),
    ("ZKJXVT05F5G6H7J8K9L1", "UAS08KSTKLOG301"),
    ("ZKJXVT05F5G6H7J8K9L2", "UAS08KSTKLOG302"),
    ("ZKJXVT05F5G6H7J8K9L3", "UAS08KSTKLOG303"),
    ("ZKJXVT05F5G6H7J8K9L4", "UAS08KSTKLOG304"),
    ("ZKJXVT05F5G6H7J8K9L5", "UAS08KSTKLOG305"),
    ("ZKJXVT05F5G6H7J8K9L6", "UAS08KSTKLOG306"),
    ("ZKJXVT05F5G6H7J8K9L7", "UAS08KSTKLOG307"),
    ("ZKJXVT05F5G6H7J8K9L8", "UAS08KSTKLOG308"),
    ("ZKJXVT05F5G6H7J8K9L9", "UAS08KSTKLOG309"),
    ("ZKJXVT05F5G6H7J8K910", "UAS08KSTKLOG310"),
    ("ZKJXVT05F5G6H7J8K911", "UAS08KSTKLOG311"),
    ("ZKJXVT05F5G6H7J8K912", "UAS08KSTKLOG312"),
    ("ZKJXVT05F5G6H7J8K913", "UAS08KSTKLOG313"),
    ("ZKJXVT05F5G6H7J8K914", "UAS08KSTKLOG314"),
    ("ZKJXVT05F5G6H7J8K915", "UAS08KSTKLOG315"),
    ("ZKJXVT05F5G6H7J8K916", "UAS08KSTKLOG316"),
    ("ZKJXVT05F5G6H7J8K917", "UAS08KSTKLOG317"),
    ("ZKJXVT05F5G6H7J8K918", "UAS08KSTKLOG318"),
    ("ZKJXVT05F5G6H7J8K919", "UAS08KSTKLOG319"),
    ("ZKJXVT05F5G6H7J8K920", "UAS08KSTKLOG320"),
    ("ZKJXVT05F5G6H7J8K921", "UAS08KSTKLOG321"),
    ("ZKJXVT05F5G6H7J8K922", "UAS08KSTKLOG322"),
    ("ZKJXVT05F5G6H7J8K923", "UAS08KSTKLOG323"),
    ("ZKJXVT05F5G6H7J8K924", "UAS08KSTKLOG324"),
    ("ZKJXVT05F5G6H7J8K925", "UAS08KSTKLOG325"),
    ("ZKJXVT05F5G6H7J8K926", "UAS08KSTKLOG326"),
    ("ZKJXVT05F5G6H7J8K927", "UAS08KSTKLOG327"),
    ("ZKJXVT05F5G6H7J8K928", "UAS08KSTKLOG328"),
    ("ZKJXVT05F5G6H7J8K929", "UAS08KSTKLOG329"),
    ("ZKJXVT05F5G6H7J8K930", "UAS08KSTKLOG330"),
    ("ZKJXVT05F5G6H7J8K931", "UAS097H9FSEC401"),
    ("ZKJXVT05F5G6H7J8K932", "UAS097H9FSEC402"),
    ("ZKJXVT05F5G6H7J8K933", "UAS097H9FSEC403"),
    ("ZKJXVT05F5G6H7J8K934", "UAS097H9FSEC404"),
    ("ZKJXVT05F5G6H7J8K935", "UAS097H9FSEC405"),
    ("ZKJXVT05F5G6H7J8K936", "UAS097H9FSEC406"),
    ("ZKJXVT05F5G6H7J8K937", "UAS097H9FSEC407"),
    ("ZKJXVT05F5G6H7J8K938", "UAS097H9FSEC408"),
    ("ZKJXVT05F5G6H7J8K939", "UAS097H9FSEC409"),
    ("ZKJXVT05F5G6H7J8K940", "UAS097H9FSEC410"),
    ("ZKJXVT05F5G6H7J8K941", "UAS097H9FSEC411"),
    ("ZKJXVT05F5G6H7J8K942", "UAS097H9FSEC412"),
    ("ZKJXVT05F5G6H7J8K943", "UAS097H9FSEC413"),
    ("ZKJXVT05F5G6H7J8K944", "UAS097H9FSEC414"),
    ("ZKJXVT05F5G6H7J8K945", "UAS097H9FSEC415"),
    ("ZKJXVT05F5G6H7J8K946", "UAS097H9FSEC416"),
    ("ZKJXVT05F5G6H7J8K947", "UAS097H9FSEC417"),
    ("ZKJXVT05F5G6H7J8K948", "UAS097H9FSEC418"),
    ("ZKJXVT05F5G6H7J8K949", "UAS097H9FSEC419"),
    ("ZKJXVT05F5G6H7J8K950", "UAS097H9FSEC420"),
    ("ZKJXVT05F5G6H7J8K951", "UAS097H9FSEC421"),
    ("ZKJXVT05F5G6H7J8K952", "UAS097H9FSEC422"),
    ("ZKJXVT05F5G6H7J8K953", "UAS097H9FSEC423"),
    ("ZKJXVT05F5G6H7J8K954", "UAS097H9FSEC424"),
    ("ZKJXVT05F5G6H7J8K955", "UAS097H9FSEC425"),
    ("ZKJXVT05F5G6H7J8K956", "UAS097H9FSEC426"),
    ("ZKJXVT05F5G6H7J8K957", "UAS097H9FSEC427"),
    ("ZKJXVT05F5G6H7J8K958", "UAS097H9FSEC428"),
    ("ZKJXVT05F5G6H7J8K959", "UAS097H9FSEC429"),
    ("ZKJXVT05F5G6H7J8K960", "UAS097H9FSEC430"),
    ("ZKJXVT05F5G6H7J8K961", "UAS10ZKJXVT0501"),
    ("ZKJXVT05F5G6H7J8K962", "UAS10ZKJXVT0502"),
    ("ZKJXVT05F5G6H7J8K963", "UAS10ZKJXVT0503"),
    ("ZKJXVT05F5G6H7J8K964", "UAS10ZKJXVT0504"),
    ("ZKJXVT05F5G6H7J8K965", "UAS10ZKJXVT0505"),
    ("ZKJXVT05F5G6H7J8K966", "UAS10ZKJXVT0506"),
    ("ZKJXVT05F5G6H7J8K967", "UAS10ZKJXVT0507"),
    ("ZKJXVT05F5G6H7J8K968", "UAS10ZKJXVT0508"),
    ("ZKJXVT05F5G6H7J8K969", "UAS10ZKJXVT0509"),
    ("ZKJXVT05F5G6H7J8K970", "UAS10ZKJXVT0510"),
    ("ZKJXVT05F5G6H7J8K971", "UAS10ZKJXVT0511"),
    ("ZKJXVT05F5G6H7J8K972", "UAS10ZKJXVT0512"),
    ("ZKJXVT05F5G6H7J8K973", "UAS10ZKJXVT0513"),
    ("ZKJXVT05F5G6H7J8K974", "UAS10ZKJXVT0514"),
    ("ZKJXVT05F5G6H7J8K975", "UAS10ZKJXVT0515"),
    ("ZKJXVT05F5G6H7J8K976", "UAS10ZKJXVT0516"),
    ("ZKJXVT05F5G6H7J8K977", "UAS10ZKJXVT0517"),
    ("ZKJXVT05F5G6H7J8K978", "UAS10ZKJXVT0518"),
    ("ZKJXVT05F5G6H7J8K979", "UAS10ZKJXVT0519"),
    ("ZKJXVT05F5G6H7J8K980", "UAS10ZKJXVT0520"),
    ("ZKJXVT05F5G6H7J8K981", "UAS10ZKJXVT0521"),
    ("ZKJXVT05F5G6H7J8K982", "UAS10ZKJXVT0522"),
    ("ZKJXVT05F5G6H7J8K983", "UAS10ZKJXVT0523"),
    ("ZKJXVT05F5G6H7J8K984", "UAS10ZKJXVT0524"),
    ("ZKJXVT05F5G6H7J8K985", "UAS10ZKJXVT0525"),
    ("ZKJXVT05F5G6H7J8K986", "UAS10ZKJXVT0526"),
    ("ZKJXVT05F5G6H7J8K987", "UAS10ZKJXVT0527"),
    ("ZKJXVT05F5G6H7J8K988", "UAS10ZKJXVT0528"),
    ("ZKJXVT05F5G6H7J8K989", "UAS10ZKJXVT0529"),
    ("ZKJXVT05F5G6H7J8K990", "UAS10ZKJXVT0530"),
]
UAV_IDENTIFIERS2 = [

]
# 由 env.ids_index 决定仅使用哪张表：1=UAV_IDENTIFIERS，2=UAV_IDENTIFIERS2；未配置时默认为 1
_idx = getattr(_env, "ids_index", 1)
ACTIVE_UAV_IDENTIFIERS: List[tuple[str, str]] = (
    UAV_IDENTIFIERS2 if _idx == 2 else UAV_IDENTIFIERS
)
# 超出上表条数时再生成 uid；与表中示例一致的 20 位（大写字母与数字）
_RND_UID_ALPHABET = string.ascii_uppercase + string.digits


def _random_aircraft_uid() -> str:
    """超出当前选用标识表（ACTIVE_UAV_IDENTIFIERS）条数时：随机生成 20 位唯一产品识别码。"""
    return "".join(random.choices(_RND_UID_ALPHABET, k=20))


def _random_registration_sign(uid: str) -> str:
    """与项目中示例风格相近的实名登记字符串（随机后缀）。"""
    return f"UAS{random.randint(1, 99):02d}RND{uid[-9:]}"


def sourceType_for_uid(uid: str) -> int:
    """
    按 uid 稳定分配 sourceType：1=无人机，2=ADS-B。
    使用哈希低位保证同一 uid 始终相同，不同 uid 上近似各半。
    """
    return 1
    b = hashlib.md5(uid.encode("utf-8")).digest()[0]
    return 1 + (b & 1)


# ADS-B 附加字段用航班前缀（与示例 CCA1214 等风格一致）
_ADS_B_CALLSIGN_PREFIXES = (
    "CCA", "CSN", "CES", "CHH", "CQH", "CDG", "CSZ", "DKH", "GCR", "HBH",
)


def ads_b_addInf_for_uid(uid: str) -> Dict[str, Any]:
    """
    sourceType=2 时 addInf：cs 航班号、sil 监视完好性水平 1～10、ssr 应答机代码字符串。
    同一 uid 结果固定。
    """
    d = hashlib.md5(uid.encode("utf-8")).digest()
    prefix = _ADS_B_CALLSIGN_PREFIXES[d[0] % len(_ADS_B_CALLSIGN_PREFIXES)]
    flight_no = 100 + (d[1] * 256 + d[2]) % 8900
    sil = 1 + (d[3] % 10)
    ssr_code = 1000 + (d[4] * 256 + d[5]) % 7000
    return {
        "cs": f"{prefix}{flight_no}",
        "sil": sil,
        "ssr": f"{ssr_code:04d}",
    }


def meters_to_geo(lat: float, lon: float, dn: float, de: float) -> tuple[float, float]:
    """
    将局部东北坐标（米）转换为经纬度增量（粗略等距投影）
    
    Args:
        lat: 当前纬度（度）
        lon: 当前经度（度）
        dn: 北向位移（米，正北为正）
        de: 东向位移（米，正东为正）
    
    Returns:
        (新纬度, 新经度)
    """
    d_lat = dn / RE_EARTH
    d_lon = de / (RE_EARTH * math.cos(math.radians(lat)))
    return lat + math.degrees(d_lat), lon + math.degrees(d_lon)


class DroneAgent:
    """ 单架无人机仿真代理，包含简单动力学、状态机、带噪声的观测模拟 """

    def __init__(
        self,
        plan: FlightPlan,
        cruise_speed: Optional[float] = None,
        registration_sign_override: Optional[str] = None,
    ):
        self.plan = plan
        self.uid = plan.aircraft.uid.decode('utf-8')
        self.sourceType = sourceType_for_uid(self.uid)
        self.addInf = ads_b_addInf_for_uid(self.uid) if self.sourceType == 2 else None
        if registration_sign_override is not None:
            self.reg_sign = registration_sign_override
        else:
            self.reg_sign = next((ident[1] for ident in ACTIVE_UAV_IDENTIFIERS if ident[0] == self.uid), self.uid)

        # 状态机定义：
        # 0:IDLE（等待起飞时间）
        # 1:TAKEOFF（爬升）
        # 2:CRUISE（航路/任务飞行）
        # 3:HOVER（定点盘旋/等待）
        # 4:LANDING（下降）
        # 5:FINISHED（任务完成，已落地）
        self.state = 0
        self.current_wp_idx = 0

        # 历史轨迹缓存（供卡尔曼滤波使用），最多保留最近10帧
        self.history_buffer = deque(maxlen=10)

        # 初始化真实位置（不含噪声）
        if plan.type == 0:  # TRAJ 航路模式
            start_p = plan.data.traj.wps[0].point
        else:  # POLY 区域模式
            start_p = plan.data.area.vertices[0]

        self.lat = start_p.lat
        self.lon = start_p.lon
        self.alt = 0.0

        # 真实速度分量（北-东-地，m/s）
        self.vn = self.ve = self.vd = 0.0
        self.heading = 0.0  # 航向（度，北向0°顺时针）

        # 性能参数：未指定时带随机性模拟不同无人机；add_plans 等外部计划可固定为 CRUISE_SPEED
        if cruise_speed is not None:
            self.cruise_speed = cruise_speed
        else:
            self.cruise_speed = CRUISE_SPEED * random.uniform(0.6, 1.5)
        self.climb_rate = CLIMB_RATE                         # 爬升/下降率 m/s
        self.hover_timer = 0.0                             # 悬停计时器

        # 目标高度确定
        if plan.type == 0 and plan.data.traj.count > 1:
            self.target_alt = plan.data.traj.wps[1].point.alt
        else:
            self.target_alt = (plan.data.area.min_alt + plan.data.area.max_alt) / 2

        # GPS位置测量噪声标准差（米）
        self.pos_noise_std = 1.0

    def update(self, current_time: float, dt: float):
        """
        无人机状态更新主入口（每步调用）
        
        Args:
            current_time: 当前仿真时间（秒，time.time()）
            dt: 时间步长（秒）
        """
        # 未到起飞时间 → 保持IDLE
        if current_time < self.plan.start_time:
            self.state = 0
            return

        # 首次进入起飞阶段
        if self.state == 0:
            self.state = 1

        # 根据任务类型更新运动逻辑
        if self.plan.type == 0:
            self._update_trajectory_mode(dt)
        else:
            self._update_loiter_mode(dt, current_time)

        # ----------------------
        # 真实物理位置更新（无噪声）
        # ----------------------
        self.lat, self.lon = meters_to_geo(self.lat, self.lon, self.vn * dt, self.ve * dt)
        self.alt += self.vd * dt
        self.alt = max(0.0, self.alt)  # 防止坠地到负高度



        self.meas_lat, self.meas_lon = self.lat, self.lon
        self.meas_alt = self.alt

        # ----------------------
        # 保存带噪声的历史轨迹（供C++端卡尔曼滤波回放）
        # ----------------------
        if self.state in (1, 2, 3, 4):  # 活跃飞行状态才记录
            snapshot = TelemetrySnapshot()
            snapshot.location = GeoPoint(self.lon, self.lat, self.alt)
            snapshot.timestamp = current_time
            snapshot.h_accuracy = int(self.pos_noise_std)
            snapshot.v_accuracy = int(self.pos_noise_std)
            snapshot.speed_accuracy =int(1.0)
            snapshot.speed = math.sqrt(self.vn**2 + self.ve**2)

            snapshot.heading = self.heading
            if snapshot.heading < 0.0:
                snapshot.heading += 360.0
            snapshot.verticalSpeed = self.vd
            self.history_buffer.append(snapshot)

    def _lerp_vel(self, cur: float, tgt: float, max_rate: float, dt: float) -> float:
        """速度线性插值，单步变化量不超过 max_rate * dt，避免速度突变"""
        diff = tgt - cur
        step = max_rate * dt
        if abs(diff) <= step:
            return tgt
        return cur + math.copysign(step, diff)

    def _update_trajectory_mode(self, dt: float):
        """ 航路点模式（Trajectory）更新逻辑 """
        wps = self.plan.data.traj.wps
        count = self.plan.data.traj.count

        # 到达最后一个航点 → 进入降落
        if self.current_wp_idx >= count - 1:
            self.state = 4

        if self.state == 1:  # TAKEOFF (修改：斜向起飞，同时飞向下一个航点)
            # 1. 计算到下一个航点（WP1）的水平向量
            target = wps[self.current_wp_idx + 1].point
            dn = (target.lat - self.lat) * RE_EARTH * math.pi / 180.0
            de = (target.lon - self.lon) * RE_EARTH * math.cos(math.radians(self.lat)) * math.pi / 180.0
            da = target.alt - self.alt
            h_dist = math.sqrt(dn**2 + de**2 )
            dist = math.sqrt(dn**2 + de**2 + da**2)

            
            # 2. 设置水平速度（朝向目标）
            if h_dist > 10.0:
                self.vn = (dn / dist) * self.cruise_speed
                self.ve = (de / dist) * self.cruise_speed
                # 更新航向
                self.heading = math.degrees(math.atan2(self.ve, self.vn))
                self.vd = (da / dist) * self.cruise_speed
            else:
                self.vn = self.ve = 0.0
            
            # 3. 设置垂直速度（保持爬升率）
                self.vd = self.climb_rate
            
            # 4. 状态切换判断：达到高度 OR 已经到达目标点附近（防止飞过了还在爬升）
            if self.alt >= self.target_alt - 5.0 or dist < self.cruise_speed*dt:
                self.current_wp_idx += 1
                self.state = 2
                # 这里不强制置 vd=0，交由 state=2 的逻辑在下一帧平滑处理

        elif self.state == 2:  # CRUISE
            target = wps[self.current_wp_idx + 1].point
            dn = (target.lat - self.lat) * RE_EARTH * math.pi / 180.0
            de = (target.lon - self.lon) * RE_EARTH * math.cos(math.radians(self.lat)) * math.pi / 180.0
            da = target.alt - self.alt
            dist = math.sqrt(dn**2 + de**2 + da**2)

            # 最后一步：直接到位
            if dist < self.cruise_speed * dt:
                if wps[self.current_wp_idx + 1].stay_duration > 0:
                    self.state = 3
                    self.hover_timer = wps[self.current_wp_idx + 1].stay_duration
                else:
                    self.current_wp_idx += 1
                self.vn = dn / dt
                self.ve = de / dt
                self.vd = da / dt
                self.heading = math.degrees(math.atan2(self.ve, self.vn))
            else:
                # 制动距离内按比例减速，之外全速巡航
                # brake_dist = 4 × v²/(2a)，提前约 4 倍理论制动距离开始减速
                brake_dist = self.cruise_speed ** 2 / (2 * MAX_HORIZ_ACCEL) * 4
                if dist < brake_dist:
                    target_speed = self.cruise_speed * max(dist / brake_dist, 0.05)
                else:
                    target_speed = self.cruise_speed
                vn_tgt = (dn / dist) * target_speed
                ve_tgt = (de / dist) * target_speed
                vd_tgt = (da / dist) * target_speed
                self.vn = self._lerp_vel(self.vn, vn_tgt, MAX_HORIZ_ACCEL, dt)
                self.ve = self._lerp_vel(self.ve, ve_tgt, MAX_HORIZ_ACCEL, dt)
                self.vd = self._lerp_vel(self.vd, vd_tgt, MAX_VERT_ACCEL, dt)
                self.heading = math.degrees(math.atan2(self.ve, self.vn))


        elif self.state == 3:  # HOVER
            self.vn = self.ve = self.vd = 0.0
            self.hover_timer -= dt
            if self.hover_timer <= dt:
                self.current_wp_idx += 1
                self.state = 2

        elif self.state == 4:  # LANDING：水平减速、垂直平滑降落
            self.vn = self._lerp_vel(self.vn, 0.0, MAX_HORIZ_ACCEL, dt)
            self.ve = self._lerp_vel(self.ve, 0.0, MAX_HORIZ_ACCEL, dt)
            self.vd = self._lerp_vel(self.vd, -CLIMB_RATE / 2, MAX_VERT_ACCEL, dt)
            if self.alt <= 0.1:
                self.state = 5

    def _update_loiter_mode(self, dt: float, current_time: float):
        """ 区域盘旋模式（Loiter）更新逻辑 """
        # 简单取对角线中点作为中心
        center = GeoPoint(0.0, 0.0, 0.0)
        center.lat = (self.plan.data.area.vertices[0].lat+self.plan.data.area.vertices[int(self.plan.data.area.vertex_count/2)].lat) / 2
        center.lon = (self.plan.data.area.vertices[0].lon+self.plan.data.area.vertices[int(self.plan.data.area.vertex_count/2)].lon) / 2

        if self.state == 1:  # 起飞爬升
            self.vd = self.climb_rate
            if self.alt >= self.target_alt:
                self.state = 2
                self.vd = 0.0
        elif self.state == 2:  # CRUISE - 圆形盘旋
            # 简单圆形盘旋（半径200m）
            radius = 200.0
            angular_speed = self.cruise_speed / radius
            self.heading += angular_speed * dt * 5.0  # 加速转弯（更明显轨迹）
            rad = math.radians(self.heading)

            # 计算圆周上的目标点
            t_lat, t_lon = meters_to_geo(
                center.lat, center.lon,
                radius * math.cos(rad),
                radius * math.sin(rad)
            )

            # 向目标点飞（修复：使用距离归一化后乘以巡航速度）
            dn = (t_lat - self.lat) * RE_EARTH * math.pi / 180.0
            de = (t_lon - self.lon) * RE_EARTH * math.cos(math.radians(self.lat)) * math.pi / 180.0
            dist = math.sqrt(dn**2 + de**2)
            if dist > 1.0:  # 避免除零
                self.vn = (dn / dist) * self.cruise_speed
                self.ve = (de / dist) * self.cruise_speed
            else:
                self.vn = dn
                self.ve = de
            self.vd = 0.0
            
            # 查看结束时间，如果到达则降落（修复：使用仿真时间而非系统时间）
            if current_time >= self.plan.end_time:
                self.state = 4
            
        if self.state == 4:  # LANDING：水平减速、垂直平滑降落
            self.vn = self._lerp_vel(self.vn, 0.0, MAX_HORIZ_ACCEL, dt)
            self.ve = self._lerp_vel(self.ve, 0.0, MAX_HORIZ_ACCEL, dt)
            self.vd = self._lerp_vel(self.vd, -CLIMB_RATE / 2, MAX_VERT_ACCEL, dt)
            if self.alt <= 0.1:
                self.state = 5
    


    def get_telemetry_payload(self, timestamp: float) -> Dict[str, Any]:
        """
        生成发送给 UTM 引擎的遥测数据包（含当前帧 + 历史轨迹）
        
        Returns:
            包含 "current" 和 "history" 两个字段的字典
        """
        t = TelemetryData()
        t.uid = self.uid.encode('utf-8')
        t.realNameRegistrationSign = self.reg_sign
        t.location = GeoPoint(self.meas_lon, self.meas_lat, self.meas_alt)
        t.classification = self.plan.aircraft.classification
        # 注意：这里速度是含噪声的瞬时值，真实工程中应由滤波器输出
        t.velocity = Vec3(0, 0, 0)
        t.speed = math.sqrt(self.vn**2 + self.ve**2)
        t.heading = self.heading
        if t.heading < 0.0:
            t.heading += 360.0
        t.verticalSpeed = self.vd
        # 高度/垂直安全阈值（用于冲突检测）
        t.longitudinal_threshold = self.plan.aircraft.longitudinal_threshold
        t.lateral_threshold = self.plan.aircraft.lateral_threshold
        t.v_threshold = self.plan.aircraft.v_threshold
        t.timestamp = int(timestamp)
        if self.state == 5:
            t.operatingStatus = 1  # 已落地
        else:
            t.operatingStatus = 2
            
        t.horizontalAccuracy = int(self.pos_noise_std)
        t.verticalAccuracy = int(self.pos_noise_std)
        t.speedAccuracy = int(1.0)
        t.sourceType = self.sourceType
        t.addInf = self.addInf if self.sourceType == 2 else {}
        return {
            "current": t,
            "history": list(self.history_buffer)  # 转换为普通list，方便ctypes传递
        }


class Simulator:
    """ 仿真管理器：负责生成无人机计划、动态禁飞区、推进仿真步进 """

    def __init__(
        self,
        origin_lat: Optional[float] = None,
        origin_lon: Optional[float] = None,
        sim_radius_m: Optional[float] = None,
        uid_start_offset: int = 0,
    ):
        env_geo = geo_kwargs_from_env()
        self.origin_lat = float(
            origin_lat if origin_lat is not None
            else env_geo.get("origin_lat", ORIGIN_LAT)
        )
        self.origin_lon = float(
            origin_lon if origin_lon is not None
            else env_geo.get("origin_lon", ORIGIN_LON)
        )
        self.sim_radius_m = float(
            sim_radius_m if sim_radius_m is not None
            else env_geo.get("sim_radius_m", SIM_RADIUS_M)
        )
        self.agents: Dict[str, DroneAgent] = {}           # uid → DroneAgent
        self.plan_counter = 0
        self.nfz_counter = 0
        self.uid_start_offset = max(0, uid_start_offset)   # 预置 ID 起始偏移量
        self._keep_alive = []   # 防止 ctypes 数组被垃圾回收
        # 每步 step 开始时移除的已落地 agent（state==5），供 main 等打印「降落 / 重飞」日志
        self.last_finished_uids: List[str] = []

    def generate_nfzs(self, count: int) -> List[DynamicNoFlyZone]:
        """
        "noDrone": 3,
    "limited": 4, "danger": 5, "segregated": 6,
        随机生成若干个动态4D禁飞区（带时间窗）
        
        修改点：
        - 禁飞区几何现在为随机凸多边形（3~10个顶点），不再固定为矩形
        - 多边形为近似规则但带随机扰动的凸多边形（保证不自交，便于后续几何计算）
        - 随机半径范围（150~600米），每个顶点半径有轻微扰动
        - 高度范围保持原逻辑（min_alt=0，max_alt 200~1500米）
        
        Returns:
            DynamicNoFlyZone 结构体的列表

        """
        types = ["noDrone","limited","danger","segregated"]
        nfzs = []
        now = time.time()


        for i in range(count):
            type = types[i%len(types)]
            self.nfz_counter += 1
            uid_str = f"NFZ_{self.nfz_counter:03d}"

            # 随机中心位置（仿真圆内）
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(0, self.sim_radius_m * 0.8)
            clat, clon = meters_to_geo(self.origin_lat, self.origin_lon,
                                    dist * math.cos(angle), dist * math.sin(angle))

            # 随机顶点数量（3~10，支持三角形、五边形、八边形等）
            num_vertices = random.randint(3, 10)
            
            # 基础半径（控制禁飞区整体大小，150~600米）
            base_radius = random.uniform(800.0, 6000.0)
            
            # 生成角度（均匀分布 + 轻微随机扰动，确保凸多边形）
            angles = []
            for i in range(num_vertices):
                base_angle = i * 2 * math.pi / num_vertices
                jitter = random.uniform(-math.pi / (num_vertices * 2), math.pi / (num_vertices * 2))
                angles.append(base_angle + jitter)
            
            # 按角度排序（保证顶点顺序为顺时针或逆时针，形成闭合凸多边形）
            angles.sort()
            
            points = []
            for angle in angles:
                # 每个顶点半径带随机扰动（±25%），增加不规则感
                radius = base_radius * random.uniform(0.75, 1.25)
                
                # 角度0指向正北（cos为北向，sin为东向）
                dn = radius * math.cos(angle)  # 北向位移（米）
                de = radius * math.sin(angle)  # 东向位移（米）
                
                plat, plon = meters_to_geo(clat, clon, dn, de)
                points.append(GeoPoint(plon, plat, 0.0))  # GeoPoint(lon, lat, alt)

            # 创建 ctypes 动态数组（长度为 num_vertices）
            arr = (GeoPoint * num_vertices)(*points)
            self._keep_alive.append(arr)  # 防止被GC回收

            nfz = DynamicNoFlyZone()
            nfz.uid = uid_str.encode('utf-8')
            nfz.priority = 100
            nfz.type = NFZ_TYPE_MAP[type]
            nfz.status = NFZ_STATUS_MAP["NFZ_STATUS_PERMANENT"]
            # 原因字段（定长char[64]），可扩展为随机原因（此处保持原样）
            reason = b"Military Exercise"
            ctypes.memmove(nfz.reason, reason, min(len(reason), 63))

            nfz.geometry.vertices = arr
            nfz.geometry.vertex_count = num_vertices
            nfz.geometry.min_alt = 0.0
            nfz.geometry.max_alt = random.uniform(200, 1500)

            # 时间窗：未来0~10分钟开始，持续30~60分钟
            nfz.start_time = now + random.uniform(0, 60)
            nfz.end_time = nfz.start_time + random.uniform(1800, 3600)

            nfzs.append(nfz)

        return nfzs

    def generate_plan(self,type ="plan") -> FlightPlan:
        """
        随机生成一个飞行计划（15%概率为区域盘旋，其余为航路点任务）
        
        修改点：
        - 区域盘旋任务（POLY）现在生成随机凸多边形（3~10个顶点）
        - 多边形为近似规则但带随机扰动的凸多边形（保证不自交，便于后续几何计算）
        - 随机半径范围（150~500米），每个顶点半径有轻微扰动
        - 高度范围更合理：围绕巡航高度 ±50~150米（不再固定从0开始）
        
        Returns:
            FlightPlan 结构体
        """
        self.plan_counter += 1
        registration_sign_override: Optional[str] = None
        idx = self.plan_counter + self.uid_start_offset
        if idx <= len(ACTIVE_UAV_IDENTIFIERS):
            identifier = ACTIVE_UAV_IDENTIFIERS[idx - 1]
            uid_str = identifier[0]
        else:
            # 超过预置 300 条后不再循环复用 uid，改为随机生成，保证多机并发时唯一
            for _ in range(128):
                uid_str = _random_aircraft_uid()
                if uid_str not in self.agents:
                    break
            else:
                # 极端情况下与当前 agents 键冲突时，用序号保证唯一（仍截断为 20 位以内由结构体约束）
                uid_str = (_random_aircraft_uid() + f"{self.plan_counter:X}")[:20]
            registration_sign_override = _random_registration_sign(uid_str)

        plan = FlightPlan()

        # plan.uid = uid_str.encode('utf-8')
        plan.plan_id = self.plan_counter

        plan.priority = random.randint(1, 10)

        now = time.time()
        plan.start_time = now + random.randint(0, 1)   # 起飞
        plan.end_time = plan.start_time + 5400            # 任务时长

        plan.aircraft.uid = uid_str.encode('utf-8')
        
        plan.aircraft.longitudinal_threshold = 200.0
        plan.aircraft.lateral_threshold = 100.0
        plan.aircraft.v_threshold = 100.0
        plan.aircraft.max_speed = CRUISE_SPEED
        random_uav = random.choice(list(UAVClassification))
        plan.aircraft.classification = random_uav.value
        cruise_alt = random.uniform(MIN_CRUISE_ALT, MAX_CRUISE_ALT) # 随机巡航高度
        # if random_uav == UAVClassification.LARGE:
        #     cruise_alt = random.uniform(100.0, 1000.0) # 随机巡航高度（100~1000米）
        # elif random_uav == UAVClassification.MEDIUM:
        #     cruise_alt = random.uniform(50.0, 500.0) # 随机巡航高度（50~500米）
        # elif random_uav == UAVClassification.SMALL:
        #     cruise_alt = random.uniform(20.0, 200.0)
        # elif random_uav == UAVClassification.LIGHT:
        #     cruise_alt = random.uniform(10.0, 100.0)
        # else :
        #     cruise_alt = random.uniform(5.0, 50.0)

        # 随机起始位置（仿真圆内，作为多边形中心）
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0, self.sim_radius_m)
        base_lat, base_lon = meters_to_geo(self.origin_lat, self.origin_lon,
                                        dist * math.cos(angle), dist * math.sin(angle))

        plan_num = random.random()
        if plan_num < 0:  # 15% 概率生成区域盘旋任务（POLY）
            plan.type = 1
            
            # 随机顶点数量（3~10，包含三角形、五边形等）
            num_vertices = random.randint(3, 10)
            
            # 基础半径（控制区域大小）
            base_radius = random.uniform(150.0, 5000.0)
            
            # 生成角度（均匀分布 + 轻微随机扰动，确保凸多边形）
            angles = []
            for i in range(num_vertices):
                # 基础均匀角度 + 小扰动（不超过相邻角度的一半，避免交叉）
                base_angle = i * 2 * math.pi / num_vertices
                jitter = random.uniform(-math.pi / (num_vertices * 2), math.pi / (num_vertices * 2))
                angles.append(base_angle + jitter)
            
            # 按角度排序（保证顺序为顺时针或逆时针，形成闭合凸多边形）
            angles.sort()
            
            points = []
            for angle in angles:
                # 每个顶点半径带随机扰动（±20%），增加不规则感
                radius = base_radius * random.uniform(0.8, 1.2)
                
                # 角度0指向正北（数学坐标系：cos为北向，sin为东向）
                dn = radius * math.cos(angle)  # 北向位移（米）
                de = radius * math.sin(angle)  # 东向位移（米）
                
                plat, plon = meters_to_geo(base_lat, base_lon, dn, de)
                points.append(GeoPoint(plon, plat, 0.0))  # GeoPoint(lon, lat, alt)
            
            # 创建 ctypes 动态数组（长度为 num_vertices）
            arr = (GeoPoint * num_vertices)(*points)
            self._keep_alive.append(arr)  # 防止被GC回收
            
            plan.data.area.vertices = arr
            plan.data.area.vertex_count = num_vertices
            
            # 高度范围：围绕巡航高度随机分布，更符合实际盘旋任务
            alt_range = random.uniform(50.0, 150.0)
            plan.data.area.min_alt = 0
            plan.data.area.max_alt = cruise_alt + alt_range / 2
            
            # 确保最小高度不低于0
            if plan.data.area.min_alt < 0:
                plan.data.area.min_alt = 0.0

        elif plan_num < 0.5:  # 航路点任务
            plan.type = 0
            wps = []
            curr_lat, curr_lon = base_lat, base_lon
            # 起飞点（高度0）
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), plan.start_time, 0, 100,1,100/2))
            curr_time = plan.start_time + (cruise_alt / CLIMB_RATE)  # 爬升所需时间粗估
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, cruise_alt), 0, 0, 100,1,1))
            # 随机生成点数
            num_points = random.randint(10, 30)
            current_heading = random.uniform(0, 2 * math.pi)
            for _ in range(num_points):
                d_dist = random.uniform(90, 3000)
                delta_angle = random.uniform(-math.pi/2, math.pi/2)
                
                # 更新当前航向
                current_heading += delta_angle
                d_ang = current_heading
                curr_lat, curr_lon = meters_to_geo(curr_lat, curr_lon,
                                                   d_dist * math.cos(d_ang), d_dist * math.sin(d_ang))
                wp_alt = cruise_alt + random.uniform(-50, 200)
                travel_time = d_dist / CRUISE_SPEED
                curr_time += travel_time
                wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, wp_alt),0, 0, 100,1,100/2))

            # 降落点
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), curr_time + 100, 0,100,1,100/2))

            arr = (Waypoint * len(wps))(*wps)
            self._keep_alive.append(arr)
            plan.data.traj.wps = arr
            plan.data.traj.count = len(wps)
            plan.end_time = curr_time + 100


        # === 分支 B: 航路点任务 (区域型） ===
        else:  
            plan.type = 0
            wps = []
            curr_lat, curr_lon = base_lat, base_lon
            
            # 1. 起飞点 (地面 -> 0m)
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), plan.start_time, 0, 100, 1, 100/2))
            
            # 2. 爬升到巡航高度 (第一个航点)
            # 估算爬升时间
            curr_time = plan.start_time + (cruise_alt / CLIMB_RATE)
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, cruise_alt), 0, 0, 100, 1, 5))
            
            # 3. 生成多边形轨迹 (走一个形状)
            # 随机选择多边形边数 (3=三角形, 4=正方形, 5=五边形, 6=六边形)
            poly_sides = random.randint(4, 30)
            
            # 边长范围 (400m - 1000m)，比之前的随机漫步范围更小，更像一个具体的任务
            side_len = random.uniform(200.0, 1000.0)
            
            # 初始航向 (随机)
            current_heading = random.uniform(0, 2 * math.pi)
            
            # 转向方向 (1: 顺时针, -1: 逆时针)
            turn_dir = 1 if random.random() > 0.5 else -1
            
            # 每次转弯的角度 (外角 = 2*PI / 边数)
            turn_angle = (2 * math.pi / poly_sides) * turn_dir
            
            # 步数：走 poly_sides 步通常会回到起点附近；
            # 如果想要“开口”多边形，可以只走 poly_sides - 1 步
            steps = poly_sides 
            
            for _ in range(steps):
                # 按照当前航向向前飞 side_len
                # cos=North, sin=East (对应 meters_to_geo 的 dn, de)
                dn = side_len * math.cos(current_heading)
                de = side_len * math.sin(current_heading)
                
                curr_lat, curr_lon = meters_to_geo(curr_lat, curr_lon, dn, de)
                
                # 累加飞行时间
                travel_time = side_len / CRUISE_SPEED
                curr_time += travel_time
                
                # 高度在巡航高度附近微调，增加一点真实感
                wp_alt = cruise_alt + random.uniform(-30, 30)
                
                wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, wp_alt), 0, 0, 100, 1, 100/2))
                
                # 转向：更新航向用于下一段
                current_heading += turn_angle

            # 4. 降落点 (在最后一个航点处直接降落)
            wps.append(Waypoint(GeoPoint(curr_lon, curr_lat, 0), curr_time + 100, 0, 100, 1, 100/2))

            # 封装数据
            arr = (Waypoint * len(wps))(*wps)
            self._keep_alive.append(arr)
            plan.data.traj.wps = arr
            plan.data.traj.count = len(wps)
            plan.end_time = curr_time + 100

        # 创建对应的无人机代理
        self.agents[uid_str] = DroneAgent(
            plan,
            registration_sign_override=registration_sign_override,
        )
        return plan


    def add_plans(self, params: List[Dict[str, Any]]) -> int:
        """
        从外部 JSON 数据追加飞行计划，格式与 mock/redis_route.json 一致。

        Args:
            params: 飞行计划列表，每项格式为:
                {
                    "key": "<uid>",
                    "value": {
                        "uniqueProductIdentificationCode": "<uid>",
                        "flightPlanList": [
                            {
                                "flightPlanId": int,
                                "planTakeoffTime": float,
                                "planLandTime": float,
                                "flightTaskId": int,
                                "flightTaskName": str,
                                "routeList": [
                                    {
                                        "sequence": int,
                                        "segmentStartLon": float, "segmentStartLat": float,
                                        "segmentEndLon": float,   "segmentEndLat": float,
                                        "segmentStartHeight": float, "segmentEndHeight": float,
                                        "segmentProtectHeight": float,
                                        "segmentProtectHeightType": int,
                                        "segmentWidth": float
                                    }, ...
                                ]
                            }
                        ]
                    }
                }

        Returns:
            成功追加的无人机数量
        """
        added = 0
        for item in params:
            value = item.get("value", {})
            uid_str = item.get("key") or value.get("uniqueProductIdentificationCode", "")
            if not uid_str:
                continue

            plan_list = value.get("flightPlanList", [])
            if not plan_list:
                continue

            # 取第一个飞行计划
            fp_data = plan_list[0]
            route_list = sorted(fp_data.get("routeList", []), key=lambda x: x["sequence"])
            if not route_list:
                continue

            self.plan_counter += 1
            plan = FlightPlan()
            plan.plan_id = fp_data.get("flightPlanId", self.plan_counter)
            plan.task_id = fp_data.get("flightTaskId", 0)

            task_name = fp_data.get("flightTaskName", "").encode("utf-8")
            ctypes.memmove(plan.task_name, task_name, min(len(task_name), 63))

            plan.start_time = fp_data.get("planTakeoffTime", time.time())
            plan.end_time   = fp_data.get("planLandTime", plan.start_time + 3600)
            plan.priority   = 5
            plan.type       = 0  # TRAJ

            plan.aircraft.uid = uid_str.encode("utf-8")
            plan.aircraft.longitudinal_threshold = 200.0
            plan.aircraft.lateral_threshold      = 100.0
            plan.aircraft.v_threshold            = 100.0
            plan.aircraft.max_speed              = CRUISE_SPEED
            plan.aircraft.classification = random.choice(list(UAVClassification)).value

            # 将 routeList 转为 Waypoint 列表：序列 0 的起始点 + 每段的终点
            first_seg = route_list[0]
            wps = [
                Waypoint(
                    GeoPoint(first_seg["segmentStartLon"], first_seg["segmentStartLat"],
                             first_seg["segmentStartHeight"]),
                    plan.start_time, 0,
                    first_seg.get("segmentWidth", 100.0),
                    first_seg.get("segmentProtectHeightType", 1),
                    first_seg.get("segmentProtectHeight", 50.0),
                )
            ]
            for seg in route_list:
                wps.append(Waypoint(
                    GeoPoint(seg["segmentEndLon"], seg["segmentEndLat"], seg["segmentEndHeight"]),
                    0, 0,
                    seg.get("segmentWidth", 100.0),
                    seg.get("segmentProtectHeightType", 1),
                    seg.get("segmentProtectHeight", 50.0),
                ))

            arr = (Waypoint * len(wps))(*wps)
            self._keep_alive.append(arr)
            plan.data.traj.wps   = arr
            plan.data.traj.count = len(wps)

            # 若该 uid 已存在则替换旧代理
            if uid_str in self.agents:
                del self.agents[uid_str]

            self.agents[uid_str] = DroneAgent(plan, cruise_speed=5)
            added += 1

        return added

    def step(self, step_size_sec: float = 1.0, sim_time: float = None) -> List[Dict[str, Any]]:
        """
        仿真推进一步
        
        Args:
            step_size_sec: 时间步长（默认1秒）
            sim_time: 可选，仿真当前时间（秒）；不传则使用系统时间
            
        Returns:
            所有活跃无人机的遥测数据包列表（含历史轨迹）
        """
        # 使用浮点时间，避免 int(time.time()) 与 plan.start_time（浮点）比较时整秒内误判为「未到起飞时间」而一直 IDLE、不写 Kafka
        current_time = float(sim_time) if sim_time is not None else time.time()
        real_start_time = time.time()  # 记录实际系统时间用于性能统计
        payloads = []

        # 清理已完成的任务（上一步已落地 state==5 的 agent）
        finished_ids = [uid for uid, agent in self.agents.items() if agent.state == 5]
        self.last_finished_uids = list(finished_ids)
        for uid in finished_ids:
            del self.agents[uid]


        for agent in self.agents.values():
            agent.update(current_time, step_size_sec)
            # 只发送正在飞行的无人机数据
            if agent.state != 0:
                payloads.append(agent.get_telemetry_payload(current_time))
                # print(f'sim current time:{current_time}')
        
        # 时长（修复：使用实际系统时间计算性能耗时）
        time_spent = time.time() - real_start_time
        # print(f"[Simulator] 步进 {step_size_sec}s，活跃无人机数：{len(self.agents)}，耗时：{time_spent*1000:.2f} ms")


        return payloads