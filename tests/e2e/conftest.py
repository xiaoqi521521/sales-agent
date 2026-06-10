from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, ToolMessage
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.agent.runtime import SalesAgentRuntime
from app.api.dependencies import get_current_user, get_db_session, get_sales_agent_runtime
from app.core.auth_context import CurrentUser
from app.main import app
from app.models.base import Base
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.models.sales_region import SalesRegion
from app.models.sales_rep import SalesRep


EAST_REGION = "华东区"


class FakeSummarizationMiddleware:
    def __init__(self, *, model: Any, trigger: tuple[str, int], keep: tuple[str, int]) -> None:
        self.model = model
        self.trigger = trigger
        self.keep = keep


class ScenarioAgent:
    def __init__(self, tools: list[Any]) -> None:
        self.tools = {tool.name: tool for tool in tools}

    async def ainvoke(self, payload: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, list[Any]]:
        messages = payload["messages"]
        user_message = messages[-1]["content"]
        history_text = "\n".join(_message_content(message) for message in messages[:-1])
        tool_messages: list[ToolMessage] = []

        async def call_tool(name: str, args: dict[str, Any]) -> str:
            content = await self.tools[name].ainvoke(args)
            tool_messages.append(
                ToolMessage(
                    content=content,
                    name=name,
                    tool_call_id=f"call-{len(tool_messages) + 1}",
                )
            )
            return content

        if _mentions(user_message, "图表", "chart"):
            chart_text = await call_tool(
                "generate_sales_chart",
                {
                    "chart_type": "pie",
                    "dimension": "region",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "months": 3,
                    "region_name": "",
                    "title": "Region Share",
                },
            )
            return _agent_result(tool_messages, f"已生成区域销售占比图表。{chart_text}")

        if _mentions(user_message, "异常", "预警", "anomaly"):
            anomaly_text = await call_tool("detect_sales_anomalies", {})
            return _agent_result(tool_messages, f"异常预警分析完成。{anomaly_text}")

        if _mentions(user_message, "环比", "排行", "综合", "multi"):
            total_text = await call_tool(
                "calculate_sales_summary",
                {
                    "summary_type": "total",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": EAST_REGION,
                    "top_n": 5,
                },
            )
            trend_text = await call_tool(
                "analyze_sales_trend",
                {
                    "trend_type": "mom",
                    "current_start": "2026-01-01",
                    "current_end": "2026-01-31",
                    "previous_start": "2025-12-01",
                    "previous_end": "2025-12-31",
                    "region_name": EAST_REGION,
                    "months": 2,
                },
            )
            ranking_text = await call_tool(
                "calculate_sales_summary",
                {
                    "summary_type": "rep_ranking",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": EAST_REGION,
                    "top_n": 3,
                },
            )
            return _agent_result(
                tool_messages,
                f"综合分析完成，覆盖销售额、环比趋势和销售员排行。\n{total_text}\n{trend_text}\n{ranking_text}",
            )

        if _mentions(user_message, "第一名", "follow"):
            if "Wang Fang" not in history_text:
                return _agent_result([], "缺少上下文，无法判断上一轮提到的第一名销售员。")
            orders_text = await call_tool(
                "query_sales_orders",
                {
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": EAST_REGION,
                    "rep_name": "Wang Fang",
                    "customer_name": "",
                    "limit": 10,
                },
            )
            return _agent_result(tool_messages, f"第一名销售员 Wang Fang 的订单明细如下。\n{orders_text}")

        if _mentions(user_message, "所有订单", "all orders"):
            orders_text = await call_tool(
                "query_sales_orders",
                {
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "region_name": "",
                    "rep_name": "",
                    "customer_name": "",
                    "limit": 20,
                },
            )
            return _agent_result(tool_messages, orders_text)

        ranking_text = await call_tool(
            "calculate_sales_summary",
            {
                "summary_type": "rep_ranking",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "region_name": EAST_REGION,
                "top_n": 3,
            },
        )
        return _agent_result(tool_messages, f"华东区 2026 年 1 月销售员第一名是 Wang Fang。\n{ranking_text}")


def scenario_agent_factory(**kwargs: Any) -> ScenarioAgent:
    return ScenarioAgent(kwargs["tools"])


@pytest_asyncio.fixture
async def e2e_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add_all(_sample_rows())
        await session.commit()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_sales_agent_runtime(
        session: AsyncSession = Depends(get_db_session),
        current_user: CurrentUser = Depends(get_current_user),
    ) -> SalesAgentRuntime:
        return SalesAgentRuntime(
            session=session,
            current_user=current_user,
            today=date(2026, 2, 15),
            agent_factory=scenario_agent_factory,
        )

    monkeypatch.setattr("app.agent.runtime.SummarizationMiddleware", FakeSummarizationMiddleware)
    monkeypatch.setattr("app.agent.runtime.create_default_chat_model", lambda: object())
    monkeypatch.setattr("app.agent.runtime.create_summary_chat_model", lambda: object())
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_sales_agent_runtime] = override_sales_agent_runtime

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def auth_headers(client: AsyncClient, rep_id: int) -> dict[str, str]:
    response = await client.post("/auth/login", json={"repId": rep_id})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def _agent_result(tool_messages: list[ToolMessage], answer: str) -> dict[str, list[Any]]:
    return {"messages": [*tool_messages, AIMessage(content=answer)]}


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


