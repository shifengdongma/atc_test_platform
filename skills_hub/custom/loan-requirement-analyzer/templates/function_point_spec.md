# 需求功能点规范 (Function Point Specification)

> 版本: 1.0 | 更新: 2026-02-28

## 1. 定位

```
需求文档 (PRD)
    ↓  提取
需求清单 (REQ-001~N)          粒度：一个业务需求，可能包含多个逻辑
    ↓  拆分
需求功能点 (FP-XXX-001.1)     粒度：一个可独立验证的原子行为 ← 本层
    ↓  生成
测试用例 (TC / Case ID)       粒度：一个具体的测试步骤和验证
```

**核心价值**：
- 消除 REQ → TC 之间的粒度跳跃，避免 AI 生成用例时自行拆分导致的遗漏
- 每个 FP 自带 `test_hints`，引导正向/负向/边界三维度设计
- 建立 REQ ↔ FP ↔ TC 三级追溯链

## 2. 拆分原则

### 2.1 原子性判断标准

一个 FP 是「原子的」当且仅当：

| 检查项 | 说明 | 示例 |
|--------|------|------|
| 单一验证目标 | 只验证一件事 | "EAL 等于 Overpayment" 而非 "EAL 计算和白名单校验" |
| 独立可测 | 不依赖其他 FP 的执行结果即可测试 | 可以单独构造前置数据验证 |
| 结果明确 | 预期结果可量化或可明确判断 | "EAL = $100" 而非 "EAL 正确" |

### 2.2 MECE 拆分方法

| 方法 | 适用场景 | 示例 |
|------|----------|------|
| **按输入条件拆** | 同一功能不同输入走不同分支 | 白名单 vs 非白名单子产品 |
| **按生命周期阶段拆** | 流程类需求 | Checkout→冻结→确认→创建贷款→还款 |
| **按计算公式拆** | 计算类需求包含多个公式 | EAL 计算、SPAAL 计算、PAL 计算 |
| **按系统交互拆** | 涉及多个系统或 API | LC 调用、LTS 展示、Portal 查询 |
| **按数据操作拆** | 同一操作读/写/校验分开 | 写入 flow_tab + 查询 flow_tab |

### 2.3 粒度把控

**太粗** (需要继续拆)：
```
❌ FP: "Checkout 时处理 Overpayment"
   → 这包含了冻结 Available Limit、冻结 Overpayment、更新 EAL、记录 Earmark 四件事
```

**合适**：
```
✅ FP-EMK-007.1: "Checkout 冻结 Earmarked Limit = min(交易金额, Available Limit)"
✅ FP-EMK-007.2: "Checkout 冻结 Earmarked Overpayment = 交易金额 - Earmarked Limit"
✅ FP-EMK-007.3: "冻结后 Extra Available Limit 变为 0"
✅ FP-EMK-007.4: "记录每笔交易的 Earmarked Overpayment 金额"
```

**太细** (可以合并)：
```
❌ FP: "EAL 在 Overpayment=$1 时等于 $1"
❌ FP: "EAL 在 Overpayment=$2 时等于 $2"
   → 这是同一规则的不同测试数据，属于 test_hints 级别
```

## 3. 字段定义

### 3.1 必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 唯一标识，格式 FP-{模块}-{REQ序号}.{FP序号} | FP-EAL-005.1 |
| `title` | 一句话描述功能点 | "1-tenor MCCIC 的 EAL 等于 Overpayment" |
| `type` | 功能点类型（见枚举） | calculation |
| `priority` | 优先级 P0/P1/P2/P3 | P0 |
| `source.req_ids` | 来源需求编号 | ["REQ-005"] |
| `source.original_text` | 需求原文片段 | "Extra Available Limit..." |
| `source.section` | 文档章节编号 | "3.2.1" |
| `source.doc_type` | 文档来源类型：PRD / TD / PRD+TD | "PRD" |
| `description` | 功能描述（比 title 详细） | 完整描述 |
| `test_hints` | 测试设计提示（正向/负向/边界） | 见模板 |

### 3.2 推荐字段

