#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UAV 数据发射器 - 场景化管理版
支持多场景、可选择 UAV、并发发送
"""

import sys
import os
import time
import json
import yaml
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# ============================================
# Kafka 客户端配置 - 修改这里指向你的 kafka_proc
# ============================================

# 方式1: 如果 kafka_proc 在系统路径中，直接导入
try:
    from kafka_proc import KafkaProducerClient

    print("✅ Kafka 客户端加载成功 (系统路径)")
except ImportError:
    # 方式2: 手动指定 kafka_proc 所在路径
    # 修改下面的路径为你项目的路径
    KAFKA_PROC_PATH = "/path/to/your/project"  # <-- 修改这里

    if os.path.exists(KAFKA_PROC_PATH):
        sys.path.insert(0, KAFKA_PROC_PATH)
        try:
            from kafka_proc import KafkaProducerClient

            print(f"✅ Kafka 客户端加载成功 ({KAFKA_PROC_PATH})")
        except ImportError:
            print(f"❌ 在 {KAFKA_PROC_PATH} 中未找到 kafka_proc")
            KafkaProducerClient = None
    else:
        print(f"⚠️  路径不存在: {KAFKA_PROC_PATH}")
        KafkaProducerClient = None

# 如果找不到 kafka_proc，使用模拟模式
if KafkaProducerClient is None:
    print("⚠️  警告: 未找到 kafka_proc 模块，使用模拟发送（不会发送到 Kafka）")
    print("   请修改 emitter.py 中的 KAFKA_PROC_PATH 指向你的项目路径")


    class KafkaProducerClient:
        """模拟 Kafka 生产者"""

        def __init__(self, url: str):
            self.url = url
            print(f"   [模拟模式] Kafka URL: {url}")

        def send_bulk(self, records: List[Dict[str, Any]], topic: str):
            print(f"   [模拟发送] {len(records)} 条到 {topic}")

        def close(self):
            pass


@dataclass
class UAVConfig:
    """UAV 配置"""
    file: str
    enabled: bool = True
    delay_ms: int = 0


@dataclass
class SceneConfig:
    """场景配置"""
    name: str
    description: str
    path: str
    uavs: List[UAVConfig]
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UAVData:
    """UAV 数据"""
    uid: str
    records: List[Dict[str, Any]]
    scene_name: str
    enabled: bool = True
    delay_ms: int = 0
    cursor: int = 0

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def progress(self) -> float:
        return self.cursor / self.total if self.total > 0 else 1.0

    def has_next(self) -> bool:
        return self.cursor < self.total

    def next(self) -> Optional[Dict[str, Any]]:
        if not self.has_next():
            return None
        record = self.records[self.cursor].copy()
        self.cursor += 1
        return record

    def reset(self):
        self.cursor = 0


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_yaml(config_path)

    def _load_yaml(self, path: str) -> Dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def get_scenes_path(self) -> str:
        return self.config.get('scenes_path', 'scenes/')

    def get_active_scenes(self) -> List[str]:
        return self.config.get('active_scenes', [])

    def get_kafka_config(self) -> Dict:
        return self.config.get('kafka', {'url': 'localhost:9092', 'topic': 'uav_runtime_data'})

    def get_emitter_config(self) -> Dict:
        return self.config.get('emitter', {
            'interval_ms': 1000,
            'timestamp_mode': 'replace',
            'loop': False
        })


class SceneLoader:
    """场景加载器"""

    def __init__(self, scenes_path: str):
        self.scenes_path = scenes_path

    def load_all_scenes(self) -> List[SceneConfig]:
        """加载所有场景"""
        scenes = []
        if not os.path.exists(self.scenes_path):
            return scenes

        for scene_name in sorted(os.listdir(self.scenes_path)):
            scene_path = os.path.join(self.scenes_path, scene_name)
            if os.path.isdir(scene_path):
                scene = self._load_scene(scene_name, scene_path)
                if scene:
                    scenes.append(scene)

        return scenes

    def load_scenes(self, scene_names: List[str]) -> List[SceneConfig]:
        """加载指定场景"""
        scenes = []
        for name in scene_names:
            scene_path = os.path.join(self.scenes_path, name)
            if os.path.exists(scene_path):
                scene = self._load_scene(name, scene_path)
                if scene:
                    scenes.append(scene)
            else:
                print(f"⚠️  场景不存在: {name}")
        return scenes

    def _load_scene(self, name: str, path: str) -> Optional[SceneConfig]:
        """加载单个场景"""
        config_path = os.path.join(path, "scene.yaml")
        if not os.path.exists(config_path):
            print(f"⚠️  场景缺少配置文件: {name}")
            return None

        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        uavs = []
        for uav_data in data.get('uavs', []):
            if isinstance(uav_data, str):
                uavs.append(UAVConfig(file=uav_data))
            else:
                uavs.append(UAVConfig(**uav_data))

        return SceneConfig(
            name=data.get('name', name),
            description=data.get('description', ''),
            path=path,
            uavs=uavs,
            params=data.get('params', {})
        )


class DataLoader:
    """数据加载器"""

    def load_uav_data(self, scene: SceneConfig) -> List[UAVData]:
        """加载场景中的 UAV 数据"""
        uav_data_list = []

        for uav_config in scene.uavs:
            if not uav_config.enabled:
                print(f"  ⏭️  跳过 UAV: {uav_config.file} (已禁用)")
                continue

            file_path = os.path.join(scene.path, uav_config.file)
            if not os.path.exists(file_path):
                print(f"  ⚠️  文件不存在: {uav_config.file}")
                continue

            try:
                records = self._load_json(file_path)
                if not records:
                    print(f"  ⚠️  空数据文件: {uav_config.file}")
                    continue

                uid = records[0].get('uniqueProductIdentificationCode', 'UNKNOWN')

                uav_data = UAVData(
                    uid=uid,
                    records=records,
                    scene_name=scene.name,
                    enabled=uav_config.enabled,
                    delay_ms=uav_config.delay_ms
                )
                uav_data_list.append(uav_data)
                print(f"  ✅ {uid}: {len(records)} 条记录")

            except Exception as e:
                print(f"  ❌ 加载失败 {uav_config.file}: {e}")

        return uav_data_list

    def _load_json(self, path: str) -> List[Dict]:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'records' in data:
            return data['records']
        return [data]


class Emitter:
    """UAV 数据发射器"""

    def __init__(self, config: Dict, uav_data_list: List[UAVData]):
        self.kafka_config = config
        self.kafka = KafkaProducerClient(config['url'])
        self.topic = config['topic']
        self.emitter_config = config.get('emitter', {})

        self.uav_data_list = [u for u in uav_data_list if u.enabled]
        self.interval_ms = self.emitter_config.get('interval_ms', 1000)
        self.timestamp_mode = self.emitter_config.get('timestamp_mode', 'replace')
        self.loop = self.emitter_config.get('loop', False)

        self.running = False
        self._thread = None
        self._first_emit_time = None
        self._first_record_time = None

        self.stats = {
            'sent': 0,
            'start_time': None,
            'end_time': None
        }

    def _process_timestamp(self, record: Dict, now_ms: int) -> int:
        """处理时间戳"""
        original_ts = record.get('timestamp', 0)

        # 减少 1000ms，使时间戳比当前时间慢 1 秒，可以慢，不能快
        now_ms = now_ms -1000

        if self.timestamp_mode == 'preserve':
            return original_ts
        elif self.timestamp_mode == 'align':
            if self._first_emit_time is None:
                self._first_emit_time = now_ms
                self._first_record_time = original_ts
                return now_ms
            offset = original_ts - self._first_record_time
            return self._first_emit_time + offset
        else:
            return now_ms

    def start(self):
        """开始发射"""
        if self.running:
            print("⚠️  发射器已在运行")
            return

        self.running = True
        self.stats['start_time'] = time.time()

        self._thread = threading.Thread(target=self._emit_loop)
        self._thread.daemon = True
        self._thread.start()

        print(f"\n🚀 发射器启动")
        print(f"   Kafka: {self.kafka_config['url']}")
        print(f"   Topic: {self.topic}")
        print(f"   间隔: {self.interval_ms}ms")
        print(f"   时间戳模式: {self.timestamp_mode}")

    def stop(self):
        """停止发射"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.kafka.close()
        self.stats['end_time'] = time.time()
        print("🛑 发射器已停止")

    def _emit_loop(self):
        """发射循环"""
        while self.running:
            t0 = time.perf_counter()

            if self._is_all_completed():
                if self.loop:
                    self._reset_all()
                else:
                    print("\n🏁 所有 UAV 数据已耗尽")
                    self.running = False
                    break

            self._emit_once()

            elapsed = (time.perf_counter() - t0) * 1000
            sleep_ms = max(0, self.interval_ms - elapsed)
            time.sleep(sleep_ms / 1000)

    def _emit_once(self):
        """单次发射"""
        records = []
        now_ms = int(time.time() * 1000)

        for uav in self.uav_data_list:
            if not uav.has_next():
                continue

            record = uav.next()
            record['timestamp'] = self._process_timestamp(record, now_ms)
            records.append(record)

        if records:
            try:
                self.kafka.send_bulk(records, self.topic)
                self.stats['sent'] += len(records)

                uids = [r.get('uniqueProductIdentificationCode') for r in records]
                progress = self._get_progress()
                print(f"📤 {uids} | {progress}")
            except Exception as e:
                print(f"❌ 发送失败: {e}")

    def _is_all_completed(self) -> bool:
        return all(not u.has_next() for u in self.uav_data_list)

    def _reset_all(self):
        for uav in self.uav_data_list:
            uav.reset()
        self._first_emit_time = None
        self._first_record_time = None
        print("🔄 循环模式: 重新开始")

    def _get_progress(self) -> str:
        total = sum(u.total for u in self.uav_data_list)
        sent = sum(u.cursor for u in self.uav_data_list)
        return f"进度: {sent}/{total} ({sent / total * 100:.1f}%)"


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║           🚁 UAV 数据发射器 - 场景化管理版                    ║
╚══════════════════════════════════════════════════════════════╝
""")


def print_scenes(scenes: List[SceneConfig]):
    print("\n📂 场景列表:")
    for i, scene in enumerate(scenes, 1):
        enabled_uavs = sum(1 for u in scene.uavs if u.enabled)
        total_uavs = len(scene.uavs)
        print(f"  {i}. {scene.name}")
        print(f"     描述: {scene.description}")
        print(f"     UAV: {enabled_uavs}/{total_uavs} 启用")
        for uav in scene.uavs:
            status = "✅" if uav.enabled else "⏭️"
            print(f"       {status} {uav.file}")


def main():
    print_banner()

    # 加载配置
    config_manager = ConfigManager()

    # 加载场景
    scenes_path = config_manager.get_scenes_path()
    scene_loader = SceneLoader(scenes_path)

    active_scenes = config_manager.get_active_scenes()
    if active_scenes:
        scenes = scene_loader.load_scenes(active_scenes)
    else:
        scenes = scene_loader.load_all_scenes()

    if not scenes:
        print("❌ 没有加载到任何场景")
        return

    print_scenes(scenes)

    # 加载 UAV 数据
    print("\n📥 加载 UAV 数据...")
    data_loader = DataLoader()
    all_uav_data = []

    for scene in scenes:
        print(f"\n  📍 {scene.name}:")
        uav_data = data_loader.load_uav_data(scene)
        all_uav_data.extend(uav_data)

    if not all_uav_data:
        print("\n❌ 没有加载到任何 UAV 数据")
        return

    print(f"\n✅ 共加载 {len(all_uav_data)} 架 UAV")

    # 创建发射器
    kafka_config = config_manager.get_kafka_config()
    emitter_config = config_manager.get_emitter_config()
    kafka_config['emitter'] = emitter_config

    emitter = Emitter(kafka_config, all_uav_data)

    # 启动发射
    emitter.start()

    try:
        while emitter.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
    finally:
        emitter.stop()

    print("\n✨ 程序结束")


if __name__ == '__main__':
    main()
