"""STT, TTS e áudio com módulos falsos: nenhum microfone, modelo ou Windows é necessário."""

import json
import sys
import threading
import types

import numpy as np
import pytest

from fidus.core.actionlog import ActionLog
from fidus.core.config import Config, VoiceConfig, load_config
from fidus.core.voice import audio, stt, tts


# ---------- áudio ----------

DEVICES = [
    {"index": 1, "name": "Microfone (Realtek)", "channels": 2, "default": True},
    {"index": 4, "name": "Headset USB", "channels": 1, "default": False},
]


def test_resolve_device():
    assert audio.resolve_device("", DEVICES) is None
    assert audio.resolve_device("4", DEVICES) == 4
    assert audio.resolve_device("headset", DEVICES) == 4
    with pytest.raises(ValueError):
        audio.resolve_device("9", DEVICES)
    with pytest.raises(ValueError):
        audio.resolve_device("inexistente", DEVICES)


def test_endpointer_espera_fala_e_depois_silencio():
    e = audio.EnergyEndpointer(threshold=0.01, silence_s=0.5)
    assert not e.feed(0.0, 0.1) and not e.heard_speech  # silêncio inicial não encerra
    assert not e.feed(0.2, 0.1) and e.heard_speech
    assert not any(e.feed(0.0, 0.1) for _ in range(4))
    assert e.feed(0.0, 0.1)  # 0,5 s de silêncio depois da fala
    e2 = audio.EnergyEndpointer(threshold=0.01, silence_s=0.5)
    e2.feed(0.2, 0.1)
    e2.feed(0.0, 0.3)
    e2.feed(0.2, 0.1)  # voltou a falar: zera o silêncio
    assert not e2.feed(0.0, 0.3)


# ---------- STT ----------


class FakeSegment:
    def __init__(self, text):
        self.text = text


def install_fake_whisper(monkeypatch):
    created, calls = [], []

    class FakeModel:
        def __init__(self, name, device, compute_type):
            created.append((name, device, compute_type))

        def transcribe(self, audio_in, **kw):
            calls.append((audio_in, kw))
            return iter([FakeSegment(" Abre o "), FakeSegment("bloco de notas ")]), None

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    monkeypatch.setattr(stt, "rss_mb", iter([100.0, 650.0]).__next__)
    return created, calls


def test_whisper_carrega_uma_vez_com_os_parametros_pedidos(config, monkeypatch):
    created, calls = install_fake_whisper(monkeypatch)
    t = stt.Transcriber(config)
    assert created == []  # nada carrega ao construir (import e modelo preguiçosos)
    a = np.zeros(16000, dtype="float32")
    assert t.transcribe(a) == "Abre o bloco de notas"
    t.transcribe(a)
    assert created == [("small", "cpu", "int8")]  # uma vez só
    kw = calls[0][1]
    assert kw["language"] == "pt" and kw["vad_filter"] is True


def test_whisper_registra_memoria_antes_e_depois(config, monkeypatch):
    install_fake_whisper(monkeypatch)
    stt.Transcriber(config).load()
    ev = json.loads(config.log_path.read_text().splitlines()[0])
    assert ev["type"] == "memoria_whisper"
    assert (ev["rss_antes_mb"], ev["rss_depois_mb"]) == (100.0, 650.0)
    assert "carga_s" in ev


def test_audio_nao_vai_para_o_disco_por_padrao(config, monkeypatch):
    install_fake_whisper(monkeypatch)
    stt.Transcriber(config).transcribe(np.zeros(16000, dtype="float32"))
    assert not config.debug_audio_dir.exists()
    assert not list(config.data_dir.rglob("*.wav"))


def test_audio_de_debug_so_quando_ligado(config, monkeypatch):
    install_fake_whisper(monkeypatch)
    config.voice.save_debug_audio = True
    stt.Transcriber(config).transcribe(np.zeros(16000, dtype="float32"))
    assert len(list(config.debug_audio_dir.glob("*.wav"))) == 1


def test_config_de_voz_do_toml(tmp_path, monkeypatch):
    f = tmp_path / "fidus.toml"
    f.write_text('[voz]\natalho = "f9"\nmodelo_whisper = "base"\nidioma = "pt-BR"\nvelocidade_voz = 99\nmicrofone = "usb"\n')
    monkeypatch.setenv("FIDUS_CONFIG", str(f))
    monkeypatch.setenv("FIDUS_HOME", str(tmp_path))
    v = load_config().voice
    assert (v.hotkey, v.whisper_model, v.microphone) == ("f9", "base", "usb")
    assert v.speech_rate == 10  # limitado a -10..10
    assert v.whisper_language == "pt" and v.save_debug_audio is False


# ---------- TTS (SAPI falso) ----------


class FakeVoiceObj:
    def __init__(self, log):
        self.log, self.Rate = log, 0
        self.Voice = types.SimpleNamespace(GetDescription=lambda: "Voz padrão")

    def GetVoices(self):
        pt = types.SimpleNamespace(
            GetAttribute=lambda k: "416;pt-BR", GetDescription=lambda: "Maria"
        )
        return types.SimpleNamespace(Count=1, Item=lambda i: pt)

    def Speak(self, text, flags):
        self.log.append((text, flags))

    def WaitUntilDone(self, ms):
        return True


@pytest.fixture
def sapi(monkeypatch):
    log = []
    obj = FakeVoiceObj(log)
    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None
    client = types.ModuleType("win32com.client")
    client.Dispatch = lambda name: obj
    win32com = types.ModuleType("win32com")
    win32com.client = client
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    return log, obj


def test_sapi_fala_em_ordem_escolhe_pt_br_e_avisa_o_inicio(sapi):
    log, obj = sapi
    t = tts.SapiTTS(rate=3)
    starts = []
    t.on_start = lambda: starts.append(1)
    for s in ("Primeira.", "Segunda."):
        t.speak(s)
    t.wait_idle(2)
    t.close()
    assert [x[0] for x in log] == ["Primeira.", "Segunda."]
    assert obj.Rate == 3 and t.voice_name == "Maria"
    assert len(starts) == 2


def test_sapi_stop_descarta_a_fila(sapi):
    log, obj = sapi
    gate = threading.Event()
    original = obj.Speak
    obj.Speak = lambda text, flags: (gate.wait(2), original(text, flags))[1]  # a primeira frase "demora"
    t = tts.SapiTTS()
    t.speak("A")
    t.speak("B")
    t.speak("C")
    t.stop()
    gate.set()
    t.wait_idle(2)
    t.close()
    assert [x[0] for x in log if x[0] in "BC"] == []  # B e C nunca foram faladas


def test_sapi_wait_idle_nao_volta_antes_da_hora(sapi):
    log, obj = sapi
    t = tts.SapiTTS()
    t.speak("x")
    t.wait_idle(2)
    t.speak("y")
    t.wait_idle(2)
    t.close()
    assert [x[0] for x in log] == ["x", "y"]


def test_tts_fora_do_windows_da_erro_claro(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="só existe no Windows"):
        tts.create_tts()
