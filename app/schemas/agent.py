from pydantic import BaseModel, ConfigDict, Field


class AgentChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100, alias="sessionId")
    message: str = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class AgentChatResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    answer: str

    model_config = ConfigDict(populate_by_name=True)
