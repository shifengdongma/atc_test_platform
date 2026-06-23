"""批量创建应用脚本"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'common'))

from asset_store import AssetStore
from cli_utils import parse_args, print_progress, print_success


def main():
    args = parse_args(
        "批量创建应用",
        count={'type': int, 'default': 10, 'help': '创建数量'}
    )

    print_success(f"创建 {args.count} 个应用")


if __name__ == '__main__':
    main()
