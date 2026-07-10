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

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 时区
ENV TZ=Asia/Shanghai
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

WORKDIR /app

# ── 安装 Python 依赖（一次性从 requirements.txt 安装全部依赖）──
COPY utm_simulator/requirements.txt /app/utm_simulator/requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r /app/utm_simulator/requirements.txt

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

# Python import 路径 — 确保 Python 能找到 /app 下各模块（common/ / database/ / services/）
ENV PYTHONPATH=/app

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/sim/status || exit 1

EXPOSE 5000

WORKDIR /app/utm_simulator
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "web_server.py"]
