# MewCode Prompt 系统重构 Tasks (v0.4)

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `mewcode/prompt/__init__.py` | 包导出 |
| 新建 | `mewcode/prompt/sections.py` | Section 类型 + 5 个模块 |
| 新建 | `mewcode/prompt/environment.py` | EnvironmentInfo + collect/format |
| 新建 | `mewcode/prompt/builder.py` | PromptBuilder + 指令常量 |
| 新建 | `mewcode/prompt/injection.py` | PlanModeInjector + 标签构造 |
| 新建 | `test_prompt.py` | prompt 包单元测试 |
| 修改 | `mewcode/providers/openai.py` | include_usage + usage 解析 |
| 修改 | `mewcode/tui/renderer.py` | 新增 render_cache_hit |
| 修改 | `mewcode/tui/session.py` | 接入 prompt 包 |
| 修改 | `mewcode/tools/read_file.py` `write_file.py` `edit_file.py` `bash.py` | 描述双重强化 |

## 依赖图

```
T1(sections) → T3(builder) ─┐
T2(environment)─────────────┼→ T5(__init__) → T6(test_prompt) → T10(session) → T11(全量)
T4(injection)───────────────┘                                    ↑
T7(工具描述)──────────────────────────────────────────────────────┤
T8(openai) ─→ T9(renderer) ──────────────────────────────────────┘
```

## T1: sections.py — 模块定义

**文件：** `mewcode/prompt/sections.py`
**依赖：** 无
**步骤：**
1. 定义 `@dataclass class Section`：`name: str`、`priority: int`、`content: str`
2. 定义 5 个模块常量（content 为中文正文）：
   - `identity` (10)：你是 MewCode，会文件/搜索/shell 工具的编程助手
   - `behavior` (20)：可链式调用工具，每个结果后决定下一步或收尾，完成时总结
   - `tool_usage` (30)：三条强化规则逐字写全——"优先使用专用工具（read_file/write_file/edit_file）处理文件操作，而不是用 shell 命令（cat/echo/sed）；对文件执行 write_file 或 edit_file 前，必须先调用 read_file 了解现状；bash 命令直接在本机执行，有破坏性风险，涉及删除/覆盖/危险操作前要谨慎并说明。"
   - `safety` (40)：涉及删除/覆盖/危险命令时先说明风险再执行
   - `output_style` (50)：简洁中文回复，引用文件用相对路径
3. 导出 `SECTIONS: list[Section]` 供 builder 使用

**验证：** `python -c "from mewcode.prompt.sections import SECTIONS; print([(s.name,s.priority) for s in SECTIONS])"`

## T2: environment.py — 环境块

**文件：** `mewcode/prompt/environment.py`
**依赖：** 无
**步骤：**
1. 定义 `@dataclass class EnvironmentInfo`：`cwd` / `os_name` / `timestamp`
2. `collect_environment() -> EnvironmentInfo`：`os.getcwd()`、`platform.system()`、`datetime.now()` 格式化
3. `format_environment(env) -> str`：返回 `"当前环境：cwd=…；os=…；time=…"`

**验证：** `python -c "from mewcode.prompt.environment import collect_environment, format_environment; print(format_environment(collect_environment()))"`

## T3: builder.py — PromptBuilder + 常量

**文件：** `mewcode/prompt/builder.py`
**依赖：** T1
**步骤：**
1. 定义 `class PromptBuilder`：`__init__(self, sections: list[Section])`；`build_stable() -> str` 按 `priority` 升序拼接各 `content`
2. 定义常量：`PLAN_FULL_INSTRUCTION`（完整 Plan 指令）、`PLAN_MINIMAL_REMINDER`（一行精简提醒）、`GENTLE_REMINDER`（"你已连续调用 5 次工具，若任务已可完成请尽快给出最终回答"）

**验证：** `python -c "from mewcode.prompt.builder import PromptBuilder, PLAN_FULL_INSTRUCTION; from mewcode.prompt.sections import SECTIONS; s=PromptBuilder(SECTIONS).build_stable(); print(len(s)); assert 'identity' not in s or 'MewCode' in s"`

## T4: injection.py — 注入通道

**文件：** `mewcode/prompt/injection.py`
**依赖：** 无
**步骤：**
1. 定义 `INJECT_OPEN = "<sys-instruct>"`、`INJECT_CLOSE = "</sys-instruct>"`
2. `make_instruction(text) -> str`：返回 `INJECT_OPEN + text + INJECT_CLOSE`
3. `class PlanModeInjector`：`__init__(self, full, minimal, repeat_every=3)`；`next()` 内部计数+1，第 1/4/7…轮返回 full，其余返回 minimal；`reset()` 清零计数

**验证：** `python -c "from mewcode.prompt.injection import PlanModeInjector, make_instruction; i=PlanModeInjector('F','M'); print([i.next() for _ in range(4)]); print(make_instruction('hi'))"` → 期望 `['F','M','M','F']`

