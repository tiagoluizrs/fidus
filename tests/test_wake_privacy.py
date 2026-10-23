"""Privacidade: no modo passivo nada vai para o disco nem para a rede."""

import builtins
import io
import os
import re
import socket
from pathlib import Path

import numpy as np

import fidus.core.voice as voice_pkg
from fidus.core.voice.audio_manager import BLOCK, AudioManager
from fidus.core.voice.wakeword import ActivationGate, DetectorRunner
from fidus.core.config import WakeWord

from test_wakeword import FakeDetector


class FakeStream:
    def __init__(self, cb): ...
    def start(self): ...
    def stop(self): ...
    def close(self): ...


def snapshot(*dirs):
    return {str(p) for d in dirs for p in Path(d).rglob("*")}


def test_modo_passivo_nao_grava_em_disco_nem_usa_a_rede(tmp_path, monkeypatch, config):
    writes, nets = [], []
    real_open = builtins.open

    def guarded_open(file, mode="r", *a, **k):
        if any(c in str(mode) for c in "wax+"):
            writes.append(file)
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: nets.append(a))
    monkeypatch.chdir(tmp_path)
    before = snapshot(tmp_path, config.data_dir.parent)

    m = AudioManager(stream_factory=FakeStream)
    m.start()
    det = FakeDetector({"ei_alfred": 0.0})
    activations = []
    runner = DetectorRunner(m, det, ActivationGate([WakeWord("ei_alfred", "ei_alfred.onnx", "alfred")], 2), activations.append)
    runner.start()
    for i in range(200):  # 16 s de "áudio" com fala o tempo todo
        m.feed(np.full(BLOCK, 3000, dtype=np.int16))
    runner.stop()
    m.stop()

    assert runner.frames + runner.dropped == 200 and activations == []  # fila limitada descarta se o teste alimentar rápido demais
    assert m.state == "off" and not m._captures  # ninguém abriu gravação
    assert writes == [] and nets == []
    assert snapshot(tmp_path, config.data_dir.parent) == before
    assert not config.log_path.exists()  # nem o log recebeu áudio ou texto


def test_modulos_de_escuta_nao_tem_codigo_de_gravar_arquivo_nem_de_rede():
    base = Path(voice_pkg.__file__).parent
    for name in ("audio_manager.py", "wakeword.py", "vad.py", "listen_loop.py", "indicator.py"):
        src = (base / name).read_text()
        assert not re.search(r"\bwave\b|\bsoundfile\b|\bopen\(|write_bytes|write_text|\bsocket\b|\brequests\b|urllib", src), name
