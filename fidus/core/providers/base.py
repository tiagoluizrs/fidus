"""Interface única entre o orquestrador e qualquer modelo (Claude agora; Ollama/OpenAI depois)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    role: str  # "user" | "assistant"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # só em "assistant"
    tool_results: list[ToolResult] = field(default_factory=list)  # só em "user"


@dataclass
class Response:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class Provider(Protocol):
    def complete(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Response: ...
