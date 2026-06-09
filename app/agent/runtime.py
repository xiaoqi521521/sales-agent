from collections.abc import Callable
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from time import perf_counter
from typing import Any

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import get_usage_metadata_callback
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory import ChatMemoryService, StoredMessage
from app.agent.prompts import build_system_prompt
from app.core.auth_context import CurrentUser
from app.core.config import get_settings
from app.core.logging import format_kv, get_logger
from app.core.token_usage import TokenUsage, log_token_usage, summarize_usage_metadata
from app.tools.formatting import tool_invalid_argument
from app.tools.registry import create_sales_tools


AgentFactory = Callable[..., Any]
logger = get_logger("sales_agent.agent")


@dataclass(frozen=True)
class ToolCallTrace:
    """Agent 单次工具调用的追踪记录。"""
    name: str      # 工具名称
    summary: str   # 工具调用结果摘要


@dataclass(frozen=True)
class AgentRunResult:
    """Agent 单次运行的完整结果，包含回答、工具调用记录和数据引用。"""
    reply: str                                          # AI 最终回答文本
    tool_calls: list[ToolCallTrace] = field(default_factory=list)   # 本轮所有工具调用记录
    data_references: list[str] = field(default_factory=list)        # 数据来源引用（预留）


def create_default_chat_model() -> Any:
    """根据配置文件创建默认的大模型实例（阿里云通义千问）。"""
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY 未配置，无法创建默认聊天模型")

    return init_chat_model(
        model=settings.openai_model,         # 模型名称，如 "qwen-max"
        model_provider="openai",             # 使用 OpenAI 兼容接口协议
        base_url=settings.openai_base_url,   # 阿里云通义千问的 API 地址
        api_key=settings.openai_api_key,
    )


