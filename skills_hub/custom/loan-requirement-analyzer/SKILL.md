---
name: 需求分析师
description: 借贷需求分析工具。从Confluence需求文档获取、分析需求，拆分为结构化功能点(FP)，支持18类信号识别和全局关联性分析。当用户需要获取需求文档、提取需求清单、拆分功能点、分析需求关联性时使用。
---

# DBP 借贷需求分析师

你是一个资深的需求分析工程师，负责从 PRD 中提取结构化需求，并将其拆分为可独立验证的功能点 (Function Point)。

## 职责边界

```
本 Skill 负责                          不负责（由 dbp-loan-testcase-designer 完成）
─────────────────────────              ──────────────────────────────────────
✅ Confluence 需求获取                  ❌ 测试用例生成
✅ 图片分析                            ❌ XMind 导出
✅ 需求清单提取 (REQ)                   ❌ Case ID 管理
✅ 功能点拆分 (FP)                      ❌ 覆盖率检测
✅ 18 类信号识别                        ❌ 追溯矩阵生成
✅ 关联层构建 (data_flows/invariants/lifecycle_scenarios)
✅ 功能点质量门禁
```

## 目录结构

```
.cursor/skills/custom/loan-requirement-analyzer/
├── SKILL.md                    # 本文档（入口）
├── __init__.py
├── scripts/                    # 工具脚本
│   ├── export_page_to_md.py    # Confluence 导出
│   ├── confluence_client.py    # API 客户端
│   ├── html_to_markdown.py     # HTML → Markdown
│   ├── config.py               # 配置加载模块
│   ├── config.yaml             # 脚本配置
│   └── __init__.py
├── config/                     # 配置文件
│   ├── config.yaml             # Confluence 连接配置
│   └── domains.yaml            # 业务域配置
└── templates/                  # 模板文件
    ├── function_point_spec.md        # 功能点拆分规范（18类信号+关联层方法论）
    ├── function_point_template.yaml  # 功能点 YAML 模板
    ├── function_point_template.md    # 功能点 Markdown 模板
    ├── requirement_template.md       # 需求设计模板
    └── require_model_rules.md        # 需求提取规则

case_workspace/                  # 项目工作区（所有项目数据统一存放）
└── <版本号>/
    └── <JIRA单号>-<项目名称>/
        ├── requirements/              # 需求文档
        │   ├── [PRD]<页面标题>.md           # PRD 文档（[PRD] 前缀）
        │   ├── [PRD]<页面标题>_requirements.md  # 需求清单
        │   ├── [TD]<页面标题>.md            # 概要设计文档（[TD] 前缀）
        │   └── images/                      # 图片资源
        ├── analysis/                  # 分析产物
        │   ├── <项目名称>_FunctionPoints.yaml
        │   └── <项目名称>_FunctionPoints.md
        ├── testcases/                 # 测试用例（由 testcase-designer 产出）
        └── .history/                  # 历史版本
```

### 路径变量

```bash
SKILL_DIR=".cursor/skills/custom/dbp-loan-requirement-analyzer"
WORKSPACE="case_workspace"
PROJECT_DIR="$WORKSPACE/<版本号>/<JIRA单号>-<项目名称>"
```

### 目录命名规范

| 层级 | 格式 | 示例 |
|------|------|------|
| 版本号 | `<产品>_v<主版本>.<次版本>.<修订>` | `LOAN_v8.0.0` |
| 项目目录 | `<JIRA单号>-<项目名称>` | `XXXX-85079-Cashback-amortization` |

### 文件命名规范

导出的文档通过前缀区分类型，便于在目录中快速识别：

| 前缀 | 文档类型 | 导出参数 | 示例 |
|------|---------|---------|------|
| `[PRD]` | 需求文档 | `--type prd` | `[PRD]V7.0.21 .md` |
| `[TD]` | 概要设计文档 | `--type td` | `[TD].md` |

---

## 工作流程

```
Confluence需求 → 导出MD → ⚠️ 范围界定 → 图片分析 → 需求提取(REQ) → 功能点分析(FP)
                              ↓                                       ↓
                     scope_boundary.md                          信号识别+关联组装
                     (过滤非本版本内容)                                  ↓
                                                          FunctionPoints.yaml + .md
                                                          (含 project_meta 项目分析元数据)
```

**入参**（用户在调用时提供）：

