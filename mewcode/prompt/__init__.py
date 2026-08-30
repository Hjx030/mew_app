"""MewCode Prompt 拼装系统。

负责全局指令的模块化拼装、环境信息注入、运行时指令注入（Plan Mode 变频 / 温和提示）。
"""

from mewcode.prompt.builder import (
    GENTLE_REMINDER,
    PLAN_FULL_INSTRUCTION,
    PLAN_MINIMAL_REMINDER,
    PromptBuilder,
)
from mewcode.prompt.environment import (
    EnvironmentInfo,
    collect_environment,
    format_environment,
)
from mewcode.prompt.injection import (
    INJECT_CLOSE,
    INJECT_OPEN,
    PlanModeInjector,
    make_instruction,
)
from mewcode.prompt.sections import SECTIONS, Section

__all__ = [
    "GENTLE_REMINDER",
    "PLAN_FULL_INSTRUCTION",
    "PLAN_MINIMAL_REMINDER",
    "PromptBuilder",
    "EnvironmentInfo",
    "collect_environment",
    "format_environment",
    "INJECT_CLOSE",
    "INJECT_OPEN",
    "PlanModeInjector",
    "make_instruction",
    "SECTIONS",
    "Section",
]
