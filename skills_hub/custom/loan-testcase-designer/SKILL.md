---
name: 用例设计师
description: DBP借贷测试用例设计工具。基于功能点(FP)生成结构化测试用例，支持Case ID管理、XMind导出、覆盖率检测和需求追溯矩阵。当用户需要生成测试用例、导出XMind、检测覆盖率、生成追溯矩阵时使用。
---

# DBP 借贷用例设计师

你是一个资深的测试设计工程师，负责基于功能点 (FP) 设计和生成高质量测试用例。

---

## 一、概述

### 1.1 职责边界

```
本 Skill 负责                          不负责（由 loan-requirement-analyzer 完成）
─────────────────────────              ──────────────────────────────────────
✅ 测试用例生成                         ❌ Confluence 需求获取
✅ Case ID 管理                        ❌ 需求清单提取 (REQ)
✅ XMind 导出                          ❌ 功能点拆分 (FP)
✅ 覆盖率检测                           ❌ 18 类信号识别
✅ 需求追溯矩阵 (REQ↔FP↔TC)            ❌ 关联层构建
✅ 版本管理（影子目录同步）
```

### 1.2 与上游 Skill 的衔接

本 Skill 消费 **loan-requirement-analyzer** 产出的功能点文件。

```
[dbp-loan-requirement-analyzer]          [dbp-loan-testcase-designer]
        ↓ 产出                                   ↓ 消费
  FunctionPoints.yaml  ──────────────→  用例生成 → TestCases.yaml
  FunctionPoints.md    ──────────────→  (评审确认后开始)
  requirements.md      ──────────────→  需求来源追溯 → traceability_matrix.md
```

**前置条件**：

1. `<项目名称>_FunctionPoints.yaml` 必须存在且符合 schema
2. 每个 FP 必须有 `test_hints` 字段
3. `data_flows` / `invariants` / `lifecycle_scenarios` 必须存在
4. requirements.md 必须存在（用于追溯）

**文件传递方式**：
- 在提示词中指定上游文件的完整路径

### 1.3 目录结构

```
.cursor/skills/custom/dbp-loan-testcase-designer/
├── SKILL.md                    # 本文档（入口）
├── __init__.py
├── scripts/                    # 工具脚本
│   ├── yaml_to_xmind.py        # YAML 转 XMind
│   ├── coverage_checker.py     # 覆盖率检测
│   ├── case_id_manager.py      # Case ID 管理
│   ├── add_case_ids_to_testcases.py  # 批量添加 Case ID
│   ├── run_traceability.sh     # 追溯矩阵脚本
│   ├── config.py               # 配置加载模块
│   ├── config.yaml             # 脚本配置
│   └── __init__.py
├── config/                     # 配置文件
│   ├── config.yaml             # 连接配置
│   └── domains.yaml            # 业务域配置
├── templates/                  # 模板文件
│   ├── case_model.yaml         # 用例格式模板
│   └── function_point_template.yaml  # 功能点 YAML schema（参考）
└── references/                 # 参考资料
    ├── README.md
    └── case_registry/          # Case ID 注册表
        └── case_id_registry.yaml

case_workspace/                  # 项目工作区（所有项目数据统一存放）
└── <版本号>/
    └── <JIRA单号>-<项目名称>/
        ├── requirements/              # 需求文档（来自 requirement-analyzer）
        │   ├── <需求文档>_requirements.md
        │   └── images/
        ├── analysis/                  # 分析产物（来自 requirement-analyzer）
        │   └── <项目名称>_FunctionPoints.yaml  ← 输入
        ├── testcases/                 # 测试用例（本 Skill 产出）
        │   ├── <项目名称>_TestCases.yaml        ← 输出
        │   ├── <项目名称>_TestCases.xmind       ← 输出
        │   └── *_traceability_matrix.md         ← 输出
        └── .history/                  # 历史版本
```

### 1.4 路径变量

```bash
SKILL_DIR=".cursor/skills/custom/dbp-loan-testcase-designer"
WORKSPACE="case_workspace"
PROJECT_DIR="$WORKSPACE/<版本号>/<JIRA单号>-<项目名称>"
```

---

## 二、工作流程

```
FunctionPoints.yaml → 用例生成(TC) → Case ID → 覆盖检测 → 追溯矩阵 → XMind导出
         ↑                                ↓                                   ↓
  来自 requirement-analyzer          TestCases.yaml                    同步到影子目录
```

**输入**（来自上游 `dbp-loan-requirement-analyzer` 的产出）：

| 文件 | 说明 |
|------|------|
| `<项目名称>_FunctionPoints.yaml` | 功能点定义（含 test_hints + 关联层） |
| `<需求文档>_requirements.md` | 需求清单（用于追溯） |
| `<需求文档>.md` | 原始需求文档（用于参考） |

---

## 三、用例格式规范

> **用例格式模板**: [templates/case_model.yaml](templates/case_model.yaml)

### 3.0 YAML 格式 Schema

