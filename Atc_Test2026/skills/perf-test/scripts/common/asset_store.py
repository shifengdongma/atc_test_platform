"""资产存储管理模块"""

import json
from pathlib import Path
from typing import Any, Dict, List


class AssetStore:
    """资产存储管理类"""

    def __init__(self, base_path: Path):
        self.base_path = base_path

    def load_json(self, filename: str) -> Any:
        """加载 JSON 文件"""
        file_path = self.base_path / filename
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_json(self, filename: str, data: Any) -> None:
        """保存 JSON 文件"""
        file_path = self.base_path / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_jsonl(self, filename: str) -> List[Dict]:
        """加载 JSONL 文件"""
        file_path = self.base_path / filename
        results = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        return results

    def append_jsonl(self, filename: str, data: Dict) -> None:
        """追加数据到 JSONL 文件"""
        file_path = self.base_path / filename
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
