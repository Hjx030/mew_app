"""OpenAI 兼容 API Provider。

支持 OpenAI 及其兼容协议（DeepSeek、vLLM、Ollama 等）。
支持 tool call（function calling）。
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from mewcode.config import Config
from mewcode.providers import BaseProvider, Message, StreamEvent


def _serialize_messages(messages: list[Message]) -> list[dict]:
    """将内部 Message 列表序列化为 OpenAI API 格式。"""
    result = []
    for m in messages:
        item: dict = {"role": m.role}
        if m.content is not None:
            item["content"] = m.content
        elif m.tool_calls:
            # tool_calls 消息必须显式设置 content: null
            item["content"] = None
        if m.tool_calls:
            item["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        result.append(item)
    return result


class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 API Provider。"""

    async def stream_chat(
        self,
        messages: list[Message],
        config: Config,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "content-type": "application/json",
        }
        body: dict = {
            "model": config.model,
            "messages": _serialize_messages(messages),
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        url = f"{config.base_url}/v1/chat/completions"

        async with httpx.AsyncClient(timeout=120, http2=False) as client:
            try:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        yield StreamEvent(
                            "error",
                            f"API 错误 ({resp.status_code}): {error_text.decode(errors='replace')}",
                        )
                        return

                    # 累积 tool_calls 的缓冲区（按 index 索引）
                    tool_calls_buffer: dict[int, dict] = {}
                    has_tool_calls = False

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:]
                        if payload.strip() == "[DONE]":
                            yield StreamEvent("done", "")
                            return
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # 处理 text delta（普通回复）
                        content = delta.get("content")
                        if content:
                            yield StreamEvent("text", content)

                        # 处理 tool_calls delta（工具调用）
                        tool_calls_delta = delta.get("tool_calls")
                        if tool_calls_delta:
                            has_tool_calls = True
                            for tc_delta in tool_calls_delta:
                                idx = tc_delta.get("index", 0)
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }
                                entry = tool_calls_buffer[idx]
                                if tc_delta.get("id"):
                                    entry["id"] = tc_delta["id"]
                                if tc_delta.get("function"):
                                    fn = tc_delta["function"]
                                    if fn.get("name"):
                                        entry["function"]["name"] += fn["name"]
                                    if fn.get("arguments"):
                                        entry["function"]["arguments"] += fn["arguments"]

                        # 处理 finish_reason
                        finish_reason = choices[0].get("finish_reason")
                        if finish_reason is not None:
                            if finish_reason == "tool_calls" and tool_calls_buffer:
                                # 组装为 ToolCall 事件
                                sorted_calls = [
                                    tool_calls_buffer[i]
                                    for i in sorted(tool_calls_buffer.keys())
                                ]
                                # 每个 tool_call 单独 yield
                                for tc in sorted_calls:
                                    try:
                                        args = json.loads(tc["function"]["arguments"])
                                    except json.JSONDecodeError:
                                        args = {}
                                    # 用 tool_tc.id 存完整 tool_call 信息
                                    call_data = {
                                        "id": tc["id"],
                                        "name": tc["function"]["name"],
                                        "arguments": args,
                                    }
                                    yield StreamEvent("tool_call", json.dumps(call_data, ensure_ascii=False))
                                yield StreamEvent("done", "")
                            else:
                                yield StreamEvent("done", "")

            except httpx.TimeoutException:
                yield StreamEvent("error", "请求超时，请检查网络连接和 API 响应时间")
            except httpx.RemoteProtocolError as e:
                yield StreamEvent("error", f"服务器断开: {e}。消息上下文可能过长")
            except httpx.RequestError as e:
                yield StreamEvent("error", f"请求失败: {e}")