```yaml
project:
  name: "项目名称"           # 对应 XMind 根节点
  version: "LOAN_v8.0.0"    # 版本号
  jira: "XXXX-XXXXX"       # JIRA 单号
  total_cases: N             # 总用例数

project_analysis:
  background: "需求背景描述"
  prd:
    - label: "【BE】"
      url: "https://..."
  design:
    - label: "【模块名】"
      url: "https://..."
  test_plan: "https://..."
  key_changes: ["改造点1", "改造点2"]
  test_focus: "测试关注点"
  test_strategy: ["验证范围：...", "不验证模块：..."]
  test_preparation: "测试准备描述"

modules:
  - name: "业务场景A"
    total_cases: N
    function_points:
      - title: "功能点标题"
        cases:
          - id: "TC-XXX-正向"           # 用例标识
            title: "用例标题"
            precondition:               # 字符串 或 列表
              - "条件一"
              - "条件二"
            steps:                      # 字符串 或 列表
              - "步骤一"
              - "步骤二"
            expected:                   # 字符串 或 列表
              - "结果一"
              - "结果二"
            priority: "P0"
            case_id: "SPBC_CHECK_A1B20001"
            req_source: "REQ-005【需求原文...】"   # 字符串 或 列表
            fp_source: "FP-EAL-005.1"              # 字符串 或 列表
            tags: ["AI-GEN", "FundLoss"]           # 标签列表
```

### 3.1 完整示例

以 Extra Available Limit 为例：

```yaml
project:
  name: "Overpayment Available to Spend"
  version: "LOAN_v7.0.22_20260403"
  jira: "XXXX-XXXXX"
  total_cases: 4

project_analysis:
  background: "随着业务增长，需要支持Overpayment金额作为Available to Spend..."
  prd:
    - label: "【BE】"
      url: "..."
  design:
    - label: "【放款】"
      url: "..."
  key_changes:
    - "Extra Available Limit 新增计算逻辑"
    - "放款流程增加EAL校验"
  test_focus: "EAL计算精度、放款与还款联动"

modules:
  - name: "Extra Available Limit"
    total_cases: 2
    function_points:
      - title: "102 ONE_TERM Extra Available Limit 等于 Overpayment Amount"
        cases:
          - id: "TC-EAL-005.1-正向"
            title: "Overpayment=$100时102 ONE_TERM EAL=$100"
            precondition:
              - "用户持有102 ONE_TERM子产品"
              - "账户状态正常"
            steps:
              - "设置用户Overpayment=$100"
              - "查询102 ONE_TERM Extra Available Limit"
            expected:
              - "EAL=$100"
              - "等于Overpayment Amount"
            priority: "P0"
            case_id: "SPBC_CHECK_E0510001"
            req_source: "REQ-005【Extra Available Limit (newly created)...】"
            fp_source: "FP-EAL-005.1"
            tags: ["AI-GEN", "FundLoss"]

          - id: "TC-EAL-005.1-边界"
            title: "Overpayment极大值时EAL精度验证"
            precondition:
              - "用户持有102 ONE_TERM子产品"
              - "账户状态正常"
            steps:
              - "设置用户Overpayment=999999999.99"
              - "查询102 ONE_TERM EAL"
            expected:
              - "EAL=999999999.99"
              - "精度不丢失"
            priority: "P2"
            case_id: "SPBC_CHECK_E0510003"
            req_source: "REQ-005【Extra Available Limit (newly created)...】"
            fp_source: "FP-EAL-005.1"
            tags: ["AI-GEN", "FundLoss"]

  - name: "Repayment"
    total_cases: 2
    function_points:
      - title: "还款触发Overpayment金额更新"
        cases:
          - id: "TC-RPY-010.1-正向"
            title: "正常还款后Overpayment增加"
            precondition:
              - "用户有活跃贷款"
              - "还款金额超过应还金额"
            steps:
              - "用户发起还款$200"
              - "查询Overpayment金额"
            expected:
              - "Overpayment金额增加$200"
            priority: "P0"
            case_id: "SPBC_REPAY_R0100001"
            req_source: "REQ-010【Repayment triggers overpayment update...】"
            fp_source: "FP-RPY-010.1"
            tags: ["AI-GEN", "FundLoss"]

          - id: "TC-RPY-010.1-幂等"
            title: "重复还款请求不产生重复Overpayment"
            precondition:
              - "用户有活跃贷款"
            steps:
              - "发送相同还款请求2次"
              - "查询Overpayment金额"
            expected:
              - "Overpayment仅增加一次"
              - "第二次请求返回幂等响应"
            priority: "P1"
            case_id: "SPBC_REPAY_R0100002"
            req_source: "REQ-010【Repayment triggers overpayment update...】"
            fp_source: "FP-RPY-010.1"
            tags: ["AI-GEN", "FundLoss"]
```

