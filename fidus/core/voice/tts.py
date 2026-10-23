"""Fala. `TTSProvider` é a interface; SAPI (voz do Windows) é o padrão, Piper (local) é opcional.

Um thread por provedor é dono do motor de voz (o COM do SAPI exige isso) e processa uma fila em ordem.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from xml.sax.saxutils import escape

from ..characters.models import Voice


class TTSProvider(Protocol):
    on_start: Callable[[], None] | None  # chamado quando uma fala começa a sair
    voice_name: str

    def configure(self, voice: Voice, base_rate: int = 0) -> None:
        """Aplica voz, tom e velocidade (a do personagem somada à geral)."""

    def speak(self, text: str) -> None:
        """Enfileira uma frase e volta na hora (não espera falar)."""

    def speak_file(self, path: Path) -> None:
        """Enfileira um áudio já gravado (fala de início em cache)."""

    def synthesize(self, text: str, path: Path) -> bool:
        """Gera `text` em um arquivo WAV (para o cache). False se este motor não consegue."""

    def wait_idle(self, timeout: float | None = None) -> None: ...

    def stop(self) -> None:
        """Interrompe a fala atual e descarta a fila."""

    def close(self) -> None: ...


class CloudVoiceProvider(Protocol):
    """Ponto de extensão para "voz por descrição" em um serviço na nuvem. Só a interface: nenhum serviço
    é implementado. O texto da fala sairia do computador, então exigiria aviso e consentimento explícitos."""

    def synthesize(self, text: str, description: str) -> bytes:
        """Devolve áudio WAV da fala com a voz descrita (ex.: 'grave, calma, sotaque neutro')."""


def _clamp(v: int, lo: int = -10, hi: int = 10) -> int:
    return max(lo, min(hi, int(v)))


class QueuedTTS:
    """Fila, geração (para interromper) e controle de 'ocioso', comuns a todos os motores."""

    def __init__(self) -> None:
        self.on_start: Callable[[], None] | None = None
        self.voice_name = ""
        self._q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._gen = 0  # sobe a cada stop(): a frase atual e as da fila ficam obsoletas
        self._pending = 0
        self._idle = threading.Event()
        self._idle.set()
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._worker, daemon=True, name=f"fidus-tts-{type(self).__name__}")

    def _start(self) -> None:
        self._thread.start()
        self._ready.wait()
        if self._error:
            raise RuntimeError(f"Não foi possível iniciar a voz ({type(self).__name__}): {self._error}")

    # --- a implementar ---
    def _engine_init(self) -> None: ...
    def _say(self, text: str, cancelled: Callable[[], bool]) -> None: ...
    def _play(self, path: Path, cancelled: Callable[[], bool]) -> None: ...
    def _synth(self, text: str, path: Path) -> bool:
        return False

    def _configure(self, voice: Voice, base_rate: int) -> None: ...
    def _stop_playback(self) -> None: ...

    def _worker(self) -> None:
        try:
            self._engine_init()
        except Exception as e:
            self._error = e
            self._ready.set()
            return
        self._ready.set()
        while (item := self._q.get()) is not None:
            kind, gen, payload = item
            if kind == "call":  # configurar/sintetizar: roda no thread do motor e não é cancelado por stop()
                fn, box, evt = payload
                try:
                    box.append(fn())
                except Exception as e:
                    box.append(e)
                evt.set()
            elif gen == self._gen:
                if self.on_start:
                    self.on_start()
                (self._say if kind == "say" else self._play)(payload, lambda g=gen: g != self._gen)
            self._done()

    def _done(self) -> None:
        with self._lock:
            self._pending = max(0, self._pending - 1)
            if self._pending == 0:
                self._idle.set()

    def _put(self, kind: str, payload) -> None:
        with self._lock:
            self._pending += 1
            self._idle.clear()
            self._q.put((kind, self._gen, payload))

    def _call(self, fn):
        box: list = []
        evt = threading.Event()
        self._put("call", (fn, box, evt))
        evt.wait()
        if isinstance(box[0], Exception):
            raise box[0]
        return box[0]

    # --- API pública ---
    def configure(self, voice: Voice, base_rate: int = 0) -> None:
        self._call(lambda: self._configure(voice, base_rate))

    def speak(self, text: str) -> None:
        if text.strip():
            self._put("say", text)

    def speak_file(self, path: Path) -> None:
        self._put("file", Path(path))

    def synthesize(self, text: str, path: Path) -> bool:
        return bool(self._call(lambda: self._synth(text, Path(path))))

    def wait_idle(self, timeout: float | None = None) -> None:
        self._idle.wait(timeout)

    def stop(self) -> None:
        with self._lock:
            self._gen += 1
        self._stop_playback()

    def close(self) -> None:
        self.stop()
        self._q.put(None)
        self._thread.join(timeout=2)


_PT_BR_LCID = "416"  # 0x416 = pt-BR


class SapiTTS(QueuedTTS):
    """SAPI via pywin32."""

    def __init__(self, rate: int = 0):
        super().__init__()
        self.rate, self.pitch = rate, 0
        self._voice = None
        self._start()

    def _engine_init(self) -> None:
        import pythoncom
        import win32com.client  # só existe no Windows

        pythoncom.CoInitialize()
        self._client = win32com.client
        self._voice = self._client.Dispatch("SAPI.SpVoice")
        self._voice.Rate = self.rate
        self._select_voice("")

    def _select_voice(self, wanted: str) -> None:
        voices = self._voice.GetVoices()
        for i in range(voices.Count):
            v = voices.Item(i)
            name = str(v.GetDescription())
            hit = wanted.lower() in name.lower() if wanted else _PT_BR_LCID in str(v.GetAttribute("Language")).lower()
            if hit:
                self._voice.Voice = v
                self.voice_name = name
                return
        self.voice_name = self._voice.Voice.GetDescription() + (f" (voz '{wanted}' não encontrada)" if wanted else " (sem voz pt-BR instalada)")

    def _configure(self, voice: Voice, base_rate: int) -> None:
        self._voice.Rate = _clamp(base_rate + voice.rate)
        self.pitch = _clamp(voice.pitch)
        self._select_voice(voice.voice)

    def _markup(self, text: str) -> tuple[str, int]:
        if self.pitch:
            return f'<pitch absmiddle="{self.pitch}">{escape(text)}</pitch>', 8  # 8 = o texto é XML
        return text, 0

    def _say(self, text: str, cancelled: Callable[[], bool]) -> None:
        markup, xml = self._markup(text)
        self._voice.Speak(markup, 1 | xml)  # 1 = assíncrono: dá para interromper
        while not self._voice.WaitUntilDone(50):
            if cancelled():
                self._voice.Speak("", 3)  # assíncrono + descarta o que estiver falando
                break

    def _play(self, path: Path, cancelled: Callable[[], bool]) -> None:
        play_wav(path, cancelled)

    def _synth(self, text: str, path: Path) -> bool:
        stream = self._client.Dispatch("SAPI.SpFileStream")
        stream.Format.Type = 22  # 22 kHz, 16 bits, mono
        stream.Open(str(path), 3)  # 3 = criar para escrita
        previous = self._voice.AudioOutputStream
        self._voice.AudioOutputStream = stream
        try:
            markup, xml = self._markup(text)
            self._voice.Speak(markup, xml)  # síncrono
        finally:
            stream.Close()
            self._voice.AudioOutputStream = previous
        return True

    def _stop_playback(self) -> None:
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


class PiperTTS(QueuedTTS):
    """Piper local (opcional): chama o executável `piper` com um modelo .onnx e toca o WAV gerado.
    Não é instalado por padrão. Instale o Piper e aponte `voz.voice` do personagem para o modelo."""

    def __init__(self, executable: str = "piper", runner: Callable = subprocess.run, player: Callable | None = None, tmp_dir: Path | None = None):
        super().__init__()
        self.executable, self.runner, self.player = executable, runner, player or play_wav
        self.model, self.length_scale = "", 1.0
        self._tmp = Path(tmp_dir) if tmp_dir else Path(tempfile.gettempdir())
        self._start()

    def _configure(self, voice: Voice, base_rate: int) -> None:
        if voice.voice:
            self.model = voice.voice
            self.voice_name = Path(voice.voice).stem
        self.length_scale = round(1.0 - _clamp(base_rate + voice.rate) * 0.05, 3)  # +10 = 2x mais rápido

    def _run_piper(self, text: str, out: Path) -> None:
        if not self.model:
            raise RuntimeError("Piper sem modelo: defina o caminho do .onnx em voz.voice do personagem.")
        self.runner(
            [self.executable, "--model", self.model, "--output_file", str(out), "--length_scale", str(self.length_scale)],
            input=text.encode("utf-8"), check=True, capture_output=True,
        )

    def _say(self, text: str, cancelled: Callable[[], bool]) -> None:
        out = self._tmp / f"fidus-piper-{threading.get_ident()}.wav"
        try:
            self._run_piper(text, out)
            self.player(out, cancelled)
        finally:
            out.unlink(missing_ok=True)

    def _play(self, path: Path, cancelled: Callable[[], bool]) -> None:
        self.player(path, cancelled)

    def _synth(self, text: str, path: Path) -> bool:
        self._run_piper(text, path)
        return True


def play_wav(path: Path, cancelled: Callable[[], bool] = lambda: False) -> None:
    """Toca um WAV e espera acabar (ou ser cancelado)."""
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)  # síncrono; stop() chama SND_PURGE
        return
    import wave

    import numpy as np
    import sounddevice as sd

    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        sd.play(data, w.getframerate())
    while sd.get_stream().active and not cancelled():
        sd.sleep(30)
    sd.stop()


class TTSManager:
    """Um provedor por motor, criados só quando um personagem pede aquele motor. Trocar de personagem
    reconfigura voz, tom e velocidade; o resto do código fala com este objeto como com qualquer TTSProvider."""

    def __init__(self, base_rate: int = 0, factories: dict[str, Callable[[Voice], TTSProvider]] | None = None):
        self.base_rate = base_rate
        self.factories = factories or default_factories(base_rate)
        self._providers: dict[str, TTSProvider] = {}
        self.current: TTSProvider | None = None
        self.current_voice = Voice()
        self._on_start: Callable[[], None] | None = None

    def use(self, voice: Voice) -> None:
        engine = voice.engine
        if engine not in self._providers:
            if engine not in self.factories:
                raise RuntimeError(f"Motor de voz desconhecido: '{engine}'. Use sapi, piper ou descricao.")
            self._providers[engine] = self.factories[engine](voice)
        provider = self._providers[engine]
        if provider is not self.current and self.current is not None:
            self.current.stop()
        provider.configure(voice, self.base_rate)
        provider.on_start = self._on_start
        self.current, self.current_voice = provider, voice

    @property
    def on_start(self):
        return self._on_start

    @on_start.setter
    def on_start(self, fn) -> None:
        self._on_start = fn
        for p in self._providers.values():
            p.on_start = fn

    @property
    def voice_name(self) -> str:
        return self.current.voice_name if self.current else ""

    def _cur(self) -> TTSProvider:
        if self.current is None:
            self.use(Voice())
        return self.current  # type: ignore[return-value]

    def speak(self, text: str) -> None:
        self._cur().speak(text)

    def speak_file(self, path: Path) -> None:
        self._cur().speak_file(path)

    def synthesize(self, text: str, path: Path) -> bool:
        return self._cur().synthesize(text, path)

    def wait_idle(self, timeout: float | None = None) -> None:
        for p in self._providers.values():
            p.wait_idle(timeout)

    def stop(self) -> None:
        for p in self._providers.values():
            p.stop()

    def close(self) -> None:
        for p in self._providers.values():
            p.close()


def _sapi(voice: Voice) -> TTSProvider:
    if sys.platform != "win32":
        raise RuntimeError("A voz do sistema (SAPI) só existe no Windows.")
    return SapiTTS()


def _cloud(voice: Voice) -> TTSProvider:
    raise NotImplementedError(
        "Voz por descrição (nuvem) ainda não é implementada: existe só o ponto de extensão CloudVoiceProvider."
    )


def default_factories(base_rate: int = 0) -> dict[str, Callable[[Voice], TTSProvider]]:
    return {"sapi": _sapi, "piper": lambda v: PiperTTS(), "descricao": _cloud}


def create_tts(rate: int = 0) -> TTSProvider:
    """SAPI direto (usado por `fidus say`)."""
    if sys.platform != "win32":
        raise RuntimeError("A voz do sistema (SAPI) só existe no Windows.")
    return SapiTTS(rate)
