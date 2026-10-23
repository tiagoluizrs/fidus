"""Fala. `TTSProvider` é a interface; SAPI (voz do Windows) é a primeira implementação, Piper virá depois."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Protocol


class TTSProvider(Protocol):
    on_start: Callable[[], None] | None  # chamado quando uma fala começa a sair

    def speak(self, text: str) -> None:
        """Enfileira uma frase e volta na hora (não espera falar)."""

    def wait_idle(self, timeout: float | None = None) -> None:
        """Bloqueia até a fila esvaziar e a fala terminar."""

    def stop(self) -> None:
        """Interrompe a fala atual e descarta a fila."""

    def close(self) -> None: ...


_PT_BR_LCID = "416"  # 0x416 = pt-BR


class SapiTTS:
    """SAPI via pywin32. Um thread próprio é dono do objeto COM (COM exige usar no thread que o criou)."""

    def __init__(self, rate: int = 0):
        self.rate = rate
        self.on_start: Callable[[], None] | None = None
        self.voice_name = ""
        self._q: queue.Queue[tuple[int, str] | None] = queue.Queue()
        self._lock = threading.Lock()
        self._gen = 0  # sobe a cada stop(): frases de gerações antigas são descartadas
        self._pending = 0  # frases enfileiradas ou falando
        self._idle = threading.Event()
        self._idle.set()
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._worker, daemon=True, name="fidus-tts")
        self._thread.start()
        self._ready.wait()
        if self._error:
            raise RuntimeError(f"Não foi possível iniciar a voz do sistema (SAPI): {self._error}")

    def _worker(self) -> None:
        try:
            import pythoncom
            import win32com.client  # só existe no Windows

            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Rate = self.rate
            self._pick_pt_br(voice)
        except Exception as e:
            self._error = e
            self._ready.set()
            return
        self._ready.set()
        while (item := self._q.get()) is not None:
            gen, text = item
            if gen == self._gen:
                if self.on_start:
                    self.on_start()
                voice.Speak(text, 1)  # 1 = assíncrono: dá para interromper
                while not voice.WaitUntilDone(50):
                    if gen != self._gen:
                        voice.Speak("", 3)  # assíncrono + descarta o que estiver falando
                        break
            self._done(1)

    def _done(self, n: int) -> None:
        with self._lock:
            self._pending = max(0, self._pending - n)
            if self._pending == 0:
                self._idle.set()

    def _pick_pt_br(self, voice) -> None:
        voices = voice.GetVoices()
        for i in range(voices.Count):
            v = voices.Item(i)
            if _PT_BR_LCID in str(v.GetAttribute("Language")).lower():
                voice.Voice = v
                self.voice_name = v.GetDescription()
                return
        self.voice_name = voice.Voice.GetDescription() + " (sem voz pt-BR instalada)"

    def speak(self, text: str) -> None:
        if text.strip():
            with self._lock:
                self._pending += 1
                self._idle.clear()
                self._q.put((self._gen, text))

    def wait_idle(self, timeout: float | None = None) -> None:
        self._idle.wait(timeout)

    def stop(self) -> None:
        with self._lock:
            self._gen += 1  # a frase atual e as da fila ficam obsoletas

    def close(self) -> None:
        self.stop()
        self._q.put(None)
        self._thread.join(timeout=2)


def create_tts(rate: int = 0) -> TTSProvider:
    import sys

    if sys.platform != "win32":
        raise RuntimeError("A voz do sistema (SAPI) só existe no Windows.")
    return SapiTTS(rate)
