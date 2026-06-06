# Phase 7 认证与权限过滤代码编写过程

## 参考依据

- `docs/reference/00_SUMMARY.md`
- `docs/reference/02_业务需求分析.md`
- `docs/reference/24_用户认证与数据权限隔离.md`
- Context7 查询 FastAPI 官方文档，确认当前主流写法仍是 `OAuth2PasswordBearer` 配合 JWT 和 `get_current_user` 依赖解析。

## 设计取舍

- 开发阶段不新增独立用户表，复用现有 `sa_sales_rep` 作为登录身份来源。
- 登录方式沿用参考文献中的 `repId` 登录，新增接口为 `POST /auth/login`。
- 本阶段只新增 `PyJWT` 依赖，用于生成和解析访问令牌。
- 暂不引入 `passlib` / `bcrypt`，因为当前没有实现密码登录；后续如果改成账号密码登录，再补密码哈希依赖。
- 没有照搬 Java 参考项目中的 `ThreadLocal UserContext`。FastAPI 是异步请求模型，因此采用请求级依赖注入，把当前用户显式传入 Agent Runtime、工具层和 Service 层。
- 权限过滤放在 `SalesQueryService`，而不是只放在 API 层，保证 Agent 和工具无法绕过权限边界。

## 角色权限

- `SALES_REP`：只能查看自己的 `rep_id` 数据；即使查询排行或聚合结果，也只基于自己的订单计算。
- `SALES_MANAGER`：只能查看自己所属 `region_id` 大区的数据。
- `SALES_DIRECTOR`：可以查看全公司数据，不额外加过滤条件。

## 主要代码改动

- 新增 `app/core/auth_context.py`，定义 `CurrentUser` 和角色判断方法；当前用户上下文只保留 `username`、`role`、`region_id`、`rep_id`。
- 新增 `app/core/security.py`，封装 JWT 创建、解析和过期校验。
- 新增 `app/schemas/auth.py`，定义登录请求、登录响应和当前用户 DTO。
- 新增 `app/api/v1/endpoints/auth.py`，实现 `POST /auth/login`。
- 修改 `app/api/dependencies.py`，通过 Bearer Token 解析当前用户，并从 `sa_sales_rep` 加载用户信息。
- 修改 `app/api/v1/endpoints/agent.py`，让 `/agent/chat` 和 `/agent/chat/stream` 成为受保护接口。
- 修改 `app/agent/runtime.py`、`app/tools/registry.py`，把当前用户继续传入工具和 Service。
- 修改 `app/agent/prompts.py`，在 System Prompt 中补充当前用户角色和权限范围。
- 修改 `app/services/sales_query_service.py`，在订单查询、销售额汇总、销售员排行、大区排行、产品排行、趋势查询、异常辅助查询等入口统一注入权限过滤。
- 修改 `app/repositories/sales_order_repository.py`，补充按销售员和大区过滤的统计查询方法。
- 修改 `app/tools/anomaly_detection_tool.py`，异常检测不再自行枚举全部大区和销售员，而是通过 Service 获取当前用户可见范围。

## 测试改动

- 新增 `tests/integration/test_auth.py`：
  - 验证 `repId` 登录能返回 Bearer Token。
  - 验证未登录访问 `/agent/chat` 返回 `401`。
- 新增 `tests/integration/test_data_permissions.py`：
  - 验证销售员只能看到自己的订单和个人范围统计数据。
  - 验证主管只能看到本大区数据。
  - 验证总监可以看到全公司数据。
  - 验证工具层调用也会受到当前用户权限约束。
  - 验证销售员请求团队销售员排行或大区排行时，工具层返回权限引导，而不是返回无意义的伪排行。
- 修改已有 Agent API 和流式接口测试，为受保护接口注入测试用当前用户，继续验证原有响应结构。

## 验证命令

```bash
$env:PYTHONPATH='.'; uv run pytest -v
```

验证结果：`28 passed`。
