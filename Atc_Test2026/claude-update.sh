#!/bin/bash

set -e

echo "🔍 正在检查 Claude Code 最新版本..."

LATEST_VERSION=$(curl -s https://api.github.com/repos/anthropics/claude-code/releases/latest | grep -o '"tag_name": "v[^"]*"' | sed 's/"tag_name": "v//' | sed 's/"//')
CURRENT_VERSION=$(claude --version | grep -o '[0-9]*\.[0-9]*\.[0-9]*')

echo "当前版本: $CURRENT_VERSION"
echo "最新版本: $LATEST_VERSION"

if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
    echo "✅ 当前已是最新版本"
    exit 0
fi

echo ""
echo "🚀 开始下载新版本 $LATEST_VERSION..."

ARCH=$(uname -m)
case "$ARCH" in
    arm64)
        FILE="claude-darwin-arm64.tar.gz"
        ;;
    x86_64)
        FILE="claude-darwin-x64.tar.gz"
        ;;
    *)
        echo "❌ 不支持的架构: $ARCH"
        exit 1
        ;;
esac

cd /tmp
curl -L -o claude.tar.gz "https://github.com/anthropics/claude-code/releases/download/v${LATEST_VERSION}/${FILE}"
tar -xzf claude.tar.gz

echo ""
echo "📦 安装新版本..."

mkdir -p ~/.local/share/claude/versions/${LATEST_VERSION}
cp /tmp/claude ~/.local/share/claude/versions/${LATEST_VERSION}/
chmod +x ~/.local/share/claude/versions/${LATEST_VERSION}/claude

rm ~/.local/bin/claude
ln -s ~/.local/share/claude/versions/${LATEST_VERSION}/claude ~/.local/bin/claude

rm -rf /tmp/claude /tmp/claude.tar.gz

echo ""
echo "✅ 更新完成！"
claude --version