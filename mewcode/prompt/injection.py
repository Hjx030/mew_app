"""运行时指令注入通道。

带 <sys-instruct> 标签的内容是给模型的补充指令，全局指令中已声明：
看到该标签按指令执行、不要当作需要回复的问题。注入内容不进入稳定前缀，不影响缓存。
"""

from __future__ import annotations

INJECT_OPEN = "<sys-instruct>"
INJECT_CLOSE = "</sys-instruct>"


def make_instruction(text: str) -> str:
    """用特殊标签包裹一段补充指令。"""
    return f"{INJECT_OPEN}{text}{INJECT_CLOSE}"


class PlanModeInjector:
    """Plan Mode 指令的变频注入器。

    开启后：第 1 轮注入完整指令，每满 repeat_every 轮重复完整指令，其余轮次注入精简提醒。
    """

    def __init__(self, full: str, minimal: str, repeat_every: int = 3) -> None:
        self._full = full
        self._minimal = minimal
        self._repeat_every = repeat_every
        self._count = 0

    def next(self) -> str:
        """返回本轮应注入的指令文本（完整或精简）。

        第 1、1+repeat_every、1+2*repeat_every…轮返回完整指令，其余返回精简提醒。
        """
        self._count += 1
        if (self._count - 1) % self._repeat_every == 0:
            return self._full
        return self._minimal

    def reset(self) -> None:
        """清零计数（/plan off 或 /clear 时调用）。"""
        self._count = 0