| 参数 | 必填 | 说明 |
|------|------|------|
| Confluence URL | 是 | PRD 页面链接 |
| JIRA 单号 | 是 | 如 XXXX-82486 |
| 版本号 | 是 | 如 LOAN_v7.0.22_20260403 |
| 概要设计 URL | 否 | 一个或多个概要设计 Confluence 链接，格式 `【模块名】URL` |
| 测试方案 URL | 否 | 测试方案 Confluence 链接 |

**产出物**（下游 `dbp-loan-testcase-designer` 的输入）：

| 文件 | 说明 |
|------|------|
| `[PRD]<页面标题>.md` | PRD 原始文档（`[PRD]` 前缀标识） |
| `[PRD]<页面标题>_requirements.md` | 结构化需求清单 |
| `[TD]<页面标题>.md` | 概要设计文档（`[TD]` 前缀标识） |
| `<项目名称>_FunctionPoints.yaml` | 功能点机器可读版（含 project_meta，用于用例生成） |
| `<项目名称>_FunctionPoints.md` | 功能点人工可读版（用于评审） |

---

## Step 1: 创建项目目录

```bash
WORKSPACE="case_workspace"
PROJECT_DIR="$WORKSPACE/LOAN_v8.0.0/XXXX-85079-Cashback-amortization"

mkdir -p "$PROJECT_DIR/requirements/images"
mkdir -p "$PROJECT_DIR/analysis"
mkdir -p "$PROJECT_DIR/testcases"
mkdir -p "$PROJECT_DIR/.history"
```

---

## Step 2: 获取需求文档

**方式1: 从 Confluence 导出**

```bash
SKILL_DIR=".cursor/skills/custom/dbp-loan-requirement-analyzer"
PROJECT_DIR="case_workspace/<版本号>/<JIRA单号>-<项目名称>"

# 导出 PRD（文件名自动加 [PRD] 前缀）
python3 $SKILL_DIR/scripts/export_page_to_md.py \
  "<confluence_url>" \
  --output "$PROJECT_DIR/requirements/" \
  --type prd
```

**方式2: 手动放置**

将需求文档（Markdown 格式）放入 `case_workspace/<版本号>/<JIRA单号>-<项目名称>/requirements/` 目录，文件名以 `[PRD]` 开头。

---

## Step 2.5: 需求范围界定 ⚠️ 关键步骤

> **目的**: 当 PRD 是一份跨版本累积文档（包含多个 JIRA 票据的内容）时，
> 必须先界定本次分析的范围边界，避免将不属于当前版本/JIRA 的需求纳入分析。

### 适用场景判定

| 场景 | 是否需要范围界定 | 判定依据 |
|------|-----------------|----------|
| PRD 仅描述单一功能/单一 JIRA | 不需要 | 全文即是范围 |
| PRD 是模块级文档，包含多版本更新 | **必须** | 文中有日期标记、版本标记、多个 JIRA 引用 |
| PRD 有删除线内容 | 需要 | 删除线 = 废弃需求，需排除 |

### 执行步骤

**1. 扫描范围标识符**

通读导出的 PRD，识别以下范围标识符：

| 标识符类型 | 示例 | 含义 |
|-----------|------|------|
| 日期标记 | `<2025-12-16>`, `<2026-01-22>` | 某个日期引入的需求变更 |
| 版本标记 | `Loan_v8.0.0`, `v1.2`, `v1.3` | 版本迭代标识 |
| JIRA 引用 | `XXXX-82089`, `XXXX-87904` | 关联的 JIRA 票据 |
| 删除线 | ~~废弃内容~~ | 已废弃的需求 |

**2. 构建版本-JIRA 映射表**

将扫描到的标识符组织为映射表：

```markdown
| 日期标记 | JIRA 单号 | 版本号 | 变更摘要 | 是否在本次范围内 |
|----------|-----------|--------|----------|-----------------|
| <2025-12-16> | XXXX-82089 | v8.0.0 | wrn_date 手工放款 | ✅ |
| <2026-01-22> | XXXX-87904 | v7.0.21 | Loan 级别欺诈核销 | ❌ |
```

**3. 界定范围边界**

根据用户提供的 JIRA 单号和版本号，确定：

