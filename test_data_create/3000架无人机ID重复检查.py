import json
import os
from collections import defaultdict

# mock 目录相对于本脚本的位置
MOCK_DIR = os.path.join(os.path.dirname(__file__), '..', 'mock')


def main():
    # kafka_data_scene2.json ~ kafka_data_scene11.json
    files = [f'kafka_data_scene{i}.json' for i in range(2, 12)]

    file_ids = {}      # 文件名 -> ID 集合
    file_stats = []    # 统计信息列表

    print(f"{'文件名':<30} | {'起止ID':<50} | {'ID数量':>8} | {'本文件重复':<12}")
    print("-" * 120)

    for fname in files:
        fpath = os.path.join(MOCK_DIR, fname)
        if not os.path.exists(fpath):
            print(f"[跳过] 文件不存在: {fname}")
            continue

        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 提取所有 uniqueProductIdentificationCode
        ids = [item['uniqueProductIdentificationCode'] for item in data]
        id_set = set(ids)

        # 本文件重复判断
        has_duplicate = len(ids) != len(id_set)
        duplicate_ids = []
        if has_duplicate:
            seen = set()
            for i in ids:
                if i in seen:
                    duplicate_ids.append(i)
                else:
                    seen.add(i)
            duplicate_ids = list(dict.fromkeys(duplicate_ids))  # 去重保持顺序

        min_id = min(id_set) if id_set else ''
        max_id = max(id_set) if id_set else ''

        file_stats.append({
            'fname': fname,
            'min_id': min_id,
            'max_id': max_id,
            'count': len(id_set),
            'has_duplicate': has_duplicate,
            'duplicate_ids': duplicate_ids,
        })
        file_ids[fname] = id_set

        range_id = f"{min_id} ~ {max_id}"
        dup_str = f"是 ({len(duplicate_ids)}个)" if has_duplicate else "否"
        print(f"{fname:<30} | {range_id:<50} | {len(id_set):>8} | {dup_str:<12}")

    # 跨文件重复检查
    print("\n" + "=" * 80)
    print("跨文件重复检查")
    print("=" * 80)

    found_cross = False
    n = len(file_stats)
    for i in range(n):
        for j in range(i + 1, n):
            fi = file_stats[i]['fname']
            fj = file_stats[j]['fname']
            common = file_ids[fi] & file_ids[fj]
            if common:
                found_cross = True
                print(f"[重复] {fi} <-> {fj} : 共有 {len(common)} 个重复ID")
                preview = list(common)[:5]
                print(f"       示例: {', '.join(preview)}{'...' if len(common) > 5 else ''}")

    if not found_cross:
        print("所有文件之间无重复ID。")


if __name__ == '__main__':
    main()
