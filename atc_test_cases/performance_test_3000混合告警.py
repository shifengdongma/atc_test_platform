# -*- coding: utf-8 -*-
"""
性能测试脚本：3000架混合告警测试（多线程版）

测试场景：
  - FIXED_COUNT 架：create_data.py 生成固定轨迹数据，由 run_kafka.py 按秒发送
  - RANDOM_COUNT 架：main.py 实时仿真随机生成并发送遥测（分多线程启动）
  - WebSocket 统计：客户端ws无人机数量统计.py 实时统计接收数量

改造说明：
  - 不再修改 env.py，所有参数通过脚本内常量或传参方式配置
  - 随机仿真分多个线程启动 DataFlow，每个线程独立分配 ID 区间
  - ID 按顺序分段分配，确保不冲突
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
FIXED_COUNT = 20              # 固定轨迹无人机数量
RANDOM_THREAD_COUNT = 3       # 随机仿真线程数（可配置）
RANDOM_COUNT_PER_THREAD = 1000  # 每线程随机仿真无人机数量
ENABLE_WS_STATS = False       # 是否启动 WebSocket 客户端统计，默认 False，开启True

# 仿真中心坐标（新疆扇区）
ORIGIN_LAT = 40.818724        # 仿真中心纬度（度）
ORIGIN_LON = 85.070136        # 仿真中心经度（度）
SIM_RADIUS_M = 5000.0       # 仿真有效半径（米），无人机在此范围内随机生成

# 计算总随机数
TOTAL_RANDOM_COUNT = RANDOM_THREAD_COUNT * RANDOM_COUNT_PER_THREAD


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
    print(f"         ID 索引范围: [0, {FIXED_COUNT - 1}]")
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


def run_dataflow_thread(thread_id: int, target_drones: int, uid_start_offset: int,
                        dataflow_list: list, stop_event: threading.Event) -> None:
    """在独立线程中启动一个 DataFlow 实例。

    Args:
        thread_id: 线程编号（用于日志）
        target_drones: 该线程要仿真的无人机数量
        uid_start_offset: ID 起始偏移量（从 UAV_IDENTIFIERS_EXTENDED 的该索引开始分配）
        dataflow_list: 共享列表，用于主线程收集 DataFlow 实例以便停止
        stop_event: 停止事件，线程轮询此事件以判断是否退出
    """
    from main import DataFlow

    thread_name = f"DataFlow-Thread-{thread_id}"
    print(f"[{thread_name}] 启动  target_drones={target_drones}  uid_start_offset={uid_start_offset}")

    dataflow = None
    try:
        dataflow = DataFlow(
            target_drones=target_drones,
            origin_lat=ORIGIN_LAT,
            origin_lon=ORIGIN_LON,
            sim_radius_m=SIM_RADIUS_M,
            uid_start_offset=uid_start_offset,
        )
        # 将实例放入共享列表，方便主线程停止
        dataflow_list.append(dataflow)
        print(f"[{thread_name}] DataFlow 已启动")

        # 阻塞等待停止信号
        while not stop_event.is_set():
            time.sleep(0.5)

    except Exception as e:
        print(f"[{thread_name}] 运行出错: {e}")
    finally:
        if dataflow is not None:
            try:
                dataflow.stop()
                print(f"[{thread_name}] DataFlow 已停止")
            except Exception as e:
                print(f"[{thread_name}] DataFlow 停止出错: {e}")


def step2_run_concurrent() -> None:
    """步骤2：同时启动多线程 DataFlow、run_kafka.py 和客户端ws无人机数量统计.py。"""
    print("=" * 70)
    print(f"步骤 2/3：并发启动")
    print(f"  - DataFlow x{RANDOM_THREAD_COUNT}          → {TOTAL_RANDOM_COUNT} 架实时随机仿真无人机")
    for i in range(RANDOM_THREAD_COUNT):
        offset = FIXED_COUNT + i * RANDOM_COUNT_PER_THREAD
        print(f"      线程-{i}: {RANDOM_COUNT_PER_THREAD} 架  uid_start_offset={offset}")
    if FIXED_COUNT > 0:
        print(f"  - run_kafka.py             → {FIXED_COUNT} 架固定轨迹数据发送")
    if ENABLE_WS_STATS:
        print(f"  - 客户端ws无人机数量统计.py → WebSocket 实时接收统计")
    print("=" * 70)

    processes = []
    dataflow_list = []          # 共享列表，收集各线程的 DataFlow 实例
    stop_event = threading.Event()
    threads = []

    try:
        # ── 启动多个 DataFlow 线程 ──────────────────────────────────
        for i in range(RANDOM_THREAD_COUNT):
            uid_start_offset = FIXED_COUNT + i * RANDOM_COUNT_PER_THREAD
            t = threading.Thread(
                target=run_dataflow_thread,
                args=(i, RANDOM_COUNT_PER_THREAD, uid_start_offset, dataflow_list, stop_event),
                daemon=True,
            )
            t.start()
            threads.append(t)
            # 稍微错开启动时间，避免同时初始化造成资源争抢
            time.sleep(0.3)

        # 等待所有 DataFlow 线程都启动完成
        print("\n等待 DataFlow 线程全部启动...")
        wait_start = time.time()
        while len(dataflow_list) < RANDOM_THREAD_COUNT and time.time() - wait_start < 30:
            time.sleep(0.5)
        print(f"  DataFlow 已启动 {len(dataflow_list)}/{RANDOM_THREAD_COUNT} 个\n")

        # ── 启动 run_kafka.py（仅当 FIXED_COUNT > 0 时）─────────────
        if FIXED_COUNT > 0:
            print(f"[启动] run_kafka.py (PID: ?)")
            proc_kafka = subprocess.Popen(
                [sys.executable, RUN_KAFKA_PY],
                cwd=ENGINE_DIR,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            processes.append((proc_kafka, "run_kafka.py"))
            print(f"         PID: {proc_kafka.pid}")

        # ── 启动 客户端ws无人机数量统计.py（可选）─────────────────────
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
        print(f"  • DataFlow x{RANDOM_THREAD_COUNT}            持续运行，请按 Ctrl+C 停止\n")

        # ── 轮询等待 ────────────────────────────────────────────────
        try:
            while True:
                # 清理已自动退出的 run_kafka.py，避免其退出后误触发 all_done
                for proc, name in list(processes):
                    if name == "run_kafka.py" and proc.poll() is not None:
                        processes.remove((proc, name))
                        print(f"  {name} 已正常退出，不再监控")

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
        # ── 通知所有 DataFlow 线程停止 ──────────────────────────────
        print("\n[停止] 正在通知 DataFlow 线程停止...")
        stop_event.set()

        # 等待所有线程结束
        for t in threads:
            t.join(timeout=10)
            if t.is_alive():
                print(f"  警告: 线程 {t.name} 未在 10 秒内结束")

        # 对可能未被线程清理的 DataFlow 实例再执行一次 stop
        for idx, df in enumerate(dataflow_list):
            try:
                df.stop()
            except Exception:
                pass

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
    print("  性能测试脚本：3000 架混合告警测试（多线程版）")
    print(f"    固定轨迹: {FIXED_COUNT}  架  →  create_data.py + run_kafka.py")
    print(f"    随机仿真: {TOTAL_RANDOM_COUNT} 架  →  DataFlow x{RANDOM_THREAD_COUNT}")
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

    # 步骤 2：并发启动多线程 DataFlow、run_kafka.py 和 ws统计脚本
    step2_run_concurrent()

    print("\n" + "=" * 70)
    print("[完成] 混合告警测试执行完毕")
    print("=" * 70)


if __name__ == "__main__":
    main()
