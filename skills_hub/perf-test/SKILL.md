---
name: perf-test
description: This skill should be used when users mention performance testing, stress testing, load testing, or benchmarking (性能测试、压测、压力测试). It covers the full workflow including data preparation (batch creating workspaces/apps/users), assembling Locust scripts, and running performance tests against private-deployment or cloud environments.
disable-model-invocation: false
---

# 私有化性能测试 Skill

## 使用时机

当用户提到以下任何一种场景时，加载本 skill：
- **性能测试**：用户说"做性能测试"、"压测"、"性能压测"等
- **数据准备**：需要在私有化环境做压测前数据准备（批量创建空间/应用/用户/加入空间）
- **组装压测脚本**：用户说"组装一个性能测试脚本"、"写一个 locust 脚本"、"编写压测脚本"等

---

## 流程入口判断（重要⚠️）

当用户触发本 skill 时，**必须先判断用户意图**，进入对应的流程：

### 入口 A：用户说"我要做性能测试" / "做压测"

> 用户只说了要做性能测试，但没有明确需要什么，此时需要先**询问确认**。

**执行步骤**：

1. **询问用户是否需要数据准备**（使用 `ask_followup_question` 工具）：
   - 提问："您的性能测试需要做哪些准备工作？"
   - 选项：
     - "需要数据准备（批量创建空间/应用/用户等）"
     - "需要组装一个压测脚本（locust 脚本）"
     - "两者都需要（先数据准备，再组装脚本）"
     - "我只是有个问题想咨询"

