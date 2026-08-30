"""权限规则模型与三级加载。"""

from __future__ import annotations

import fnmatch
import os
import pathlib
import re
from dataclasses import dataclass, field

import yaml

USER_RULES_PATH = os.path.join(str(pathlib.Path.home()), ".config", "mewcode", "rules.yaml")

# 规则匹配时按工具提取的参数名
_PATH_ARGS = {"read_file": "path", "write_file": "path", "edit_file": "path"}
_BASE_DIR_ARGS = {"glob": "base_dir", "grep": "base_dir"}


@dataclass
class Rule:
    """一条权限规则。

    tool: 工具名；action: allow/deny/ask；pattern: 文件工具=glob 匹配路径、bash=正则匹配命令。
    """

    tool: str
    action: str
    pattern: str
    source: str  # user / project / session

    def match(self, tool_name: str, arguments: dict) -> bool:
        """判断本规则是否命中一次工具调用。"""
        if tool_name != self.tool:
            return False
        if self.tool == "bash":
            command = arguments.get("command", "")
            return bool(re.search(self.pattern, command))
        if self.tool in _PATH_ARGS:
            target = arguments.get(_PATH_ARGS[self.tool], "")
        elif self.tool in _BASE_DIR_ARGS:
            target = arguments.get(_BASE_DIR_ARGS[self.tool], ".")
        else:
            return False
        return bool(fnmatch.fnmatch(target, self.pattern))


@dataclass
class RuleStore:
    """会话级规则的内存存储。"""

    _rules: list[Rule] = field(default_factory=list)

    def add(self, rule: Rule) -> None:
        self._rules.append(rule)

    def list(self) -> list[Rule]:
        return list(self._rules)


def _load_from_yaml(path: str, source: str) -> list[Rule]:
    """从 YAML 读取规则列表。文件不存在或格式异常返回空列表。"""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    rules: list[Rule] = []
    for item in data.get("rules", []) or []:
        tool = item.get("tool")
        action = item.get("action")
        pattern = item.get("pattern")
        if tool and action and pattern:
            rules.append(Rule(tool=tool, action=action, pattern=pattern, source=source))
    return rules


def load_user_rules() -> list[Rule]:
    """读用户全局规则 ~/.config/mewcode/rules.yaml。"""
    return _load_from_yaml(USER_RULES_PATH, "user")


def load_project_rules(root: str) -> list[Rule]:
    """读项目级规则 <root>/.mewcode/rules.yaml。"""
    path = os.path.join(root, ".mewcode", "rules.yaml")
    return _load_from_yaml(path, "project")


def save_project_rule(root: str, rule: Rule) -> str:
    """追加写入项目规则文件，返回写入路径。"""
    path = os.path.join(root, ".mewcode", "rules.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing: list[dict] = []
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            existing = (data.get("rules") if isinstance(data, dict) else []) or []
        except Exception:
            existing = []
    existing.append({"tool": rule.tool, "action": rule.action, "pattern": rule.pattern})
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump({"rules": existing}, f, allow_unicode=True)
    return path
