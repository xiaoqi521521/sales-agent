import logging
from datetime import date

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import pytest

from app.agent.runtime import SalesAgentRuntime
from app.models.base import Base


class FakeAIMessage:
    type = "ai"
    content = "完成"
    usage_metadata = {
        "input_tokens": 1000,
        "output_tokens": 500,
        "total_tokens": 1500,
        "input_token_details": {"cache_read": 200},
    }


class FakeAgent:
    async def ainvoke(self, payload, config=None):
        return {"messages": [FakeAIMessage()]}


class FakeNoUsageAIMessage:
    type = "ai"
    content = "完成"


class FakeNoUsageAgent:
    async def ainvoke(self, payload, config=None):
        return {"messages": [FakeNoUsageAIMessage()]}


def fake_agent_factory(**kwargs):
    return FakeAgent()


def fake_no_usage_agent_factory(**kwargs):
    return FakeNoUsageAgent()


@pytest.fixture(autouse=True)
def fake_configured_model(monkeypatch):
    class FakeSummarizationMiddleware:
        def __init__(self, *, model, trigger, keep):
            self.model = model
            self.trigger = trigger
            self.keep = keep

    monkeypatch.setattr("app.agent.runtime.SummarizationMiddleware", FakeSummarizationMiddleware)
    monkeypatch.setattr("app.agent.runtime.create_default_chat_model", lambda: object())
    monkeypatch.setattr("app.agent.runtime.create_summary_chat_model", lambda: object())


@pytest.mark.asyncio
async def test_agent_runtime_logs_token_usage_from_ai_message_metadata(caplog):
    caplog.set_level(logging.INFO)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        runtime = SalesAgentRuntime(
            session=session,
            today=date(2026, 2, 15),
            agent_factory=fake_agent_factory,
        )

        result = await runtime.chat_with_trace(session_id="token-session-001", message="查一下销售额")

    await engine.dispose()

    assert result.reply == "完成"
    assert "event=token_usage" in caplog.text
    assert "sessionId=token-session-001" in caplog.text
    assert "inputTokens=1000" in caplog.text
    assert "cachedInputTokens=200" in caplog.text
    assert "outputTokens=500" in caplog.text
    assert "totalTokens=1500" in caplog.text


@pytest.mark.asyncio
async def test_stream_fallback_logs_token_usage_unavailable(caplog):
    caplog.set_level(logging.INFO)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        runtime = SalesAgentRuntime(
            session=session,
            today=date(2026, 2, 15),
            agent_factory=fake_no_usage_agent_factory,
        )

        events = [
            event
            async for event in runtime.stream_chat(
                session_id="stream-token-session-001",
                message="流式查询",
            )
        ]

    await engine.dispose()

    assert events[-1].event == "done"
    assert "event=token_usage_unavailable" in caplog.text
    assert "sessionId=stream-token-session-001" in caplog.text