| 字段 | 说明 | 什么时候必须填 |
|------|------|----------------|
| `business_rules` | 业务规则/公式 | type=calculation 或 constraint 时 |
| `inputs` / `outputs` | 输入输出定义 | type=api_behavior 或 calculation 时 |
| `preconditions` | 前置条件 | 有特定前提时 |
| `dependencies` | 依赖的其他 FP | 有执行顺序依赖时 |
| `affects` | 影响的其他 FP | 状态变更影响下游时 |
| `api_path` | 涉及的 API | type=api_behavior 时 |

### 3.3 doc_type 填写规则

`source.doc_type` 标识功能点的文档来源，用于区分 PRD 分析阶段和 TD 分析阶段产出的功能点：

| doc_type | 含义 | 判定规则 | section 格式 |
|----------|------|---------|-------------|
| `PRD` | 来自需求文档 | FP 的 original_text 引自 PRD | 仅 PRD 章节号，如 `"3.2.1"` |
| `TD` | 来自概要设计 | FP 在 TD 分析阶段新增或 original_text 引自 TD | 仅 TD 章节号，如 `"3.1.4"` |
| `PRD+TD` | 两个文档共同定义 | PRD 定义业务需求，TD 补充了技术细节 | 保留双前缀，如 `"PRD 3.2.3.3 / TD 3.1.3"` |

**填写时机**：
- **Step 5（PRD 分析阶段）**产出的 FP → `doc_type: "PRD"`
- **Step 6（TD 分析阶段）**新增的 FP → `doc_type: "TD"`
- **Step 6 对已有 PRD FP 补充技术细节**（如补全 api_spec、增加 business_rules）→ 升级为 `doc_type: "PRD+TD"`

### 3.4 type 枚举

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

## 4. test_hints 编写规则

`test_hints` 是功能点到测试用例的桥梁，每个 FP 必须包含三个维度：

| 维度 | 编写规则 | 数量要求 |
|------|----------|----------|
| `positive` | 正常场景，验证功能按预期工作 | >= 1 条 |
| `negative` | 异常/错误场景，验证防御逻辑 | >= 1 条 |
| `boundary` | 边界值场景 | >= 1 条（如适用） |

**编写技巧**：
```yaml
test_hints:
  positive:
    - "具体输入 → 具体输出"        # 要有数值，不要写 "正常情况下可用"
  negative:
    - "什么条件下 → 什么结果"       # 要说明触发条件
  boundary:
    - "参数=边界值 → 预期行为"      # 要指明是哪个边界
```

## 5. FP → TC 映射关系

一个 FP 通常产出以下测试用例：

```
FP-EAL-005.1: "1-tenor MCCIC 的 EAL 等于 Overpayment"
│
├── TC-1 (正向): Overpayment=$100 → EAL=$100          ← from test_hints.positive
├── TC-2 (正向): Overpayment=$200 → EAL=$200          ← from test_hints.positive
├── TC-3 (负向): Overpayment=$0 → EAL=$0              ← from test_hints.negative
├── TC-4 (负向): 非白名单产品 → EAL=0                  ← from test_hints.negative
├── TC-5 (边界): Overpayment=0.01                      ← from test_hints.boundary
└── TC-6 (边界): Overpayment=Total Credit Limit        ← from test_hints.boundary
```

**经验值**：每个 FP 平均产出 3~6 条测试用例。

## 6. 与现有系统的衔接

### 6.1 文件命名和存放

```
resource/<版本号>/<JIRA单号>-<项目名称>/
├── <需求文档>.md                    # 原始文档
├── <需求文档>_requirements.md       # 需求清单 (REQ)
├── <项目名称>_FunctionPoints.yaml   # ← 新增：功能点 (FP)
├── <项目名称>_FunctionPoints.md     # ← 新增：功能点人读版
├── <项目名称>_TestCases.md          # 测试用例 (TC)
└── *_traceability_matrix.md         # 追溯矩阵 (REQ ↔ FP ↔ TC)
```

### 6.2 工作流程更新

```
Confluence需求 → 导出MD → 图片分析 → 需求提取(REQ)
                                         ↓
                                    功能点拆分(FP)  ← 新增
                                         ↓
                                    用例生成(TC) → 覆盖检测 → XMind导出
```

### 6.3 追溯矩阵升级