> **注意**：`FP-EAL-005.1` 是 `calculation` 类型，选择了「正向 + 边界」；`FP-RPY-010.1` 是 `workflow` 类型，选择了「正向 + 幂等」，体现了按 FP type 差异化选择覆盖类型的策略。

### 3.2 模块组织策略（按业务场景）

> **核心原则**：`modules` 按**业务场景**维度组织，而非按功能模块(FP module)维度。

**组织规则**：

1. **业务场景优先**：按用户使用的业务流程/场景划分模块（如 NTB 定价测试、ETB 批量定价测试），而非按技术功能域（如 Data Model、API）
2. **通用能力独立**：跨场景共享的能力（如定价选择逻辑、数据约束、写入接口）作为独立模块
3. **E2E/不变量融入场景**：来自 `lifecycle_scenarios` 和 `invariants` 的用例**不独立成模块**，而是分配到对应的业务场景模块中。仅 **E2E 生命周期用例**（lifecycle_scenarios）标记为 `[基线]`（P0）；`invariants` 类用例（数据一致性、防御性约束等）不标基线，按判定矩阵正常定级
4. **基线用例规则**：
   - 功能点标题以 `[基线]` 前缀，如 `[基线] NTB完整生命周期: 开户→锁定→放款→过期→回退PC`
   - 用例名称使用 `基线` 标识，如 `TC-LS-001-基线`
   - 基线用例必须为 **P0 等级**
   - 每个业务场景模块至少包含 1 条基线用例（验证该场景的端到端链路）
5. **模块命名**：使用业务语言而非技术术语，如"NTB 定价测试"而非"NTB/NTP Real-time Flow"

**典型模块结构**：

| 模块类型 | 示例 | 来源 |
|----------|------|------|
| 业务场景 | NTB 定价测试、ETB 批量定价测试 | FP 中的业务流程 + lifecycle_scenarios |
| 通用能力 | 定价选择与Drawdown、数据约束与唯一性 | FP 中的共享逻辑 + invariants |
| 接口能力 | 锁定定价写入接口 | FP 中的 api_behavior |
| 运营能力 | 活动管理与失效 | FP 中的 workflow/integration |

### 3.3 格式约束

**YAML 结构约束**：

- `project` 必须包含 `name`、`total_cases`（生成完成后填写实际值）
- `project_analysis` 必须作为第一个顶层节点，不计入用例统计
- `modules` 按业务场景划分，每个 module 必须包含 `name`、`total_cases`
- 每个 `function_points[].cases[]` 必须包含以下字段：`id`、`title`、`precondition`、`steps`、`expected`、`priority`、`case_id`、`req_source`、`fp_source`、`tags`
- `precondition` / `steps` / `expected` 推荐使用列表写法（每项一个步骤），也支持字符串写法
- `req_source` / `fp_source` 支持字符串或列表（多个需求/功能点时使用列表）

**内容约束**：

- 测试用例**直接挂在功能点下**，不需要「正向测试/异常测试/边界测试」等分组节点（测试类型已编码在 `id` 中，如 `TC-XXX-正向`、`TC-XXX-异常`、`TC-XXX-边界`、`TC-XXX-基线`）
- **`case_id` 格式**：`{业务域}_{功能}_{hash4位}{序列号4位}`
- **`req_source` 格式**：`REQ-编号【需求原文】`
- **`fp_source` 格式**：`FP-编号`
- **`tags` 为列表**：AI 生成的用例包含 `AI-GEN`，涉及资金安全的用例追加 `FundLoss`，如 `["AI-GEN", "FundLoss"]`
- **`priority` 按 Section 4.1 判定矩阵确定**，禁止所有用例统一标 P0
- **`project_analysis` 内容来源**：`background` 从 PRD 提取；`prd`/`design`/`test_plan` 的 URL 由用户提供；`key_changes` 从 FP module 列表精炼核心关键点（不罗列全部）；`test_strategy` 提供推导框架，主要由人工填写

### 3.4 输出位置

- 主文件: `case_workspace/<版本号>/<JIRA单号>-<项目名称>/testcases/<项目名称>_TestCases.yaml`
- XMind: `case_workspace/<版本号>/<JIRA单号>-<项目名称>/testcases/<项目名称>_TestCases.xmind`
- 历史版本: `case_workspace/<版本号>/<JIRA单号>-<项目名称>/.history/<项目名称>_TestCases_v<N>.yaml`

---

## 四、用例设计方法（按覆盖类型）

### 4.0 覆盖类型选择策略

> **核心原则**：按 FP 的 `type` 和业务特征选择最有价值的覆盖类型，**禁止机械地为每个 FP 统一生成正向/异常/边界三板斧**。

**按 FP type 推荐覆盖类型**：

