from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100, alias="sessionId")
    message: str = Field(..., min_length=1, max_length=2000)
    user_context: dict[str, Any] | None = Field(default=None, alias="userContext")

    model_config = ConfigDict(populate_by_name=True)


class AgentToolCallSummary(BaseModel):
    name: str
    summary: str


class AgentChatResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    reply: str
    duration_ms: int = Field(..., alias="durationMs")
    tool_calls: list[AgentToolCallSummary] = Field(default_factory=list, alias="toolCalls")
    data_references: list[str] = Field(default_factory=list, alias="dataReferences")

    model_config = ConfigDict(populate_by_name=True)
