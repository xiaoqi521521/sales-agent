# ContextVars 用户上下文权限传递改造过程

## 背景

Phase 7 已经实现了 JWT 登录、角色权限和数据隔离，但早期实现采用显式参数传递当前用户：

```text
FastAPI dependency -> SalesAgentRuntime -> tools registry -> SalesQueryService
```

这种方式能工作，但调用链较长，后续新增工具或服务时容易继续把 `CurrentUser` 当作构造参数层层传递。为了让权限上下文更接近请求级横切信息，本次改造改为使用 `contextvars.ContextVar` 存储当前请求用户。

本次目标：

- 保留原有 JWT 登录和角色权限语义。
- 当前用户上下文在受保护请求内可读。
- 请求结束、异常或流式响应结束后必须 reset。
- Service 层继续作为权限过滤主边界。
- 移除 Runtime、Tool、Service 构造参数中的 `CurrentUser` 传递。

## 参考资料

- `docs/reference/24_用户认证与数据权限隔离.md`
- `docs/plans/001-sales-agent-refactor-master-plan.md`
- `docs/specs/project/005-contextvars-user-permission-context.md`
- Python 官方 `contextvars` 文档，经 Context7 核实：
  - `ContextVar.set(...)` 返回 token。
  - 应在 `finally` 中调用 `reset(token)` 恢复之前的上下文值。

## 设计取舍

- `get_current_user` 认证依赖仍只负责解析 JWT、查询销售员并返回 `CurrentUser`，不直接写入 `ContextVar`。
- `get_sales_agent_runtime` 是当前 Agent 受保护接口的运行时依赖，因此由它在认证成功后写入用户上下文，并在 `finally` 中 reset。
- 这样可以避免普通认证依赖被其它测试或接口复用时产生额外副作用。
- 当前实现只保证 Agent 同步接口和 SSE 流式接口自动拥有用户上下文；后续如果新增其它受保护业务接口，需要复用相同的上下文依赖边界。
- `SalesQueryService` 在没有当前用户上下文时保持原有不加权限过滤行为，便于普通 service/tool 单测继续覆盖基础业务查询；受保护请求必须通过 runtime 依赖写入上下文。

## 主要代码改动

### `app/core/user_context.py`

新增请求级用户上下文模块：

- `set_current_user(user)`：写入当前用户并返回 token。
- `get_current_user()`：读取当前用户，未设置时返回 `None`。
- `require_current_user()`：权限敏感场景可强制要求上下文存在。
- `reset_current_user(token)`：使用 token 恢复之前的上下文值。

### `app/api/dependencies.py`

调整 `get_sales_agent_runtime(...)`：

- 继续依赖 `get_current_user(...)` 完成 JWT 认证。
- 使用 `set_current_user(current_user)` 写入请求级上下文。
- `yield SalesAgentRuntime(session=session)`。
- 在 `finally` 中调用 `reset_current_user(context_token)`，确保正常返回、异常返回和流式响应结束后都会清理上下文。

### `app/agent/runtime.py`

移除 `SalesAgentRuntime.__init__` 的 `current_user` 参数。

Runtime 初始化时：

- `create_sales_tools(session=session, today=self.today)` 不再传用户。
- `build_system_prompt(..., current_user=get_current_user())` 从上下文读取当前用户，用于提示词展示角色和权限范围。

### `app/tools/registry.py`

移除 `create_sales_tools(...)` 的 `current_user` 参数。

工具注册只负责绑定数据库会话、日期和可选 service；默认创建 `SalesQueryService()`，由 service 自己从上下文读取当前用户。

### `app/services/sales_query_service.py`

移除构造参数 `current_user`，改为属性读取：

```python
@property
def current_user(self) -> CurrentUser | None:
    return get_current_user()
```

原有权限过滤逻辑保持不变：

- 销售员只看自己的 `rep_id`。
- 主管只看自己的 `region_id`。
- 总监看全公司。

## 测试改动

### `tests/unit/test_user_context.py`

新增上下文单元测试：

- 验证当前用户可以 set/get/reset。
- 验证 `require_current_user()` 在缺失上下文时抛错。
- 验证嵌套设置后 reset 会恢复之前的用户。

### `tests/integration/test_auth.py`

新增 `test_protected_request_clears_current_user_context_after_response`：

- 登录后请求 `/agent/chat`。
- Fake runtime 在请求处理中断言当前用户上下文存在。
- 请求结束后断言 `get_current_user()` 回到 `None`。

### `tests/integration/test_data_permissions.py`

调整权限测试：

- 不再通过 `SalesQueryService(current_user=...)` 注入用户。
- 改为在测试中使用 `set_current_user(...)` 建立上下文。
- 每个测试都在 `finally` 中 reset。
- 工具层权限测试同样通过上下文驱动，验证工具调用仍受 Service 权限过滤约束。

### `tests/e2e/conftest.py`

调整 e2e fake runtime override：

- 移除 `SalesAgentRuntime(current_user=...)` 参数。
- 保留认证依赖，保证受保护接口仍需要登录用户。

## 文档同步

- 更新 `docs/plans/001-sales-agent-refactor-master-plan.md`：
  - Phase 7 增加 `app/core/user_context.py` 和 spec 文件。
  - 将 contextvars 用户上下文和 Service 权限过滤任务标记为完成。
  - 补充“请求完成后上下文被清理”的验收标准。
- 新增并修正 `docs/specs/project/005-contextvars-user-permission-context.md`：
  - 明确认证依赖负责解析用户。
  - 明确受保护 runtime 依赖负责写入和 reset 用户上下文。

## 验证命令

先尝试直接运行：

```powershell
uv run pytest tests/unit/test_user_context.py tests/integration/test_auth.py tests/integration/test_data_permissions.py tests/integration/test_agent_api.py tests/integration/test_agent_streaming.py tests/integration/test_agent_memory.py tests/integration/test_agent_summarization.py tests/integration/test_agent_token_logging.py tests/integration/test_sales_tools.py tests/integration/test_tool_parameter_validation.py tests/unit/test_agent_prompt.py -v
```

该命令因未设置 `PYTHONPATH`，在收集阶段出现 `ModuleNotFoundError: No module named 'app'`。

随后按项目既有测试方式设置 `PYTHONPATH`：

```powershell
$env:PYTHONPATH='.'; uv run pytest tests/unit/test_user_context.py tests/integration/test_auth.py tests/integration/test_data_permissions.py tests/integration/test_agent_api.py tests/integration/test_agent_streaming.py tests/integration/test_agent_memory.py tests/integration/test_agent_summarization.py tests/integration/test_agent_token_logging.py tests/integration/test_sales_tools.py tests/integration/test_tool_parameter_validation.py tests/unit/test_agent_prompt.py -v
```

沙箱内首次执行因无法访问用户目录下 `uv` 缓存失败，提升权限后重新运行通过。

验证结果：

```text
30 passed in 1.68s
```