| FP type | 必选 | 推荐策略 | 不推荐 |
|---------|------|--------------|--------|
| `calculation` | 功能(正向) | 边界值、等价类 | 可观测性 |
| `constraint` | 功能(正向) | 异常(违反约束) | 边界(常无意义) |
| `workflow` | 功能(正向) | 场景分支、幂等/并发 | 边界(常无意义) |
| `api_behavior` | 功能(正向) | 接口(参数/响应/状态码)、并发/幂等 | 可观测性 |
| `data_record` | 功能(正向) | 可观测性(字段完整性)、边界(精度/长度/分片)、并发(乐观锁) | - |
| `config` | 功能(正向) | 兼容性(配置变更/多环境) | 并发 |
| `display` | 功能(正向) | 边界(格式/精度)、异常(无数据) | 幂等性 |

**生成规则**：

1. **每个 FP 至少 2 条用例**：正向必选 + 按上表选最有价值的覆盖类型
2. **禁止伪边界**：若该 FP 无真实数值范围或长度限制，不生成边界用例
3. **禁止冗余覆盖**：若 FP-A 的异常用例与 FP-B 的正向用例验证同一行为，仅保留其中一条
4. **跨 FP 覆盖类型互补**：同一模块内不同 FP 的覆盖类型应互补而非重复
5. **E2E/不变量用例融入业务场景模块**：仅 `lifecycle_scenarios` 的 E2E 用例标记为 `[基线]`（P0）；`invariants` 用例（数据一致性、幂等性、防御性约束等）不标基线，按 Section 4.1.4 分配指导和判定矩阵定级

**用例命名中的类型标识**：

| 标识 | 对应覆盖类型 |
|------|-------------|
| `正向` | 功能测试 (functional) |
| `异常` | 异常测试 (negative) |
| `边界` | 边界测试 (boundary) |
| `幂等` | 幂等性测试 (idempotency) |
| `并发` | 并发测试 (concurrency) |
| `可观测` | 可观测性测试 (observability) |
| `兼容` | 兼容性测试 (compatibility) |
| `场景` | 场景测试 (scenario) |
| `基线` | 基线场景 (baseline) — 仅 E2E 生命周期场景验证，P0 |

### 4.1 用例等级定义与判定

> **核心原则**：用例等级由 **FP priority × 覆盖类型** 双维度交叉决定，而非简单继承 FP priority。

#### 4.1.1 等级定义

| 等级 | 含义 | 回归策略 | 预期占比 |
|------|------|---------|---------|
| **P0** | 核心链路 — 功能不可用或数据错误直接导致资损/业务阻塞 | 每次发版必测 | 15%-25% |
| **P1** | 重要功能 — 主流程的关键分支或核心约束，出错影响较大 | 每个迭代测试 | 20%-40% |
| **P2** | 一般功能 — 辅助功能、次要路径、异常容错、边界补充 | 按需测试/里程碑测试 | 20%-35% |

#### 4.1.2 判定矩阵（FP priority × 覆盖类型）

| FP priority | 正向/基线/幂等 | 并发/场景 | 异常/边界/可观测/兼容 |
|-------------|--------------|----------|---------------------|
| **P0** | **P0** | **P1** | **P2** |
| **P1** | **P1** | **P2** | **P2** |
| **P2** | **P2** | **P2** | **P2** |

#### 4.1.3 特殊升降级规则

| 规则 | 调整 | 说明 |
|------|------|------|
| `[基线]` 标记 | **强制 P0** | 仅 **E2E 生命周期场景**（lifecycle_scenarios）标基线且强制 P0；数据一致性不变量、防御性约束校验等不标基线，按判定矩阵定级 |
| 资金处理类 (FundLoss) + 正向覆盖 | **升一级** | 仅对**正向/基线**覆盖类型的 FundLoss 用例升级；异常/边界等覆盖类型不升级 |
| 需求级别 MAY | **降一级** | 非必须需求的用例优先级下调 |

#### 4.1.4 用例等级精细化指导

> **核心原则**：P0 仅覆盖核心业务主链路和幂等性保障，验证性/防御性/完整性检查均为 P1。生成用例后须执行冗余覆盖检查，去除重复的 P0。

##### 4.1.4.1 P0 聚焦范围

> P0 是最小必测集，仅以下类别纳入 P0：

| P0 类别 | 含义 | 示例 |
|---------|------|------|
| 核心业务流程正向 | 写入/定价选择/放款集成/状态流转的主路径 | 锁定写入成功、定价优先级、放款利率校验、MQ 创建/关闭活动 |
| E2E 生命周期基线 | `lifecycle_scenarios` 端到端场景，标记 `[基线]` | NTB/NTP/ETB 完整生命周期 |
| 唯一性约束核心正向 | 数据唯一性/排他性的核心保障用例 | 时间重叠记录被丢弃 |
| 幂等性验证 | 重复操作不产生副作用 | 重复调用返回一致、数据不重复写入 |

##### 4.1.4.2 P1 类别清单

> 以下类别明确**不纳入 P0**，按判定矩阵从 P1 起分配：

