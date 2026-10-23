"""Estado do núcleo visto pela interface (o que vai no `ready` e nos eventos)."""

from __future__ import annotations

from ..config import Config


class CoreState:
    def __init__(self, config: Config, persona, events):
        self.config, self.persona, self.events = config, persona, events
        self.status = "starting"  # starting | ready | error
        self.message = ""
        self.state = "idle"
        self.mic = "passive"
        self.character_id = persona.default_id()
        self.calls_enabled = True
        self.paused_until: float | None = None
        self.muted = False

    def model_info(self) -> dict:
        if self.config.provider == "local":
            return {"provider": "local", "name": self.config.local_model, "where": "Neste computador"}
        return {"provider": "claude", "name": self.config.model, "where": "Nuvem"}

    def set_status(self, status: str, message: str = "") -> None:
        self.status, self.message = status, message
        self.events.emit("status", core=status, message=message)

    def snapshot(self) -> dict:
        return {
            "status": self.status, "message": self.message, "state": self.state, "mic": self.mic,
            "character": self.persona.ui_profile(self.character_id), "default_character": self.persona.default_id(),
            "characters": [self.persona.ui_profile(c) for c in self.persona.ids()],
            "model": self.model_info(), "calls": {"enabled": self.calls_enabled, "until": self.paused_until},
            "muted": self.muted,
        }


class StateTap:
    """Envolve o canal de eventos para o `CoreState` acompanhar o que passa (e assim o snapshot do `ready` fica certo)."""

    def __init__(self, inner, state: CoreState):
        self.inner, self.state = inner, state

    @property
    def has_clients(self) -> bool:
        return self.inner.has_clients

    def emit(self, type: str, **data) -> None:
        s = self.state
        if type == "state":
            s.state, s.mic = data.get("state", s.state), data.get("mic", s.mic)
            s.muted = s.state == "muted"
        elif type == "character":
            s.character_id = data.get("id", s.character_id)
        elif type == "calls":
            s.calls_enabled, s.paused_until = bool(data.get("enabled", True)), data.get("until")
        self.inner.emit(type, **data)
