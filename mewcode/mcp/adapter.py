"""MCP 远端工具适配层：包装成 MewCode Tool。"""

from __future__ import annotations

import re

from mewcode.tools.base import Tool


def _sanitize(name: str) -> str:
    """把名字规范化为 [a-zA-Z0-9_-]，其余替换为 _。"""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def make_mcp_tool(server_name: str, tool_info, client) -> Tool:
    """构造一个包装远端工具的 Tool 实例。"""
    tool_name = f"mcp_{_sanitize(server_name)}_{_sanitize(tool_info.name)}"
    return _McpTool(tool_name, tool_info, client, server_name)


class _McpTool(Tool):
    """把远端 MCP 工具包装成 MewCode 可调用的 Tool。"""

    def __init__(self, tool_name: str, tool_info, client, server_name: str) -> None:
        self.name = tool_name
        self._remote_name = tool_info.name
        self.description = tool_info.description or f"MCP 远端工具 {tool_info.name}"
        schema = dict(tool_info.input_schema or {})
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": schema.get("properties", {})}
        self.parameters = schema
        self._client = client
        self.server = server_name

    async def run(self, **kwargs) -> str:
        try:
            return await self._client.call_tool(self._remote_name, kwargs)
        except Exception as e:
            return f"错误: MCP 工具 {self.name} 调用失败: {e}"
