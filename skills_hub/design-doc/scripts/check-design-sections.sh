#!/usr/bin/env bash
# 用法: ./scripts/check-design-sections.sh <design.md 路径>
# 输出缺失的必选节，供 design-doc 技能并入符合性检查。

FILE="${1:-}"
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
echo"Usage: $0 <path-to-design.md>"
exit 1
fi

echo"=== 设计文档必选节检查 ==="
for section in 设计目标与范围 用户与关键场景 交互设计 视觉与组件 可访问性 交付物; do
if grep -qE "^## *$section""$FILE" 2>/dev/null; then
    echo"✓ $section"
else
    echo"✗ 缺失: $section"
fi
done