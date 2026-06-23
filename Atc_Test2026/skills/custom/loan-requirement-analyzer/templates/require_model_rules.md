使用业务领域建模方式和MECE原则进行划分，并应用以下模版来生成需求文档
#### REQ-STG-001: TENOR_FIRST Level1金额类型优先级

| 属性 | 内容 |
|------|------|
| **需求ID** | REQ-STG-001 |
| **需求标题** | 金额类型优先级规则 |
| **优先级** | P0 |

**需求描述**:
部分还款时，按 overdue > MPD > statement due > un-statement due 顺序分配

**前置条件**:
- [x] billRepayStrategy = TENOR_FIRST
- [x] 存在部分还款场景

**业务规则**:
| 规则ID | 规则描述 | 优先级 |
|--------|----------|--------|
| BR-001 | overdue 优先于 MPD | 1 |
| BR-002 | MPD 优先于 statement due | 2 |
| BR-003 | statement due 优先于 un-statement due | 3 |

**功能描述**:
功能详细说明，举例、样例

