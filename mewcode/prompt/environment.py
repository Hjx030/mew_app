"""环境信息采集。

环境块是"半稳定"内容：cwd 会话内基本不变，timestamp 每轮必须刷新。
它作为独立 system 消息放在稳定全局指令之后、用户对话之前，环境变化不拖垮缓存前缀。
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EnvironmentInfo:
    """会话运行环境。"""

    cwd: str
    os_name: str
    timestamp: str


def collect_environment() -> EnvironmentInfo:
    """采集当前环境信息（每次对话开头调用，timestamp 实时刷新）。"""
    return EnvironmentInfo(
        cwd=os.getcwd(),
        os_name=platform.system(),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def format_environment(env: EnvironmentInfo) -> str:
    """格式化为环境块文本。"""
    return f"当前环境：cwd={env.cwd}；os={env.os_name}；time={env.timestamp}"
