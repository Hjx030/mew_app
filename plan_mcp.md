# MewCode MCP 客户端 Plan (v0.6)

## 架构概览

新增独立 `mewcode/mcp/` 包，按**传输层 / 协议层 / 适配层**分层。session 启动时调用 `mcp.discover()` 连接 server、发现工具、注册进工具中心。

| 组件 | 职责 | 对应 spec |
|------|------|-----------|
| **config.py** | 读 mcp_servers.yaml → server 配置对象（stdio/http 两种） | F1 |
| **transports/stdio.py** | 子进程 stdin/stdout，newline-delimited JSON，读者任务 + id 关联 | F2, F6 |
| **transports/http.py** | Streamable HTTP：POST + JSON/SSE 响应解析 + 会话头 + DELETE | F3, F6 |
| **client.py** | McpClient（握手/发现/调用）+ ConnectionPool（池化+空闲关闭） | F4, F5, F9 |
| **adapter.py** | 远端工具 → MewCode Tool（名称规范化 + Schema 透传 + tools/call 转发） | F7 |
| **policy/sandbox.py**（改） | 新增远端工具路径参数的最佳努力沙箱 | F8 |
| **tui/session.py**（改） | 启动时 discover + 注册；`/mcp` 命令 | F9, F10 |
| **cli.py / __main__.py**（改） | `--mcp-config` 参数传递 | F1 |

## 核心数据结构

```python
# config.py
@dataclass
class StdioServerConfig:
    name: str
    transport: str = "stdio"
    command: str
    args: list[str]
    env: dict
    timeout_s: float = 30

@dataclass
class HttpServerConfig:
    name: str
    transport: str = "http"
    url: str
    headers: dict
    timeout_s: float = 30

McpServerConfig = StdioServerConfig | HttpServerConfig

# transports/base.py
class Transport(ABC):
    async def connect(self) -> None: ...
    async def request(self, msg: dict) -> dict: ...   # 发送并返回按 id 关联的响应
    async def notify(self, msg: dict) -> None: ...    # 通知（无响应）
    async def close(self) -> None: ...

# client.py
@dataclass
class ToolInfo:
    name: str          # 远端原始工具名
    description: str
    input_schema: dict
```

## 模块设计

### config.py

- `DEFAULT_MCP_CONFIG = ~/.config/mewcode/mcp_servers.yaml`
- `load_mcp_config(path=None) -> list[McpServerConfig]`：path 缺省读默认文件；显式指定但文件不存在 → 抛 ConfigError；文件存在但不可解析 → 抛 ConfigError；单个条目格式错误 → 跳过该条目并打印警告（不静默，也不阻塞其余）

### transports/base.py — Transport 抽象

- `connect()` / `request(msg)` / `notify(msg)` / `close()`，四个方法定义传输契约

### transports/stdio.py — StdioTransport

- `connect()`：`asyncio.create_subprocess_exec(command, *args, env=...)`，启动读取任务
- 读取任务：持续 `readline` stdout，解析 JSON；有 `id` 且命中 pending → resolve future；`id` 不命中或通知 → 忽略/记录
- `request(msg)`：id 注册 pending future，写 `json.dumps(msg)+"\n"` 到 stdin，`await future`
- 处理：子进程退出 → 所有 pending 报错；命令不存在 → connect 报错

### transports/http.py — StreamableHttpTransport

- `connect()`：无预先动作（会话在 initialize 时建立）
- `request(msg)`：`POST url`，头含 `Accept: application/json, text/event-stream`、`MCP-Protocol-Version`、`Mcp-Session-Id`（若有）；响应 `application/json` → 直接返回；`text/event-stream` → 逐事件解析，找到 `id` 匹配的 `message` 事件返回；响应头含 `Mcp-Session-Id` → 存下回传
- `notify(msg)`：POST 后忽略响应体（规范下返回 202）
- `close()`：`DELETE url` 结束会话（带会话头）
- 错误处理：404 → 会话失效，可重连；405 → 方法不支持报错

### client.py — McpClient

- `initialize()`：`_request("initialize", {protocolVersion, capabilities:{}, clientInfo:{name:"mewcode",version:...}})` → 存 `protocol_version`/`server_info`；随后 `_notify("notifications/initialized")`
- `list_tools() -> list[ToolInfo]`：`_request("tools/list", {})`，按 `nextCursor` 分页循环直到无 cursor
- `call_tool(name, arguments) -> str`：`_request("tools/call", {name, arguments})` → 格式化 `content`（拼 text 块，`isError` 加前缀）
- `_request` / `_notify`：分配递增 id，转发到 transport
- `close()`
- **ConnectionPool**：`{server_name: McpClient}` 缓存；`get(name)` 复用；空闲超时（60s）任务关闭 idle 连接

### adapter.py — McpTool

- `make_mcp_tool(server_name, tool_info, client) -> Tool`
- 名称：`mcp_<server>_<tool>`，替换非 `[a-zA-Z0-9_-]` 为 `_`
- `description` 透传；`parameters` = input_schema（确保 `type: object`，缺 properties 补空）
- `run(**kwargs)`：`await client.call_tool(原始名, kwargs)`，返回字符串；异常转错误字符串

