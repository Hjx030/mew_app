"""Anthropic Claude API Provider。

实现 Claude Messages API 的流式对话，支持 extended thinking。
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from mewcode.config import Config
from mewcode.providers import BaseProvider, Message, StreamEvent


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API Provider。"""

    async def stream_chat(
        self,
        messages: list[Message],
        config: Config,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        # Anthropic tool use 暂不支持（v0.2 专注 OpenAI/DeepSeek）
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Anthropic API: system prompt 是独立字段，不在 messages 数组中
        system_prompt = None
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        body: dict = {
            "model": config.model,
            "max_tokens": 4096,
            "messages": api_messages,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt

        # Extended thinking: 当 model 名称包含 "thinking" 时启用
        if "thinking" in config.model.lower():
            body["thinking"] = {"type": "enabled", "budget_tokens": 16000}

        url = f"{config.base_url}/v1/messages"

        async with httpx.AsyncClient(timeout=120) as client:
            try:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        yield StreamEvent(
                            "error",
                            f"Anthropic API 错误 ({resp.status_code}): {error_text.decode(errors='replace')}",
                        )
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        event_type = data.get("type", "")

                        if event_type == "content_block_delta":
                            delta = data.get("delta", {})
                            delta_type = delta.get("type", "")
                            if delta_type == "text_delta":
                                yield StreamEvent("text", delta.get("text", ""))
                            elif delta_type == "thinking_delta":
                                yield StreamEvent("thinking", delta.get("thinking", ""))
                        elif event_type == "message_stop":
                            yield StreamEvent("done", "")
                        elif event_type == "error":
                            err = data.get("error", {})
                            yield StreamEvent("error", err.get("message", "Unknown Anthropic error"))

            except httpx.TimeoutException:
                yield StreamEvent("error", "请求超时，请检查网络连接和 API 响应时间")
            except httpx.RemoteProtocolError as e:
                yield StreamEvent("error", f"服务器断开: {e}")
            except httpx.RequestError as e:
                yield StreamEvent("error", f"请求失败: {e}")
