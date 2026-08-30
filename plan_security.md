# MewCode 安全检查层 Plan (v0.5)

## 架构概览

新增独立 `mewcode/policy/` 包，承担安全策略的**裁决**职责（黑名单、沙箱、规则、档位、HITL），与模型和 TUI 解耦。session 在执行工具前调用裁决，作为唯一入口（F8 接管）。

| 组件 | 职责 | 对应 spec |
|------|------|-----------|
| **rules.py** | Rule 模型 + 三级规则加载（用户/项目 YAML、会话内存）+ 永久允许写回项目文件 | F3, F6 |
| **engine.py** | PolicyEngine：`decide(tool, args)` → allow/deny/ask；裁决顺序 黑名单→规则→沙箱→档位兜底 | F1-F6 |
| **sandbox.py** | 路径解析（realpath 防 `../`/符号链接）+ 越界校验；bash 尽力识别 | F2 |
| **hitl.py** | a/s/p/n 按键菜单交互 | F5 |
| **tools/base.py**（改） | 删除 `needs_confirmation` 字段 | F8 |
| **tui/session.py**（改） | 执行前调 `engine.decide()`；加 `/mode` `/rules` 命令；删旧确认分支 | F4, F7, F8 |
| **tui/renderer.py**（改） | 新增拦截提示、HITL 菜单、档位/规则展示 | F4, F5, F7 |

## 核心数据结构

```python
# rules.py — 规则
@dataclass
class Rule:
    tool: str        # "bash" | "read_file" | "write_file" | "edit_file" | "glob" | "grep"
    action: str      # "allow" | "deny" | "ask"
    pattern: str     # 文件工具=glob匹配路径；bash=正则匹配命令
    source: str      # "user" | "project" | "session"

# engine.py — 裁决结果
@dataclass
class Decision:
    verdict: str     # "allow" | "deny" | "ask"
    reason: str      # 黑名单/沙箱/规则/档位兜底 的说明
    rule: Rule | None

# engine.py — 档位
Mode = "strict" | "default" | "permissive"
```

## 模块设计

### rules.py

- `Rule.match(tool_name, arguments) -> bool`：按工具提取待匹配值——bash 取 `command`（正则匹配）；read/write/edit 取 `path`（glob 匹配）；glob/grep 取 `base_dir`（glob 匹配）
- `load_user_rules() -> list[Rule]`：读 `~/.config/mewcode/rules.yaml`
- `load_project_rules(root) -> list[Rule]`：读 `<root>/.mewcode/rules.yaml`
- `save_project_rule(root, rule)`：追加写入项目规则文件（HITL 永久允许用）
- `RuleStore`：会话级规则的内存列表（HITL 本会话允许时追加）

YAML 格式：
```yaml
rules:
  - tool: bash
    action: deny
    pattern: 'rm -rf .*'
  - tool: write_file
    action: allow
    pattern: 'logs/**/*.log'
```

### sandbox.py

- `resolve_real(path) -> str`：展开 `~`、`os.path.realpath`（解析 `..` 和符号链接）
- `is_within(path, root) -> bool`：真实路径 == root 或以 root+分隔符 开头
- `check_file_tool(tool, args, root) -> str | None`：越界返回原因，否则 None
- `check_bash(command, root) -> str | None`：正则扫描命令中的绝对路径 token，解析后越界则返回原因（best-effort，识别不了的返回 None 交给兜底）

### engine.py — PolicyEngine

- `__init__(user_rules, project_rules, session_store, mode="default", allowed_root=None)`
- `decide(tool_name, arguments) -> Decision`，按**固定裁决顺序**：
  1. **黑名单**（内置四类正则）→ 命中返回 `deny`（最高优先，任何 allow 规则不可覆盖）
  2. **具体规则**（会话级 > 项目级 > 用户级，同级后者覆盖）→ 命中 allow/deny/ask 返回对应结论；allow 可覆盖沙箱（显式授权越界）
  3. **沙箱** → 未命中 allow 且越界 → `deny`
  4. **档位兜底** → 未命中任何规则时：strict→`ask`；default→只读工具（read/glob/grep）`allow`、写入/执行（write/edit/bash）`ask`；permissive→`allow`
- `add_session_rule(rule)` / `set_mode(mode)` / `get_rules_summary()`

### hitl.py

