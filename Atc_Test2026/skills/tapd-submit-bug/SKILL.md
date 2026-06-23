# TAPD Submit Bug Skill

聚焦 TAPD 缺陷提交与附件上传场景。基于 TAPD 开放 API 与 `tapd_client_stdlib.py`，完成「创建 bug -> 上传截图/日志附件 -> 返回链接」的标准流程。
优先使用通用包装脚本 `scripts/submit_bug_with_attachment.py`，避免 Windows PowerShell 下中文参数直传引起的乱码或转义问题。

## 何时使用

- 用户明确要求提交 TAPD bug。
- 用户给出 bug 标题、描述、优先级、严重程度、负责人、提单人等字段。
- 用户需要把本地截图、日志或录屏作为附件关联到 bug。

## 必要输入

- `title`：缺陷标题（创建必填）。
- `description`：问题描述与复现步骤。
- 可选 `file`：本地附件路径（截图/日志等）。

以下固定字段可通过本地配置自动补齐（推荐）：

- `workspace_id`：项目编号。
- `current_owner`：当前负责人昵称（可由模块自动映射）。
- `reporter`：提单人昵称。
- `version`：所属版本。

以下字段需由 AI 判断或人工显式指定（不再由配置默认）：

- `priority`：优先级（如 `high`、`medium`、`low`）。
- `severity`：严重程度（如 `fatal`、`serious`、`normal`、`prompt`）。

## 环境与认证

- 认证二选一：
  - `TAPD_ACCESS_TOKEN`（推荐）
  - `TAPD_API_USER` + `TAPD_API_PASSWORD`
- 可选：
  - `TAPD_API_BASE_URL`（默认 `https://api.tapd.cn`）
  - `TAPD_BASE_URL`（默认 `https://www.tapd.cn`）

## 标准执行流程

1. 调用 `POST bugs` 创建缺陷。
2. 从返回体读取 bug 长 id（示例：`1169725253001000006`）。
3. 若有附件，调用 `upload-attachment` 子命令上传并关联：
   - `--workspace-id` = 项目编号
   - `--entry-id` = bug 长 id
   - `--type` = `bug`
   - `--file` = 本地文件路径
4. 返回 bug id、附件 id（如有）和前端可访问链接。

## 附件失败恢复（防重复提单）

- 脚本会基于 `workspace_id + title + description + reporter` 计算 `idempotency_key`，并将状态落盘到：
  - `prcoess_skill/.tapd/submit_state.json`
- 当出现“Bug 已创建成功，但附件上传失败”时：
  1. 状态会记录 `bug_id` 且 `attachment_uploaded=false`；
  2. 下次同内容重试会优先命中状态，直接对已有 `bug_id` 重试附件上传；
  3. 不会再次执行 `POST bugs`，避免重复提单。
- 支持显式恢复参数：
  - `--resume-only`：仅从状态恢复并继续附件上传；若没有可恢复状态则报错，不会新建 bug。

恢复结果说明：

- 成功返回里会附带：
  - `recovered`：是否命中恢复路径；
  - `idempotent_skip`：是否因为同一附件已上传而直接幂等返回；
  - `idempotency_key`：本次幂等键，便于排障。
- 附件失败时会返回结构化错误：
  - `error=attachment_upload_failed`
  - `next_action=retry_attachment_only`
  - 同时包含 `bug_id` 与 `bug_url`，可直接人工查看已创建缺陷。

## 本地配置（一次性预设）

推荐先执行配置初始化 Skill 自动生成/升级配置：

```powershell
python ".cursor/skills/tapd/tapd-config-init/scripts/init_tapd_config.py"
```

1. 复制模板为本地私有配置文件（不入库）：
   - 模板：`prcoess_skill/.tapd/project_config.template.json`
   - 本地：`prcoess_skill/.tapd/project_config.json`
2. 在本地文件中维护固定信息：
   - `workspace_id`
   - `defaults.reporter/version`
   - `module_owner_map`（模块 -> 开发负责人）
   - 可选 `module_field_map`（模块级自定义字段）

