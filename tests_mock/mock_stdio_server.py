"""测试用 stdio MCP server：在 stdin/stdout 上收发 JSON-RPC。

实现 initialize / tools/list / tools/call 三方法，供 MCP 客户端测试使用。
用法：python tests_mock/mock_stdio_server.py
"""

from __future__ import annotations

import json
import sys

TOOLS = [
    {
        "name": "read_file",
        "description": "Mock 远端读文件",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Mock 远端写文件",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
]


def _make_response(msg_id, result=None, error=None):
    resp = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


def handle(msg: dict) -> dict | None:
    """处理一条 JSON-RPC 消息；通知返回 None。"""
    if "id" not in msg:
        return None  # 通知，忽略
    mid = msg["id"]
    method = msg.get("method")
    if method == "initialize":
        return _make_response(
            mid,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "mock-stdio", "version": "1.0.0"},
            },
        )
    if method == "tools/list":
        return _make_response(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "read_file":
            return _make_response(
                mid,
                {"content": [{"type": "text", "text": f"mock content of {args.get('path')}"}], "isError": False},
            )
        if name == "write_file":
            return _make_response(
                mid,
                {"content": [{"type": "text", "text": f"mock wrote {args.get('content')} to {args.get('path')}"}], "isError": False},
            )
        return _make_response(mid, None, {"code": -32602, "message": f"未知工具: {name}"})
    return _make_response(mid, None, {"code": -32601, "message": f"方法不存在: {method}"})


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
