# 智能销售数据分析 Agent：职责与关键代码片段

> 说明：本文根据 `docs/resume/project.md` 中的项目职责整理。原职责中偏 Java 生态的表述，如 Redis、ThreadLocal、Micrometer，已按当前 Python / FastAPI / LangChain 项目实现调整。

## 1. LangChain 工具集与 Agent 编排

建议职责写法：

基于 LangChain `create_agent` ，设计覆盖查询 / 统计 / 趋势 / 图表 / 异常预警五类场景的工具集，Agent 通过 ReAct 循环自主规划调用链路，单次提问最多串联 5 步工具调用完成复杂分析任务

关键代码：

```python
# app/tools/registry.py
def create_sales_tools(
    *,
    session: AsyncSession,
    service: SalesQueryService | None = None,
    today: date | None = None,
    current_user: CurrentUser | None = None,
) -> list[BaseTool]:
    query_service = service or SalesQueryService(current_user=current_user)
    current_date = today or date.today()
    return [
        create_sales_query_tool(session, query_service),
        create_sales_summary_tool(session, query_service),
        create_sales_trend_tool(session, query_service, current_date),
        create_chart_generator_tool(session, query_service, current_date),
        create_anomaly_detection_tool(session, query_service, current_date),
    ]
```

```python
# app/agent/runtime.py
agent_kwargs = {
    "model": agent_model,
    "tools": self.tools,
    "system_prompt": self.system_prompt,
    "middleware": [self._build_summary_middleware(settings)],
}
self.agent = agent_factory(**agent_kwargs)
```


## 2. LLM 友好的工具输出与图表协议

建议职责写法：

LLM 友好型工具输出设计，工具返回值统一格式化为自然语言，降低模型推理认知负担，提升多步推理答案质量；图表工具使用 `CHART_JSON:` 前缀协议，便于前端识别并渲染。

关键代码：
```python
@tool(args_schema=SalesSummaryInput)
async def calculate_sales_summary(...):
    """计算销售汇总统计，包括总销售额、销售员排名、大区排名、产品排名、Top N 分析。"""
    if summary_type == "total":
        result = await _sales_total(service, session, start, end, region_name_value)
        return tool_call_finished(tool_name, started_at, result)
```

```python
# app/tools/sales_query_tool.py
lines = [
    f"订单查询结果（{start} 至 {end}{title_scope}）：",
    f"共找到 {total} 条订单" + (f"，以下显示前 {len(orders)} 条" if len(orders) < total else ""),
    "",
]

for order in orders:
    lines.append(
        f"- 订单号：{order.order_no} | 日期：{order.order_date} | 销售员：{order.rep_name} | "
        f"客户：{order.customer_name} | 金额：{format_money(order.amount)} | 状态：{translate_status(order.status)}"
    )

lines.append(f"小计：完成订单 {completed_count} 笔，金额合计 {format_money(completed_total)}")
return "\n".join(lines)
```

```python
# app/tools/formatting.py
def format_money(value: Decimal) -> str:
    return f"¥{value:,.0f}"


def translate_status(status: str) -> str:
    translations = {
        "COMPLETED": "已完成",
        "REFUNDED": "已退款",
        "CANCELLED": "已取消",
    }
    return translations.get(status, status)


def tool_empty_data(message: str) -> str:
    return f"TOOL_EMPTY_DATA\n{message}\n可能原因：该时段无交易、数据尚未录入，或查询条件过于严格。"
```

```python
# app/tools/chart_generator_tool.py
option = {
    "title": {"text": title or "销售对比"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": names, "axisLabel": {"rotate": 30}},
    "yAxis": {"type": "value", "name": "销售额（元）"},
    "series": [{"type": "bar", "data": values}],
}
return "CHART_JSON:" + json.dumps(option, ensure_ascii=False)
```

## 3. Prompt 工程与能力边界

建议职责写法：

设计结构化 Prompt，System Prompt 注入当天日期解决模型时间感知盲区，注入用户权限及其能力边界防止越界推理

关键代码：

```python
# app/agent/prompts.py
def build_system_prompt(today: date | str, current_user: CurrentUser | None = None) -> str:
    prompt = SYSTEM_PROMPT_TEMPLATE.format(today=str(today))
    if current_user is None:
        return prompt
    return (
        prompt
        + "\n\n"
        + "Current authenticated user:\n"
        + f"- username: {current_user.username}\n"
        + f"- role: {current_user.role}\n"
        + f"- permission scope: {current_user.permission_description()}\n"
        + "Only answer with sales data inside this permission scope. "
        + "The service layer enforces the same boundary."
    )
```

## 4. Token 成本控制与监控
建议职责写法：

模型上下文达到 20 条消息时触发摘要压缩，并保留最近 6 条消息保证追问连贯性，解决了多轮历史对话持续累积导致的上下文膨胀；LangChain usage metadata 采集每次 Agent 调用的输入、输出和缓存 token，并按百万 token 单价估算成本并输出结构化日志，以实现 Token 用量监控