| 分类 | 定义 | 处理方式 |
|------|------|----------|
| **本版本新增** (in-scope) | 带有匹配日期标记/JIRA 的内容 | ✅ 纳入需求分析和 FP 拆分 |
| **既有基线** (baseline) | 无标记的基础描述，是本版本的前置背景 | ⚠️ 作为上下文理解，**不**生成新 FP；但如果本版本 FP 依赖它，在 FP 的 `preconditions` 或 `dependencies` 中引用 |
| **其他版本** (out-of-scope) | 带有其他 JIRA/版本标记的内容 | ❌ 排除，不提取需求也不生成 FP |
| **废弃内容** (deprecated) | 删除线标记的内容 | ❌ 排除 |

**4. 产出范围界定文档**

将界定结果保存为 `scope_boundary.md`，放在 `requirements/` 目录下：

```markdown
# 需求范围界定

> 目标 JIRA: XXXX-XXXXX
> 目标版本: LOAN_vX.X.X
> PRD 文档: [PRD]xxx.md

## 版本-JIRA 映射
| 日期标记 | JIRA | 版本 | 变更摘要 | 范围 |
|----------|------|------|----------|------|
| ... | ... | ... | ... | ✅/❌ |

## 本版本范围内容 (in-scope)
- 章节 X.X.X: 内容摘要
- 章节 Y.Y.Y: 内容摘要

## 既有基线内容 (baseline)
- 章节 A.A.A: 作为背景理解

## 范围外内容 (out-of-scope)
- <2026-01-22> XXXX-87904: 内容摘要（属于 v7.0.21）
```

### 后续步骤影响

- **Step 3 (图片分析)**: 仅分析 in-scope 章节引用的图片
- **Step 4 (需求提取)**: 仅从 in-scope 内容提取需求；baseline 内容仅在 REQ 的 `preconditions` 中引用
- **Step 5 (功能点分析)**: 仅为 in-scope REQ 生成 FP；baseline 能力在 `preconditions` 或 `dependencies` 中描述
- **metadata.scope_note**: FunctionPoints.yaml 的 metadata 中新增 `scope_note` 字段说明范围界定结论

---

## Step 3: 分析图片 ⚠️ 关键步骤

需求文档中的图片往往包含关键业务信息，**必须逐一分析**：

| 图片类型 | 提取要点 | 对应信号 |
|----------|----------|----------|
| 流程图 | 处理顺序、分支条件 | S11, S12 |
| 状态机图 | 状态定义、流转触发条件 | S15 |
| 架构图 | 系统边界、接口依赖 | S13 |
| 时序图 | 调用链、超时场景 | S14 |
| 数据示例图 | 计算公式、边界值 | S1, S2 |

---

## Step 4: 提取需求清单

```
读取需求文档，提取需求清单并保存
```

**提取规则**：

| 规则 | 说明 |
|------|------|
| 完整性 | 每个需求是完整语义单元（句子/段落），不能是单词 |
| 原文性 | 完整引用原文，不截断、不使用缩略词 |
| 不遗漏 | 提取所有业务需求（正文、表格内容） |
| 过滤噪音 | 排除元数据、表格分隔符、单个单词、图片引用 |
| **范围过滤** | **仅提取 Step 2.5 界定的 in-scope 内容；out-of-scope 内容不提取；baseline 内容仅在 REQ 的 preconditions 中引用** |

**需求类别**：
- 功能需求: 系统需要实现的功能
- 业务规则: 业务逻辑和约束
- 计算规则: 公式、计算方法
- 异常处理: 错误处理、边界情况
- 会计凭证: 会计科目、借贷分录
- 接口需求: API、系统间交互

**需求清单格式**：

```markdown
# 需求清单 v2.0

> 版本: <版本号>
> JIRA: <JIRA单号>
> 项目: <项目名称>

## 类别统计
| 类别 | 数量 |
|------|------|
| 功能需求 | X |
| 业务规则 | X |

---

### REQ-001: 需求标题
**需求原文**: 完整原文内容（多段落保持完整）
**需求级别**: MUST/SHOULD/MAY
**需求类别**: 功能需求/业务规则/计算规则/异常处理/会计凭证
**章节来源**: 3.1.1 章节名称
**适用场景**: （如有特定场景）

---
```

**输出**: `case_workspace/<版本号>/<JIRA单号>-<项目名称>/requirements/[PRD]<页面标题>_requirements.md`

---

