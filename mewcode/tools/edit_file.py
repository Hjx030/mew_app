"""改文件工具（行范围替换）。"""

from mewcode.tools.base import Tool


class EditFile(Tool):
    name = "edit_file"
    description = "替换文件指定行范围的内容（行号从 1 开始）。用新内容替换从 start_line 到 end_line 的行。执行前必须先调用 read_file 了解目标文件现状。请用本工具而非 sed。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "start_line": {"type": "integer", "description": "起始行号（从 1 开始）"},
            "end_line": {"type": "integer", "description": "结束行号（包含）"},
            "new_content": {"type": "string", "description": "替换后的内容"},
        },
        "required": ["path", "start_line", "end_line", "new_content"],
    }

    async def run(self, path: str, start_line: int, end_line: int, new_content: str) -> str:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        if start_line < 1:
            return f"错误: start_line 必须 >= 1（实际: {start_line}）"
        if end_line > len(lines):
            return f"错误: end_line 超过文件总行数（文件共 {len(lines)} 行，end_line={end_line}）"

        new_lines = new_content.splitlines(keepends=True)
        # 如果没有换行符结尾，加上
        if new_content and not new_content.endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"

        before = lines[: start_line - 1]
        after = lines[end_line:]
        result_lines = before + new_lines + after

        with open(path, "w", encoding="utf-8") as f:
            f.writelines(result_lines)

        return f"成功替换 {path} 第 {start_line}-{end_line} 行"
