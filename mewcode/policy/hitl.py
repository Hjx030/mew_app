"""人在回路（HITL）交互：a/s/p/n 按键菜单。"""

from __future__ import annotations

import asyncio

from mewcode.tui.renderer import render_policy_ask


async def ask_user(tool_name: str, args: dict, mode: str) -> str:
    """向用户询问一个未命中规则的操作。

    Returns:
        "allow" | "allow-session" | "allow-forever" | "deny"
    """
    render_policy_ask(tool_name, args, mode)
    loop = asyncio.get_event_loop()
    line = await loop.run_in_executor(None, input, "> ")
    key = line.strip()[:1].lower()
    if key == "s":
        return "allow-session"
    if key == "p":
        return "allow-forever"
    if key == "n":
        return "deny"
    # 空（回车）或其它输入默认本次允许
    return "allow"
