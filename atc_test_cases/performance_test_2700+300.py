# -*- coding: utf-8 -*-
"""
性能测试脚本：3000架无人机并发测试（改造版）

测试场景：
  - FIXED_COUNT 架：create_data.py 生成固定轨迹数据，由 run_kafka.py 按秒发送
  - RANDOM_COUNT 架：main.py 实时仿真随机生成并发送遥测
  - WebSocket 统计：客户端ws无人机数量统计.py 实时统计接收数量

改造说明：
  - 不再修改 env.py，所有参数通过脚本内常量或传参方式配置
  - 直接 import DataFlow 并传入参数
"""
import os
import sys
import subprocess
import time
import signal
import threading

# ── 路径配置 ─────────────────────────────────────────────────────────
# 脚本位于: .../Atc_Test2026/utm_moc52_develop/utm_test_cases/testcases/xxx.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录: .../Atc_Test2026 (向上退2层: testcases -> utm_test_cases -> utm_moc52_develop)
ENGINE_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
TOOLS_DIR = os.path.join(ENGINE_DIR, "tools")
PROJECT_ROOT = os.path.dirname(ENGINE_DIR)

sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, TOOLS_DIR)

# ========== Monkey Patch：扩展内置 ID 列表至 5000 个 ==========
# 必须在 from main import DataFlow 之前执行，确保 simulation_core 加载的是扩展列表
import simulation_core as _sim_core
from uav_identifiers_extended import UAV_IDENTIFIERS_EXTENDED
_sim_core.UAV_IDENTIFIERS = UAV_IDENTIFIERS_EXTENDED
_sim_core.ACTIVE_UAV_IDENTIFIERS = UAV_IDENTIFIERS_EXTENDED
# =============================================================

# ========== 动态修改仿真核心参数：巡航高度范围 ==========
# 如需触发最低飞行高度告警，可将范围设低（如 5~30 米）
# 默认使用较高范围，避免大并发场景下过度触发告警
MIN_CRUISE_ALT = 50.0   # 最低巡航高度（米）
MAX_CRUISE_ALT = 200.0  # 最高巡航高度（米）
_sim_core.set_simulation_params(
    min_cruise_alt=MIN_CRUISE_ALT,
    max_cruise_alt=MAX_CRUISE_ALT,
)
print(f"[配置] 巡航高度范围已设置为 {MIN_CRUISE_ALT}~{MAX_CRUISE_ALT} 米")
# =============================================================

CREATE_DATA_PY = os.path.join(TOOLS_DIR, "create_data.py")
RUN_KAFKA_PY = os.path.join(TOOLS_DIR, "run_kafka.py")
WS_STATS_PY = os.path.join(SCRIPT_DIR, "客户端ws无人机数量统计.py")

# ── 常量（场景参数，全部在本脚本中配置）───────────────────────────────
FIXED_COUNT = 300      # 固定轨迹无人机数量
RANDOM_COUNT = 700    # 随机仿真无人机数量
ENABLE_WS_STATS = False   # 是否启动 WebSocket 客户端统计，默认 False，开启True

# 仿真中心坐标（新疆扇区）
ORIGIN_LAT = 40.818724            # 仿真中心纬度（度）
ORIGIN_LON = 85.070136            # 仿真中心经度（度）
SIM_RADIUS_M = 100000.0           # 仿真有效半径（米），无人机在此范围内随机生成


def step1_generate_mock_data() -> None:
    """步骤1：运行 create_data.py --count FIXED_COUNT 生成固定轨迹数据。"""
    if FIXED_COUNT <= 0:
        print("=" * 70)
        print("步骤 1/3：跳过固定轨迹数据生成（FIXED_COUNT=0）")
        print("=" * 70)
        print()
        return

    print("=" * 70)
    print(f"步骤 1/3：生成 {FIXED_COUNT} 架固定轨迹数据 (create_data.py)")
    print("=" * 70)

    # 直接调用 create_data.main（复用当前进程的 Monkey Patch，避免子进程无法继承扩展 ID）
    import create_data
    try:
        create_data.main(
            target_drones=FIXED_COUNT,
            origin_lat=ORIGIN_LAT,
            origin_lon=ORIGIN_LON,
            sim_radius_m=SIM_RADIUS_M,
        )
    except SystemExit as e:
        if e.code != 0 and e.code is not None:
            print(f"\n[错误] create_data.py 执行失败，返回码: {e.code}")
            sys.exit(1)

    print(f"\n[完成] {FIXED_COUNT} 架固定轨迹数据已生成到 mock/ 目录\n")


