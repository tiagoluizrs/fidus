"""Adaptador da Anthropic. O SDK só é importado quando a primeira chamada acontece."""

from __future__ import annotations

from ..secrets import get_anthropic_key
from .base import Message, Response, ToolCall, ToolSpec

MAX_TOKENS = 1024


class AnthropicProvider:
    def __init__(self, model: str, api_key: str | None = None):
        self.model = model
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic

            key = self._api_key or get_anthropic_key()
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY não encontrada. Defina no .env (desenvolvimento) ou no keyring."
                )
            self._client = anthropic.Anthropic(api_key=key)
        return self._client

    def complete(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Response:
        kwargs = {}
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]
        reply = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[_to_api(m) for m in messages],
            **kwargs,
        )
        text = "".join(b.text for b in reply.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in reply.content if b.type == "tool_use"]
        return Response(text=text, tool_calls=calls)

    def check_key(self) -> str:
        """Chamada mínima para confirmar que a chave funciona. Devolve o texto da resposta."""
        reply = self.client.messages.create(
            model=self.model, max_tokens=16, messages=[{"role": "user", "content": "Responda apenas: ok"}]
        )
        return "".join(b.text for b in reply.content if b.type == "text")


def _to_api(m: Message) -> dict:
    if m.role == "assistant":
        blocks: list[dict] = [{"type": "text", "text": m.text}] if m.text else []
        blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
        return {"role": "assistant", "content": blocks}
    if m.tool_results:
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": r.is_error}
                for r in m.tool_results
            ],
        }
    return {"role": "user", "content": m.text}
