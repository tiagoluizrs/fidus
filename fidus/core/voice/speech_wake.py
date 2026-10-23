"""Chamado por reconhecimento de fala: funciona SEM modelos de palavra de ativação treinados.

O Fidus detecta quando alguém fala (VAD), transcreve a fala com o Whisper local e só acorda se ela COMEÇAR chamando um
personagem ("ei Alfred, ..."). Tudo o mais é descartado na hora, sem guardar. Gasta mais CPU que um modelo dedicado, mas
não exige treino: é o padrão enquanto você não tiver os modelos (veja docs/WAKEWORDS.md).
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Callable

import numpy as np

from ..config import WakeWord
from .audio_manager import BLOCK, SAMPLE_RATE
from .wake_text import match_wake
from .wakeword import Activation

BLOCK_S = BLOCK / SAMPLE_RATE


class SpeechWakeRunner:
    """Mesma interface do DetectorRunner (start/stop/flush), mas com VAD + Whisper no lugar do detector de palavra."""

    def __init__(
        self,
        manager,
        vad,
        stt,
        names: Callable[[], dict[str, str]],
        words: dict[str, WakeWord],
        on_activation: Callable[[Activation], None],
        silence_s: float = 0.8,
        max_s: float = 12.0,
        min_speech_s: float = 0.5,
        preroll_s: float = 0.4,
        clock: Callable[[], float] = time.perf_counter,
        out: Callable[[str], None] = print,
    ):
        self.vad, self.stt, self.names, self.words = vad, stt, names, words
        self.on_activation, self.clock, self.out = on_activation, clock, out
        self.silence_s, self.max_s, self.min_speech_s = silence_s, max_s, min_speech_s
        self._pre: deque[np.ndarray] = deque(maxlen=max(1, round(preroll_s / BLOCK_S)))
        self._seg: list[np.ndarray] | None = None
        self._hits = 0
        self._quiet = 0
        self._q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=300)  # ~24 s de folga enquanto o Whisper trabalha
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True, name="fidus-speechwake")
        self.dropped = 0
        manager.subscribe(self._push)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._q.put(None)
        if self._thread.is_alive():
            self._thread.join(timeout=3)

    def flush(self) -> None:
        """Descarta o áudio pendente e a fala em andamento (ao voltar a escutar depois de uma conversa)."""
        with self._lock:
            try:
                while True:
                    self._q.get_nowait()
            except queue.Empty:
                pass
            self._reset()

    def _reset(self) -> None:
        self._seg, self._hits, self._quiet = None, 0, 0
        self._pre.clear()
        self.vad.reset()

    def _push(self, block: np.ndarray) -> None:  # chamado no fluxo de áudio: só enfileira
        try:
            self._q.put_nowait(block)
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        while (block := self._q.get()) is not None:
            try:
                self.process(block)
            except Exception as e:  # um erro de transcrição não derruba a escuta
                self.out(f"(chamado por fala: {type(e).__name__}: {e})")

    def process(self, block: np.ndarray) -> None:
        """Máquina de estados: espera a fala começar, junta os blocos até o silêncio e então confere se é um chamado."""
        with self._lock:
            speech = self.vad.is_speech(block)
            if self._seg is None:
                self._pre.append(block)
                self._hits = self._hits + 1 if speech else 0
                if self._hits >= 2:  # duas fatias seguidas de fala: começou (o início da frase vem do pré-roll)
                    self._seg, self._quiet = list(self._pre), 0
                return
            self._seg.append(block)
            self._quiet = 0 if speech else self._quiet + 1
            if self._quiet * BLOCK_S < self.silence_s and len(self._seg) * BLOCK_S < self.max_s:
                return
            seg, quiet = self._seg, self._quiet
            self._seg, self._hits, self._quiet = None, 0, 0
            self._pre.clear()
        self._finish(seg, quiet)

    def _finish(self, seg: list[np.ndarray], quiet: int) -> None:
        if (len(seg) - quiet) * BLOCK_S < self.min_speech_s:
            return  # barulho curto (porta, tosse): nem chega ao Whisper
        text = self.stt.transcribe(np.concatenate(seg).astype(np.float32) / 32768.0)
        cid, rest = match_wake(text, self.names())
        if cid is None:
            return  # não era comigo: nada é guardado nem registrado
        word = self.words.get(cid) or WakeWord(f"voz_{cid}", "", cid)
        self.out(f"Chamado por fala: {cid}" + (f" -> “{rest}”" if rest else ""))
        self.on_activation(Activation(word, 1.0, self.clock(), text=rest or None))
