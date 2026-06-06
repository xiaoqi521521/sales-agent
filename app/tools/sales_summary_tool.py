from decimal import Decimal

from langchain.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales_query_service import SalesQueryService
from app.tools.formatting import (
    blank_to_none,
    clamp,
    date_error_message,
    format_money,
    parse_required_range,
    tool_empty_data,
    tool_execution_error,
    tool_invalid_argument,
    tool_unknown_entity,
)
from app.tools.schemas import SalesSummaryInput


def create_sales_summary_tool(session: AsyncSession, service: SalesQueryService):
    @tool(args_schema=SalesSummaryInput)
    async def calculate_sales_summary(
        summary_type: str,
        start_date: str,
        end_date: str,
        region_name: str | None = None,
        top_n: int = 5,
    ) -> str:
        """计算销售汇总统计，包括总销售额、销售员排名、大区排名、产品排名、Top N 分析。不适用于查询具体订单详情。"""
        try:
            start, end = parse_required_range(start_date, end_date)
            region_name_value = blank_to_none(region_name)
            if summary_type == "total":
                return await _sales_total(service, session, start, end, region_name_value)
            if summary_type == "rep_ranking":
                return await _rep_ranking(service, session, start, end, region_name_value, top_n)
            if summary_type == "region_ranking":
                return await _region_ranking(service, session, start, end)
            if summary_type == "product_ranking":
                return await _product_ranking(service, session, start, end, top_n)
            return tool_invalid_argument("未知汇总类型，请使用 total、rep_ranking、region_ranking 或 product_ranking。")
        except Exception as exc:
            if isinstance(exc, ValueError):
                return date_error_message(exc)
            return tool_execution_error()

    return calculate_sales_summary


async def _sales_total(service: SalesQueryService, session: AsyncSession, start, end, region_name: str | None) -> str:
    region_id = None
    if region_name:
        region_id = await service.get_region_id_by_name(session, region_name)
        if region_id is None:
            return tool_unknown_entity("大区", region_name)
    total = await service.query_total_amount(session, region_id=region_id, start=start, end=end)
    scope = region_name if region_name else "全公司"
    return f"销售额汇总（{start} 至 {end}，{scope}）：\n总销售额：{format_money(total)}"


async def _rep_ranking(
    service: SalesQueryService,
    session: AsyncSession,
    start,
    end,
    region_name: str | None,
    top_n: int,
) -> str:
    n = clamp(top_n, 1, 20)
    if service.current_user and service.current_user.is_sales_rep:
        return (
            "NO_PERMISSION_REP_RANKING\n"
            "当前账号只能查看本人销售数据，不能查看团队销售员排行。"
            "你可以查询“我的销售额”“我的产品销售排行”或“我的销售趋势”。"
        )
    reps = await service.query_rep_ranking(session, start, end, n if not region_name else 100)
    if region_name:
        reps = [rep for rep in reps if rep.region_name == region_name][:n]
    if not reps:
        return tool_empty_data(f"在 {start} 至 {end} 期间，暂无销售员排名数据。")

    scope = region_name if region_name else "全公司"
    lines = [f"销售员业绩排名（{start} 至 {end}，{scope}）：", ""]
    for index, rep in enumerate(reps[:n], start=1):
        lines.append(f"第 {index} 名：{rep.rep_name}（{rep.region_name}） 销售额：{format_money(rep.total_amount)}")
    return "\n".join(lines)


async def _region_ranking(service: SalesQueryService, session: AsyncSession, start, end) -> str:
    if service.current_user and service.current_user.is_sales_rep:
        return (
            "NO_PERMISSION_REGION_RANKING\n"
            "当前账号无权查看大区排行。该数据需要销售主管或销售总监权限。"
            "你可以查询“我的销售额”“我的产品销售排行”或“我的销售趋势”。"
        )
    regions = await service.query_region_ranking(session, start, end)
    if not regions:
        return tool_empty_data(f"在 {start} 至 {end} 期间，暂无大区销售数据。")
    grand_total = sum((region.total_amount for region in regions), Decimal("0"))
    lines = [f"大区业绩排名（{start} 至 {end}）：", ""]
    for index, region in enumerate(regions, start=1):
        ratio = region.total_amount / grand_total * Decimal("100") if grand_total else Decimal("0")
        lines.append(
            f"第 {index} 名：{region.region_name} 销售额：{format_money(region.total_amount)} 占比：{ratio:.1f}%"
        )
    lines.append("")
    lines.append(f"全公司合计：{format_money(grand_total)}")
    return "\n".join(lines)


async def _product_ranking(service: SalesQueryService, session: AsyncSession, start, end, top_n: int) -> str:
    is_worst = top_n < 0
    n = clamp(abs(top_n), 1, 20)
    products = await service.query_product_ranking(session, start, end, 100 if is_worst else n)
    if is_worst:
        products = list(reversed(products[-n:]))
    else:
        products = products[:n]
    if not products:
        return tool_empty_data(f"在 {start} 至 {end} 期间，暂无产品销售数据。")

    prefix = "PERSONAL_PRODUCT_RANKING\n" if service.current_user and service.current_user.is_sales_rep else ""
    lines = [f"{prefix}产品销售排名{'（最差）' if is_worst else '（最佳）'}（{start} 至 {end}）：", ""]
    for index, product in enumerate(products, start=1):
        lines.append(
            f"第 {index} 名：{product.product_name} [{product.sku_code}] 品类：{product.category} "
            f"销售额：{format_money(product.total_amount)} 数量：{product.total_quantity} 件"
        )
    return "\n".join(lines)
