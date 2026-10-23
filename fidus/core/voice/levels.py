"""Nível de áudio para a interface (anel reagindo à voz): 3 valores de 0 a 1 por bloco de 80 ms (~37 por segundo)."""

from __future__ import annotations

import numpy as np

SUBBLOCKS = 3


def block_levels(block: np.ndarray) -> list[float]:
    """RMS de cada terço do bloco int16, comprimido (raiz) para a voz normal já mexer bem no anel."""
    x = block.astype(np.float32) / 32768.0
    out = []
    for part in np.array_split(x, SUBBLOCKS):
        rms = float(np.sqrt(np.mean(part * part))) if len(part) else 0.0
        out.append(round(min(1.0, (rms / 0.12) ** 0.6), 3))
    return out
