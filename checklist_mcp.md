# MewCode MCP 客户端 Checklist (v0.6)

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] **[配置加载]** stdio/http 两种条目从 yaml 正确解析；坏条目警告跳过、显式路径缺失报错（验证：test_mcp_config）
- [ ] **[stdio 传输]** 与 mock server 完成 initialize→tools/list→tools/call 三阶段（验证：test_mcp_client stdio 用例）
- [ ] **[HTTP 传输]** 与本地 HTTP mock 完成三阶段，会话头正确回传（验证：test_mcp_client http 用例）
- [ ] **[JSON-RPC 关联]** 请求带递增 id、响应按 id 关联；错误码区分（验证：单测断言响应匹配）
- [ ] **[适配层]** 工具名规范化 `mcp_<server>_<tool>`、注册进 registry、调用走 tools/call（验证：test_mcp_adapter）
- [ ] **[远端沙箱]** `mcp_*` 工具的路径类参数越界被 deny（验证：test_policy 新增用例）

## 集成

- [ ] **session 启动 discover** 启动时连接 server、注册 MCP 工具、失败 server 跳过并提示（验证：驱动会话观察）
- [ ] **远端工具走安全层** 默认档下写类远端工具触发 HITL 询问（验证：确定性驱动）
- [ ] **`/mcp` 命令** 显示已加载 MCP 工具与 server 状态（验证：驱动会话观察）

## 编译与测试

- [ ] 全部测试通过（验证：`python -X utf8 -m pytest -q`，期望 57 + 新增全绿）
- [ ] 无导入错误、版本正常（验证：`python -X utf8 -m mewcode --version` 输出 0.3.0）

## 端到端场景

- [ ] **场景 1（stdio mock 全链路）**：启动带 mock_stdio_server 的配置 → 工具被注册 → 让模型调用一个远端工具 → 结果回传（验证：mock server 端到端）
- [ ] **场景 2（连接池复用）**：连续两次调用同一 server 工具，spawn/连接次数不增（验证：mock 记录连接次数）
- [ ] **场景 3（失败跳过）**：配置一个坏 server + 一个 mock server → 坏 server 提示、mock 正常加载工具（验证：驱动会话）
- [ ] **场景 4（安全裁决）**：让模型调用远端写类工具 → 默认档触发 HITL（验证：驱动会话观察询问）
