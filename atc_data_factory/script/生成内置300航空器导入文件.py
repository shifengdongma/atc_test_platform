# -*- coding: utf-8 -*-
"""
将 simulation_core.py 中的300个内置无人机标识符转化为航空器导入模板
航空器识别码（第2列）使用 UAV_IDENTIFIERS 第一列
实名登记号（第3列）使用 UAV_IDENTIFIERS 第二列
其他字段参考生成脚本随机填充
"""
import os
import sys
import random
import string
from datetime import datetime, timedelta
from openpyxl import load_workbook

# ==================== 配置 ====================
GENERATE_COUNT = 300  # UAV_IDENTIFIERS 中的无人机数量
OUTPUT_FILENAME = '内置3000航空器数据_300_0.1.xlsx'
# ==================== 配置 ====================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'test_data')
TEMPLATE_PATH = os.path.join(BASE_DIR, '航空器数据导入模板.xlsx')
OUTPUT_PATH = os.path.join(BASE_DIR, OUTPUT_FILENAME)

# 导入达梦数据库客户端（同目录下 dmdbclient.py）
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    from dmdbclient import DmDbClient
except ImportError as e:
    print(f"[警告] 导入 dmdbclient 失败: {e}")
    DmDbClient = None

# ==================== 内置300个无人机标识符 ====================
# 从 simulation_core.py 123-426 行提取
# 格式: (uniqueProductIdentificationCode, realNameRegistrationSign)
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
    """生成单条航空器数据

    Args:
        index: 数据索引（从0开始）
        aircraft_code: 航空器识别码（来自UAV_IDENTIFIERS第一列）
        registration_no: 实名登记号（来自UAV_IDENTIFIERS第二列）
        personal_ids: 真实个人用户身份证号列表
        organizations: 真实运营单位信息列表 [(name, uscc), ...]
    """
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

    # 生成有效期
    start_date = random_date(2024, 2027)
    end_date = random_date(2027, 2030)
    valid_period = f"{start_date}-{end_date}"

    row = [
        generate_uav_name(idx),  # 航空器名称
        aircraft_code,  # 航空器识别码（内置）
        registration_no,  # 实名登记号（内置）
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
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
        for cell in row:
            cell.value = None

    print(f"\n开始生成 {GENERATE_COUNT} 条内置航空器数据...")

    # 从达梦数据库获取真实数据
    print("\n--- 从达梦数据库查询真实数据 ---")
    personal_ids = fetch_personal_users()
    organizations = fetch_organizations()

    if not personal_ids:
        print("[提示] 未获取到个人用户数据，将使用模拟身份证号")
    if not organizations:
        print("[提示] 未获取到单位数据，将使用模拟统一社会信用代码")

    # 从数据库查询已有航空器识别码，过滤已存在的ID
    print("\n--- 航空器识别码去重检查 ---")
    existing_codes = fetch_existing_identify_codes()
    if existing_codes:
        original_count = len(UAV_IDENTIFIERS)
        filtered_identifiers = [
            item for item in UAV_IDENTIFIERS
            if item[0] not in existing_codes
        ]
        filtered_count = len(filtered_identifiers)
        skipped = original_count - filtered_count
        print(f"[去重] 原ID总数: {original_count}, 已存在: {skipped}, 剩余可导入: {filtered_count}")
        if filtered_count == 0:
            print("[警告] 所有航空器识别码均已存在于数据库中，无需生成")
            return
    else:
        filtered_identifiers = UAV_IDENTIFIERS

    # 从第3行开始写入数据
    for i in range(len(filtered_identifiers)):
        aircraft_code, registration_no = filtered_identifiers[i]
        row_data = generate_row(i, aircraft_code, registration_no, personal_ids, organizations)
        row_num = i + 3  # Excel行号从1开始，第3行是第一条数据
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=row_num, column=col_idx, value=value)

        if (i + 1) % 50 == 0:
            print(f"  已生成 {i + 1} 条...")

    print("保存文件...")
    wb.save(OUTPUT_PATH)
    print(f"完成！文件保存至: {OUTPUT_PATH}")
    print(f"共生成 {len(filtered_identifiers)} 条航空器数据")
    print(f"使用了 {len(UAV_IDENTIFIERS)} 个内置无人机标识符")
    if skipped > 0:
        print(f"  - 已跳过（数据库中已存在）: {skipped} 条")
    if personal_ids:
        print(f"  - 个人用户: 使用数据库真实证件号码 ({len(personal_ids)} 条)")
    if organizations:
        print(f"  - 运营单位: 使用数据库真实统一社会信用代码 ({len(organizations)} 条)")


if __name__ == "__main__":
    main()
