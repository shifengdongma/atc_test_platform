import requests
import time
import os

# 抑制SSL警告
requests.packages.urllib3.disable_warnings()

# 定义请求的URL
URL = "https://10.165.32.35/dolphin-agent/cluster.txt"

# 获取脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 创建日志目录
LOG_DIR = os.path.join(SCRIPT_DIR, "log")
os.makedirs(LOG_DIR, exist_ok=True)

# 生成日志文件名
log_filename = time.strftime("cluster_master_%Y%m%d_%H_%M.txt")
log_filepath = os.path.join(LOG_DIR, log_filename)

def get_cluster_info():
    """获取并解析集群信息"""
    try:
        # 发送HTTP请求
        response = requests.get(URL, verify=False)  # 忽略SSL验证，因为是内部地址
        response.raise_for_status()  # 检查请求是否成功
        
        # 解析响应内容
        content = response.text.strip()
        
        # 识别集群
        if "cluster_B" in content:
            cluster = "集群B"
        elif "cluster_A" in content:
            cluster = "集群A"
        else:
            cluster = "未知集群"
        
        return cluster
    except Exception as e:
        print(f"请求失败: {e}")
        return "未知集群"

def main():
    """主函数，循环执行"""
    print("开始监控集群状态...")
    print(f"日志文件: {log_filepath}")
    print("格式: 时间(到秒)、集群x")
    print("按 Ctrl+C 停止执行")
    
    try:
        while True:
            # 记录循环开始时间
            start_time = time.time()
            
            # 获取当前时间（到秒）
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取集群信息
            cluster = get_cluster_info()
            
            # 输出结果
            log_line = f"{current_time}、{cluster}"
            print(log_line)
            
            # 写入日志文件
            with open(log_filepath, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
            
            # 计算需要睡眠的时间，确保总循环时间接近1秒
            elapsed_time = time.time() - start_time
            sleep_time = max(0, 1 - elapsed_time)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\n执行已停止")
        return

if __name__ == "__main__":
    main()