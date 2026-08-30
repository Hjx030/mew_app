"""MCP 配置解析单测。"""

import os
import tempfile

import pytest

from mewcode.mcp.config import (
    DEFAULT_MCP_CONFIG,
    HttpServerConfig,
    StdioServerConfig,
    load_mcp_config,
)


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class TestLoadMcpConfig:
    def test_stdio_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mcp.yaml")
            _write(
                path,
                """servers:
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem"]
    env: {FOO: bar}
    timeout_s: 15
""",
            )
            cfgs = load_mcp_config(path)
            assert len(cfgs) == 1
            cfg = cfgs[0]
            assert isinstance(cfg, StdioServerConfig)
            assert cfg.name == "filesystem"
            assert cfg.command == "npx"
            assert cfg.args == ["-y", "@modelcontextprotocol/server-filesystem"]
            assert cfg.env == {"FOO": "bar"}
            assert cfg.timeout_s == 15

    def test_http_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mcp.yaml")
            _write(
                path,
                """servers:
  github:
    transport: http
    url: https://example.com/mcp
    headers: {Authorization: "Bearer xyz"}
""",
            )
            cfgs = load_mcp_config(path)
            assert len(cfgs) == 1
            cfg = cfgs[0]
            assert isinstance(cfg, HttpServerConfig)
            assert cfg.url == "https://example.com/mcp"
            assert cfg.headers == {"Authorization": "Bearer xyz"}

    def test_explicit_missing_path_raises(self):
        with pytest.raises(ValueError):
            load_mcp_config("/nonexistent/mcp_servers.yaml")

    def test_default_missing_returns_empty(self, monkeypatch):
        monkeypatch.setattr("mewcode.mcp.config.DEFAULT_MCP_CONFIG", "/nonexistent/default.yaml")
        assert load_mcp_config() == []

    def test_bad_entry_skipped_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mcp.yaml")
            _write(
                path,
                """servers:
  good:
    transport: stdio
    command: python
  bad:
    transport: stdio
  worse:
    transport: flying
""",
            )
            cfgs = load_mcp_config(path)
            assert len(cfgs) == 1
            assert cfgs[0].name == "good"

    def test_unparseable_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mcp.yaml")
            _write(path, "not: [valid\n  yaml: {{")
            with pytest.raises(ValueError):
                load_mcp_config(path)
