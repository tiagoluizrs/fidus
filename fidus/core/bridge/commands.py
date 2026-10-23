"""Comandos que a interface manda ao núcleo. Cada um valida os argumentos e devolve um dicionário curto."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .. import settings as settings_io
from .settings_schema import CLAUDE_MODELS, GEMINI_MODELS, RESTART_REQUIRED, SCHEMA, InvalidSetting, effective, validate_all


class CoreCommands:
    def __init__(self, config, state, loop=None, broker=None, persona=None, on_quit: Callable[[], None] | None = None):
        self.config, self.state, self.loop, self.broker, self.persona = config, state, loop, broker, persona
        self.on_quit = on_quit
        from .handlers import Handlers

        self.h = Handlers(config, state, persona, loop, save_settings=self._save) if persona else None

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
        return {
            "settings": settings_io.read(self.config.settings_path), "effective": effective(self.config), "schema": sorted(SCHEMA),
            "claude_models": list(CLAUDE_MODELS), "gemini_models": list(GEMINI_MODELS), "restart_required": sorted(RESTART_REQUIRED),
        }

    def cmd_set_settings(self, patch: dict):
        if not isinstance(patch, dict) or not patch:
            raise ValueError("'patch' precisa ser um objeto com chave: valor")
        clean = {k: validate_all(k, v) for k, v in patch.items()}  # valida tudo antes de gravar qualquer coisa
        if clean.get("modelo.local_acoes_ciente") is False and "modelo.local_acoes" not in clean:
            clean["modelo.local_acoes"] = False  # tirar a ciência desliga a liberação
        merged = {**effective(self.config), **clean}
        if merged["modelo.local_acoes"] and not merged["modelo.local_acoes_ciente"]:
            raise ValueError("Para liberar ações com o modelo local, marque que você entende os riscos.")
        self._save(clean)
        return {"saved": sorted(clean), "restart_required": sorted(set(clean) & RESTART_REQUIRED)}

    def _save(self, clean: dict[str, Any]) -> None:
        from ..config import apply_live, load_config

        for k, v in clean.items():
            settings_io.set_value(self.config.settings_path, k, v)
        apply_live(self.config, load_config())  # aplica sem reiniciar o que dá para aplicar na hora
        self._apply_runtime()
        self.state.events.emit("settings", changed=sorted(clean))

    def _apply_runtime(self) -> None:
        """O que não está só em `config`: o modelo do provedor e a velocidade da voz."""
        loop = self.loop
        orch = getattr(getattr(loop, "handler", None), "orchestrator", None)
        if orch is not None:
            from ..providers import sync_provider

            sync_provider(orch, self.config)
        self.state.events.emit("model", **self.state.model_info())  # a tela e o menu mostram quem está respondendo
        tts = getattr(loop, "tts", None)
        if tts is not None and hasattr(tts, "base_rate"):
            tts.base_rate = self.config.voice.speech_rate
            speaker = getattr(loop, "speaker", None)
            if speaker is not None:
                speaker._applied = None  # reaplica a voz (e a velocidade nova) na próxima fala

    # ---- confirmação ----

    def cmd_confirm_reply(self, id: str, answer: bool):
        if not isinstance(answer, bool):
            raise ValueError("'answer' precisa ser verdadeiro ou falso")
        if not self.broker:
            raise ValueError("Nenhuma confirmação pendente")
        return {"accepted": self.broker.reply(id, answer)}

    # ---- telas de Configurações (operações por domínio) ----

    def _domain(self, name: str, op: str, args: dict):
        if self.h is None:
            raise ValueError("Núcleo sem personagens carregados.")
        self.h.loop = self.loop  # o laço real pode ter sido ligado depois da criação
        return getattr(self.h, name)(op, **args)

    def cmd_characters(self, op: str = "list", **a):
        return self._domain("characters", op, a)

    def cmd_memory(self, op: str = "list", **a):
        return self._domain("memory", op, a)

    def cmd_accounts(self, op: str = "list", **a):
        return self._domain("accounts", op, a)

    def cmd_privacy(self, op: str = "get", **a):
        return self._domain("privacy", op, a)

    def cmd_about(self, op: str = "get", **a):
        return self._domain("about", op, a)

    def cmd_devices(self):
        return self.h.devices()

    def cmd_api_key(self, op: str = "status", value: str = "", provider: str = "claude"):
        self.h.loop = self.loop
        return self.h.api_key(op, value, provider)

    def cmd_piper(self, op: str = "status", voice: str = ""):
        self.h.loop = self.loop
        return self.h.piper(op, voice)

    def cmd_voice_cloud(self, op: str = "status", **a):
        self.h.loop = self.loop
        return self.h.voice_cloud(op, **a)

    def cmd_ask(self, text: str, id: str | None = None):
        ask = getattr(self.loop, "ask", None)
        if ask is None:
            raise ValueError("Pedidos por texto só existem no modo `fidus daemon --headless` (testes no Docker/navegador).")
        return ask(text, id)

    def cmd_ask_audio(self, pcm: str, id: str | None = None, wake: bool = False):
        ask = getattr(self.loop, "ask_audio", None)
        if ask is None:
            raise ValueError("A fala pelo navegador só existe no modo `fidus daemon --headless` (testes no Docker/navegador).")
        return ask(pcm, id, wake is True)

    def cmd_browser_mic(self, on: bool = True):
        set_mic = getattr(self.loop, "set_browser_mic", None)
        if set_mic is None:
            raise ValueError("O microfone do navegador só existe no modo `fidus daemon --headless`.")
        if not isinstance(on, bool):
            raise ValueError("'on' precisa ser verdadeiro ou falso")
        set_mic(on)
        return {"on": on}

    def cmd_local_models(self, op: str = "list", model: str = ""):
        self.h.loop = self.loop
        return self.h.local_models(op, model)

    def cmd_voices(self, engine: str = "sapi"):
        self.h.loop = self.loop
        return self.h.voices(engine)

    # ---- ciclo de vida ----

    def cmd_quit(self):
        if self.on_quit:
            self.on_quit()
        return {"bye": True}

    def cmd_simulate(self):
        raise ValueError("Disponível só no modo simulado (`fidus daemon --simulado`).")
