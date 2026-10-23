"""Núcleo REAL sem áudio (`fidus daemon --headless`): o mesmo modelo, ferramentas, permissões e configurações,
mas o pedido chega por texto (comando `ask`) em vez do microfone, e a resposta volta como legendas.

Serve para testar tudo no Docker/navegador, onde não há microfone nem voz do Windows.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

from ..assistant import build_assistant
from ..config import Config
from .confirm import ConfirmBroker


class HeadlessLoop:
    """Faz o papel do ListenLoop para os comandos da interface (silenciar, chamados, confirmação) sem usar áudio."""

    def __init__(self, config: Config, events, state, provider=None):
        self.config, self.events, self.state = config, events, state
        self.broker = ConfirmBroker(events)
        confirm = lambda prompt: self.broker.run(prompt, self.broker.wait_ui)  # noqa: E731 - sem voz: só o clique na tela vale
        self.orchestrator, self.persona, _ = build_assistant(config, confirm, provider=provider)
        self.handler = SimpleNamespace(orchestrator=self.orchestrator)  # onde o `_apply_runtime` procura o provedor
        self.manager = self.tts = self.speaker = None  # sem microfone nem voz
        self._busy = threading.Lock()
        self._stop = threading.Event()

    # ---- pedido por texto ----

    def ask(self, text: str, character: str | None = None) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("Digite um pedido.")
        if not self._busy.acquire(blocking=False):
            raise ValueError("Ainda estou respondendo ao pedido anterior.")
        cid = self.persona.resolve_id(character or self.state.character_id)
        threading.Thread(target=self._run, args=(text, cid), daemon=True, name="fidus-ask").start()
        return {"started": True, "character": cid}

    def _run(self, text: str, cid: str) -> None:
        emit = self.events.emit
        try:
            emit("character", **self.persona.ui_profile(cid))
            emit("state", state="listening", mic="recording")
            emit("caption", role="user", text=text, final=True)
            emit("state", state="thinking", mic="paused")
            speaking = False

            def on_text(chunk: str) -> None:
                nonlocal speaking
                if not speaking:
                    speaking = True
                    emit("state", state="speaking", mic="paused")
                emit("caption", role="assistant", text=chunk, final=False)

            self.orchestrator.run(text, on_text=on_text, personagem_ativo=cid)
            emit("caption", role="assistant", text="", final=True)
        except Exception as e:  # o erro aparece na tela em vez de derrubar o núcleo
            emit("error", message=f"{type(e).__name__}: {e}")
        finally:
            emit("state", state="idle", mic="passive")
            self._busy.release()

    # ---- o que a interface controla ----

    def set_muted(self, value: bool) -> None:
        self.events.emit("state", state="muted" if value else "idle", mic="muted" if value else "passive")

    def set_calls_enabled(self, value: bool) -> None:
        self.events.emit("calls", enabled=value, until=None)

    def pause_calls(self, minutes: float) -> None:
        self.events.emit("calls", enabled=not minutes, until=None)

    def request_stop(self) -> None:
        self._stop.set()
