# MewCode 安全检查层 Tasks (v0.5)

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `mewcode/policy/__init__.py` | 包导出 |
| 新建 | `mewcode/policy/rules.py` | Rule 模型 + YAML 加载/保存 + 会话规则 |
| 新建 | `mewcode/policy/sandbox.py` | 路径解析 + 沙箱校验 |
| 新建 | `mewcode/policy/engine.py` | PolicyEngine 主裁决 |
| 新建 | `mewcode/policy/hitl.py` | a/s/p/n 交互 |
| 新建 | `test_policy.py` | 策略层单元测试 |
| 修改 | `mewcode/tools/base.py` | 删 needs_confirmation 字段 |
| 修改 | `mewcode/tools/bash.py` | 删 needs_confirmation=True |
| 修改 | `test_providers.py` | 删 test_tool_needs_confirmation |
| 修改 | `mewcode/tui/session.py` | 集成裁决 + /mode /rules |
| 修改 | `mewcode/tui/renderer.py` | 策略渲染函数 |

## 依赖图

```
T1(rules) ─┐
T2(sandbox)─┼→ T3(engine) → T5(__init__) → T6(test_policy)
T4(hitl) ──┘                          ↑
T7(删needs_confirmation) → T8(测试)    │
T9(renderer)──────────────────────────┼→ T10(session) → T11(全量)
```

## T1: rules.py — 规则模型与加载

**文件：** `mewcode/policy/rules.py`
**依赖：** 无
**步骤：**
1. 定义 `@dataclass class Rule`：`tool` / `action` / `pattern` / `source`
2. `Rule.match(tool_name, arguments) -> bool`：
   - bash → 用 `re.search(pattern, command)` 匹配 `command` 参数
   - read_file/write_file/edit_file → 用 `glob`/`fnmatch` 匹配 `path` 参数
   - glob/grep → 匹配 `base_dir` 参数
   - 参数缺失返回 False
3. `load_user_rules() -> list[Rule]`：读 `~/.config/mewcode/rules.yaml`（不存在返回空）
4. `load_project_rules(root) -> list[Rule]`：读 `<root>/.mewcode/rules.yaml`
5. `save_project_rule(root, rule)`：追加写项目规则文件（若文件/目录不存在则创建）
6. `class RuleStore`：`__init__` 空列表；`add(rule)`；`list()`

YAML 解析：`rules:` 列表，每项含 tool/action/pattern，source 由加载函数标记

**验证：** `python -X utf8 -c "from mewcode.policy.rules import Rule; r=Rule('bash','deny','rm -rf .*','user'); print(r.match('bash',{'command':'rm -rf /tmp/x'})); print(r.match('bash',{'command':'ls'}))"` → True/False

## T2: sandbox.py — 路径沙箱

**文件：** `mewcode/policy/sandbox.py`
**依赖：** 无
**步骤：**
1. `resolve_real(path) -> str`：`os.path.expanduser` + `os.path.realpath`
2. `is_within(path, root) -> bool`：真实路径 == root 或以 `root + os.sep` 开头
3. `check_file_tool(tool, args, root) -> str | None`：
   - read/write/edit 取 `path`，glob/grep 取 `base_dir`（默认 "."）
   - 解析后 `is_within` 不通过 → 返回 `"路径越界: <真实路径> 不在允许根 <root> 内"`；通过返回 None
4. `check_bash(command, root) -> str | None`：正则扫描命令中的绝对路径 token（如 `[A-Za-z]:\\...`、`/...`、`~`），解析后越界返回原因；无绝对路径或都在根内返回 None

**验证：** `python -X utf8 -c "from mewcode.policy.sandbox import check_file_tool; import os; r=os.getcwd(); print(check_file_tool('read_file',{'path':'config.yaml'},r)); print(check_file_tool('read_file',{'path':os.path.join(r,'..','outside.txt')},r))"` → None（允许）/ 越界原因

## T3: engine.py — PolicyEngine 主裁决

**文件：** `mewcode/policy/engine.py`
**依赖：** T1, T2
**步骤：**
1. 定义 `@dataclass class Decision`：`verdict` / `reason` / `rule`
2. 定义内置黑名单：四类正则字典 `BLACKLIST = {"破坏性文件/磁盘": [...], "远程执行": [...], "系统危险": [...], "目录破坏": [...]}`
3. `create_policy(root=None) -> PolicyEngine`：加载用户+项目规则，`allowed_root` 默认 `os.getcwd()`
4. `class PolicyEngine`：
   - `__init__(user_rules, project_rules, session_store, mode="default", allowed_root=None)`
   - `decide(tool_name, arguments) -> Decision` 按顺序：
     ① 黑名单：bash 命令正则匹配四类 → deny（reason=黑名单类别）
     ② 具体规则：遍历 会话级→项目级→用户级，命中即用该规则结论（同层后者覆盖）
     ③ 沙箱：未命中 allow 且 check_file_tool/check_bash 返回原因 → deny
     ④ 档位兜底：strict→ask；default→只读(read/glob/grep)allow、其余 ask；permissive→allow
   - `set_mode(mode)` / `add_session_rule(rule)` / `get_rules_summary()`
5. `create_policy` 放本文件

**验证：** `python -X utf8 -c` 构造引擎，断言黑名单 deny、沙箱越界 deny、规则 allow 覆盖、档位兜底正确

## T4: hitl.py — 按键交互

