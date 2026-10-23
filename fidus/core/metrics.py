"""Medições de latência e memória. Ficam só no log local; nada é enviado."""

from __future__ import annotations

import time
from dataclasses import dataclass


def rss_mb() -> float:
    """Memória residente do processo, em MB."""
    import psutil

    return round(psutil.Process().memory_info().rss / 1024 / 1024, 1)


@dataclass
class Timings:
    """Marcas de tempo (time.perf_counter) de um pedido falado."""

    speech_end: float = 0.0  # soltou o atalho
    text_ready: float = 0.0  # transcrição pronta
    first_word: float = 0.0  # primeira palavra do modelo
    speech_start: float = 0.0  # a voz começou a falar

    def mark_first_word(self) -> None:
        if not self.first_word:
            self.first_word = time.perf_counter()

    def mark_speech_start(self) -> None:
        if not self.speech_start:
            self.speech_start = time.perf_counter()

    def as_log(self) -> dict:
        def gap(a: float, b: float) -> float | None:
            return round(b - a, 3) if a and b else None

        return {
            "a_fala_ate_texto_s": gap(self.speech_end, self.text_ready),
            "b_texto_ate_primeira_palavra_s": gap(self.text_ready, self.first_word),
            "c_fala_ate_inicio_da_voz_s": gap(self.speech_end, self.speech_start),
        }
