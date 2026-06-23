import os
import glob
import re
from datetime import datetime

DOWNLOAD_PATH = r"C:\Users\wdjlw\Downloads"
LOG_DIR_PATTERN = "la-atc-daemon-server-*"

VIP_SWITCH_KEYWORD = "VIP switch detected, new cluster sign"
BUSINESS_SWITCH_KEYWORD = "Deleting pod:"

def get_latest_log_file_or_dir():
    """获取下载路径中最新的日志文件或目录"""
    pattern = os.path.join(DOWNLOAD_PATH, LOG_DIR_PATTERN)
    items = glob.glob(pattern)
    
    if not items:
        return None
    
    items.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return items[0]

def get_log_files(path):
    """获取日志文件列表（支持文件或目录）"""
    if os.path.isfile(path):
        return [path]
    elif os.path.isdir(path):
        log_files = []
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith('.log') or file.endswith('.txt') or 'log' in file.lower():
                    log_files.append(os.path.join(root, file))
        return log_files
    return []

def parse_log_line(line):
    """解析日志行，提取时间和切换类型"""
    timestamp_pattern = r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})'
    
    timestamp_match = re.search(timestamp_pattern, line)
    if not timestamp_match:
        return None, None
    
    timestamp = timestamp_match.group(1).replace('T', ' ')
    
    if VIP_SWITCH_KEYWORD in line:
        return timestamp, "海豚切换"
    elif BUSINESS_SWITCH_KEYWORD in line:
        return timestamp, "业务切换"
    
    return None, None

def analyze_logs(log_files):
    """分析日志文件，提取切换事件"""
    events = []
    
    for log_file in log_files:
        print(f"  分析: {os.path.basename(log_file)}")
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    timestamp, switch_type = parse_log_line(line)
                    if timestamp and switch_type:
                        events.append((timestamp, switch_type, log_file))
        except Exception as e:
            print(f"    读取失败: {e}")
    
    events.sort(key=lambda x: x[0])
    return events

def display_results(events):
    """以表格形式显示结果"""
    if not events:
        print("未找到任何切换事件")
        return
    
    print(f"{'序号':^6} | {'日志打印时间':^20} | {'切换类型':^10}")
    print("-" * 44)
    
    for idx, (timestamp, switch_type, _) in enumerate(events, 1):
        print(f"{idx:^6} | {timestamp:^20} | {switch_type:^10}")

def main():
    print("=" * 60)
    print("日志分析工具 - VIP切换与业务切换检测")
    print("=" * 60)
    
    print(f"\n下载路径: {DOWNLOAD_PATH}")
    
    latest_item = get_latest_log_file_or_dir()
    if not latest_item:
        print(f"未找到匹配的日志: {LOG_DIR_PATTERN}")
        return
    
    item_type = "文件" if os.path.isfile(latest_item) else "目录"
    print(f"最新日志{item_type}: {latest_item}")
    print(f"修改时间: {datetime.fromtimestamp(os.path.getmtime(latest_item)).strftime('%Y-%m-%d %H:%M:%S')}")
    
    log_files = get_log_files(latest_item)
    if not log_files:
        print("未找到日志文件")
        return
    
    print(f"找到 {len(log_files)} 个日志文件")
    print("\n正在分析日志...")
    
    events = analyze_logs(log_files)
    
    print(f"\n共发现 {len(events)} 个切换事件:\n")
    display_results(events)
    
    vip_count = sum(1 for e in events if e[1] == "海豚切换")
    business_count = sum(1 for e in events if e[1] == "业务切换")
    
    print(f"\n统计:")
    print(f"  - 海豚切换: {vip_count} 次")
    print(f"  - 业务切换: {business_count} 次")

if __name__ == "__main__":
    main()