- `async ask_user(tool_name, args, mode) -> str`：返回 `"allow" | "allow-session" | "allow-forever" | "deny"`；用 `input()` 读首字符，回车（空）默认 `"allow"`

### tui/session.py（改）

- 启动时 `create_policy(root=cwd)` 加载用户+项目规则
- `_run_agent_loop` 执行工具前：`decision = policy.decide(name, args)` →
  - `deny` → 渲染拦截原因，把"策略拦截"作为 tool 结果回给模型，`continue`（不执行）
  - `ask` → `hitl.ask_user`：`deny` 同上；`allow-session` → 加会话规则并执行；`allow-forever` → 写项目规则并执行；`allow` → 执行
  - `allow` → 直接执行
- 命令：`/mode strict|default|permissive` 调 `set_mode`；`/rules` 调 `get_rules_summary` 渲染
- 删除旧 `confirmed_tools` 和确认分支

### tui/renderer.py（改）

- `render_policy_blocked(reason)`（红）、`render_policy_ask(tool, args, mode)`（黄，HITL 菜单）、`render_mode(mode)`、`render_rules(text)`

## 模块交互

```
模型发起 tool_call
  │
  ▼
session._run_agent_loop 收到 tool_call
  │
  ▼
policy.engine.decide(tool, args)          ← 唯一入口（F8）
  │
  ├─ ① 黑名单命中 ──► deny → render_policy_blocked → 拦截消息回模型 → continue
  ├─ ② 规则命中 ──► allow → 执行
  │             └─► deny  → 同上拦截
  │             └─► ask   → 进入 HITL
  ├─ ③ 沙箱越界 ──► deny → 同上拦截
  └─ ④ 档位兜底 ──► 按 strict/default/permissive 出 allow 或 ask
                         │
                         ▼
                    HITL:  [a]本次 [s]本会话 [p]永久 [n]拒绝
                         │
               ┌─────────┼──────────┐
               ▼         ▼          ▼
           执行工具   加会话规则    写项目规则
                      (内存)      (rules.yaml)
               └─────────┴──────────┘
                   执行工具 → 结果入历史 → 继续循环
```

## 文件组织

```
mewcode/
├── policy/                    ← 新增包
│   ├── __init__.py            # 导出 PolicyEngine、Decision、create_policy 等
│   ├── rules.py               # Rule 模型 + YAML 加载/保存 + 会话规则存储
│   ├── engine.py              # PolicyEngine.decide() 主裁决
│   ├── sandbox.py             # 路径解析 + 沙箱校验
│   └── hitl.py                # a/s/p/n 交互
├── tui/
│   ├── session.py             # 集成裁决 + /mode /rules 命令
│   └── renderer.py            # 加策略相关渲染
└── tools/
    ├── base.py                # 删 needs_confirmation
    └── bash.py                # 删 needs_confirmation=True
```

新增测试：`test_policy.py`（黑名单/沙箱/规则优先级/档位兜底，纯单测不依赖 API）
规则文件位置：用户全局 `~/.config/mewcode/rules.yaml`、项目级 `<项目>/.mewcode/rules.yaml`

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 策略层组织 | 独立 `mewcode/policy/` 包 | 与模型/TUI 解耦，策略逻辑可独立单测 |
| 裁决顺序 | 黑名单 → 规则(会话>项目>用户) → 沙箱 → 档位兜底 | 黑名单最高（硬拦不可覆盖）；allow 规则可覆盖沙箱（显式授权越界）；档位兜底未命中的情况 |
| 规则匹配 | 文件工具 glob 匹配路径，bash 正则匹配命令 | 每种场景用最自然语法（已确认） |
| 沙箱实现 | `os.path.realpath` 解析后前缀比较 | 防 `../` 与符号链接逃逸 |
| bash 越界检测 | 正则扫描绝对路径 token + 解析比对 | best-effort，识别不了交给黑名单/规则/询问兜底 |
| HITL 交互 | 单行 `a/s/n/p` 按键菜单，回车默认 a | 已确认 |
| 永久允许 | 追加写项目级 `.mewcode/rules.yaml` | 已确认 |
| 档位切换 | `/mode` 命令改 `engine.mode`，立即生效 | 已确认 |
| needs_confirmation | 删除字段 + session 旧分支 + 对应测试 | F8 完全接管 |
| 黑名单实现 | 内置四类正则集合，硬拦截不询问 | 已确认四类清单 |
