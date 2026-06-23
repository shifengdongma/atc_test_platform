"""命令行工具模块"""

import argparse
from typing import Any, Dict


def parse_args(description: str, **kwargs) -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description=description)
    for key, value in kwargs.items():
        parser.add_argument(f'--{key}', **value)
    return parser.parse_args()


def print_progress(current: int, total: int, message: str = "") -> None:
    """打印进度信息"""
    percent = (current / total) * 100 if total > 0 else 0
    print(f"{message} [{current}/{total}] ({percent:.1f}%)")


def print_success(message: str) -> None:
    """打印成功信息"""
    print(f"✓ {message}")


def print_error(message: str) -> None:
    """打印错误信息"""
    print(f"✗ {message}")
