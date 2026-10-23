"""Ponto único por onde o núcleo avisa a interface. Sem interface conectada, não custa nada."""

from __future__ import annotations

from typing import Protocol


class EventSink(Protocol):
    @property
    def has_clients(self) -> bool: ...

    def emit(self, type: str, **data) -> None: ...


class NullEvents:
    """Padrão quando não há interface (terminal): descarta tudo."""

    has_clients = False

    def emit(self, type: str, **data) -> None:
        pass


# Estado interno do laço de escuta -> estado que a interface desenha.
def ui_state(loop_state: str, muted: bool) -> str:
    if muted:
        return "muted"
    return {"sleeping": "idle", "recording": "listening", "followup": "listening", "processing": "thinking"}.get(loop_state, "idle")
