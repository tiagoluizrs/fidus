"""Medição da escuta passiva: CPU e memória em repouso e o tempo entre o chamado e o início da gravação."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import numpy as np

from ..actionlog import ActionLog
from ..config import Config
from .audio_manager import BLOCK, SAMPLE_RATE, AudioManager


class SyntheticStream:
    """Microfone de mentira para testar sem hardware: ruído baixo em tempo real. Rotulado no relatório."""

    def __init__(self, callback: Callable):
        self.callback = callback
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None: ...

    def _run(self) -> None:
        rng = np.random.default_rng(0)
        period, nxt = BLOCK / SAMPLE_RATE, time.perf_counter()
        while not self._stop.is_set():
            self.callback((rng.standard_normal(BLOCK) * 30).astype(np.int16))  # ~ -60 dBFS
            nxt += period
            time.sleep(max(0.0, nxt - time.perf_counter()))


def run_bench(
    config: Config,
    seconds: float = 60.0,
    include_test: bool = False,
    synthetic: bool = False,
    out: Callable[[str], None] = print,
) -> int:
    import psutil

    from .listen_build import make_manager
    from .wakeword import ActivationGate, DetectorRunner, load_detector

    log = ActionLog(config.log_path)
    proc = psutil.Process()
    rss_before = proc.memory_info().rss / 2**20
    detector, active = load_detector(config, log, include_test, out)
    if not detector:
        out("Nenhuma palavra ativa para medir. Use --somente-teste ou instale os modelos (docs/WAKEWORDS.md).")
        return 1
    manager = make_manager(config, SyntheticStream if synthetic else None)
    gate = ActivationGate(active, config.wake.cooldown_s)
    latencies: list[float] = []

    def on_activation(act) -> None:
        cap = manager.open_capture(config.wake.preroll_call_s)  # o mesmo caminho do laço real
        latencies.append(time.perf_counter() - act.t)
        cap.close()

    runner = DetectorRunner(manager, detector, gate, on_activation)
    rss_loaded = proc.memory_info().rss / 2**20
    runner.start()
    manager.start()
    proc.cpu_percent(None)  # inicia a janela de medição de CPU
    samples: list[float] = []
    out(f"Medindo {seconds:.0f} s de escuta passiva ({'áudio SINTÉTICO, sem microfone' if synthetic else 'microfone real, fique em silêncio'})...")
    t_end = time.monotonic() + seconds
    try:
        while time.monotonic() < t_end:
            time.sleep(1.0)
            samples.append(proc.memory_info().rss / 2**20)
    except KeyboardInterrupt:
        pass
    cpu = proc.cpu_percent(None)  # média da janela, em % de UM núcleo
    cores = psutil.cpu_count() or 1
    manager.stop()
    runner.stop()

    frames = max(runner.frames, 1)
    report = {
        "segundos": seconds,
        "fonte": "sintética" if synthetic else "microfone",
        "palavras": [w.id for w in active],
        "cpu_pct_de_um_nucleo": round(cpu, 1),
        "cpu_pct_da_maquina": round(cpu / cores, 2),
        "rss_antes_mb": round(rss_before, 1),
        "rss_com_modelos_mb": round(rss_loaded, 1),
        "rss_medio_mb": round(sum(samples) / len(samples), 1) if samples else None,
        "rss_max_mb": round(max(samples), 1) if samples else None,
        "frames": runner.frames,
        "inferencia_media_ms": round(runner.total_s / frames * 1000, 2),
        "inferencia_max_ms": round(runner.max_s * 1000, 2),
        "frames_descartados": runner.dropped,
        "chamados": len(latencies),
        "deteccao_ate_gravacao_ms": round(sum(latencies) / len(latencies) * 1000, 2) if latencies else None,
    }
    log.event("bench_escuta_passiva", **report)
    out("\n=== Relatório: escuta passiva ===")
    for k, v in report.items():
        out(f"  {k:<28} {v}")
    out(f"  (cada frame tem 80 ms; a inferência média é {report['inferencia_media_ms']/80*100:.1f}% desse orçamento)")
    return 0
