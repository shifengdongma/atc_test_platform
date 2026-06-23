# -*- coding: utf-8 -*-
"""
3000平行模拟器发射（IDE 直接执行）

参考 performance_test_2700+300.py 优化：
- 结构化步骤（数据生成 → 并发发射）
- Monkey Patch 扩展 ID 列表至 5000 个
- 完善的进程管理（信号处理、finally 清理）
- 数据文件缺失时自动生成
- 支持命令行参数覆盖默认配置

用法：
    1. 直接在 IDE 中运行本脚本
    2. 命令行传参：python 3000平行模拟器发射.py --interval 500 --no-consume-trace
"""
import os
import sys
import multiprocessing
import subprocess
import argparse

# ── 路径配置 ─────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
TOOLS_DIR = os.path.join(ENGINE_DIR, "tools")
PROJECT_ROOT = os.path.dirname(ENGINE_DIR)
GENERATOR_PY = os.path.join(TOOLS_DIR, "3000架平行飞行无人机轨迹点生成.py")

sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, TOOLS_DIR)

# ========== Monkey Patch：扩展内置 ID 列表至 5000 个 ==========
# 必须在 from run_kafka_scene import SceneEmitter 之前执行
import simulation_core as _sim_core
from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED
_sim_core.UAV_IDENTIFIERS = UAV_IDENTIFIERS_EXTENDED
_sim_core.ACTIVE_UAV_IDENTIFIERS = UAV_IDENTIFIERS_EXTENDED
# =============================================================

from run_kafka_scene import SceneEmitter

# ── 默认参数（可在此修改）─────────────────────────────────────────────
DEFAULT_INTERVAL_MS = 1000      # 发射间隔（毫秒）
DEFAULT_LOOP = False            # 数据耗尽后是否循环
DEFAULT_CONSUME_TRACE = True    # 是否消费 uav_runtime_trace

# IDE 直接运行配置：设为 True 时，无需命令行参数直接发射多场景数据
IDE_QUICK_RUN = True

# IDE 模式下要发射的场景文件列表（与生成脚本的 IDE_DATASETS 对应）
IDE_SCENE_FILES = [
    #"mock/kafka_data_scene1.json",
    "mock/kafka_data_scene2.json",
    "mock/kafka_data_scene3.json",
    "mock/kafka_data_scene4.json",
    "mock/kafka_data_scene5.json",
    "mock/kafka_data_scene6.json",
    "mock/kafka_data_scene7.json",
    "mock/kafka_data_scene8.json",
    "mock/kafka_data_scene9.json",
    "mock/kafka_data_scene10.json",
    "mock/kafka_data_scene11.json",
]


def step1_generate_data():
    """步骤1：检查并生成数据文件。若缺失则自动调用生成脚本。"""
    json_files = [os.path.join(ENGINE_DIR, f) for f in IDE_SCENE_FILES]
    missing = [f for f in json_files if not os.path.isfile(f)]

    if not missing:
        print(f"[步骤1/2] 所有数据文件已存在，跳过生成")
        return json_files

    print("=" * 70)
    print("步骤 1/2：数据文件缺失，自动调用生成脚本")
    print("=" * 70)
    if not os.path.isfile(GENERATOR_PY):
        print(f"[错误] 找不到生成脚本: {GENERATOR_PY}")
        sys.exit(1)

    # 调用生成脚本（IDE_QUICK_RUN=True 时会自动读取 IDE_DATASETS）
    try:
        result = subprocess.run(
            [sys.executable, GENERATOR_PY],
            cwd=ENGINE_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"[错误] 数据生成失败:\n{e.stdout}\n{e.stderr}")
        sys.exit(1)

    # 再次检查
    still_missing = [f for f in json_files if not os.path.isfile(f)]
    if still_missing:
        print(f"[错误] 生成后仍缺少以下文件:")
        for f in still_missing:
            print(f"  - {f}")
        sys.exit(1)

    print(f"[完成] 数据生成完毕\n")
    return json_files


def _emit_worker(json_file, interval_ms, loop, consume_trace, quiet=False, trace_group_id=None):
    """单个发射器工作进程（完全隔离，避免线程间 Kafka 全局状态冲突）"""
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


