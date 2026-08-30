# Changelog

本项目所有值得记录的变更，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.4.0] - 2026-08-30

### Added
- 新增 `mewcode.prompt` 包：`PromptBuilder` 按优先级拼装稳定全局指令，含 5 个全局指令模块（身份 / 行为 / 工具使用 / 安全 / 输出风格）
- 新增环境块采集（cwd / OS / 时间戳），持久化到 user 消息开头，保证相邻轮次首条消息字节一致、缓存前缀稳定命中
- 新增 `<sys-instruct>` 运行时指令注入通道与 `PlanModeInjector`：首轮注入完整 Plan 指令、每 3 轮重复、其余轮次注入精简提醒
- 新增 TUI 缓存命中统计展示（命中率 >50% 显示绿色，否则黄色）
- OpenAI Provider 新增 `usage` 流事件（DeepSeek 流式显式开启 `include_usage`）
- 新增 `test_prompt.py` 单元测试与 `test_providers.py` 的 usage 事件测试
- 新增 v0.4 Prompt 系统重构规划文档（spec / plan / task / checklist）

### Changed
- `tui/session.py` 重构：内联系统提示词与 Plan Mode 指令移入 `mewcode.prompt` 包；工具调用达 5 次后注入温和收敛提醒
- 四个工具 description 强化：引导优先使用专用文件工具而非 shell 命令（sed / cat / 重定向），修改文件前先调用 read_file
- `/clear`、`/plan` 命令接入 PlanModeInjector 的开关与状态重置
