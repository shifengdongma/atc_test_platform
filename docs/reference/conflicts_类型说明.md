# conflicts.json 冲突类型与 DEF_xx 含义说明

> 依据 `_source/conflicts.json` 中出现的类型键，结合 `_source/算法对接 2026030301.md` 整理。数据格式与枚举以 **`_source/算法对接 2026030301.md`** 为准。  
> 命名规则：`DEF_{告警大类}_{空域类型或机型编号}`，**ALERT**=告警，**WARN**=预警。

---

## 1. 文件结构概览

- **文件**：`_source/conflicts.json`
- **结构**：顶层为「冲突类型编码」→ 该类型下的冲突记录数组。
- **单条记录字段**：

| 字段            | 类型   | 说明                                                        |
| --------------- | ------ | ----------------------------------------------------------- |
| subject_uid     | String | 主体 UID（一般为无人机编号，如 UAV_00010）                  |
| object_uid      | String | 客体 UID（无人机编号 或 空域/禁飞区 ID；设备/偏离类可为空） |
| conflict_time   | Float  | 冲突发生时间（秒级时间戳）                                  |
| frame_timestamp | Float  | 仿真帧时间戳（秒）                                          |

- **客体含义**：
  - **碰撞类**：`object_uid` 为另一架无人机 UID。
  - **空域侵入类**：`object_uid` 为空域/禁飞区 ID（如 NFZ_001）。
  - **设备/偏离类**（如 DEF_DEV_ALERT）：`object_uid` 常为空。

---

## 2. DEF\_ 类型一览与含义

### 2.1 类型汇总表

| DEF\_ 类型                    | 含义（中文）                             |
| ----------------------------- | ---------------------------------------- |
| DEF_COLLISION_ALERT_C0～C4    | 短期冲突告警 - 机型 C0～C4               |
| DEF_COLLISION_WARN_C0～C4     | 短期冲突预警 - 机型 C0～C4               |
| DEF_AIRSPACE_ALERT_T3C0～T3C4 | 空域侵入告警 - 空域 T3 - 机型 C0～C4     |
| DEF_AIRSPACE_ALERT_T4C0～T4C4 | 空域侵入告警 - 空域 T4 - 机型 C0～C4     |
| DEF_AIRSPACE_ALERT_T5C0～T5C4 | 空域侵入告警 - 空域 T5 - 机型 C0～C4     |
| DEF_AIRSPACE_ALERT_T6C0～T6C4 | 空域侵入告警 - 空域 T6 - 机型 C0～C4     |
| DEF_AIRSPACE_WARN_T3C0～T6C4  | 空域侵入预警 - 空域 T3～T6 - 机型 C0～C4 |
| DEF_DEV_ALERT                 | 飞行器状态异常告警                       |

### 2.2 告警大类与算法文档对应

| 前缀                   | 文档中的名称                                 | 说明                                               |
| ---------------------- | -------------------------------------------- | -------------------------------------------------- |
| DEF*COLLISION_ALERT*\* | collisionShortAlert / 短期冲突告警           | 两机间短期冲突告警，对应 **STCA**                  |
| DEF*COLLISION_WARN*\*  | collisionShortWarn / 短期冲突预警            | 两机间短期冲突预警                                 |
| DEF*AIRSPACE_ALERT*\*  | airspaceEnterAlert / 空域侵入告警            | 危险区/禁区/限制区/隔离空域侵入告警                |
| DEF*AIRSPACE_WARN*\*   | airspaceEnterWarn / 空域侵入预警             | 将侵入某类空域的预警（**DAIW/RAIW/PAW/IAIW** 等）  |
| DEF_DEV_ALERT          | uavStateAlertProperties / 飞行器状态异常告警 | 对应 **EMG**；亦可能与 PYAW、UIA 等设备/状态类相关 |

### 2.3 空域类型 T3～T6（typeCode）

| T 编号 | typeCode   | 中文名称 |
| ------ | ---------- | -------- |
| T3     | limited    | 限制区   |
| T4     | danger     | 危险区   |
| T5     | segregated | 隔离空域 |
| T6     | noDrone    | 空中禁区 |

