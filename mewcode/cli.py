"""命令行参数解析。"""

from __future__ import annotations

import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 参数列表，默认为 sys.argv[1:]

    Returns:
        解析后的 Namespace
    """
    parser = argparse.ArgumentParser(
        prog="mewcode",
        description="MewCode — CLI AI Coding Assistant",
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="配置文件路径（默认 ~/.config/mewcode/config.yaml）",
    )
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="显示版本号",
    )
    return parser.parse_args(argv)
