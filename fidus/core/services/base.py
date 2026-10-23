"""Interfaces genéricas de serviços. O orquestrador e as ferramentas só conhecem isto, nunca Gmail/Slack/Google.

Regras de privacidade valem aqui: itens são curtos (cortados), sem anexos, e a caixa de entrada nunca é devolvida inteira.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from ..tools.base import ToolError


class NotConnected(ToolError):
    """A conta não está conectada (ou a escrita não foi liberada). A mensagem diz o que fazer."""


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


def fit(items: list[str], limits, item_chars: int | None = None) -> str:
    """Aplica os limites de conteúdo externo: itens, tamanho por item e tamanho do pedido inteiro."""
    out: list[str] = []
    total = 0
    for item in items[: limits.max_items]:
        item = clip(item, item_chars or limits.item_chars)
        if total + len(item) + 1 > limits.request_chars:
            out.append("[o restante foi omitido pelo limite de tamanho]")
            return "\n".join(out)
        out.append(item)
        total += len(item) + 1
    if len(items) > limits.max_items:
        out.append(f"[+{len(items) - limits.max_items} item(ns) não mostrados; peça uma busca mais específica]")
    return "\n".join(out)


# ------------------------------------------------------------------ agenda


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime | date
    end: datetime | date
    all_day: bool = False
    location: str = ""  # a descrição do evento NUNCA entra: só o necessário vai ao modelo


class CalendarService(Protocol):
    def list_events(self, start: date, days: int, limit: int = 50) -> list[CalendarEvent]: ...

    def create_event(self, title: str, start: datetime, end: datetime, location: str = "") -> CalendarEvent: ...

    def update_event(
        self, event_id: str, title: str | None = None, start: datetime | None = None,
        end: datetime | None = None, location: str | None = None,
    ) -> CalendarEvent: ...
    # Sem apagar evento: não existe ação irreversível na agenda na v1.


# ------------------------------------------------------------------ e-mail


@dataclass
class EmailItem:
    id: str
    sender: str
    subject: str
    date: str
    snippet: str  # trecho do corpo, já cortado
    unread: bool = False


class EmailService(Protocol):
    def search(self, query: str, limit: int, snippet_chars: int) -> list[EmailItem]: ...

    def read(self, email_id: str, max_chars: int) -> EmailItem: ...

    def create_draft(self, to: str, subject: str, body: str, reply_to_id: str | None = None) -> str:
        """Cria um RASCUNHO e devolve o id. Não existe envio nesta interface (v1)."""


# ------------------------------------------------------------------ chat


@dataclass
class Channel:
    id: str
    name: str
    private: bool = False


@dataclass
class ChatMessage:
    ts: str
    channel: str
    author: str
    text: str
    when: str = ""


class ChatService(Protocol):
    def channels(self) -> list[Channel]:
        """Só os canais/conversas permitidos na configuração."""

    def read(self, channel: str, limit: int, text_chars: int) -> list[ChatMessage]: ...

    def reply(self, channel: str, text: str, thread_ts: str | None = None) -> str:
        """Responde em um canal permitido (a ferramenta sempre pede confirmação antes)."""
