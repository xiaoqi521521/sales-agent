from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
import pytest

from app.agent.streaming import AgentStreamEvent
from app.api.dependencies import get_sales_agent_runtime
from app.main import app


class FakeStreamingRuntime:
    async def stream_chat(self, *, session_id: str, message: str) -> AsyncIterator[AgentStreamEvent]:
        yield AgentStreamEvent(event="token", data={"content": "你好"})
        yield AgentStreamEvent(
            event="tool",
            data={"name": "query_sales_orders", "summary": "查询订单完成"},
        )
        yield AgentStreamEvent(
            event="done",
            data={
                "reply": f"{session_id}:{message}",
                "durationMs": 12,
                "toolCalls": [{"name": "query_sales_orders", "summary": "查询订单完成"}],
                "dataReferences": [],
            },
        )


class FailingStreamingRuntime:
    async def stream_chat(self, *, session_id: str, message: str) -> AsyncIterator[AgentStreamEvent]:
        raise RuntimeError("model unavailable")
        yield


@pytest.mark.asyncio
async def test_agent_stream_endpoint_returns_sse_events():
    app.dependency_overrides[get_sales_agent_runtime] = lambda: FakeStreamingRuntime()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={"sessionId": "stream-session-001", "message": "近6个月趋势"},
            headers={"accept": "text/event-stream"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: token" in body
    assert 'data: {"content":"你好"}' in body
    assert "event: tool" in body
    assert "event: done" in body
    assert '"reply":"stream-session-001:近6个月趋势"' in body


@pytest.mark.asyncio
async def test_agent_stream_endpoint_returns_uniform_error_event():
    app.dependency_overrides[get_sales_agent_runtime] = lambda: FailingStreamingRuntime()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent/chat/stream",
            json={"sessionId": "stream-session-err", "message": "会失败"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "event: error" in response.text
    assert 'data: {"message":"服务暂时不可用，请稍后重试"}' in response.text
