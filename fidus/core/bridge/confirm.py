"""Confirmação com a interface: o pedido aparece na tela (sim/não) e é falado ao mesmo tempo; vale a primeira resposta."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

from ..permissions import Confirmer


class ConfirmBroker:
    def __init__(self, events, timeout_s: float = 30.0):
        self.events, self.timeout_s = events, timeout_s
        self._lock = threading.Lock()
        self._id: str | None = None
        self._answer: bool | None = None
        self._evt = threading.Event()

    # ---- lado da interface ----

    def reply(self, confirm_id: str, answer: bool) -> bool:
        """A interface respondeu. False se não havia pedido com esse id (resposta velha)."""
        with self._lock:
            if confirm_id != self._id or self._evt.is_set():
                return False
            self._answer = bool(answer)
            self._evt.set()
            return True

    # ---- lado do núcleo ----

    def is_answered(self) -> bool:
        return self._evt.is_set()

    def wait_ui(self, prompt: str) -> bool:
        """Plano B do 'sim/não' por voz: espera o clique na interface. Sem interface conectada, nega na hora."""
        if not self.events.has_clients:
            return False
        self._evt.wait(self.timeout_s)
        return bool(self._answer)

    def run(self, prompt: str, voice: Confirmer) -> bool:
        """Mostra o pedido na interface, pergunta por voz e devolve a primeira resposta."""
        with self._lock:
            self._id, self._answer = uuid.uuid4().hex[:12], None
            self._evt.clear()
            cid = self._id
        self.events.emit("confirm", id=cid, text=prompt)
        try:
            if self._evt.is_set():  # (já respondido)
                return bool(self._answer)
            result = voice(prompt)
            return bool(self._answer) if self._evt.is_set() else bool(result)
        finally:
            with self._lock:
                self._id = None
            self.events.emit("confirm_done", id=cid)
