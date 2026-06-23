#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT 连接检测脚本
用于检测 MQTT 服务器是否可以连接成功
"""

import socket
import sys
import argparse
from datetime import datetime


def check_mqtt_connection(host, port, timeout=5):
    """
    检测 MQTT 服务器连接状态
    
    Args:
        host: MQTT 服务器地址
        port: MQTT 服务器端口
        timeout: 连接超时时间（秒）
    
    Returns:
        tuple: (是否成功, 错误信息)
    """
    try:
        # 创建 socket 连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        # 尝试连接
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            return True, None
        else:
            error_msg = f"连接失败，错误码: {result}"
            if result == 10061:
                error_msg = "连接被拒绝，MQTT 服务未运行"
            elif result == 10060:
                error_msg = "连接超时，网络不可达"
            elif result == 10051:
                error_msg = "网络不可达"
            return False, error_msg
            
    except socket.gaierror:
        return False, "无法解析主机地址"
    except socket.timeout:
        return False, "连接超时"
    except Exception as e:
        return False, f"连接异常: {str(e)}"


def main():
    parser = argparse.ArgumentParser(description='MQTT 连接检测工具')
    parser.add_argument('--host', default='10.165.19.100', help='MQTT 服务器地址 (默认: 10.165.19.100)')
    parser.add_argument('--port', type=int, default=21883, help='MQTT 服务器端口 (默认: 21883)')
    parser.add_argument('--timeout', type=int, default=5, help='连接超时时间（秒）(默认: 5)')
    parser.add_argument('--retry', type=int, default=1, help='重试次数 (默认: 1)')
    
    args = parser.parse_args()
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] MQTT 连接检测")
    print(f"目标地址: tcp://{args.host}:{args.port}")
    print(f"超时时间: {args.timeout}秒")
    print(f"重试次数: {args.retry}")
    print("-" * 50)
    
    success_count = 0
    fail_count = 0
    
    for i in range(args.retry):
        if args.retry > 1:
            print(f"\n第 {i + 1}/{args.retry} 次检测...")
        
        success, error = check_mqtt_connection(args.host, args.port, args.timeout)
        
        if success:
            success_count += 1
            print(f"✅ MQTT 连接成功")
        else:
            fail_count += 1
            print(f"❌ MQTT 连接失败: {error}")
    
    print("-" * 50)
    print(f"检测完成: 成功 {success_count} 次, 失败 {fail_count} 次")
    
    # 返回退出码
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
