# -*- coding: utf-8 -*-
"""
偏离航路告警_金鸡湖（IDE 直接执行）

调用 run_kafka_scene.py 发射 偏离航路_金鸡湖.json 数据

用法：
    1. 直接在 IDE 中运行本脚本
    2. 命令行传参：python 偏离航路告警_金鸡湖.py --interval 500 --no-consume-trace
"""
import os
import sys
import argparse

# ── 路径配置 ─────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "utm_simulator")
TOOLS_DIR = os.path.join(ENGINE_DIR, "tools")
#DATA_FILE = os.path.join(ENGINE_DIR, "mock", "kafka_data_scene_bj_tsjk.json")
DATA_FILE = os.path.join(ENGINE_DIR, "mock", "跨顺义三河段航路最低安全高度数据_0.1.json")
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, TOOLS_DIR)

from run_kafka_scene import SceneEmitter

# ── 默认参数（可在此修改）─────────────────────────────────────────────
DEFAULT_INTERVAL_MS = 1000      # 发射间隔（毫秒）
DEFAULT_LOOP = False            # 数据耗尽后是否循环
DEFAULT_CONSUME_TRACE = True    # 是否消费 uav_runtime_trace


def main():
    parser = argparse.ArgumentParser(
        description="偏离航路告警_金鸡湖 发射",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MS, help="发射间隔(毫秒)")
    parser.add_argument("--loop", action="store_true", default=DEFAULT_LOOP, help="数据耗尽后循环")
    parser.add_argument("--consume-trace", action="store_true", default=DEFAULT_CONSUME_TRACE, help="消费uav_runtime_trace")
    parser.add_argument("--no-consume-trace", action="store_true", help="不消费uav_runtime_trace")
    args = parser.parse_args()

    consume_trace = not args.no_consume_trace if args.no_consume_trace else args.consume_trace

    # 检查数据文件
    if not os.path.isfile(DATA_FILE):
        print(f"[错误] 找不到数据文件: {DATA_FILE}")
        sys.exit(1)

    print("=" * 60)
    print("  偏离航路告警_金鸡湖 发射")
    print(f"  数据文件: {DATA_FILE}")
    print(f"  发射间隔: {args.interval}ms")
    print(f"  循环模式: {'开启' if args.loop else '关闭'}")
    print(f"  Trace消费: {'开启' if consume_trace else '关闭'}")
    print("=" * 60)
    print()

    emitter = SceneEmitter(
        files=[DATA_FILE],
        interval_ms=args.interval,
        loop=args.loop,
        consume_trace=consume_trace,
    )
    emitter.start()
    try:
        emitter.wait_until_done()
    except KeyboardInterrupt:
        print("\n[中断] 收到停止信号")
    finally:
        if emitter.is_running():
            emitter.stop()
    print("\n✨ 程序结束")


if __name__ == "__main__":
    main()
