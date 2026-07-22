# -*- coding: utf-8 -*-
# ATC/UTM 自动化测试平台 — Docker 镜像
#
# 构建（在项目根目录执行）：
#   docker build -t utm-simulator:latest -f docker/Dockerfile .
#
# 说明：
#   - 构建上下文 = 项目根目录（atc_test_platfrom/）
#   - 主服务入口 = web/server.py (Flask :5000)
#   - env.py 敏感配置通过运行时挂载注入，不进镜像

FROM python:3.11-slim

LABEL maintainer="atc-team"
LABEL description="低空空管 UTM 无人机模拟器 Web 控制台"

# ── 系统源加速（阿里云镜像）───────────────────────────
RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources

# ── 系统依赖 ──────────────────────────────────────────
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

# ── 达梦 dmPython 加密模块补丁 ───────────────────────
# dmPython Linux .so 动态链接 libssl.so.1.1 / libcrypto.so.1.1
# python:3.11-slim (Debian 12) 默认只有 OpenSSL 3.x
# 从 Debian 11 获取 OpenSSL 1.1 兼容库
RUN echo "deb http://mirrors.aliyun.com/debian bullseye main" > /etc/apt/sources.list.d/bullseye.list && \
    apt-get update -o Acquire::AllowReleaseInfoChange=true -qq && \
    apt-get install -y --no-install-recommends libssl1.1 && \
    rm -f /etc/apt/sources.list.d/bullseye.list && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ── 验证 OpenSSL 1.1 ──────────────────────────────────
RUN echo "=== libssl1.1 包文件列表 ===" && \
    dpkg -L libssl1.1 2>/dev/null | grep -E '\.so' && \
    echo "=== 验证 libssl.so.1.1 ===" && \
    ldconfig -p | grep -q libssl.so.1.1 && echo "  OK libssl.so.1.1" || \
    (echo "  ERR libssl.so.1.1 未找到！达梦加密模块将不可用 (-70089)" >&2 && exit 1) && \
    echo "=== 验证 libcrypto.so.1.1 ===" && \
    ldconfig -p | grep -q libcrypto.so.1.1 && echo "  OK libcrypto.so.1.1" || \
    (echo "  ERR libcrypto.so.1.1 未找到！达梦加密模块将不可用 (-70089)" >&2 && exit 1) && \
    echo "=== OpenSSL 1.1 验证通过 ==="

# ── 时区 ──────────────────────────────────────────────
ENV TZ=Asia/Shanghai
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

WORKDIR /app

# ── 安装 Python 依赖 ──────────────────────────────────
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r /app/requirements.txt \
    && python -c "import pymysql; v=pymysql.__version__; assert v<'2.0', f'pymysql {v} 不兼容，需1.x'; print(f'pymysql {v} OK')" \
    && python -c "from dbutils.pooled_db import PooledDB; print(f'DBUtils OK, PooledDB={PooledDB}')"

# ── 达梦数据库驱动（仅 Linux/Docker）──────────────────
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    dmPython>=2.5.22

# ── 复制项目文件 ─────────────────────────────────────
# 项目根目录结构：web/ core/ common/ database/ services/ tools/ data/
COPY web/       /app/web/
COPY core/      /app/core/
COPY common/    /app/common/
COPY database/  /app/database/
COPY services/  /app/services/
COPY tools/     /app/tools/
COPY data/      /app/data/

# 入口脚本
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ── 环境变量 ─────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5000

# 达梦 dmPython 加密库路径
# dmssl 目录必须排在首位：DPI 库运行时 dlopen("libcrypto.so") 优先加载自带版本
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/dmssl:/usr/lib/x86_64-linux-gnu:/usr/lib:${LD_LIBRARY_PATH}

# Python import 路径 — 确保能找到各模块
ENV PYTHONPATH=/app

# ── 健康检查 ─────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/sim/status || exit 1

EXPOSE 5000

WORKDIR /app
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "web/server.py"]
