# MewCode Prompt 系统重构 Plan (v0.4)

## 架构概览

新增独立 `mewcode/prompt/` 包，承担所有 prompt 拼装职责，与 TUI 解耦；session 只负责调用和状态跟踪。

| 组件 | 职责 | 对应 spec |
|------|------|-----------|
| **sections.py** | 定义 Section 模块（身份/行为/工具使用/安全/输出风格），带优先级 | F1 |
| **builder.py** | 按优先级拼装稳定全局指令；持有 Plan 指令文本、注入标签常量、温和提醒模板 | F1, F2, F4, F6, F7 |
| **environment.py** | 采集工作目录/操作系统/时间，格式化为环境块 | F3 |
| **injection.py** | PlanModeInjector（变频注入）+ 特殊标签指令构造 | F5, F6 |
| **providers/openai.py**（改） | 加 include_usage，解析 usage 缓存字段，产出 usage 事件 | F8 |
| **tui/session.py**（改） | 调 prompt 包组装请求消息；维护 plan 变频计数、工具调用计数；展示缓存命中 | F2-F8 接线 |
| **tui/renderer.py**（改） | 新增缓存命中展示函数 | F8 |

## 核心数据结构

```python
# sections.py — 全局指令模块
@dataclass
class Section:
    name: str          # identity / behavior / tool_usage / safety / output_style
    priority: int      # 越小越靠前
    content: str       # 模块正文

# environment.py — 环境信息
@dataclass
class EnvironmentInfo:
    cwd: str
    os_name: str
    timestamp: str     # 每次对话刷新

# injection.py — 注入通道
INJECT_OPEN = "<sys-instruct>"
INJECT_CLOSE = "</sys-instruct>"

# 新增流式事件类型（复用 StreamEvent）
# type = "usage"，content = JSON 字符串:
# {"prompt_tokens": N, "prompt_cache_hit_tokens": M, "prompt_cache_miss_tokens": K, "completion_tokens": C}
```

## 模块设计

### sections.py — 5 个全局指令模块

| 模块 | priority | 内容要点 |
|------|---------|---------|
| identity | 10 | 你是 MewCode，会文件/搜索/shell 工具的编程助手 |
| behavior | 20 | 可链式调用工具，每个结果后决定下一步或收尾，完成时总结 |
| tool_usage | 30 | 三条强化规则：优先专用工具而非 bash；write/edit 前必须先 read_file；bash 有破坏性、谨慎执行 |
| safety | 40 | 涉及删除/覆盖/危险命令时先说明风险 |
| output_style | 50 | 简洁中文回复、引用文件用路径 |

`tool_usage` 的正文和工具描述里的强化规则**逐字一致**（F4 双重强化）。

### builder.py — PromptBuilder

- `build_stable() -> str`：按 priority 排序拼接所有 Section → 稳定全局指令（构建一次、全程复用）
- 常量：`PLAN_FULL_INSTRUCTION`、`PLAN_MINIMAL_REMINDER`、`GENTLE_REMINDER`（"你已连续调用 5 次工具，若任务已可完成请尽快给出最终回答"）

### environment.py

- `collect_environment() -> EnvironmentInfo`：`os.getcwd()`、`platform.system()`、当前时间
- `format_environment(env) -> str`：拼成"当前环境：cwd=…；os=…；time=…"

### injection.py — PlanModeInjector

```python
class PlanModeInjector:
    def __init__(self, full: str, minimal: str, repeat_every: int = 3): ...
    def next(self) -> str | None:   # 计数+1；第1、4、7…轮→full；其余→minimal
    def reset(self):                # /plan off 或 /clear 时调用
```

注入文本统一用 `make_instruction(text)` 包上 `<sys-instruct>` 标签。

### providers/openai.py（改）

- 请求体加 `"stream_options": {"include_usage": True}`
- 流循环中：在 `if not choices: continue` 之前先检查 `data.get("usage")`，命中则 yield `StreamEvent("usage", json.dumps(usage))`，然后继续消费到 `[DONE]`

### tui/session.py（改）

- 移除 `BASE_SYSTEM_PROMPT` / `PLAN_MODE_INSTRUCTION` / `_build_system_prompt`
- 每轮请求消息组装：
  ```
  request_msgs = [Message("system", build_stable()),
                  Message("system", format_environment(collect_environment()))]
                 + 历史对话
  ```
