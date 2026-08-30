"""MCP server 配置模型与加载。"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

import yaml

DEFAULT_MCP_CONFIG = os.path.join(str(pathlib.Path.home()), ".config", "mewcode", "mcp_servers.yaml")


@dataclass
class StdioServerConfig:
    """本地子进程传输的 server 配置。"""

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)
    timeout_s: float = 30


@dataclass
class HttpServerConfig:
    """Streamable HTTP 传输的 server 配置。"""

    name: str
    transport: str = "http"
    url: str = ""
    headers: dict = field(default_factory=dict)
    timeout_s: float = 30
    proxy: str | None = None  # 显式代理；缺省直连（trust_env=False）


McpServerConfig = StdioServerConfig | HttpServerConfig


def _parse_entry(name: str, data: dict) -> McpServerConfig | None:
    """解析单个 server 条目，格式错误返回 None（调用方打印警告）。"""
    transport = data.get("transport")
    try:
        timeout = float(data.get("timeout_s", 30))
    except (TypeError, ValueError):
        timeout = 30
    if transport == "stdio":
        command = data.get("command")
        if not command:
            print(f"[mcp] 跳过 server '{name}': stdio 缺少 command")
            return None
        return StdioServerConfig(
            name=name,
            command=command,
            args=list(data.get("args", []) or []),
            env=dict(data.get("env", {}) or {}),
            timeout_s=timeout,
        )
    if transport == "http":
        url = data.get("url")
        if not url:
            print(f"[mcp] 跳过 server '{name}': http 缺少 url")
            return None
        return HttpServerConfig(
            name=name,
            url=url,
            headers=dict(data.get("headers", {}) or {}),
            timeout_s=timeout,
            proxy=data.get("proxy") or None,
        )
    print(f"[mcp] 跳过 server '{name}': 未知 transport '{transport}'")
    return None


def load_mcp_config(path: str | None = None) -> list[McpServerConfig]:
    """加载 MCP server 配置。

    - path 缺省读默认文件（~/.config/mewcode/mcp_servers.yaml，不存在返回空列表）
    - 显式指定的 path 缺失或文件不可解析 → 抛 ValueError
    - 单个条目格式错误 → 警告并跳过（不阻塞其余）
    """
    if path is None:
        path = DEFAULT_MCP_CONFIG
    if not os.path.isfile(path):
        if path == DEFAULT_MCP_CONFIG:
            return []
        raise ValueError(f"MCP 配置文件未找到: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        raise ValueError(f"MCP 配置文件解析失败: {path}: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"MCP 配置文件格式错误: {path}")
    servers_raw = data.get("servers", {})
    if not isinstance(servers_raw, dict):
        raise ValueError(f"MCP 配置文件缺少 servers 映射: {path}")
    result: list[McpServerConfig] = []
    for name, entry in servers_raw.items():
        if not isinstance(entry, dict):
            print(f"[mcp] 跳过 server '{name}': 条目不是映射")
            continue
        cfg = _parse_entry(name, entry)
        if cfg:
            result.append(cfg)
    return result
