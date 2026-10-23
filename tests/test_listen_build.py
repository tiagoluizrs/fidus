"""Montagem do laço de escuta do app instalado (o que o núcleo faz ao iniciar), com microfone, Whisper e voz falsos."""

import numpy as np

from fidus.core.voice import listen_build


class FakeManager:
    def subscribe(self, cb): ...
    def start(self): ...
    def open_capture(self, preroll): ...


class FakeSTT:
    def __init__(self, *a, **k): ...
    def load(self): ...
    def transcribe(self, audio):
        return ""


class FakeVAD:
    def is_speech(self, block):
        return False

    def reset(self): ...


class FakeTTS:
    def __init__(self, *a, **k): ...
    def use(self, voice): ...
    def stop(self): ...
    def close(self): ...


def test_sem_modelo_treinado_o_laco_sobe_com_o_chamado_por_fala_para_todos_os_personagens(config, monkeypatch, tmp_path):
    from fidus.core.voice import stt as sttmod, tts as ttsmod, vad as vadmod, wakeword

    config.data_dir = tmp_path / "data"
    config.characters.speak_start = False
    monkeypatch.setattr(listen_build, "make_manager", lambda cfg, sf=None: FakeManager())
    monkeypatch.setattr(sttmod, "Transcriber", FakeSTT)
    monkeypatch.setattr(vadmod, "load_vad", lambda t: FakeVAD())
    monkeypatch.setattr(ttsmod, "TTSManager", FakeTTS)
    monkeypatch.setattr(wakeword, "load_detector", lambda *a, **k: (None, []))
    config.wake.mode = "auto"
    loop = listen_build.build_listen_loop(config)  # antes quebrava com KeyError ao montar o chamado por fala
    runner = loop.runner
    assert {"alfred", "donna", "jarbis", "custom"} <= set(runner.words)
    assert runner.names()["custom"] == "Personalizado"
