"""写文件工具。"""

from mewcode.tools.base import Tool


class WriteFile(Tool):
    name = "write_file"
    description = "将内容写入指定文件（覆盖已存在的文件）"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的内容"},
        },
        "required": ["path", "content"],
    }

    async def run(self, path: str, content: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功写入 {path}（{len(content)} 字符）"
