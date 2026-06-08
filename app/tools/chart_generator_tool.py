import json
from decimal import Decimal

from langchain.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales_query_service import SalesQueryService
from app.tools.formatting import (
    blank_to_none,
    clamp,
    date_error_message,
    parse_required_range,
    tool_empty_data,
    tool_execution_error,
    tool_invalid_argument,
    tool_unknown_entity,
)
from app.tools.logging import tool_call_finished, tool_call_started
from app.tools.schemas import SalesChartInput


def create_chart_generator_tool(session: AsyncSession, service: SalesQueryService, today):
    @tool(args_schema=SalesChartInput)
    async def generate_sales_chart(
        chart_type: str,
        dimension: str = "region",
        start_date: str | None = None,
        end_date: str | None = None,
        months: int = 6,
        region_name: str | None = None,
        title: str | None = None,
    ) -> str:
        """生成销售图表的 ECharts JSON 数据。适用于折线图、柱状图、饼图、趋势图、排行榜图和销售占比图。"""
        tool_name = "generate_sales_chart"
        started_at = tool_call_started(
            tool_name,
            {
                "chart_type": chart_type,
                "dimension": dimension,
                "start_date": start_date,
                "end_date": end_date,
                "months": months,
                "region_name": region_name,
                "title": title,
            },
        )
        try:
            if chart_type == "line":
                result = await _line_chart(service, session, today, months, blank_to_none(region_name), title)
                return tool_call_finished(tool_name, started_at, result)
            start, end = parse_required_range(start_date, end_date)
            if chart_type == "bar":
                if dimension not in {"region", "rep"}:
                    return tool_call_finished(tool_name, started_at, tool_invalid_argument("柱状图支持的维度为 region 或 rep。"))
                result = await _bar_chart(service, session, dimension, start, end, title)
                return tool_call_finished(tool_name, started_at, result)
            if chart_type == "pie":
                if dimension not in {"region", "category"}:
                    return tool_call_finished(tool_name, started_at, tool_invalid_argument("饼图支持的维度为 region 或 category。"))
                result = await _pie_chart(service, session, dimension, start, end, title)
                return tool_call_finished(tool_name, started_at, result)
            return tool_call_finished(tool_name, started_at, tool_invalid_argument("未知图表类型，请使用 line、bar 或 pie。"))
        except Exception as exc:
            if isinstance(exc, ValueError):
                return tool_call_finished(tool_name, started_at, date_error_message(exc))
            return tool_call_finished(tool_name, started_at, tool_execution_error())

    return generate_sales_chart


async def _line_chart(service: SalesQueryService, session: AsyncSession, today, months: int, region_name: str | None, title: str | None):
    region_id = await service.get_region_id_by_name(session, region_name) if region_name else None
    if region_name and region_id is None:
        return tool_unknown_entity("大区", region_name)
    data = await service.query_monthly_trend(session, region_id, clamp(months, 1, 24), today=today)
    if not data:
        return tool_empty_data("暂无销售趋势数据，无法生成图表。")
    option = {
        "title": {"text": title or "销售趋势"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": [item.month for item in data]},
        "yAxis": {"type": "value", "name": "销售额（元）"},
        "series": [
            {
                "type": "line",
                "name": "销售额",
                "smooth": True,
                "data": [int(item.total_amount) for item in data],
            }
        ],
    }
    return "CHART_JSON:" + json.dumps(option, ensure_ascii=False)


async def _bar_chart(service: SalesQueryService, session: AsyncSession, dimension: str, start, end, title: str | None):
    if dimension == "rep":
        rows = await service.query_rep_ranking(session, start, end, 10)
        names = [row.rep_name for row in rows]
        values = [int(row.total_amount) for row in rows]
    else:
        rows = await service.query_region_ranking(session, start, end)
        names = [row.region_name for row in rows]
        values = [int(row.total_amount) for row in rows]
    if not names:
        return tool_empty_data(f"在 {start} 至 {end} 期间，暂无销售对比数据，无法生成图表。")
    option = {
        "title": {"text": title or "销售对比"},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": names, "axisLabel": {"rotate": 30}},
        "yAxis": {"type": "value", "name": "销售额（元）"},
        "series": [{"type": "bar", "data": values}],
    }
    return "CHART_JSON:" + json.dumps(option, ensure_ascii=False)


async def _pie_chart(service: SalesQueryService, session: AsyncSession, dimension: str, start, end, title: str | None):
    if dimension == "category":
        products = await service.query_product_ranking(session, start, end, 100)
        category_totals: dict[str, Decimal] = {}
        for product in products:
            category_totals[product.category] = category_totals.get(product.category, Decimal("0")) + product.total_amount
        data = [{"name": key, "value": int(value)} for key, value in category_totals.items()]
    else:
        regions = await service.query_region_ranking(session, start, end)
        data = [{"name": region.region_name, "value": int(region.total_amount)} for region in regions]
    if not data:
        return tool_empty_data(f"在 {start} 至 {end} 期间，暂无销售占比数据，无法生成图表。")
    option = {
        "title": {"text": title or "销售占比", "left": "center"},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"orient": "vertical", "left": "left"},
        "series": [{"type": "pie", "radius": "55%", "data": data}],
    }
    return "CHART_JSON:" + json.dumps(option, ensure_ascii=False)