## T5: prompt/__init__.py — 包导出

**文件：** `mewcode/prompt/__init__.py`
**依赖：** T1–T4
**步骤：**
1. 导出 `Section`、`SECTIONS`、`PromptBuilder`、`collect_environment`、`format_environment`、`EnvironmentInfo`、`make_instruction`、`PlanModeInjector` 及三个指令常量
2. 定义 `__all__`

**验证：** `python -c "import mewcode.prompt; print(sorted(mewcode.prompt.__all__))"`

## T6: test_prompt.py — 单元测试

**文件：** `test_prompt.py`
**依赖：** T5
**步骤：**
1. 测试 section 按 priority 排序拼接
2. 测试环境块包含 cwd/os/time 三字段
3. 测试 PlanModeInjector 变频序列（1/4/7 full，其余 minimal）和 reset
4. 测试 make_instruction 标签包裹

**验证：** `python -m pytest test_prompt.py -q` 全绿

## T7: 工具描述双重强化（F4）

**文件：** `mewcode/tools/read_file.py` `write_file.py` `edit_file.py` `bash.py`
**依赖：** 无（但须与 T1 的 tool_usage 正文逐字一致）
**步骤：**
1. `read_file.py` 描述改为："读取指定文件的内容并返回。文件操作请使用本工具而非 shell 命令（cat/head）。"
2. `write_file.py` 描述追加："执行前必须先调用 read_file 了解目标文件现状。请用本工具而非 shell 重定向。"
3. `edit_file.py` 描述追加："执行前必须先调用 read_file 了解目标文件现状。请用本工具而非 sed。"
4. `bash.py` 描述保留破坏性警示，追加："文件读写请优先使用 read_file/write_file/edit_file 专用工具。"
5. 确保与 tool_usage 的规则句意一致

**验证：** `python -m pytest test_providers.py -q -k "read_file or write_file or edit_file or bash or confirmation"` 通过

## T8: openai.py — usage 解析（F8）

**文件：** `mewcode/providers/openai.py`
**依赖：** 无
**步骤：**
1. 请求体 `body` 加 `"stream_options": {"include_usage": True}`
2. 流循环中，在 `choices = data.get(...)` / `if not choices: continue` **之前**检查 `data.get("usage")`，非空则 `yield StreamEvent("usage", json.dumps(data["usage"]))`
3. 在 `test_providers.py` 新增一个测试：模拟含 usage 的最终块，断言产出 `usage` 事件且字段正确

**验证：** `python -m pytest test_providers.py -q` 全绿

## T9: renderer.py — 缓存展示

**文件：** `mewcode/tui/renderer.py`
**依赖：** 无
**步骤：**
1. 新增 `def render_cache_hit(hit: int, miss: int) -> None`：计算命中率，`>50%` 绿色、否则黄色，打印 `缓存命中 X tokens / 未命中 Y tokens（命中率 Z%）`

**验证：** `python -c "from mewcode.tui.renderer import render_cache_hit; render_cache_hit(900,100); render_cache_hit(50,100)"` 观察颜色

## T10: session.py — 接入 prompt 包

**文件：** `mewcode/tui/session.py`
**依赖：** T5, T7, T8, T9
**步骤：**
1. 删除 `BASE_SYSTEM_PROMPT` / `PLAN_MODE_INSTRUCTION` / `_build_system_prompt`
2. 启动时构建一次 `stable = PromptBuilder(SECTIONS).build_stable()`
3. `_run_agent_loop` 改为接收 `stable`；每轮组装 `request_msgs = [Message("system", stable), Message("system", format_environment(collect_environment()))] + history`
4. Plan Mode：`/plan on` 创建 `PlanModeInjector(...)`；每轮开头调 `next()`，返回非 None 则把指令附加到当前 user 消息副本；`/plan off` 和 `/clear` 时 `reset()` 或置空
5. 温和提醒：循环内工具调用计数变量，达 5 时把 `make_instruction(GENTLE_REMINDER)` 附加到即将入历史的 tool result 字符串副本
6. `_run_agent_loop` 事件循环处理 `usage` 事件 → `render_cache_hit(hit, miss)`（解析 JSON content）
7. 确保 `/help` 里 /plan 文案仍准确

**验证：** `python -c "from mewcode.tui.session import run_session; print('OK')"` 且 `python -m pytest -q` 全绿

## T11: 全量验证 + 冒烟

**文件：** 无
**依赖：** T10
**步骤：**
1. `python -m pytest -q` 全部通过
2. `python -m mewcode --version` 输出 0.3.0（版本号本轮不变）

**验证：** 上述命令输出符合预期

## 执行顺序

```
T1 → T3 → T5 ─┐
T2 ───────────┼→ T6 → T10 → T11
T4 ───────────┘    ↑
T7 ────────────────┤
T8 → T9 ───────────┘
```