示例：

```json
{
  "workspace_id": "69725253",
  "defaults": {
    "reporter": "张三",
    "version": "v2.3.0"
  },
  "module_owner_map": {
    "登录": "李四",
    "订单": "王五"
  }
}
```

## 命令示例（推荐：payload 文件 + 通用脚本）

### Windows（PowerShell）

```powershell
# baseDir 为当前 skill 根目录（运行时注入）
$env:PYTHONIOENCODING = "utf-8"
$payload = Join-Path $env:TEMP "tapd_bug_payload.json"

@'
{
  "workspace_id": "69725253",
  "title": "登录页弱网下偶发白屏",
  "description": "问题描述：...复现步骤：...",
  "priority": "high",
  "severity": "fatal",
  "current_owner": "开发同学昵称",
  "reporter": "提单人昵称"
}
'@ | Set-Content -Encoding UTF8 $payload

python "{baseDir}/scripts/submit_bug_with_attachment.py" `
  --payload-file $payload `
  --file "C:\path\to\screenshot.jpg"
```

### Windows（PowerShell，配置兜底最简提单）

```powershell
$env:PYTHONIOENCODING = "utf-8"
$payload = Join-Path $env:TEMP "tapd_bug_payload_min.json"

@'
{
  "title": "登录页弱网下偶发白屏",
  "summary": "弱网切换后登录页出现白屏，影响登录流程",
  "description": "复现步骤：1) 打开登录页 2) 网络切为3G 3) 输入账号密码点击登录；实际结果：白屏卡住；期望结果：可正常进入首页。",
  "module": "登录"
}
'@ | Set-Content -Encoding UTF8 $payload

python "{baseDir}/scripts/submit_bug_with_attachment.py" `
  --payload-file $payload `
  --config-file "prcoess_skill/.tapd/project_config.json" `
  --file "C:\path\to\screenshot.jpg" `
  --dry-run
```

### Windows（PowerShell，附件失败后仅恢复绑定）

```powershell
$env:PYTHONIOENCODING = "utf-8"
python "{baseDir}/scripts/submit_bug_with_attachment.py" `
  --payload-file $payload `
  --config-file "prcoess_skill/.tapd/project_config.json" `
  --file "C:\path\to\screenshot.jpg" `
  --resume-only
```

### macOS / Linux（Bash/Zsh）

```bash
# baseDir 为当前 skill 根目录（运行时注入）
export PYTHONIOENCODING="utf-8"
payload="${TMPDIR:-/tmp}/tapd_bug_payload.json"

cat > "$payload" <<'EOF'
{
  "workspace_id": "69725253",
  "title": "登录页弱网下偶发白屏",
  "description": "问题描述：...复现步骤：...",
  "priority": "high",
  "severity": "fatal",
  "current_owner": "开发同学昵称",
  "reporter": "提单人昵称"
}
EOF

python3 "{baseDir}/scripts/submit_bug_with_attachment.py" \
  --payload-file "$payload" \
  --file "/path/to/screenshot.jpg"
```

## 兼容方式（fallback）

```powershell
# 仍可分两步调用 tapd_client_stdlib.py
# 1) POST bugs
python ".cursor/skills/tapd/tapd-plus/scripts/tapd_client_stdlib.py" post --endpoint "bugs" `
  -p workspace_id=69725253 `
  -p title="登录页弱网下偶发白屏" `
  -p description="问题描述：...复现步骤：..." `
  -p priority=high `
  -p severity=fatal `
  -p current_owner="开发同学昵称" `
  -p reporter="提单人昵称"

# 2) upload-attachment
python ".cursor/skills/tapd/tapd-plus/scripts/tapd_client_stdlib.py" upload-attachment `
  --workspace-id 69725253 `
  --entry-id 1169725253001000006 `
  --type bug `
  --file "C:\path\to\screenshot.jpg"
