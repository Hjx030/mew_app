"""配置加载与校验模块。"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

import yaml


class ConfigError(Exception):
    """配置相关错误。"""

    def __init__(self, path: str, field: str | None = None) -> None:
        if field:
            super().__init__(f"配置文件 {path}: 字段 '{field}' 缺失或为空")
        else:
            super().__init__(f"配置文件未找到: {path}")


@dataclass
class Config:
    """LLM 供应商配置。"""

    protocol: str  # "anthropic" | "openai"
    model: str
    base_url: str
    api_key: str


def load_config(path: str | None = None) -> Config:
    """加载并校验 YAML 配置文件。

    Args:
        path: 配置文件路径，默认为 ~/.config/mewcode/config.yaml

    Returns:
        Config 实例

    Raises:
        ConfigError: 文件不存在、字段缺失或为空
    """
    if path is None:
        path = os.path.join(str(pathlib.Path.home()), ".config", "mewcode", "config.yaml")

    if not os.path.isfile(path):
        raise ConfigError(path)

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ConfigError(path)

    required = ["protocol", "model", "base_url", "api_key"]
    for field in required:
        value = data.get(field)
        if value is None or not isinstance(value, str):
            raise ConfigError(path, field)
        if field != "api_key" and not value.strip():
            raise ConfigError(path, field)

    return Config(
        protocol=data["protocol"].strip(),
        model=data["model"].strip(),
        base_url=data["base_url"].strip().rstrip("/"),
        api_key=data["api_key"].strip(),
    )
