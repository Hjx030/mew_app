"""Glob 文件搜索工具。"""

from mewcode.tools.base import Tool


class Glob(Tool):
    name = "glob"
    description = "按 glob 模式递归搜索文件名，返回匹配的文件路径列表，每行一个。"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "glob 模式，如 **/*.py 或 *.txt"},
            "base_dir": {"type": "string", "description": "搜索根目录，默认为当前目录"},
        },
        "required": ["pattern"],
    }

    async def run(self, pattern: str, base_dir: str = ".") -> str:
        import glob as glob_mod

        matches = glob_mod.glob(pattern, root_dir=base_dir, recursive=True)
        if not matches:
            return "(无匹配文件)"
        return "\n".join(sorted(matches))
