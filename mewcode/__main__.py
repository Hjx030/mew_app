"""MewCode 入口点。

支持 python -m mewcode 和安装后的 mewcode 命令。
"""

from __future__ import annotations

import asyncio
import sys

from mewcode import cli
from mewcode.config import ConfigError, load_config
from mewcode.tools import (
    Bash,
    EditFile,
    Glob,
    Grep,
    ReadFile,
    ToolRegistry,
    WriteFile,
)
from mewcode.tui.session import run_session

VERSION = "0.3.0"


def _setup_default_tools() -> ToolRegistry:
    """注册内置工具。"""
    registry = ToolRegistry()
    registry.register(ReadFile())
    registry.register(WriteFile())
    registry.register(EditFile())
    registry.register(Bash())
    registry.register(Glob())
    registry.register(Grep())
    return registry


def main() -> None:
    """MewCode 主入口。"""
    args = cli.parse_args()

    if args.version:
        print(f"MewCode {VERSION}")
        return

    # 加载配置
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        print("请创建配置文件或使用 --config 指定路径", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"读取配置时出错: {e}", file=sys.stderr)
        sys.exit(1)

    # 注册工具
    tool_registry = _setup_default_tools()

    # 运行交互式会话
    try:
        asyncio.run(
            run_session(config, tool_registry=tool_registry, mcp_config_path=args.mcp_config)
        )
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n未预期的错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
