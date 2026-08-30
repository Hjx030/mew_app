"""Prompt 拼装主入口。"""

from __future__ import annotations

from mewcode.prompt.sections import Section

# Plan Mode 完整指令
PLAN_FULL_INSTRUCTION = (
    "对于多步任务，请先向用户展示清晰的逐步计划，说明每一步要做什么。"
    "等待用户确认后再开始执行工具。"
)

# Plan Mode 精简提醒
PLAN_MINIMAL_REMINDER = "多步任务请先出计划，等待用户确认后再执行。"

# 温和提醒（工具调用次数过多时注入）
GENTLE_REMINDER = "你已连续调用 5 次工具，若任务已可完成请尽快给出最终回答。"


class PromptBuilder:
    """按优先级拼装全局指令模块，产出稳定全局指令（可缓存前缀）。"""

    def __init__(self, sections: list[Section]) -> None:
        self._sections = sections

    def build_stable(self) -> str:
        """按 priority 升序拼接所有模块，返回稳定全局指令。"""
        ordered = sorted(self._sections, key=lambda s: s.priority)
        return "\n\n".join(s.content for s in ordered)
