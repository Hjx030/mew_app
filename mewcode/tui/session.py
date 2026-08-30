"""会话主循环。

基于 prompt_toolkit 的交互式对话界面，支持 Agent Loop 和 Plan Mode。
Prompt 拼装由 mewcode.prompt 包负责：稳定全局指令 + 环境块 + 运行时注入。
"""

from __future__ import annotations

import asyncio
import json
import sys

from prompt_toolkit import PromptSession

from mewcode.config import Config
from mewcode.providers import Message
from mewcode.providers import create_provider
from mewcode.prompt import (
    GENTLE_REMINDER,
    PLAN_FULL_INSTRUCTION,
    PLAN_MINIMAL_REMINDER,
    PlanModeInjector,
    PromptBuilder,
    SECTIONS,
    collect_environment,
    format_environment,
    make_instruction,
)
from mewcode.tools import ToolCall, ToolRegistry
from mewcode.tui.renderer import (
    render_cache_hit,
    render_error,
    render_step_counter,
    render_system,
    render_tool_call,
    render_tool_confirm,
    render_tool_result,
    render_user_input,
    stream_text,
)

MAX_STEPS = 10
GENTLE_REMINDER_THRESHOLD = 5


async def _confirm_action(prompt_text: str) -> str:
    """在终端中等待用户确认。"""
    print(prompt_text, end="", flush=True)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sys.stdin.readline)


def _attach_to_last_tool(request_msgs: list[Message], instruction: str) -> list[Message]:
    """把指令附加到最后一个 tool 消息的副本（不改写存储历史）。"""
    result = list(request_msgs)
    for i in range(len(result) - 1, -1, -1):
        if result[i].role == "tool":
            m = result[i]
            result[i] = Message(
                "tool", (m.content or "") + "\n" + instruction, tool_call_id=m.tool_call_id
            )
            break
    return result


async def run_session(
    config: Config,
    tool_registry: ToolRegistry | None = None,
) -> None:
    """启动交互式对话会话。

    Args:
        config: 供应商配置
        tool_registry: 工具注册器（可选）
    """
    plan_mode = True
    stable_prompt = PromptBuilder(SECTIONS).build_stable()
    plan_injector: PlanModeInjector | None = PlanModeInjector(
        PLAN_FULL_INSTRUCTION, PLAN_MINIMAL_REMINDER
    )
    messages: list[Message] = []
    provider = create_provider(config)
    prompt_session = PromptSession(">>> ")

    render_system(f"MewCode v0.3.0 — {config.protocol} / {config.model}")
    if tool_registry:
        tools_count = len(tool_registry.get_schemas())
        render_system(f"已加载 {tools_count} 个工具")
    render_system(f"Plan Mode: {'开' if plan_mode else '关'}")
    render_system("输入 /help 查看命令，/exit 退出")

    current_task: asyncio.Task | None = None

    def cancel_current():
        nonlocal current_task
        if current_task and not current_task.done():
            current_task.cancel()
            print()

    while True:
        try:
            user_input = await prompt_session.prompt_async()
        except KeyboardInterrupt:
            cancel_current()
            continue
        except EOFError:
            break

        text = user_input.strip()
        if not text:
            continue

        # ---- 内置命令 ----
        if text in ("/exit", "/quit"):
            break
        if text == "/help":
            render_system("可用命令：")
            render_system("  /exit, /quit    — 退出")
            render_system("  /clear          — 清空对话历史")
            render_system("  /tools          — 列出已加载的工具")
            render_system("  /plan on|off    — 开关 Plan Mode")
            render_system("  /help           — 显示此帮助")
            continue
        if text == "/clear":
            messages = []
            if plan_injector:
                plan_injector.reset()
            render_system("对话历史已清空")
            continue
        if text == "/tools":
            if tool_registry:
                names = list(tool_registry._tools.keys())
                render_system(f"已加载工具: {', '.join(names)}")
            else:
                render_system("未加载工具")
            continue
        if text.startswith("/plan"):
            parts = text.split()
            if len(parts) == 2 and parts[1] == "on":
                plan_mode = True
                plan_injector = PlanModeInjector(PLAN_FULL_INSTRUCTION, PLAN_MINIMAL_REMINDER)
                render_system("Plan Mode: 开")
            elif len(parts) == 2 and parts[1] == "off":
                plan_mode = False
                plan_injector = None
                render_system("Plan Mode: 关")
            else:
                render_system(f"用法: /plan on 或 /plan off（当前: {'开' if plan_mode else '关'}）")
            continue
        if text.startswith("/"):
            render_error(f"未知命令：{text}")
            continue

        # ---- 正常对话 ----
        render_user_input(text)
        # 环境块 + Plan 指令注入：附加到 user 消息开头并持久化。
        # 持久化保证相邻轮次的首条 user 消息字节一致，缓存前缀稳定命中。
        prefix_parts = [format_environment(collect_environment())]
        if plan_injector is not None:
            prefix_parts.append(make_instruction(plan_injector.next()))
        user_content = "\n".join(prefix_parts) + "\n" + text
        messages.append(Message("user", user_content))

        try:
            current_task = asyncio.create_task(
                _run_agent_loop(provider, messages, config, tool_registry, stable_prompt)
            )
            await current_task
            current_task = None
        except asyncio.CancelledError:
            render_system("已中断")
            current_task = None


