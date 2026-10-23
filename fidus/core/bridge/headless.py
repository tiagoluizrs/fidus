"""Núcleo REAL sem áudio (`fidus daemon --headless`): o mesmo modelo, ferramentas, permissões e configurações,
mas os pedidos chegam por TEXTO (comando `ask`) ou pela fala captada no microfone do NAVEGADOR (`ask_audio`), e a resposta
volta como legendas.

Serve para testar tudo no Docker/navegador, onde não há microfone nem voz do Windows.
"""

from __future__ import annotations

import base64
import binascii
import queue
import re
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from ..assistant import build_assistant
from ..config import Config
from ..voice.wake_text import match_wake  # noqa: F401 - também usado pelos testes por este caminho
from .confirm import ConfirmBroker


_SENTENCE_END = re.compile(r"(?<=[.!?…])[*_\"')\]]*\s+|\n+")  # fim de frase, mesmo com **negrito** ou aspas logo depois


def clean_for_speech(text: str) -> str:
    """Tira o que não se fala: marcas de Markdown, links e emojis."""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>~]+", "", text)
    text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class SentenceSpeaker:
    """Divide a resposta em frases, sintetiza cada uma em segundo plano e manda o áudio para o navegador, na ordem."""

    def __init__(self, synth: Callable[[str], bytes | None], emit: Callable[..., None]):
        self.synth, self.emit = synth, emit
        self.buf = ""
        self.seq = 0
        self.q: queue.Queue[str | None] = queue.Queue()
        self.thread = threading.Thread(target=self._work, daemon=True, name="fidus-speaker")
        self.thread.start()

    def feed(self, chunk: str) -> None:
        self.buf += chunk
        *done, self.buf = _SENTENCE_END.split(self.buf)
        for sentence in done:
            self._enqueue(sentence)

    def finish(self) -> None:
        self._enqueue(self.buf)
        self.buf = ""
        self.q.put(None)

    def _enqueue(self, sentence: str) -> None:
        sentence = clean_for_speech(sentence)
        if sentence:
            self.q.put(sentence)

    def _work(self) -> None:
        while (sentence := self.q.get()) is not None:
            try:
                wav = self.synth(sentence)
            except Exception as e:  # uma frase que falha não derruba a conversa: a legenda continua na tela
                self.emit("error", message=f"Não consegui gerar a voz ({type(e).__name__}: {e}).")
                continue
            if wav:
                self.seq += 1
                self.emit("speak_audio", seq=self.seq, text=sentence, wav=base64.b64encode(wav).decode())