| REQ-ID | REQ 标题 | FP-ID | FP 标题 | TC (Case ID) | 覆盖状态 |
|--------|----------|-------|---------|---------------|----------|
| REQ-005 | Extra Available Limit | FP-EAL-005.1 | 1-tenor EAL=Overpayment | SPBC_CHECK_82480001 | ✅ |
| REQ-005 | Extra Available Limit | FP-EAL-005.2 | 非白名单不享受 EAL | SPBC_CHECK_82480003~04 | ✅ |

## 7. 全局关联性信号识别方法论

### 7.0 信号全景图

需求分析的本质是从非结构化的 PRD 中提取结构化的关联关系。
信号来源分三类：**文本信号**、**图表信号**、**结构信号**。

```
PRD 原始内容
│
├── 文本信号 ──────────── 从文字描述中识别
│   ├── S1  重复公式         → invariants
│   ├── S2  变量值跨阶段变化  → data_flows
│   ├── S3  编号阶段+数值    → lifecycle_scenarios
│   ├── S4  交叉引用词       → dependencies
│   ├── S5  同操作多实体计算  → affects / invariants
│   ├── S6  时序/优先级词    → ordering constraints
│   ├── S7  排除/否定语句    → constraint FPs + negative test_hints
│   ├── S8  条件分支 (if/when) → branching scenarios
│   ├── S9  Current vs Expected → regression scope
│   └── S10 API 入参出参表格  → api_behavior FPs + data contracts
│
├── 图表信号 ──────────── 从流程图/架构图中识别
│   ├── S11 流程图节点+连线  → lifecycle paths + 分支覆盖
│   ├── S12 流程图判断菱形   → constraint FPs + boundary
│   ├── S13 架构图系统边界   → integration FPs + 系统接口约束
│   ├── S14 时序图调用链     → 调用顺序 invariant + 超时场景
│   └── S15 状态机图状态流转  → state transition FPs + 非法转换
│
└── 结构信号 ──────────── 从文档结构本身识别
    ├── S16 章节编号层级     → module 划分
    ├── S17 表格行列结构     → MECE 枚举覆盖
    └── S18 标记(Yes/No/Pending) → scope 边界 + 变更影响
```

---

### 7.0.1 文本信号详解

#### S1-S5 (已有) 核心五类

| 信号 | PRD 中的表现 | 提取结果 |
|------|-------------|----------|
| S1 重复公式 | 同一等式在多个 Stage 代入计算 | → `invariants` |
| S2 变量跨阶段变化 | 同一字段在多个 Stage 出现不同值 | → `data_flows` |
| S3 编号阶段+数值 | Stage 1~N 带状态快照 | → `lifecycle_scenarios` |
| S4 交叉引用词 | "consistent with"、"refer to"、"same as" | → FP `dependencies` |
| S5 同操作多实体 | 一个操作列出多个子产品的影响 | → `affects` + `invariant.check_after_fps` |

#### S6 时序/优先级词 — NEW

**识别词**：`first...then`、`before`、`after`、`prior to`、`优先`、`先...后`

**PRD 实例**：
```
Rule 3: "use overpayment first"
Rule 4: "unfreeze available limit first, then overpayment"
Stage 1.4: "for future use cases such as app display and loan creation"
```

**提取结果**：
- Rule 3 "overpayment first" → 冻结 FP 必须有优先级参数：先扣 Overpayment 再扣 Limit
- Rule 4 "unfreeze limit first" → 解冻 FP 优先级是冻结的逆序
- 这两条规则构成一对 **对称约束** → invariant: freeze 顺序和 unfreeze 顺序互逆
- "for future use cases" → Earmark 记录是 Display/Loan Creation 的前置依赖

**关键价值**：时序词揭示了 FP 之间的 **执行顺序约束**，不只是数据依赖，还有业务语义上的"必须先做 A 再做 B"。漏掉时序就会漏掉顺序相关的测试场景（比如：如果冻结和解冻的优先级不是互逆的，会怎样？）。

#### S7 排除/否定语句 — NEW

**识别词**：`only`、`cannot`、`should not`、`except`、`unable`、`不能`、`仅`、`排除`

**PRD 实例**：
```
"The overpayment can only be used for MCCIC with 1 tenor and Credit Card"
"sub-Product 104,103,107 and 102 multi-tenor being unable to use overpayment"
"this purchase will be rejected for the over limit"
"should be failed and not returned"
```

