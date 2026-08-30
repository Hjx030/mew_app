# MewCode MCP 客户端 Tasks (v0.6)

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `mewcode/mcp/__init__.py` | discover() 主入口 |
| 新建 | `mewcode/mcp/config.py` | McpServerConfig 模型 + 加载 |
| 新建 | `mewcode/mcp/transports/__init__.py` | 传输导出 |
| 新建 | `mewcode/mcp/transports/base.py` | Transport 抽象 |
| 新建 | `mewcode/mcp/transports/stdio.py` | StdioTransport |
| 新建 | `mewcode/mcp/transports/http.py` | StreamableHttpTransport |
| 新建 | `mewcode/mcp/client.py` | McpClient + ConnectionPool |
| 新建 | `mewcode/mcp/adapter.py` | McpTool |
| 新建 | `tests_mock/mock_stdio_server.py` | 测试用 stdio MCP server |
| 新建 | `test_mcp_config.py` | 配置解析单测 |
| 新建 | `test_mcp_client.py` | stdio/http 端到端单测 |
| 新建 | `test_mcp_adapter.py` | 适配与注册单测 |
| 修改 | `mewcode/policy/sandbox.py` `engine.py` | check_remote_args 远端沙箱 |
| 修改 | `mewcode/tui/session.py` | discover + /mcp |
| 修改 | `mewcode/cli.py` `__main__.py` | --mcp-config |

## 依赖图

```
T1(config) → T10(config测试)
T2(base) → T3(stdio)/T4(http) → T5(transports) → T6(client) → T7(adapter) → T8(discover)
T9(mock server)────────────────────────────────────────→ T11(client测试)/T12(adapter测试)
T13(policy sandbox) ────────────────────────────────────→ T14(session集成) → T15(全量)
```

## T1: config.py — server 配置模型与加载

**文件：** `mewcode/mcp/config.py`
**依赖：** 无
**步骤：**
1. `@dataclass StdioServerConfig`：name/transport="stdio"/command/args/env/timeout_s=30
2. `@dataclass HttpServerConfig`：name/transport="http"/url/headers/timeout_s=30
3. `DEFAULT_MCP_CONFIG = ~/.config/mewcode/mcp_servers.yaml`
4. `load_mcp_config(path=None) -> list`：path 缺省读默认文件（不存在返回空）；显式路径缺失或文件不可解析 → 抛 ValueError；条目缺 transport 或必填字段 → 警告并跳过
5. YAML 格式：`servers: {名称: {transport, command, args, env, url, headers, timeout_s}}`

**验证：** `python -X utf8 -c` 用临时 yaml 验证 stdio/http 两种解析 + 坏条目跳过

## T2: transports/base.py — Transport 抽象

**文件：** `mewcode/mcp/transports/base.py`
**依赖：** 无
**步骤：**
1. `class Transport(ABC)`：`async connect()` / `async request(msg) -> dict` / `async notify(msg)` / `async close()`，均 `pass` 或 `raise NotImplementedError`

**验证：** `python -X utf8 -c "from mewcode.mcp.transports.base import Transport; print('OK')"`

## T3: transports/stdio.py — StdioTransport

**文件：** `mewcode/mcp/transports/stdio.py`
**依赖：** T2
**步骤：**
1. `connect()`：`asyncio.create_subprocess_exec(command, *args, env=...)`，stdin/stdout 用 pipe；启动读者任务
2. 读者任务：`await proc.stdout.readline()` 循环 → `json.loads` → 有 `id` 且命中 `_pending` → `future.set_result(msg)`；否则忽略
3. `request(msg)`：`_pending[msg["id"]] = future`，写 `json.dumps(msg)+"\n"` 到 stdin，`await future`（带超时）
4. 子进程退出/异常 → 所有 pending future 设异常；`notify(msg)` 只写不读；`close()` 终止进程

**验证：** import 通过（端到端放 T11）

## T4: transports/http.py — StreamableHttpTransport