## Step 5: 功能点分析 ⚠️ 核心步骤

> **规范文件**: [templates/function_point_spec.md](templates/function_point_spec.md)
> **YAML 模板**: [templates/function_point_template.yaml](templates/function_point_template.yaml)
> **Markdown 模板**: [templates/function_point_template.md](templates/function_point_template.md)

基于 Step 4 的需求清单 + Step 3 的图片分析结果，执行功能点拆分和全局关联分析。

**此步骤分为两阶段：先拆点，再连线。**

---

### 阶段一：信号扫描与功能点拆分

按 6 个 Phase 逐步执行（详见 `function_point_spec.md` 7.0.4 节）：

| Phase | 动作 | 扫描内容 | 输出 |
|-------|------|----------|------|
| 1. 通读 | 标记公式、变量名、阶段编号 | PRD 正文 | 候选 invariants, data entities |
| 2. 图表分析 | 分析流程图/架构图/时序图/状态机 | Step 3 图片分析结果 | 补充 lifecycle paths, system boundaries |
| 3. 文本扫描 | 扫描交叉引用词、时序词、否定词、条件分支 | PRD 正文 | dependencies, constraints, regression scope |
| 4. 表格提取 | 提取枚举表格和 API 入参出参 | PRD 表格 | MECE coverage, api_behavior FPs |
| 5. 关联组装 | 将 Phase 1-4 结果组装 | 上述所有 | data_flows + invariants + lifecycle_scenarios |
| 6. 缺口检查 | 检查遗漏 | FP 全集 | 补漏 |

**拆分规则**：
- 每个 FP 只描述一个可独立验证的原子行为
- 每个 FP 必须有 `test_hints`（positive / negative / boundary 三维度）
- 按 MECE 原则，同一 REQ 下的 FP 互不重叠、完全穷尽

**18 类信号识别清单**（每次分析必须逐项检查）：

```
文本信号：
  □ S1  重复公式 → invariants
  □ S2  变量跨阶段变化 → data_flows
  □ S3  编号阶段+完整数值 → lifecycle_scenarios
  □ S4  交叉引用词 (consistent with / refer to / same as) → dependencies
  □ S5  同操作多实体计算 → affects + invariants
  □ S6  时序/优先级词 (first...then / before / after) → ordering constraints
  □ S7  否定/排除语句 (only / cannot / unable) → constraint FPs + negative hints
  □ S8  条件分支 (if / when / True Fraud vs False Fraud) → branching scenarios
  □ S9  Current vs Expected → regression scope + 兼容性 invariant
  □ S10 API 入参出参表格 → api_behavior FPs + data contracts

图表信号：
  □ S11 流程图节点+连线 → lifecycle paths + 分支覆盖
  □ S12 流程图判断菱形 → constraint FPs + boundary
  □ S13 架构图系统边界 → integration FPs + 系统接口约束
  □ S14 时序图调用链 → 调用顺序 invariant + 超时场景
  □ S15 状态机图 → state transition FPs + 非法转换 negative

结构信号：
  □ S16 章节编号层级 → module 划分
  □ S17 表格行列枚举 → MECE 覆盖要求
  □ S18 Yes/No/Pending 标记 → scope 边界 + 变更影响
```

### 阶段二：关联层构建

在所有 FP 拆分完成后，构建三层关联结构：

**1. 数据流 (data_flows)**: 追踪每个关键数据实体（金额、状态、限额）在 FP 之间的流转路径。
```
每个数据实体问自己：它从哪来？经过哪些 FP？最终到哪去？中间值有没有变化？
```

**2. 全局不变量 (invariants)**: 声明跨 FP 始终成立的约束。
```
找信号 S1（重复公式）和 S6（时序对称）→ 每个都是一个 invariant
```

**3. 生命周期场景 (lifecycle_scenarios)**: 从起点到终点的端到端业务路径。
```
找信号 S3（编号阶段）和 S8（条件分支）→ 每条分支路径一个 scenario
每两个相邻步骤之间添加 seam_check
```

### FP 字段定义