**提取结果**：
- `only...102 ONE_TERM and 106` → 白名单 constraint FP + 所有非白名单子产品的 negative test_hints
- `unable to use` → 这些子产品必须有专门的 negative 测试用例
- `rejected` / `failed and not returned` → 错误场景的预期结果必须明确

**关键价值**：否定语句直接告诉你 negative test case 的设计方向。很多测试遗漏就是因为 PRD 说了"只能"，但测试没验证"不能"。

#### S8 条件分支 — NEW

**识别词**：`if`、`when`、`in case of`、`depending on`、枚举表格

**PRD 实例**：
```
Stage 7 (Card Dispute):
  "[Investigation Complete] True Fraud: update loan status to 'Fraudulent'"
  "[Investigation Complete] False Fraud: re-post a new loan"
```

```
Stage 4 vs Stage 2:
  Refund before Order Confirm → unfreeze
  Refund after Order Confirm → credit back to overpayment
```

**提取结果**：
- True Fraud / False Fraud → 同一个入口（Dispute）分叉成两条完全不同的路径 → 两个 lifecycle_scenario
- Before/After Order Confirm → 退款时机不同导致完全不同的资金流向 → 两个独立的 FP + 两条 data_flow 分支

**关键价值**：每个条件分支至少产出 2 个 lifecycle_scenario（一个走 true 分支，一个走 false 分支）。分支点也是 seam_check 的重点位置。

#### S9 Current Design vs Expected Design — NEW

**识别词**：`Current Design`、`Expected Design`、`currently`、`will be changed to`

**PRD 实例**：
```
Others 1 (Query Services):
  Current Design: LTS calls getAccountInfo → "Available to Spend" = 500
  Expected Design: LC adds "Product Actual Spendable Amount" → 600
```

**提取结果**：
- 新增字段 `Product Actual Spendable Amount` → api_behavior FP
- 旧字段 `Product Actual Available Limit` 仍然存在 → 兼容性 invariant: 两个字段并存
- 变更影响范围：所有依赖 getAccountInfo 的下游（LTS App Display）→ integration dependency
- **回归测试**：旧字段的计算逻辑不能被破坏

**关键价值**：Current vs Expected 暗示了**变更影响分析**。旧逻辑不能被改坏，新逻辑需要兼容旧的，这产出的是回归测试和兼容性测试。

#### S10 API 入参出参表格 — NEW

**PRD 实例**：
```
Overpayment Flow API:
  [input] clientNo; [input] accountNo;
  [output] tran_time, tran_type, tran_amt, previous_available_overpayment...
```

**提取结果**：
- 每个 input 参数 → 参数校验 FP（必填、类型、格式）
- 每个 output 字段 → 数据完整性 FP（字段是否返回、值是否正确）
- input/output 组合 → 接口契约 invariant: 给定输入，输出必须满足某个约束

---

### 7.0.2 图表信号详解

PRD 中的图表往往包含文字中没有明确写出的逻辑。

#### S11 流程图节点+连线

**分析方法**：
```
将每个节点映射为一个 FP 或一个 lifecycle_scenario 的 step；
将每条连线映射为一个 seam_check 或 dependency。
```

**以 Overpayment PRD 中的流程图（image2026-2-27_9-36-42.png）为例**：

如果流程图展示的是 Overpayment Payout Flow：
```
客户购买 → Limit Check → Freeze → [Order Confirm?]
                                      ├── Yes → Create Loan → Direct Repay → Record Flow
                                      └── No  → [Refund?]
                                                  ├── Yes → Unfreeze
                                                  └── No  → Wait
```

**提取**：
- 节点数 = FP 候选数（每个处理步骤可能是一个 FP）
- 连线 = seam_check（A→B 之间的数据传递是否正确）
- 分支 = lifecycle_scenario 的变体（每条路径一个场景）
- **路径总数** = 所有从起点到终点的不同路径 → lifecycle_scenario 的最小数量

#### S12 流程图判断菱形

**分析方法**：
```
每个判断菱形 = 一个 constraint FP + 两侧的 boundary 测试
```

比如 `Application Amount <= SPAAL?`：
- Yes 分支 → positive FP
- No 分支 → negative FP
- 刚好等于 → boundary test_hint
- 超出一分钱 → boundary test_hint

