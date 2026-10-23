"""Transcrição local com faster-whisper. O modelo é carregado uma vez e mantido; o áudio nunca vai à rede."""

from __future__ import annotations

import time
import wave
from datetime import datetime

from ..actionlog import ActionLog
from ..config import Config
from ..metrics import rss_mb


class Transcriber:
    def __init__(self, config: Config, log: ActionLog | None = None):
        self.config = config
        self.log = log or ActionLog(config.log_path)
        self._model = None

    def load(self) -> None:
        """Carrega o modelo (idempotente) e registra tempo e memória antes/depois."""
        if self._model is not None:
            return
        from faster_whisper import WhisperModel  # pesado: só aqui

        v = self.config.voice
        before, t0 = rss_mb(), time.perf_counter()
        self._model = WhisperModel(v.whisper_model, device=v.device, compute_type=v.compute_type)
        self.log.event(
            "memoria_whisper",
            modelo=v.whisper_model,
            compute_type=v.compute_type,
            rss_antes_mb=before,
            rss_depois_mb=rss_mb(),
            carga_s=round(time.perf_counter() - t0, 2),
        )

    def transcribe(self, audio) -> str:
        """`audio`: array float32 mono 16 kHz, em memória."""
        self.load()
        v = self.config.voice
        if v.save_debug_audio:
            self._save_debug(audio)
        segments, _ = self._model.transcribe(
            audio,
            language=v.whisper_language,
            vad_filter=True,  # corta silêncio e evita "alucinação" em trechos sem fala
            vad_parameters={"min_silence_duration_ms": 500},
            beam_size=1,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def _save_debug(self, audio) -> None:
        import numpy as np

        d = self.config.debug_audio_dir
        d.mkdir(parents=True, exist_ok=True)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
        with wave.open(str(d / f"{datetime.now():%Y%m%d-%H%M%S-%f}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16_000)
            w.writeframes(pcm.tobytes())
