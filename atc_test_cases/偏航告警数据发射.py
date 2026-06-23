# -*- coding: utf-8 -*-
"""
场景测试脚本：偏航告警测试
使用条件：
  - 创建飞行任务，选择DJY20260422001002031 dj小鱼  航空器
  - 航路选择：飞隔离空域，金鸡湖边上的航线，
  - 或者克隆飞行任务，修改时间即可
测试场景：
  - 通过 run_kafka_scene.py 发射 scenes/偏离航路告警/偏离航路.json 中的轨迹数据
  - 触发偏航告警（无人机偏离预设航路）

使用方法：
  python 偏航告警.py
"""

import os
import sys
import json
import time

# ── 路径配置 ─────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
TOOLS_DIR = os.path.join(ENGINE_DIR, "tools")
PROJECT_ROOT = os.path.dirname(ENGINE_DIR)

SCENE_DIR = os.path.join(ENGINE_DIR, "utm_test_cases", "scenes", "偏离航路告警")
SCENE_JSON = os.path.join(SCENE_DIR, "偏离航路.json")

sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, TOOLS_DIR)

# ── 常量配置 ─────────────────────────────────────────────────────────
TOPIC = 'uav_runtime_data'
INTERVAL_MS = 1000
TIMESTAMP_MODE = 'replace'
LOOP = False


def count_uavs_in_scene(json_path: str) -> int:
    """统计场景 JSON 中 UAV 数量"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        uids = set()
        for record in data:
            uid = record.get('uniqueProductIdentificationCode')
            if uid:
                uids.add(uid)
        return len(uids)
    except Exception as e:
        print(f"⚠️  统计 UAV 数量失败: {e}")
        return 0


def main():
    print("=" * 70)
    print("  场景测试脚本：偏航告警测试")
    print("=" * 70)

    if not os.path.isfile(SCENE_JSON):
        print(f"[错误] 找不到场景数据文件: {SCENE_JSON}")
        sys.exit(1)

    uav_count = count_uavs_in_scene(SCENE_JSON)
    print(f"  场景数据: {SCENE_JSON}")
    print(f"  UAV 数量: {uav_count}")
    print(f"  Kafka Topic: {TOPIC}")
    print(f"  发射间隔: {INTERVAL_MS}ms")
    print("=" * 70)
    print()

    from run_kafka_scene import SceneEmitter

    emitter = None
    try:
        emitter = SceneEmitter(
            files=[SCENE_JSON],
            topic=TOPIC,
            interval_ms=INTERVAL_MS,
            timestamp_mode=TIMESTAMP_MODE,
            loop=LOOP,
        )
        emitter.start()
        emitter.wait_until_done()

    except KeyboardInterrupt:
        print("\n[中断] 收到停止信号（Ctrl+C）")
    finally:
        if emitter is not None and emitter.is_running():
            emitter.stop()

    print("\n" + "=" * 70)
    print("[完成] 偏航告警场景测试执行完毕")
    print("=" * 70)


if __name__ == "__main__":
    main()