2. **根据用户回答分流**：
   - 选择"数据准备" → 进入 **[流程 1：数据准备](#流程-1数据准备)**
   - 选择"组装压测脚本" → 进入 **[流程 2：组装 Locust 脚本](#流程-2组装-locust-脚本)**
   - 选择"两者都需要" → 先走流程 1，完成后走流程 2
   - 选择"咨询" → 自由对话，参考本 skill 的知识回答

### 入口 B：用户说"组装一个性能测试脚本" / "写个压测脚本"

> 用户明确要求组装脚本。

**直接进入** → **[流程 2：组装 Locust 脚本](#流程-2组装-locust-脚本)**

### 入口 C：用户说"做数据准备" / "批量创建空间/应用/用户"

> 用户明确要求做数据准备。

**直接进入** → **[流程 1：数据准备](#流程-1数据准备)**

---

## 流程 1：数据准备

### 能力说明

- 提供 N 个原子脚本，支持串行或按需组合调用
- 脚本结果写入统一 JSON 资产文件，便于后续脚本复用
- 脚本内部复用仓库现有 `Service/API`，不手写签名或明文密钥

### 目录与脚本

- `scripts/create_spaces.py`：批量创建空间并记录 `SpaceId`
- `scripts/create_apps.py`：在指定空间批量创建应用
- `scripts/create_users.py`：批量创建用户并记录用户信息
- `scripts/add_users_to_space.py`：批量把用户加入空间
- `scripts/create_shared_kbs.py`：批量创建共享知识库，结果写入 `shared_kbs` 字段
- `scripts/gen_doc_variants.py`：从单个 docx 源文件多线程批量生成差异化变体，每份文档末尾插入唯一 UUID，文件名含序号+UUID 前缀
- `scripts/common/asset_store.py`：统一资产 JSON 读写
- `scripts/common/cli_utils.py`：命令行参数与输入解析
- `scripts/common/batch_runner.py`：批量执行、重试、节流

### 资产文件约定

默认资产文件可放在 skill 目录下（或通过参数覆盖）：
- `spaces.json`、`users.json`、`apps.json`

统一结构（示例）：

{
  "run_id": "20260324_143501",
  "spaces": [],
  "users": [],
  "apps": [],
  "failed": []
}

### 推荐执行链路

1. 先建空间：`create_spaces.py`
2. 再建用户：`create_users.py`
3. 把用户加到空间：`add_users_to_space.py`
4. 在空间建应用：`create_apps.py`
5. 在空间批量建共享知识库：`create_shared_kbs.py`

### 调用示例


python3 .codebuddy/skills/perf-test/scripts/create_spaces.py --account Master_Default --count 5 --output .codebuddy/skills/perf-test/assets/spaces.json


python3 .codebuddy/skills/perf-test/scripts/create_users.py --account Master_Default --count 20 --user-prefix perf_u --password-encrypted <加密密码串> --output .codebuddy/skills/perf-test/assets/users.json

python3 .codebuddy/skills/perf-test/scripts/add_users_to_space.py --account Master_Default --space-id <space_id> --users-file .codebuddy/skills/perf-test/assets/users.json --output .codebuddy/skills/perf-test/assets/membership.json



python3 .codebuddy/skills/perf-test/scripts/create_apps.py --account Master_Default --space-ids <space_id1,space_id2> --count-per-space 30 --app-prefix perf_app --output .codebuddy/skills/perf-test/assets/apps.json



# 在默认空间批量创建 10 个共享知识库（主账号）
python3 .codebuddy/skills/perf-test/scripts/create_shared_kbs.py \
    --count 10 \
    --output .codebuddy/skills/perf-test/assets/shared_kbs.json

# 指定空间和账号
python3 .codebuddy/skills/perf-test/scripts/create_shared_kbs.py \
    --account Master_Default \
    --space-id <space_id> \
    --count 20 \
    --kb-prefix perf_kb \
    --output .codebuddy/skills/perf-test/assets/shared_kbs.json


### 参数设计原则

- 数量参数均为正整数
- 所有输入支持"命令行直传"和"从资产 JSON 读取"两种方式
- 支持 `--run-id` 以实现多批次可追踪
- 支持 `--retry`、`--interval` 控制重试与节流

### 故障处理

- 每次 API 调用均检查 `Response.Error`
- 失败项写入 `failed` 数组，不吞错
- 总结输出成功数/失败数/关键失败原因

---

## 流程 2：组装 Locust 脚本

### 核心原则（重要⚠️）

1. **完全独立**：脚本必须一个文件包含所有依赖，**不能 import 项目内其他模块**
2. **最小依赖**：仅依赖 `pip install locust requests` 可安装的标准库
3. **环境变量驱动**：所有连接信息通过环境变量覆盖
4. **内置签名**：TC3-HMAC-SHA256 签名和 S3 V4 签名必须内嵌在脚本中

### 执行步骤

#### Step 1：收集用户需求

向用户了解以下信息（使用 `ask_followup_question` 工具）：

**必须了解的信息**：
- **压测场景**：需要压测什么业务流程？
  - 示例选项：标准模式全流程（创建应用→上传文档→发布→对话→清理）、纯对话压测、创建应用压测、文档上传压测、自定义场景等
- **目标环境**：私有化环境的 Host 地址、SecretId/SecretKey 等（可以后续通过环境变量传入）

**可选了解的信息**：
- 并发用户数、运行时长
- 是否需要特殊的指标统计
- 是否有特殊的业务参数

#### Step 2：参考 Cookbook 编写脚本

根据用户描述的场景，**参考 `references/locust-cookbook.md`** 中的代码片段和模式来编写独立 locust 脚本。

**编写规范**：

1. **文件头**：包含完整的文档字符串，说明场景、指标、依赖、运行方式、环境变量
2. **导入区**：标准库 + requests + locust（参考 cookbook 的导入清单）
3. **常量区**：所有可配置项通过 `os.getenv()` 读取，提供合理默认值
4. **基础设施层**：按需包含以下组件（从 cookbook 复制）：
   - `get_tc3_headers()`：调用xxx API 时必须包含
   - `post_yun_api()`：调用xxx API 时必须包含
   - `get_s3_v4_signature()` + `upload_file_to_minio()`：上传文档时必须包含
   - `process_response_sse()`：SSE 对话时必须包含
5. **业务 API 层**：根据场景按需包含（从 cookbook 复制/裁剪）
6. **Locust 上报工具**：`fire_success()` + `fire_failure()` 必须包含
7. **Locust User 类**：参考 cookbook 的 workflow 编排模式
8. **文件驱动数据**：如果用户提到以下需求，**必须参考 cookbook 第 8 章**：
   - "从文件读取数据"、"每个并发用不同数据"、"数据用完停止" → 使用 **8.2 Queue 消耗方案**（数据不重复，耗尽自动停）
   - "数据可以重复"、"按时间跑"、"循环使用数据" → 使用 **8.6 循环读取方案**（`itertools.cycle` 或 `random.choice`，配合 `-t` 停止）

**脚本输出位置**：
- 优先复用 skill 内置脚本：`.codebuddy/skills/perf-test/scripts/`
- 如需定制场景，再保存到 `tool/pef_test/` 目录

**内置常用查询压测脚本（开箱即用）**：
- `locust_list_app_perf.py`：压测 `ListApp`（默认 `PageSize=15`），统计响应时间指标
- `locust_list_shared_knowledge_perf.py`：压测 `ListSharedKnowledge`（默认 `PageSize=15`），统计响应时间指标
- `locust_describe_space_list_perf.py`：压测 `DescribeSpaceList`（无分页参数），统计响应时间指标

**内置脚本运行示例**：

locust -f .codebuddy/skills/perf-test/scripts/locust_list_app_perf.py --headless -u 10 -r 2 -t 5m



locust -f .codebuddy/skills/perf-test/scripts/locust_list_shared_knowledge_perf.py --headless -u 10 -r 2 -t 5m



locust -f .codebuddy/skills/perf-test/scripts/locust_describe_space_list_perf.py --headless -u 10 -r 2 -t 5m


#### Step 3：询问是否执行

脚本编写完成后，**必须询问用户是否需要帮助执行**（使用 `ask_followup_question` 工具）：

- 提问："压测脚本已编写完成，是否需要我帮你执行？"
- 选项：
- "是，帮我执行（headless 模式）"
- "否，我自己执行"

#### Step 4：执行脚本（如果用户选择执行）

使用 locust **headless 模式**运行脚本：

# 基本执行（询问用户并发数和时长）
locust -f <脚本路径> --headless -u <并发用户数> -r <孵化率> -t <运行时长>

# 示例
locust -f tool/pef_test/locust_chat_only_perf.py --headless -u 5 -r 1 -t 5m


执行前需确认：
1. 环境变量是否已设置（ADP_HOST、ADP_SECRET_ID、ADP_SECRET_KEY 等）
2. 如果未设置，提示用户设置或使用默认值
3. 并发用户数（-u）和运行时长（-t）

---

## 指标统计规范

### 标准指标命名

| 指标名称 | 说明 | 单位 |
|---------|------|------|
| `0_workflow` | 总流程成功/失败 | ms |
| `1_create_app` | 创建应用 | ms |
| `2_upload_and_import_doc` | 文档上传并导入 | ms |
| `3_release_app` | 应用发布 | ms |
| `4_chat` | 对话 | ms |
| `4_chat_ttft` | 首 Token 延迟 | ms |
| `4_chat_tokens_per_second` | 吐字率 | tokens/s |
| `5_delete_app` | 清理应用 | ms |

### 命名规则

- 使用**数字前缀**表示步骤顺序（0_workflow 排最前）
- 失败分类使用下划线后缀：`4_chat_error_rate_limit`、`4_chat_error_question_sensitive`

---

## 安全要求

- 不在日志中输出明文密钥、密码
- 脚本中的默认 SecretId/SecretKey 仅用于开发调试，生产环境必须通过环境变量覆盖
- 用户创建脚本仅接收外部传入密文密码串，不做明文加密
- 数据准备脚本复用 `BaseApi.do_req_by_env` 做签名与环境路由

---

## 参考

- 详细接口备注见：`references/api-notes.md`
- Locust 脚本编写参考手册：`references/locust-cookbook.md`（⚠️ 编写压测脚本时必须参考此文档）