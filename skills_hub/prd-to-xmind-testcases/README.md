# PRD/需求文档 → XMind 测试用例

根据需求文档或 PRD 生成可导入 XMind 的测试用例思维导图大纲。

## 需求文档目录

本 Skill 根目录下提供 **`requirements/`** 文件夹：将 PRD、PDF 等需求文档放入该目录后，可直接用指令让 Skill 读取并生成测试用例，无需每次写完整路径。

## 使用方式

在 Cursor 中直接说出需求，例如：

- 「读取 requirements 里的需求文件，生成测试用例」
- 「根据 requirements 目录下的 PRD 生成思维导图测试用例」
- 「根据这份 PRD 生成思维导图测试用例」（粘贴内容或指定任意路径）
- 「把 `docs/需求.docx` 转成 XMind 测试用例」

支持**从 `requirements/` 读取**、**指定文件路径**（.docx / .pdf / .txt / .md）或**粘贴文档内容**。

## 所有项目通用

若希望在所有项目里都能用本 Skill，可将本目录复制到 Cursor 的用户级 Skill 目录，例如：

- **macOS/Linux**：`~/.cursor/skills/prd-to-xmind-testcases/`
- 具体路径以你当前 Cursor 版本「Skill 加载路径」为准。

复制后保持目录结构：`SKILL.md` 与 `references/` 在同一目录下。

## 测试规范说明

- **默认（未提接口/性能）**：按 `references/general-testcases-standard.md` 通用规范生成，包含边界值、等价类、场景法、正向/反向、状态与流程等策略。
- **接口测试**：对话中说明「按接口测试」「生成接口测试用例」时，会加载 `references/api-testcases-standard.md`。
- **性能测试**：说明「按性能测试」「生成性能测试用例」时，会加载 `references/performance-testcases-standard.md`。

接口/性能规范已内置在 `references/` 中，无需自行添加；若有项目特有补充，可再在 `references/` 下增加文档并在对话中引用。
