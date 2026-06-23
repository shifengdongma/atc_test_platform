#!/bin/bash
# 仅查看日志：bash deploy_repeat.sh -o
if [ "$1" = "-o" ]; then
  exec tail -f /opt/kdm/utm_moc/output.log
fi

# --count 透传给 lines_to_redis_route.py --count（默认 60）
TARGET_DRONES=60
[ "${1:-}" = "--count" ] && TARGET_DRONES="${2:?[deploy] --count 需要数值}" && shift 2
[ $# -eq 0 ] || { echo "[deploy] 未知参数: $*" >&2; exit 1; }

LINES_CMD="python3 -u tools/lines_to_redis_route.py --count ${TARGET_DRONES}"

# 若已有仿真进程则结束；无进程视为首次部署，创建目录 ps -ef |grep run_kafka
PIDS=$(pgrep -f "run_kafka_alive.py" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "[deploy] 发现运行中的 run_kafka_alive.py，PID: $PIDS，执行 kill -9, 启动算法"
  kill -9 $PIDS
  cd /opt/kdm/utm_moc && cp /tmp/utm_moc52.zip . && unzip -o utm_moc52.zip && ${LINES_CMD} && nohup python3 -u tools/run_kafka_alive.py > output.log 2>&1
else
  mkdir -p /opt/kdm/utm_moc
  echo "[deploy] 目录已就绪, 启动算法"
  cd /opt/kdm/utm_moc && cp /tmp/utm_moc52.zip . && unzip -o utm_moc52.zip && pip3 install --no-index --find-links=packages -r requirements.txt && ${LINES_CMD} && nohup python3 -u tools/run_kafka_alive.py > output.log 2>&1
fi

# cd /tmp && unzip -o utm_moc52.zip && bash deploy_repeat.sh -o
#python3 /opt/kdm/utm_moc/main.py
# cd /opt/kdm/utm_moc && nohup python3 -u main.py > output.log 2>&1
# cd /opt/kdm/utm_moc && nohup python3 -u main.py > /dev/null 2>&1
# tail -f /opt/kdm/utm_moc/output.log
# tail -f /log/user/dlapp.log

# pip download -r requirements.txt -d ./packages   
# pip install -r requirements.txt --no-index --find-links=./packages 