- Plan 变频：`/plan on` 时实例化 PlanModeInjector；每轮开头调 `next()`，有返回则把标签指令附加到**当前 user 消息**（构造副本，不改存储历史）
- 温和提醒：Agent Loop 内工具调用计数达 5 时，把提醒附加到**即将追加的 tool result 内容**（改副本）
- 收到 `usage` 事件 → 调 renderer 展示

### tui/renderer.py（改）

- 新增 `render_cache_hit(hit: int, miss: int)`：显示 `缓存命中 X tokens / 未命中 Y tokens`，命中率用颜色标注（>50% 绿，否则黄）

## 模块交互

```
用户输入
  │
  ▼
session：
  collect_environment() → 环境块（每轮刷新）
  PlanModeInjector.next() → Plan 指令（变频）
  user_content = 环境块 + [Plan指令] + 用户输入   ← 持久化到历史
  │
  ├──build_stable()──► 稳定全局指令（构建一次，全程复用，可缓存前缀）
  │
  ▼
request_msgs = [system(稳定)] + ...历史（含已持久化的 user 消息）...
  │
  ▼
provider.stream_chat(request_msgs, tools)
  │                          ▲
  │  流事件：                 │ 执行工具
  ├─ text ──► stream_text    │
  ├─ tool_call ──► 工具调用计数+1
  │                  ├─ 达 5 次？→ make_instruction(温和提醒) 附加到 tool result 副本
  │                  └─ execute() → 结果入历史 → 继续循环
  ├─ usage ──► render_cache_hit(hit, miss)
  └─ done / 文字回复 ──► 本轮结束
```

## 文件组织

```
mewcode/
├── prompt/                    ← 新增包
│   ├── __init__.py            # 导出 PromptBuilder、collect_environment 等
│   ├── sections.py            # Section 数据类型 + 5 个模块
│   ├── builder.py             # PromptBuilder 主入口 + 指令常量
│   ├── environment.py         # EnvironmentInfo + collect/format
│   └── injection.py           # PlanModeInjector + 标签构造
├── tui/
│   ├── session.py             # 改造：接入 prompt 包 + usage 展示
│   └── renderer.py            # 改造：加 render_cache_hit
└── providers/
    └── openai.py              # 改造：include_usage + 解析 usage
```

新增测试文件：`test_prompt.py`（拼装/环境/变频注入的单元测试，不依赖 API）

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 缓存验证 | 解析 DeepSeek usage 的 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` | DeepSeek 原生字段，`prompt_tokens = hit + miss` |
| 请求体 | 加 `stream_options: {"include_usage": True}` | 流式默认不返回 usage，必须显式开启 |
| 消息结构 | system 只放稳定指令；环境块 + Plan 指令附加到 **user 消息**开头并持久化 | **验收实证**：环境块若作为独立 system 消息，时间一刷新整个 system 前缀缓存全部失效（hit=0）；附加到 user 消息后命中 91% |
| 注入实现 | `<sys-instruct>` 标签文本，附加到 user 消息（轮首）/ tool result（循环中） | OpenAI 兼容格式禁止 system 乱序，附加到现有消息协议安全；注入内容必须随 user 消息**持久化**，否则首条 user 消息跨轮不一致导致缓存失效 |
| Plan 变频 | 计数在 PlanModeInjector 内，第 1/4/7…轮完整、其余精简；随 user 消息持久化 | 首轮强提醒，间隔刷新防遗忘；持久化保证首条 user 消息跨轮字节一致 |
| 温和提醒 | 阈值 5 次，触发当轮注入一次（附加到 tool result 副本，不持久化） | 按 spec F7；tool result 位于缓存前缀之后，瞬时注入对缓存影响可忽略 |
| 环境块位置 | user 消息开头（紧贴用户输入前） | 实证：放进 system 块会因时间刷新导致整块失效 |

> **验收实证结论（关键）**：DeepSeek 把 system 块（稳定指令 + 环境块）当作原子缓存单元。任何 system 内容的变动——哪怕只有一个时间字段——都会让整个 system 前缀缓存失效。因此"会变化的内容必须离开 system 块"，这也是环境块和 Plan 指令都移入 user 消息的原因。
