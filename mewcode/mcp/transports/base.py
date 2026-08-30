"""传输层抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Transport(ABC):
    """MCP 传输契约。

    request/notify 收发 JSON-RPC 消息；id 关联由各传输内部实现。
    """

    @abstractmethod
    async def connect(self) -> None:
        """建立连接。"""

    @abstractmethod
    async def request(self, msg: dict) -> dict:
        """发送 JSON-RPC 请求并返回按 id 关联的响应消息。"""

    @abstractmethod
    async def notify(self, msg: dict) -> None:
        """发送 JSON-RPC 通知（无响应）。"""

    @abstractmethod
    async def close(self) -> None:
        """关闭连接。"""
