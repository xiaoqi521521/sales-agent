from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest
from pydantic import ValidationError

from app.agent.runtime import SalesAgentRuntime
from app.models.base import Base
from app.tools.schemas import SalesQueryInput


class ValidationFailingAgent:
    async def ainvoke(self, payload, config=None):
        raise _validation_error()


def _validation_error() -> ValidationError:
    try:
        SalesQueryInput(
            start_date="2026-01-01",
            end_date="2026-01-31",
            region_name="'; DROP TABLE sales_order; --",
            limit=10,
        )
    except ValidationError as exc:
        return exc
    raise AssertionError("expected validation error")


@pytest.mark.asyncio
async def test_runtime_converts_tool_parameter_validation_error_to_readable_reply():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        runtime = SalesAgentRuntime(
            session=session,
            model=object(),
            agent_factory=lambda **kwargs: ValidationFailingAgent(),
        )

        result = await runtime.chat_with_trace(session_id="validation-session-001", message="查询恶意大区")

    await engine.dispose()

    assert result.reply.startswith("TOOL_INVALID_ARGUMENT")
    assert "工具参数不合法" in result.reply
    assert "日期格式" in result.reply
    assert result.tool_calls == []


@pytest.mark.asyncio
async def test_stream_runtime_converts_tool_parameter_validation_error_to_error_event():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        runtime = SalesAgentRuntime(
            session=session,
            model=object(),
            agent_factory=lambda **kwargs: ValidationFailingAgent(),
        )

        events = [
            event
            async for event in runtime.stream_chat(session_id="validation-stream-001", message="查询恶意大区")
        ]

    await engine.dispose()

    assert len(events) == 1
    assert events[0].event == "error"
    assert events[0].data["message"].startswith("TOOL_INVALID_ARGUMENT")
    assert "工具参数不合法" in events[0].data["message"]
