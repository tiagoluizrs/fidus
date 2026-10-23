"""Interface única entre o orquestrador e qualquer modelo (Claude agora; Ollama/OpenAI depois)."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, Protocol


class SystemPrompt(str):
    """Prompt de sistema em duas partes: a estável (regras + personagem), que o cache de prompt da API reaproveita,
    e a volátil (data, memória, resumo), que muda a cada pedido. Continua sendo uma `str` normal."""

    stable_len: int

    def __new__(cls, stable: str, volatile: str = ""):
        obj = super().__new__(cls, stable + volatile)
        obj.stable_len = len(stable)
        return obj


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
    extra: Any = None  # dado bruto do provedor que precisa voltar na próxima rodada (ex.: assinatura de raciocínio do Gemini)


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

    def complete_stream(
        self, system: str, messages: list[Message], tools: list[ToolSpec], on_text: Callable[[str], None]
    ) -> Response:
        """Como `complete`, mas entrega cada trecho de texto a `on_text` assim que chega."""
        ...
