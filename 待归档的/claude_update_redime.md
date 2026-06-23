# Claude Code 更新脚本

## 背景

官方下载服务器 `https://downloads.claude.ai` 在部分网络环境下无法访问，导致 `claude update` 命令失败。本脚本通过 GitHub Releases 提供替代更新方案。

## 使用方法

```bash
cd Atc_Test2026
chmod +x claude-update
./claude-update
```

## 脚本功能

- 自动检测当前版本与最新版本
- 从 GitHub Releases 下载对应架构的安装包
- 自动安装到标准路径 `~/.local/share/claude/versions/`
- 更新符号链接 `~/.local/bin/claude`
- 清理临时文件
- 支持 macOS arm64 和 x86_64 架构

## 手动更新命令

如果脚本不可用，可手动运行以下命令：

```bash
VERSION="2.1.183"
cd /tmp && curl -L -o claude.tar.gz "https://github.com/anthropics/claude-code/releases/download/v${VERSION}/claude-darwin-arm64.tar.gz" && tar -xzf claude.tar.gz
mkdir -p ~/.local/share/claude/versions/${VERSION} && cp /tmp/claude ~/.local/share/claude/versions/${VERSION}/ && chmod +x ~/.local/share/claude/versions/${VERSION}/claude
rm ~/.local/bin/claude && ln -s ~/.local/share/claude/versions/${VERSION}/claude ~/.local/bin/claude
rm -rf /tmp/claude /tmp/claude.tar.gz
claude --version
```

## 项目文件

- `claude-update` - 更新脚本（bash）
- `claude_update_redime.md` - 说明文档