> 文档 typeCode 完整枚举：controlled、restrictedUse、fusion、noDrone、limited、danger、segregated、suppression（见算法对接文档约 696 行）。

### 2.4 机型/规则编号 C0～C4（无人机类型）

| C 编号 | uavType | 中文名称 |
| ------ | ------- | -------- |
| C0     | LIGHT   | 轻型     |
| C1     | SMALL   | 小型     |
| C2     | MEDIUM  | 中型     |
| C3     | LARGE   | 大型     |
| C4     | MICRO   | 微型     |

> C0～C4 与机型的对应以实际算法/配置为准，上表为常见映射。

---

## 3. 各冲突类型明细及记录数

### 3.1 设备/偏离类

| 类型编码      | 说明               | 记录数 |
| ------------- | ------------------ | ------ |
| DEF_DEV_ALERT | 飞行器状态异常告警 | 317    |

### 3.2 短期冲突告警（DEF_COLLISION_ALERT_Cn）

| 类型编码               | 记录数 |
| ---------------------- | ------ |
| DEF_COLLISION_ALERT_C0 | 188    |
| DEF_COLLISION_ALERT_C1 | 202    |
| DEF_COLLISION_ALERT_C2 | 165    |
| DEF_COLLISION_ALERT_C3 | 190    |
| DEF_COLLISION_ALERT_C4 | 177    |

### 3.3 短期冲突预警（DEF_COLLISION_WARN_Cn）

| 类型编码              | 记录数 |
| --------------------- | ------ |
| DEF_COLLISION_WARN_C0 | 389    |
| DEF_COLLISION_WARN_C1 | 427    |
| DEF_COLLISION_WARN_C2 | 319    |
| DEF_COLLISION_WARN_C3 | 366    |
| DEF_COLLISION_WARN_C4 | 356    |

### 3.4 空域侵入告警（DEF_AIRSPACE_ALERT_TmCn）

| 类型编码                      | 记录数 |
| ----------------------------- | ------ |
| DEF_AIRSPACE_ALERT_T3C0～T3C4 | 78     |
| DEF_AIRSPACE_ALERT_T4C0～T4C4 | 35     |
| DEF_AIRSPACE_ALERT_T5C0～T5C4 | 27     |
| DEF_AIRSPACE_ALERT_T6C0～T6C4 | 15     |

### 3.5 空域侵入预警（DEF_AIRSPACE_WARN_TnCn）

各 T3～T6 与 C0～C4 组合在 conflicts.json 中均有对应键，具体条数见 JSON；对应算法文档「空域侵入预警」格式（约 574～591 行）。

---

## 4. 与算法对接文档、Kafka 约定摘要

| 算法对接文档（算法对接 2026030301.md） | conflicts.json 中的类型       |
| -------------------------------------- | ----------------------------- |
| 短期冲突告警 collisionShortAlert       | DEF_COLLISION_ALERT_C0～C4    |
| 短期冲突预警 collisionShortWarn        | DEF_COLLISION_WARN_C0～C4     |
| 空域侵入告警 airspaceEnterAlert        | DEF_AIRSPACE_ALERT_T3C0～T6C4 |
| 空域侵入预警 airspaceEnterWarn         | DEF_AIRSPACE_WARN_T3C0～T6C4  |
| 飞行器状态异常告警（EMG 等）           | DEF_DEV_ALERT                 |

- **Kafka**：告警通过 Topic **uav_collision_alarm** 下发，消息为数组，可包含多种告警。
- **告警状态**：文档中告警有 **start / active / stop**；本 JSON 为仿真结果快照，仅记录发生时刻。
- **时间**：`conflict_time` / `frame_timestamp` 为秒级时间戳；对接时若需毫秒或 `yyyy-MM-dd HH:mm:ss`，按算法文档转换。
- 空域 typeCode、suppressionType（STCA、EMG、DAIW、RAIW、PAW、IAIW 等）以 `算法对接 2026030301.md` 第 691～698 行为准。

---

## 5. 类型总数与记录总数

- **冲突类型数**：52 种（conflicts.json 中 DEF\_ 键的个数）。
- **记录总数**：以当前 `conflicts.json` 统计为准。

若算法侧对 DEF\_、T 编号、C 编号有明确定义表，以算法侧文档为准并更新本说明。
