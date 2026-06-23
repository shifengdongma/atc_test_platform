# TAPD Bug Stats Skill

聚焦 TAPD 缺陷统计与报表场景。支持两类能力：**① 结构化统计（经 `bug_stats_report.py` 落盘 Excel + 对话 brief）；② 根因归类（Excel 两工作表：类别统计 + 缺陷归类）**。

## 何时使用

- 用户要求统计当前 bug 数量。
- 用户需要查看未解决 bug 数。
- 用户希望按状态、优先级、严重程度查看数量分布。
- 用户要求“本周项目 Bug 情况”“当前迭代 Bug 统计表”“按开发负责人 Bug 分布报表”。
- **用户要求缺陷根因分析、主题归类、从描述归纳问题类型**。
- **用户明确要求同时看**：数量分布与根因归纳——先拉数归类，再生成 Excel。

## 能力分工（避免混用）

| 场景 | 做法 |
|------|------|
| 统计、列表、未解决/未关闭、按模块负责人分布 | **`bug_stats_report.py` → 必出 `.xlsx`（stats + raw 工作表）+ 对话 `brief`** |
| 根因/主题归类 | **两步**：`--include-description` 拉数（JSON 含 `bugs_for_classification`）→ Agent 归类 → `--root-cause-categories` 生成**根因 Excel** |

## 环境与认证

- 认证二选一：
  - `TAPD_ACCESS_TOKEN`（推荐）
  - `TAPD_API_USER` + `TAPD_API_PASSWORD`
- 可选：
  - `TAPD_API_BASE_URL`（默认 `https://api.tapd.cn`）

## 工作空间范围（必传其一）

本 Skill **不读取** `prcoess_skill/.tapd/project_config.json`。统计前须从用户话术或命令行取得 **工作空间 ID** 或 **工作空间名称**。

| 用户提供 | 处理方式 |
|---------|---------|
| 工作空间 ID | `--workspace-id` |
| 工作空间名称 | `--project-name` / `--workspace-name`；`GET workspaces/user_participant_projects` 解析 |
| 均未给出 | 向用户确认；或 `tapd_client_stdlib.py projects --nick <昵称>` 列出项目 |

**优先级**：`--workspace-id` 高于 `--project-name` / `--workspace-name`（不可同时指定）。

## 必出 Excel 报告（强约束）

- **凡本 Skill 响应（除根因拉数阶段）**：须先执行 [`bug_stats_report.py`](scripts/bug_stats_report.py)；**禁止**仅在对话里列表而不落盘。
- **统计场景**：落盘 `prcoess_skill/.tapd/tapd_bugs_<场景>_<workspace_id>_<时间戳>.xlsx`
  - 工作表 `stats`：按 `--group-by` 聚合（模块/负责人等）
  - 工作表 `raw`：缺陷明细
- **根因落盘场景**：`bug_root_cause_analysis_<workspace_id>_<时间戳>.xlsx`，**仅两个工作表**：
  - `根因类别统计`：根因类别 | 条数 | 占比
  - `缺陷归类`：**根因类别 | Bug ID | 标题**（根因类别列在最前）
- **根因拉数阶段**（仅 `--include-description`、无 categories）：**不写 xlsx**，stdout JSON 含 `bugs_for_classification`；Agent 归类后再跑第二步。
- **对话**：只贴 `brief`；用户要表时打开 `.xlsx` 或指向 `xlsx_path`。
- **不使用 Markdown 报告**（不生成 `.md`、不写 `markdown_report_path`）。

### 场景 → 脚本参数

| 用户意图 | 脚本参数 |
|---------|---------|
| 本周 / 时间段统计 | `--start-date` / `--end-date` |
| 未解决 / 未关闭 / 遗留 | `--open-only` |
| 仅排除已关闭 | `--exclude-status closed`（与 `--open-only` 互斥） |
| 根因拉数 | `--include-description`（+ 与筛选一致的 `--open-only` 等） |
| 根因落盘 | `--root-cause-categories <json>`（与拉数相同筛选参数） |

## 报表能力

- 默认输出 **xlsx** 至 `.tapd/`（标准库 zip，无第三方依赖）。
- 脚本 JSON 含 `brief`、`summary`、`xlsx_path`（拉数阶段除外）；根因拉数含 `root_cause_stage: fetch` 与 `bugs_for_classification`；落盘含 `root_cause_stage: report`。

