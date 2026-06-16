from datetime import date

from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales_query_service import SalesQueryService
from app.tools.anomaly_detection_tool import create_anomaly_detection_tool
from app.tools.chart_generator_tool import create_chart_generator_tool
from app.tools.sales_query_tool import create_sales_query_tool
from app.tools.sales_summary_tool import create_sales_summary_tool
from app.tools.sales_trend_tool import create_sales_trend_tool


def create_sales_tools(
    *,
    session: AsyncSession,
    service: SalesQueryService | None = None,
    today: date | None = None,
) -> list[BaseTool]:
    query_service = service or SalesQueryService()
    current_date = today or date.today()
    return [
        create_sales_query_tool(session, query_service),
        create_sales_summary_tool(session, query_service),
        create_sales_trend_tool(session, query_service, current_date),
        create_chart_generator_tool(session, query_service, current_date),
        create_anomaly_detection_tool(session, query_service, current_date),
    ]
