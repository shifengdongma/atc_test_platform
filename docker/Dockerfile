# -*- coding: utf-8 -*-
# ATC/UTM 自动化测试平台 — Docker 镜像
# 构建：docker build -t utm-simulator:latest -f docker/Dockerfile .
# 说明：基于项目根目录构建，主服务为 utm_simulator/web_server.py (Flask :5000)

FROM python:3.11-slim

LABEL maintainer="atc-team"
LABEL description="低空空管 UTM 无人机模拟器 Web 控制台"

# 替换 Debian 源为阿里云镜像（国内网络加速 apt 下载）
RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources

# 系统依赖（含达梦 dmPython 加密/DPI 模块所需的全部系统库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    openssl \
    libssl3 \
    libatomic1 \
    libc6 \
    libgcc-s1 \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# ── 达梦 dmPython 加密模块补丁 ─────────────────────────
# dmPython Linux .so 动态链接 libssl.so.1.1 / libcrypto.so.1.1
# python:3.11-slim (Debian 12 Bookworm) 默认只有 OpenSSL 3.x (libssl.so.3)
# 需从 Debian 11 Bullseye 获取 OpenSSL 1.1 兼容库。
# 独立 RUN 层：便于缓存隔离，安装失败时可单独排查本层日志。
RUN echo "deb http://mirrors.aliyun.com/debian bullseye main" > /etc/apt/sources.list.d/bullseye.list && \
    apt-get update -o Acquire::AllowReleaseInfoChange=true -qq && \
    apt-get install -y --no-install-recommends libssl1.1 && \
    rm -f /etc/apt/sources.list.d/bullseye.list && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ── 验证 OpenSSL 1.1 库文件完整性 ─────────────────────
# dmPython 同时依赖 libssl.so.1.1 和 libcrypto.so.1.1，缺一不可
RUN echo "=== libssl1.1 包文件列表 ===" && \
    dpkg -L libssl1.1 2>/dev/null | grep -E '\.so' && \
    echo "=== 验证 libssl.so.1.1 ===" && \
    ldconfig -p | grep -q libssl.so.1.1 && echo "  ✓ libssl.so.1.1 已注册" || \
    (echo "  ✗ libssl.so.1.1 未找到！达梦加密模块将不可用 (-70089)" >&2 && exit 1) && \
    echo "=== 验证 libcrypto.so.1.1 ===" && \
    ldconfig -p | grep -q libcrypto.so.1.1 && echo "  ✓ libcrypto.so.1.1 已注册" || \
    (echo "  ✗ libcrypto.so.1.1 未找到！达梦加密模块将不可用 (-70089)" >&2 && exit 1) && \
    echo "=== OpenSSL 1.1 验证全部通过 ==="

# 时区
ENV TZ=Asia/Shanghai
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

WORKDIR /app

# ── 安装 Python 依赖（一次性从 requirements.txt 安装全部依赖）──
COPY utm_simulator/requirements.txt /app/utm_simulator/requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r /app/utm_simulator/requirements.txt \
    && python -c "import pymysql; v=pymysql.__version__; assert v<'2.0', f'pymysql版本 {v} 不兼容，需1.x！请检查requirements.txt'; print(f'pymysql {v} OK')" \
    && python -c "from dbutils.pooled_db import PooledDB; print(f'DBUtils OK, PooledDB={PooledDB}')"

# ── 达梦数据库驱动（仅 Linux/Docker 需要，v2.5.22+ 自带 DPI 库免配置）──
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com dmPython>=2.5.22

# ── 复制项目文件 ─────────────────────────────────────
# 仅复制运行时需要的模块（利用 .dockerignore 排除不必要文件）
COPY utm_simulator/ /app/utm_simulator/
COPY atc_api_autotest/ /app/atc_api_autotest/
COPY atc_ha_test/ /app/atc_ha_test/
COPY web/ /app/web/
COPY data/ /app/data/
COPY database/ /app/database/
COPY common/ /app/common/
COPY services/ /app/services/

# 入口脚本
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ── 环境变量 ─────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5000

# 达梦 dmPython 需要找到自带加密库 (dmssl/libcrypto.so) 和系统 OpenSSL 1.1
# dmssl 目录必须排在首位：DPI 库运行时 dlopen("libcrypto.so") 优先加载自带版本
# libssl1.1 包将 .so 安装在 /usr/lib/x86_64-linux-gnu/，确保在链接路径中
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/dmssl:/usr/lib/x86_64-linux-gnu:/usr/lib:${LD_LIBRARY_PATH}

# Python import 路径 — 确保 Python 能找到 /app 下各模块（common/ / database/ / services/）
ENV PYTHONPATH=/app

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/sim/status || exit 1

EXPOSE 5000

WORKDIR /app/utm_simulator
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "web_server.py"]
