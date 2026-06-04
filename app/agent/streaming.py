import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentStreamEvent:
    event: str
    data: dict[str, Any]


def format_sse_event(event: AgentStreamEvent) -> str:
    data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {data}\n\n"
