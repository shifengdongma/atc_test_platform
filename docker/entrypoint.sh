#!/bin/bash
# ATC/UTM 模拟器 Docker 入口脚本
# 功能：启动前环境检查 + 信号处理 + 优雅退出

set -e

echo "============================================"
echo " ATC/UTM 无人机模拟器 Web 控制台"
echo " 版本: ${IMAGE_VERSION:-unknown}"
echo " 启动时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ── 环境变量检查 ─────────────────────────────────────
echo "[1/3] 检查运行环境..."

# 检查 env.py 是否存在
if [ -f "/app/utm_simulator/env.py" ]; then
    echo "  ✓ env.py 配置文件已挂载"
else
    echo "  ⚠ env.py 未找到，使用环境变量模式"
fi

# 检查 Python 版本
PYTHON_VERSION=$(python --version 2>&1)
echo "  ✓ ${PYTHON_VERSION}"

# ── 连接测试（可选，超时 5s）─────────────────────────
echo "[2/3] 连通性检测..."

# Redis
if [ -n "${UTM_REDIS_HOST}" ]; then
    REDIS_HOST="${UTM_REDIS_HOST}"
    REDIS_PORT="${UTM_REDIS_PORT:-21003}"
    if timeout 5 bash -c "echo >/dev/tcp/${REDIS_HOST}/${REDIS_PORT}" 2>/dev/null; then
        echo "  ✓ Redis 可达 (${REDIS_HOST}:${REDIS_PORT})"
    else
        echo "  ⚠ Redis 不可达 (${REDIS_HOST}:${REDIS_PORT})，服务启动后可能报错"
    fi
else
    echo "  ⚠ 未配置 UTM_REDIS_HOST"
fi

# Kafka
if [ -n "${UTM_KAFKA_URL}" ]; then
    KAFKA_HOST=$(echo "${UTM_KAFKA_URL}" | cut -d: -f1)
    KAFKA_PORT=$(echo "${UTM_KAFKA_URL}" | cut -d: -f2)
    if timeout 5 bash -c "echo >/dev/tcp/${KAFKA_HOST}/${KAFKA_PORT}" 2>/dev/null; then
        echo "  ✓ Kafka 可达 (${KAFKA_HOST}:${KAFKA_PORT})"
    else
        echo "  ⚠ Kafka 不可达 (${KAFKA_HOST}:${KAFKA_PORT})，服务启动后可能报错"
    fi
else
    echo "  ⚠ 未配置 UTM_KAFKA_URL"
fi

# ── 启动 Web 服务 ────────────────────────────────────
echo "[3/3] 启动 Web 控制台..."
echo "  监听地址: http://0.0.0.0:${FLASK_PORT:-5000}"
echo "============================================"

cd /app/utm_simulator

# 捕获 SIGTERM/SIGINT，优雅关闭
cleanup() {
    echo ""
    echo "收到退出信号，正在关闭..."
    # Flask 进程会收到信号自行退出
    wait
    echo "服务已停止。"
    exit 0
}
trap cleanup SIGTERM SIGINT

exec python web_server.py
