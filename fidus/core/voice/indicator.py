"""Indicador textual do microfone: o usuário sempre vê em que estado ele está."""

from __future__ import annotations

from collections.abc import Callable

LABELS = {
    "passive": "[MICROFONE: ESCUTA PASSIVA] só aguardando o chamado; nada é gravado nem enviado",
    "recording": "[MICROFONE: GRAVANDO] o áudio vai ser transcrito neste computador",
    "paused": "[MICROFONE: ABERTO, ESCUTA PAUSADA] respondendo",
    "muted": "[MICROFONE: SILENCIADO] fechado; ninguém está ouvindo",
    "off": "[MICROFONE: FECHADO]",
}


class Indicator:
    def __init__(self, out: Callable[[str], None] = print):
        self.out, self.state = out, ""

    def show(self, state: str) -> None:
        if state != self.state:  # só imprime quando muda
            self.state = state
            self.out(LABELS[state])
