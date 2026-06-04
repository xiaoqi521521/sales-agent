from collections.abc import Callable
from datetime import date
from typing import Any

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory import ChatMemoryService, StoredMessage
from app.agent.prompts import build_system_prompt
from app.core.config import get_settings
from app.tools.registry import create_sales_tools


AgentFactory = Callable[..., Any]


def create_default_chat_model() -> Any:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY 未配置，无法创建默认聊天模型")

    return init_chat_model(
        model=settings.openai_model,
        model_provider="openai",
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
    )


class SalesAgentRuntime:
    def __init__(
        self,
        *,
        session: AsyncSession,
        model: Any | None = None,
        today: date | None = None,
        memory_service: ChatMemoryService | None = None,
        checkpointer: Any | None = None,
        agent_factory: AgentFactory = create_agent,
        recursion_limit: int = 10,
    ) -> None:
        self.session = session
        self.today = today or date.today()
        self.memory_service = memory_service or ChatMemoryService(max_messages=20)
        self.recursion_limit = recursion_limit
        self.tools = create_sales_tools(session=session, today=self.today)
        self.system_prompt = build_system_prompt(self.today)
        agent_kwargs = {
            "model": model or create_default_chat_model(),
            "tools": self.tools,
            "system_prompt": self.system_prompt,
        }
        if checkpointer is not None:
            agent_kwargs["checkpointer"] = checkpointer

        self.agent = agent_factory(
            **agent_kwargs,
        )

    async def chat(self, *, session_id: str, message: str) -> str:
        normalized_session_id = self._validate_session_id(session_id)
        normalized_message = self._validate_message(message)

        history = await self.memory_service.get_context_messages(self.session, normalized_session_id)
        payload = {
            "messages": [
                *[item.as_langchain_message() for item in history],
                {"role": "user", "content": normalized_message},
            ]
        }
        config = {
            "configurable": {"thread_id": normalized_session_id},
            "recursion_limit": self.recursion_limit,
        }

        result = await self.agent.ainvoke(payload, config=config)
        answer = self._extract_answer(result)
        tool_messages = self._extract_tool_messages(result)
        await self.memory_service.append_turn(
            self.session,
            normalized_session_id,
            normalized_message,
            answer,
            tool_messages=tool_messages,
        )
        return answer

    def _validate_session_id(self, session_id: str) -> str:
        """校验并规范化 session_id。

        去除首尾空格后，校验非空且长度不超过 100，不满足则抛出 ValueError。
        """
        value = session_id.strip()
        if not value:
            raise ValueError("session_id 不能为空")
        if len(value) > 100:
            raise ValueError("session_id 长度不能超过 100")
        return value

    def _validate_message(self, message: str) -> str:
        """校验并规范化用户消息。

        去除首尾空格后，校验非空，不满足则抛出 ValueError。
        """
        value = message.strip()
        if not value:
            raise ValueError("message 不能为空")
        return value

    def _extract_answer(self, result: Any) -> str:
        """从 Agent 执行结果中提取最终回答文本。

        取消息列表中最后一条消息的 content 作为回答；
        若结果为空或非字典，则返回空字符串。
        """
        messages = result.get("messages", []) if isinstance(result, dict) else []
        if not messages:
            return ""
        content = getattr(messages[-1], "content", "")
        if isinstance(content, str):
            return content
        return str(content)

    def _extract_tool_messages(self, result: Any) -> list[StoredMessage]:
        """从 Agent 执行结果中提取所有工具调用消息。

        遍历消息列表，筛选 type 为 "tool" 的消息，
        转换为 StoredMessage 对象列表，用于持久化到对话记忆中。
        """
        messages = result.get("messages", []) if isinstance(result, dict) else []
        tool_messages: list[StoredMessage] = []
        for message in messages:
            if getattr(message, "type", None) != "tool":
                continue
            content = getattr(message, "content", "")
            name = getattr(message, "name", None)
            tool_messages.append(
                StoredMessage(
                    role="tool",
                    content=content if isinstance(content, str) else str(content),
                    name=name if isinstance(name, str) else None,
                )
            )
        return tool_messages