class HeadlessLoop:
    """Faz o papel do ListenLoop para os comandos da interface (silenciar, chamados, confirmação) sem usar áudio."""

    MAX_AUDIO_S = 20  # o limite de 1 MB por mensagem do canal local comporta cerca de 25 s; 20 s deixa folga
    SAMPLE_RATE = 16_000

    def __init__(self, config: Config, events, state, provider=None):
        self.config, self.events, self.state = config, events, state
        self.broker = ConfirmBroker(events)
        confirm = lambda prompt: self.broker.run(prompt, self.broker.wait_ui)  # noqa: E731 - sem voz: só o clique na tela vale
        self.orchestrator, self.persona, _ = build_assistant(config, confirm, provider=provider)
        self.handler = SimpleNamespace(orchestrator=self.orchestrator)  # onde o `_apply_runtime` procura o provedor
        self.manager = self.tts = self.speaker = None  # sem microfone nem voz
        self.headless = True  # a interface mostra links (login do Google) em vez de o núcleo abrir o navegador
        self.mic_on = False  # o microfone é o do navegador: ele avisa quando liga (`browser_mic`)
        state.mic = "off"
        self.transcriber = None  # Whisper, criado só na primeira fala (baixa e carrega o modelo)
        self._tts = None  # motor de voz (Piper/ElevenLabs), criado só quando um personagem usa
        self._followup_until = 0.0  # depois de uma resposta, aceita uma continuação sem chamar o nome de novo
        self._busy = threading.Lock()
        self._stop = threading.Event()

    # ---- voz do personagem (Piper ou nuvem), tocada pelo navegador ----

    def _server_voice(self, cid: str):
        """O motor de voz do personagem, se ele puder falar aqui (Piper instalado ou voz da nuvem com chave). Senão None."""
        from .. import secrets as vault
        from ..voice.piper_setup import PiperStore
        from ..voice.tts import TTSManager

        voice = self.persona.profile(cid).voice
        if voice.engine == "piper":
            store = PiperStore(self.config.data_dir / "piper")
            if not store.exe.is_file() or store.model_path(voice.voice) is None:
                return None
        elif voice.engine == "kokoro":
            from ..voice.kokoro_setup import KokoroStore

            if not KokoroStore(self.config.data_dir / "kokoro").installed():
                return None
        elif voice.engine in ("descricao", "propria"):
            if not voice.voice or not vault.get_secret(vault.ELEVENLABS_KEY):
                return None
        else:
            return None  # voz do sistema (SAPI) só existe no Windows: o navegador usa a dele
        if self._tts is None:
            self._tts = TTSManager(self.config.voice.speech_rate, data_dir=self.config.data_dir)
        self._tts.use(voice)
        return self._tts

    def _synth(self, tts) -> Callable[[str], bytes | None]:
        def run(text: str) -> bytes | None:
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "fala.wav"
                return path.read_bytes() if tts.synthesize(text, path) and path.is_file() else None

        return run

    def speaker_for(self, cid: str) -> SentenceSpeaker | None:
        """Avisa o navegador de quem vai falar (servidor ou a voz dele) e devolve o locutor, se for o servidor."""
        try:
            tts = self._server_voice(cid)
        except Exception as e:
            self.events.emit("error", message=f"Voz do personagem indisponível ({type(e).__name__}: {e}). Usando a voz do navegador.")
            tts = None
        self.events.emit("voice_mode", mode="server" if tts else "browser", engine=self.persona.profile(cid).voice.engine)
        return SentenceSpeaker(self._synth(tts), self.events.emit) if tts else None

    def preview_voice(self, cid: str, text: str) -> dict:
        """"Ouvir amostra" da tela de voz: fala uma frase com a voz do personagem pelo navegador."""
        speaker = self.speaker_for(cid)
        if speaker is None:
            return {"spoken": False, "reason": "Esta voz só toca no Windows (voz do sistema). Escolha Piper ou uma voz da nuvem para ouvir aqui."}
        speaker.feed(text)
        speaker.finish()
        return {"spoken": True, "text": text}

    def _idle_mic(self) -> str:
        return "passive" if self.mic_on else "off"

    def set_browser_mic(self, on: bool) -> None:
        self.mic_on = bool(on)
        if self._busy.acquire(blocking=False):  # só mexe no anel se nada está acontecendo
            try:
                self.events.emit("state", state="idle", mic=self._idle_mic())
            finally:
                self._busy.release()

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

    # ---- fala captada pelo navegador ----

    def ask_audio(self, pcm_b64: str, character: str | None = None, wake: bool = False) -> dict:
        """Fala do microfone do NAVEGADOR (PCM 16 bits, mono, 16 kHz, base64), transcrita pelo Whisper local.

        `wake=True` é o microfone sempre ligado: só age se a fala começar chamando um personagem ("ei Alfred...") ou se
        for a continuação de uma conversa em andamento; qualquer outra coisa é ignorada, como no app instalado.
        """
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
            if wake:
                return {"ignored": "ocupado"}  # microfone aberto: falas durante a resposta são descartadas em silêncio
            raise ValueError("Ainda estou respondendo ao pedido anterior.")
        cid = self.persona.resolve_id(character or self.state.character_id)
        threading.Thread(target=self._run_audio, args=(audio.astype(np.float32) / 32768.0, cid, wake), daemon=True, name="fidus-ask-audio").start()
        return {"started": True, "character": cid}

    def _names(self) -> dict[str, str]:
        return {cid: self.persona.ui_profile(cid)["name"] for cid in self.persona.ids()}

    def _run_audio(self, audio, cid: str, wake: bool) -> None:
        emit = self.events.emit
        try:
            if not wake:
                emit("character", **self.persona.ui_profile(cid))
                emit("state", state="thinking", mic="paused")
                emit("caption", role="user", text="Transcrevendo…", final=False)
            if self.transcriber is None:
                from ..voice.stt import Transcriber

                self.transcriber = Transcriber(self.config)
            text = self.transcriber.transcribe(audio).strip()
        except Exception as e:
            emit("error", message=f"Não consegui transcrever o áudio ({type(e).__name__}: {e}).")
            emit("state", state="idle", mic=self._idle_mic())
            self._busy.release()
            return
        if wake:
            target, rest = match_wake(text, self._names())
            if target is None and time.monotonic() > self._followup_until:
                emit("state", state="idle", mic=self._idle_mic())  # não era comigo: segue escutando, sem alarde
                self._busy.release()
                return
            if target:
                cid, text = target, rest
            emit("character", **self.persona.ui_profile(cid))
            if not text:  # só chamou ("ei Alfred"): responde com a fala de início e espera o pedido
                self._acknowledge(cid)
                return
        if not text:
            emit("caption", role="user", text="", final=True)
            emit("error", message="Não entendi o áudio. Fale mais perto do microfone e tente de novo.")
            emit("state", state="idle", mic=self._idle_mic())
            self._busy.release()
            return
        self._run(text, cid, announce_listening=False)

    def _acknowledge(self, cid: str) -> None:
        emit = self.events.emit
        line = self.persona.phrase(cid, "inicio") or "Pode falar."
        voice = self.speaker_for(cid)
        if voice:
            voice.feed(line)
            voice.finish()
        emit("state", state="speaking", mic="paused")
        emit("caption", role="user", text="", final=True)
        emit("caption", role="assistant", text=line, final=False)
        emit("caption", role="assistant", text="", final=True)
        self._followup_until = time.monotonic() + max(self.config.wake.wait_speech_s, 8.0)
        emit("state", state="idle", mic=self._idle_mic())
        self._busy.release()

    def _run(self, text: str, cid: str, announce_listening: bool = True) -> None:
        emit = self.events.emit
        try:
            emit("character", **self.persona.ui_profile(cid))
            if announce_listening:
                emit("state", state="listening", mic=self._idle_mic())
            emit("caption", role="user", text=text, final=True)
            emit("state", state="thinking", mic="paused")
            speaking = False
            voice = self.speaker_for(cid)

            def on_text(chunk: str) -> None:
                nonlocal speaking
                if not speaking:
                    speaking = True
                    emit("state", state="speaking", mic="paused")
                emit("caption", role="assistant", text=chunk, final=False)
                if voice:
                    voice.feed(chunk)

            try:
                self.orchestrator.run(text, on_text=on_text, personagem_ativo=cid)
            finally:
                if voice:
                    voice.finish()
            emit("caption", role="assistant", text="", final=True)
        except Exception as e:  # o erro aparece na tela em vez de derrubar o núcleo
            emit("error", message=f"{type(e).__name__}: {e}")
        finally:
            self._followup_until = time.monotonic() + max(self.config.wake.followup_s, 6.0)
            emit("state", state="idle", mic=self._idle_mic())
            self._busy.release()

    # ---- o que a interface controla ----

    def set_muted(self, value: bool) -> None:
        self.events.emit("state", state="muted" if value else "idle", mic="muted" if value else self._idle_mic())

    def set_calls_enabled(self, value: bool) -> None:
        self.events.emit("calls", enabled=value, until=None)

    def pause_calls(self, minutes: float) -> None:
        self.events.emit("calls", enabled=not minutes, until=None)

    def request_stop(self) -> None:
        self._stop.set()