**关键价值**：判断菱形是 boundary test 的直接来源，也是 lifecycle_scenario 分叉点。

#### S13 架构图系统边界

**分析方法**：
```
每两个系统之间的箭头 = 一个 integration FP + 一组接口契约
```

如果架构图展示：
```
Shopee MP → LTS → LC (Loan Core) → CRMS
                    ↓
                Overpayment Account
                    ↓
                Admin Portal
```

**提取**：
- LTS → LC：getAccountInfo API → api_behavior FP + data_flow
- LC → CRMS：获取 Total Credit Limit → 外部依赖，CRMS 不可用时的降级场景
- LC → Overpayment Account：内部数据操作 → data_record FP
- LC → Admin Portal：查询 API → api_behavior FP

**关键价值**：
- 系统边界处天然是 **集成风险** 最高的地方
- 跨系统调用 = seam_check 的必查点
- 外部系统依赖 = 需要考虑异常/超时/重试的 negative 场景

#### S14 时序图调用链

**分析方法**：
```
时序图中每一根箭头 = 一次调用
箭头的顺序 = 调用顺序 invariant
返回箭头 = output 验证点
```

如果存在时序图描述 Checkout 流程：
```
Shopee → LTS: 发起购买
LTS → LC: disbursement pre-check
LC → LC: calculate SPAAL (with EAL)
LC → LTS: pre-check result
LTS → LC: freeze limit
LC → Overpayment: freeze overpayment
LC → LTS: freeze result
```

**提取**：
- 调用顺序：先 pre-check 再 freeze → lifecycle_scenario 的 step 顺序
- 每个返回值 → data_flow 的一跳
- **超时场景**：如果 LC → Overpayment freeze 超时怎么办？→ negative FP
- **部分失败**：freeze limit 成功但 freeze overpayment 失败？→ 事务一致性 invariant

#### S15 状态机图

**分析方法**：
```
每个状态 = 系统的一种合法状态
每个转换 = 一个 workflow FP
非法转换（图中没有的箭头）= negative test case
```

如果存在 Loan 状态机：
```
Active → Earmarked → Used → Paid Off
                 ↘ Refunded (partial)
Active → Frozen → Active (unfreeze)
Used → Fraudulent (dispute true fraud)
Used → Active (dispute false fraud → re-post)
```

**提取**：
- 每个合法转换 → workflow FP
- 不存在的转换（如 Paid Off → Active）→ negative test case
- 同一状态的多个出口 → 条件分支，每个分支一个 lifecycle_scenario

---

### 7.0.3 结构信号详解

#### S16 章节编号层级

**PRD 结构**：
```
3.1 Business Requirements
  3.1.1 General Rules
  3.1.2 Lifecycle
3.2 Loan Core Enhancements
  3.2.1 Extra Available Limit
  3.2.2 Disbursement Pre-check & Trial
  3.2.3 Earmark Concept
  ...
```

**提取**：3.2.x 的每个小节 = 一个 module 候选。章节的并列关系暗示模块之间的 MECE 划分。

#### S17 表格行列结构

**PRD 中的枚举表格**：
```
| Product | Sub-product | Variant    | EAL Amount |
| 813     | 102         | ONE_TERM   | 100        |
| 813     | 102         | MULTI_TERM | 0          |
| 813     | 106         | -          | 100        |
```

**提取**：表格的每一行 = 一个测试数据组合。所有行加起来 = MECE 的完整枚举。
如果测试用例没有覆盖表格中的每一行，就存在遗漏。

#### S18 Yes/No/Pending 标记

**PRD 中每个 Stage 都有标记**：
```
Stage 1: trueRedYes  (需要改造)
Stage 4: trueGreenno (不需要改造)
```

**提取**：
- `Yes` = 需要新开发 → 有对应的 FP（功能变更）
- `No` = 现有逻辑不变 → 但需要回归测试确保不被破坏
- `Pending` = 需求未确定 → 标记为 open question，暂不生成 FP

---

### 7.0.4 信号提取执行清单

每次分析 PRD 时，按以下清单逐项执行：

