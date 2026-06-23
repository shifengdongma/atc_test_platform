import os
import glob

DOWNLOAD_PATH = r"C:\Users\wdjlw\Downloads"
LOG_PATTERN = "la-atc-daemon-server-*"

def delete_log_files():
    """删除下载路径中的日志文件"""
    pattern = os.path.join(DOWNLOAD_PATH, LOG_PATTERN)
    files = glob.glob(pattern)
    
    if not files:
        print(f"未找到匹配的文件: {LOG_PATTERN}")
        return
    
    print(f"找到 {len(files)} 个文件:")
    for f in files:
        print(f"  - {os.path.basename(f)}")
    
    deleted = 0
    for f in files:
        try:
            os.remove(f)
            print(f"  已删除: {os.path.basename(f)}")
            deleted += 1
        except Exception as e:
            print(f"  删除失败 {os.path.basename(f)}: {e}")
    print(f"\n共删除 {deleted} 个文件")

if __name__ == "__main__":
    delete_log_files()
