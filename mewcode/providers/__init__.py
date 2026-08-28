"""LLM Provider 抽象层。

定义统一的 Provider 接口和事件模型，各后端通过工厂函数按 protocol 分发。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

from mewcode.config import Config


@dataclass
class Message:
    """对话消息。"""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list | None = None       # assistant role 专用：工具调用请求
    tool_call_id: str | None = None      # tool role 专用：对应的工具调用 ID


@dataclass
class StreamEvent:
    """流式事件，屏蔽各后端协议差异。"""
    type: str   # "text" | "thinking" | "tool_call" | "done" | "error"
    content: str = field(default="")


class BaseProvider(ABC):
    """LLM Provider 抽象基类。"""

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[Message],
        config: Config,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式对话。

        Args:
            messages: 对话历史
            config: 供应商配置
            tools: OpenAI 兼容的 tools 参数列表（可选）

        Yields:
            StreamEvent — "text" | "thinking" | "tool_call" | "done" | "error"
        """
        ...


def create_provider(config: Config) -> BaseProvider:
    """工厂函数：按 config.protocol 创建对应的 Provider。

    Args:
        config: 供应商配置

    Returns:
        BaseProvider 实例

    Raises:
        ValueError: 不支持的 protocol
    """
    if config.protocol == "anthropic":
        from mewcode.providers.anthropic import AnthropicProvider
        return AnthropicProvider()
    elif config.protocol == "openai":
        from mewcode.providers.openai import OpenAIProvider
        return OpenAIProvider()
    else:
        raise ValueError(f"不支持的 protocol: '{config.protocol}'，可选: anthropic, openai")