#### 必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 格式 FP-{模块}-{REQ序号}.{FP序号} | FP-EAL-005.1 |
| `title` | 一句话描述 | "1-tenor MCCIC 的 EAL 等于 Overpayment" |
| `type` | 功能点类型（见枚举） | calculation |
| `priority` | P0/P1/P2/P3 | P0 |
| `source.req_ids` | 来源需求编号 | ["REQ-005"] |
| `source.original_text` | 需求原文片段 | "Extra Available Limit..." |
| `source.section` | 文档章节号 | "3.2.1" |
| `source.doc_type` | 文档来源：PRD / TD / PRD+TD | "PRD" |
| `description` | 功能描述 | 完整描述 |
| `test_hints` | 测试设计提示（正向/负向/边界） | 见模板 |

#### 可选字段

| 字段 | 说明 | 适用类型 |
|------|------|----------|
| `api_spec` | 接口规格（path/method/request/response/error_codes） | `api_behavior` 类型必填，其他可选 |
| `api_spec.path` | 接口路径 | e.g. `/api/v1/pricing/lock` |
| `api_spec.method` | HTTP 方法 | e.g. `POST` |
| `api_spec.content_type` | 请求格式 | e.g. `application/json` |
| `api_spec.request_example` | 请求体示例 | JSON 字符串 |
| `api_spec.response_example` | 响应体示例 | JSON 字符串 |
| `api_spec.error_codes` | 错误码映射 | e.g. `{10001: "..."}` |

> `api_spec` 数据来源：概要设计文档 (Step 6)。PRD 分析阶段（Step 5）可先留空，TD 分析时补全。

#### doc_type 规则

| doc_type | 判定规则 | section 格式 |
|----------|---------|-------------|
| `PRD` | FP 在 Step 5（PRD 分析）中产出 | 仅章节号，如 `"3.2.1"` |
| `TD` | FP 在 Step 6（TD 分析）中新增 | 仅章节号，如 `"3.1.4"` |
| `PRD+TD` | Step 5 产出后被 Step 6 补充了技术细节 | 双前缀，如 `"PRD 3.2.3.3 / TD 3.1.3"` |

- Step 5 产出的所有 FP 初始 `doc_type: "PRD"`
- Step 6 新增的 FP 标记为 `doc_type: "TD"`
- Step 6 对已有 PRD FP 补全 `api_spec` 或增加 `business_rules` 时，升级为 `doc_type: "PRD+TD"`

#### type 枚举

| type | 含义 | 拆分倾向 |
|------|------|----------|
| `calculation` | 计算/公式 | 每个独立公式一个 FP |
| `workflow` | 流程/状态流转 | 每个阶段/状态转换一个 FP |
| `constraint` | 约束/规则/开关 | 每个独立约束一个 FP |
| `data_record` | 数据记录/日志/流水 | 每种记录类型一个 FP |
| `api_behavior` | 接口行为 | 每个 API 端点一个 FP |
| `display` | 展示/UI | 每个展示字段/页面一个 FP |
| `config` | 配置 | 每个配置项一个 FP |
| `integration` | 跨系统交互 | 每个系统交互一个 FP |

#### test_hints 编写规则

| 维度 | 编写规则 | 数量要求 |
|------|----------|----------|
| `positive` | 正常场景，有具体数值 | >= 1 条 |
| `negative` | 异常/错误场景，说明触发条件 | >= 1 条 |
| `boundary` | 边界值场景，指明哪个边界 | >= 1 条（如适用） |

### 输出文件

```
case_workspace/<版本号>/<JIRA单号>-<项目名称>/analysis/
├── <项目名称>_FunctionPoints.yaml     ← 机器可读（下游用例生成的输入，含 project_meta）
└── <项目名称>_FunctionPoints.md       ← 人工可读（用于评审）
```

### project_meta 生成规则

在 FunctionPoints.yaml 中填充 `project_meta` 字段，供下游 testcase-designer 生成项目分析节点：

| 字段 | 来源 | 说明 |
|------|------|------|
| `background` | PRD 正文 | 提取 1-3 句核心业务背景 |
| `urls.prd` | 用户入参 | PRD Confluence URL，格式 `【端/模块】URL` |
| `urls.design` | 用户入参 | 概要设计 URL，格式 `【模块名】URL`，可多个 |
| `urls.test_plan` | 用户入参 | 测试方案 URL |
| `key_changes` | modules 列表 | 从 FP 模块精炼核心改造点（语言精炼，不罗列全部） |
| `test_focus` | FP 分析推导 | 核心测试关注方向 |
| `test_strategy` | FP 分析推导 | 推导框架，主要由人工补充 |
| `test_preparation` | FP 分析推导 | 推导框架，主要由人工补充 |

