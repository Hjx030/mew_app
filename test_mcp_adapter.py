"""MCP 适配层测试：工具名规范化、注册、调用转发。"""

import pytest

from mewcode.mcp.adapter import make_mcp_tool
from mewcode.mcp.client import ToolInfo
from mewcode.tools import ToolRegistry


class FakeClient:
    def __init__(self, result="mock-result"):
        self.calls = []
        self.result = result

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.result


def make_info(name="read-file", description="读文件", schema=None):
    return ToolInfo(
        name=name,
        description=description,
        input_schema=schema or {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )


class TestNameSanitize:
    def test_hyphen_preserved(self):
        # 连字符在 OpenAI 函数名合法集合 [a-zA-Z0-9_-] 内，保留
        tool = make_mcp_tool("file-system", make_info("read-file"), FakeClient())
        assert tool.name == "mcp_file-system_read-file"

    def test_dots_sanitized(self):
        tool = make_mcp_tool("github.api", make_info("get.repo"), FakeClient())
        assert tool.name == "mcp_github_api_get_repo"

    def test_invalid_chars_replaced(self):
        tool = make_mcp_tool("file system!", make_info("read_file"), FakeClient())
        assert tool.name == "mcp_file_system__read_file"


class TestRegistration:
    def test_registered_in_registry(self):
        client = FakeClient()
        tool = make_mcp_tool("fs", make_info("read_file"), client)
        reg = ToolRegistry()
        reg.register(tool)
        schemas = reg.get_schemas()
        names = {s["function"]["name"] for s in schemas}
        assert "mcp_fs_read_file" in names
        assert reg.get("mcp_fs_read_file") is tool

    def test_parameters_passthrough(self):
        schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }
        tool = make_mcp_tool("fs", make_info("read_file", schema=schema), FakeClient())
        assert tool.parameters == schema

    def test_non_object_schema_wrapped(self):
        tool = make_mcp_tool("fs", make_info("x", schema={"type": "string"}), FakeClient())
        assert tool.parameters["type"] == "object"


class TestCallForwarding:
    @pytest.mark.asyncio
    async def test_forwards_to_remote(self):
        client = FakeClient("remote says hi")
        tool = make_mcp_tool("fs", make_info("read_file"), client)
        result = await tool.run(path="a.txt")
        assert result == "remote says hi"
        assert client.calls == [("read_file", {"path": "a.txt"})]

    @pytest.mark.asyncio
    async def test_error_wrapped(self):
        class BrokenClient:
            async def call_tool(self, name, arguments):
                raise RuntimeError("boom")

        tool = make_mcp_tool("fs", make_info("read_file"), BrokenClient())
        result = await tool.run(path="a.txt")
        assert "错误" in result and "boom" in result
