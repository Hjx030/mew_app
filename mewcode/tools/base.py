"""Tool 基类和注册器。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """模型发起的工具调用请求。"""
    id: str
    name: str
    arguments: dict


class Tool:
    """工具基类。

    子类需定义 name、description、parameters，并实现 run()。
    """
    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)
    needs_confirmation: bool = False

    async def run(self, **kwargs) -> str:
        raise NotImplementedError


class ToolRegistry:
    """工具注册器，管理所有可用工具。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        """返回 OpenAI 兼容的 tools 参数列表。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def execute(self, name: str, **kwargs) -> str:
        """执行工具并返回字符串结果。"""
        tool = self._tools.get(name)
        if not tool:
            return f"错误: 未知工具 '{name}'"
        try:
            result = await tool.run(**kwargs)
            return str(result)
        except Exception as e:
            return f"错误: 工具 {name} 执行失败: {e}"
