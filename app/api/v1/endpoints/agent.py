from time import perf_counter

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.runtime import SalesAgentRuntime
from app.agent.streaming import AgentStreamEvent, format_sse_event
from app.api.dependencies import get_sales_agent_runtime
from app.schemas.agent import AgentChatRequest, AgentChatResponse, AgentToolCallSummary


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    request: AgentChatRequest,
    runtime: SalesAgentRuntime = Depends(get_sales_agent_runtime),
) -> AgentChatResponse:
    started_at = perf_counter()
    result = await runtime.chat_with_trace(session_id=request.session_id, message=request.message)
    duration_ms = int((perf_counter() - started_at) * 1000)
    return AgentChatResponse(
        session_id=request.session_id,
        reply=result.reply,
        duration_ms=duration_ms,
        tool_calls=[
            AgentToolCallSummary(name=tool_call.name, summary=tool_call.summary)
            for tool_call in result.tool_calls
        ],
        data_references=result.data_references,
    )


@router.post("/chat/stream")
async def chat_stream(
    request: AgentChatRequest,
    runtime: SalesAgentRuntime = Depends(get_sales_agent_runtime),
) -> StreamingResponse:
    async def event_generator():
        try:
            async for event in runtime.stream_chat(session_id=request.session_id, message=request.message):
                yield format_sse_event(event)
        except Exception:
            yield format_sse_event(
                AgentStreamEvent(
                    event="error",
                    data={"message": "服务暂时不可用，请稍后重试"},
                )
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
