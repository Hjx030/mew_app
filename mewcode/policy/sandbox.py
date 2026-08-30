"""路径沙箱校验。

文件工具（read/write/edit/glob/grep）的路径参数解析为真实路径后必须落在允许根内。
bash 命令尽力扫描绝对路径 token，越界则拦截（best-effort，识别不了交给规则/询问兜底）。
"""

from __future__ import annotations

import os
import re
import shlex

_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/].+")
_ROOT_RE = re.compile(r"^[/\\][^/\\]+[/\\].+")


def resolve_real(path: str) -> str:
    """展开 ~ 并解析为真实路径（处理 .. 和符号链接）。"""
    expanded = os.path.expanduser(path)
    return os.path.realpath(expanded)


def is_within(path: str, root: str) -> bool:
    """判断解析后的真实路径是否在允许根内（相等或以 root+分隔符 开头）。"""
    rp = os.path.normcase(os.path.realpath(path))
    rr = os.path.normcase(os.path.realpath(root))
    if rp == rr:
        return True
    return rp.startswith(rr + os.sep)


def _extract_path_args(tool: str, args: dict) -> list[str]:
    """按工具提取需要校验的路径型参数。"""
    if tool in ("read_file", "write_file", "edit_file"):
        return [args.get("path", "")]
    if tool in ("glob", "grep"):
        return [args.get("base_dir", ".")]
    return []


def check_file_tool(tool: str, args: dict, root: str) -> str | None:
    """文件工具沙箱校验：越界返回原因，否则 None。"""
    for raw in _extract_path_args(tool, args):
        if not raw:
            continue
        real = resolve_real(raw)
        if not is_within(real, root):
            return f"路径越界: {raw} → {real} 不在允许根 {root} 内"
    return None


def _is_absolute_path(token: str) -> bool:
    return bool(_DRIVE_RE.match(token)) or bool(_ROOT_RE.match(token))


def check_bash(command: str, root: str) -> str | None:
    """bash 命令越界检测（best-effort）：发现解析后落在允许根外的绝对路径则返回原因。"""
    try:
        tokens = shlex.split(command, posix=False)
    except Exception:
        tokens = command.split()
    for token in tokens:
        clean = token.strip("\"'")
        if not _is_absolute_path(clean):
            continue
        try:
            real = resolve_real(clean)
        except Exception:
            continue
        if not is_within(real, root):
            return f"命令中的路径越界: {clean} → {real} 不在允许根 {root} 内"
    return None


_PATH_KEY_HINTS = ("path", "dir", "file", "folder", "directory")


def check_remote_args(args: dict, root: str) -> str | None:
    """远端 MCP 工具参数的最佳努力沙箱。

    扫描参数中 key 含 path/dir/file 等提示、或值像绝对路径的字段，解析后越界返回原因。
    """
    for key, value in args.items():
        if not isinstance(value, str) or not value:
            continue
        is_path_key = any(h in key.lower() for h in _PATH_KEY_HINTS)
        if not is_path_key and not _is_absolute_path(value):
            continue
        try:
            real = resolve_real(value)
        except Exception:
            continue
        if not is_within(real, root):
            return f"参数 {key} 的路径越界: {value} → {real} 不在允许根 {root} 内"
    return None