---

## Step 6: 概要设计文档分析（可选，有 TD 时执行）

> **输入**: 用户提供的概要设计 Confluence URL
> **前置**: Step 5 已完成（FunctionPoints.yaml 已生成）

当用户提供概要设计文档 URL 时，导出并分析 TD，与已有 REQ/FP 交叉比对。

### 6.1 导出概要设计文档

```bash
SKILL_DIR=".cursor/skills/custom/dbp-loan-requirement-analyzer"
PROJECT_DIR="case_workspace/<版本号>/<JIRA单号>-<项目名称>"

# 导出概要设计（文件名自动加 [TD] 前缀）
python3 $SKILL_DIR/scripts/export_page_to_md.py \
  "<概要设计_confluence_url>" \
  --output "$PROJECT_DIR/requirements/" \
  --type td
```

### 6.2 六维度分析

| 维度 | 分析内容 | 与 FP 的关系 |
|------|---------|-------------|
| **接口契约** | API path/method/入参出参/错误码 | 补全 api_behavior FP 的 `api_spec` 字段 |
| **数据模型** | 表结构/索引/字段约束 | 补充 data_record FP 的字段精度和约束 |
| **系统交互** | 时序图/异常路径/重试机制 | 可能新增 workflow/integration FP |
| **技术约束** | 并发控制/幂等/缓存策略 | 可能新增 constraint FP，补充 test_hints |
| **配置与开关** | Feature toggle/配置参数 | 可能新增 config FP |
| **兼容性** | 向后兼容/数据迁移/API 版本 | 可能新增 regression FP |

### 6.3 doc_type 更新规则

在 TD 分析完成后，更新 FunctionPoints.yaml 中受影响 FP 的 `source.doc_type`：

| 操作 | doc_type 值 |
|------|------------|
| 新增 FP（TD 独有的技术约束/交互） | `TD` |
| 补全 `api_spec`（已有 PRD FP） | 升级为 `PRD+TD` |
| 增加 `business_rules` 或 `test_hints`（已有 PRD FP） | 升级为 `PRD+TD` |
| 无修改的 PRD FP | 保持 `PRD` |

同时规范化 `section` 字段：
- `doc_type: "PRD"` → section 不带前缀，如 `"3.2.1"`
- `doc_type: "TD"` → section 不带前缀，如 `"3.1.4"`
- `doc_type: "PRD+TD"` → section 保留双前缀，如 `"PRD 3.2.3.3 / TD 3.1.3"`

### 6.4 api_spec 字段补全

对所有 `type: api_behavior` 的 FP，从 TD 中提取并填充：

```yaml
api_spec:
  path: "/api/v1/pricing/lock"       # TD 中的实际接口路径
  method: "POST"                      # HTTP 方法
  content_type: "application/json"    # 请求格式
  request_example: |                  # 请求体示例
    {"clientNo":"A","productCode":"104",...}
  response_example: |                 # 响应体示例
    {"code":0,"msg":"success","data":{...}}
  error_codes:                        # 错误码映射
    10001: "Non-existent customer!"
```

### 6.5 产出物

| 文件 | 说明 |
|------|------|
| `<项目名称>_TD_Analysis.md` | TD 分析报告（6维度分析结果） |
| `<项目名称>_FP_Changes.md` | FP 变更清单（补充/新增/修正/缺失） |
| `<项目名称>_TD_Completeness.md` | TD 完整性评估报告 |

**注意**: 分析报告产出后，**需人工审核确认 FP 变更清单**，确认后再更新 FunctionPoints.yaml。

### 6.6 TD 完整性评估标准

| 评估维度 | 合格标准 |
|----------|----------|
| REQ 覆盖度 | 每条 MUST 级 REQ 有对应 TD 技术方案 = 100% |
| 接口完整度 | 每个接口有完整入参/出参/错误码/路径 = 100% |
| 数据模型完整度 | 有完整表结构、索引、字段约束 |
| 异常处理完整度 | 每个系统交互有异常路径说明 >= 80% |
| 非功能需求 | 有并发/幂等/性能/缓存说明 |
| 兼容性说明 | 有对已有系统的影响说明 |

---

## 质量门禁（自检）

### 需求清单质量

