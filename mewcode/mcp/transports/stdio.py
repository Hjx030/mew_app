"""stdio 传输：子进程 stdin/stdout，newline-delimited JSON。"""

from __future__ import annotations

import asyncio
import json

from mewcode.mcp.transports.base import Transport


class StdioTransport(Transport):
    """通过子进程 stdin/stdout 收发 JSON-RPC 消息。

    读者任务持续读 stdout，按消息 id 关联到 pending future（F6）。
    """

    def __init__(self, config) -> None:
        self._config = config
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._closed = False

    async def connect(self) -> None:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                self._config.command,
                *self._config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._config.env or None,
            )
        except FileNotFoundError as e:
            raise ConnectionError(f"MCP 命令不存在: {self._config.command}") from e
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if not future.done():
                        future.set_result(msg)
        finally:
            self._fail_all("MCP server 子进程已退出")

    def _fail_all(self, reason: str) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(ConnectionError(reason))
        self._pending.clear()

    async def request(self, msg: dict) -> dict:
        assert self._proc and self._proc.stdin
        if self._closed:
            raise ConnectionError("MCP 传输已关闭")
        msg_id = msg.get("id")
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        try:
            self._proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            await self._proc.stdin.drain()
            return await asyncio.wait_for(future, timeout=self._config.timeout_s)
        except asyncio.TimeoutError as e:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"等待 MCP 响应超时 ({self._config.timeout_s}s)") from e

    async def notify(self, msg: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.kill()
                await self._proc.wait()
            except Exception:
                pass
        self._fail_all("MCP 传输已关闭")