class SalesAgentRuntime:
    """销售 AI Agent 运行时，负责组装并驱动 Agent 完成多轮对话。"""

    def __init__(
        self,
        *,
        session: AsyncSession,                                    # 数据库会话，用于记忆读写
        model: Any | None = None,                                 # 大模型实例，默认从配置创建
        today: date | None = None,                                # 当前日期，用于系统提示词，默认当天
        memory_service: ChatMemoryService | None = None,          # 对话记忆服务，默认最多保留20条
        checkpointer: Any | None = None,                          # LangGraph 检查点（可选，用于持久化图状态）
        current_user: CurrentUser | None = None,
        agent_factory: AgentFactory = create_agent,               # Agent 工厂函数，支持替换为 Mock
        recursion_limit: int = 10,                                # Agent 最大递归调用次数，防止死循环
    ) -> None:
        self.session = session
        self.today = today or date.today()
        self.current_user = current_user
        self.memory_service = memory_service or ChatMemoryService(max_messages=20)
        self.recursion_limit = recursion_limit
        # 创建所有销售查询工具（闭包绑定 session 和 today）
        self.tools = create_sales_tools(session=session, today=self.today, current_user=current_user)
        # 构建系统提示词（告知 Agent 角色、规则、当前日期）
        self.system_prompt = build_system_prompt(self.today, current_user=current_user)
        agent_kwargs = {
            "model": model or create_default_chat_model(),
            "tools": self.tools,
            "system_prompt": self.system_prompt,
        }
        # 可选：加入 LangGraph 检查点，用于图状态持久化
        if checkpointer is not None:
            agent_kwargs["checkpointer"] = checkpointer

        # 用工厂函数组装 Agent（模型 + 工具 + 提示词）
        self.agent = agent_factory(
            **agent_kwargs,
        )

    async def chat(self, *, session_id: str, message: str) -> str:
        """简易对话接口，只返回 AI 回答文本，不含工具调用详情。"""
        result = await self.chat_with_trace(session_id=session_id, message=message)
        return result.reply

    async def chat_with_trace(self, *, session_id: str, message: str) -> AgentRunResult:
        """带追踪的对话接口，返回完整结果（回答 + 工具调用记录 + 数据引用）。"""
        normalized_session_id = self._validate_session_id(session_id)
        normalized_message = self._validate_message(message)
        started_at = perf_counter()
        settings = get_settings()
        logger.info(
            format_kv(
                "agent_run_started",
                sessionId=normalized_session_id,
                messageLength=len(normalized_message),
                model=settings.openai_model,
            )
        )

        # 构建 Agent 输入：历史上下文 + 当前用户消息
        payload, config = await self._build_agent_input(normalized_session_id, normalized_message)

        try:
            # 调用 Agent（大模型决策 + 自动调用工具）
            with get_usage_metadata_callback() as usage_callback:
                result = await self.agent.ainvoke(payload, config=config)
        except ValidationError:
            logger.warning(format_kv("agent_tool_parameter_validation_failed", sessionId=normalized_session_id))
            return AgentRunResult(reply=_tool_parameter_validation_message())
        except Exception:
            logger.exception(format_kv("agent_run_failed", sessionId=normalized_session_id))
            raise
        # 提取 AI 最终回答
        answer = self._extract_answer(result)
        # 提取工具调用的中间结果
        tool_messages = self._extract_tool_messages(result)
        usage = summarize_usage_metadata(usage_callback.usage_metadata)
        if usage.total_tokens <= 0:
            usage = self._extract_usage(result)
        log_token_usage(
            session_id=normalized_session_id,
            model_name=settings.openai_model,
            usage=usage,
            settings=settings,
        )
        # 将本轮完整对话（用户+工具+AI）持久化到记忆
        await self.memory_service.append_turn(
            self.session,
            normalized_session_id,
            normalized_message,
            answer,
            tool_messages=tool_messages,
        )
        duration_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            format_kv(
                "agent_run_completed",
                sessionId=normalized_session_id,
                model=settings.openai_model,
                durationMs=duration_ms,
                toolCalls=len(tool_messages),
            )
        )
        return AgentRunResult(reply=answer, tool_calls=self._to_tool_traces(tool_messages))

    async def stream_chat(self, *, session_id: str, message: str) -> AsyncIterator["AgentStreamEvent"]:
        """流式对话接口，逐 token 推送 AI 回答，支持实时展示生成过程。"""
        from app.agent.streaming import AgentStreamEvent

        normalized_session_id = self._validate_session_id(session_id)
        normalized_message = self._validate_message(message)
        payload, config = await self._build_agent_input(normalized_session_id, normalized_message)

        started_at = perf_counter()      # 记录开始时间（高精度时钟）
        answer_parts: list[str] = []     # 累积流式 token 片段
        latest_model_answer = ""         # 兜底：若 token 拼接为空，取最后一次模型完整输出
        tool_messages: list[StoredMessage] = []  # 本轮工具调用结果

        # 降级处理：若 Agent 不支持流式（astream），退化为普通 ainvoke 一次性返回
        if not hasattr(self.agent, "astream"):
            try:
                result = await self.agent.ainvoke(payload, config=config)
            except ValidationError:
                logger.warning(format_kv("agent_tool_parameter_validation_failed", sessionId=normalized_session_id))
                yield AgentStreamEvent(event="error", data={"message": _tool_parameter_validation_message()})
                return
            answer = self._extract_answer(result)
            tool_messages = self._extract_tool_messages(result)
            if answer:
                yield AgentStreamEvent(event="token", data={"content": answer})
            duration_ms = int((perf_counter() - started_at) * 1000)
            settings = get_settings()
            log_token_usage(
                session_id=normalized_session_id,
                model_name=settings.openai_streaming_model,
                usage=self._extract_usage(result),
                settings=settings,
            )
            await self.memory_service.append_turn(
                self.session,
                normalized_session_id,
                normalized_message,
                answer,
                tool_messages=tool_messages,
            )
            yield self._done_event(normalized_session_id, answer, tool_messages, duration_ms)
            return

        # 流式模式：同时接收 messages（逐 token）和 updates（节点完成事件）
        try:
            async for chunk in self.agent.astream(
                payload,
                config=config,
                stream_mode=["messages", "updates"],  # messages=逐 token，updates=节点状态变更
                version="v2",
            ):
                chunk_type = chunk.get("type") if isinstance(chunk, dict) else None

                if chunk_type == "messages":
                    # 逐 token 推送：实时发给前端展示打字效果
                    token, _metadata = chunk.get("data", (None, None))
                    text = self._extract_token_text(token)
                    if text:
                        answer_parts.append(text)
                        yield AgentStreamEvent(event="token", data={"content": text})

                elif chunk_type == "updates":
                    # 节点更新事件：捕获工具调用结果和模型完整输出
                    for source, update in chunk.get("data", {}).items():
                        messages = update.get("messages", []) if isinstance(update, dict) else []
                        if not messages:
                            continue
                        latest_message = messages[-1]
                        if source == "tools" or getattr(latest_message, "type", None) == "tool":
                            # 工具节点完成：提取工具调用结果，推送 tool 事件给前端
                            tool_message = self._to_stored_tool_message(latest_message)
                            if tool_message is not None:
                                tool_messages.append(tool_message)
                                yield AgentStreamEvent(
                                    event="tool",
                                    data={
                                        "name": tool_message.name or "unknown_tool",
                                        "summary": tool_message.content,
                                    },
                                )
                        elif source == "model":
                            # 模型节点完成：记录完整回答作为兜底
                            content = getattr(latest_message, "content", "")
                            if isinstance(content, str) and content:
                                latest_model_answer = content
        except ValidationError:
            logger.warning(format_kv("agent_tool_parameter_validation_failed", sessionId=normalized_session_id))
            yield AgentStreamEvent(event="error", data={"message": _tool_parameter_validation_message()})
            return

        # 流式结束：拼接 token 得到最终回答，持久化并发送 done 事件
        answer = "".join(answer_parts) or latest_model_answer
        duration_ms = int((perf_counter() - started_at) * 1000)
        settings = get_settings()
        log_token_usage(
            session_id=normalized_session_id,
            model_name=settings.openai_streaming_model,
            usage=TokenUsage(),
            settings=settings,
        )
        await self.memory_service.append_turn(
            self.session,
            normalized_session_id,
            normalized_message,
            answer,
            tool_messages=tool_messages,
        )
        yield self._done_event(normalized_session_id, answer, tool_messages, duration_ms)

    async def _build_agent_input(self, session_id: str, message: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """构建 Agent 的输入 payload 和运行 config。

        payload: 历史消息列表 + 当前用户消息
        config:  运行配置（thread_id 用于记忆隔离，recursion_limit 防止死循环）
        """
        history = await self.memory_service.get_context_messages(self.session, session_id)
        payload = {
            "messages": [
                *[item.as_langchain_message() for item in history],  # 历史上下文
                {"role": "user", "content": message},                 # 当前用户输入
            ]
        }
        config = {
            "configurable": {"thread_id": session_id},  # thread_id 隔离不同会话的图状态
            "recursion_limit": self.recursion_limit,    # 限制 Agent 最大工具调用轮数
        }
        return payload, config

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
            tool_message = self._to_stored_tool_message(message)
            if tool_message is not None:
                tool_messages.append(tool_message)
        return tool_messages

    def _extract_usage(self, result: Any) -> TokenUsage:
        messages = result.get("messages", []) if isinstance(result, dict) else []
        for message in reversed(messages):
            usage_metadata = getattr(message, "usage_metadata", None)
            if isinstance(usage_metadata, dict):
                usage = summarize_usage_metadata(usage_metadata)
                if usage.total_tokens > 0:
                    return usage
        return TokenUsage()

    def _to_stored_tool_message(self, message: Any) -> StoredMessage | None:
        """将 LangChain 的 tool 类型消息转换为 StoredMessage。

        若消息类型不是 "tool"，则返回 None（用于流式模式中逐条过滤）。
        """
        # 只处理 type="tool" 的消息，其余类型直接跳过
        if getattr(message, "type", None) != "tool":
            return None
        content = getattr(message, "content", "")
        name = getattr(message, "name", None)
        return StoredMessage(
            role="tool",
            # content 可能是非字符串类型（如 list），统一转为 str
            content=content if isinstance(content, str) else str(content),
            name=name if isinstance(name, str) else None,
        )

    def _to_tool_traces(self, tool_messages: list[StoredMessage]) -> list[ToolCallTrace]:
        """将 StoredMessage 列表转换为 ToolCallTrace 列表，用于接口响应和 done 事件。

        若工具名称为空，则兜底标记为 "unknown_tool"。
        """
        return [
            ToolCallTrace(
                name=message.name or "unknown_tool",  # 工具名称，缺失时兜底
                summary=message.content,              # 工具调用结果摘要
            )
            for message in tool_messages
        ]

    def _extract_token_text(self, token: Any) -> str:
        """从流式 token 对象中提取文本内容。

        优先取 text 属性（AIMessageChunk），兜底取 content 属性。
        """
        text = getattr(token, "text", "")
        if isinstance(text, str) and text:
            return text

        content = getattr(token, "content", "")
        if isinstance(content, str):
            return content
        return ""

    def _done_event(
        self,
        session_id: str,
        reply: str,
        tool_messages: list[StoredMessage],
        duration_ms: int,
    ) -> "AgentStreamEvent":
        """构建流式结束事件（event="done"），携带完整回答、工具调用摘要和耗时。"""
        from app.agent.streaming import AgentStreamEvent

        return AgentStreamEvent(
            event="done",
            data={
                "sessionId": session_id,                  # 会话 ID，与同步接口响应保持一致
                "reply": reply,                        # AI 最终完整回答
                "durationMs": duration_ms,             # 本次对话总耗时（毫秒）
                "toolCalls": [                         # 本轮所有工具调用摘要
                    {"name": trace.name, "summary": trace.summary}
                    for trace in self._to_tool_traces(tool_messages)
                ],
                "dataReferences": [],                  # 数据来源引用（预留字段）
            },
        )


def _tool_parameter_validation_message() -> str:
    return tool_invalid_argument("工具参数不合法，请检查日期格式、大区名称、图表类型、维度或数值范围。")
