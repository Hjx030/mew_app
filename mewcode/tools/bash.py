"""Shell 命令执行工具（需用户确认）。"""

from __future__ import annotations

import asyncio

from mewcode.tools.base import Tool


class Bash(Tool):
    name = "bash"
    description = "执行一条 shell 命令并返回输出。命令在本地系统上直接执行，有破坏性风险，执行前需用户确认。文件读写请优先使用 read_file/write_file/edit_file 专用工具。"
    needs_confirmation = True
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
        },
        "required": ["command"],
    }

    async def run(self, command: str) -> str:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "错误: 命令执行超时（60 秒）"

        output = ""
        if stdout:
            decoded = stdout.decode("utf-8", errors="replace")
            if decoded.strip():
                output += decoded
        if stderr:
            decoded = stderr.decode("utf-8", errors="replace")
            if decoded.strip():
                if output:
                    output += "\n--- stderr ---\n"
                output += decoded
        return output if output else "(命令无输出)"
