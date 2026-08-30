"""读文件工具。"""

from mewcode.tools.base import Tool


class ReadFile(Tool):
    name = "read_file"
    description = "读取指定文件的内容并返回。文件操作请使用本工具而非 shell 命令（cat/head）。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
        },
        "required": ["path"],
    }

    async def run(self, path: str) -> str:
        with open(path, encoding="utf-8") as f:
            return f.read()
