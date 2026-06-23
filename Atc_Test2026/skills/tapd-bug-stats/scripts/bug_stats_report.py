"""
TAPD Bug 统计报表脚本（仅标准库）
- 拉取全量 bugs（支持分页）
- 按模块/负责人维度聚合
- 默认落盘 Excel 至 .tapd/；根因拉数阶段仅输出 JSON
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape


DEFAULT_PAGE_SIZE = 200
ORGANIZATION_CATEGORY = "organization"
SEVERE_SET = {"fatal", "serious"}
DONE_STATUS_SET = {"closed", "resolved"}
BUG_FIELDS_BASE = (
    "id,title,status,severity,priority_label,module,current_owner,created"
)
BUG_FIELDS_WITH_DESC = f"{BUG_FIELDS_BASE},description"


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
    parser = argparse.ArgumentParser(description="TAPD Bug 统计/分析（默认 Excel 报告）")
    parser.add_argument("--workspace-id", help="工作空间 ID（TAPD workspace_id）")
    parser.add_argument(
        "--project-name",
        dest="workspace_name",
        help="工作空间名称（从用户参与项目中解析为 workspace_id）",
    )
    parser.add_argument("--workspace-name", dest="workspace_name", help="同 --project-name")
    parser.add_argument(
        "--nick",
        default=os.environ.get("CURRENT_USER_NICK", ""),
        help="TAPD 用户昵称；按名称解析工作空间时使用，默认 CURRENT_USER_NICK",
    )
    parser.add_argument("--start-date", help="起始日期，YYYY-MM-DD（按本地过滤）")
    parser.add_argument("--end-date", help="结束日期，YYYY-MM-DD（按本地过滤）")
    parser.add_argument("--iteration-id", help="迭代 ID（可选）")
    parser.add_argument("--iteration-name", help="迭代名（可选；会解析为 iteration_id）")
    parser.add_argument("--version", help="版本名（可选）")
    parser.add_argument(
        "--group-by",
        choices=["module", "owner", "module_owner"],
        default="module_owner",
        help="报表分组维度",
    )
    parser.add_argument("--output-xlsx", help="Excel 报告路径（默认自动生成至 .tapd/）")
    parser.add_argument(
        "--output-dir",
        help="报告默认输出目录（未指定路径时），默认 <工作区>/.tapd",
    )
    parser.add_argument(
        "--open-only",
        action="store_true",
        help="仅未解决：排除 status 为 closed、resolved",
    )
    parser.add_argument(
        "--exclude-status",
        help="排除指定状态，逗号分隔，如 closed（与 --open-only 互斥）",
    )
    parser.add_argument(
        "--include-description",
        action="store_true",
        help="拉取含 description，JSON 输出 bugs_for_classification（根因拉数，不写 xlsx）",
    )
    parser.add_argument(
        "--root-cause-categories",
        help="根因类别 JSON：{bug_id: 类别} 或 [{id, category}]；生成根因分析 xlsx（两工作表）",
    )
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="分页大小，默认 200")
    parser.add_argument("--max-pages", type=int, default=200, help="最大分页数，防止意外无限拉取")
    parser.add_argument(
        "--source-json",
        help="可选：从本地 JSON 文件读取 bugs 数据进行离线验证（跳过 TAPD 请求）",
    )
    args = parser.parse_args()
    if args.open_only and str(args.exclude_status or "").strip():
        parser.error("--open-only 与 --exclude-status 不能同时使用")
    return args


def default_tapd_output_dir() -> Path:
    return Path(__file__).resolve().parents[5] / ".tapd"


def workspace_items_from_response(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = resp.get("data", [])
    items: List[Dict[str, Any]] = []
    if not isinstance(data, list):
        return items
    for row in data:
        if not isinstance(row, dict):
            continue
        ws = row.get("Workspace", row)
        if isinstance(ws, dict):
            items.append(ws)
    return items


def resolve_workspace_id_from_name(client: Any, name: str, nick: str) -> Tuple[str, str]:
    """通过 workspaces/user_participant_projects 将工作空间名称解析为 ID。"""
    name_norm = name.strip()
    if not name_norm:
        raise ValueError("工作空间名称不能为空")
    nick_norm = (nick or "").strip()
    if not nick_norm:
        raise ValueError(
            "按名称解析工作空间需要 nick：请传 --nick 或设置环境变量 CURRENT_USER_NICK"
        )
    resp = client.request(
        "GET",
        "workspaces/user_participant_projects",
        params={"nick": nick_norm},
    )
    rows = workspace_items_from_response(resp)
    candidates: List[Dict[str, str]] = []
    for ws in rows:
        category = str(ws.get("category", "")).strip().lower()
        if category == ORGANIZATION_CATEGORY:
            continue
        wid = str(ws.get("id", "")).strip()
        wname = str(ws.get("name", "")).strip()
        if not wid or not wname:
            continue
        candidates.append({"id": wid, "name": wname})

    exact: Optional[Dict[str, str]] = None
    fuzzy_matches: List[Dict[str, str]] = []
    for c in candidates:
        if c["name"] == name_norm:
            exact = c
            break
        if name_norm in c["name"]:
            fuzzy_matches.append(c)

    if exact:
        return exact["id"], exact["name"]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]["id"], fuzzy_matches[0]["name"]
    if len(fuzzy_matches) > 1:
        listing = ", ".join(f'{c["id"]}={c["name"]}' for c in fuzzy_matches[:20])
        raise ValueError(
            f"工作空间名称「{name_norm}」匹配到多个项目，请改用 --workspace-id。候选：{listing}"
        )
    sample = ", ".join(f'{c["id"]}={c["name"]}' for c in candidates[:15])
    hint = f" 当前参与项目示例：{sample}" if sample else ""
    raise ValueError(f"未找到工作空间名称「{name_norm}」。{hint}".strip())


def resolve_workspace_scope(
    client: Optional[Any], args: argparse.Namespace
) -> Tuple[str, Dict[str, Any]]:
    """
    解析统计范围：--workspace-id 优先于 --project-name / --workspace-name。
    返回 (workspace_id, meta)，meta 含 resolved_from、workspace_name 等。
    """
    wid = str(args.workspace_id or "").strip()
    pname = str(getattr(args, "workspace_name", None) or "").strip()

    if wid and pname:
        raise ValueError("请只指定 --workspace-id 或 --project-name/--workspace-name 之一")
    if wid:
        return wid, {"resolved_from": "id", "workspace_name": ""}

    if pname:
        if client is None:
            raise ValueError("按名称解析工作空间需要 TAPD 客户端，请勿与仅离线场景混用")
        resolved_id, resolved_name = resolve_workspace_id_from_name(client, pname, args.nick)
        return resolved_id, {
            "resolved_from": "name",
            "workspace_name": resolved_name,
            "requested_name": pname,
        }

    raise ValueError("请提供 --workspace-id 或 --project-name（工作空间名称）")


def normalize_date_str(s: str) -> Optional[datetime]:
    text = (s or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def bug_items_from_response(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = resp.get("data", [])
    items: List[Dict[str, Any]] = []
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                bug = row.get("Bug", row)
                if isinstance(bug, dict):
                    items.append(bug)
    elif isinstance(data, dict):
        bug = data.get("Bug")
        if isinstance(bug, dict):
            items.append(bug)
    return items


def read_source_json(path: str) -> List[Dict[str, Any]]:
    p = Path(path).resolve()
    with p.open("r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        if isinstance(obj.get("bugs"), list):
            return [x for x in obj["bugs"] if isinstance(x, dict)]
        return bug_items_from_response(obj)
    raise ValueError("source-json 必须是数组或 TAPD 响应对象")


def resolve_iteration_id(
    client: Any, workspace_id: str, iteration_id: Optional[str], iteration_name: Optional[str]
) -> Optional[str]:
    if str(iteration_id or "").strip():
        return str(iteration_id).strip()
    if not str(iteration_name or "").strip():
        return None
    resp = client.request(
        "GET",
        "iterations",
        params={"workspace_id": workspace_id, "name": iteration_name, "limit": 200, "page": 1},
    )
    rows = resp.get("data", [])
    if not isinstance(rows, list):
        return None
    exact = None
    fuzzy = None
    name_norm = iteration_name.strip()
    for row in rows:
        it = row.get("Iteration", row) if isinstance(row, dict) else {}
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id", "")).strip()
        iname = str(it.get("name", "")).strip()
        if not iid:
            continue
        if iname == name_norm:
            exact = iid
            break
        if name_norm and name_norm in iname and fuzzy is None:
            fuzzy = iid
    return exact or fuzzy


def fetch_workspace_display_name(client: Any, workspace_id: str) -> str:
    try:
        resp = client.request(
            "GET",
            "workspaces/get_workspace_info",
            params={"workspace_id": workspace_id},
        )
        data = resp.get("data", {})
        if isinstance(data, dict):
            w = data.get("Workspace", data)
            if isinstance(w, dict):
                return str(w.get("name", "")).strip()
    except Exception:
        pass
    return ""


def parse_exclude_statuses(raw: Optional[str]) -> set:
    return {x.strip().lower() for x in str(raw or "").split(",") if x.strip()}


def match_status_local(bug: Dict[str, Any], args: argparse.Namespace) -> bool:
    status = str(bug.get("status", "")).strip().lower()
    if args.open_only:
        return status not in DONE_STATUS_SET
    excluded = parse_exclude_statuses(args.exclude_status)
    if excluded:
        return status not in excluded
    return True


def _period_label(start_date: str, end_date: str) -> str:
    s = (start_date or "").strip()
    e = (end_date or "").strip()
    if s and e:
        return f"{s}～{e}"
    if s:
        return f"{s} 起"
    if e:
        return f"至 {e}"
    return "全量"


def build_filter_label(args: argparse.Namespace) -> str:
    parts: List[str] = []
    if args.open_only:
        parts.append("未解决（排除 closed/resolved）")
    elif str(args.exclude_status or "").strip():
        parts.append(f"排除状态：{args.exclude_status.strip()}")
    period = _period_label(args.start_date or "", args.end_date or "")
    if period != "全量":
        parts.append(period)
    if str(args.iteration_name or "").strip():
        parts.append(f"迭代 {args.iteration_name.strip()}")
    elif str(args.iteration_id or "").strip():
        parts.append(f"迭代 {args.iteration_id.strip()}")
    if str(args.version or "").strip():
        parts.append(f"版本 {args.version.strip()}")
    return "｜".join(parts) if parts else "全量"


def output_slug(args: argparse.Namespace) -> str:
    if args.include_description or str(getattr(args, "root_cause_categories", None) or "").strip():
        return "rootcause"
    if args.open_only:
        return "open"
    if (args.start_date or "").strip() or (args.end_date or "").strip():
        return "range"
    return "stats"


def default_output_xlsx_path(args: argparse.Namespace, workspace_id: str) -> Path:
    out_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else default_tapd_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if str(getattr(args, "root_cause_categories", None) or "").strip():
        return out_dir / f"bug_root_cause_analysis_{workspace_id}_{ts}.xlsx"
    return out_dir / f"tapd_bugs_{output_slug(args)}_{workspace_id}_{ts}.xlsx"


def _strip_html_simple(text: str, limit: int = 400) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        return t[: limit - 3] + "..."
    return t


UNCATEGORIZED_LABEL = "未分类"


def load_root_cause_categories(path: str) -> Dict[str, str]:
    """读取根因类别映射：支持 {id: category} 或 [{id, category}, ...]。"""
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k).strip()] = str(v or "").strip() or UNCATEGORIZED_LABEL
        return out
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            bid = str(item.get("id", item.get("bug_id", ""))).strip()
            if not bid:
                continue
            cat = str(item.get("category", item.get("root_cause", ""))).strip()
            out[bid] = cat or UNCATEGORIZED_LABEL
        return out
    raise ValueError("根因类别 JSON 须为对象或数组")


def build_assignments_from_bugs(
    bugs: Sequence[Dict[str, Any]], category_by_id: Dict[str, str]
) -> List[Dict[str, str]]:
    assignments: List[Dict[str, str]] = []
    for b in bugs:
        bid = str(b.get("id", "")).strip()
        title = str(b.get("title", "")).strip()
        category = category_by_id.get(bid, "").strip() or UNCATEGORIZED_LABEL
        assignments.append({"id": bid, "title": title, "category": category})
    return assignments


def _root_cause_category_counts(assignments: Sequence[Dict[str, str]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for a in assignments:
        cat = (a.get("category") or "").strip() or UNCATEGORIZED_LABEL
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def root_cause_summary_rows(assignments: Sequence[Dict[str, str]]) -> List[List[Any]]:
    counts = _root_cause_category_counts(assignments)
    total = len(assignments)
    out: List[List[Any]] = [["根因类别", "条数", "占比"]]
    for cat in sorted(counts.keys(), key=lambda c: (-counts[c], c)):
        n = counts[cat]
        pct = round((n / total * 100.0) if total else 0.0, 1)
        out.append([cat, n, f"{pct}%"])
    return out


def root_cause_list_rows(assignments: Sequence[Dict[str, str]]) -> List[List[Any]]:
    sorted_items = sorted(
        assignments,
        key=lambda a: (
            (a.get("category") or "").strip() or UNCATEGORIZED_LABEL,
            str(a.get("id", "")),
        ),
    )
    out: List[List[Any]] = [["根因类别", "Bug ID", "标题"]]
    for a in sorted_items:
        out.append(
            [
                (a.get("category") or "").strip() or UNCATEGORIZED_LABEL,
                a.get("id", ""),
                a.get("title", ""),
            ]
        )
    return out


def build_bugs_for_classification(
    bugs: Sequence[Dict[str, Any]], preview_limit: int = 600
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for b in bugs:
        out.append(
            {
                "id": str(b.get("id", "")).strip(),
                "title": str(b.get("title", "")).strip(),
                "description_preview": _strip_html_simple(
                    str(b.get("description", "")), limit=preview_limit
                ),
            }
        )
    return out


def count_severe_open(bugs: Iterable[Dict[str, Any]]) -> int:
    n = 0
    for bug in bugs:
        status = str(bug.get("status", "")).strip().lower()
        severity = str(bug.get("severity", "")).strip().lower()
        if status not in DONE_STATUS_SET and severity in SEVERE_SET:
            n += 1
    return n


def fetch_all_bugs(
    client: Any,
    workspace_id: str,
    page_size: int,
    max_pages: int,
    iteration_id: Optional[str],
    version: Optional[str],
    include_description: bool = False,
) -> List[Dict[str, Any]]:
    all_items: List[Dict[str, Any]] = []
    base_params: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "limit": page_size,
        "fields": BUG_FIELDS_WITH_DESC if include_description else BUG_FIELDS_BASE,
    }
    if iteration_id:
        base_params["iteration_id"] = iteration_id
    if version:
        base_params["version"] = version
    for page in range(1, max_pages + 1):
        params = dict(base_params)
        params["page"] = page
        resp = client.request("GET", "bugs", params=params)
        rows = bug_items_from_response(resp)
        if not rows:
            break
        all_items.extend(rows)
        if len(rows) < page_size:
            break
    return all_items


def pick_first_text(d: Dict[str, Any], keys: Sequence[str], fallback: str = "未分类") -> str:
    for k in keys:
        val = d.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
    return fallback


def get_bug_time(bug: Dict[str, Any]) -> Optional[datetime]:
    for key in ("created", "created_at", "created_time", "create_time", "modified"):
        dt = normalize_date_str(str(bug.get(key, "")).strip())
        if dt:
            return dt
    return None


def in_date_range(bug: Dict[str, Any], start: Optional[datetime], end: Optional[datetime]) -> bool:
    if not start and not end:
        return True
    dt = get_bug_time(bug)
    if dt is None:
        return False
    if start and dt < start:
        return False
    if end and dt > end.replace(hour=23, minute=59, second=59):
        return False
    return True


def match_version_local(bug: Dict[str, Any], version: Optional[str]) -> bool:
    if not str(version or "").strip():
        return True
    target = version.strip()
    vals = [
        str(bug.get("version", "")).strip(),
        str(bug.get("fix_version", "")).strip(),
        str(bug.get("release", "")).strip(),
    ]
    return any(target == v for v in vals if v)


def match_iteration_local(
    bug: Dict[str, Any], iteration_id: Optional[str], iteration_name: Optional[str]
) -> bool:
    if not str(iteration_id or "").strip() and not str(iteration_name or "").strip():
        return True
    if str(iteration_id or "").strip():
        target_id = str(iteration_id).strip()
        bug_iter_id = str(
            bug.get("iteration_id", bug.get("iteration", bug.get("iterationId", "")))
        ).strip()
        if bug_iter_id:
            return bug_iter_id == target_id
    if str(iteration_name or "").strip():
        target_name = str(iteration_name).strip()
        bug_iter_name = str(
            bug.get("iteration_name", bug.get("iterationName", bug.get("iteration", "")))
        ).strip()
        if bug_iter_name:
            return bug_iter_name == target_name
    return False


def group_key(bug: Dict[str, Any], group_by: str) -> Tuple[str, str]:
    module = pick_first_text(
        bug,
        ["module", "module_name", "component", "custom_field_module"],
        fallback="未分类模块",
    )
    owner = pick_first_text(bug, ["current_owner", "owner"], fallback="未分配负责人")
    if group_by == "module":
        return module, "ALL"
    if group_by == "owner":
        return "ALL", owner
    return module, owner


def aggregate_rows(bugs: Iterable[Dict[str, Any]], group_by: str) -> List[Dict[str, Any]]:
    agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for bug in bugs:
        key = group_key(bug, group_by)
        row = agg.setdefault(
            key,
            {
                "module": key[0],
                "owner": key[1],
                "total": 0,
                "fixed": 0,
                "leftover": 0,
                "severe_leftover": 0,
            },
        )
        row["total"] += 1
        status = str(bug.get("status", "")).strip().lower()
        severity = str(bug.get("severity", "")).strip().lower()
        is_done = status in DONE_STATUS_SET
        if is_done:
            row["fixed"] += 1
        else:
            row["leftover"] += 1
            if severity in SEVERE_SET:
                row["severe_leftover"] += 1
    rows = list(agg.values())
    rows.sort(key=lambda r: (-r["total"], -r["severe_leftover"], r["module"], r["owner"]))
    return rows


def build_markdown_table(rows: Sequence[Dict[str, Any]]) -> str:
    header = "| 模块 | 负责人 | 总数 | 已修复 | 遗留 | 严重Bug数 |\n|---|---:|---:|---:|---:|---:|"
    lines = [header]
    for r in rows:
        lines.append(
            f"| {r['module']} | {r['owner']} | {r['total']} | {r['fixed']} | {r['leftover']} | {r['severe_leftover']} |"
        )
    return "\n".join(lines)


def compute_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = sum(r["total"] for r in rows)
    fixed = sum(r["fixed"] for r in rows)
    leftover = sum(r["leftover"] for r in rows)
    severe_leftover = sum(r["severe_leftover"] for r in rows)
    top_module = max(rows, key=lambda r: r["total"]) if rows else None
    top_owner = max(rows, key=lambda r: r["total"]) if rows else None
    fix_rate = (fixed / total * 100.0) if total else 0.0
    return {
        "total": total,
        "fixed": fixed,
        "leftover": leftover,
        "severe_leftover": severe_leftover,
        "fix_rate": round(fix_rate, 2),
        "top_module": top_module["module"] if top_module else "",
        "top_module_count": top_module["total"] if top_module else 0,
        "top_owner": top_owner["owner"] if top_owner else "",
        "top_owner_count": top_owner["total"] if top_owner else 0,
    }


def build_insight_text(summary: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"- 整体 Bug 总量 {summary['total']}，已修复 {summary['fixed']}，遗留 {summary['leftover']}，修复率 {summary['fix_rate']}%。",
            f"- 问题最多模块：{summary['top_module']}（{summary['top_module_count']} 个）。",
            f"- 缺陷量最高负责人：{summary['top_owner']}（{summary['top_owner_count']} 个）。",
            f"- 高严重遗留 Bug 数：{summary['severe_leftover']}，请优先排查 fatal/serious 且未关闭问题。",
        ]
    )


def build_brief_text(
    summary: Dict[str, Any],
    workspace_id: str,
    workspace_name: str,
    filter_label: str,
    xlsx_path: str,
) -> str:
    """对话默认回执（统计聚合型）。"""
    title_name = (workspace_name or "").strip() or workspace_id
    top_module = summary.get("top_module") or "—"
    top_owner = summary.get("top_owner") or "—"
    top_count = summary.get("top_module_count") or 0
    return "\n".join(
        [
            f"## {title_name} · Bug 统计",
            "",
            f"- 范围：{workspace_id}｜{filter_label}",
            f"- 共 {summary.get('total', 0)}｜遗留 {summary.get('leftover', 0)}｜"
            f"修复率 {summary.get('fix_rate', 0)}%｜高严重 {summary.get('severe_leftover', 0)}",
            f"- 集中：{top_module} / {top_owner}（{top_count}）",
            f"- 报告：`{xlsx_path}`（stats + raw 工作表）",
        ]
    )


def build_list_brief_text(
    count: int,
    severe_count: int,
    workspace_id: str,
    workspace_name: str,
    filter_label: str,
    scene_label: str,
    xlsx_path: str,
) -> str:
    """对话默认回执（列表明细型，如未解决列表）。"""
    title_name = (workspace_name or "").strip() or workspace_id
    return "\n".join(
        [
            f"## {title_name} · {scene_label}",
            "",
            f"- 范围：{workspace_id}｜{filter_label}",
            f"- 共 {count} 条｜高严重 {severe_count}",
            f"- 报告：`{xlsx_path}`（stats + raw 工作表）",
        ]
    )


def build_root_cause_fetch_brief(
    count: int,
    workspace_id: str,
    workspace_name: str,
    filter_label: str,
) -> str:
    """根因拉数阶段：无 xlsx，仅 JSON 供 Agent 归类。"""
    title_name = (workspace_name or "").strip() or workspace_id
    return "\n".join(
        [
            f"## {title_name} · Bug 根因分析（拉数）",
            "",
            f"- 范围：{workspace_id}｜{filter_label}｜共 {count} 条",
            "- 已输出 `bugs_for_classification`（含描述摘要），请归类后带 `--root-cause-categories` 再执行生成 Excel",
        ]
    )


def build_root_cause_brief(
    count: int,
    workspace_id: str,
    workspace_name: str,
    filter_label: str,
    xlsx_path: str,
) -> str:
    """根因报告落盘后的对话回执。"""
    title_name = (workspace_name or "").strip() or workspace_id
    return "\n".join(
        [
            f"## {title_name} · Bug 根因分析",
            "",
            f"- 范围：{workspace_id}｜{filter_label}｜共 {count} 条",
            "- 报告含「根因类别统计」「缺陷归类」两个工作表（缺陷归类列：根因类别 | Bug ID | 标题）",
            f"- 报告：`{xlsx_path}`",
        ]
    )


def col_name(idx: int) -> str:
    s = ""
    n = idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def sheet_xml(rows: Sequence[Sequence[Any]]) -> str:
    body: List[str] = []
    for r_idx, row in enumerate(rows, start=1):
        c_nodes: List[str] = []
        for c_idx, val in enumerate(row, start=1):
            ref = f"{col_name(c_idx)}{r_idx}"
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                c_nodes.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                text = escape(str(val))
                c_nodes.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        body.append(f'<row r="{r_idx}">{"".join(c_nodes)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData>'
        "</worksheet>"
    )


def _sanitize_sheet_name(name: str) -> str:
    s = re.sub(r"[\[\]:*?/\\]", "_", (name or "Sheet").strip()) or "Sheet"
    return s[:31]


def write_xlsx_multi(
    path: Path, sheets: Sequence[Tuple[str, Sequence[Sequence[Any]]]]
) -> None:
    if not sheets:
        raise ValueError("至少需要一个工作表")
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(sheets)
    override_lines = [
        '  <Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '  <Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for i in range(1, n + 1):
        override_lines.append(
            f'  <Override PartName="/xl/worksheets/sheet{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        + "\n".join(override_lines)
        + "\n</Types>"
    )
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    sheet_entries: List[str] = []
    wb_rels: List[str] = []
    for idx, (sheet_name, _) in enumerate(sheets, start=1):
        safe = escape(_sanitize_sheet_name(sheet_name)).replace('"', "&quot;")
        sheet_entries.append(f'    <sheet name="{safe}" sheetId="{idx}" r:id="rId{idx}"/>')
        wb_rels.append(
            f'  <Relationship Id="rId{idx}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
        )
    wb_rels.append(
        f'  <Relationship Id="rId{n + 1}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        f'Target="styles.xml"/>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        "  <sheets>\n"
        + "\n".join(sheet_entries)
        + "\n  </sheets>\n</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        + "\n".join(wb_rels)
        + "\n</Relationships>"
    )
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf/></cellStyleXfs>
  <cellXfs count="1"><xf/></cellXfs>
</styleSheet>"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", styles)
        for idx, (_, rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml(rows))


def write_xlsx(path: Path, rows_stat: Sequence[Sequence[Any]], rows_raw: Sequence[Sequence[Any]]) -> None:
    write_xlsx_multi(path, [("stats", rows_stat), ("raw", rows_raw)])


def stat_rows_for_sheet(rows: Sequence[Dict[str, Any]]) -> List[List[Any]]:
    out: List[List[Any]] = [["模块", "负责人", "总数", "已修复", "遗留", "严重Bug数"]]
    for r in rows:
        out.append([r["module"], r["owner"], r["total"], r["fixed"], r["leftover"], r["severe_leftover"]])
    return out


def raw_rows_for_sheet(
    bugs: Sequence[Dict[str, Any]], include_description: bool = False
) -> List[List[Any]]:
    header: List[str] = [
        "id",
        "title",
        "status",
        "severity",
        "priority_label",
        "module",
        "owner",
        "created",
    ]
    if include_description:
        header.append("description")
    out: List[List[Any]] = [header]
    for b in bugs:
        row: List[Any] = [
            b.get("id", ""),
            b.get("title", ""),
            b.get("status", ""),
            b.get("severity", ""),
            b.get("priority_label", b.get("priority", "")),
            pick_first_text(b, ["module", "module_name", "component"], "未分类模块"),
            pick_first_text(b, ["current_owner", "owner"], "未分配负责人"),
            b.get("created", ""),
        ]
        if include_description:
            row.append(b.get("description", ""))
        out.append(row)
    return out


def main() -> None:
    args = parse_args()
    start = normalize_date_str(args.start_date or "")
    end = normalize_date_str(args.end_date or "")

    iteration_id: Optional[str] = str(args.iteration_id or "").strip() or None
    bugs: List[Dict[str, Any]]
    workspace_meta: Dict[str, Any] = {}

    client: Optional[Any] = None
    if not args.source_json or not str(args.workspace_id or "").strip():
        client = load_tapd_client()

    workspace_id, workspace_meta = resolve_workspace_scope(client, args)

    if args.source_json:
        bugs = read_source_json(args.source_json)
    else:
        if client is None:
            client = load_tapd_client()
        if not iteration_id and str(args.iteration_name or "").strip():
            iteration_id = resolve_iteration_id(
                client, workspace_id, args.iteration_id, args.iteration_name
            )
            if not iteration_id:
                raise ValueError(f"未找到迭代：{args.iteration_name}")
        bugs = fetch_all_bugs(
            client=client,
            workspace_id=workspace_id,
            page_size=max(1, int(args.page_size)),
            max_pages=max(1, int(args.max_pages)),
            iteration_id=iteration_id,
            version=args.version,
            include_description=bool(args.include_description),
        )

    display_name = (workspace_meta.get("workspace_name") or "").strip()
    if not display_name and workspace_meta.get("requested_name"):
        display_name = str(workspace_meta["requested_name"]).strip()
    if not display_name and client is not None and not args.source_json:
        display_name = fetch_workspace_display_name(client, workspace_id)

    filtered = [
        b
        for b in bugs
        if in_date_range(b, start, end)
        and match_version_local(b, args.version)
        and match_iteration_local(b, iteration_id, args.iteration_name)
        and match_status_local(b, args)
    ]
    filter_label = build_filter_label(args)
    rows = aggregate_rows(filtered, args.group_by)
    summary = compute_summary(rows)
    md = build_markdown_table(rows)
    insights = build_insight_text(summary)

    categories_path = str(getattr(args, "root_cause_categories", None) or "").strip()
    has_categories = bool(categories_path)
    include_desc = bool(args.include_description)
    fetch_for_root_cause = include_desc and not has_categories

    xlsx_path_str: Optional[str] = None
    if not fetch_for_root_cause:
        if args.output_xlsx:
            xlsx_out = Path(args.output_xlsx).expanduser().resolve()
        else:
            xlsx_out = default_output_xlsx_path(args, workspace_id)
        xlsx_out.parent.mkdir(parents=True, exist_ok=True)
        if has_categories:
            category_by_id = load_root_cause_categories(categories_path)
            assignments = build_assignments_from_bugs(filtered, category_by_id)
            write_xlsx_multi(
                xlsx_out,
                [
                    ("根因类别统计", root_cause_summary_rows(assignments)),
                    ("缺陷归类", root_cause_list_rows(assignments)),
                ],
            )
            brief = build_root_cause_brief(
                count=len(filtered),
                workspace_id=workspace_id,
                workspace_name=display_name,
                filter_label=filter_label,
                xlsx_path=str(xlsx_out),
            )
        else:
            write_xlsx(
                xlsx_out,
                stat_rows_for_sheet(rows),
                raw_rows_for_sheet(filtered, include_description=include_desc),
            )
            if args.open_only:
                severe_n = count_severe_open(filtered)
                brief = build_list_brief_text(
                    count=len(filtered),
                    severe_count=severe_n,
                    workspace_id=workspace_id,
                    workspace_name=display_name,
                    filter_label=filter_label,
                    scene_label="未解决 Bug",
                    xlsx_path=str(xlsx_out),
                )
            else:
                brief = build_brief_text(
                    summary=summary,
                    workspace_id=workspace_id,
                    workspace_name=display_name,
                    filter_label=filter_label,
                    xlsx_path=str(xlsx_out),
                )
        xlsx_path_str = str(xlsx_out)
    else:
        brief = build_root_cause_fetch_brief(
            count=len(filtered),
            workspace_id=workspace_id,
            workspace_name=display_name,
            filter_label=filter_label,
        )

    result: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "resolved_from": workspace_meta.get("resolved_from", "id"),
        "workspace_name": display_name,
        "filter_label": filter_label,
        "iteration_id": iteration_id,
        "total_raw_bugs": len(bugs),
        "total_filtered_bugs": len(filtered),
        "group_by": args.group_by,
        "brief": brief,
        "markdown_table": md,
        "insights": insights,
        "summary": summary,
    }
    if xlsx_path_str:
        result["xlsx_path"] = xlsx_path_str
    if fetch_for_root_cause:
        result["root_cause_stage"] = "fetch"
        result["bugs_for_classification"] = build_bugs_for_classification(filtered)
    elif has_categories:
        result["root_cause_stage"] = "report"
    if workspace_meta.get("requested_name"):
        result["requested_name"] = workspace_meta["requested_name"]
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