| P1 类别 | 含义 | 示例 |
|---------|------|------|
| 不可变性验证 | 写入后字段不可修改的防御性检查 | 修改 endDate 被拒绝 |
| 双表/字段完整性 | 多表全字段存储正确性验证 | 策略表+客户表全字段验证 |
| 数据一致性校验 | 跨表状态同步、写入后唯一性事后验证 | 策略表与客户表状态一致 |
| 活动交叠/约束检查 | 业务约束的正向与反向验证 | 交叠丢弃、不交叠写入 |
| 参数校验/输入验证 | 输入合法性的防御性检查 | 客户/产品不存在报错、日期无效报错 |
| 状态前置校验/防御性报错 | 操作前状态条件不满足的报错 | 已失效策略报错、状态不可逆 |
| 并发验证 | 多线程/多请求竞争处理 | 并发串行处理、乐观锁冲突 |
| 辅助功能 | 非核心路径的补充功能（P1-P2） | 默认值处理、影响记录计数 |

##### 4.1.4.3 P0 冗余覆盖降级规则

> 即使某用例按 4.1.4.1 属于 P0 类别，若触发以下冗余规则，应降为 P1：

| 降级规则 | 判定条件 | 示例 |
|---------|---------|------|
| **E2E 基线已覆盖** | 原子用例的验证点已被同模块 E2E 基线的某个步骤覆盖 | "NTB 实时生效"被"NTB 完整生命周期基线"步骤 2 覆盖 |
| **同行为多入口** | 两个 P0 用例验证相同业务行为，仅触发入口不同 → 保留核心入口为 P0 | "试算回退 PC"与"Drawdown 回退 PC"验证同一回退逻辑 |
| **约束互补对的次要方** | 约束类"拒绝+放行"成对出现时，核心保障是拒绝方 → 放行方降 P1 | "无重叠正常写入"相对于"重叠记录被丢弃" |
| **状态验证与选择验证重叠** | ACTIVE 状态参与定价选择的验证已被"锁定优先级"用例覆盖 | "ACTIVE 参与定价选择"与"有锁定记录返回锁定定价" |

#### 4.1.5 标签体系

标签用于标记用例的特殊属性，YAML 中为 `tags` 列表：

| 标签 | 含义 | 标记条件 |
|------|------|---------|
| `AI-GEN` | AI 生成的用例 | 所有由 AI 生成的用例 |
| `MANUAL` | 人工补充的用例 | 人工编写或修改的用例 |
| `FundLoss` | 资金损失风险 | 涉及金额计算、利率计算、额度变更的用例 |

**FundLoss 标记规则**（仅标记直接影响资金正确性的用例）：
- 涉及金额计算的正确性验证 → 标记 FundLoss
- 涉及利率计算/精度验证（如利率值比对、decimal 精度） → 标记 FundLoss
- 涉及额度变更（冻结/释放/扣减） → 标记 FundLoss
- 定价选择逻辑、写入流程、状态管理、MQ事件、参数校验、文件处理 → **不标记**

**多标签格式**：`tags: ["AI-GEN", "FundLoss"]`

### 4.2 功能测试 (functional)

**正向用例设计**

采用等价类划分和判定表技术：

```yaml
- id: "TC-[模块]-[功能]-[序号]-正向"
  title: "[动作] + [对象] + [预期结果]"
  precondition:
    - "前提条件一"
    - "前提条件二"
  steps:
    - "[操作1]"
    - "[操作2]"
  expected:
    - "明确、可验证的结果一"
    - "明确、可验证的结果二"
  priority: "P0"
  case_id: "SPBC_CHECK_A1B20001"
  req_source: "REQ-001【需求原文】"
  fp_source: "FP-XXX-001.1"
  tags: ["AI-GEN"]
```

**业务流程用例**

设计端到端场景：

- 主流程（Happy Path）
- 分支流程（Alternative Path）
- 组合流程（多功能串联）

### 4.3 异常测试 (negative)

覆盖以下异常类型：

| 异常类型 | 设计方法 | 示例 |
|----------|----------|------|
| 无效输入 | 非法字符、格式错误 | 邮箱格式错误 |
| 缺失输入 | 必填项为空 | 用户名为空 |
| 越界输入 | 超出范围值 | 金额为负数 |
| 状态异常 | 非法状态转换 | 已取消订单再次取消 |
| 依赖异常 | 外部服务失败 | 支付网关超时 |
| 资源异常 | 数据不存在或被占用 | 订单已被他人修改 |

### 4.4 边界测试 (boundary)

应用边界值分析：

```
对于范围 [min, max]:
- 边界点: min, max
- 边界内: min+1, max-1
- 边界外: min-1, max+1
- 特殊值: 0, null, 空字符串
```

常见边界场景：

- 字符串长度边界
- 数值范围边界
- 日期时间边界
- 数量限制边界
- 分页边界

### 4.5 权限测试 (permission)

权限矩阵:

