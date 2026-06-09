from datetime import date
from decimal import Decimal

from langchain.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales_query_service import SalesQueryService
from app.tools.formatting import (
    blank_to_none,
    date_error_message,
    format_money,
    parse_required_range,
    tool_empty_data,
    tool_execution_error,
    tool_unknown_entity,
    translate_status,
)
from app.tools.logging import tool_call_finished, tool_call_started
from app.tools.schemas import SalesQueryInput


def create_sales_query_tool(session: AsyncSession, service: SalesQueryService):
    @tool(args_schema=SalesQueryInput)
    async def query_sales_orders(
        start_date: str,
        end_date: str,
        region_name: str | None = None,
        rep_name: str | None = None,
        customer_name: str | None = None,
        limit: int = 20,
    ) -> str:
        """查询原始销售订单数据，适用于查具体订单、某客户订单、某时段订单列表。不适用于统计排名、趋势分析、图表生成、异常检测。"""
        tool_name = "query_sales_orders"
        started_at = tool_call_started(
            tool_name,
            {
                "start_date": start_date,
                "end_date": end_date,
                "region_name": region_name,
                "rep_name": rep_name,
                "customer_name": customer_name,
                "limit": limit,
            },
        )
        try:
            start, end = parse_required_range(start_date, end_date)
            region_name_value = blank_to_none(region_name)
            rep_name_value = blank_to_none(rep_name)
            customer_name_value = blank_to_none(customer_name)

            region_id = await _resolve_region_id(service, session, region_name_value)
            if region_name_value and region_id is None:
                return tool_call_finished(tool_name, started_at, tool_unknown_entity("大区", region_name_value))

            rep_id = await _resolve_rep_id(service, session, rep_name_value)
            if rep_name_value and rep_id is None:
                return tool_call_finished(tool_name, started_at, tool_unknown_entity("销售员", rep_name_value))

            orders = await service.query_orders(session, rep_id=rep_id, region_id=region_id, start=start, end=end)
            if customer_name_value:
                orders = [order for order in orders if customer_name_value in order.customer_name]

            if not orders:
                scope = _scope_text(region_name_value, rep_name_value)
                return tool_call_finished(
                    tool_name,
                    started_at,
                    tool_empty_data(f"在 {start_date} 至 {end_date} 期间，{scope}暂无订单数据。"),
                )

            limited = orders[:limit]
            return tool_call_finished(tool_name, started_at, _format_orders(limited, len(orders), start, end, region_name_value))
        except Exception as exc:
            if isinstance(exc, ValueError):
                return tool_call_finished(tool_name, started_at, date_error_message(exc))
            return tool_call_finished(tool_name, started_at, tool_execution_error())

    return query_sales_orders


async def _resolve_region_id(service: SalesQueryService, session: AsyncSession, region_name: str | None) -> int | None:
    if region_name is None:
        return None
    return await service.get_region_id_by_name(session, region_name)


async def _resolve_rep_id(service: SalesQueryService, session: AsyncSession, rep_name: str | None) -> int | None:
    if rep_name is None:
        return None
    return await service.get_rep_id_by_name(session, rep_name)


def _scope_text(region_name: str | None, rep_name: str | None) -> str:
    parts = [part for part in [region_name, rep_name] if part]
    return " ".join(parts) + " " if parts else ""


def _format_orders(orders, total: int, start: date, end: date, region_name: str | None) -> str:
    title_scope = f"，{region_name}" if region_name else ""
    lines = [
        f"订单查询结果（{start} 至 {end}{title_scope}）：",
        f"共找到 {total} 条订单" + (f"，以下显示前 {len(orders)} 条" if len(orders) < total else ""),
        "",
    ]

    completed_total = Decimal("0")
    completed_count = 0
    for order in orders:
        if order.status == "COMPLETED":
            completed_total += order.amount
            completed_count += 1
        lines.append(
            f"- 订单号：{order.order_no} | 日期：{order.order_date} | 销售员：{order.rep_name} | "
            f"客户：{order.customer_name} | 金额：{format_money(order.amount)} | 状态：{translate_status(order.status)}"
        )

    lines.append("")
    lines.append(f"小计：完成订单 {completed_count} 笔，金额合计 {format_money(completed_total)}")
    return "\n".join(lines)
