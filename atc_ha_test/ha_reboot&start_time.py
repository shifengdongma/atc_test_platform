import datetime
import subprocess
import requests
import time
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 配置区域 ====================

# 场景开关："reboot" 表示服务器重启场景，"start" 表示物理机启动场景
SCENARIO = "reboot"  # 可选值: "reboot" 或 "start"

# 目标IP地址（只监控单个服务器）
TARGET_IP = "10.165.32.24"

# 检测间隔（秒）
CHECK_INTERVAL = 5

# 服务URL列表
URLS = {
    "iomp": f"http://{TARGET_IP}:8801/iomp",
    "rbac": f"https://{TARGET_IP}/cloud-rbac",
    "atc": f"https://{TARGET_IP}/atc/login"
}

# ==================== 工具函数 ====================

def get_now():
    """获取当前时间字符串"""
    return datetime.datetime.now()

def format_time(dt):
    """格式化时间为字符串"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def time_diff_seconds(start, end):
    """计算两个时间之间的秒数差"""
    return (end - start).total_seconds()

def ping_host(ip):
    """Ping主机，返回是否连通"""
    ping_result = subprocess.run(
        ["ping", "-n", "1", ip],
        capture_output=True,
        text=True
    )
    return ping_result.returncode == 0

def check_url(url):
    """检测URL是否连通"""
    try:
        response = requests.get(url, timeout=5, verify=False)
        return response.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        return False

# ==================== 核心逻辑 ====================

def run_reboot_scenario():
    """
    Reboot场景：服务器重启监控
    脚本启动时服务器应处于可访问状态，随后服务器会被重启
    监控流程：脚本启动 -> 服务器ping不通（重启中）-> ping通 -> 服务恢复
    """
    script_start_time = get_now()
    print(f"[{format_time(script_start_time)}] Reboot场景监控启动，目标IP: {TARGET_IP}")
    print("等待服务器进入不可达状态（重启开始）...")
    print("-" * 80)

    last_ping_unreachable_time = None  # 最后一个ping不通的时间
    ping_recovered_time = None         # ping恢复的时间
    service_times = {                  # 各服务恢复时间
        "iomp": None,
        "rbac": None,
        "atc": None
    }

    # 阶段1：等待服务器ping不通（确认重启开始）
    reboot_started = False
    while not reboot_started:
        current_time = get_now()
        ping_ok = ping_host(TARGET_IP)

        if not ping_ok:
            last_ping_unreachable_time = current_time
            print(f"[{format_time(current_time)}] 服务器已不可达，重启开始")
            reboot_started = True
        else:
            print(f"[{format_time(current_time)}] 服务器仍可达，等待重启...")

        time.sleep(CHECK_INTERVAL)

    # 阶段2：持续监控，等待ping恢复和服务恢复
    print("-" * 80)
    print("等待服务器恢复...")
    print("-" * 80)

    while True:
        current_time = get_now()
        ping_ok = ping_host(TARGET_IP)

        # 记录ping恢复时间
        if ping_ok and ping_recovered_time is None:
            ping_recovered_time = current_time
            print(f"[{format_time(current_time)}] 服务器ping已恢复")

        # 如果ping已恢复，检测服务状态
        if ping_ok:
            for service_name, url in URLS.items():
                if service_times[service_name] is None:
                    if check_url(url):
                        service_times[service_name] = current_time
                        print(f"[{format_time(current_time)}] 服务 [{service_name}] 已连通")

        # 检查是否所有服务都已恢复
        if all(t is not None for t in service_times.values()):
            atc_recovered_time = service_times["atc"]
            print("-" * 80)
            print("所有服务已恢复！汇总结果：")
            print("-" * 80)
            print(f"脚本执行时间:           {format_time(script_start_time)}")
            print(f"最后一个ping不通时间:   {format_time(last_ping_unreachable_time)}")
            print(f"ping通时间:             {format_time(ping_recovered_time)}")
            print(f"iomp连通时间:           {format_time(service_times['iomp'])}")
            print(f"rbac连通时间:           {format_time(service_times['rbac'])}")
            print(f"atc连通时间:            {format_time(atc_recovered_time)}")
            print("-" * 80)
            print(f"重启时间1 (atc连通时间 - 脚本执行时间):        {time_diff_seconds(script_start_time, atc_recovered_time):.2f} 秒")
            print(f"重启时间2 (atc连通时间 - 最后一个ping不通时间): {time_diff_seconds(last_ping_unreachable_time, atc_recovered_time):.2f} 秒")
            print("-" * 80)
            break

        # 更新最后一个ping不通时间（如果仍然不通）
        if not ping_ok:
            last_ping_unreachable_time = current_time

        time.sleep(CHECK_INTERVAL)


def run_start_scenario():
    """
    Start场景：物理机启动监控
    脚本启动时物理机处于关机/未启动状态
    监控流程：脚本启动 -> 等待ping通 -> 服务恢复
    """
    script_start_time = get_now()
    print(f"[{format_time(script_start_time)}] Start场景监控启动，目标IP: {TARGET_IP}")
    print("等待物理机启动（ping通）...")
    print("-" * 80)

    ping_recovered_time = None          # ping恢复的时间
    service_times = {                   # 各服务恢复时间
        "iomp": None,
        "rbac": None,
        "atc": None
    }

    while True:
        current_time = get_now()
        ping_ok = ping_host(TARGET_IP)

        # 记录ping恢复时间（仅第一次）
        if ping_ok and ping_recovered_time is None:
            ping_recovered_time = current_time
            print(f"[{format_time(current_time)}] 物理机已ping通")
            print("-" * 80)
            print("等待服务恢复...")
            print("-" * 80)

        # 如果ping已恢复，检测服务状态
        if ping_ok:
            for service_name, url in URLS.items():
                if service_times[service_name] is None:
                    if check_url(url):
                        service_times[service_name] = current_time
                        print(f"[{format_time(current_time)}] 服务 [{service_name}] 已连通")

            # 检查是否所有服务都已恢复
            if all(t is not None for t in service_times.values()):
                atc_recovered_time = service_times["atc"]
                print("-" * 80)
                print("所有服务已恢复！汇总结果：")
                print("-" * 80)
                print(f"脚本执行时间:   {format_time(script_start_time)}")
                print(f"ping通时间:     {format_time(ping_recovered_time)}")
                print(f"iomp连通时间:   {format_time(service_times['iomp'])}")
                print(f"rbac连通时间:   {format_time(service_times['rbac'])}")
                print(f"atc连通时间:    {format_time(atc_recovered_time)}")
                print("-" * 80)
                print(f"启动时间1 (atc连通时间 - 脚本执行时间): {time_diff_seconds(script_start_time, atc_recovered_time):.2f} 秒")
                print(f"启动时间2 (atc连通时间 - ping通时间):   {time_diff_seconds(ping_recovered_time, atc_recovered_time):.2f} 秒")
                print("-" * 80)
                break
        else:
            print(f"[{format_time(current_time)}] 物理机尚未ping通，继续等待...")

        time.sleep(CHECK_INTERVAL)


# ==================== 主入口 ====================

if __name__ == "__main__":
    if SCENARIO == "reboot":
        run_reboot_scenario()
    elif SCENARIO == "start":
        run_start_scenario()
    else:
        print(f"错误: 未知的场景配置 '{SCENARIO}'，请设置为 'reboot' 或 'start'")
