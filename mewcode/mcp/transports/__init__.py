"""MCP 传输层。"""

from __future__ import annotations

from mewcode.mcp.transports.base import Transport
from mewcode.mcp.transports.http import StreamableHttpTransport
from mewcode.mcp.transports.stdio import StdioTransport


def make_transport(config) -> Transport:
    """按配置创建传输实例。"""
    if config.transport == "stdio":
        return StdioTransport(config)
    if config.transport == "http":
        return StreamableHttpTransport(config)
    raise ValueError(f"未知 MCP 传输: {config.transport}")


__all__ = ["Transport", "StdioTransport", "StreamableHttpTransport", "make_transport"]