**文件：** `mewcode/mcp/transports/http.py`
**依赖：** T2
**步骤：**
1. `connect()`：无动作
2. `request(msg)`：用 `httpx.AsyncClient` POST `url`，headers 含 `Accept: application/json, text/event-stream`、`MCP-Protocol-Version: 2025-06-18`、`Mcp-Session-Id`（若有）、配置 headers；响应头取 `Mcp-Session-Id` 存下；`application/json` → 直接返回 body；`text/event-stream` → 按 `\n\n` 分事件，找 `data: {...}` 中 id 匹配的 message 返回
3. `notify(msg)`：POST 后忽略响应体；`close()`：带会话头 `DELETE url`
4. 错误：404 → 抛会话失效；405 → 抛不支持；其他非 200 → 抛 HTTP 错误

**验证：** import 通过（端到端放 T11）

## T5: transports/__init__.py — 传输导出

**文件：** `mewcode/mcp/transports/__init__.py`
**依赖：** T2–T4
**步骤：**
1. `make_transport(config) -> Transport`：按 `config.transport` 返回 Stdio/Http
2. 导出 `Transport`、`StdioTransport`、`StreamableHttpTransport`、`make_transport`

**验证：** `python -X utf8 -c "from mewcode.mcp.transports import make_transport; print('OK')"`

## T6: client.py — McpClient + ConnectionPool

**文件：** `mewcode/mcp/client.py`
**依赖：** T5
**步骤：**
1. `@dataclass ToolInfo`：name/description/input_schema
2. `class McpClient`：
   - `__init__(config)`：建 transport；`_next_id` 计数
   - `_request(method, params)`：id 递增，`transport.request({jsonrpc:"2.0",id,method,params})`；result 有 `error` 字段 → 抛错误
   - `initialize()`：`_request("initialize", {protocolVersion:"2025-06-18", capabilities:{}, clientInfo:{name:"mewcode",version:"0.3.0"}})` 存 server_info；`notify("notifications/initialized")`
   - `list_tools()`：循环 `_request("tools/list", {cursor?})` 直到无 `nextCursor`，收集 ToolInfo
   - `call_tool(name, arguments)`：`_request("tools/call", {name, arguments})` → 格式化 `content`（拼 text 块，`isError` 加前缀）
   - `close()`：transport.close()
3. `class ConnectionPool`：`_clients: dict[str, McpClient]`；`get(config)` 复用；`close_all()`

**验证：** import + T11 端到端

## T7: adapter.py — McpTool

**文件：** `mewcode/mcp/adapter.py`
**依赖：** T6
**步骤：**
1. `_sanitize(name)`：替换非 `[a-zA-Z0-9_-]` 为 `_`
2. `make_mcp_tool(server_name, tool_info, client) -> Tool`：返回 `McpTool` 子类实例
   - `name = "mcp_" + _sanitize(server_name) + "_" + _sanitize(tool_info.name)`
   - `description` 透传；`parameters` = input_schema（`type` 非 object 时包一层）
3. `McpTool.run(**kwargs)`：`await client.call_tool(原始名, kwargs)`，异常转错误字符串

**验证：** import + T12 单测

## T8: mcp/__init__.py — discover 主入口

**文件：** `mewcode/mcp/__init__.py`
**依赖：** T1, T6, T7
**步骤：**
1. `async discover(config_path=None) -> tuple[list[Tool], list[str]]`：
   - `load_mcp_config` → 逐个 server：`ConnectionPool.get(config)` → `initialize()` → `list_tools()` → `make_mcp_tool()` 收集
   - 异常捕获 → 记入 errors，跳过该 server
   - 返回 `(tools, errors)`
2. 导出 `discover`、`McpClient`、`ConnectionPool`、`McpTool`

**验证：** import + T11/T12 端到端

## T9: mock server — 测试基础设施

