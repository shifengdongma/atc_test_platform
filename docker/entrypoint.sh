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

# ── 数据库配置诊断 ────────────────────────────────────
echo ""
echo "=== 数据库配置诊断 ==="

# MySQL
echo "  [MySQL]"
if [ -n "${UTM_MYSQL_HOST}" ]; then
    echo "    ✓ UTM_MYSQL_HOST=${UTM_MYSQL_HOST}"
    echo "    PORT=${UTM_MYSQL_PORT:-3306}, DB=${UTM_MYSQL_DB:-utm_simulator}, USER=${UTM_MYSQL_USER:-(默认)}"
else
    echo "    ⚠ UTM_MYSQL_HOST 未设置"
    echo "    容器将尝试从 /app/utm_simulator/env.py 读取 MYSQL_HOST"
    if [ -f "/app/utm_simulator/env.py" ]; then
        ENV_MYSQL_HOST=$(grep -oP 'MYSQL_HOST\s*=\s*["'"'"']?\K[^"'"'"'\n]+' /app/utm_simulator/env.py 2>/dev/null || echo "无法解析")
        echo "    env.py 中 MYSQL_HOST=${ENV_MYSQL_HOST}"
        if [ "${ENV_MYSQL_HOST}" = "127.0.0.1" ] || [ "${ENV_MYSQL_HOST}" = "localhost" ]; then
            echo "    ⚠⚠⚠ WARNING: env.py 中 MYSQL_HOST=${ENV_MYSQL_HOST}，容器内不可达！"
            echo "    请在 1Panel 环境变量中设置 UTM_MYSQL_HOST=实际的MySQL地址"
        fi
    else
        echo "    env.py 未挂载，MySQL 将保持未配置状态 (configured=False)"
    fi
fi

# 达梦
echo "  [达梦]"
if [ -n "${UTM_DM_HOST}" ]; then
    echo "    UTM_DM_HOST=${UTM_DM_HOST}, PORT=${UTM_DM_PORT:-5237}, SCHEMA=${UTM_DM_SCHEMA:-ATC_DKWRJ_TEST}"
else
    echo "    UTM_DM_HOST 未设置，使用默认值 10.165.32.32"
fi
echo "    OpenSSL 1.1 库检测:"
if ldconfig -p 2>/dev/null | grep -q libssl.so.1.1; then
    echo "      ✓ libssl.so.1.1 已安装"
else
    echo "      ✗ libssl.so.1.1 未安装！达梦加密模块将不可用 (-70089)"
fi
if ldconfig -p 2>/dev/null | grep -q libcrypto.so.1.1; then
    echo "      ✓ libcrypto.so.1.1 已安装"
else
    echo "      ✗ libcrypto.so.1.1 未安装！达梦加密模块将不可用 (-70089)"
fi

# 命名卷代码版本检查
echo "  [代码版本]"
if [ -f "/app/database/json_data_manager.py" ]; then
    if grep -q "query_available_routes" /app/database/json_data_manager.py 2>/dev/null; then
        echo "    ✓ json_data_manager.py: 包含 query_available_routes"
    else
        echo "    ✗✗✗ CRITICAL: json_data_manager.py 版本过旧（缺少 query_available_routes）！"
        echo "    命名卷缓存了旧代码，请执行以下步骤更新："
        echo "      docker compose down"
        echo "      docker volume rm atc_test_platfrom_utm-database"
        echo "      docker compose build --no-cache"
        echo "      docker compose up -d"
    fi
else
    echo "    ⚠ /app/database/json_data_manager.py 未找到"
fi

# pymysql/MySQL 导入验证
echo "  [pymysql/MySQL]"
PYMYSQL_CHECK=$(python -c "import pymysql; print(pymysql.__version__)" 2>&1) || true
if echo "$PYMYSQL_CHECK" | grep -qE '^[0-9]+\.[0-9]+'; then
    echo "    ✓ pymysql ${PYMYSQL_CHECK} 已安装，mysqldbclient 可导入"
else
    echo "    ✗✗✗ CRITICAL: pymysql 未安装或导入失败！"
    echo "    错误详情: ${PYMYSQL_CHECK}"
    echo "    修复: docker compose build --no-cache (确保 pip install pymysql 成功)"
fi

# DBUtils/PooledDB 导入验证
echo "  [DBUtils/PooledDB]"
DBUTILS_CHECK=$(python -c "from dbutils.pooled_db import PooledDB; print('OK')" 2>&1) || true
if [ "$DBUTILS_CHECK" = "OK" ]; then
    echo "    ✓ DBUtils/PooledDB 已安装，连接池可用"
else
    echo "    ✗✗✗ CRITICAL: DBUtils 未安装或导入失败！"
    echo "    错误详情: ${DBUTILS_CHECK}"
    echo "    修复: docker compose build --no-cache (确保 pip install DBUtils>=3.0 成功)"
fi

# MySQL 连接测试（仅在配置了 UTM_MYSQL_HOST 时）
if [ -n "${UTM_MYSQL_HOST}" ]; then
    MYSQL_TEST=$(python -c "
import pymysql
try:
    conn = pymysql.connect(host='${UTM_MYSQL_HOST}', port=${UTM_MYSQL_PORT:-3306},
                           user='${UTM_MYSQL_USER}', password='${UTM_MYSQL_PASSWORD}',
                           database='${UTM_MYSQL_DB:-utm_simulator}',
                           ssl={}, connect_timeout=5)
    conn.close()
    print('OK')
except Exception as e:
    print(f'FAIL: {e}')
" 2>&1) || true
    if echo "$MYSQL_TEST" | grep -q '^OK$'; then
        echo "    ✓ MySQL 连接成功 (${UTM_MYSQL_HOST}:${UTM_MYSQL_PORT:-3306}/${UTM_MYSQL_DB:-utm_simulator})"
    else
        echo "    ✗ MySQL 连接失败: ${MYSQL_TEST}"
        echo "    检查: 1) UTM_MYSQL_HOST/PORT/USER/PASSWORD 是否正确"
        echo "         2) MySQL 用户 '${UTM_MYSQL_USER}' 是否允许从容器 IP 连接"
        echo "         3) MySQL 服务是否正常运行"
    fi
else
    echo "    ⚠ UTM_MYSQL_HOST 未设置，跳过 MySQL 连接测试"
fi

echo "========================="
echo ""

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

# ── 达梦 dmPython 加密模块：强制预加载 OpenSSL 1.1 库 ──
# dmPython 自带 dmssl/libcrypto.so 可能与系统库冲突导致 -70089
# LD_PRELOAD 确保系统 OpenSSL 1.1 库最先被动态链接器加载
if [ -f /usr/lib/x86_64-linux-gnu/libssl.so.1.1 ] && [ -f /usr/lib/x86_64-linux-gnu/libcrypto.so.1.1 ]; then
    export LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libssl.so.1.1:/usr/lib/x86_64-linux-gnu/libcrypto.so.1.1"
    echo "  ✓ LD_PRELOAD 已设置 (OpenSSL 1.1 优先加载)"
else
    echo "  ⚠ 未找到 OpenSSL 1.1 库，LD_PRELOAD 跳过"
fi

exec python web_server.py
