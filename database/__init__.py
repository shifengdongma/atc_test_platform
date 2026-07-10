# -*- coding: utf-8 -*-
"""
数据库持久化层 — SQLite + MySQL（可选）统一管理

模块：
- db_manager:       SQLite CRUD 基础操作
- env_manager:      多环境配置管理
- json_data_manager: JSON 文件管理（DB + data/mock/ 同步）
- scheduler:        Cron 定时任务调度
- log_streamer:     实时日志流（内存缓冲 + WebSocket + MySQL持久化）
"""
