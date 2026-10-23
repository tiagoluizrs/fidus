"""Núcleo simulado: mesmos eventos e comandos do real, sem microfone, modelo nem voz. Serve para desenvolver e testar a interface."""

from __future__ import annotations

import math
import threading
import time

from .commands import CoreCommands

SCRIPT_USER = "O que tenho na agenda hoje?"
SCRIPT_ASSISTANT = "Bom dia. Você tem duas reuniões; a primeira é às 9h."


class SimulatedCommands(CoreCommands):
    """Comandos reais de estado/configuração + `simulate`, que encena uma conversa."""

    def __init__(self, *a, speed: float = 1.0, **kw):
        super().__init__(*a, **kw)
        self.speed = speed
        self._thread: threading.Thread | None = None
        self.muted = False
        self.calls = True

    def _emit(self, type, **d):
        self.state.events.emit(type, **d)

    def cmd_mute(self, value: bool = True):
        if not isinstance(value, bool):
            raise ValueError("'value' precisa ser verdadeiro ou falso")
        self.muted = value
        self._emit("state", state="muted" if value else "idle", mic="muted" if value else "passive")
        return {"muted": self.muted}

    def cmd_calls(self, value: bool = True):
        if not isinstance(value, bool):
            raise ValueError("'value' precisa ser verdadeiro ou falso")
        self.calls = value
        self._emit("calls", enabled=self.calls, until=None)
        return {"enabled": self.calls}

    def cmd_pause(self, minutes: float = 60):
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not 0 <= minutes <= 24 * 60:
            raise ValueError("'minutes' precisa ser um número de 0 a 1440")
        until = time.time() + minutes * 60 if minutes else None
        self._emit("calls", enabled=not minutes, until=until)
        return {"minutes": minutes}

    def cmd_simulate(self):
        if self._thread and self._thread.is_alive():
            return {"running": True}
        self._thread = threading.Thread(target=self._play, daemon=True, name="fidus-simulacao")
        self._thread.start()
        return {"running": True}

    def _sleep(self, s: float) -> None:
        time.sleep(s / self.speed)

    def _play(self) -> None:
        ch = self.persona.ui_profile(self.state.character_id)
        self._emit("character", **ch)
        self._emit("state", state="listening", mic="recording")
        for i in range(60):  # ~2 s de "voz": 30 lotes de 3 valores
            if i % 2 == 0:
                self._emit("level", values=[round(abs(math.sin((i + k) / 3.0)) * 0.8, 3) for k in range(3)])
            self._sleep(0.033)
        self._emit("caption", role="user", text=SCRIPT_USER, final=True)
        self._emit("state", state="thinking", mic="paused")
        self._sleep(1.2)
        self._emit("state", state="speaking", mic="paused")
        for word in SCRIPT_ASSISTANT.split(" "):
            self._emit("caption", role="assistant", text=word + " ", final=False)
            self._sleep(0.18)
        self._emit("caption", role="assistant", text="", final=True)
        self._sleep(0.6)
        self._emit("state", state="idle", mic="passive")
