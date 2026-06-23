#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 json 目录数据运行航迹准确度计算。

等价于将 trajectory_accuracy.py 的 DEFAULT_JSON_DIR 改为 json 后执行：
  --simulated json/kafka_data.json
  --predicted json/redis_trace.json
  --html json/trajectory_accuracy_report.html
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

# 项目根目录（tools 的上级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = PROJECT_ROOT / "json"
SCRIPT = Path(__file__).resolve().parent / "trajectory_accuracy.py"


def main() -> int:
    simulated = JSON_DIR / "kafka_data.json"
    predicted = JSON_DIR / "redis_trace.json"
    html_out = JSON_DIR / "trajectory_accuracy_report.html"
    json_out = JSON_DIR / "trajectory_accuracy_report.json"

    if not SCRIPT.exists():
        print(f"错误: 未找到脚本 {SCRIPT}", file=sys.stderr)
        return 1
    if not simulated.exists():
        print(f"错误: 未找到模拟数据 {simulated}", file=sys.stderr)
        return 1
    if not predicted.exists():
        print(f"错误: 未找到预测数据 {predicted}", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--simulated", str(simulated),
        "--predicted", str(predicted),
        "--html", str(html_out),
        # "--output", str(json_out),
    ]
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT)).returncode


if __name__ == "__main__":
    sys.exit(main())
