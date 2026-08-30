"""MCP 客户端端到端测试（stdio + Streamable HTTP，用 mock server）。"""

import asyncio
import json
import os
import sys

import pytest

from mewcode.mcp.client import ConnectionPool, McpClient
from mewcode.mcp.config import HttpServerConfig, StdioServerConfig
from tests_mock.mock_stdio_server import handle as mcp_handle

MOCK_PATH = os.path.join(os.path.dirname(__file__), "tests_mock", "mock_stdio_server.py")


def make_stdio_config():
    return StdioServerConfig(
        name="mock",
        command=sys.executable,
        args=[MOCK_PATH],
        timeout_s=10,
    )


class TestStdioClient:
    @pytest.mark.asyncio
    async def test_three_phases(self):
        config = make_stdio_config()
        client = McpClient(config)
        await client.connect()
        await client.initialize()
        assert client.protocol_version == "2025-06-18"
        assert client.server_info["name"] == "mock-stdio"

        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert names == {"read_file", "write_file"}

        result = await client.call_tool("read_file", {"path": "a.txt"})
        assert "mock content of a.txt" in result

        result2 = await client.call_tool("write_file", {"path": "b.txt", "content": "hi"})
        assert "mock wrote hi to b.txt" in result2

        await client.close()

    @pytest.mark.asyncio
    async def test_call_error_is_raised(self):
        config = make_stdio_config()
        client = McpClient(config)
        await client.connect()
        await client.initialize()
        with pytest.raises(Exception):
            await client.call_tool("nonexistent", {})
        await client.close()


class TestPoolReuse:
    @pytest.mark.asyncio
    async def test_same_client_reused(self):
        pool = ConnectionPool()
        config = make_stdio_config()
        c1 = await pool.get(config)
        c2 = await pool.get(config)
        assert c1 is c2, "池化应返回同一个客户端"
        await pool.close_all()


class HttpMockServer:
    """用 asyncio 实现的极简 Streamable HTTP mock。"""

    def __init__(self):
        self.requests = []  # 记录收到的 (method, session_id)

    async def start(self):
        self.server = await asyncio.start_server(self._handler, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/mcp"

    async def _handler(self, reader, writer):
        try:
            request_line = await reader.readline()
            headers = {}
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                k, _, v = line.decode("utf-8", errors="replace").partition(":")
                headers[k.strip().lower()] = v.strip()
            parts = request_line.decode("utf-8", errors="replace").split()
            method = parts[0] if parts else ""
            path = parts[1] if len(parts) > 1 else "/"
            self.requests.append((method, headers.get("mcp-session-id")))

            if method == "DELETE":
                await self._respond(writer, b"", content_type="application/json", session=True)
                return

            cl = int(headers.get("content-length", 0) or 0)
            body = await reader.readexactly(cl) if cl else b""
            msg = json.loads(body) if body else {}
            resp = mcp_handle(msg)
            payload = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            if "sse=1" in path:
                sse_body = f"data: {payload.decode()}\n\n".encode("utf-8")
                await self._respond(writer, sse_body, content_type="text/event-stream", session=True)
            else:
                await self._respond(writer, payload, content_type="application/json", session=True)
        except Exception as e:
            import traceback

            traceback.print_exc()
        finally:
            writer.close()

    async def _respond(self, writer, payload, content_type, session=False):
        headers = [
            "HTTP/1.1 200 OK",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(payload)}",
        ]
        if session:
            headers.append("Mcp-Session-Id: mock-http-session")
        headers += ["", ""]
        writer.write("\r\n".join(headers).encode("utf-8") + payload)
        await writer.drain()

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()


class TestHttpClient:
    @pytest.mark.asyncio
    async def test_three_phases_and_session_header(self):
        mock = HttpMockServer()
        await mock.start()
        try:
            config = HttpServerConfig(name="http-mock", url=mock.url, timeout_s=10)
            client = McpClient(config)
            await client.connect()
            await client.initialize()
            assert client.protocol_version == "2025-06-18"

            tools = await client.list_tools()
            assert len(tools) == 2

            result = await client.call_tool("read_file", {"path": "x.txt"})
            assert "mock content of x.txt" in result

            await client.close()

            # 会话头回传验证：非 initialize 请求都应带上 Mcp-Session-Id
            methods = [m for m, _ in mock.requests if m == "POST"]
            assert len(methods) >= 3
            post_sessions = [sid for m, sid in mock.requests if m == "POST"]
            # 除第一个（initialize，会话头未建立）外，其余应带会话头
            assert any(sid == "mock-http-session" for sid in post_sessions[1:])
        finally:
            await mock.stop()

    @pytest.mark.asyncio
    async def test_sse_response(self):
        mock = HttpMockServer()
        await mock.start()
        try:
            config = HttpServerConfig(name="http-sse", url=mock.url + "?sse=1", timeout_s=10)
            client = McpClient(config)
            await client.connect()
            await client.initialize()
            tools = await client.list_tools()
            assert len(tools) == 2
            await client.close()
        finally:
            await mock.stop()
