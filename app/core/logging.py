"""日志基础设施模块

提供结构化日志格式、追踪 ID 自动注入和统一日志配置。
输出格式为 key=value 的结构化日志，便于日志采集系统（如 ELK）解析。
"""
import logging
import sys
from typing import Any

from app.core.request_context import get_trace_id


def configure_logging() -> None:
    """初始化全局日志配置：stdout 输出、INFO 级别、简洁格式。

    幂等设计：仅在无 handler 时添加，避免重复注册导致日志重复打印。
    """
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 Logger 实例，通常传入模块名如 'sales_agent.api'。"""
    return logging.getLogger(name)


def format_kv(event: str, **fields: Any) -> str:
    """将事件名和字段格式化为 key=value 结构的日志字符串。

    自动从上下文注入 traceId，None 值字段会被过滤。

    Args:
        event: 事件标识符，如 "http_request_completed"
        **fields: 任意附加字段，如 method="GET", durationMs=120

    Returns:
        格式化字符串，如 'event=http_request_completed traceId=abc method=GET durationMs=120'
    """
    values: dict[str, Any] = {"event": event}
    trace_id = get_trace_id()
    if trace_id:
        values["traceId"] = trace_id
    values.update({key: value for key, value in fields.items() if value is not None})
    return " ".join(f"{key}={_format_value(value)}" for key, value in values.items())


def _format_value(value: Any) -> str:
    """格式化单个值：含空格的字符串加引号包裹，防止日志解析歧义。"""
    text = str(value)
    if any(char.isspace() for char in text):
        return repr(text)
    return text