## 核心统计口径

- `总数`：`GET bugs/count`（`workspace_id`）。
- `已关闭`：+ `status=closed`。
- `已解决`：+ `status=resolved`。
- `未解决`：总数 − 已关闭 − 已解决（与 `--open-only` 一致）。

## 基于标题与描述的大模型根因分析

从缺陷 **title + description** 为每条 Bug **指定一个根因类别**；**不依赖** TAPD 自定义「缺陷根因」字段。**禁止**在 Excel 外再手写冗长分析报告。

### 两步流程

1. **拉数**：`bug_stats_report.py` + 与用户一致的筛选 + **`--include-description`** → 读 JSON 中 `bugs_for_classification`（含 `description_preview`）。
2. **归类并落盘**：Agent 归纳类别，写入 JSON（`{"<bug_id>": "<类别>"}` 或 `[{"id","category"}, ...]`），**再次执行**脚本并传入 **`--root-cause-categories`**（筛选参数与第 1 步一致）→ 脚本生成两工作表 xlsx。

类别名在「根因类别统计」与「缺陷归类」须一致；未指定 id 记为「未分类」。

### 描述处理

- 描述仅出现在 JSON 的 `description_preview`（截断），**不写入** xlsx 根因报告（根因 xlsx 仅两表，无描述列）。

### Agent 必须完成

- 为**每条**纳入范围的 Bug 指定**一个**根因类别。
- 通过 `--root-cause-categories` 让脚本生成 Excel（推荐）。

**不要**单独手搓 `GET bugs` 且不落盘。

## 命令示例

```powershell
# 统计 → Excel（stats + raw）
python ".cursor/skills/tapd/tapd-bug-stats/scripts/bug_stats_report.py" `
  --workspace-id 69725253 `
  --start-date 2026-05-11 `
  --end-date 2026-05-17 `
  --group-by module_owner

# 未解决列表统计
python ".cursor/skills/tapd/tapd-bug-stats/scripts/bug_stats_report.py" `
  --workspace-id 69725253 `
  --open-only

# 根因第 1 步：拉数（无 xlsx，仅 JSON）
python ".cursor/skills/tapd/tapd-bug-stats/scripts/bug_stats_report.py" `
  --workspace-id 69725253 `
  --open-only `
  --include-description

# 根因第 2 步：写入 categories 后生成 Excel
python ".cursor/skills/tapd/tapd-bug-stats/scripts/bug_stats_report.py" `
  --workspace-id 69725253 `
  --open-only `
  --root-cause-categories ".tapd/root_cause_categories_69725253.json"

# 可选：指定 Excel 路径
python ".cursor/skills/tapd/tapd-bug-stats/scripts/bug_stats_report.py" `
  --workspace-id 69725253 `
  --output-xlsx ".tapd/custom_report.xlsx"
```

常用参数：

- `--workspace-id` / `--project-name` / `--workspace-name` / `--nick`
- `--open-only` / `--exclude-status` / `--start-date` / `--end-date`
- `--group-by module|owner|module_owner`
- `--include-description`：根因拉数
- `--root-cause-categories`：根因落盘 JSON
- `--output-xlsx` / `--output-dir`

## 对用户回执（简洁优先）

- 约 **5–8 行**；落盘后 **必含** `xlsx_path`（拉数阶段除外）。
- 根因拉数阶段无 xlsx，brief 说明已输出 `bugs_for_classification` 及下一步。
- 默认不要贴整份表、`markdown_table` 全文、stdout JSON。

### brief 模板（统计）

```markdown
## {项目名} · Bug 统计

- 范围：{workspace_id}｜{filter_label}
- 共 {total}｜遗留 {leftover}｜修复率 {fix_rate}%｜高严重 {severe_leftover}
- 报告：`{xlsx_path}`（stats + raw 工作表）
```

### brief 模板（根因落盘）

```markdown
## {项目名} · Bug 根因分析

- 范围：{workspace_id}｜{filter_label}｜共 {count} 条
- 报告含「根因类别统计」「缺陷归类」两个工作表
- 报告：`{xlsx_path}`
```

## 注意事项

- 须取得工作空间 ID 或名称后再执行。
- 按名称解析依赖 `CURRENT_USER_NICK` 与用户参与项目列表。
- 未解决口径固定：排除 closed、resolved。
