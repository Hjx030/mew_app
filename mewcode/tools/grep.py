"""代码内容搜索工具。"""

from __future__ import annotations

import re
from pathlib import Path

from mewcode.tools.base import Tool


class Grep(Tool):
    name = "grep"
    description = "递归搜索文件中包含指定关键词或正则表达式的行，返回文件名、行号和内容。"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "搜索关键词或正则表达式"},
            "base_dir": {"type": "string", "description": "搜索根目录，默认为当前目录"},
            "include": {"type": "string", "description": "只搜索匹配此 glob 模式的文件，如 *.py"},
        },
        "required": ["pattern"],
    }

    async def run(self, pattern: str, base_dir: str = ".", include: str | None = None) -> str:
        root = Path(base_dir)
        matches: list[str] = []
        regex = re.compile(pattern)

        files = list(root.rglob(include)) if include else list(root.rglob("*"))

        for f in files:
            if f.is_dir():
                continue
            # 跳过隐藏文件和目录
            if any(part.startswith(".") for part in f.relative_to(root).parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{f}:{i}: {line.strip()[:200]}")

        if not matches:
            return "(无匹配)"
        limited = "\n".join(matches[:100])
        if len(matches) > 100:
            limited += f"\n... 还有 {len(matches) - 100} 条匹配"
        return limited