| 功能 | 游客 | 普通用户 | 管理员 | 超级管理员 |
|------|------|----------|--------|------------|
| 查看 | ✓    | ✓        | ✓      | ✓          |
| 创建 | ✗    | ✓        | ✓      | ✓          |
| 编辑 | ✗    | 自己     | 全部   | 全部       |
| 删除 | ✗    | ✗        | 部分   | 全部       |

覆盖场景：

- 未登录访问
- 越权操作（水平/垂直）
- Token 过期
- 角色变更后的权限更新

### 4.6 幂等性测试 (idempotency)

```
幂等性验证模板:
1. 执行操作 A，记录结果 R1
2. 再次执行相同操作 A
3. 验证结果 R2 = R1（或符合幂等预期）
4. 验证系统状态无副作用
```

关键场景：

- 重复提交表单
- 接口重试
- 消息重复消费
- 定时任务重复触发

### 4.7 并发测试 (concurrency)

```
并发场景模板:
- 并发数: N (建议 2, 10, 100, 1000)
- 操作类型: 读/写/混合
- 资源竞争点: [具体资源]
- 预期行为: [一致性要求]
```

覆盖场景：

- 同一资源并发修改
- 库存/余额扣减
- 分布式锁竞争
- 乐观锁冲突处理

### 4.8 可观测性测试 (observability)

```
可观测性验证:
- 日志: 关键操作是否记录
- 指标: Metrics 是否上报
- 链路: TraceID 是否串联
- 告警: 异常是否触发告警
```

### 4.9 兼容性测试 (compatibility)

兼容性矩阵:

| 维度 | 覆盖范围 |
|------|----------|
| 浏览器 | Chrome/Firefox/Safari/Edge |
| 设备 | Desktop/Mobile/Tablet |
| 系统 | Windows/macOS/iOS/Android |
| 版本 | 当前版本 vs 历史版本 |
| 网络 | 4G/5G/WiFi/弱网 |

### 4.10 场景测试 (scenario)

覆盖完整业务流程，验证多步骤串联后的最终状态：

```
场景用例模板:
- 主流程 (Happy Path): 正常业务流的完整链路
- 分支流程 (Alternative Path): 业务中的条件分支
- 组合流程: 多个功能模块串联（如 授信→放款→还款→结清）
- 回归流程: 涉及状态回退的场景（如 退款后再放款）
```

关键场景：

- 端到端完整生命周期（从创建到结束）
- 跨模块联动（上游输出作为下游输入）
- 异常恢复后的后续流程
- 多次循环操作（如循环放款-还款）

### 4.11 接口测试 (api)

针对 API 的输入输出验证：

```
接口测试模板:
- 请求方法: GET/POST/PUT/DELETE
- 请求参数: 必填/选填/类型/格式
- 响应结构: 字段完整性/类型/默认值
- 状态码: 200/400/401/403/404/500
```

覆盖场景：

- 参数校验（缺失、类型错误、格式不合法）
- 响应字段完整性和准确性
- 接口幂等性（POST 重复调用）
- 分页/排序/过滤逻辑
- 超时与重试机制

### 4.12 覆盖范围总览

| 覆盖类型 | 关注点 |
|----------|--------|
| 功能测试 | 核心业务逻辑 |
| 场景测试 | 端到端业务流程 |
| 接口测试 | API 输入输出验证 |
| 边界测试 | 参数边界值 |
| 异常测试 | 错误处理与容错 |
| 权限测试 | 角色与权限控制 |
| 幂等性测试 | 重复操作无副作用 |
| 并发测试 | 多线程资源竞争 |
| 可观测性测试 | 日志/指标/链路/告警 |
| 兼容性测试 | 多市场/多版本/多环境适配 |

---

## 五、Case ID 管理

### 5.1 格式

```
{业务域前缀}_{功能类型}_{hash4位}{序列号4位}
```

**示例**: `CHL_TRIAL_A1B20001` - 渠道贷试算用例，内容哈希 A1B2，该分组第1个

### 5.2 业务域前缀

| 前缀 | 业务域 | 接口路径模式 |
|------|--------|-------------|
| `CHL` | 渠道贷 | `/channel/`, `/channeling/` |
| `SPSC` | 自营个人标准现金贷 | `/self-operated/personal/standard/cash/` |
| `SESC` | 自营企业标准现金贷 | `/self-operated/enterprise/` |
| `SPBC` | 自营个人账单消费贷 | `/self-operated/personal/bill/` |
| `COMM` | 公共模块 | `/common/`, `/portal/` |

### 5.3 功能类型

| 类型 | 关键词 |
|------|--------|
| `REPAY` | repay, repayment, 还款 |
| `DRAW` | draw, drawdown, disburse, 支用, 放款 |
| `TRIAL` | trial, 试算 |
| `QUERY` | query, get, list, 查询 |
| `ACCT` | account, open, 账户, 开户 |
| `WAIVE` | waive, 减免 |
| `REVERSE` | reverse, 冲正 |
| `SETTLE` | settle, 结清 |
| `CHECK` | check, precheck, 校验 |
| `UPDATE` | update, modify, 更新 |
| `OTHER` | 其他 |

