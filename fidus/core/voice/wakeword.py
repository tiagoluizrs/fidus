"""Detecção de palavra de ativação: interface, implementação com openWakeWord e a regra de ativação.

O detector só vê blocos de áudio de 80 ms em memória e devolve pontuações. Nada é gravado nem enviado.
A única rede é o download dos arquivos de modelo (não de áudio) na primeira vez de um modelo pronto.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from ..actionlog import ActionLog
from ..config import Config, WakeWord


@dataclass
class Activation:
    word: WakeWord
    score: float
    t: float  # time.perf_counter() do momento da detecção


class WakeWordDetector(Protocol):
    def predict(self, frame: np.ndarray) -> dict[str, float]:
        """Pontuação (0 a 1) de cada palavra para um bloco int16 de 80 ms. Chaves = `WakeWord.score_key`."""

    def reset(self) -> None:
        """Esquece o áudio recente (evita a mesma fala disparar duas vezes)."""


class ActivationGate:
    """Aplica o limiar de cada palavra e o intervalo mínimo entre ativações."""

    def __init__(self, words: list[WakeWord], cooldown_s: float, clock: Callable[[], float] = time.perf_counter):
        self.words, self.cooldown_s, self.clock = words, cooldown_s, clock
        self._last: float | None = None
        self.suppressed = 0  # ativações ignoradas por estarem dentro do intervalo

    def check(self, scores: dict[str, float], now: float | None = None) -> Activation | None:
        now = self.clock() if now is None else now
        best: tuple[float, WakeWord] | None = None
        for w in self.words:
            score = scores.get(w.score_key, 0.0)
            if score >= w.threshold and (best is None or score > best[0]):
                best = (score, w)
        if best is None:
            return None
        if self._last is not None and now - self._last < self.cooldown_s:
            self.suppressed += 1
            return None
        self._last = now
        return Activation(best[1], best[0], now)


class OpenWakeWordDetector:
    """Vários modelos ao mesmo tempo, com o runtime ONNX (o único disponível no Windows)."""

    def __init__(self, words: list[WakeWord], models_dir: Path, model_factory: Callable | None = None):
        self.words = words
        paths = [str(models_dir / w.model) if _is_file_model(w) else w.model for w in words]
        if model_factory is None:
            from .oww import import_openwakeword

            import_openwakeword()
            from openwakeword.model import Model  # pesado: só aqui

            model_factory = Model
        self._model = model_factory(wakeword_models=paths, inference_framework="onnx")

    def predict(self, frame: np.ndarray) -> dict[str, float]:
        return {k: float(v) for k, v in self._model.predict(frame).items()}

    def reset(self) -> None:
        self._model.reset()


def _is_file_model(w: WakeWord) -> bool:
    return Path(w.model).suffix.lower() in {".onnx", ".tflite"}


def ensure_resources(builtin_names: list[str], download: Callable | None = None) -> None:
    """Baixa, se faltarem, os modelos auxiliares do openWakeWord e os modelos prontos pedidos."""
    from .oww import import_openwakeword

    openwakeword = import_openwakeword()
    base = Path(openwakeword.__file__).parent / "resources" / "models"
    needed = ["melspectrogram.onnx", "embedding_model.onnx", "silero_vad.onnx"]
    needed += [f"{openwakeword.MODELS[n]['download_url'].split('/')[-1].replace('.tflite', '.onnx')}" for n in builtin_names if n in openwakeword.MODELS]
    if all((base / n).exists() for n in needed):
        return
    if download is None:
        from openwakeword.utils import download_models as download
    download(builtin_names)


def load_detector(
    config: Config,
    log: ActionLog,
    include_test: bool = False,
    out: Callable[[str], None] = print,
    model_factory: Callable | None = None,
    download: Callable | None = None,
) -> tuple[OpenWakeWordDetector | None, list[WakeWord]]:
    """Carrega as palavras ativas. Modelo ausente ou quebrado desativa só aquela palavra (avisa e registra)."""
    wake = config.wake
    wanted = [w for w in wake.words if w.enabled or (include_test and w.test_only)]
    usable: list[WakeWord] = []
    for w in wanted:
        if _is_file_model(w) and not (wake.models_dir / w.model).is_file():
            _disable(w, f"modelo não encontrado em {wake.models_dir / w.model}", log, out)
        else:
            usable.append(w)
    if not usable:
        return None, []
    ensure_resources([w.model for w in usable if not _is_file_model(w)], download)

    try:
        return OpenWakeWordDetector(usable, wake.models_dir, model_factory), usable
    except Exception:
        good = []
        for w in usable:  # descobre qual modelo quebrou e mantém os outros
            try:
                OpenWakeWordDetector([w], wake.models_dir, model_factory)
                good.append(w)
            except Exception as e:
                _disable(w, f"modelo inválido ({type(e).__name__}: {e})", log, out)
        if not good:
            return None, []
        return OpenWakeWordDetector(good, wake.models_dir, model_factory), good


def _disable(w: WakeWord, reason: str, log: ActionLog, out: Callable[[str], None]) -> None:
    out(f"Palavra '{w.id}' desativada: {reason}. O push-to-talk continua funcionando.")
    log.event("wakeword_desativada", palavra=w.id, motivo=reason)


class DetectorRunner:
    """Roda o detector em um thread próprio (a inferência não pode travar o fluxo do microfone)."""

    def __init__(
        self,
        manager,
        detector: WakeWordDetector,
        gate: ActivationGate,
        on_activation: Callable[[Activation], None],
        on_scores: Callable[[dict[str, float]], None] | None = None,
    ):
        self.detector, self.gate = detector, gate
        self.on_activation, self.on_scores = on_activation, on_scores
        self._q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=50)
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True, name="fidus-wakeword")
        self.frames = 0
        self.dropped = 0
        self.total_s = 0.0
        self.max_s = 0.0
        manager.subscribe(self._push)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._q.put(None)
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def _push(self, block: np.ndarray) -> None:  # chamado no fluxo de áudio: só enfileira
        try:
            self._q.put_nowait(block)
        except queue.Full:
            self.dropped += 1

    def flush(self) -> None:
        """Descarta o áudio pendente e zera o detector (ao voltar a escutar depois de uma conversa)."""
        with self._lock:
            try:
                while True:
                    self._q.get_nowait()
            except queue.Empty:
                pass
            self.detector.reset()

    def process(self, block: np.ndarray) -> None:
        with self._lock:
            t0 = time.perf_counter()
            scores = self.detector.predict(block)
            dt = time.perf_counter() - t0
            self.frames += 1
            self.total_s += dt
            self.max_s = max(self.max_s, dt)
            activation = self.gate.check(scores)
            if activation:
                self.detector.reset()
        if self.on_scores:
            self.on_scores(scores)
        if activation:
            self.on_activation(activation)

    def _run(self) -> None:
        while (block := self._q.get()) is not None:
            self.process(block)
