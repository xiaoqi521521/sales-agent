from datetime import date, timedelta

from langchain.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.product_repository import ProductRepository
from app.schemas.sales import AnomalyDTO
from app.services.sales_query_service import SalesQueryService
from app.tools.formatting import format_money, tool_execution_error


def create_anomaly_detection_tool(
    session: AsyncSession,
    service: SalesQueryService,
    today: date,
    zero_sale_threshold_days: int = 5,
    trend_drop_threshold: float = 0.3,
):
    @tool
    async def detect_sales_anomalies() -> str:
        """自动检测销售数据异常，包括大区订单量骤降、产品连续零销售、销售员退单率异常、销售员业绩骤降。适用于预警、风险排查、有没有异常等问题。"""
        try:
            anomalies: list[AnomalyDTO] = []
            anomalies.extend(await _detect_region_drop(session, service, today, trend_drop_threshold))
            anomalies.extend(await _detect_zero_sale_products(session, service, today, zero_sale_threshold_days))
            anomalies.extend(await _detect_high_refund_reps(session, service, today))
            anomalies.extend(await _detect_rep_performance_drop(session, service, today))
            if not anomalies:
                return "当前数据未检测到明显异常，销售数据运行正常。"
            anomalies.sort(key=lambda item: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(item.severity, 3))
            return _format_anomalies(anomalies)
        except Exception:
            return tool_execution_error()

    return detect_sales_anomalies


async def _detect_region_drop(session: AsyncSession, service: SalesQueryService, today: date, threshold: float):
    recent_start = today - timedelta(days=14)
    recent_end = today
    base_start = today - timedelta(days=42)
    base_end = today - timedelta(days=15)

    anomalies = []
    for region in await service.visible_regions(session):
        recent_count = await service.query_order_count(session, region.id, recent_start, recent_end)
        base_count = await service.query_order_count(session, region.id, base_start, base_end)
        base_avg = base_count / 2
        if base_avg < 2:
            continue
        drop_rate = (base_avg - recent_count) / base_avg
        if drop_rate > threshold:
            anomalies.append(
                AnomalyDTO(
                    type="大区订单量骤降",
                    severity="HIGH" if drop_rate > 0.6 else "MEDIUM",
                    subject=region.name,
                    description=f"近 2 周订单量 {recent_count} 笔，过去 4 周均值 {base_avg:.1f} 笔/两周，下降 {drop_rate * 100:.0f}%",
                    suggestion="建议联系大区负责人确认原因，检查是否有系统问题或市场变化",
                )
            )
    return anomalies


async def _detect_zero_sale_products(
    session: AsyncSession,
    service: SalesQueryService,
    today: date,
    threshold_days: int,
):
    if service.current_user and service.current_user.is_sales_rep:
        return []
    product_repository = ProductRepository()
    anomalies = []
    for product in await product_repository.find_by_status(session, "ACTIVE"):
        last_order_date = await service.query_last_order_date(session, product.id)
        if last_order_date is None:
            continue
        days_without_sale = (today - last_order_date).days
        if days_without_sale >= threshold_days:
            anomalies.append(
                AnomalyDTO(
                    type="产品连续零销售",
                    severity="HIGH" if days_without_sale >= 14 else "MEDIUM" if days_without_sale >= 7 else "LOW",
                    subject=f"{product.name}（{product.sku_code}）",
                    description=f"已连续 {days_without_sale} 天无销售订单，上次出单日期：{last_order_date}",
                    suggestion="检查产品是否下架、库存是否充足、价格是否有竞争力",
                )
            )
    return anomalies


async def _detect_high_refund_reps(session: AsyncSession, service: SalesQueryService, today: date):
    start = today - timedelta(days=30)
    rows = await service.query_refund_rates(session, start, today)
    anomalies = []
    for rep_id, refunded, total in rows:
        if total < 3:
            continue
        refund_rate = refunded / total
        if refund_rate > 0.15:
            rep_name = await service.get_rep_name(session, rep_id)
            anomalies.append(
                AnomalyDTO(
                    type="销售员退单率异常",
                    severity="HIGH" if refund_rate > 0.3 else "MEDIUM",
                    subject=rep_name,
                    description=f"近 30 天退单率 {refund_rate * 100:.0f}%（{refunded}/{total} 单），明显高于团队平均水平",
                    suggestion="建议与该销售员沟通了解原因，排查是否存在虚报订单或客户不满意的情况",
                )
            )
    return anomalies


async def _detect_rep_performance_drop(session: AsyncSession, service: SalesQueryService, today: date):
    current_start = today - timedelta(days=30)
    previous_start = today - timedelta(days=60)
    previous_end = today - timedelta(days=31)
    anomalies = []
    for rep in await service.visible_sales_reps(session):
        current = await service.order_repository.sum_amount_by_rep(session, rep.id, current_start, today)
        previous = await service.order_repository.sum_amount_by_rep(session, rep.id, previous_start, previous_end)
        if previous <= 0:
            continue
        drop_rate = (previous - current) / previous
        if drop_rate > 0.4:
            anomalies.append(
                AnomalyDTO(
                    type="销售员业绩骤降",
                    severity="HIGH" if drop_rate > 0.7 else "MEDIUM",
                    subject=rep.name,
                    description=f"近 30 天销售额 {format_money(current)}，上一周期 {format_money(previous)}，下降 {drop_rate * 100:.0f}%",
                    suggestion="建议主管复盘该销售员客户跟进情况，确认是否存在重点客户流失",
                )
            )
    return anomalies


def _format_anomalies(anomalies: list[AnomalyDTO]) -> str:
    lines = [f"异常检测结果：共发现 {len(anomalies)} 个异常", ""]
    severity_text = {"HIGH": "高优先级", "MEDIUM": "中优先级", "LOW": "低优先级"}
    for anomaly in anomalies:
        lines.append(f"{severity_text.get(anomaly.severity, anomaly.severity)}｜{anomaly.type}")
        lines.append(f"  对象：{anomaly.subject}")
        lines.append(f"  描述：{anomaly.description}")
        lines.append(f"  建议：{anomaly.suggestion}")
        lines.append("")
    return "\n".join(lines).rstrip()
