"""MewCode MCP 客户端：连接外部 MCP server，把远端工具包装成本地 Tool。"""

from __future__ import annotations

from mewcode.mcp.adapter import make_mcp_tool
from mewcode.mcp.client import ConnectionPool, McpClient, ToolInfo
from mewcode.mcp.config import (
    DEFAULT_MCP_CONFIG,
    HttpServerConfig,
    StdioServerConfig,
    load_mcp_config,
)


async def discover(config_path: str | None = None, pool: ConnectionPool | None = None):
    """连接所有配置的 MCP server，发现并包装远端工具。

    Args:
        config_path: mcp_servers.yaml 路径（缺省用默认全局文件）
        pool: 外部传入的连接池（便于调用方管理生命周期）；缺省新建

    Returns:
        (tools, errors)：注册用的 Tool 列表 + 失败 server 的错误提示列表
    """
    configs = load_mcp_config(config_path)
    pool = pool or ConnectionPool()
    tools: list = []
    errors: list[str] = []
    for cfg in configs:
        try:
            client = await pool.get(cfg)
            infos = await client.list_tools()
            for info in infos:
                tools.append(make_mcp_tool(cfg.name, info, client))
        except Exception as e:
            errors.append(f"MCP server '{cfg.name}' 连接失败: {e}")
    return tools, errors


__all__ = [
    "discover",
    "McpClient",
    "ConnectionPool",
    "ToolInfo",
    "load_mcp_config",
    "DEFAULT_MCP_CONFIG",
    "StdioServerConfig",
    "HttpServerConfig",
    "make_mcp_tool",
]
