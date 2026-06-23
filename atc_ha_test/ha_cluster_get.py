#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高可用集群状态探测脚本
功能：循环探测 cluster.txt 接口，毫秒级记录请求耗时与状态变化间隔
逻辑等价于 ha_cluster_get.sh 第 11-64 行
"""

import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime

URL = "https://10.165.26.246/dolphin-agent/cluster.txt"

# 状态常量
STATE_INIT = -1   # 初始
STATE_FAIL = 0    # 失败（不通）
STATE_OK = 1      # 成功（通）

last_ok = STATE_INIT      # 上一次请求状态
last_change_ns = 0        # 上次状态变化时间（纳秒级）


def get_now_str() -> str:
    """获取当前格式化时间字符串（精确到毫秒）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def get_time_ns() -> int:
    """获取当前纳秒级时间戳"""
    return time.time_ns()


def do_request(url: str) -> str:
    """
    发起 HTTPS GET 请求（跳过证书校验，超时 0.1s）
    返回响应正文；异常时返回空字符串
    """
    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=0.1, context=ctx) as resp:
            return ' '.join(resp.read().decode("utf-8").strip().split())
    except Exception:
        return ""


def main() -> None:
    global last_ok, last_change_ns

    while True:
        # 记录请求前时间
        ts = get_now_str()
        start_ns = get_time_ns()

        # 发起请求
        result = do_request(URL)

        # 计算耗时
        end_ns = get_time_ns()
        cost_ns = end_ns - start_ns
        cost_ms = cost_ns / 1_000_000  # 纳秒转毫秒

        # 判定状态：有返回值即为通
        if result:
            ok = STATE_OK
            status = "通"
        else:
            ok = STATE_FAIL
            status = "不通"
            result = "N/A"

        # 仅在状态变化时计算持续时长
        extra = ""
        if last_ok != STATE_INIT and last_ok != ok:
            if ok == STATE_OK:
                # 从 不通 -> 通，计算恢复耗时
                duration_ms = (end_ns - last_change_ns) / 1_000_000
                extra = f" | 恢复耗时={duration_ms:.0f}ms"
            else:
                # 从 通 -> 不通，记录变化时间点
                last_change_ns = end_ns

        # 首次初始化
        if last_ok == STATE_INIT:
            last_change_ns = end_ns
        last_ok = ok

        # 单行输出
        print(f"[{ts}] 状态={status} | 请求耗时={cost_ms:.0f}μs | 结果={result}{extra}")

        # 如需间隔可放开
        # time.sleep(0.1)


if __name__ == "__main__":
    main()
