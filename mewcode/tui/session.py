"""会话主循环。

基于 prompt_toolkit 的交互式对话界面，支持 Agent Loop 和 Plan Mode。
Agent Loop：模型可连续调用工具（最多 10 步），直到主动给出文字回复。
Plan Mode：引导 AI 对复杂任务先出计划，用户确认后再执行。
"""

from __future__ import annotations

import asyncio
import json
import sys

from prompt_toolkit import PromptSession

from mewcode.config import Config
from mewcode.providers import Message
from mewcode.providers import create_provider
from mewcode.tools import ToolCall, ToolRegistry
from mewcode.tui.renderer import (
    render_error,
    render_step_counter,
    render_system,
    render_tool_call,
    render_tool_confirm,
    render_tool_result,
    render_user_input,
    stream_text,
)

BASE_SYSTEM_PROMPT = """You are MewCode, an AI coding assistant with file, code search, and shell command tools.

You can chain multiple tool calls to complete tasks. After each tool result, decide whether to call another tool or give the final answer. When the task is complete, summarize what was done."""

PLAN_MODE_INSTRUCTION = """
For multi-step tasks, first present a clear step-by-step plan to the user. Explain what you will do in each step. Then wait for the user to confirm before executing tools."""

MAX_STEPS = 10


async def _confirm_action(prompt_text: str) -> str:
    """在终端中等待用户确认。"""
    print(prompt_text, end="", flush=True)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sys.stdin.readline)


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
    messages: list[Message] = [Message("system", _build_system_prompt(plan_mode))]
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
            messages = [Message("system", _build_system_prompt(plan_mode))]
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
                messages.insert(0, Message("system", _build_system_prompt(True)))
                render_system("Plan Mode: 开")
            elif len(parts) == 2 and parts[1] == "off":
                plan_mode = False
                messages.insert(0, Message("system", _build_system_prompt(False)))
                render_system("Plan Mode: 关")
            else:
                render_system(f"用法: /plan on 或 /plan off（当前: {'开' if plan_mode else '关'}）")
            continue
        if text.startswith("/"):
            render_error(f"未知命令：{text}")
            continue

        # ---- 正常对话 ----
        render_user_input(text)
        messages.append(Message("user", text))

        try:
            current_task = asyncio.create_task(
                _run_agent_loop(provider, messages, config, tool_registry)
            )
            await current_task
            current_task = None
        except asyncio.CancelledError:
            render_system("已中断")
            current_task = None


def _build_system_prompt(plan_mode: bool) -> str:
    """根据 plan_mode 构造系统提示词。"""
    if plan_mode:
        return BASE_SYSTEM_PROMPT + PLAN_MODE_INSTRUCTION
    return BASE_SYSTEM_PROMPT


async def _run_agent_loop(
    provider,
    messages: list[Message],
    config: Config,
    tool_registry: ToolRegistry | None,
) -> None:
    """执行一轮 Agent Loop：模型可连续调用工具直到给出文字回复。"""
    tools = tool_registry.get_schemas() if tool_registry else None
    confirmed_tools: set[str] = set()

    for step in range(MAX_STEPS):
        text_buffer = ""
        pending_tool_call: ToolCall | None = None
        stream_error: str | None = None

        # 一次性消费完整个 SSE 流，不做 break 退出
        async for event in provider.stream_chat(messages, config, tools=tools):
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
