"""
TAPD 缺陷提交通用脚本：
- 创建 bug
- 可选上传附件
- 输出统一 JSON 结果
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_TAPD_BASE_URL = "https://www.tapd.cn"
DEFAULT_CONFIG_FILE = Path(__file__).resolve().parents[5] / ".tapd" / "project_config.json"
DEFAULT_STATE_FILE = Path(__file__).resolve().parents[5] / ".tapd" / "submit_state.json"


def load_tapd_client():
    script_path = (
        Path(__file__).resolve().parents[2] / "tapd-plus" / "scripts" / "tapd_client_stdlib.py"
    )
    if not script_path.is_file():
        raise FileNotFoundError(f"未找到 tapd 客户端脚本: {script_path}")

    spec = importlib.util.spec_from_file_location("tapd_client_stdlib", script_path)
    if not spec or not spec.loader:
        raise RuntimeError("加载 tapd_client_stdlib 失败")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建 TAPD 缺陷并可选上传附件")
    parser.add_argument("--payload-file", help="UTF-8 JSON 文件路径，推荐")
    parser.add_argument("--config-file", help="项目本地配置文件路径（可选）")
    parser.add_argument("--workspace-id", dest="workspace_id")
    parser.add_argument("--title")
    parser.add_argument("--description")
    parser.add_argument("--priority")
    parser.add_argument("--severity")
    parser.add_argument("--current-owner", dest="current_owner")
    parser.add_argument("--reporter")
    parser.add_argument("--module", help="缺陷所属模块，用于自动匹配负责人")
    parser.add_argument("--version", help="所属版本，可覆盖配置默认值")
    parser.add_argument("--file", dest="file_path", help="附件路径（可选）")
    parser.add_argument(
        "--resume-only",
        action="store_true",
        help="仅从本地状态恢复并继续附件上传，不创建新 bug",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅校验并输出最终 payload，不实际提交")
    parser.add_argument(
        "--show-raw-response",
        action="store_true",
        help="输出 TAPD 原始响应（调试用）",
    )
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> Dict[str, Any]:
    config_path = Path(args.config_file).resolve() if args.config_file else DEFAULT_CONFIG_FILE
    if not config_path.is_file():
        return {}

    with config_path.open("r", encoding="utf-8-sig") as f:
        config = json.load(f)

    if not isinstance(config, dict):
        raise ValueError("配置文件必须是 JSON 对象")
    return config


def normalize_description(summary: str, description: str) -> str:
    if not summary:
        return description
    return f"问题概述：{summary}\n\n{description}"

def format_description_for_tapd(description: str) -> str:
    """
    TAPD 页面在部分场景下对纯 \\n 展示不稳定，统一转换为 <br/> 提高换行可读性。
    """
    normalized = description.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "<br/>".join(lines)


def pick_value(payload: Dict[str, Any], config: Dict[str, Any], key: str) -> Optional[Any]:
    if str(payload.get(key, "")).strip():
        return payload.get(key)
    defaults = config.get("defaults", {})
    if isinstance(defaults, dict) and str(defaults.get(key, "")).strip():
        return defaults.get(key)
    if str(config.get(key, "")).strip():
        return config.get(key)
    return None


def load_payload(args: argparse.Namespace, config: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if args.payload_file:
        payload_path = Path(args.payload_file).resolve()
        with payload_path.open("r", encoding="utf-8-sig") as f:
            from_file = json.load(f)
        if not isinstance(from_file, dict):
            raise ValueError("payload 文件必须是 JSON 对象")
        payload.update(from_file)

    cli_values = {
        "workspace_id": args.workspace_id,
        "title": args.title,
        "description": args.description,
        "priority": args.priority,
        "severity": args.severity,
        "current_owner": args.current_owner,
        "reporter": args.reporter,
        "module": args.module,
        "version": args.version,
    }
    for k, v in cli_values.items():
        if v is not None:
            payload[k] = v

    # 配置兜底：全局默认字段
    for field in ["workspace_id", "reporter", "version"]:
        value = pick_value(payload, config, field)
        if value is not None:
            payload[field] = value

    # 模块负责人自动匹配
    if not str(payload.get("current_owner", "")).strip():
        module = str(payload.get("module", "")).strip()
        if module:
            module_owner_map = config.get("module_owner_map", {})
            if isinstance(module_owner_map, dict) and str(module_owner_map.get(module, "")).strip():
                payload["current_owner"] = module_owner_map[module]
            elif config:
                raise ValueError(f"模块 '{module}' 未在 module_owner_map 中配置负责人")

    # 模块扩展字段
    module = str(payload.get("module", "")).strip()
    if module:
        module_field_map = config.get("module_field_map", {})
        if isinstance(module_field_map, dict):
            module_extra = module_field_map.get(module, {})
            if isinstance(module_extra, dict):
                for k, v in module_extra.items():
                    if k not in payload or payload[k] in (None, ""):
                        payload[k] = v

    summary = str(payload.pop("summary", "")).strip()
    description = str(payload.get("description", "")).strip()
    if summary and description:
        payload["description"] = normalize_description(summary, description)
    elif description:
        payload["description"] = description

    if str(payload.get("description", "")).strip():
        payload["description"] = format_description_for_tapd(str(payload["description"]))

    required = [
        "workspace_id",
        "title",
        "description",
        "priority",
        "severity",
        "current_owner",
        "reporter",
    ]
    missing = [k for k in required if not str(payload.get(k, "")).strip()]
    if missing:
        raise ValueError(f"缺少必填字段: {', '.join(missing)}")

    payload["workspace_id"] = str(payload["workspace_id"])
    return payload


def extract_bug_id(response: Dict[str, Any]) -> str:
    bug = response.get("data", {}).get("Bug", {})
    bug_id = bug.get("id")
    if not bug_id:
        raise RuntimeError(f"创建缺陷返回异常: {json.dumps(response, ensure_ascii=False)}")
    return str(bug_id)


def build_bug_url(workspace_id: str, bug_id: str) -> str:
    base_url = os.environ.get("TAPD_BASE_URL", DEFAULT_TAPD_BASE_URL).rstrip("/")
    return f"{base_url}/{workspace_id}/bugtrace/bugs/view/{bug_id}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def calc_idempotency_key(payload: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(payload.get("workspace_id", "")).strip(),
            str(payload.get("title", "")).strip(),
            str(payload.get("description", "")).strip(),
            str(payload.get("reporter", "")).strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calc_file_fingerprint(file_path: Optional[str]) -> Optional[str]:
    if not file_path:
        return None
    p = Path(file_path)
    if not p.is_file():
        return None
    stat = p.stat()
    return f"{p.name}:{stat.st_size}:{stat.st_mtime_ns}"


def load_submit_state(state_path: Path) -> Dict[str, Any]:
    if not state_path.is_file():
        return {"records": {}}
    with state_path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {"records": {}}
    records = data.get("records")
    if not isinstance(records, dict):
        data["records"] = {}
    return data


def save_submit_state(state_path: Path, state: Dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_state_record(
    state: Dict[str, Any],
    idempotency_key: str,
    payload: Dict[str, Any],
    bug_id: str,
    attachment_uploaded: bool,
    attachment_file_fingerprint: Optional[str],
    attachment_id: Optional[str] = None,
    attachment_filename: Optional[str] = None,
) -> Dict[str, Any]:
    records = state.setdefault("records", {})
    if not isinstance(records, dict):
        records = {}
        state["records"] = records
    record = {
        "idempotency_key": idempotency_key,
        "workspace_id": str(payload.get("workspace_id", "")),
        "title": str(payload.get("title", "")),
        "reporter": str(payload.get("reporter", "")),
        "bug_id": str(bug_id),
        "attachment_uploaded": bool(attachment_uploaded),
        "attachment_file_fingerprint": attachment_file_fingerprint,
        "attachment_id": attachment_id,
        "attachment_filename": attachment_filename,
        "updated_at": utc_now_iso(),
    }
    records[idempotency_key] = record
    return record


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    config = load_config(args)
    payload = load_payload(args, config)
    state_path = DEFAULT_STATE_FILE
    state = load_submit_state(state_path)
    idempotency_key = calc_idempotency_key(payload)
    current_fingerprint = calc_file_fingerprint(args.file_path)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "payload": payload,
                    "config_file": str((Path(args.config_file).resolve() if args.config_file else DEFAULT_CONFIG_FILE)),
                    "file_path": args.file_path or None,
                    "state_file": str(state_path),
                    "idempotency_key": idempotency_key,
                },
                ensure_ascii=False,
            )
        )
        return

    client = load_tapd_client()
    record = state.get("records", {}).get(idempotency_key, {})
    if not isinstance(record, dict):
        record = {}
    bug_id = str(record.get("bug_id", "")).strip()
    create_resp: Optional[Dict[str, Any]] = None
    recovered = False
    idempotent_skip = False
    if bug_id:
        recovered = True
    if args.resume_only and not bug_id:
        raise RuntimeError("未找到可恢复状态：请先执行一次创建，或去掉 --resume-only")
    if not bug_id:
        create_resp = client.request("POST", "bugs", data=payload)
        bug_id = extract_bug_id(create_resp)
        upsert_state_record(
            state=state,
            idempotency_key=idempotency_key,
            payload=payload,
            bug_id=bug_id,
            attachment_uploaded=False,
            attachment_file_fingerprint=current_fingerprint,
        )
        save_submit_state(state_path, state)

    attachment_resp: Optional[Dict[str, Any]] = None
    attachment_info: Dict[str, Any] = {}
    if args.file_path:
        uploaded = bool(record.get("attachment_uploaded"))
        old_fingerprint = record.get("attachment_file_fingerprint")
        if uploaded and old_fingerprint and old_fingerprint == current_fingerprint:
            idempotent_skip = True
            attachment_info = {
                "attachment_id": record.get("attachment_id"),
                "attachment_filename": record.get("attachment_filename"),
            }
        else:
            try:
                attachment_resp = client.upload_attachment(
                    workspace_id=int(payload["workspace_id"]),
                    entry_id=bug_id,
                    entry_type="bug",
                    file_path=args.file_path,
                )
            except Exception as exc:
                upsert_state_record(
                    state=state,
                    idempotency_key=idempotency_key,
                    payload=payload,
                    bug_id=bug_id,
                    attachment_uploaded=False,
                    attachment_file_fingerprint=current_fingerprint,
                    attachment_id=record.get("attachment_id"),
                    attachment_filename=record.get("attachment_filename"),
                )
                save_submit_state(state_path, state)
                error_result = {
                    "error": "attachment_upload_failed",
                    "message": str(exc),
                    "bug_id": bug_id,
                    "bug_url": build_bug_url(payload["workspace_id"], bug_id),
                    "next_action": "retry_attachment_only",
                    "idempotency_key": idempotency_key,
                }
                if args.show_raw_response:
                    error_result["raw_response"] = {"create_bug": create_resp, "upload_attachment": None}
                print(json.dumps(error_result, ensure_ascii=False), file=sys.stderr)
                raise SystemExit(2)

            attachment = attachment_resp.get("data", {}).get("Attachment", {})
            attachment_info = {
                "attachment_id": attachment.get("id"),
                "attachment_filename": attachment.get("filename"),
            }
            upsert_state_record(
                state=state,
                idempotency_key=idempotency_key,
                payload=payload,
                bug_id=bug_id,
                attachment_uploaded=True,
                attachment_file_fingerprint=current_fingerprint,
                attachment_id=attachment_info.get("attachment_id"),
                attachment_filename=attachment_info.get("attachment_filename"),
            )
            save_submit_state(state_path, state)
    else:
        upsert_state_record(
            state=state,
            idempotency_key=idempotency_key,
            payload=payload,
            bug_id=bug_id,
            attachment_uploaded=bool(record.get("attachment_uploaded", False)),
            attachment_file_fingerprint=record.get("attachment_file_fingerprint"),
            attachment_id=record.get("attachment_id"),
            attachment_filename=record.get("attachment_filename"),
        )
        save_submit_state(state_path, state)

    result: Dict[str, Any] = {
        "bug_id": bug_id,
        "bug_url": build_bug_url(payload["workspace_id"], bug_id),
        "recovered": recovered,
        "idempotent_skip": idempotent_skip,
        "idempotency_key": idempotency_key,
        **attachment_info,
    }

    if args.show_raw_response:
        result["raw_response"] = {
            "create_bug": create_resp,
            "upload_attachment": attachment_resp,
        }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