### 5.4 相似度复用规则

- **阈值**: 90%
- **复用逻辑**: 新用例与已有用例相似度 >= 90% 时，复用已有 Case ID
- **特征提取**: 基于接口路径、用例标题、关键词计算相似度

### 5.5 使用方法

```python
from scripts.case_id_manager import CaseIdManager

manager = CaseIdManager()

case_info = {
    "title": "clientNo参数缺失校验",
    "test_steps": "1、调用API 2、请求参数中不传clientNo字段",
    "expected_result": "1、API返回错误码",
    "api_path": "/v1/channel/personal/standard/debt/trialRepayment"
}
case_id, is_new = manager.get_or_create_case_id(case_info)
```

### 5.6 命令行工具

```bash
SKILL_DIR=".cursor/skills/custom/dbp-loan-testcase-designer"

# 查看统计信息
python3 $SKILL_DIR/scripts/case_id_manager.py --stats

# 列出所有 Case ID
python3 $SKILL_DIR/scripts/case_id_manager.py --list

# 按业务域筛选
python3 $SKILL_DIR/scripts/case_id_manager.py --list --domain channel_loan
```

---

## 六、执行步骤

### Step 1: 生成项目分析

> **输入**: 用户提供的 PRD URL、概要设计 URL、测试方案 URL、`<项目名称>_FunctionPoints.yaml`

在测试用例之前生成「项目分析」区块，作为 YAML 中 `project_analysis` 字段：

1. **需求背景**: 从 PRD 提取 1-3 句核心业务背景
2. **需求PRD**: 用户提供的 PRD Confluence URL，格式 `【端/模块】<URL>`
3. **概要设计**: 用户提供的设计文档 URL，格式 `【模块名】<URL>`
4. **测试方案**: 用户提供的测试方案 URL
5. **关键改造点**: 从 FP YAML 的 module 列表精炼核心改造点（语言精炼，整理核心关键点，不罗列全部改造）
6. **测试关注点**: 基于 FP 分析推导的核心测试关注方向
7. **测试策略**: 提供推导框架（验证范围、不验证模块），此部分主要由人工填写补充
8. **测试准备&效率分析**: 提供推导框架，此部分主要由人工填写补充

### Step 2: 生成测试用例

> **输入**: `<项目名称>_FunctionPoints.yaml`
> **用例格式模板**: [templates/case_model.yaml](templates/case_model.yaml)
> **覆盖类型选择**: 按 Section 4.0 「覆盖类型选择策略」，根据 FP type 选择最有价值的覆盖类型
> **模块组织**: 按 Section 3.2 「模块组织策略（按业务场景）」，按业务场景维度划分模块

**生成步骤**：
1. 分析 FP YAML 中的业务流程和 `lifecycle_scenarios`，确定业务场景模块
2. 将原子层 FP 用例分配到对应的业务场景模块
3. 将 `lifecycle_scenarios` 中的 E2E 用例分配到对应场景模块，标记为 `[基线]`，等级 P0
4. 将 `invariants` 中的不变量用例分配到最相关的模块，**不标基线**，按 Section 4.1.4 分配指导和判定矩阵正常定级
5. 每个业务场景模块至少 1 条基线用例
6. **按 Section 4.1 判定矩阵确定每条用例等级**（FP priority × 覆盖类型），应用特殊升降级规则
7. **标记 FundLoss 标签**：扫描涉及资金安全的用例，追加 `FundLoss` 标签

### Step 3: 生成需求追溯矩阵

```bash
SKILL_DIR=".cursor/skills/custom/dbp-loan-testcase-designer"
PROJECT_DIR="case_workspace/<版本号>/<JIRA单号>-<项目名称>"

python3 $SKILL_DIR/scripts/coverage_checker.py \
  "$PROJECT_DIR/requirements/<需求文档>_requirements.md" \
  "$PROJECT_DIR/testcases/<项目名称>_TestCases.md"
```

**输出文件**: `<项目名称>_TestCases_traceability_matrix.md`

**追溯矩阵内容**:

- 统计信息（需求总数、功能点总数、Case ID 总数、覆盖率）
- 三级追溯矩阵（REQ → FP → TC/Case ID）
- Case ID 反向索引（Case ID → FP → REQ）
- 关联层覆盖统计（data_flows 覆盖率、invariants 覆盖率、lifecycle_scenarios 覆盖率）

**覆盖率门禁**:

| 级别 | 门禁 |
|------|------|
| MUST | 100% |
| SHOULD | 80% |
| MAY | 50% |

### Step 4: 生成 XMind