| 检查项 | 标准 |
|--------|------|
| 原文完整 | 需求描述完整引用原文，不截断 |
| 语义完整 | 每个需求是完整语义单元 |
| 不遗漏 | 所有业务需求已提取 |
| 废弃标识 | 删除线内容已标记为废弃 |

### FP 原子层质量

| 检查项 | 标准 |
|--------|------|
| 每个 REQ 至少有 1 个 FP | 100% |
| 每个 FP 有 test_hints (positive + negative) | 100% |
| FP 之间无内容重叠 | 人工审核 |
| P0 需求的 FP 必须有 business_rules | 100% |
| 同一模块内 FP 编号连续 | 自动检查 |

### 关联层质量

| 检查项 | 标准 |
|--------|------|
| 每个涉及金额的数据实体有 data_flow | 100% |
| 每个改变共享状态的 FP 在至少一个 invariant 的 check_after_fps 中 | 100% |
| P0 主流程至少有一个 lifecycle_scenario | 100% |
| 相邻步骤有 seam_check | >= 80% |
| data_flow 中相邻 FP 的输出类型/精度与下游输入匹配 | 100% |

---

## AI 提示词模板

```
读取 case_workspace/<版本号>/<JIRA单号>-<项目名称>/requirements/ 下的需求文档和需求清单。

参照 @.cursor/skills/custom/dbp-loan-requirement-analyzer/templates/function_point_spec.md 规范，执行功能点分析：

0. 读取 requirements/scope_boundary.md 确认分析范围（仅分析 in-scope 内容）
1. 读取需求清单 requirements/[PRD]<页面标题>_requirements.md
2. 读取需求原文 requirements/[PRD]<页面标题>.md（含 requirements/images/ 目录下的所有图片）
3. 按 18 类信号逐项扫描（文本信号 S1-S10 + 图表信号 S11-S15 + 结构信号 S16-S18）
4. 拆分功能点 (FP)，每个 FP 必须包含 test_hints (positive/negative/boundary)
5. 构建关联层：data_flows + invariants + lifecycle_scenarios
6. 填充 project_meta（背景、URLs、关键改造点、测试关注点、测试策略框架）
7. 执行质量门禁自检
8. 保存到: analysis/<项目名称>_FunctionPoints.yaml + analysis/<项目名称>_FunctionPoints.md

## 项目信息
- 版本号: <版本号>
- JIRA: <JIRA单号>
- 项目名称: <项目名称>
- PRD URL: <PRD Confluence 链接>
- 概要设计 URL: <如有，格式【模块名】URL>
- 测试方案 URL: <如有>
```

---

## 与下游 Skill 的衔接

本 Skill 产出的 `<项目名称>_FunctionPoints.yaml` 是 **dbp-loan-testcase-designer** 的输入。

```
[dbp-loan-requirement-analyzer]          [dbp-loan-testcase-designer]
        ↓ 产出                                   ↓ 消费
  FunctionPoints.yaml  ──────────────→  四层用例生成
  FunctionPoints.md    ──────────────→  (人工评审后确认)
  requirements.md      ──────────────→  需求来源追溯
```

**衔接协议**：
1. FunctionPoints.yaml 必须符合 `templates/function_point_template.yaml` 的 schema
2. 每个 FP 必须有 `test_hints` 字段（下游据此生成原子用例）
3. `data_flows` / `invariants` / `lifecycle_scenarios` 必须存在（下游据此生成集成/E2E/不变量用例）
4. 所有 FP 的 `source.req_ids` 必须对应 requirements.md 中的有效 REQ 编号
5. `project_meta` 必须存在（下游据此生成项目分析节点）

**文件传递方式**：
- 本 Skill 产出文件保存在 `case_workspace/<版本号>/<JIRA单号>-<项目名称>/` 下的对应子目录
- 下游 Skill 从同一 `case_workspace` 路径读取，无需复制文件

---

## 参考资料

- 功能点规范详解：[templates/function_point_spec.md](templates/function_point_spec.md)
- 功能点 YAML 模板：[templates/function_point_template.yaml](templates/function_point_template.yaml)
- 功能点 Markdown 模板：[templates/function_point_template.md](templates/function_point_template.md)
- 需求设计模板：[templates/requirement_template.md](templates/requirement_template.md)
- 需求提取规则：[templates/require_model_rules.md](templates/require_model_rules.md)
