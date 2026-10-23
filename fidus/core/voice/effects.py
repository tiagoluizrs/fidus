"""Efeitos de voz aplicados em cima do WAV gerado (só numpy). Hoje: `robo` (voz sintética metálica, estilo assistente de IA)."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

EFFECTS = ("", "robo")


def robotize(x: np.ndarray, sr: int) -> np.ndarray:
    """Modulação em anel suave (zumbido grave) + eco curtíssimo (timbre metálico). `x` em float32, -1..1."""
    t = np.arange(len(x)) / sr
    y = 0.62 * x + 0.38 * x * np.sin(2 * np.pi * 62 * t)
    d = max(1, int(0.0045 * sr))
    out = y.copy()
    out[d:] += 0.5 * y[:-d]
    out[2 * d:] += 0.25 * y[:-2 * d]
    peak = float(np.abs(out).max()) or 1.0
    return (out / peak * 0.92).astype(np.float32)


def apply_pronunciations(text: str, spec: str) -> str:
    """Troca palavras pelo jeito que o motor deve lê-las. `spec`: "Alfred=Al fred; Donna=Dona" (só a fala, não o texto da tela)."""
    import re

    for pair in spec.replace("\n", ";").split(";"):
        word, sep, say = pair.partition("=")
        word, say = word.strip(), say.strip()
        if sep and word:
            text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", say, text, flags=re.IGNORECASE)
    return text


def shape(x: np.ndarray, sr: int, timbre: int = 0, edge: int = 0) -> np.ndarray:
    """Dá forma ao timbre sem mudar o tom nem a velocidade (filtro no espectro).

    `timbre` -10..10: do fechado (abafado, sem brilho) ao aberto (claro, com ar).
    `edge` -10..10: do macio ao "pontudo" (presença cortante nos médios-agudos, em torno de 3 kHz, sem ficar agudo)."""
    if not timbre and not edge:
        return x
    spec = np.fft.rfft(x)
    f = np.maximum(np.fft.rfftfreq(len(x), 1 / sr), 60.0)
    octaves = np.log2(f / 1000.0)
    db = np.clip(timbre * 1.1 * octaves, -14, 14) + edge * 1.2 * np.exp(-((np.log2(f / 3000.0)) ** 2) / (2 * 0.6**2))
    y = np.fft.irfft(spec * 10 ** (db / 20), n=len(x)).astype(np.float32)
    peak = float(np.abs(y).max()) or 1.0
    return y * min(1.0, 0.92 / peak)


def shape_file(path: Path, timbre: int, edge: int) -> None:
    """Aplica `shape` num WAV (16 bits, mono). Sem ajuste, não mexe no arquivo."""
    if not timbre and not edge:
        return
    with wave.open(str(path), "rb") as w:
        sr, ch, raw = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    y = shape(x, sr, timbre, edge)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def set_pitch(path: Path, factor: float) -> None:
    """Muda o tom só trocando a taxa de amostragem do cabeçalho (sem tocar nas amostras). 1.0 não faz nada."""
    if abs(factor - 1.0) < 0.001:
        return
    with wave.open(str(path), "rb") as w:
        params, raw = w.getparams(), w.readframes(w.getnframes())
    with wave.open(str(path), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(int(params.framerate * factor))
        w.writeframes(raw)


def apply_effect(path: Path, effect: str) -> None:
    """Regrava o WAV (16 bits, mono) com o efeito. Efeito vazio ou desconhecido não mexe em nada."""
    if effect != "robo":
        return
    with wave.open(str(path), "rb") as w:
        sr, ch, raw = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    y = robotize(x, sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
