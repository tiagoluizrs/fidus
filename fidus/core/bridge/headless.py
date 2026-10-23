"""Núcleo REAL sem áudio (`fidus daemon --headless`): o mesmo modelo, ferramentas, permissões e configurações,
mas o pedido chega por texto (comando `ask`) em vez do microfone, e a resposta volta como legendas.

Serve para testar tudo no Docker/navegador, onde não há microfone nem voz do Windows.
"""

from __future__ import annotations

import base64
import binascii
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
        self.headless = True  # a interface mostra links (login do Google) em vez de o núcleo abrir o navegador
        state.mic = "off"  # sem microfone no núcleo: o navegador capta a voz e envia o áudio (`ask_audio`)
        self.transcriber = None  # Whisper, criado só na primeira fala (baixa e carrega o modelo)
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

    MAX_AUDIO_S = 20  # o limite de 1 MB por mensagem do canal local comporta cerca de 25 s; 20 s deixa folga
    SAMPLE_RATE = 16_000

    def ask_audio(self, pcm_b64: str, character: str | None = None) -> dict:
        """Fala captada pelo microfone do NAVEGADOR (PCM 16 bits, mono, 16 kHz, em base64): transcreve com o Whisper local."""
        import numpy as np

        try:
            raw = base64.b64decode(pcm_b64 or "", validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("Áudio inválido.") from e
        if len(raw) % 2:
            raise ValueError("Áudio inválido.")
        audio = np.frombuffer(raw, dtype=np.int16)
        if len(audio) < 0.4 * self.SAMPLE_RATE:
            raise ValueError("Áudio curto demais: segure o botão enquanto fala.")
        if len(audio) > self.MAX_AUDIO_S * self.SAMPLE_RATE:
            raise ValueError(f"Áudio longo demais (máximo {self.MAX_AUDIO_S} s).")
        if not self._busy.acquire(blocking=False):
            raise ValueError("Ainda estou respondendo ao pedido anterior.")
        cid = self.persona.resolve_id(character or self.state.character_id)
        threading.Thread(target=self._run_audio, args=(audio.astype(np.float32) / 32768.0, cid), daemon=True, name="fidus-ask-audio").start()
        return {"started": True, "character": cid}

    def _run_audio(self, audio, cid: str) -> None:
        emit = self.events.emit
        try:
            emit("character", **self.persona.ui_profile(cid))
            emit("state", state="thinking", mic="paused")
            emit("caption", role="user", text="Transcrevendo…", final=False)
            if self.transcriber is None:
                from ..voice.stt import Transcriber

                self.transcriber = Transcriber(self.config)
            text = self.transcriber.transcribe(audio).strip()
        except Exception as e:
            emit("error", message=f"Não consegui transcrever o áudio ({type(e).__name__}: {e}).")
            emit("state", state="idle", mic="off")
            self._busy.release()
            return
        if not text:
            emit("caption", role="user", text="", final=True)
            emit("error", message="Não entendi o áudio. Fale mais perto do microfone e tente de novo.")
            emit("state", state="idle", mic="off")
            self._busy.release()
            return
        self._run(text, cid, announce_listening=False)

    def _run(self, text: str, cid: str, announce_listening: bool = True) -> None:
        emit = self.events.emit
        try:
            emit("character", **self.persona.ui_profile(cid))
            if announce_listening:
                emit("state", state="listening", mic="off")
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
            emit("state", state="idle", mic="off")
            self._busy.release()

    # ---- o que a interface controla ----

    def set_muted(self, value: bool) -> None:
        self.events.emit("state", state="muted" if value else "idle", mic="muted" if value else "off")

    def set_calls_enabled(self, value: bool) -> None:
        self.events.emit("calls", enabled=value, until=None)

    def pause_calls(self, minutes: float) -> None:
        self.events.emit("calls", enabled=not minutes, until=None)

    def request_stop(self) -> None:
        self._stop.set()