| Phase | 动作 | 输出 |
|-------|------|------|
| **Phase 1: 通读** | 标记所有公式、变量名、阶段编号 | 候选 invariants, data entities, stages |
| **Phase 2: 图表分析** | 逐个分析流程图/架构图/时序图/状态机 | 补充 lifecycle paths, system boundaries, state transitions |
| **Phase 3: 文本扫描** | 扫描交叉引用词、时序词、否定词、条件分支、Current vs Expected | 补充 dependencies, constraints, regression scope |
| **Phase 4: 表格提取** | 提取所有枚举表格和 API 入参出参 | 补充 MECE coverage, api_behavior FPs |
| **Phase 5: 关联组装** | 将 Phase 1-4 的结果组装为 data_flows + invariants + lifecycle_scenarios | 完整的关联层 |
| **Phase 6: 缺口检查** | 检查是否有数据实体无 data_flow、状态变更无 invariant、主路径无 scenario | 补漏 |

---

## 7.1 问题（保持原有内容）

### 7.1 问题

单个 FP 是原子的，但需求不是。以 Overpayment 为例：

```
FP-EAL-005.1 计算 EAL=$100
       ↓ 这个 $100 传到哪去了？
FP-DSB-006.1 检查 SPAAL=$600
       ↓ 检查通过后呢？
FP-EMK-007.1 冻结 Earmarked Overpayment=$100
       ↓ 冻结后的 $100 怎么用？
FP-LOAN-010.1 直接还款 $100
       ↓ 还完以后？
FP-OPF-020.1 写流水记录
```

如果只看 FP-EMK-007.1（冻结），测试工程师不知道冻结的 $100 是从哪来的、之后会怎么用。
仅靠 `dependencies` / `affects` 字段只能描述直接的两两关系，看不到全链路。

### 7.2 三层关联结构

在 `function_point_template.yaml` 中，FP 列表之后新增三个顶层结构：

```
modules:
  └── function_points[]     ← 原子级功能点（点）

data_flows[]                ← 数据流链（线）—— 追踪关键数据的全链路流转
invariants[]                ← 全局不变量（面）—— 跨 FP 始终成立的约束
lifecycle_scenarios[]       ← 生命周期场景（路径）—— 端到端业务路径
```

#### 7.2.1 数据流 (Data Flows)

**解决的问题**：一个关键数据实体（如 Overpayment Amount）在多个 FP 之间传递，
单看任何一个 FP 都不知道上游给了什么、下游期望什么。

**结构**：

```yaml
data_flows:
  - id: "DF-001"
    entity: "Overpayment Amount"        # 被追踪的数据实体
    flow_path:                           # 按时间顺序的流转路径
      - fp_id: "FP-EAL-005.1"
        role: "input"                    # input / output / transform / check
        field: "Overpayment Amount"
        state_change: "..."              # 该 FP 对这个数据做了什么
      - fp_id: "FP-EMK-007.1"
        role: "transform"
        state_change: "Available → Earmarked"
    integration_test_hints:              # 基于整条链产出的集成测试点
      - "验证上游输出 = 下游输入"
```

**使用方式**：
- 拆分 FP 时：检查每个关键数据实体是否有完整的 data_flow
- 生成用例时：data_flow 的 `integration_test_hints` 直接产出集成测试用例
- 审查时：检查 flow_path 中相邻两个 FP 的值是否一致

#### 7.2.2 全局不变量 (Invariants)

**解决的问题**：有些约束不属于任何一个 FP，而是「无论做什么操作，这个等式都必须成立」。
如果没有显式声明，测试工程师很容易只验证单步结果而忽略全局一致性。

**结构**：

```yaml
invariants:
  - id: "INV-001"
    title: "额度守恒"
    formula: "PAL = Total - Used - Frozen - Earmarked"
    check_after_fps: ["FP-EMK-007.1", "FP-LOAN-010.1"]  # 哪些 FP 执行后需要检查
    severity: "P0"
    test_hint: "每个关键步骤后查询 PAL 验证公式"
```

**使用方式**：
- 拆分 FP 时：每定义一个会改变状态的 FP，检查是否影响某个 invariant
- 生成用例时：每个 invariant 产出 N 条校验用例（N = check_after_fps 的数量）
- 常见不变量类型：
  - 金额守恒（总量 = 各分量之和）
  - 状态互斥（不能同时处于两个状态）
  - 数据一致性（A 表字段 = B 表字段）
  - 流水完整性（每次变化都有记录）

