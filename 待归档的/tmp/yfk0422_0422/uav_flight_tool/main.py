#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UAV 飞行数据工具 - 统一入口
整合 uav_emitter + utm_随机模拟飞行数据

用法:
    python main.py
    python main.py --mode simulation
    python main.py --config my_config.yaml
"""

import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config_manager import ConfigManager
from modes.scene_mode import SceneMode
from modes.simulation_mode import SimulationMode
from modes.stress_test_mode import StressTestMode


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           UAV 飞行数据工具 - 统一运行入口                         ║
║           整合 uav_emitter + utm_随机模拟飞行数据                  ║
╚══════════════════════════════════════════════════════════════════╝
""")


def create_mode(config_manager: ConfigManager, mode_override: str = None):
    """根据配置创建对应模式实例"""
    full_config = config_manager.get_full_config()
    mode = mode_override if mode_override else config_manager.get_mode()

    if mode == "scene":
        print("运行模式: 场景模式 (自定义轨迹)")
        return SceneMode(full_config)
    elif mode == "simulation":
        print("运行模式: 仿真模式 (随机生成 + 物理仿真)")
        return SimulationMode(full_config)
    elif mode == "stress_test":
        print("运行模式: 压力测试模式 (3000架 + 发送解耦)")
        return StressTestMode(full_config)
    else:
        raise ValueError(f"未知的运行模式: {mode}，支持的值: scene | simulation | stress_test")


def run_mode(mode_instance):
    """运行模式并处理用户中断"""
    mode_instance.start()

    try:
        if isinstance(mode_instance, SceneMode):
            # 场景模式：等待数据发送完毕
            while mode_instance.is_running():
                time.sleep(1)
        elif isinstance(mode_instance, SimulationMode):
            # 仿真模式：每秒打印汇总
            while mode_instance.is_running():
                if mode_instance.all_plans_ended():
                    print("所有飞行计划已全部完成，自动停止...")
                    mode_instance.stop()
                    break
                time.sleep(1)
                current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                kafka_stats = mode_instance.kafka_producer.get_and_reset_stats() if mode_instance.kafka_producer else {'success': 0, 'failed': 0}
                print(f"{current_time} [汇总] 当前活跃无人机总数: {mode_instance.active_drone_count()} ；插入kafka成功{kafka_stats['success']}条，失败{kafka_stats['failed']}条")
        elif isinstance(mode_instance, StressTestMode):
            # 压力测试模式：每秒打印汇总
            while mode_instance.is_running():
                if mode_instance.all_plans_ended():
                    print("所有飞行计划已全部完成，自动停止...")
                    mode_instance.stop()
                    break
                time.sleep(1)
                current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                kafka_stats = mode_instance.get_kafka_stats()
                print(f"{current_time} [汇总] 当前活跃无人机总数: {mode_instance.active_drone_count()} ；插入kafka成功{kafka_stats['success']}条，失败{kafka_stats['failed']}条")
    except KeyboardInterrupt:
        print("\n收到停止信号，正在停止程序...")
        mode_instance.stop()

    print('程序已退出')


def main():
    parser = argparse.ArgumentParser(description='UAV 飞行数据工具')
    parser.add_argument('--config', '-c', type=str, default='config.yaml', help='配置文件路径')
    parser.add_argument('--mode', '-m', type=str, choices=['scene', 'simulation', 'stress_test'], help='运行模式（覆盖配置文件）')
    args = parser.parse_args()

    print_banner()

    # 加载配置
    config_manager = ConfigManager(args.config)
    print(f"配置文件: {config_manager.config_path}")
    print(f"默认运行模式: {config_manager.get_mode()}")

    # 创建模式实例
    mode_instance = create_mode(config_manager, args.mode)

    # 运行
    run_mode(mode_instance)


if __name__ == '__main__':
    main()
