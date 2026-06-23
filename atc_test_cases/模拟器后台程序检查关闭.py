# -*- coding: utf-8 -*-
"""
模拟器后台程序检查与清理工具

功能：
  - 检查系统中残留的无人机模拟器相关 Python 进程
  - 打印进程详情（PID、启动命令）
  - 支持自动终止或交互式确认后终止
  - 交互模式下 5 秒无输入自动终止（避免残留日志干扰输入）

使用方式：
  1. 手动清理（推荐，5秒超时自动终止）：python 模拟器后台程序检查关闭.py
  2. 立即强制终止（不提示）：python 模拟器后台程序检查关闭.py --force
"""
import os
import sys
import subprocess
import argparse
import threading
import time

# ── 配置 ─────────────────────────────────────────────────────────────
# 用于识别模拟器相关进程的关键字（匹配命令行或进程名）
TARGET_KEYWORDS = [
    "main.py",
    "run_kafka.py",
    "run_kafka_alive.py",
    "客户端ws无人机数量统计.py",
    "performance_test_2700+300.py",
    "performance_test_禁区侵入.py",
]


def _get_python_processes_psutil():
    """使用 psutil 获取所有 Python 进程信息。"""
    try:
        import psutil
    except ImportError:
        return None

    processes = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] and "python" in proc.info["name"].lower():
                cmdline = " ".join(proc.info["cmdline"] or [])
                processes.append({
                    "pid": proc.info["pid"],
                    "name": proc.info["name"],
                    "cmdline": cmdline,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def _get_python_processes_wmic():
    """使用 wmic 获取所有 Python 进程信息（Windows 备用方案）。"""
    processes = []
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name like '%python%'", "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().splitlines()
        for line in lines[2:]:  # 跳过表头
            parts = line.strip().split(",")
            if len(parts) >= 3:
                pid_str = parts[-1].strip().strip('"')
                cmdline = ",".join(parts[1:-1]).strip().strip('"')
                if pid_str.isdigit():
                    processes.append({
                        "pid": int(pid_str),
                        "name": "python.exe",
                        "cmdline": cmdline,
                    })
    except Exception:
        pass
    return processes


def _get_python_processes():
    """获取所有 Python 进程，优先使用 psutil，回退到 wmic。"""
    processes = _get_python_processes_psutil()
    if processes is not None:
        return processes
    return _get_python_processes_wmic()


def _is_simulator_process(proc):
    """判断进程是否与无人机模拟器相关。"""
    cmdline = proc.get("cmdline", "")
    for kw in TARGET_KEYWORDS:
        if kw in cmdline:
            return True
    return False


def _input_with_timeout(prompt, timeout=5):
    """带超时的 input，超时返回 None。"""
    result = [None]
    def _get_input():
        try:
            result[0] = input(prompt)
        except Exception:
            result[0] = None
    t = threading.Thread(target=_get_input, daemon=True)
    t.start()
    t.join(timeout)
    return result[0]


def _kill_process(pid):
    """强制终止指定 PID 的进程（Windows / Linux 兼容）。"""
    try:
        if sys.platform == "win32":
            cmd = ["taskkill", "/PID", str(pid), "/T", "/F"]
            subprocess.run(cmd, capture_output=True, check=True)
        else:
            import signal
            os.kill(pid, signal.SIGKILL)
        return True
    except Exception as e:
        print(f"  [失败] 终止 PID {pid} 出错: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="模拟器后台程序检查与清理")
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制终止，不询问确认",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  模拟器后台程序检查与清理")
    print("=" * 70)
    print()

    # 获取所有 Python 进程
    all_py_procs = _get_python_processes()
    if not all_py_procs:
        print("[信息] 未检测到任何 Python 进程。")
        return

    # 筛选模拟器相关进程
    sim_procs = [p for p in all_py_procs if _is_simulator_process(p)]

    if not sim_procs:
        print(f"[信息] 未检测到残留的模拟器相关进程（共扫描 {len(all_py_procs)} 个 Python 进程）。")
        print()
        print("所有 Python 进程列表（供参考）：")
        for p in all_py_procs:
            print(f"  PID {p['pid']:>6} | {p['cmdline'][:80]}")
        return

    print(f"[发现] 检测到 {len(sim_procs)} 个模拟器相关残留进程：\n")
    for p in sim_procs:
        print(f"  PID {p['pid']:>6} | {p['cmdline'][:80]}")
    print()

    # 确认终止
    if args.force:
        confirm = "y"
    else:
        print()
        print("提示: 如果残留进程日志干扰输入，可直接用 --force 参数跳过确认")
        confirm = _input_with_timeout("[确认] 是否终止以上进程？(y/N，5秒无输入自动终止): ", timeout=5)
        if confirm is None:
            print("\n[超时] 未检测到输入，自动终止进程...")
            confirm = "y"
        else:
            confirm = confirm.strip().lower()

    if confirm in ("y", "yes"):
        print()
        print("[终止] 正在停止进程...")
        killed = 0
        for p in sim_procs:
            print(f"  正在终止 PID {p['pid']}...", end=" ")
            if _kill_process(p["pid"]):
                print("成功")
                killed += 1
            else:
                print("失败")
        print()
        print(f"[完成] 已终止 {killed}/{len(sim_procs)} 个进程。")
    else:
        print("[取消] 未执行终止操作。")


if __name__ == "__main__":
    main()