#### 7.2.3 生命周期场景 (Lifecycle Scenarios)

**解决的问题**：FP 是静态的点，但业务是动态的路径。
同样的 FP 组合，不同执行顺序会产生不同结果。
比如「先退款再确认」和「先确认再退款」走的是完全不同的逻辑。

**结构**：

```yaml
lifecycle_scenarios:
  - id: "LS-001"
    title: "Happy Path: 购买→冻结→确认→还款"
    steps:
      - order: 1
        fp_id: "FP-EAL-005.1"
        action: "计算 EAL"
        state_snapshot: { ... }         # 该步骤执行后的完整状态快照
      - order: 2
        fp_id: "FP-EMK-007.1"
        action: "冻结"
        state_snapshot: { ... }

    seam_checks:                         # 接缝检查：相邻 FP 之间的衔接验证
      - between: ["FP-EAL-005.1", "FP-DSB-006.1"]
        check: "SPAAL 在 Pre-check 中被正确引用"

    invariant_checks: ["INV-001", "INV-002"]  # 该场景需要验证哪些不变量
```

**关键概念——接缝检查 (Seam Check)**：

两个 FP 各自都对的，但拼在一起可能出错。接缝检查专门验证：
- FP-A 的输出格式/精度 是否满足 FP-B 的输入要求
- FP-A 执行后的状态 是否满足 FP-B 的前置条件
- FP-A → FP-B 之间是否有并发/时序风险

### 7.3 三层结构如何协作产出测试用例

```
第一层：原子用例（来自单个 FP 的 test_hints）
  FP-EAL-005.1 → TC: EAL=$100, EAL=0 (boundary) ...
  FP-EMK-007.1 → TC: 冻结成功, 冻结金额不足 ...

第二层：集成用例（来自 data_flows 的 integration_test_hints）
  DF-001 → TC: Overpayment 从 EAL 到 Earmark 到还款的全链路数值一致性
  DF-002 → TC: Available Limit 在每个阶段的守恒验证

第三层：E2E 用例（来自 lifecycle_scenarios）
  LS-001 → TC: Happy Path 端到端（含每步 state_snapshot 断言 + seam_checks）
  LS-002 → TC: 含退款路径的端到端

第四层：不变量用例（来自 invariants）
  INV-001 → TC: 在 Checkout/Confirm/Refund 后分别验证额度守恒公式
  INV-002 → TC: 在每次 Overpayment 变动后验证总量等式
```

### 7.4 拆分 FP 时的关联性检查清单

每完成一个 FP 的拆分，执行以下检查：

| # | 检查项 | 动作 |
|---|--------|------|
| 1 | 该 FP 的输出是否被其他 FP 使用？ | 是 → 添加到对应 data_flow |
| 2 | 该 FP 是否改变了共享状态？ | 是 → 检查是否影响某个 invariant，加入 check_after_fps |
| 3 | 该 FP 是否属于某个端到端路径？ | 是 → 加入对应 lifecycle_scenario 的 steps |
| 4 | 该 FP 与前后 FP 的接缝是否安全？ | 添加 seam_check |
| 5 | 该 FP 有并发/时序风险吗？ | 是 → 在 lifecycle_scenario 中标注 |

## 8. 质量门禁

### 8.1 原子层 (FP 级别)

| 检查项 | 标准 |
|--------|------|
| 每个 REQ 至少有 1 个 FP | 100% |
| 每个 FP 有 test_hints 三维度 | positive + negative 必填，boundary 视情况 |
| FP 之间无内容重叠 | 人工审核 |
| P0 需求的 FP 必须有 business_rules | 100% |
| 同一模块内 FP 编号连续 | 自动检查 |

### 8.2 关联层 (全局级别)

| 检查项 | 标准 |
|--------|------|
| 每个涉及金额的数据实体有 data_flow | 100% |
| 每个会改变共享状态的 FP 出现在至少一个 invariant 的 check_after_fps 中 | 100% |
| P0 需求涉及的主流程有对应的 lifecycle_scenario | 100% |
| 每个 lifecycle_scenario 的相邻步骤有 seam_check | >= 80% |
| data_flow 中相邻 FP 的输出类型/精度与下游输入匹配 | 100% |
