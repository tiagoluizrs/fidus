"""Fala ou silêncio, para decidir quando a gravação termina."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .audio_manager import BLOCK, SAMPLE_RATE

BLOCK_S = BLOCK / SAMPLE_RATE


class EnergyVAD:
    """Plano B: volume do bloco. Mais sujeito a erro com barulho de fundo."""

    def __init__(self, threshold: float = 0.015):
        self.threshold = threshold

    def is_speech(self, block: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean((block.astype(np.float32) / 32768.0) ** 2)))
        return rms >= self.threshold

    def reset(self) -> None: ...


class SileroVAD:
    """VAD Silero que acompanha o openWakeWord (ONNX, local)."""

    def __init__(self, threshold: float = 0.5):
        from .oww import import_openwakeword

        import_openwakeword()
        from openwakeword.vad import VAD  # pesado: só aqui

        self.threshold = threshold
        self._vad = VAD()

    def is_speech(self, block: np.ndarray) -> bool:
        return float(self._vad.predict(block, frame_size=640)) >= self.threshold

    def reset(self) -> None:
        self._vad.reset_states()


def load_vad(threshold: float, out: Callable[[str], None] = print):
    try:
        return SileroVAD(threshold)
    except Exception as e:
        out(f"VAD Silero indisponível ({type(e).__name__}); usando detecção por volume.")
        return EnergyVAD()


class SilenceEndpointer:
    """Decide o fim da fala: silêncio depois de falar, tempo máximo, ou ninguém falou."""

    def __init__(self, silence_s: float = 1.2, max_s: float = 15.0, wait_speech_s: float = 5.0):
        self.silence_s, self.max_s, self.wait_speech_s = silence_s, max_s, wait_speech_s
        self.elapsed = 0.0
        self.heard_speech = False
        self._quiet = 0.0

    def feed(self, is_speech: bool, seconds: float = BLOCK_S) -> str | None:
        """None = continua; senão o motivo: 'silencio', 'maximo' ou 'sem_fala'."""
        self.elapsed += seconds
        if is_speech:
            self.heard_speech, self._quiet = True, 0.0
        elif self.heard_speech:
            self._quiet += seconds
        if self.elapsed >= self.max_s:
            return "maximo"
        if self.heard_speech and self._quiet >= self.silence_s:
            return "silencio"
        if not self.heard_speech and self.elapsed >= self.wait_speech_s:
            return "sem_fala"
        return None


def capture_utterance(capture, vad, endpointer: SilenceEndpointer, should_abort: Callable[[], bool] = lambda: False):
    """Lê blocos da `Capture` até o fim da fala. Devolve (áudio int16 | None, motivo)."""
    import queue

    vad.reset()
    blocks: list[np.ndarray] = []
    while True:
        if should_abort() or capture.closed:
            return None, "abortado"
        try:
            block = capture.queue.get(timeout=0.2)
        except queue.Empty:
            continue
        blocks.append(block)
        reason = endpointer.feed(vad.is_speech(block))
        if reason:
            if reason == "sem_fala":
                return None, reason
            return np.concatenate(blocks), reason
