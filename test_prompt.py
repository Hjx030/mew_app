"""Prompt 拼装系统单元测试。"""

from mewcode.prompt.builder import (
    GENTLE_REMINDER,
    PLAN_FULL_INSTRUCTION,
    PLAN_MINIMAL_REMINDER,
    PromptBuilder,
)
from mewcode.prompt.environment import collect_environment, format_environment
from mewcode.prompt.injection import PlanModeInjector, make_instruction
from mewcode.prompt.sections import SECTIONS


class TestSectionSort:
    def test_all_sections_present(self):
        output = PromptBuilder(SECTIONS).build_stable()
        for kw in ("MewCode", "链式调用", "read_file", "删除", "简洁中文"):
            assert kw in output, f"缺少模块关键词: {kw}"

    def test_priority_order(self):
        output = PromptBuilder(SECTIONS).build_stable()
        # identity(10) 在最前，output_style(50) 在最后
        assert output.index("你是 MewCode") < output.index("回复使用简洁中文")


class TestEnvironment:
    def test_environment_fields_present(self):
        env = collect_environment()
        assert env.cwd
        assert env.os_name
        assert env.timestamp

    def test_format_contains_all_fields(self):
        env = collect_environment()
        text = format_environment(env)
        assert env.cwd in text
        assert env.os_name in text
        assert env.timestamp in text


class TestPlanModeInjector:
    def test_frequency_full_on_1_4_7(self):
        injector = PlanModeInjector("F", "M", repeat_every=3)
        sequence = [injector.next() for _ in range(6)]
        assert sequence == ["F", "M", "M", "F", "M", "M"]

    def test_reset(self):
        injector = PlanModeInjector("F", "M")
        injector.next()
        injector.reset()
        assert injector.next() == "F"

    def test_custom_repeat_every(self):
        injector = PlanModeInjector("F", "M", repeat_every=2)
        sequence = [injector.next() for _ in range(4)]
        assert sequence == ["F", "M", "F", "M"]


class TestMakeInstruction:
    def test_tag_wrapped(self):
        assert make_instruction("注意收敛") == "<sys-instruct>注意收敛</sys-instruct>"

    def test_constants_nonempty(self):
        assert PLAN_FULL_INSTRUCTION
        assert PLAN_MINIMAL_REMINDER
        assert GENTLE_REMINDER

    def test_gentle_reminder_contains_count(self):
        assert "5 次" in GENTLE_REMINDER
