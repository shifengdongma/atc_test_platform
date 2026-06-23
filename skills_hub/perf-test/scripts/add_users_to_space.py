"""添加用户到空间脚本"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'common'))

from asset_store import AssetStore
from cli_utils import parse_args, print_progress, print_success


def main():
    args = parse_args(
        "添加用户到空间",
        space_id={'type': str, 'required': True, 'help': '空间 ID'},
        user_ids={'type': str, 'nargs': '+', 'required': True, 'help': '用户 ID 列表'}
    )

    print_success(f"添加 {len(args.user_ids)} 个用户到空间 {args.space_id}")


if __name__ == '__main__':
    main()
