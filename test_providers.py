"""Provider 集成测试 — 模拟 HTTP 响应验证流式解析逻辑。"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mewcode.config import Config
from mewcode.providers import Message, StreamEvent, create_provider


def make_mock_stream(status_code: int, lines: list[str], error_body: bytes = b""):
    """创建一个模拟的 AsyncClient.stream() 上下文管理器。

    用法: patch.object(httpx.AsyncClient, 'stream', return_value=make_mock_stream(...))
    """
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.aiter_lines.return_value.__aiter__.return_value = iter(lines)
    mock_resp.aread.return_value = error_body

    cm = AsyncMock()
    cm.__aenter__.return_value = mock_resp
    cm.__aexit__.return_value = None
    return cm


def make_sse_data(data: object) -> str:
    """将对象包装成 SSE data: 行。"""
    import json
    return f"data: {json.dumps(data, ensure_ascii=False)}"


class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_basic_streaming(self):
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        provider = create_provider(config)

        lines = [
            make_sse_data({"choices": [{"delta": {"content": "你好"}, "finish_reason": None}]}),
            make_sse_data({"choices": [{"delta": {"content": "世界"}, "finish_reason": None}]}),
            make_sse_data({"choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]}),
            "data: [DONE]",
        ]

        with patch.object(httpx.AsyncClient, "stream", return_value=make_mock_stream(200, lines)):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config)]

        assert events[0].type == "text" and events[0].content == "你好"
        assert events[1].type == "text" and events[1].content == "世界"
        assert events[-1].type == "done"

    @pytest.mark.asyncio
    async def test_api_error(self):
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-bad")
        provider = create_provider(config)

        with patch.object(
            httpx.AsyncClient, "stream",
            return_value=make_mock_stream(401, [], error_body=b'{"error":"unauthorized"}'),
        ):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config)]

        assert len(events) == 1
        assert events[0].type == "error"
        assert "401" in events[0].content

    @pytest.mark.asyncio
    async def test_network_error(self):
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        provider = create_provider(config)

        with patch.object(httpx.AsyncClient, "stream", side_effect=httpx.NetworkError("connection refused")):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config)]

        assert len(events) == 1
        assert events[0].type == "error"
        assert "connection refused" in events[0].content.lower() or "网络错误" in events[0].content

    @pytest.mark.asyncio
    async def test_empty_choices_skipped(self):
        """验证空的 choices 被跳过不产生事件。"""
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        provider = create_provider(config)

        lines = [
            # 一些 API 可能在开始或结束时发空的 choices
            make_sse_data({"choices": []}),
            make_sse_data({"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}),
            "data: [DONE]",
        ]

        with patch.object(httpx.AsyncClient, "stream", return_value=make_mock_stream(200, lines)):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config)]

        # 空的 choices 不产生事件
        text_events = [e for e in events if e.type == "text"]
        assert len(text_events) == 1
        assert text_events[0].content == "hello"

    @pytest.mark.asyncio
    async def test_usage_event(self):
        """验证含 usage 的最终块（choices 为空）被解析为 usage 事件。"""
        import json

        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        provider = create_provider(config)

        lines = [
            make_sse_data({"choices": [{"delta": {"content": "hi"}, "finish_reason": "stop"}]}),
            make_sse_data({
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "prompt_cache_hit_tokens": 90,
                    "prompt_cache_miss_tokens": 10,
                    "completion_tokens": 5,
                },
            }),
            "data: [DONE]",
        ]

        with patch.object(httpx.AsyncClient, "stream", return_value=make_mock_stream(200, lines)):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config)]

        usage_events = [e for e in events if e.type == "usage"]
        assert len(usage_events) == 1, f"期望 1 个 usage 事件，实际 {len(usage_events)}"
        usage = json.loads(usage_events[0].content)
        assert usage["prompt_cache_hit_tokens"] == 90
        assert usage["prompt_cache_miss_tokens"] == 10


class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_basic_streaming(self):
        config = Config("anthropic", "claude-sonnet-5", "https://api.anthropic.com", "sk-test")
        provider = create_provider(config)

        lines = [
            make_sse_data({"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "..."}}),
            make_sse_data({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "你好"}, "index": 1}),
            make_sse_data({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "世界"}, "index": 1}),
            make_sse_data({"type": "message_stop"}),
        ]

        with patch.object(httpx.AsyncClient, "stream", return_value=make_mock_stream(200, lines)):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config)]

        assert events[0].type == "thinking"
        assert events[1].type == "text" and events[1].content == "你好"
        assert events[2].type == "text" and events[2].content == "世界"
        assert events[-1].type == "done"

    @pytest.mark.asyncio
    async def test_extended_thinking_enabled(self):
        """model 含 thinking 时，请求体应有 thinking 字段。"""
        config = Config("anthropic", "claude-sonnet-5-thinking", "https://api.anthropic.com", "sk-test")
        provider = create_provider(config)

        captured_args = {}

        def capture_side_effect(method, url, **kwargs):
            captured_args["json"] = kwargs.get("json", {})
            return make_mock_stream(200, [make_sse_data({"type": "message_stop"})])

        with patch.object(httpx.AsyncClient, "stream", side_effect=capture_side_effect):
            async for _ in provider.stream_chat([Message("user", "hi")], config):
                pass

        body = captured_args.get("json", {})
        assert "thinking" in body
        assert body["thinking"]["type"] == "enabled"

    @pytest.mark.asyncio
    async def test_system_prompt_separated(self):
        """system prompt 应从 messages 中分离到独立字段。"""
        config = Config("anthropic", "claude-sonnet-5", "https://api.anthropic.com", "sk-test")
        provider = create_provider(config)

        captured_args = {}

        def capture_side_effect(method, url, **kwargs):
            captured_args["json"] = kwargs.get("json", {})
            return make_mock_stream(200, [make_sse_data({"type": "message_stop"})])

        with patch.object(httpx.AsyncClient, "stream", side_effect=capture_side_effect):
            messages = [
                Message("system", "You are a helpful assistant."),
                Message("user", "hello"),
            ]
            async for _ in provider.stream_chat(messages, config):
                pass

        body = captured_args.get("json", {})
        assert body.get("system") == "You are a helpful assistant."
        assert body["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_api_error(self):
        config = Config("anthropic", "claude-sonnet-5", "https://api.anthropic.com", "sk-bad")
        provider = create_provider(config)

        with patch.object(
            httpx.AsyncClient, "stream",
            return_value=make_mock_stream(401, [], error_body=b'{"error":"unauthorized"}'),
        ):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config)]

        assert len(events) == 1
        assert events[0].type == "error"


class TestFactory:
    def test_unknown_protocol(self):
        config = Config("unknown", "x", "x", "x")
        with pytest.raises(ValueError, match="unknown"):
            create_provider(config)

    def test_anthropic_provider(self):
        config = Config("anthropic", "claude-sonnet-5", "https://api.anthropic.com", "sk-test")
        from mewcode.providers.anthropic import AnthropicProvider
        assert isinstance(create_provider(config), AnthropicProvider)

    def test_openai_provider(self):
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        from mewcode.providers.openai import OpenAIProvider
        assert isinstance(create_provider(config), OpenAIProvider)


class TestToolCallParsing:
    """Tool call 流式解析测试。"""

    @pytest.mark.asyncio
    async def test_single_tool_call_streaming(self):
        """验证单 tool_call 流式增量累积和解析。"""
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        provider = create_provider(config)

        # DeepSeek/OpenAI 流式中 tool_calls 的典型增量序列
        lines = [
            make_sse_data({
                "choices": [{
                    "delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": ""}}]},
                    "finish_reason": None,
                }]
            }),
            make_sse_data({
                "choices": [{
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"path": "'}}]},
                    "finish_reason": None,
                }]
            }),
            make_sse_data({
                "choices": [{
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'config.yaml"}'}}]},
                    "finish_reason": None,
                }]
            }),
            make_sse_data({
                "choices": [{"delta": {}, "finish_reason": "tool_calls"}]
            }),
            "data: [DONE]",
        ]

        with patch.object(httpx.AsyncClient, "stream", return_value=make_mock_stream(200, lines)):
            events = [e async for e in provider.stream_chat([Message("user", "读文件")], config)]

        tool_events = [e for e in events if e.type == "tool_call"]
        assert len(tool_events) == 1, f"Expected 1 tool_call event, got {len(tool_events)}"

        import json
        tc = json.loads(tool_events[0].content)
        assert tc["name"] == "read_file"
        assert tc["arguments"]["path"] == "config.yaml"
        assert tc["id"] == "call_1"

    @pytest.mark.asyncio
    async def test_tools_in_request_body(self):
        """验证 tools 参数出现在请求体中。"""
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        provider = create_provider(config)

        captured_args = {}

        def capture(method, url, **kwargs):
            captured_args["json"] = kwargs.get("json", {})
            return make_mock_stream(200, [make_sse_data({"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]}), "data: [DONE]"])

        tools = [{
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读文件",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }]

        with patch.object(httpx.AsyncClient, "stream", side_effect=capture):
            async for _ in provider.stream_chat([Message("user", "hi")], config, tools=tools):
                pass

        body = captured_args.get("json", {})
        assert "tools" in body
        assert body["tools"] == tools

    @pytest.mark.asyncio
    async def test_text_response_with_tools_available(self):
        """验证当模型选择不调用工具时，行为与普通文本回复一致。"""
        config = Config("openai", "deepseek-chat", "https://api.deepseek.com", "sk-test")
        provider = create_provider(config)

        lines = [
            make_sse_data({"choices": [{"delta": {"content": "你好"}, "finish_reason": None}]}),
            make_sse_data({"choices": [{"delta": {"content": "世界"}, "finish_reason": "stop"}]}),
            "data: [DONE]",
        ]

        tools = [{"type": "function", "function": {"name": "test", "parameters": {}}}]

        with patch.object(httpx.AsyncClient, "stream", return_value=make_mock_stream(200, lines)):
            events = [e async for e in provider.stream_chat([Message("user", "hi")], config, tools=tools)]

        text_events = [e for e in events if e.type == "text"]
        assert len(text_events) == 2
        assert "你好" in text_events[0].content
        assert events[-1].type == "done"

    @pytest.mark.asyncio
    async def test_tool_call_message_serialization(self):
        """验证带有 tool_calls 和 tool 角色的消息正确序列化。"""
        from mewcode.providers.openai import _serialize_messages

        msgs = [
            Message("system", "You are an assistant."),
            Message("user", "Read the file"),
            Message(
                "assistant",
                content=None,
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "test.txt"}'},
                }],
            ),
            Message("tool", "file content", tool_call_id="call_1"),
        ]

        serialized = _serialize_messages(msgs)
        assert len(serialized) == 4
        assert serialized[0]["role"] == "system"
        assert serialized[2]["role"] == "assistant"
        # Assistant 带 tool_calls 时必须有 content: null
        assert serialized[2]["content"] is None, "tool_calls 消息应显式设置 content: null"
        assert "tool_calls" in serialized[2]
        assert serialized[3]["role"] == "tool"
        assert serialized[3]["tool_call_id"] == "call_1"
        assert serialized[3]["content"] == "file content"


class TestToolSystem:
    """工具系统测试。"""

    def test_tool_registry(self):
        from mewcode.tools import ToolRegistry, Tool

        reg = ToolRegistry()
        t = Tool()
        t.name = "test_tool"
        t.description = "A test tool"
        t.parameters = {"type": "object", "properties": {"x": {"type": "string"}}}
        reg.register(t)

        assert reg.get("test_tool") is t
        schemas = reg.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_tool_execute(self):
        from mewcode.tools import ToolRegistry, Tool

        class MyTool(Tool):
            name = "my_tool"
            description = ""
            parameters = {}

            async def run(self, msg: str = "") -> str:
                return f"executed: {msg}"

        reg = ToolRegistry()
        reg.register(MyTool())

        result = await reg.execute("my_tool", msg="hello")
        assert result == "executed: hello"

    @pytest.mark.asyncio
    async def test_tool_execute_unknown(self):
        from mewcode.tools import ToolRegistry

        reg = ToolRegistry()
        result = await reg.execute("nonexistent")
        assert "未知" in result

    @pytest.mark.asyncio
    async def test_tool_execute_error(self):
        from mewcode.tools import ToolRegistry, Tool

        class BrokenTool(Tool):
            name = "broken"
            description = ""
            parameters = {}
            async def run(self, **kwargs) -> str:
                raise RuntimeError("something broke")

        reg = ToolRegistry()
        reg.register(BrokenTool())
        result = await reg.execute("broken")
        assert "错误" in result

    def test_tool_needs_confirmation(self):
        from mewcode.tools import Bash
        assert Bash().needs_confirmation is True

    def test_read_file_tool(self):
        from mewcode.tools import ReadFile
        t = ReadFile()
        assert t.name == "read_file"
        assert "path" in t.parameters["required"]

    def test_write_file_tool(self):
        from mewcode.tools import WriteFile
        t = WriteFile()
        assert t.name == "write_file"
        assert "content" in t.parameters["required"]

    def test_edit_file_tool(self):
        from mewcode.tools import EditFile
        t = EditFile()
        assert t.name == "edit_file"

    def test_glob_tool(self):
        from mewcode.tools import Glob
        t = Glob()
        assert t.name == "glob"
        assert "pattern" in t.parameters["required"]

    def test_grep_tool(self):
        from mewcode.tools import Grep
        t = Grep()
        assert t.name == "grep"
        assert "pattern" in t.parameters["required"]

    @pytest.mark.asyncio
    async def test_read_file_integration(self):
        """实际读写文件验证工具功能。"""
        import tempfile, os
        from mewcode.tools import ReadFile, WriteFile

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            # 先写
            w = WriteFile()
            result = await w.run(path=path, content="Hello World")
            assert "成功" in result
            # 再读
            r = ReadFile()
            content = await r.run(path=path)
            assert content == "Hello World"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
