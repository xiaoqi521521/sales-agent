from datetime import date
from inspect import signature
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.runtime import SalesAgentRuntime
from app.models import Base


def test_agent_runtime_constructor_does_not_accept_model_override():
    assert "model" not in signature(SalesAgentRuntime).parameters


class FakeCompiledAgent:
    async def ainvoke(self, payload, config):
        return {"messages": []}


@pytest.mark.asyncio
async def test_agent_runtime_configures_summarization_middleware(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    captured_middleware = {}

    class FakeSummarizationMiddleware:
        def __init__(self, *, model, trigger, keep):
            captured_middleware["model"] = model
            captured_middleware["trigger"] = trigger
            captured_middleware["keep"] = keep

    monkeypatch.setattr("app.agent.runtime.SummarizationMiddleware", FakeSummarizationMiddleware, raising=False)
    monkeypatch.setattr("app.agent.runtime.create_default_chat_model", lambda: object())
    monkeypatch.setattr("app.agent.runtime.create_summary_chat_model", lambda: "deepseek-v4-flash")
    monkeypatch.setattr(
        "app.agent.runtime.get_settings",
        lambda: SimpleNamespace(
            openai_api_key="",
            agent_summary_model="deepseek-v4-flash",
            agent_summary_trigger_messages=20,
            agent_summary_keep_messages=6,
        ),
    )

    captured_agent_kwargs = {}

    def capture_agent(**kwargs):
        captured_agent_kwargs.update(kwargs)
        return FakeCompiledAgent()

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        SalesAgentRuntime(
            session=session,
            today=date(2026, 2, 15),
            agent_factory=capture_agent,
        )

    await engine.dispose()

    assert captured_middleware == {
        "model": "deepseek-v4-flash",
        "trigger": ("messages", 20),
        "keep": ("messages", 6),
    }
    assert captured_agent_kwargs["middleware"]
    assert isinstance(captured_agent_kwargs["middleware"][0], FakeSummarizationMiddleware)
