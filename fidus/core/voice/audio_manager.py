"""Gerenciador único de áudio: UM fluxo de microfone, compartilhado pelo detector e pelas gravações.

- Buffer circular de ~2 s (pré-roll) só em memória.
- Nada daqui grava em disco ou usa a rede. O áudio só sai do gerenciador quando alguém abre uma `Capture`
  (chamado detectado, atalho segurado ou resposta de confirmação).
- Estados: "passive" (escuta passiva), "recording", "paused" (detector pausado), "muted" (microfone fechado), "off".
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from collections.abc import Callable

import numpy as np

SAMPLE_RATE = 16_000
BLOCK = 1280  # 80 ms: o tamanho de frame do openWakeWord


class Capture:
    """Gravação em andamento: recebe o pré-roll e depois cada bloco novo, em `queue`."""

    def __init__(self, manager: AudioManager, preroll: list[np.ndarray]):
        self._manager = manager
        self.queue: queue.Queue[np.ndarray] = queue.Queue()
        for b in preroll:
            self.queue.put(b)
        self.closed = False

    def drain(self) -> np.ndarray:
        """Tudo o que chegou até agora (int16), esvaziando a fila."""
        blocks = []
        while True:
            try:
                blocks.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.int16)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._manager._close_capture(self)


def to_float32(audio: np.ndarray) -> np.ndarray:
    """int16 -> float32 em [-1, 1], o formato que o Whisper espera."""
    return audio.astype(np.float32) / 32768.0


class AudioManager:
    def __init__(
        self,
        device: int | None = None,
        ring_s: float = 2.0,
        stream_factory: Callable[[Callable], object] | None = None,
        on_state: Callable[[str], None] | None = None,
    ):
        self.device = device
        self._ring: deque[np.ndarray] = deque(maxlen=max(1, round(ring_s * SAMPLE_RATE / BLOCK)))
        self._stream_factory = stream_factory or self._sounddevice_stream
        self._stream = None
        self._subscribers: list[Callable[[np.ndarray], None]] = []
        self._captures: list[Capture] = []
        self._lock = threading.Lock()
        self._detection_paused = False
        self._muted = False
        self._on_state = on_state
        self._last_state = "off"
        self.on_level: Callable[[list[float]], None] | None = None  # nível de áudio para a interface
        self.level_enabled: Callable[[], bool] = lambda: True  # só calcula se alguém está olhando

    # ---- fluxo ----

    def _sounddevice_stream(self, callback):
        import sounddevice as sd  # import preguiçoso

        return sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=BLOCK, device=self.device,
            callback=lambda indata, frames, t, status: callback(indata[:, 0].copy()),
        )

    def start(self) -> None:
        """Abre o microfone (a menos que esteja silenciado)."""
        if self._muted or self._stream is not None:
            return
        self._stream = self._stream_factory(self.feed)
        self._stream.start()
        self._notify()

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        with self._lock:
            self._ring.clear()
        self._notify()

    def feed(self, block: np.ndarray) -> None:
        """Entrada de um bloco do microfone. Chamado pelo fluxo de áudio (e pelos testes)."""
        with self._lock:
            if self._muted:
                return
            self._ring.append(block)
            captures = list(self._captures)
            subs = [] if self._detection_paused else list(self._subscribers)
        if self.on_level is not None and self.level_enabled():
            from .levels import block_levels

            self.on_level(block_levels(block))
        for c in captures:
            c.queue.put(block)
        for cb in subs:
            cb(block)

    # ---- assinantes (detector) ----

    def subscribe(self, callback: Callable[[np.ndarray], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def pause_detection(self) -> None:
        with self._lock:
            self._detection_paused = True
        self._notify()

    def resume_detection(self) -> None:
        with self._lock:
            self._detection_paused = False
        self._notify()

    # ---- gravação ----

    def open_capture(self, preroll_s: float = 0.0) -> Capture:
        n = round(preroll_s * SAMPLE_RATE / BLOCK)
        with self._lock:
            blocks = list(self._ring)[-n:] if n > 0 else []
            cap = Capture(self, blocks)
            self._captures.append(cap)
        self._notify()
        return cap

    def _close_capture(self, cap: Capture) -> None:
        with self._lock:
            if cap in self._captures:
                self._captures.remove(cap)
        self._notify()

    # ---- silenciar ----

    @property
    def muted(self) -> bool:
        return self._muted

    def mute(self) -> None:
        """Fecha o microfone de verdade: nada é capturado, nem para o detector nem para o atalho."""
        self._muted = True
        self.stop()
        with self._lock:
            for c in self._captures:
                c.closed = True
            self._captures.clear()
        self._notify()

    def unmute(self) -> None:
        self._muted = False
        self.start()
        self._notify()

    # ---- estado ----

    @property
    def state(self) -> str:
        if self._muted:
            return "muted"
        if self._stream is None:
            return "off"
        if self._captures:
            return "recording"
        return "paused" if self._detection_paused else "passive"

    def _notify(self) -> None:
        state = self.state
        if self._on_state and state != self._last_state:
            self._last_state = state
            self._on_state(state)
