# -*- coding: utf-8 -*-
"""
公共基础设施层 — 配置、日志、类型、校验

模块：
- config:       统一配置管理（dataclass 层次，环境变量 > env.py > 默认值）
- exceptions:   语义化异常层次（9个异常类）
- log_setup:    结构化日志初始化
- schemas:      TypedDict 类型定义（飞行计划/遥测/空域/场景）
- validators:   Pydantic 数据校验器
"""
