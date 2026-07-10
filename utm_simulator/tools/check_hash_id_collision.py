#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
ID 碰撞检测脚本
============================================================
用途：
    模拟后端 Java 代码 `Math.abs(identifyCode.hashCode()) + timestamp`
    的 ID 生成逻辑，对 mock 数据中的无人机轨迹记录批量生成 ID，
    并检测是否存在重复（碰撞），以验证该算法是否能作为唯一 ID 策略。

检测对象：
    读取 ../mock/kafka_data_scene2.json ~ kafka_data_scene11.json，
    提取每条记录的 uniqueProductIdentificationCode（作为 identifyCode）
    和 timestamp，按上述公式生成 ID 后做重复校验。

输出说明：
    - 总记录数 / 生成 ID 数 / 唯一 ID 数
    - 重复类型分布（同 identifyCode、不同 identifyCode 碰撞）
    - 不同 identifyCode 碰撞的示例（用于排查问题）

用法：
    直接运行即可，无需额外参数：
        python check_hash_id_collision.py

依赖：
    Python 3.x，仅使用标准库（json、os、collections）

注意事项：
    1. 本脚本严格模拟 Java String.hashCode() 和 Math.abs(int) 行为，
       包括 Math.abs(Integer.MIN_VALUE) == Integer.MIN_VALUE 的溢出坑。
    2. 若需检测其他目录或文件名格式的数据，请修改 main() 中的 files 列表。
============================================================
"""
import json
import os
from collections import defaultdict

# mock 数据目录：位于本脚本的上级目录中的 mock 文件夹
MOCK_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'mock')


def java_hash_code(s: str) -> int:
    """
    模拟 Java String.hashCode() 算法。

    Java 中字符串 hashCode 计算公式：
        s[0]*31^(n-1) + s[1]*31^(n-2) + ... + s[n-1]
    结果为有符号 32 位整数，可能为负数。

    Args:
        s: 输入字符串（对应 identifyCode）

    Returns:
        int: Java 风格的 32 位有符号 hash 值
    """
    h = 0
    for ch in s:
        h = (31 * h + ord(ch)) & 0xFFFFFFFF
    # 将超过 0x7FFFFFFF 的无符号值转回有符号负数
    if h > 0x7FFFFFFF:
        h -= 0x100000000
    return h


def java_math_abs(n: int) -> int:
    """
    模拟 Java Math.abs(int) 行为。

    注意：Java 中 Math.abs(Integer.MIN_VALUE) 由于溢出，
    结果仍为 Integer.MIN_VALUE（-2147483648），不会变成正数。

    Args:
        n: 有符号 32 位整数

    Returns:
        int: 绝对值结果，注意 Integer.MIN_VALUE 的坑
    """
    if n == -0x80000000:
        return -0x80000000  # Java: Math.abs(Integer.MIN_VALUE) == Integer.MIN_VALUE
    return abs(n)


def generate_id(identify_code: str, timestamp: int) -> str:
    """
    模拟后端的 ID 生成逻辑。

    对应 Java 代码：
        long hash = Math.abs(identifyCode.hashCode());
        return String.valueOf(hash + timestamp);

    Args:
        identify_code: 无人机唯一标识码
        timestamp: 时间戳（毫秒级）

    Returns:
        str: 生成的 ID 字符串
    """
    h = java_math_abs(java_hash_code(identify_code))
    return str(h + timestamp)


def main():
    """
    主函数：读取 mock 数据，批量生成 ID 并检测碰撞。

    流程：
        1. 加载 kafka_data_scene2.json ~ kafka_data_scene11.json
        2. 对每条记录使用 generate_id() 生成 ID
        3. 统计重复情况并分类输出
    """
    # 默认检测 scene2 ~ scene11 的数据文件
    files = [f'kafka_data_scene{i}.json' for i in range(2, 12)]

    all_records = []
    for fname in files:
        fpath = os.path.join(MOCK_DIR, fname)
        if not os.path.exists(fpath):
            print(f"[警告] 文件不存在，已跳过: {fname}")
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        all_records.extend(data)

    print(f"总记录数: {len(all_records)}")

    # 建立生成 ID -> (identifyCode, timestamp) 的映射，用于检测重复
    id_to_sources = defaultdict(list)
    for item in all_records:
        code = item.get('uniqueProductIdentificationCode', '')
        ts = item.get('timestamp', 0)
        gid = generate_id(code, ts)
        id_to_sources[gid].append((code, ts))

    # 筛选出生成 ID 值出现多次的情况
    duplicates = {k: v for k, v in id_to_sources.items() if len(v) > 1}
    dup_records_count = sum(len(v) for v in duplicates.values())

    print(f"生成 ID 数量: {len(all_records)}")
    print(f"唯一 ID 数量: {len(id_to_sources)}")
    print(f"重复生成的ID值数量: {len(duplicates)}")
    print(f"涉及重复的记录数: {dup_records_count}")

    # 按重复原因分类统计
    same_code_same_ts = 0   # 同一 identifyCode + 同一 timestamp（完全重复记录）
    same_code_diff_ts = 0   # 同一 identifyCode + 不同 timestamp（理论上不应发生）
    diff_code = 0           # 不同 identifyCode 但生成相同 ID（hash 碰撞 + 时间戳抵消）

    for gid, sources in duplicates.items():
        codes = [s[0] for s in sources]
        tss = [s[1] for s in sources]
        if len(set(codes)) == 1 and len(set(tss)) == 1:
            same_code_same_ts += len(sources)
        elif len(set(codes)) == 1:
            same_code_diff_ts += len(sources)
        else:
            diff_code += len(sources)

    print(f"\n重复类型分布:")
    print(f"  同identifyCode + 同timestamp: {same_code_same_ts}条")
    print(f"  同identifyCode + 不同timestamp: {same_code_diff_ts}条")
    print(f"  不同identifyCode碰撞: {diff_code}条")

    # 输出不同 identifyCode 碰撞的示例，用于问题定位
    print(f"\n不同identifyCode导致重复的示例:")
    count = 0
    for gid, sources in duplicates.items():
        codes = [s[0] for s in sources]
        if len(set(codes)) > 1:
            count += 1
            print(f"  生成ID={gid}")
            for code, ts in sources[:5]:
                print(f"    {code} @ {ts}")
            if count >= 5:
                break
    if count == 0:
        print("  无（所有重复均为同identifyCode同timestamp的重复记录）")


if __name__ == '__main__':
    main()
