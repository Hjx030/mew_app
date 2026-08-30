"""MCP 客户端：握手、工具发现、工具调用、连接池。"""

from __future__ import annotations

from dataclasses import dataclass

from mewcode.mcp.transports import make_transport

MCP_PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "mewcode"
CLIENT_VERSION = "0.3.0"


@dataclass
class ToolInfo:
    """远端工具信息。"""

    name: str
    description: str
    input_schema: dict


class McpError(Exception):
    """MCP 调用错误（含 JSON-RPC error）。"""


class McpClient:
    """一个 MCP server 的客户端会话。"""

    def __init__(self, config) -> None:
        self._config = config
        self._transport = make_transport(config)
        self._next_id = 0
        self.server_info: dict = {}
        self.protocol_version: str | None = None

    async def connect(self) -> None:
        await self._transport.connect()

    def _next_request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        return {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}

    async def _request(self, method: str, params: dict | None = None) -> dict:
        msg = self._next_request(method, params or {})
        resp = await self._transport.request(msg)
        if "error" in resp:
            err = resp["error"]
            raise McpError(f"MCP 方法 {method} 错误 ({err.get('code')}): {err.get('message')}")
        return resp.get("result", {})

    async def _notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        await self._transport.notify(msg)

    async def initialize(self) -> None:
        """握手：initialize → notifications/initialized。"""
        result = await self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        )
        self.protocol_version = result.get("protocolVersion")
        self.server_info = result.get("serverInfo", {})
        await self._notify("notifications/initialized")

    async def list_tools(self) -> list[ToolInfo]:
        """工具发现，支持 cursor 分页直到取完。"""
        tools: list[ToolInfo] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = await self._request("tools/list", params)
            for t in result.get("tools", []) or []:
                tools.append(
                    ToolInfo(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    )
                )
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        """调用远端工具，返回格式化文本结果。"""
        result = await self._request("tools/call", {"name": name, "arguments": arguments})
        parts = []
        for item in result.get("content", []) or []:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        text = "\n".join(parts)
        if result.get("isError"):
            text = f"(远端工具错误) {text}"
        return text if text else "(无输出)"

    async def close(self) -> None:
        await self._transport.close()


class ConnectionPool:
    """按 server 名缓存 McpClient，避免重复连接。"""

    def __init__(self) -> None:
        self._clients: dict[str, McpClient] = {}

    async def get(self, config) -> McpClient:
        """获取（或创建并初始化）某个 server 的客户端。"""
        client = self._clients.get(config.name)
        if client is None:
            client = McpClient(config)
            await client.connect()
            await client.initialize()
            self._clients[config.name] = client
        return client

    def has(self, name: str) -> bool:
        return name in self._clients

    def servers(self) -> list[str]:
        return list(self._clients.keys())

    async def close_all(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()
