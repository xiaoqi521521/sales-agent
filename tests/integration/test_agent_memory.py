from datetime import date

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.runtime import SalesAgentRuntime
from app.models import Base
from app.repositories.chat_memory_repository import ChatMemoryRepository


class FakeCompiledAgent:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, payload, config):
        self.calls.append({"payload": payload, "config": config})
        thread_id = config["configurable"]["thread_id"]
        message_count = len(payload["messages"])
        return {"messages": [AIMessage(content=f"{thread_id}:{message_count}")]}


class FakeToolResultAgent:
    async def ainvoke(self, payload, config):
        return {
            "messages": [
                ToolMessage(content="销售额汇总：¥94,979", tool_call_id="call-1", name="calculate_sales_summary"),
                AIMessage(content="华东区上个月销售额为 ¥94,979。"),
            ]
        }


@pytest.mark.asyncio
async def test_agent_runtime_persists_history_and_uses_thread_id():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fake_agent = FakeCompiledAgent()

    async with session_factory() as session:
        runtime = SalesAgentRuntime(
            session=session,
            model=object(),
            today=date(2026, 2, 15),
            agent_factory=lambda **kwargs: fake_agent,
        )

        first_answer = await runtime.chat(session_id="session-a", message="上个月华东区销售额是多少？")
        second_answer = await runtime.chat(session_id="session-a", message="按产品品类拆分一下")
        other_answer = await runtime.chat(session_id="session-b", message="本季度 Top 3 销售员是谁？")

        assert first_answer == "session-a:1"
        assert second_answer == "session-a:3"
        assert other_answer == "session-b:1"
        assert fake_agent.calls[0]["config"]["configurable"]["thread_id"] == "session-a"
        assert fake_agent.calls[0]["config"]["recursion_limit"] == 10
        assert len(fake_agent.calls[1]["payload"]["messages"]) == 3
        assert fake_agent.calls[1]["payload"]["messages"][0]["role"] == "user"
        assert fake_agent.calls[1]["payload"]["messages"][1]["role"] == "assistant"

        memory = await ChatMemoryRepository().find_by_session_id(session, "session-a")
        assert memory is not None
        assert "按产品品类拆分一下" in memory.messages
        assert "session-a:3" in memory.messages

    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_runtime_binds_five_sales_tools_and_system_prompt():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    captured = {}

    def capture_agent(**kwargs):
        captured.update(kwargs)
        return FakeCompiledAgent()

    async with session_factory() as session:
        runtime = SalesAgentRuntime(
            session=session,
            model=object(),
            today=date(2026, 2, 15),
            agent_factory=capture_agent,
        )

        await runtime.chat(session_id="session-tools", message="你好")

        assert [tool.name for tool in captured["tools"]] == [
            "query_sales_orders",
            "calculate_sales_summary",
            "analyze_sales_trend",
            "generate_sales_chart",
            "detect_sales_anomalies",
        ]
        assert "今天是 2026-02-15" in captured["system_prompt"]
        assert "checkpointer" not in captured

    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_runtime_persists_key_tool_results():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        runtime = SalesAgentRuntime(
            session=session,
            model=object(),
            today=date(2026, 2, 15),
            agent_factory=lambda **kwargs: FakeToolResultAgent(),
        )

        await runtime.chat(session_id="session-tool-result", message="上个月华东区销售额是多少？")

        memory = await ChatMemoryRepository().find_by_session_id(session, "session-tool-result")
        assert memory is not None
        assert "calculate_sales_summary" in memory.messages
        assert "销售额汇总：¥94,979" in memory.messages

    await engine.dispose()
