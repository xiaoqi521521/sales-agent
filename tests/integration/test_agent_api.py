from httpx import ASGITransport, AsyncClient
import pytest

from app.agent.runtime import AgentRunResult, ToolCallTrace
from app.api.dependencies import get_sales_agent_runtime
from app.main import app


class FakeRuntime:
    async def chat_with_trace(self, *, session_id: str, message: str) -> AgentRunResult:
        return AgentRunResult(
            reply=f"{session_id}:{message}",
            tool_calls=[
                ToolCallTrace(
                    name="calculate_sales_summary",
                    summary="销售额汇总：¥94,979",
                )
            ],
        )


@pytest.mark.asyncio
async def test_agent_chat_endpoint_returns_reference_response_shape():
    app.dependency_overrides[get_sales_agent_runtime] = lambda: FakeRuntime()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/agent/chat",
            json={"sessionId": "api-session-001", "message": "你好"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == "api-session-001"
    assert body["reply"] == "api-session-001:你好"
    assert isinstance(body["durationMs"], int)
    assert body["toolCalls"] == [
        {
            "name": "calculate_sales_summary",
            "summary": "销售额汇总：¥94,979",
        }
    ]
    assert body["dataReferences"] == []


@pytest.mark.asyncio
async def test_agent_chat_endpoint_validates_request_body():
    app.dependency_overrides[get_sales_agent_runtime] = lambda: FakeRuntime()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/agent/chat",
            json={"sessionId": "", "message": ""},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 422