```bash
SKILL_DIR=".cursor/skills/custom/dbp-loan-testcase-designer"
PROJECT_DIR="case_workspace/<版本号>/<JIRA单号>-<项目名称>"

# 生成主文件
python3 $SKILL_DIR/scripts/yaml_to_xmind.py \
  "$PROJECT_DIR/testcases/<项目名称>_TestCases.yaml"

# 同步到历史版本目录（带版本号）
cp "$PROJECT_DIR/testcases/<项目名称>_TestCases.yaml" \
   "$PROJECT_DIR/.history/<项目名称>_TestCases_v<N>.yaml"

python3 $SKILL_DIR/scripts/yaml_to_xmind.py \
  "$PROJECT_DIR/.history/<项目名称>_TestCases_v<N>.yaml"
```

---

## 七、版本管理规则

每次生成或修改用例时，**必须同步到项目历史目录**：

1. **检查版本号**: 查找 `.history/` 中已有的版本文件
2. **确定新版本号**: 已有版本数 + 1
3. **复制并重命名**: 将主文件复制到历史目录，添加版本后缀
4. **生成对应 XMind**: 为历史版本也生成 XMind 文件

```bash
PROJECT_DIR="case_workspace/<版本号>/<JIRA单号>-<项目名称>"

# 查找已有版本
ls $PROJECT_DIR/.history/*_TestCases_v*.yaml 2>/dev/null | wc -l
# 输出数量 +1 即为新版本号
```

| 目录 | 用途 |
|------|------|
| `testcases/` | 当前最新版本，用于交付和评审 |
| `.history/` | 历史版本归档，用于回溯和对比 |

---

## 八、质量门禁

### 8.1 用例质量

| 检查项 | 标准 |
|--------|------|
| 每个 FP 至少有 2 条用例（正向 + 按 FP type 选择的覆盖类型） | 100% |
| 每条用例有 Case ID | 100% |
| 每条用例有需求来源 (REQ-编号【原文】) | 100% |
| 每条用例有功能点来源 (FP-编号) | 100% |
| 每条 AI 生成用例 tags 包含 `AI-GEN` | 100% |
| 资金处理类用例标记 `FundLoss` 标签 | 100% |
| 用例等级按判定矩阵确定（P0 占比 15%-25%） | 检查 |
| YAML schema 符合 case_model.yaml 定义 | 100% |
| 前置条件 / 测试步骤 / 预期结果 三字段完整 | 100% |
| 用例直接挂在功能点下（无多余分组节点） | 100% |
| 覆盖类型按 FP type 选择（无伪边界/冗余覆盖） | 100% |
| 步骤/结果不换行 | 100% |
| 输出符合 YAML 语法规范 | 100% |
| modules 按业务场景组织（非按 FP module） | 100% |
| 每个业务场景模块至少 1 条 `[基线]` 用例（P0） | 100% |
| E2E/不变量用例融入对应模块（不独立成 E2E 模块） | 100% |

### 8.2 覆盖率

| 覆盖维度 | 标准 |
|----------|------|
| MUST 需求覆盖率 | 100% |
| SHOULD 需求覆盖率 | >= 80% |
| data_flows 每条至少 1 条集成用例 | 100% |
| invariants 每个至少 1 条校验用例（不要求基线标记） | 100% |
| lifecycle_scenarios 每条至少 1 条 `[基线]` E2E 用例 | 100% |

---

## 九、AI 提示词模板

```
读取 case_workspace/<版本号>/<JIRA单号>-<项目名称>/analysis/<项目名称>_FunctionPoints.yaml，
按 @.cursor/skills/custom/dbp-loan-testcase-designer/templates/case_model.yaml 格式生成测试用例。

## 项目信息
- 版本号: <版本号>
- JIRA: <JIRA单号>
- 项目名称: <项目名称>


## 测试用例要求
1. **必须查看 requirements/images/ 目录下的所有图片**，提取业务规则、流程、状态流转
2. 按照MECE原则，分类提取核心功能点，确保不遗漏
3. **按 Section 4.0 覆盖类型选择策略**，根据每个 FP 的 type 选择最有价值的覆盖类型，禁止为所有 FP 统一生成正向/异常/边界
4. **按 Section 4.1 用例等级判定矩阵**确定每条用例的 P0/P1/P2 等级，禁止所有用例统一标 P0
5. **需求来源格式**：`REQ-编号【需求原文完整内容】`，必须包含原文
6. **标签**：所有 AI 生成用例 tags 包含 `AI-GEN`；涉及资金安全的用例追加 `FundLoss`
7. **输出为 YAML 格式**，precondition/steps/expected 使用列表写法


## 输出要求
1. 用例文件: case_workspace/<版本号>/<JIRA单号>-<项目名称>/testcases/<项目名称>_TestCases.yaml
2. 同步历史版本到 .history/
3. 生成追溯矩阵
4. 使用 yaml_to_xmind.py 生成 XMind

```

---

## 十、参考资料

- 用例 YAML 模板：[templates/case_model.yaml](templates/case_model.yaml)
- 功能点 YAML schema：[templates/function_point_template.yaml](templates/function_point_template.yaml)
- YAML → XMind 转换脚本：[scripts/yaml_to_xmind.py](scripts/yaml_to_xmind.py)
