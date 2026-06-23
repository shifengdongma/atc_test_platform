---
name: prd-to-xmind-testcases
description: 根据需求文档或 PRD 生成可导入 XMind 的测试用例思维导图大纲。可从本 Skill 的 requirements 目录读取需求文件（PRD/PDF 等），或根据用户提供的路径/粘贴内容生成。按功能/模块拆分，每项下挂测试点（标题+简要步骤/预期）。未提及接口/性能时默认按通用测试规范（边界值、等价类、场景法等）生成；提及接口/性能测试时加载 references 内对应规范。当用户说「读取需求文件并生成测试用例」「生成思维导图测试用例」等时使用。支持 .docx、.pdf、.txt、.md。
---

# 需求/PRD → XMind 测试用例

根据需求文档或 PRD 生成**可直接导入 XMind** 的测试用例大纲，保证覆盖全、结构清晰、格式省事。

## 需求文档目录

本 Skill 提供**需求文档目录** `requirements/`：用户可将 PRD、PDF 等需求文件放入该目录，通过指令让 Skill 读取并生成测试用例。

- **路径**：与 SKILL.md 同级的 `requirements/` 文件夹。
- **支持格式**：PRD/需求类文字文档——`.docx`、`.pdf`、`.txt`、`.md`。
- **指令示例**：「读取 requirements 里的需求文件并生成测试用例」「根据 requirements 下的 PRD 生成思维导图测试用例」。若未指定具体文件，先列出 `requirements/` 下符合格式的文件供用户选择，再按用户选择读取并生成。

## 工作流

1. **获取输入**：  
   - **方式 A**：用户指示从 `requirements/` 读取（如「读取需求文件并生成测试用例」）→ 解析该目录下的 .docx / .pdf / .txt / .md，若未指定文件则先列出再选。  
   - **方式 B**：用户提供需求文档的**任意文件路径**或直接粘贴正文。  
   若做接口测试、性能测试等专项，按需加载 `references/` 下对应规范。
2. **读取内容**：按路径读取；若环境无法解析 .docx/.pdf（如为二进制无法提取文本），则提示用户将正文复制到对话或提供 .txt 导出。
3. **解析功能/模块**：从文档中识别**全部**功能/模块，不遗漏；若有 references 中的测试规范，结合规范细化测试类型（功能/接口/性能等）。
4. **生成大纲**：按 [references/testcase-structure.md](references/testcase-structure.md) 的层级与字段生成测试用例；格式严格遵循 [references/xmind-outline-format.md](references/xmind-outline-format.md)。**输出为 Markdown (.md)**，因 XMind 不支持 .txt 导入与文本粘贴，仅支持 .md / OPML 等格式导入。
5. **交付**：输出完整 .md 内容并保存为 .md 文件（如存于 `requirements/` 下），并说明「XMind → 文件 → 导入 → Markdown → 选择该 .md 文件」即可导入。

## 格式与结构

- **层级与字段**：见 [references/testcase-structure.md](references/testcase-structure.md)（功能/模块 → 测试点 → 标题 + 简要步骤/预期）。
- **XMind 导入格式**：见 [references/xmind-outline-format.md](references/xmind-outline-format.md)。输出为 **Markdown (.md)**（# / ## / ### / #### 与 - 列表），XMind 通过「文件 → 导入 → Markdown」导入；不支持 .txt 导入与文本粘贴。

## 测试用例设计规范（按需加载）

- **未提及接口测试或性能测试**：**默认**按 [references/general-testcases-standard.md](references/general-testcases-standard.md) 生成测试点，运用通用软件测试策略（正向、反向、边界值、等价类、场景法、状态与流程等），保证覆盖全。
- **明确要求接口测试**：加载 [references/api-testcases-standard.md](references/api-testcases-standard.md)，在保持「按功能/模块 + 测试点」的前提下，按接口测试维度（请求/参数、响应/错误码、鉴权/权限、幂等/并发等）补充或调整测试点。
- **明确要求性能测试**：加载 [references/performance-testcases-standard.md](references/performance-testcases-standard.md)，按性能测试维度（指标/基线、场景类型、瓶颈/降级等）补充或调整测试点。
