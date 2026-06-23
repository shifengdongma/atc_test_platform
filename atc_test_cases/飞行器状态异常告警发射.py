# -*- coding: utf-8 -*-
"""
飞行器状态异常告警发射（IDE 直接执行）

功能：
- 发射 mock/ 目录下的告警场景 JSON 数据到 Kafka
- 支持单文件/多文件发射，可配置间隔、循环、trace 消费
- 自动检测数据文件是否存在，缺失时提示生成命令

用法：
    1. 直接在 IDE 中运行本脚本（发射全部启用的场景）
    2. 命令行传参：python 飞行器状态异常告警发射.py --interval 500 --scene3 --scene5
"""
import os
import sys
import multiprocessing
import argparse

# ── 路径配置 ─────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
TOOLS_DIR = os.path.join(ENGINE_DIR, "tools")
PROJECT_ROOT = os.path.dirname(ENGINE_DIR)

sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, TOOLS_DIR)

from run_kafka_scene import SceneEmitter

# ── 默认参数（可在此修改）─────────────────────────────────────────────
DEFAULT_INTERVAL_MS = 1000      # 发射间隔（毫秒）
DEFAULT_LOOP = False            # 数据耗尽后是否循环
DEFAULT_CONSUME_TRACE = True    # 是否消费 uav_runtime_trace

# IDE 直接运行配置：设为 True 时，无需命令行参数直接发射
IDE_QUICK_RUN = True

# IDE 模式下要发射的告警场景文件（位于 utm_moc52_develop/mock/）
IDE_SCENE_FILES = [
    ("mock/飞行器丢失状态3.json", "状态3-紧急后恢复"),
    ("mock/飞行器丢失状态5.json", "状态5-航空器丢失"),
    ("mock/飞行器丢失状态3-5.json", "状态3转5-紧急后丢失"),
]

# 场景开关（IDE 模式下控制发射哪些场景）
SCENE_3_ENABLED = True
SCENE_5_ENABLED = False
SCENE_3_5_ENABLED = False
# ================================================================


def _emit_worker(json_file, interval_ms, loop, consume_trace, quiet=True, trace_group_id=None):
    """单个发射器工作进程"""
    scene_name = os.path.basename(json_file)
    try:
        emitter = SceneEmitter(
            files=[json_file],
            interval_ms=interval_ms,
            loop=loop,
            consume_trace=consume_trace,
            trace_group_id=trace_group_id,
            quiet=quiet,
        )
        print(f"[{scene_name}] 发射器初始化完成，UAV数量: {len(emitter.uav_data_list)}")
        emitter.start()
        try:
            emitter.wait_until_done()
        except KeyboardInterrupt:
            pass
        finally:
            try:
                if emitter.is_running():
                    emitter.stop()
            except KeyboardInterrupt:
                pass
    except Exception as e:
        print(f"[{scene_name}] 发射异常: {e}")
    finally:
        print(f"[{scene_name}] 进程结束")


def emit_parallel(scene_files, interval_ms, loop, consume_trace):
    """并发启动多个发射进程"""
    print("=" * 70)
    print("飞行器状态异常告警发射")
    print("=" * 70)
    for i, (f, label) in enumerate(scene_files, 1):
        print(f"  场景{i}: {label} -> {os.path.basename(f)}")
    print(f"  总场景数: {len(scene_files)}")
    print(f"  发射间隔: {interval_ms}ms")
    print(f"  循环模式: {'开启' if loop else '关闭'}")
    print(f"  Trace消费: {'开启' if consume_trace else '关闭'}")
    print("=" * 70)
    print()

    processes = []
    shared_trace_group = "alarm_emitter_trace_shared"
    for i, (f, label) in enumerate(scene_files):
        consume = consume_trace if i == 0 else False
        p = multiprocessing.Process(
            target=_emit_worker,
            args=(f, interval_ms, loop, consume, quiet_mode, shared_trace_group if consume else None),
        )
        p.start()
        processes.append((p, os.path.basename(f)))
        print(f"[启动] {label} (pid={p.pid}, trace={'开启' if consume else '关闭'})")

    try:
        for p, name in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n[中断] 收到停止信号，正在终止所有进程...")
        for p, name in processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=5)
                if p.is_alive():
                    p.kill()
                    p.join(timeout=3)
        print("\n已强制停止")
        return

    print("\n所有场景发射完成")


def main():
    parser = argparse.ArgumentParser(
        description="飞行器状态异常告警发射",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MS, help="发射间隔(毫秒)")
    parser.add_argument("--loop", action="store_true", default=DEFAULT_LOOP, help="数据耗尽后循环")
    parser.add_argument("--consume-trace", action="store_true", default=DEFAULT_CONSUME_TRACE, help="消费uav_runtime_trace")
    parser.add_argument("--no-consume-trace", action="store_true", help="不消费uav_runtime_trace")
    parser.add_argument("--quiet", action="store_true", default=False, help="静默模式，不打印发送日志")
    parser.add_argument("--scene3", action="store_true", default=SCENE_3_ENABLED, help="发射状态3场景")
    parser.add_argument("--scene5", action="store_true", default=SCENE_5_ENABLED, help="发射状态5场景")
    parser.add_argument("--scene3-5", action="store_true", default=SCENE_3_5_ENABLED, help="发射状态3-5场景")
    args = parser.parse_args()

    consume_trace = not args.no_consume_trace if args.no_consume_trace else args.consume_trace
    quiet_mode = args.quiet

    # 组装要发射的场景列表
    scene_map = [
        (args.scene3, IDE_SCENE_FILES[0]),
        (args.scene5, IDE_SCENE_FILES[1]),
        (args.scene3_5, IDE_SCENE_FILES[2]),
    ]
    active_scenes = [(os.path.join(ENGINE_DIR, f), label) for enabled, (f, label) in scene_map if enabled]

    if not active_scenes:
        print("[错误] 没有启用的场景，请通过 --scene3 / --scene5 / --scene3-5 指定")
        sys.exit(1)

    # 检查文件是否存在
    missing = [(f, label) for f, label in active_scenes if not os.path.isfile(f)]
    if missing:
        print("[错误] 以下数据文件不存在:")
        for f, label in missing:
            print(f"  - {label}: {f}")
        print("\n请先生成数据:")
        print(f'  cd {TOOLS_DIR}')
        print('  python 飞行器状态告警数据点位生成.py')
        sys.exit(1)

    if IDE_QUICK_RUN:
        emit_parallel(active_scenes, args.interval, args.loop, consume_trace)
        return

    # 单文件模式（非 IDE_QUICK_RUN 时发射第一个启用的场景）
    json_file, label = active_scenes[0]
    print("=" * 60)
    print(f"  飞行器状态异常告警发射（单文件模式）")
    print(f"  场景: {label}")
    print(f"  数据文件: {json_file}")
    print(f"  发射间隔: {args.interval}ms")
    print("=" * 60)
    print()

    emitter = SceneEmitter(
        files=[json_file],
        interval_ms=args.interval,
        loop=args.loop,
        consume_trace=consume_trace,
        quiet=quiet_mode,
    )
    emitter.start()
    try:
        emitter.wait_until_done()
    except KeyboardInterrupt:
        print("\n[中断] 收到停止信号")
    finally:
        if emitter.is_running():
            emitter.stop()
    print("\n程序结束")


if __name__ == "__main__":
    main()
