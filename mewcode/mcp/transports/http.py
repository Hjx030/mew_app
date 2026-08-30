"""Streamable HTTP 传输（MCP 2025-06-18）。"""

from __future__ import annotations

import json

import httpx

from mewcode.mcp.transports.base import Transport

MCP_PROTOCOL_VERSION = "2025-06-18"


class StreamableHttpTransport(Transport):
    """MCP Streamable HTTP 传输。

    单端点 POST JSON-RPC；响应可能为 application/json 或 text/event-stream。
    会话用 Mcp-Session-Id 头管理；close 时 DELETE 结束会话。
    """

    def __init__(self, config) -> None:
        self._config = config
        self._session_id: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        # trust_env=False：不走系统代理（Windows 注册表代理会劫持 localhost → 502）；
        # 需要代理时在配置里显式指定 proxy。
        self._client = httpx.AsyncClient(
            timeout=self._config.timeout_s,
            proxy=self._config.proxy,
            trust_env=False,
        )

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            **self._config.headers,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def request(self, msg: dict) -> dict:
        assert self._client is not None
        resp = await self._client.post(self._config.url, json=msg, headers=self._headers())
        new_session = resp.headers.get("Mcp-Session-Id")
        if new_session:
            self._session_id = new_session
        if resp.status_code == 404:
            raise ConnectionError("MCP 会话已失效 (404)")
        if resp.status_code == 405:
            raise ConnectionError("MCP 方法不支持 (405)")
        if resp.status_code != 200:
            raise ConnectionError(f"HTTP 错误 ({resp.status_code}): {resp.text[:200]}")
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            return self._parse_sse(resp.text, msg.get("id"))
        return resp.json()

    @staticmethod
    def _parse_sse(body: str, msg_id) -> dict:
        for block in body.split("\n\n"):
            for line in block.splitlines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if data.get("id") == msg_id:
                        return data
        raise ConnectionError("SSE 响应中未找到匹配的响应消息")

    async def notify(self, msg: dict) -> None:
        assert self._client is not None
        await self._client.post(self._config.url, json=msg, headers=self._headers())

    async def close(self) -> None:
        assert self._client is not None
        if self._session_id:
            try:
                await self._client.request("DELETE", self._config.url, headers=self._headers())
            except Exception:
                pass
        await self._client.aclose()
        self._client = None
