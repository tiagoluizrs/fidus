"""Captura de áudio (sounddevice, 16 kHz mono). O áudio fica só na memória."""

from __future__ import annotations

import threading
import time

SAMPLE_RATE = 16_000


def list_devices() -> list[dict]:
    """Dispositivos de entrada: índice, nome, canais e se é o padrão do sistema."""
    import sounddevice as sd

    default_in = sd.default.device[0]
    return [
        {"index": i, "name": d["name"], "channels": d["max_input_channels"], "default": i == default_in}
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def resolve_device(spec: str, devices: list[dict]) -> int | None:
    """'' -> padrão do sistema (None); '3' -> índice 3; 'Realtek' -> primeiro nome que contém o texto."""
    spec = spec.strip()
    if not spec:
        return None
    inputs = {d["index"] for d in devices}
    if spec.isdigit():
        if int(spec) not in inputs:
            raise ValueError(f"Dispositivo de entrada {spec} não existe. Rode `uv run fidus mics`.")
        return int(spec)
    for d in devices:
        if spec.lower() in d["name"].lower():
            return d["index"]
    raise ValueError(f"Nenhum microfone com '{spec}' no nome. Rode `uv run fidus mics`.")


class Recorder:
    """Grava do microfone enquanto start()..stop(). Abre o fluxo só durante a gravação."""

    def __init__(self, device: int | None = None, max_seconds: float = 30.0):
        self.device = device
        self.max_samples = int(max_seconds * SAMPLE_RATE)
        self._chunks: list = []
        self._samples = 0
        self._stream = None
        self._lock = threading.Lock()

    def start(self) -> None:
        import sounddevice as sd

        self._chunks, self._samples = [], 0
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.device, callback=self._on_block
        )
        self._stream.start()

    def _on_block(self, indata, frames, time_info, status) -> None:
        with self._lock:
            if self._samples < self.max_samples:
                self._chunks.append(indata[:, 0].copy())
                self._samples += frames

    def stop(self):
        """Para e devolve o áudio (float32, mono, 16 kHz). Vazio se não estava gravando."""
        import numpy as np

        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        with self._lock:
            chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")


class EnergyEndpointer:
    """Decide quando uma resposta curta (sim/não) terminou: fala detectada + silêncio depois."""

    def __init__(self, threshold: float = 0.015, silence_s: float = 0.8):
        self.threshold, self.silence_s = threshold, silence_s
        self.heard_speech = False
        self._quiet_for = 0.0

    def feed(self, rms: float, seconds: float) -> bool:
        """True quando acabou: já houve fala e o silêncio durou o suficiente."""
        if rms >= self.threshold:
            self.heard_speech, self._quiet_for = True, 0.0
        elif self.heard_speech:
            self._quiet_for += seconds
        return self.heard_speech and self._quiet_for >= self.silence_s


def record_until_silence(device: int | None, timeout_s: float):
    """Grava uma resposta curta. Devolve o áudio, ou None se ninguém falou dentro do tempo limite."""
    import numpy as np
    import sounddevice as sd

    block = int(SAMPLE_RATE * 0.1)
    end = EnergyEndpointer()
    chunks: list = []
    deadline = time.monotonic() + timeout_s
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=device, blocksize=block) as s:
        while time.monotonic() < deadline:
            data, _ = s.read(block)
            mono = data[:, 0].copy()
            chunks.append(mono)
            if end.feed(float(np.sqrt(np.mean(mono**2))), 0.1):
                break
    return np.concatenate(chunks) if end.heard_speech else None