关键代码：

```python
# app/core/config.py
token_input_price_per_1m: Decimal = Decimal("1")
token_cached_input_price_per_1m: Decimal = Decimal("0.2")
token_output_price_per_1m: Decimal = Decimal("2")
token_cost_currency: str = "CNY"

agent_summary_trigger_messages: int = 20
agent_summary_keep_messages: int = 6
```

```python
# app/agent/runtime.py
return SummarizationMiddleware(
    model=create_summary_chat_model(),
    trigger=("messages", settings.agent_summary_trigger_messages),
    keep=("messages", settings.agent_summary_keep_messages),
)
```

```python
# app/agent/runtime.py
with get_usage_metadata_callback() as usage_callback:
    result = await self.agent.ainvoke(payload, config=config)

usage = summarize_usage_metadata(usage_callback.usage_metadata)
if usage.total_tokens <= 0:
    usage = self._extract_usage(result)
log_token_usage(
    session_id=normalized_session_id,
    model_name=settings.openai_model,
    usage=usage,
    settings=settings,
)
```

```python
# app/core/token_usage.py
normal_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
cost = (
    Decimal(normal_input_tokens) / Decimal(1_000_000) * settings.token_input_price_per_1m
    + Decimal(usage.cached_input_tokens) / Decimal(1_000_000) * settings.token_cached_input_price_per_1m
    + Decimal(usage.output_tokens) / Decimal(1_000_000) * settings.token_output_price_per_1m
)

logger.info(
    format_kv(
        "token_usage",
        sessionId=session_id,
        model=model_name,
        inputTokens=usage.input_tokens,
        cachedInputTokens=usage.cached_input_tokens,
        outputTokens=usage.output_tokens,
        totalTokens=usage.total_tokens,
        estimatedCost=f"{estimated_cost:.6f}",
        currency=settings.token_cost_currency,
    )
)
```

## 5. 代码级数据权限控制

建议职责写法：

数据权限由 Prompt 软约束升级为代码级硬保障。仅依靠系统提示约束模型查询范围存在安全风险，LLM 行为不可控，Prompt 限制在推理过程中可能失效。系统通过 contextvars 传递用户权限上下文，实现权限控制与模型推理完全解耦，从代码层面杜绝越权查询。

关键代码：

```python
# app/core/user_context.py
_current_user: ContextVar[CurrentUser | None] = ContextVar("current_user", default=None)


def get_current_user() -> CurrentUser | None:
    return _current_user.get()


def set_current_user(user: CurrentUser) -> Token[CurrentUser | None]:
    return _current_user.set(user)


def reset_current_user(token: Token[CurrentUser | None]) -> None:
    _current_user.reset(token)
```

```python
# app/api/dependencies.py
async def get_sales_agent_runtime(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AsyncIterator[SalesAgentRuntime]:
    context_token = set_current_user(current_user)
    try:
        yield SalesAgentRuntime(session=session)
    finally:
        reset_current_user(context_token)
```

```python
# app/services/sales_query_service.py
@property
def current_user(self) -> CurrentUser | None:
    return get_current_user()
```

```python
# app/services/sales_query_service.py
if self.current_user is None or self.current_user.is_sales_director:
    return rep_id, region_id

if self.current_user.is_sales_rep:
    if rep_id is not None and rep_id != self.current_user.rep_id:
        return -1, -1
    if region_id is not None and region_id != self.current_user.region_id:
        return -1, -1
    return self.current_user.rep_id, self.current_user.region_id
```

## 6. 工具参数白名单与 SQL 注入防护

建议职责写法：

使用 Pydantic 约束工具参数，对日期格式、区域名称、图表类型等做白名单校验，在 LLM 将自然语言转换为工具参数后，提前拦截非法参数和异常值，避免无效参数进入业务查询；在 Repository 层，所有数据库访问统一通过 SQLAlchemy 表达式生成参数化查询，不进行 SQL 字符串拼接，以避免 SQL 注入

关键代码：

```python
# app/tools/schemas.py
ALLOWED_REGION_NAMES = frozenset({"华东区", "华南区", "华北区", "西南区"})


def _normalize_region_name(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped not in ALLOWED_REGION_NAMES:
        raise ValueError(REGION_ERROR)
    return stripped
```

```python
# app/tools/schemas.py
class SalesChartInput(ToolInputModel):
    chart_type: Literal["line", "bar", "pie"]
    dimension: Literal["region", "rep", "category"] = "region"
    months: int = Field(default=6, ge=1, le=24)
```

```python
# app/repositories/sales_order_repository.py
result = await session.execute(
    select(SalesOrder.rep_id, func.sum(SalesOrder.amount).label("total"))
    .where(SalesOrder.status == "COMPLETED")
    .where(SalesOrder.order_date.between(start, end))
    .group_by(SalesOrder.rep_id)
    .order_by(func.sum(SalesOrder.amount).desc())
)
```
