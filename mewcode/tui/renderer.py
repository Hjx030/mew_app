"""TUI 渲染工具。

基于 rich 的终端输出渲染函数，支持 markdown 显示、流式输出、工具调用展示。
"""

from __future__ import annotations

import json
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.style import Style
from rich.text import Text

# 全局 Console 实例 — 兼容 Windows 终端颜色
console = Console(force_terminal=True)


def stream_text(text: str) -> None:
    """流式输出文本片段（逐 token 使用，不换行）。"""
    sys.stdout.write(text)
    sys.stdout.flush()


def render_thinking(text: str) -> None:
    """显示思考过程（灰色斜体）。"""
    style = Style(dim=True, italic=True)
    console.print(Text(text, style=style), end="")


def render_markdown(text: str) -> None:
    """用 rich Markdown 渲染完整文本。"""
    if text.strip():
        console.print(Markdown(text))


def render_error(msg: str) -> None:
    """显示错误信息（红色）。"""
    console.print(f"[red]✖ {msg}[/red]")


def render_system(msg: str) -> None:
    """显示系统提示（蓝色）。"""
    console.print(f"[cyan]ℹ {msg}[/cyan]")


def render_user_input(text: str) -> None:
    """显示用户输入（绿色高亮 prompt）。"""
    console.print(f"[bold green]>>>[/bold green] {text}")


def render_tool_call(name: str, arguments: dict) -> None:
    """显示工具调用信息（黄色）。"""
    args_str = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    console.print(f"[yellow]🔧 调用工具: [bold]{name}[/bold]({args_str})[/yellow]")


def render_tool_result(result: str) -> None:
    """显示工具执行结果（灰色）。"""
    if "\n" in result:
        console.print("[dim]结果:[/dim]")
        # 只展示前 20 行
        lines = result.splitlines()
        display = "\n".join(lines[:20])
        if len(lines) > 20:
            display += f"\n... 还有 {len(lines) - 20} 行"
        console.print(f"[dim]{display}[/dim]")
    else:
        truncated = result[:200] + "..." if len(result) > 200 else result
        console.print(f"[dim]✅ {truncated}[/dim]")


def render_tool_confirm(name: str, arguments: dict) -> None:
    """显示工具确认提示（黄色加粗）。"""
    args_str = ", ".join(f"{k}={v!r}" for k, v in arguments.items())
    console.print(f"[bold yellow]⚠ 即将执行: {name}({args_str})[/bold yellow]")
    console.print("[yellow]按 [bold]回车[/bold] 确认，输入 [bold]n[/bold] 取消[/yellow]")


def render_step_counter(current: int, total: int = 10) -> None:
    """显示 Agent Loop 当前执行步数。"""
    console.print(f"[cyan]─── 步骤 {current}/{total} ───[/cyan]")


def render_cache_hit(hit: int, miss: int) -> None:
    """显示缓存命中统计（命中率高显示绿色，否则黄色）。"""
    total = hit + miss
    if total <= 0:
        console.print("[dim]缓存统计：无数据[/dim]")
        return
    rate = hit / total * 100
    color = "green" if rate > 50 else "yellow"
    console.print(
        f"[{color}]缓存命中 {hit} tokens / 未命中 {miss} tokens（命中率 {rate:.0f}%）[/{color}]"
    )