async def _run_agent_loop(
    provider,
    messages: list[Message],
    config: Config,
    tool_registry: ToolRegistry | None,
    stable_prompt: str,
) -> None:
    """执行一轮 Agent Loop：模型可连续调用工具直到给出文字回复。

    Args:
        provider: LLM Provider
        messages: 对话历史（不含 system；本函数会追加消息）
        config: 供应商配置
        tool_registry: 工具注册器
        stable_prompt: 稳定全局指令（可缓存前缀）
    """
    tools = tool_registry.get_schemas() if tool_registry else None
    confirmed_tools: set[str] = set()
    tool_call_count = 0
    gentle_sent = False

    for step in range(MAX_STEPS):
        # 组装本轮请求消息：稳定指令前置，历史在后
        # （环境块与 Plan 指令已在 run_session 中持久化到 user 消息，保证前缀稳定）
        request_msgs = [Message("system", stable_prompt)] + messages

        # 温和提醒：工具调用达阈值后，在下一轮请求时注入一次（附加到最后一条 tool result 副本）
        if tool_call_count >= GENTLE_REMINDER_THRESHOLD and not gentle_sent:
            request_msgs = _attach_to_last_tool(request_msgs, make_instruction(GENTLE_REMINDER))
            gentle_sent = True

        text_buffer = ""
        pending_tool_call: ToolCall | None = None
        stream_error: str | None = None

        # 一次性消费完整个 SSE 流，不做 break 退出
        async for event in provider.stream_chat(request_msgs, config, tools=tools):
            if event.type == "text":
                text_buffer += event.content
                stream_text(event.content)
            elif event.type == "tool_call":
                if text_buffer:
                    print()
                    text_buffer = ""
                tc_data = json.loads(event.content)
                pending_tool_call = ToolCall(**tc_data)
                # 继续消费完剩余流（清理连接），再处理 tool_call
            elif event.type == "usage":
                _render_usage(event.content)
            elif event.type == "error":
                stream_error = event.content

        # ---- 流结束后处理 ----
        if stream_error:
            if text_buffer:
                print()
            render_error(stream_error)
            return

        if pending_tool_call:
            render_tool_call(pending_tool_call.name, pending_tool_call.arguments)

            # 确认检查
            tool_def = tool_registry.get(pending_tool_call.name) if tool_registry else None
            if tool_def and tool_def.needs_confirmation and pending_tool_call.name not in confirmed_tools:
                render_tool_confirm(pending_tool_call.name, pending_tool_call.arguments)
                confirm = await _confirm_action("确认? [Enter/n] ")
                if confirm.strip().lower() in ("n", "no", "q", "quit"):
                    render_system("已取消工具调用")
                    messages.append(_make_assistant_tool_call_msg(pending_tool_call))
                    messages.append(
                        Message("tool", "用户取消了该工具调用", tool_call_id=pending_tool_call.id)
                    )
                    if step < MAX_STEPS - 1:
                        render_step_counter(step + 2, MAX_STEPS)
                    continue
                confirmed_tools.add(pending_tool_call.name)

            # 执行工具
            result = await tool_registry.execute(pending_tool_call.name, **pending_tool_call.arguments)
            tool_call_count += 1
            render_tool_result(result)
            messages.append(_make_assistant_tool_call_msg(pending_tool_call))
            messages.append(Message("tool", result, tool_call_id=pending_tool_call.id))

            if step < MAX_STEPS - 1:
                render_step_counter(step + 2, MAX_STEPS)
            continue

        # 模型输出文字（未触发 tool_call）→ 循环结束
        if text_buffer:
            print()
            messages.append(Message("assistant", text_buffer))
            return

    # 超出步数上限
    render_system(f"已达最大步数上限 ({MAX_STEPS})，如需继续请追问")


def _render_usage(content: str) -> None:
    """解析 usage 事件并展示缓存命中。"""
    try:
        usage = json.loads(content)
    except json.JSONDecodeError:
        return
    hit = usage.get("prompt_cache_hit_tokens", 0) or 0
    miss = usage.get("prompt_cache_miss_tokens", 0) or 0
    render_cache_hit(hit, miss)


def _make_assistant_tool_call_msg(tc: ToolCall) -> Message:
    """构造 assistant 的 tool_call 请求消息（OpenAI 格式）。"""
    return Message(
        role="assistant",
        content=None,
        tool_calls=[
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
        ],
    )
