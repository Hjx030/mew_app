# MewCode v0.3 — Agent Loop + Plan Mode Plan

## 架构变化

v0.2 线性流程：
```
用户输入 → API(tools) → [tool_call → 执行 → API(no tools) → 文字] → 停
```

v0.3 循环流程：
```
用户输入 → 循环(最多 10 步) {
  API(tools) → text? → 停 ✓
             → tool_call? → 确认(首步) → 执行 → 加入 history → 继续循环
}
```

Plan Mode 嵌入流程：
```
用户输入 → AI 输出计划(文字) → 用户确认"开始" → 进入 Agent Loop 执行
                                                        ↘ 用户可提修改意见
```

## 核心数据流

### Agent Loop

```python
# 单轮对话的执行循环
for step in range(MAX_STEPS):
    async for event in provider.stream_chat(messages, config, tools=tools):
        if event.type == "text":
            buffer += event.content
            stream_text(event.content)
        elif event.type == "tool_call":
            # 展示工具调用
            render_tool_call(name, arguments)
            # 首次确认(如bash)
            if needs_confirmation and not confirmed:
                wait_for_user()
            # 执行工具
            result = await tool_registry.execute(name, **args)
            render_tool_result(result)
            # 加入对话历史
            messages.append(tool_call_msg)
            messages.append(tool_result_msg)
            break  # 继续下一轮 for step
        elif event.type == "error":
            render_error()
            return

    if not tool_was_called and text_buffer:
        # 模型主动输出文字 → 循环结束
        messages.append(Message("assistant", text_buffer))
        return

render_system(f"已达最大步数 ({MAX_STEPS})")
```

### Plan Mode

- **系统提示词**加入 Plan Mode 指令
- **自动触发**：AI 对多步任务输出计划，等待用户确认
- **确认方式**：用户在对话中输入"开始执行"/"好"等
- `/plan` 命令：切换 Plan Mode 开/关，`/plan on` → AI 必须出计划再执行

## 模块设计变更

| 模块 | 变更 | 说明 |
|------|------|------|
| `tui/session.py` | **重写** `_run_conversation_turn` 为循环结构 | Agent Loop + Plan Mode |
| `tui/renderer.py` | 新增 `render_step_counter()` | 显示当前步数/总数 |
| `__main__.py` | 更新版本号 0.3.0 | |

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 循环实现 | `for step in range(10)` + `break` 退出 | 简单直接，break 清理 async generator |
| 确认追踪 | `confirmed_tools: set[str]` | 每轮用户输入重置，安全 |
| Plan Mode 判断 | 由 AI 自主决定（系统提示词引导） | 灵活，不需要规则匹配 |
| 步数显示 | `render_step_counter(step+1, MAX)` | 独立函数，1/10 → 2/10 递增 |
| SYSTEM_PROMPT | 更新为包含 Plan Mode + Agent Loop 指令 | 一次修改，全局生效 |
