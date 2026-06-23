"""生成文档变体脚本"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'common'))

from asset_store import AssetStore
from cli_utils import parse_args, print_progress, print_success


def main():
    args = parse_args(
        "生成文档变体",
        count={'type': int, 'default': 10, 'help': '生成数量'}
    )

    print_success(f"生成 {args.count} 个文档变体")


if __name__ == '__main__':
    main()
