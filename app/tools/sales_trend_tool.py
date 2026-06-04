from datetime import timedelta

from langchain.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales_query_service import SalesQueryService
from app.tools.formatting import blank_to_none, clamp, date_error_message, format_money, parse_required_range
from app.tools.schemas import SalesTrendInput


def create_sales_trend_tool(session: AsyncSession, service: SalesQueryService, today):
    @tool(args_schema=SalesTrendInput)
    async def analyze_sales_trend(
        trend_type: str,
        current_start: str | None = None,
        current_end: str | None = None,
        previous_start: str | None = None,
        previous_end: str | None = None,
        region_name: str | None = None,
        months: int = 6,
    ) -> str:
        """分析销售趋势，计算环比、同比和月度趋势。适用于增长率、同比去年、环比上期、近几个月走势等问题。"""
        try:
            region_id, region_label = await _resolve_region(service, session, blank_to_none(region_name))
            if trend_type == "mom":
                return await _month_over_month(
                    service,
                    session,
                    current_start,
                    current_end,
                    previous_start,
                    previous_end,
                    region_id,
                    region_label,
                )
            if trend_type == "yoy":
                return await _year_over_year(service, session, current_start, current_end, region_id, region_label)
            if trend_type == "monthly":
                return await _monthly_trend(service, session, region_id, region_label, months, today)
            return "未知趋势类型，请使用 mom、yoy 或 monthly"
        except Exception as exc:
            if isinstance(exc, ValueError):
                return date_error_message(exc)
            return "获取趋势数据时出现问题，请稍后重试"

    return analyze_sales_trend


async def _resolve_region(service: SalesQueryService, session: AsyncSession, region_name: str | None):
    if not region_name:
        return None, "全公司"
    region_id = await service.get_region_id_by_name(session, region_name)
    if region_id is None:
        raise RuntimeError(f"未找到大区：{region_name}")
    return region_id, region_name


async def _month_over_month(
    service: SalesQueryService,
    session: AsyncSession,
    current_start,
    current_end,
    previous_start,
    previous_end,
    region_id,
    region_label: str,
) -> str:
    current_start_date, current_end_date = parse_required_range(current_start, current_end)
    if previous_start and previous_end:
        previous_start_date, previous_end_date = parse_required_range(previous_start, previous_end)
    else:
        days = (current_end_date - current_start_date).days + 1
        previous_end_date = current_start_date - timedelta(days=1)
        previous_start_date = previous_end_date - timedelta(days=days - 1)

    current = await service.query_total_amount(session, region_id, current_start_date, current_end_date)
    previous = await service.query_total_amount(session, region_id, previous_start_date, previous_end_date)
    rate = service.calc_growth_rate(current, previous)
    lines = [
        f"环比分析（{region_label}）：",
        "",
        f"当前周期（{current_start_date} 至 {current_end_date}）：{format_money(current)}",
        f"对比周期（{previous_start_date} 至 {previous_end_date}）：{format_money(previous)}",
    ]
    if rate is None:
        lines.append("对比周期无数据，无法计算增长率")
    else:
        trend = "增长" if rate >= 0 else "下降"
        lines.append(f"环比变化：{trend} {abs(rate):.2f}%（差额 {format_money(abs(current - previous))}）")
    return "\n".join(lines)


async def _year_over_year(service: SalesQueryService, session: AsyncSession, current_start, current_end, region_id, region_label):
    start, end = parse_required_range(current_start, current_end)
    previous_start = start.replace(year=start.year - 1)
    previous_end = end.replace(year=end.year - 1)
    current = await service.query_total_amount(session, region_id, start, end)
    previous = await service.query_total_amount(session, region_id, previous_start, previous_end)
    rate = service.calc_growth_rate(current, previous)
    lines = [
        f"同比分析（{region_label}）：",
        "",
        f"今年（{start} 至 {end}）：{format_money(current)}",
        f"去年（{previous_start} 至 {previous_end}）：{format_money(previous)}",
    ]
    if rate is None:
        lines.append("去年同期无数据，无法计算同比增长率")
    else:
        trend = "同比增长" if rate >= 0 else "同比下降"
        lines.append(f"同比变化：{trend} {abs(rate):.2f}%")
    return "\n".join(lines)


async def _monthly_trend(service: SalesQueryService, session: AsyncSession, region_id, region_label: str, months: int, today):
    month_count = clamp(months, 1, 24)
    trend = await service.query_monthly_trend(session, region_id, month_count, today=today)
    if not trend:
        return "暂无趋势数据"
    lines = [f"月度销售趋势（近 {month_count} 个月，{region_label}）：", ""]
    previous = None
    for item in trend:
        suffix = ""
        if previous is not None:
            rate = service.calc_growth_rate(item.total_amount, previous)
            if rate is not None:
                suffix = f" ({'↑' if rate >= 0 else '↓'}{abs(rate):.2f}%)"
        lines.append(f"{item.month}：{format_money(item.total_amount)} 订单数：{item.order_count}{suffix}")
        previous = item.total_amount
    return "\n".join(lines)
