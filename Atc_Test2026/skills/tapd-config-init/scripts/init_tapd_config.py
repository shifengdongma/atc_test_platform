"""
初始化并升级 TAPD 本地配置：
- 不存在则创建
- 存在则递归补齐缺失字段
- 保留已有值，不做覆盖
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


DEFAULT_TEMPLATE = Path(__file__).resolve().parents[5] / ".tapd" / "project_config.template.json"
DEFAULT_TARGET = Path(__file__).resolve().parents[5] / ".tapd" / "project_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化/升级 TAPD 项目配置")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="模板 JSON 路径")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="目标配置 JSON 路径")
    return parser.parse_args()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return obj


def merge_missing_keys(
    target: Dict[str, Any], template: Dict[str, Any], prefix: str = ""
) -> Tuple[Dict[str, Any], List[str]]:
    added: List[str] = []
    for key, tpl_val in template.items():
        key_path = f"{prefix}.{key}" if prefix else key
        if key not in target:
            target[key] = tpl_val
            added.append(key_path)
            continue

        cur_val = target[key]
        if isinstance(cur_val, dict) and isinstance(tpl_val, dict):
            _, nested_added = merge_missing_keys(cur_val, tpl_val, key_path)
            added.extend(nested_added)
    return target, added


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    args = parse_args()
    template_path = Path(args.template).resolve()
    target_path = Path(args.target).resolve()

    if not template_path.is_file():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")

    template_obj = read_json(template_path)

    if not target_path.exists():
        write_json(target_path, template_obj)
        result = {
            "status": "created",
            "template_path": str(template_path),
            "target_path": str(target_path),
            "added_keys": sorted(template_obj.keys()),
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    target_obj = read_json(target_path)
    merged_obj, added = merge_missing_keys(target_obj, template_obj)

    if added:
        write_json(target_path, merged_obj)
        status = "merged"
    else:
        status = "skipped"

    result = {
        "status": status,
        "template_path": str(template_path),
        "target_path": str(target_path),
        "added_keys": added,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

