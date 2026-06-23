#!/bin/bash
'''
while true; do
    timestamp=$(date +"%Y-%m-%d %H:%M:%S.%3N")
    echo "[$timestamp] 开始请求..."
    result=$(curl -k -s --max-time 0.1 --connect-timeout 0.1  "https://10.165.26.246/dolphin-agent/cluster.txt")
    echo "[$timestamp] $result"
    echo "---"
done
'''
URL="https://10.165.26.246/dolphin-agent/cluster.txt"

last_ok=-1      # -1=初始, 0=失败, 1=成功
last_change=""  # 上次状态变化时间（毫秒级）

while true; do
    # 只取一次时间戳，兼容 Windows Git Bash
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    start_ms=$(date +%s%N 2>/dev/null || date +%s000000000)  # 纳秒/毫秒备用
    start_ms=${start_ms:0:13}  # 取到毫秒位
    
    # 请求
    result=$(curl -k -s --max-time 0.1 --connect-timeout 0.1 "$URL" 2>/dev/null)
    
    # 计算耗时
    end_ms=$(date +%s%N 2>/dev/null || date +%s000000000)
    end_ms=${end_ms:0:13}
    cost=$((end_ms - start_ms))
    
    # 判定状态：有返回值即为通
    if [ -n "$result" ]; then
        ok=1
        status="通"
    else
        ok=0
        status="不通"
        result="N/A"
    fi
    
    # 仅在状态变化时计算持续时长
    extra=""
    if [ $last_ok -ne -1 ] && [ $last_ok -ne $ok ]; then
        if [ $ok -eq 1 ]; then
            # 从 不通→通，计算恢复耗时
            duration=$(( (end_ms - last_change) / 1000000 ))
            extra=" | 恢复耗时=${duration}ms"
        else
            # 从 通→不通，记录变化时间点
            last_change=$end_ms
        fi
    fi
    
    # 首次初始化
    if [ $last_ok -eq -1 ]; then
        last_change=$end_ms
    fi
    last_ok=$ok
    
    # 单行输出
    echo "[$ts] 状态=$status | 请求耗时=${cost}μs | 结果=$result$extra"
    
    # 如需间隔可放开
    # sleep 0.1
done