def _mentions(text: str, *keywords: str) -> bool:
    lower_text = text.lower()
    return any(keyword.lower() in lower_text for keyword in keywords)


def _sample_rows() -> list[Any]:
    return [
        SalesRegion(id=1, name="华东区"),
        SalesRegion(id=2, name="华北区"),
        SalesRep(id=1, name="East Manager", region_id=1, role="SALES_MANAGER", email="manager@example.com"),
        SalesRep(id=2, name="Zhang Wei", region_id=1, role="SALES_REP", email="zhangwei@example.com"),
        SalesRep(id=3, name="Wang Fang", region_id=1, role="SALES_REP", email="wangfang@example.com"),
        SalesRep(id=4, name="Zhang Lei", region_id=2, role="SALES_REP", email="zhanglei@example.com"),
        SalesRep(id=5, name="Director", region_id=0, role="SALES_DIRECTOR", email="director@example.com"),
        Product(
            id=1,
            sku_code="SKU-1001",
            name="Laptop",
            category="Digital",
            unit_price=Decimal("500.00"),
            cost=Decimal("300.00"),
            status="ACTIVE",
        ),
        Product(
            id=2,
            sku_code="SKU-8821",
            name="Smart Watch Pro",
            category="Digital",
            unit_price=Decimal("200.00"),
            cost=Decimal("120.00"),
            status="ACTIVE",
        ),
        Product(
            id=3,
            sku_code="SKU-3001",
            name="Jacket",
            category="Clothing",
            unit_price=Decimal("300.00"),
            cost=Decimal("180.00"),
            status="ACTIVE",
        ),
        SalesOrder(
            id=1,
            order_no="ORD-001",
            rep_id=2,
            product_id=1,
            region_id=1,
            customer_name="Shanghai Tech",
            quantity=2,
            unit_price=Decimal("500.00"),
            amount=Decimal("1000.00"),
            cost=Decimal("600.00"),
            profit=Decimal("400.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 10),
        ),
        SalesOrder(
            id=2,
            order_no="ORD-002",
            rep_id=3,
            product_id=1,
            region_id=1,
            customer_name="Hangzhou Flagship",
            quantity=3,
            unit_price=Decimal("500.00"),
            amount=Decimal("1500.00"),
            cost=Decimal("900.00"),
            profit=Decimal("600.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 15),
        ),
        SalesOrder(
            id=3,
            order_no="ORD-003",
            rep_id=3,
            product_id=2,
            region_id=1,
            customer_name="Refund Customer A",
            quantity=1,
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            cost=Decimal("120.00"),
            profit=Decimal("80.00"),
            status="REFUNDED",
            order_date=date(2026, 1, 20),
        ),
        SalesOrder(
            id=4,
            order_no="ORD-006",
            rep_id=4,
            product_id=1,
            region_id=2,
            customer_name="North Old A",
            quantity=4,
            unit_price=Decimal("500.00"),
            amount=Decimal("2000.00"),
            cost=Decimal("1200.00"),
            profit=Decimal("800.00"),
            status="COMPLETED",
            order_date=date(2025, 12, 5),
        ),
        SalesOrder(
            id=5,
            order_no="ORD-007",
            rep_id=4,
            product_id=1,
            region_id=2,
            customer_name="North Old B",
            quantity=4,
            unit_price=Decimal("500.00"),
            amount=Decimal("2000.00"),
            cost=Decimal("1200.00"),
            profit=Decimal("800.00"),
            status="COMPLETED",
            order_date=date(2025, 12, 12),
        ),
        SalesOrder(
            id=6,
            order_no="ORD-008",
            rep_id=4,
            product_id=1,
            region_id=2,
            customer_name="North Old C",
            quantity=4,
            unit_price=Decimal("500.00"),
            amount=Decimal("2000.00"),
            cost=Decimal("1200.00"),
            profit=Decimal("800.00"),
            status="COMPLETED",
            order_date=date(2025, 12, 20),
        ),
        SalesOrder(
            id=7,
            order_no="ORD-009",
            rep_id=4,
            product_id=2,
            region_id=2,
            customer_name="Smart Watch Buyer",
            quantity=1,
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            cost=Decimal("120.00"),
            profit=Decimal("80.00"),
            status="COMPLETED",
            order_date=date(2026, 1, 1),
        ),
        SalesOrder(
            id=8,
            order_no="ORD-010",
            rep_id=4,
            product_id=1,
            region_id=2,
            customer_name="North Recent",
            quantity=1,
            unit_price=Decimal("500.00"),
            amount=Decimal("500.00"),
            cost=Decimal("300.00"),
            profit=Decimal("200.00"),
            status="COMPLETED",
            order_date=date(2026, 2, 5),
        ),
    ]
