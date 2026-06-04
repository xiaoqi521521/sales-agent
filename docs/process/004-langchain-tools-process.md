# LangChain 工具层编写过程

本文档记录 Phase 4 的 5 个 LangChain 工具编写过程，说明工具粒度、参考资料、依赖选择和测试方式。

## 参考资料

本阶段先读取 `docs/reference/00_SUMMARY.md`，再加载 Phase 4 直接相关文献：

- `docs/reference/09_工具设计原则.md`
- `docs/reference/10_工具一-销售数据查询.md`
- `docs/reference/11_工具二-统计汇总与排名.md`
- `docs/reference/12_工具三-同比环比与趋势分析.md`
- `docs/reference/13_工具四-图表数据生成.md`
- `docs/reference/14_工具五-异常数据告警.md`

同时使用 Context7 查询 LangChain 官方文档，确认当前 Python 工具创建方式：

- 使用 `@tool` 创建工具。
- 使用 `args_schema` 接入 Pydantic 参数对象。
- 工具描述通过 docstring/description 帮助模型选择工具。
- 后续 Agent runtime 可直接绑定 `BaseTool` 列表。

## 依赖引入

通过 uv 引入 LangChain：

```bash
uv add langchain
```

引入后更新：

- `pyproject.toml`
- `uv.lock`

当前工具层只需要 `langchain` 和随包引入的 `langchain-core`。`langchain-openai` 留到 Agent runtime 阶段再引入。

## 工具粒度

工具粒度严格对齐参考文献中的 5 类问题：

1. `query_sales_orders`

   查询原始销售订单数据。适用于具体订单、客户订单、某时段订单列表。不负责统计、排名、趋势和图表。

2. `calculate_sales_summary`

   计算销售汇总与排名。通过 `summary_type` 支持总销售额、销售员排名、大区排名、产品排名。

3. `analyze_sales_trend`

   分析销售趋势。通过 `trend_type` 支持环比、同比、月度趋势。

4. `generate_sales_chart`

   生成 ECharts 图表 JSON。通过 `chart_type` 支持折线图、柱状图、饼图，返回 `CHART_JSON:{...}`。

5. `detect_sales_anomalies`

   自动检测销售异常，包括大区订单量骤降、产品连续零销售、销售员退单率异常、销售员业绩骤降。

## 编写顺序

1. 先写测试

   新增 `tests/integration/test_sales_tools.py`，使用 SQLite 内存库和样例数据验证：

   - registry 暴露 5 个工具。
   - 工具名称与参考粒度一致。
   - 文本工具返回可读文本。
   - 图表工具返回 `CHART_JSON:` 前缀和可解析 JSON。
   - 异常检测工具能输出预期异常类型。

2. 创建工具参数 schema

   新增 `app/tools/schemas.py`，用 Pydantic 定义：

   - `SalesQueryInput`
   - `SalesSummaryInput`
   - `SalesTrendInput`
   - `SalesChartInput`

   schema 中对日期格式、枚举值、可选参数含义进行描述，帮助模型正确传参。

3. 创建格式化工具函数

   新增 `app/tools/formatting.py`，封装空字符串处理、日期解析、金额格式化、状态翻译和日期错误提示。

4. 分别实现 5 个工具模块

   - `app/tools/sales_query_tool.py`
   - `app/tools/sales_summary_tool.py`
   - `app/tools/sales_trend_tool.py`
   - `app/tools/chart_generator_tool.py`
   - `app/tools/anomaly_detection_tool.py`

   每个模块提供一个 `create_*_tool(...)` 工厂函数，通过闭包拿到 `AsyncSession` 和 `SalesQueryService`。

5. 创建 registry

   新增 `app/tools/registry.py`，提供 `create_sales_tools(session=..., service=..., today=...)`，统一返回 5 个 LangChain `BaseTool`。

## 主要文件职责

### `app/tools/schemas.py`

定义工具入参模型。它面向模型调用，不直接复用 API schema，是为了让工具描述、参数枚举和值域更贴近 LangChain 工具调用语义。

### `app/tools/formatting.py`

放置工具层复用的格式化函数。这样每个工具文件只关注业务意图，减少重复的日期、金额、状态处理代码。

### `app/tools/sales_query_tool.py`

实现原始订单查询工具。返回结构化文本，包含订单号、日期、销售员、客户、金额、状态和小计。

### `app/tools/sales_summary_tool.py`

实现统计汇总与排名工具。内部按 `summary_type` 分发到总销售额、销售员排名、大区排名、产品排名。

### `app/tools/sales_trend_tool.py`

实现趋势分析工具。支持：

- `mom`：环比，支持自动计算上一等长周期。
- `yoy`：同比，自动计算去年同期。
- `monthly`：近 N 个月趋势。

### `app/tools/chart_generator_tool.py`

实现 ECharts option 生成。文本工具返回给模型阅读，图表工具返回给前端消费，因此返回值以 `CHART_JSON:` 开头。

### `app/tools/anomaly_detection_tool.py`

实现异常检测。参考文献中“销售员业绩骤降”示例残缺，但当前 Repository 已有 `sum_amount_by_rep`，因此补齐了完整实现。

### `app/tools/registry.py`

后续 Agent runtime 的工具入口。Agent 层不需要逐个知道工具模块，只需要调用 `create_sales_tools(...)` 获取工具列表。

## 设计取舍

- 使用 LangChain 官方推荐的 `@tool(args_schema=...)`。
- 工具以自然语言文本为主，符合参考文献“返回结构化文本”的原则。
- 图表工具例外，返回 `CHART_JSON:{...}`，供前端识别并渲染 ECharts。
- 工具层不直接拼 SQL，只调用 Service/Repository 已封装能力。
- 当前工具通过闭包持有 `AsyncSession`，适合后续在 API/Agent runtime 中按请求创建工具列表。
- 暂不引入 `ToolRuntime`，因为本阶段还未实现 Agent context、用户权限和持久记忆。后续 Phase 5/7 可再把用户上下文接入 runtime context。

## 验证命令

```bash
uv run python -m pytest tests\integration\test_sales_tools.py -v
```

完整集成测试：

```bash
uv run python -m pytest tests\integration -v
```

当前验证结果为 `14 passed`。
