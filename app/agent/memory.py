import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.chat_memory_repository import ChatMemoryRepository


@dataclass(frozen=True)
class StoredMessage:
    """对话消息的数据对象，不可变，用于内存传递和持久化。"""

    role: str  # 消息角色："user"（用户）| "assistant"（AI）| "tool"（仅用于本轮工具追踪）
    content: str  # 消息正文内容
    name: str | None = None  # 工具名称，仅当 role="tool" 时有值

    def as_langchain_message(self) -> dict[str, str]:
        """转换为发送给大模型的格式，仅保留 role + content。"""
        return {"role": self.role, "content": self.content}

    def as_storage_message(self) -> dict[str, str]:
        """转换为存入数据库的格式。长期记忆只保存 role + content。"""
        return {"role": self.role, "content": self.content}


class ChatMemoryService:
    """管理每个会话的对话历史存取，支持滑动窗口控制消息数量。"""

    def __init__(self, repository: ChatMemoryRepository | None = None, max_messages: int = 20) -> None:
        # repository: 对话记忆的数据访问层，默认创建新实例（依赖注入）
        # max_messages: 历史消息保留上限，超出部分在保存时被截断丢弃
        self.repository = repository or ChatMemoryRepository()
        self.max_messages = max_messages

    async def get_messages(self, session: AsyncSession, session_id: str) -> list[StoredMessage]:
        """从数据库读取历史对话消息，返回最近 max_messages 条。"""
        memory = await self.repository.find_by_session_id(session, session_id)
        if memory is None:
            return []

        # 解析 JSON，若数据损坏则安全降级返回空列表
        try:
            raw_messages = json.loads(memory.messages)
        except json.JSONDecodeError:
            return []

        # 逐条校验并转换为 StoredMessage
        messages: list[StoredMessage] = []
        for item in raw_messages:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            # 长期记忆只接受 user/assistant，历史脏数据中的 tool 会被丢弃
            if role in {"user", "assistant"} and isinstance(content, str):
                messages.append(
                    StoredMessage(
                        role=role,
                        content=content,
                    )
                )
        # 滑动窗口：只返回最近 max_messages 条
        return messages[-self.max_messages :]

    async def get_context_messages(self, session: AsyncSession, session_id: str) -> list[StoredMessage]:
        """获取发给大模型的上下文消息，与数据库长期记忆保持一致。"""
        return await self.get_messages(session, session_id)

    async def append_turn(
        self,
        session: AsyncSession,
        session_id: str,
        user_message: str,     # 本轮用户输入
        ai_message: str,       # 本轮 AI 最终回答
        tool_messages: list[StoredMessage] | None = None,  # 本轮工具调用的中间结果
    ) -> None:
        """追加一轮对话（用户消息 + AI回答）并保存到数据库。"""
        messages = await self.get_messages(session, session_id)
        messages.append(StoredMessage(role="user", content=user_message))
        messages.append(StoredMessage(role="assistant", content=ai_message))
        # 保存时截断，只保留最近 max_messages 条
        await self._save(session, session_id, messages[-self.max_messages :])

    async def clear(self, session: AsyncSession, session_id: str) -> None:
        """清空指定会话的全部对话记忆。"""
        await self.repository.delete_by_session_id(session, session_id)

    async def _save(self, session: AsyncSession, session_id: str, messages: list[StoredMessage]) -> None:
        """将消息列表序列化为 JSON 并持久化到数据库。"""
        # ensure_ascii=False 保留中文原文，不转义为 \uXXXX
        payload = json.dumps(
            [message.as_storage_message() for message in messages],
            ensure_ascii=False,
        )
        await self.repository.save_messages(session, session_id, payload)
