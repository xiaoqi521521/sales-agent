import logging
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest

from app.models.base import Base
from app.models.sales_region import SalesRegion
from app.tools.registry import create_sales_tools


@pytest.mark.asyncio
async def test_tool_invocation_logs_started_and_failed_events(caplog):
    caplog.set_level(logging.INFO)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(SalesRegion(id=1, name="华东区"))
        await session.commit()
        tools = {tool.name: tool for tool in create_sales_tools(session=session, today=date(2026, 2, 15))}

        result = await tools["query_sales_orders"].ainvoke(
            {
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "region_name": "华东区",
                "rep_name": "",
                "limit": 10,
            }
        )

    await engine.dispose()

    assert result.startswith("TOOL_EMPTY_DATA")
    assert "event=tool_call_started" in caplog.text
    assert "event=tool_call_failed" in caplog.text
    assert "toolName=query_sales_orders" in caplog.text
    assert "errorCode=TOOL_EMPTY_DATA" in caplog.text
    assert "resultLength=" in caplog.text