def step2_run_concurrent() -> None:
    """步骤2：同时启动 DataFlow、run_kafka.py 和客户端ws无人机数量统计.py。"""
    print("=" * 70)
    print(f"步骤 2/3：并发启动")
    print(f"  - DataFlow                 → {RANDOM_COUNT} 架实时随机仿真无人机")
    if FIXED_COUNT > 0:
        print(f"  - run_kafka.py             → {FIXED_COUNT} 架固定轨迹数据发送")
    if ENABLE_WS_STATS:
        print(f"  - 客户端ws无人机数量统计.py → WebSocket 实时接收统计")
    print("=" * 70)

    from main import DataFlow

    processes = []
    dataflow = None

    try:
        # 启动 DataFlow（直接实例化，传入参数）
        print(f"[启动] DataFlow    (target_drones={RANDOM_COUNT})")
        dataflow = DataFlow(
            target_drones=RANDOM_COUNT,
            origin_lat=ORIGIN_LAT,
            origin_lon=ORIGIN_LON,
            sim_radius_m=SIM_RADIUS_M,
            uid_start_offset=FIXED_COUNT,
        )
        print("         DataFlow 已启动")

        # 启动 run_kafka.py（仅当 FIXED_COUNT > 0 时）
        if FIXED_COUNT > 0:
            print(f"[启动] run_kafka.py (PID: ?)")
            proc_kafka = subprocess.Popen(
                [sys.executable, RUN_KAFKA_PY],
                cwd=ENGINE_DIR,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            processes.append((proc_kafka, "run_kafka.py"))
            print(f"         PID: {proc_kafka.pid}")

        # 启动 客户端ws无人机数量统计.py（WebSocket 接收统计，可选）
        if ENABLE_WS_STATS:
            print(f"[启动] 客户端ws无人机数量统计.py (PID: ?)")
            proc_ws = subprocess.Popen(
                [sys.executable, WS_STATS_PY],
                cwd=SCRIPT_DIR,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            processes.append((proc_ws, "客户端ws无人机数量统计.py"))
            print(f"         PID: {proc_ws.pid}")

        print("\n进程已同时启动。")
        if FIXED_COUNT > 0:
            print("  • run_kafka.py             会在轨迹数据发送完毕后自动退出")
        print("  • DataFlow                 持续运行，请按 Ctrl+C 停止\n")

        # 轮询等待：run_kafka.py 会自动结束；DataFlow / ws统计 需手动停止
        try:
            while True:
                # 清理已自动退出的 run_kafka.py，避免其退出后误触发 all_done
                for proc, name in list(processes):
                    if name == "run_kafka.py" and proc.poll() is not None:
                        processes.remove((proc, name))
                        print(f"  {name} 已正常退出，不再监控")

                # 如果没有需要手动停止的子进程，无限等待（仅由 Ctrl+C 退出）
                if not processes:
                    time.sleep(1)
                    continue
                all_done = True
                for proc, name in processes:
                    if proc.poll() is None:
                        all_done = False
                        break
                if all_done:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[中断] 收到停止信号（Ctrl+C）")

    finally:
        # ── 停止 DataFlow ───────────────────────────────────────────
        if dataflow is not None:
            print("\n[停止] 正在停止 DataFlow...")
            try:
                dataflow.stop()
                print("  DataFlow 已停止")
            except KeyboardInterrupt:
                print("  DataFlow 停止被中断，继续清理...")
            except Exception as e:
                print(f"  DataFlow 停止出错: {e}")

        # ── 清理子进程 ──────────────────────────────────────────────
        print("\n[停止] 正在终止残留进程...")
        for proc, name in processes:
            if proc.poll() is None:
                try:
                    if sys.platform == "win32":
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        proc.terminate()
                    proc.wait(timeout=3)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        proc.kill()
                        proc.wait(timeout=3)
                    except Exception:
                        pass
                    print(f"  {name} (PID {proc.pid}) 被强制终止")
                except KeyboardInterrupt:
                    # 即使清理过程被再次 Ctrl+C，也强制杀掉
                    try:
                        proc.kill()
                        proc.wait(timeout=2)
                    except Exception:
                        pass
                    print(f"  {name} (PID {proc.pid}) 被强制终止")
                else:
                    print(f"  {name} (PID {proc.pid}) 已终止")
            else:
                print(f"  {name} (PID {proc.pid}) 已退出，返回码: {proc.returncode}")


def main() -> None:
    """主入口。"""
    print("=" * 70)
    print("  性能测试脚本：3000 架无人机并发测试（改造版）")
    print(f"    固定轨迹: {FIXED_COUNT}  架  →  create_data.py + run_kafka.py")
    print(f"    随机仿真: {RANDOM_COUNT} 架  →  DataFlow")
    print(f"    WebSocket统计: 客户端ws无人机数量统计.py")
    print(f"    巡航高度: {MIN_CRUISE_ALT}~{MAX_CRUISE_ALT} 米")
    print("=" * 70)
    print()

    # 检查必要文件是否存在
    for path, desc in [
        (CREATE_DATA_PY, "create_data.py"),
        (RUN_KAFKA_PY, "run_kafka.py"),
        (WS_STATS_PY, "客户端ws无人机数量统计.py"),
    ]:
        if not os.path.isfile(path):
            print(f"[错误] 找不到 {desc}: {path}")
            sys.exit(1)

    # 步骤 1：生成 mock 数据
    step1_generate_mock_data()

    # 步骤 2：并发启动 DataFlow、run_kafka.py 和 ws统计脚本
    step2_run_concurrent()

    print("\n" + "=" * 70)
    print("[完成] 性能测试脚本执行完毕")
    print("=" * 70)


if __name__ == "__main__":
    main()