```

## 返回结果格式

- Bug 链接：`{TAPD_BASE_URL}/{workspace_id}/bugtrace/bugs/view/{id}`
- 返回建议字段：
  - `bug_id`
  - `bug_url`
  - `attachment_id`（有附件时）
  - `attachment_filename`（有附件时）

## 注意事项

- 附件上传必须在 bug 创建成功之后执行。
- `upload-attachment` 的 `--type` 必须是 `bug`，不要与其他接口参数混用。
- 若只使用 `setx` 设置过 `TAPD_ACCESS_TOKEN`，当前会话拿不到变量时，脚本会尝试从 `HKCU\Environment` 读取。
- 若实例字段有定制（如严重程度候选值），应按项目实际配置传值。
- 推荐优先使用 `submit_bug_with_attachment.py --payload-file ...` 传中文字段，减少 PowerShell 引号与编码干扰。
- 示例中统一使用 `{baseDir}`，避免写死 `.cursor` 导致跨仓库复用困难。
- 支持参数优先级：CLI 显式参数 > payload 字段 > 本地配置默认值。
- `module` 已提供但未命中 `module_owner_map` 时会报错，避免负责人为空直接提单。
- 默认配置路径为 `prcoess_skill/.tapd/project_config.json`，可通过 `--config-file` 指定其他路径覆盖。

## AI 解析与确认提交流程（会话约定）

日常使用建议输入：`Bug截图 + 简述 + 模块`。AI 需先提炼以下结构化字段：

- `title`：一句话缺陷标题
- `summary`：问题概述
- `description`：包含复现步骤、实际结果、期望结果
- `module`：用于映射 `current_owner`
- `priority`：AI 判定优先级
- `severity`：AI 判定严重程度

低置信度处理：

- 当 AI 无法可靠判断 `priority/severity` 时，需要给出建议值并明确标注“待确认”。
- 用户确认建议值后再正式提交，避免误分级直接入库。

字段来源优先级：

- 人工显式传值（CLI / payload） > AI 判定值 > 配置默认（`priority/severity` 无配置兜底）。

执行约定：

1. 先 `--dry-run` 展示“完整缺陷单草稿”（含配置自动带入字段）。
2. 用户回复“确认提交”后，再执行正式提交（去掉 `--dry-run`）。
3. 正式提交时必须与“已确认草稿”保持一致，禁止切换为英文标题/英文描述。

草稿展示语言约定：

- `--dry-run` 后给用户展示的“草稿内容”必须使用中文提示，不使用英文字段说明句式。
- 标题展示值必须是中文语义；若内部草稿标题是英文，需先转换/改写为中文再展示给用户确认。
- 即使 payload 内部字段名是英文（如 `title`/`description`），对用户展示时也要转成中文标签。
- 推荐展示模板如下：

```text
草稿内容：
- 标题：xxx
- 空间ID：xxx
- 当前处理人：xxx
- 提单人：xxx
- 版本：xxx
- 优先级：xxx（建议，可改）
- 严重程度：xxx（建议，可改）
- 描述：
  复现步骤：
  1) xxx
  2) xxx
  实际结果：xxx
  期望结果：xxx
  影响范围：xxx
- 附件：xxx（已带上/无）
```

正式提交语言约定：

- 提交到 TAPD 的 `title`、`summary`、`description` 默认使用中文业务表达，不得使用英文整句。
- 若用户最初提供英文信息，AI 需要先翻译并给出中文草稿，用户确认后再提交。
- 提交前必须做一次自检：
  - `title` 不是英文句子（可含少量英文参数名，如 `tenantName`、`name`）。
  - `description` 必须包含中文小节：`复现步骤`、`实际结果`、`期望结果`、`影响范围`。
- 换行要求：`description` 需按段落组织，提交前转换为 TAPD 友好的 `<br/>` 换行，避免页面展示成一行。
- 若发现 payload 为英文内容，必须先中止提交并回到“草稿确认”步骤，不得直接提单。
