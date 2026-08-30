"""策略引擎：黑名单 + 规则 + 沙箱 + 档位兜底 的固定裁决顺序。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from mewcode.policy.rules import RuleStore, load_project_rules, load_user_rules
from mewcode.policy.sandbox import check_bash, check_file_tool, check_remote_args

READ_ONLY_TOOLS = ("read_file", "glob", "grep")

# 内置黑名单（仅作用于 bash 命令），硬拦截、不询问、任何 allow 规则不可覆盖
BLACKLIST: dict[str, list[str]] = {
    "破坏性文件/磁盘操作": [
        r"\brm\b[^|&;\n]*-[A-Za-z]*[rR][A-Za-z]*[fF]",  # rm -rf
        r"\brm\b[^|&;\n]*-[A-Za-z]*[fF][A-Za-z]*[rR]",  # rm -fr
        r"\bdel(?:tree)?\b\s+/[sS]",
        r"\bdd\b[^\n]*\bof=",
        r"\bmkfs(?:\.\w+)?\b",
        r"\bfdisk\b",
        r"\bformat\s+[A-Za-z]:",
    ],
    "远程脚本下载即执行": [
        r"curl[^\n|&]*\|\s*(?:sh|bash|zsh|pwsh|powershell)",
        r"wget[^\n|&]*\|\s*(?:sh|bash|zsh|pwsh|powershell)",
        r"curl[^\n&]*\s+-o\s*\S+\s*(?:&&|;)\s*(?:sh|bash)\b",
        r"powershell[^\n]*iex",
        r"\biwr\b[^\n]*\|\s*iex",
        r"Invoke-Expression",
    ],
    "系统级危险": [
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bhibernate\b",
        r"\btaskkill\s+/[fF]",
    ],
    "目录破坏": [
        r"\brm\b[^\n|&]*-[A-Za-z]*[rR][A-Za-z]*[fF][A-Za-z]*\s+[/\\]+(?:\s|$)",
        r"\bchmod\s+-R\s*777\s+[/\\]+(?:\s|$)",
        r"\brm\s+-rf\s+[A-Za-z]:[\\/]",
    ],
}


@dataclass
class Decision:
    """一次工具调用的裁决结果。"""

    verdict: str  # allow / deny / ask
    reason: str
    rule: object | None = None


class PolicyEngine:
    """权限裁决引擎，按固定顺序：黑名单 → 规则 → 沙箱 → 档位兜底。"""

    def __init__(
        self,
        user_rules: list,
        project_rules: list,
        session_store: RuleStore | None = None,
        mode: str = "default",
        allowed_root: str | None = None,
    ) -> None:
        self.user_rules = user_rules
        self.project_rules = project_rules
        self.session_store = session_store or RuleStore()
        self.mode = mode
        self.allowed_root = os.path.realpath(allowed_root or os.getcwd())

    def decide(self, tool_name: str, arguments: dict) -> Decision:
        """裁决一次工具调用。"""
        # ① 黑名单（硬拦截，最高优先）
        if tool_name == "bash":
            command = arguments.get("command", "")
            for category, patterns in BLACKLIST.items():
                for pat in patterns:
                    if re.search(pat, command):
                        return Decision("deny", f"黑名单[{category}]")

        # ② 具体规则（会话级 > 项目级 > 用户级；同层后者覆盖）
        for level in (self.session_store.list(), self.project_rules, self.user_rules):
            matched = [r for r in level if r.match(tool_name, arguments)]
            if matched:
                rule = matched[-1]
                return Decision(rule.action, f"规则[{rule.source}] {rule.action}: {rule.pattern}", rule)

        # ③ 沙箱（未命中规则时；allow 规则可显式授权越界）
        if tool_name in ("read_file", "write_file", "edit_file", "glob", "grep"):
            reason = check_file_tool(tool_name, arguments, self.allowed_root)
            if reason:
                return Decision("deny", "沙箱: " + reason)
        elif tool_name == "bash":
            command = arguments.get("command", "")
            reason = check_bash(command, self.allowed_root)
            if reason:
                return Decision("deny", "沙箱: " + reason)
        elif tool_name.startswith("mcp_"):
            reason = check_remote_args(arguments, self.allowed_root)
            if reason:
                return Decision("deny", "沙箱: " + reason)

        # ④ 档位兜底
        if self.mode == "strict":
            return Decision("ask", "严格档: 未命中明确允许规则")
        if self.mode == "permissive":
            return Decision("allow", "放行档: 未命中拒绝规则")
        if tool_name in READ_ONLY_TOOLS:
            return Decision("allow", "默认档: 只读操作自动放行")
        return Decision("ask", "默认档: 写入/执行需确认")

    def set_mode(self, mode: str) -> None:
        if mode not in ("strict", "default", "permissive"):
            raise ValueError(f"未知档位: {mode}")
        self.mode = mode

    def add_session_rule(self, rule) -> None:
        self.session_store.add(rule)

    def save_project_rule(self, rule) -> str:
        """把规则永久写入项目级 rules.yaml（HITL 永久允许）。"""
        from mewcode.policy.rules import save_project_rule as _save

        return _save(self.allowed_root, rule)

    def get_rules_summary(self) -> str:
        """生成 /rules 展示文本。"""
        lines = [f"档位: {self.mode}", f"允许根: {self.allowed_root}"]
        for label, rules in (
            ("会话级规则", self.session_store.list()),
            ("项目级规则", self.project_rules),
            ("用户全局规则", self.user_rules),
        ):
            lines.append(f"{label}:")
            if not rules:
                lines.append("  （无）")
            for r in rules:
                lines.append(f"  [{r.source}] {r.tool} {r.action} {r.pattern}")
        return "\n".join(lines)


def create_policy(root: str | None = None) -> PolicyEngine:
    """从文件加载用户/项目规则，构造默认档位的策略引擎。"""
    if root is None:
        root = os.getcwd()
    return PolicyEngine(
        user_rules=load_user_rules(),
        project_rules=load_project_rules(root),
        allowed_root=root,
    )