def step2_emit_parallel(json_files, interval_ms, loop, consume_trace):
    """步骤2：并发启动多个发射进程。"""
    print("=" * 70)
    print("步骤 2/2：并发启动发射进程")
    print("=" * 70)
    for i, f in enumerate(json_files, 1):
        print(f"  场景{i}: {os.path.basename(f)}")
    print(f"  总场景数: {len(json_files)}")
    print(f"  发射间隔: {interval_ms}ms")
    print(f"  循环模式: {'开启' if loop else '关闭'}")
    print(f"  Trace消费: {'开启' if consume_trace else '关闭'}")
    print("=" * 70)
    print()

    processes = []
    shared_trace_group = "scene_emitter_trace_shared"
    for i, f in enumerate(json_files):
        # 只让第一个进程消费 trace，避免重复打印；所有子进程静默发送
        consume = consume_trace if i == 0 else False
        p = multiprocessing.Process(
            target=_emit_worker,
            args=(f, interval_ms, loop, consume, True, shared_trace_group if consume else None),
        )
        p.start()
        processes.append((p, os.path.basename(f)))
        print(f"[启动] 发射进程: {os.path.basename(f)} (pid={p.pid}, trace={'开启' if consume else '关闭'})")

    # 等待所有进程完成（或收到中断信号）
    try:
        for p, name in processes:
            p.join()
    except KeyboardInterrupt:
        print("\n[中断] 收到停止信号，正在终止所有进程...")
        _terminate_processes(processes)
        print("\n✨ 已强制停止")
        return

    print("\n✨ 所有场景发射完成")


def _terminate_processes(processes):
    """终止所有残留进程（借鉴 performance_test_2700+300.py 的清理逻辑）"""
    for p, name in processes:
        if p.is_alive():
            try:
                p.terminate()
                p.join(timeout=5)
            except (Exception, KeyboardInterrupt):
                pass
            if p.is_alive():
                try:
                    p.kill()
                    p.join(timeout=3)
                except (Exception, KeyboardInterrupt):
                    pass
                print(f"  {name} (PID {p.pid}) 被强制终止")
            else:
                print(f"  {name} (PID {p.pid}) 已终止")


def main():
    parser = argparse.ArgumentParser(
        description="3000平行模拟器发射",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MS, help="发射间隔(毫秒)")
    parser.add_argument("--loop", action="store_true", default=DEFAULT_LOOP, help="数据耗尽后循环")
    parser.add_argument("--consume-trace", action="store_true", default=DEFAULT_CONSUME_TRACE, help="消费uav_runtime_trace")
    parser.add_argument("--no-consume-trace", action="store_true", help="不消费uav_runtime_trace")
    parser.add_argument("--generate-only", action="store_true", help="仅生成数据，不发射")
    parser.add_argument("--emit-only", action="store_true", help="跳过生成，直接发射")
    args = parser.parse_args()

    consume_trace = not args.no_consume_trace if args.no_consume_trace else args.consume_trace

    if IDE_QUICK_RUN and not args.generate_only:
        # 步骤1：数据生成（若缺失）
        if not args.emit_only:
            json_files = step1_generate_data()
        else:
            json_files = [os.path.join(ENGINE_DIR, f) for f in IDE_SCENE_FILES]
            missing = [f for f in json_files if not os.path.isfile(f)]
            if missing:
                print(f"[错误] 找不到以下数据文件（请先用 --generate-only 生成）:")
                for f in missing:
                    print(f"  - {f}")
                sys.exit(1)

        if args.generate_only:
            print("\n[完成] 数据生成完毕，--generate-only 模式下跳过发射")
            return

        # 步骤2：并发发射
        step2_emit_parallel(json_files, args.interval, args.loop, consume_trace)
        return

    # 单文件模式
    JSON_PATH = os.path.join(ENGINE_DIR, "mock", "kafka_data_parallel.json")
    if not os.path.isfile(JSON_PATH):
        print(f"[错误] 找不到数据文件: {JSON_PATH}")
        print("请先生成数据: python tools\\3000架平行飞行无人机轨迹点生成.py")
        sys.exit(1)

    print("=" * 60)
    print("  3000平行模拟器发射（单文件模式）")
    print(f"  数据文件: {JSON_PATH}")
    print(f"  发射间隔: {args.interval}ms")
    print("=" * 60)
    print()

    emitter = SceneEmitter(
        files=[JSON_PATH],
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
