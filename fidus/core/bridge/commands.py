"""Comandos que a interface manda ao núcleo. Cada um valida os argumentos e devolve um dicionário curto."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .. import settings as settings_io
from .settings_schema import SCHEMA, InvalidSetting, validate


class CoreCommands:
    def __init__(self, config, state, loop=None, broker=None, persona=None, on_quit: Callable[[], None] | None = None):
        self.config, self.state, self.loop, self.broker, self.persona = config, state, loop, broker, persona
        self.on_quit = on_quit

    def handle(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        fn = getattr(self, f"cmd_{name}", None)
        if fn is None:
            raise ValueError(f"Comando sem implementação: {name}")
        return fn(**args) if args else fn()

    # ---- estado ----

    def cmd_get_state(self):
        return self.state.snapshot()

    def cmd_ping(self):
        return {"pong": True, "t": time.time()}

    # ---- microfone e chamados ----

    def cmd_mute(self, value: bool = True):
        if not isinstance(value, bool):
            raise ValueError("'value' precisa ser verdadeiro ou falso")
        if self.loop:
            self.loop.set_muted(value)
        return {"muted": value}

    def cmd_pause(self, minutes: float = 60):
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not 0 <= minutes <= 24 * 60:
            raise ValueError("'minutes' precisa ser um número de 0 a 1440")
        if self.loop:
            self.loop.pause_calls(minutes)
        return {"minutes": minutes}

    def cmd_calls(self, value: bool = True):
        if not isinstance(value, bool):
            raise ValueError("'value' precisa ser verdadeiro ou falso")
        if self.loop:
            self.loop.set_calls_enabled(value)
        return {"enabled": value}

    # ---- personagem e configurações ----

    def cmd_set_default_character(self, id: str):
        ids = self.persona.ids() if self.persona else []
        if id not in ids:
            raise ValueError(f"Personagem desconhecido: {id}")
        self._save({"chamados.personagem_padrao": id})
        self.state.events.emit("character", **self.persona.ui_profile(id))
        return {"default_character": id}

    def cmd_get_settings(self):
        return {"settings": settings_io.read(self.config.settings_path), "schema": sorted(SCHEMA)}

    def cmd_set_settings(self, patch: dict):
        if not isinstance(patch, dict) or not patch:
            raise ValueError("'patch' precisa ser um objeto com chave: valor")
        clean = {k: validate(k, v) for k, v in patch.items()}  # valida tudo antes de gravar qualquer coisa
        self._save(clean)
        return {"saved": sorted(clean)}

    def _save(self, clean: dict[str, Any]) -> None:
        from ..config import load_config

        for k, v in clean.items():
            settings_io.set_value(self.config.settings_path, k, v)
        fresh = load_config()  # aplica sem reiniciar o que dá para aplicar na hora
        self.config.wake.default_character = fresh.wake.default_character
        self.config.wake.beep = fresh.wake.beep
        self.config.user.name, self.config.user.surname = fresh.user.name, fresh.user.surname
        self.config.characters.speak_start = fresh.characters.speak_start
        self.config.characters.speak_farewell = fresh.characters.speak_farewell
        self.state.events.emit("settings", changed=sorted(clean))

    # ---- confirmação ----

    def cmd_confirm_reply(self, id: str, answer: bool):
        if not isinstance(answer, bool):
            raise ValueError("'answer' precisa ser verdadeiro ou falso")
        if not self.broker:
            raise ValueError("Nenhuma confirmação pendente")
        return {"accepted": self.broker.reply(id, answer)}

    # ---- ciclo de vida ----

    def cmd_quit(self):
        if self.on_quit:
            self.on_quit()
        return {"bye": True}

    def cmd_simulate(self):
        raise ValueError("Disponível só no modo simulado (`fidus daemon --simulado`).")