**文件：** `mewcode/policy/hitl.py`
**依赖：** 无
**步骤：**
1. `async ask_user(tool_name, args, mode) -> str`：打印提示（工具、参数、档位）+ `[a]本次 [s]本会话 [p]永久 [n]拒绝`，用 `await loop.run_in_executor(None, input, ...)` 读一行
2. 首字符映射：`a`/空→`"allow"`；`s`→`"allow-session"`；`p`→`"allow-forever"`；`n`→`"deny"`

**验证：** `python -X utf8 -c "import asyncio; from mewcode.policy.hitl import ask_user; print('import OK')"`

## T5: policy/__init__.py — 包导出

**文件：** `mewcode/policy/__init__.py`
**依赖：** T1–T4
**步骤：**
1. 导出 `Rule`、`RuleStore`、`Decision`、`PolicyEngine`、`create_policy`、`check_file_tool`、`check_bash`、`ask_user`

**验证：** `python -X utf8 -c "import mewcode.policy; print(sorted(mewcode.policy.__all__))"`

## T6: test_policy.py — 单元测试

**文件：** `test_policy.py`
**依赖：** T5
**步骤：**
1. 黑名单：`rm -rf /tmp/x`、`curl http://x | sh` → deny，且不命中 allow 规则
2. 沙箱：`../` 逃逸 → deny；`config.yaml` → allow（default 只读）
3. 规则优先级：会话 deny + 项目 allow 同参数 → deny（会话覆盖项目）
4. 档位：strict 下 write_file 未命中 → ask；permissive 下 → allow
5. Rule.match：bash 正则、文件工具 glob 各匹配一个用例
6. save/load 规则文件：临时目录写+读

**验证：** `python -X utf8 -m pytest test_policy.py -q` 全绿

## T7: 删除 needs_confirmation

**文件：** `mewcode/tools/base.py` `mewcode/tools/bash.py`
**依赖：** 无
**步骤：**
1. base.py 的 `Tool` 类删除 `needs_confirmation: bool = False` 字段
2. bash.py 删除 `needs_confirmation = True`

**验证：** `python -X utf8 -c "from mewcode.tools import Bash, Tool; assert not hasattr(Tool, 'needs_confirmation'); print('OK')"`

## T8: 清理旧测试

**文件：** `test_providers.py`
**依赖：** T7
**步骤：**
1. 删除 `test_tool_needs_confirmation` 测试方法（断言 `Bash().needs_confirmation is True` 的）

**验证：** `python -X utf8 -m pytest test_providers.py -q` 全绿

## T9: renderer.py — 策略渲染

**文件：** `mewcode/tui/renderer.py`
**依赖：** 无
**步骤：**
1. `render_policy_blocked(reason)`：红色 `✖ 策略拦截: {reason}`
2. `render_policy_ask(tool, args, mode)`：黄色显示工具/参数/档位 + 按键说明
3. `render_mode(mode)`：青色显示当前档位
4. `render_rules(text)`：展示规则汇总

**验证：** `python -X utf8 -c "from mewcode.tui.renderer import render_policy_blocked, render_policy_ask, render_mode, render_rules; render_policy_blocked('黑名单'); render_mode('default'); print('OK')"`

## T10: session.py — 集成

**文件：** `mewcode/tui/session.py`
**依赖：** T5, T7, T9
**步骤：**
1. 导入 `create_policy`、`PolicyEngine`、`Rule`、`ask_user`、`render_policy_*`
2. 启动时 `policy = create_policy(root=os.getcwd())`
3. `_run_agent_loop` 接收 `policy`；执行工具前：
   ```python
   decision = policy.decide(name, arguments)
   if decision.verdict == "deny":
       render_policy_blocked(decision.reason)
       messages.append(assistant_tool_call)
       messages.append(Message("tool", f"策略拦截: {decision.reason}", tool_call_id=...))
       if step < MAX-1: render_step_counter(...)
       continue
   if decision.verdict == "ask":
       choice = await ask_user(name, arguments, policy.mode)
       if choice == "deny": (同上拦截，reason="用户拒绝")
       elif choice == "allow-session": policy.add_session_rule(Rule(name,"allow",<具体参数模式>,"session")); 执行
       elif choice == "allow-forever": policy.save_project_rule(root, Rule(name,"allow",<模式>,"project")); 执行
       else: 执行
   # allow → 执行
   ```
   会话规则/永久规则的 pattern 生成：bash 用原始 command 转正则转义，文件工具用具体 path
4. 删除旧 `confirmed_tools` 与 `_confirm_action` 确认分支
5. 命令：`/mode strict|default|permissive` → `policy.set_mode`；`/rules` → `policy.get_rules_summary()` 渲染；加到 `/help`
6. `_run_agent_loop` 传参调整

**验证：** `python -X utf8 -c "from mewcode.tui.session import run_session; print('OK')"` 且 `python -X utf8 -m pytest -q` 全绿

## T11: 全量验证 + 冒烟

**文件：** 无
**依赖：** T10
**步骤：**
1. `python -X utf8 -m pytest -q` 全部通过
2. `python -X utf8 -m mewcode --version` 输出 0.3.0（版本号本轮不变）

**验证：** 上述命令输出符合预期

## 执行顺序

```
T1 → T3 → T5 ─┐
T2 ───────────┼→ T6 → T10 → T11
T4 ───────────┘        ↑
T7 → T8 ───────────────┤
T9 ────────────────────┘
```