**文件：** `tests_mock/mock_stdio_server.py`（新建目录）
**依赖：** 无
**步骤：**
1. stdio mock：`main()` 循环 `sys.stdin.readline`，解析 JSON-RPC；响应 `initialize`（返回 2025-06-18/capabilities/serverInfo）、`tools/list`（返回 2 个工具：`read_file`/`write_file` 带 inputSchema）、`tools/call`（返回 content 文本或 isError）；其他方法返回 method-not-found 错误
2. HTTP mock：在 `test_mcp_client.py` 内用 `asyncio.start_server` 实现，POST 处理同样三方法，响应 JSON + 设 `Mcp-Session-Id` 头

**验证：** `python tests_mock/mock_stdio_server.py` 手动喂一行 initialize 看响应（或靠 T11 测试）

## T10: test_mcp_config.py — 配置单测

**文件：** `test_mcp_config.py`
**依赖：** T1
**步骤：**
1. 临时 yaml：stdio 条目、http 条目 → 解析正确
2. 显式路径缺失 → 抛错；坏条目 → 警告跳过；默认路径缺失 → 返回空

**验证：** `python -X utf8 -m pytest test_mcp_config.py -q` 全绿

## T11: test_mcp_client.py — 端到端单测

**文件：** `test_mcp_client.py`
**依赖：** T6, T9
**步骤：**
1. stdio：spawn mock_stdio_server，McpClient 完成 initialize → list_tools（2 个工具）→ call_tool 成功与失败
2. http：本地 asyncio HTTP server，同样三阶段 + 会话头回传验证
3. 连接复用：连续两次 call 同一 client，spawn/连接次数不增加

**验证：** `python -X utf8 -m pytest test_mcp_client.py -q` 全绿

## T12: test_mcp_adapter.py — 适配单测

**文件：** `test_mcp_adapter.py`
**依赖：** T7, T9
**步骤：**
1. 工具名规范化：`mcp_file-system_read-file` → `mcp_file_system_read_file`
2. 注册进 ToolRegistry：get_schemas 含该工具
3. 调用走 tools/call（用 mock client 断言转发）

**验证：** `python -X utf8 -m pytest test_mcp_adapter.py -q` 全绿

## T13: policy 远端沙箱

**文件：** `mewcode/policy/sandbox.py` `mewcode/policy/engine.py`
**依赖：** 无
**步骤：**
1. sandbox.py 新增 `check_remote_args(args, root) -> str | None`：遍历 args，key 含 `path`/`dir`/`file` 或值像绝对路径 → `resolve_real` → 越界返回原因
2. engine.py `decide`：工具名以 `mcp_` 开头且未命中规则时，调用 `check_remote_args`，越界 → deny
3. test_policy.py 加一个远端工具用例

**验证：** `python -X utf8 -m pytest test_policy.py -q` 全绿

## T14: session 集成 + 命令

**文件：** `mewcode/tui/session.py` `mewcode/cli.py` `mewcode/__main__.py`
**依赖：** T8, T13
**步骤：**
1. session：`run_session(..., mcp_config_path=None)` 启动时 `tools, errors = await discover(mcp_config_path)`；tools 注册进 tool_registry；errors 用 render_system 提示
2. `/mcp` 命令：列出以 `mcp_` 开头的已加载工具 + server 状态
3. cli.py 加 `--mcp-config`；__main__ 传给 run_session
4. /help 加 /mcp

**验证：** `python -X utf8 -c "from mewcode.tui.session import run_session; print('OK')"` + 全量 pytest

## T15: 全量验证 + 冒烟

**文件：** 无
**依赖：** T14
**步骤：**
1. `python -X utf8 -m pytest -q` 全部通过
2. `python -X utf8 -m mewcode --version` 输出 0.3.0

**验证：** 命令输出符合预期

## 执行顺序

```
T1 → T10
T2 → T3 → T5 → T6 → T7 → T8 ─┐
T2 → T4 ──────────────────────┤→ T14 → T15
T9 ───────────────────────────┤
T13 ──────────────────────────┘
T10/T11/T12 各依赖其目标模块
```
