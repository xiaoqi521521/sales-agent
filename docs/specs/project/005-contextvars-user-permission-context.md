# ContextVars User Permission Context Spec

## 背景与目标

当前项目的权限边界已经明确：登录后只能看到自己、本大区或全公司范围内的数据，且这个边界必须在代码层生效，而不是只靠 Prompt 约束。

本阶段要解决的是“用户身份在请求链路中如何稳定传递”的问题。对于 FastAPI + async 场景，继续使用显式参数层层传递 `CurrentUser` 会让 `runtime -> tool -> service` 的调用链变长，也容易把权限边界分散在多个构造参数里。

因此本阶段改为使用 `contextvars.ContextVar` 存储请求级用户上下文：

- 认证依赖负责校验 JWT、加载用户信息；受保护的 runtime 依赖在认证成功后写入上下文。
- Service 和 Agent runtime 从上下文读取当前用户。
- 请求结束或异常时必须清理上下文，防止协程复用导致用户串号。

本阶段只解决“请求级用户上下文传递与清理”，不改认证模型本身，不改角色定义，不改数据库结构。

## 参考资料

- `docs/reference/24_用户认证与数据权限隔离.md`
- `docs/plans/001-sales-agent-refactor-master-plan.md`
- Python 官方 `contextvars` 文档（Context7 已核实 `ContextVar.set()` 返回 token，必须在 finally 中 `reset(token)`）

## In Scope

- 新增 `app/core/user_context.py`，封装请求级用户上下文的 `set/get/reset` 能力。
- 在受保护的 Agent runtime 依赖中把已验证的 `CurrentUser` 写入上下文。
- 请求结束、异常结束、流式响应结束时都要 reset 上下文。
- Service 层改为从上下文读取当前用户，并据此执行权限过滤。
- Agent runtime 和工具链路读取同一份用户上下文，不再把 `CurrentUser` 当作构造参数逐层传递。
- 增加测试，验证不同请求、不同角色、同步接口和 SSE 接口之间不会串用上下文。

## Out of Scope

- 不改 JWT 签发和校验逻辑。
- 不改角色定义。
- 不改数据库表结构。
- 不引入 Redis、Session、ThreadLocal 或额外权限中间件。
- 不把 `contextvars` 扩大到 traceId 之外的其它横切缓存。
- 不把用户上下文当作持久化数据。

## 设计

### 上下文模型

用户上下文只保存请求级的 `CurrentUser`，而不是原始 token、数据库 session 或其他业务对象。

建议形式：

- `ContextVar[CurrentUser | None]`
- 提供 `set_current_user(...)`
- 提供 `get_current_user()`
- 提供 `reset_current_user(token)`
- 可选提供 `require_current_user()`，在权限敏感场景下缺失上下文时直接失败

### 生命周期

1. 请求进入认证依赖。
2. 依赖解码 JWT，并从数据库加载 `SalesRep`，返回 `CurrentUser`。
3. 受保护的 runtime 依赖接收 `CurrentUser`，写入 `ContextVar`。
4. 后续 runtime、service、tool 调用从上下文读取当前用户。
5. 请求完成、抛异常、或流式响应结束时，使用 token 清理上下文。

### 边界约束

- Service 层仍然是权限过滤主边界。
- Agent 和 Tool 只能通过 Service 间接访问销售数据。
- `contextvars` 只负责“把当前用户带到正确的请求链路里”，不负责权限判断本身。
- 没有当前用户上下文的 protected 请求，必须视为认证链路异常，而不是默认放行。

### 与现有 `trace_id` 的关系

`app/core/request_context.py` 继续只负责 traceId。  
用户上下文单独放在 `app/core/user_context.py`，两者都属于 request-scoped context，但职责不重叠。

## 测试

### 必须覆盖

- 登录后当前请求能读到同一个 `CurrentUser`。
- 请求结束后上下文被清理。
- 不同请求之间不会串号。
- 销售员、主管、总监在同步 Agent 接口里看到不同范围的数据。
- SSE 流式接口在分片输出期间仍能读取同一用户上下文。
- 认证失败时不会留下残留用户上下文。

### 推荐测试文件

- `tests/integration/test_auth.py`
- `tests/integration/test_data_permissions.py`
- `tests/integration/test_agent_api.py`
- `tests/integration/test_agent_streaming.py`
- 新增 `tests/unit/test_user_context.py`

## 涉及文件

- 新增 `app/core/user_context.py`
- 修改 `app/api/dependencies.py`
- 修改 `app/services/sales_query_service.py`
- 修改 `app/agent/runtime.py`
- 视需要修改 `app/tools/*_tool.py`
- 修改/新增相关测试

## 验收标准

- 登录后的权限信息通过请求级上下文传递，不再依赖 Runtime -> Tool -> Service 的手工参数层层传递。
- 不同请求的用户上下文相互隔离。
- 请求结束后上下文被清理，不会污染后续请求。
- 现有角色权限边界保持不变。
- 同步接口和 SSE 接口都能稳定通过权限测试。
