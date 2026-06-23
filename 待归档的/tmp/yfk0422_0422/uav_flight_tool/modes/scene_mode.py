#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
场景模式
加载自定义 JSON 轨迹文件并发送（原 uav_emitter 功能）
"""

import os
import time
import json
import yaml
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from modes.base_mode import BaseMode
from core.kafka_client import create_kafka_producer
from core.aircraft_name_generator import AircraftNameGenerator


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


class SceneLoader:
    """场景加载器"""

    def __init__(self, scenes_path: str):
        self.scenes_path = scenes_path

    def load_all_scenes(self) -> List[SceneConfig]:
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
        scenes = []
        for name in scene_names:
            scene_path = os.path.join(self.scenes_path, name)
            if os.path.exists(scene_path):
                scene = self._load_scene(name, scene_path)
                if scene:
                    scenes.append(scene)
            else:
                print(f"场景不存在: {name}")
        return scenes

    def _load_scene(self, name: str, path: str) -> Optional[SceneConfig]:
        config_path = os.path.join(path, "scene.yaml")
        if not os.path.exists(config_path):
            print(f"场景缺少配置文件: {name}")
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

    def load_uav_data(self, scene: SceneConfig, name_gen: AircraftNameGenerator = None) -> List[UAVData]:
        uav_data_list = []

        for uav_config in scene.uavs:
            if not uav_config.enabled:
                continue

            file_path = os.path.join(scene.path, uav_config.file)
            if not os.path.exists(file_path):
                print(f"  文件不存在: {uav_config.file}")
                continue

            try:
                records = self._load_json(file_path)
                if not records:
                    continue

                uid = records[0].get('uniqueProductIdentificationCode', 'UNKNOWN')
                # 如果启用了自定义名称生成，替换 UID
                if name_gen and name_gen.enabled:
                    new_uid = name_gen.generate()
                    for r in records:
                        r['uniqueProductIdentificationCode'] = new_uid
                        r['realNameRegistrationSign'] = new_uid
                    uid = new_uid

                uav_data = UAVData(
                    uid=uid,
                    records=records,
                    scene_name=scene.name,
                    enabled=uav_config.enabled,
                    delay_ms=uav_config.delay_ms
                )
                uav_data_list.append(uav_data)
                print(f"  {uid}: {len(records)} 条记录")

            except Exception as e:
                print(f"  加载失败 {uav_config.file}: {e}")

        return uav_data_list

    def _load_json(self, path: str) -> List[Dict]:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and 'records' in data:
            return data['records']
        return [data]


class SceneMode(BaseMode):
    """
    场景模式
    加载预定义的 JSON 轨迹文件，按配置发送到 Kafka
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.scene_config = config
        self.kafka = None
        self.topic = None
        self.emitter_config = {}
        self.uav_data_list: List[UAVData] = []
        self._thread = None
        self._first_emit_time = None
        self._first_record_time = None
        self.stats = {'sent': 0, 'start_time': None, 'end_time': None}
        self.name_gen = AircraftNameGenerator(config.get('aircraft_name', {}))

    def start(self):
        if self.running:
            print("发射器已在运行")
            return

        print("\n" + "=" * 60)
        print("场景模式启动")
        print("=" * 60)

        # 加载场景
        scenes_path = self.scene_config.get('scenes_path', 'scenes/')
        active_scenes = self.scene_config.get('active_scenes', [])

        if not os.path.isabs(scenes_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            scenes_path = os.path.join(base_dir, scenes_path)

        scene_loader = SceneLoader(scenes_path)
        if active_scenes:
            scenes = scene_loader.load_scenes(active_scenes)
        else:
            scenes = scene_loader.load_all_scenes()

        if not scenes:
            print("没有加载到任何场景")
            return

        print("\n场景列表:")
        for i, scene in enumerate(scenes, 1):
            enabled_uavs = sum(1 for u in scene.uavs if u.enabled)
            print(f"  {i}. {scene.name} ({enabled_uavs}/{len(scene.uavs)} 架启用)")

        # 加载 UAV 数据
        print("\n加载 UAV 数据...")
        data_loader = DataLoader()
        all_uav_data = []
        for scene in scenes:
            uav_data = data_loader.load_uav_data(scene, self.name_gen)
            all_uav_data.extend(uav_data)

        if not all_uav_data:
            print("\n没有加载到任何 UAV 数据")
            return

        self.uav_data_list = [u for u in all_uav_data if u.enabled]
        print(f"\n共加载 {len(self.uav_data_list)} 架 UAV")

        # 连接 Kafka
        kafka_cfg = self.config.get('kafka', {})
        self.topic = kafka_cfg.get('topic', 'uav_runtime_data')
        client_type = kafka_cfg.get('client_type', 'kafka-python')
        self.kafka = create_kafka_producer(kafka_cfg.get('url', 'localhost:9092'), client_type, verbose=True)

        self.emitter_config = self.scene_config.get('emitter', {})

        self.running = True
        self.stats['start_time'] = time.time()

        self._thread = threading.Thread(target=self._emit_loop)
        self._thread.daemon = True
        self._thread.start()

        print(f"\n发射器启动")
        print(f"   Kafka: {kafka_cfg.get('url')}")
        print(f"   Topic: {self.topic}")
        print(f"   间隔: {self.emitter_config.get('interval_ms', 1000)}ms")
        print(f"   时间戳模式: {self.emitter_config.get('timestamp_mode', 'replace')}")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self.kafka:
            self.kafka.close()
        self.stats['end_time'] = time.time()
        print("发射器已停止")
        print(f"总计发送: {self.stats['sent']} 条")

    def is_running(self) -> bool:
        return self.running

    def get_status(self) -> Dict[str, Any]:
        total = sum(u.total for u in self.uav_data_list)
        sent = sum(u.cursor for u in self.uav_data_list)
        return {
            'mode': 'scene',
            'running': self.running,
            'total_uavs': len(self.uav_data_list),
            'total_records': total,
            'sent_records': sent,
            'progress': f"{sent}/{total} ({sent/total*100:.1f}%)" if total > 0 else "N/A",
            'stats': self.stats,
        }

    def _process_timestamp(self, record: Dict, now_ms: int) -> int:
        """处理时间戳"""
        original_ts = record.get('timestamp', 0)
        now_ms = now_ms - 1000

        timestamp_mode = self.emitter_config.get('timestamp_mode', 'replace')

        if timestamp_mode == 'preserve':
            return original_ts
        elif timestamp_mode == 'align':
            if self._first_emit_time is None:
                self._first_emit_time = now_ms
                self._first_record_time = original_ts
                return now_ms
            offset = original_ts - self._first_record_time
            return self._first_emit_time + offset
        else:
            return now_ms

    def _emit_loop(self):
        interval_ms = self.emitter_config.get('interval_ms', 1000)
        loop = self.emitter_config.get('loop', False)

        while self.running:
            t0 = time.perf_counter()

            if self._is_all_completed():
                if loop:
                    self._reset_all()
                else:
                    print("\n所有 UAV 数据已耗尽")
                    self.running = False
                    break

            self._emit_once()

            elapsed = (time.perf_counter() - t0) * 1000
            sleep_ms = max(0, interval_ms - elapsed)
            time.sleep(sleep_ms / 1000)

    def _emit_once(self):
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
                print(f"发送 {uids} | {progress}")
            except Exception as e:
                print(f"发送失败: {e}")

    def _is_all_completed(self) -> bool:
        return all(not u.has_next() for u in self.uav_data_list)

    def _reset_all(self):
        for uav in self.uav_data_list:
            uav.reset()
        self._first_emit_time = None
        self._first_record_time = None
        print("循环模式: 重新开始")

    def _get_progress(self) -> str:
        total = sum(u.total for u in self.uav_data_list)
        sent = sum(u.cursor for u in self.uav_data_list)
        return f"进度: {sent}/{total} ({sent / total * 100:.1f}%)"
