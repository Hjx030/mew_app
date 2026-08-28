# MewCode v0.3 — Agent Loop + Plan Mode Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `mewcode/tui/renderer.py` | 新增 `render_step_counter()` |
| 修改 | `mewcode/tui/session.py` | Agent Loop 循环 + Plan Mode 提示词 |
| 修改 | `mewcode/__main__.py` | 版本号 0.3.0 |

## 依赖图

```
T1 (renderer) → T2 (session loop) → T3 (version)
```

---

## T1: Renderer — 步数计数器

**文件：** `mewcode/tui/renderer.py`
**依赖：** 无
**步骤：**
1. 在文件末尾新增函数：
   ```python
   def render_step_counter(current: int, total: int = 10) -> None:
       """显示 Agent Loop 当前执行步数。"""
       console.print(f"[cyan]─── 步骤 {current}/{total} ───[/cyan]")
   ```
2. 在 `__all__` 或模块级导出中加一行

**验证：**
```bash
python -c "from mewcode.tui.renderer import render_step_counter; render_step_counter(2); print('OK')"
```

---

## T2: Session — Agent Loop 重写

**文件：** `mewcode/tui/session.py`
**依赖：** T1
**步骤：**
1. 更新 `SYSTEM_PROMPT` 为 v0.3 版（含 Plan Mode 引导）：
   ```python
   SYSTEM_PROMPT = """You are MewCode, an AI coding assistant with access to file, code search, and shell command tools.

   For multi-step tasks, first present a clear step-by-step plan to the user. Ask for confirmation before executing.
   Once confirmed, you can chain multiple tool calls to complete the task.
   After each tool result, decide whether to call another tool or provide the final answer.
   When the task is complete, summarize what was done."""
   ```
2. 将 `_run_conversation_turn` 整个替换为基于 `for step in range(MAX_STEPS)` 的循环结构
3. 移除不再需要的 `_stream_and_handle_tool` 和 `_stream_to_buffer` 函数
4. 在 `_run_conversation_turn` 开头定义步数上限：
   ```python
   MAX_STEPS = 10
   ```
5. 循环逻辑：
   - 每次迭代调用 `provider.stream_chat(messages, config, tools=tools)`
   - 收到 `"text"` → 累积到 buffer，实时打印
   - 收到 `"tool_call"` → 展示、确认(首步)、执行、加入 history、`break` 继续下一轮
   - 收到 `"error"` → 渲染错误并返回
   - 一轮结束后：若无 tool_call 且有 text → 加入 assistant message → 返回
   - 若步数未达上限 → 打印 `render_step_counter(step+2, MAX_STEPS)`
   - 超出上限 → 打印已达上限提示
6. 在 `run_session` 的命令列表中加入 `/plan`：
   ```
   /plan on    — 开启 Plan Mode（AI 先出计划再执行）
   /plan off   — 关闭 Plan Mode（AI 直接执行）
   ```
   Plan Mode 状态保存为 `plan_mode: bool`，为 True 时在 tools 前加一条 system message 提示先出计划

**验证：** `python -c "from mewcode.tui.session import run_session; print('OK')"`

---

## T3: 版本号更新

**文件：** `mewcode/__main__.py`
**依赖：** T2
**步骤：**
1. `VERSION = "0.2.0"` → `VERSION = "0.3.0"`

**验证：** `python -m mewcode --version` 输出 `0.3.0`
