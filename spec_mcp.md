# MewCode MCP 客户端 Spec (v0.6)

## 背景

MewCode 已完成 Agent Loop（v0.3）、缓存感知 Prompt 重构（v0.4）、安全检查层（v0.5）。当前工具系统有 6 个**本地**工具（文件/命令/搜索），无法调用外部能力（GitHub、数据库、云服务等）。**MCP（Model Context Protocol）是让 agent 通过统一标准协议接入外部 server 的开放规范**——按官方 2025-06-18 规范手写一个客户端，既能彻底学会协议，又能连上兼容的第三方 server。

## 目标

- **手写 MCP 客户端**（不依赖官方 SDK，但严格兼容 2025-06-18 规范）：
  - 两种传输：**stdio**（本地子进程）+ **Streamable HTTP**（远程端点）
  - 三阶段：**initialize 握手 → tools/list 发现 → tools/call 调用**
  - JSON-RPC 2.0 请求带 id、响应按 id 关联
- **适配层**：把发现的远端工具包装成 MewCode 已有的 Tool 接口，注册进工具中心，Agent 调用时无感
- **连接池**：多个 server 的连接复用，避免每次调用都重连
- **安全集成**：远端工具调用同样走 v0.5 安全检查层

## 功能需求

- **F1 配置加载** — 从 `~/.config/mewcode/mcp_servers.yaml`（或 `--mcp-config` 指定路径）读取 server 列表。每条条目含：`transport`（`stdio` | `http`）、stdio 条目含 `command`/`args`/`env`、http 条目含 `url`/`headers`（静态鉴权头）、`timeout_s` 超时。配置缺失或格式错误时明确报错，不静默跳过。
- **F2 stdio 传输** — 启动子进程，JSON-RPC 消息经 stdin/stdout 以 **newline-delimited JSON** 收发；处理子进程意外退出、启动失败（命令不存在）的错误。
- **F3 Streamable HTTP 传输** — 向端点 `POST` JSON-RPC 请求，携带 `Mcp-Session-Id` 会话头（按响应中的值回传）；响应可能是 `application/json` 或 `text/event-stream` 两种，需都处理；支持 `DELETE` 结束会话；处理会话过期（404）与不支持方法（405）。
- **F4 握手初始化** — 连接建立后发送 `initialize`（协议版本 `2025-06-18`，能力声明、客户端信息），接收 `protocolVersion`/`capabilities`/`serverInfo` 完成版本协商；协商成功后再发 `notifications/initialized` 通知进入操作阶段。
- **F5 工具发现** — 发送 `tools/list` 获取远端工具清单（`name`/`description`/`inputSchema`），支持 cursor 分页（`nextCursor`）直到取完；发现的工具进入注册流程。
- **F6 JSON-RPC 关联** — 每个请求分配递增 id，响应/错误按 id 关联到发起方；请求-响应支持异步对应；按 JSON-RPC 错误码（`-32700` 解析错误、`-32601` 方法不存在等）区分错误。
- **F7 适配层** — 把每个远端工具包装成 MewCode `Tool`：名称规范化为 `mcp_<server>_<tool>`（去除非 `[a-zA-Z0-9_-]` 字符），`description` 透传，`inputSchema`（JSON Schema）转换为 MewCode 工具参数格式；调用时把参数转成 `tools/call` 请求，结果回传。
- **F8 安全集成** — 远端工具调用以规范化的名称进入 PolicyEngine 裁决（黑名单/规则/档位兜底）；远端工具的路径类参数同样做沙箱校验；HITL 询问与本地工具一致。
- **F9 连接池** — MewCode 启动时逐个连接配置的 server（握手 + 发现工具），连接缓存在池中复用；空闲超时（默认 60s）自动关闭；连接/握手失败的 server 跳过并在启动提示中说明，不影响其他 server。
- **F10 命令面** — 新增 `/mcp` 命令显示已加载的 MCP 工具列表和各 server 的连接状态。

## 非功能需求

- **N1 可测试性** — 传输层 / 协议层 / 适配层各自可独立单元测试，不依赖真实第三方 server；用自写的 mock server（stdio 脚本 + 本地 HTTP）做端到端验证。
- **N2 健壮性** — 某个 server 连接失败不阻塞 MewCode 启动；单次工具调用失败时把错误回传模型让模型决策，不崩溃 Agent Loop。
- **N3 兼容性** — 严格按 2025-06-18 规范实现消息格式与阶段流程，能连兼容该版本的第三方 server。

## 不做的事

- **resources / prompts 原语** — 本轮只做 tools 链路。
- **sampling / roots 能力** — 客户端向 server 暴露采样或根目录的机制，本轮不做。
- **新版 stateless MCP（2026 草案）** — 本轮按 2025-06-18 规范（有会话与握手）。
- **旧版 HTTP+SSE 传输（2024-11-05）** — 只做 Streamable HTTP。
- **OAuth 认证** — 只支持配置里的静态 headers 鉴权，不做动态授权流程。
- **MCP server 实现** — 本轮只写客户端，server 只用于测试 mock。

## 验收标准

| 编号 | 验收条件 | 对应需求 |
|------|---------|---------|
| AC1 | 配置加载正确：stdio 与 http 两种条目都能从 mcp_servers.yaml 解析出（验证：调配置加载，观察字段） | F1 |
| AC2 | stdio 传输 + mock server：完成 `initialize` → `tools/list` → `tools/call` 三阶段，工具发现正确（验证：mock server 端到端单测） | F2, F4, F5 |
| AC3 | Streamable HTTP 传输 + mock server：同样三阶段走通，会话头正确回传（验证：本地 HTTP mock 端到端） | F3, F4, F5 |
| AC4 | 发现工具以 `mcp_<server>_<tool>` 名称注册进 ToolRegistry，Agent 调用时走通 tools/call（验证：注册后 registry 查询 + 调用） | F7 |
| AC5 | 远端工具调用经 PolicyEngine 裁决：默认档下写类远端工具触发 ask、HITL 允许后执行（验证：确定性驱动） | F8 |
| AC6 | 连接池复用：连续两次调用同一 server 工具不重复 spawn/握手（验证：mock server 记录连接次数） | F9 |
| AC7 | 连接失败的 server 跳过并提示，其他 server 正常加载（验证：配置一个坏 server + 一个好 server） | F9, N2 |
| AC8 | `/mcp` 命令显示已加载工具与 server 状态（验证：驱动会话观察） | F10 |
| AC9 | 全部测试通过、导入正常（验证：pytest + `mewcode --version`） | N1 |