### policy/sandbox.py（改）

- 新增 `check_remote_args(args, root) -> str | None`：扫描参数中 key 含 `path`/`dir`/`file` 的值或明显绝对路径的值，解析后越界返回原因（best-effort）
- engine 的 `decide` 对 `mcp_*` 工具在规则未命中后调用此检查

### tui/session.py（改）

- `run_session(..., mcp_config_path=None)`：启动时 `tools, errors = await discover(mcp_config_path)`，注册进 tool_registry，errors 作为系统提示显示
- `/mcp` 命令：列出以 `mcp_` 开头的已加载工具 + server 状态

### cli.py / __main__.py（改）

- `--mcp-config` 参数；`__main__` 把值传给 `run_session`

## 模块交互

```
MewCode 启动
  │
  ▼
session.run_session ──discover(mcp_config_path)──►  mcp/__init__.discover()
  │                                                   │
  │                                                   ├─ load_mcp_config → 配置列表
  │                                                   ├─ 逐个 server:
  │                                                   │    ConnectionPool.get(name)
  │                                                   │    → McpClient.connect()
  │                                                   │    → initialize() 握手
  │                                                   │    → list_tools() 发现
  │                                                   │    → make_mcp_tool() 包装
  │                                                   │    失败 → 收集错误，跳过
  │                                                   └─ 返回 (tools, errors)
  │
  ├─ 注册 MCP 工具进 tool_registry（Agent 可见、可调用）
  ├─ 渲染 errors 为启动提示
  │
  ▼
Agent Loop 中模型发起 mcp_filesystem_read_file 调用
  │
  ├─ policy.decide("mcp_filesystem_read_file", args)
  │    黑名单 / 规则 / 远端参数沙箱(check_remote_args) / 档位兜底
  │    （默认档：远端工具不在只读白名单 → ask）
  ├─ HITL 询问 / 直接执行
  │
  ▼
McpTool.run(**kwargs) → client.call_tool("read_file", kwargs)
  │                     → transport.request(tools/call)
  │                        stdio：写行 → 读者任务按 id resolve
  │                        http：POST → 解析 JSON/SSE 响应
  └─ 结果格式化回传模型 → 循环继续
```

## 文件组织

```
mewcode/
├── mcp/                          ← 新增包
│   ├── __init__.py               # discover() 主入口
│   ├── config.py                 # McpServerConfig 模型 + 加载
│   ├── client.py                 # McpClient + ConnectionPool
│   ├── adapter.py                # McpTool（包装成 Tool）
│   └── transports/
│       ├── __init__.py
│       ├── base.py               # Transport 抽象
│       ├── stdio.py              # StdioTransport
│       └── http.py               # StreamableHttpTransport
├── policy/
│   └── sandbox.py                # 改：check_remote_args
├── tui/
│   └── session.py                # 改：discover + /mcp
└── cli.py / __main__.py          # 改：--mcp-config
```

新增测试：`test_mcp_config.py`（配置解析）、`test_mcp_client.py`（stdio/http mock server 端到端）、`test_mcp_adapter.py`（适配与注册）
测试用 mock server：`tests_mock/mock_stdio_server.py`（stdin/stdout JSON-RPC 脚本）、本地 HTTP mock server（内联在测试里）

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 协议版本 | 固定请求 `2025-06-18`，接受服务器协商结果 | 规范握手语义；不追求多版本 |
| 传输抽象 | `Transport.request/notify/close`，id 关联在传输内部 | stdio 用读者任务+future，http 用同步 POST，各自封装 |
| stdio 关联 | 读者任务持续读 stdout，pending future 按 id resolve | 支持 server 中途插 notification，F6 异步匹配 |
| HTTP 响应 | 支持 `application/json` 直接返回 + `text/event-stream` 扫 id | Streamable HTTP 规范两种响应形式 |
| 会话管理 | `Mcp-Session-Id` 头回传；`close` 时 `DELETE` | 规范要求；404 时允许重连 |
| 工具命名 | `mcp_<server>_<tool>`，sanitize 非 `[a-zA-Z0-9_-]` | OpenAI 函数名限制；server 前缀防冲突 |
| Schema 转换 | MCP inputSchema 直接作为 Tool.parameters | MCP 和 MewCode 都用 JSON Schema，可透传 |
| 安全集成 | 远端工具走 PolicyEngine；新增 `check_remote_args` 扫路径参数 | 与 v0.5 纵深防御一致 |
| 连接池 | ConnectionPool 按 server 名缓存 McpClient，空闲 60s 关闭 | 避免每次调用重连 |
| 启动失败 | 单个 server 失败跳过+提示，不阻塞 | N2 健壮性 |
| 配置解析 | 显式路径缺失/文件损坏→报错；单条目损坏→警告跳过 | F1 与 N2 平衡 |
