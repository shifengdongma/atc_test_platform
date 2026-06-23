import datetime
import subprocess
import requests
import time
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置目标IP地址
IP_ADDRESSES = [
    "10.165.32.24",
    "10.165.32.25"
]

# 主循环
while True:
    # 获取当前时间
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 循环检测每个IP及其URL
    for ip in IP_ADDRESSES:
        # 为当前IP生成URL列表
        urls = [
            f"http://{ip}:8801/iomp",
            f"https://{ip}/dops",
            f"https://{ip}/cloud-rbac",
            f"https://{ip}/atc/login"
        ]
        
        # Ping IP地址
        ping_result = subprocess.run(
            ["ping", "-n", "1", ip],
            capture_output=True,
            text=True
        )
        ping_status = "连通" if ping_result.returncode == 0 else "不通"
        
        # 检测每个URL
        url_statuses = []
        for url in urls:
            try:
                response = requests.get(url, timeout=5, verify=False)
                status = "连通" if response.status_code == 200 else "不通"
            except (requests.ConnectionError, requests.Timeout):
                status = "不通"
            url_statuses.append(status)
        
        # 输出结果
        print(f"{current_time} | IP_{ip.split('.')[-1]}| IP {ping_status}| iomp {url_statuses[0]}| dops {url_statuses[1]}|cloud-rbac {url_statuses[2]}|atc {url_statuses[3]}|")
    
    # 等待5秒后再次执行
    time.sleep(5)
