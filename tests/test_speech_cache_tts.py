import sys
import types
from pathlib import Path

import pytest

from fidus.core.characters.models import Voice
from fidus.core.characters.speech_cache import SpeechCache, voice_fingerprint
from fidus.core.voice import tts as ttsmod
from fidus.core.voice.persona_speech import PersonaSpeaker
from fidus.core.voice.tts import PiperTTS, SapiTTS, TTSManager

FP = voice_fingerprint(Voice(), 0, "Maria")


class Synth:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def __call__(self, text, path):
        self.calls.append(text)
        if self.ok:
            Path(path).write_bytes(b"RIFF" + b"\0" * 100)
        return self.ok


# ---------- cache de falas ----------


def test_gera_uma_vez_e_reaproveita(tmp_path):
    synth = Synth()
    c = SpeechCache(tmp_path, synth)
    p1 = c.get("alfred", "Pois não, senhor.", FP)
    p2 = c.get("alfred", "Pois não, senhor.", FP)
    assert p1 == p2 and p1.is_file() and synth.calls == ["Pois não, senhor."]  # sintetizou só uma vez
    assert c.lookup("alfred", "Pois não, senhor.", FP) == p1


def test_muda_a_frase_ou_a_voz_invalida_o_cache(tmp_path):
    synth = Synth()
    c = SpeechCache(tmp_path, synth)
    base = c.get("alfred", "Olá.", FP)
    assert c.get("alfred", "Olá!", FP) != base  # frase mudou
    assert c.get("alfred", "Olá.", voice_fingerprint(Voice(pitch=3), 0, "Maria")) != base  # tom mudou
    assert c.get("alfred", "Olá.", voice_fingerprint(Voice(), 0, "Daniel")) != base  # voz mudou
    assert c.get("alfred", "Olá.", voice_fingerprint(Voice(rate=2), 0, "Maria")) != base  # velocidade mudou
    assert c.get("alfred", "Olá.", voice_fingerprint(Voice(), 5, "Maria")) != base  # velocidade geral mudou
    assert c.get("donna", "Olá.", FP) != base  # outro personagem
    assert len(synth.calls) == 7


def test_warm_gera_so_o_que_falta_e_apaga_o_que_deixou_de_valer(tmp_path):
    synth = Synth()
    c = SpeechCache(tmp_path, synth)
    assert c.warm("alfred", ["A", "B", "C"], FP) == 3
    assert c.warm("alfred", ["A", "B", "C"], FP) == 0  # tudo em cache
    assert c.warm("alfred", ["A", "D"], FP) == 1  # B e C saíram da lista: removidos do disco
    assert len(list((tmp_path / "alfred").glob("*.wav"))) == 2
    c.warm("alfred", ["A", "D"], voice_fingerprint(Voice(pitch=9), 0, "Maria"))  # voz mudou: regenera e limpa as antigas
    assert len(list((tmp_path / "alfred").glob("*.wav"))) == 2 and len(synth.calls) == 6


def test_motor_que_nao_gera_arquivo_nao_quebra(tmp_path):
    c = SpeechCache(tmp_path, Synth(ok=False))
    assert c.get("alfred", "x", FP) is None and not list(tmp_path.rglob("*.wav")) and not list(tmp_path.rglob("*.part"))

    def boom(text, path):
        raise RuntimeError("falhou")

    assert SpeechCache(tmp_path, boom).get("alfred", "x", FP) is None


# ---------- PersonaSpeaker: usa o cache quando existe ----------


class FakePersona:
    def __init__(self):
        self.voices = {"alfred": Voice(pitch=-2), "donna": Voice(pitch=2)}

    def resolve_id(self, cid):
        return cid if cid in self.voices else "alfred"

    def voice(self, cid):
        return self.voices[cid]

    def phrase(self, cid, moment, context=None):
        return f"{cid}-{moment}"

    def ids(self):
        return list(self.voices)

    def renderings(self, cid, moment):
        return [f"{cid}-{moment}", f"{cid}-{moment}-2"]


class FakeManager:
    base_rate = 0
    voice_name = "Maria"

    def __init__(self):
        self.said, self.files, self.used, self.current_voice = [], [], [], Voice()
        self.synth = Synth()

    def use(self, voice):
        self.used.append(voice)
        self.current_voice = voice

    def speak(self, text):
        self.said.append(text)

    def speak_file(self, path):
        self.files.append(path)

    def wait_idle(self, timeout=None): ...

    def synthesize(self, text, path):
        return self.synth(text, path)


def make_speaker(tmp_path):
    tts, persona = FakeManager(), FakePersona()
    cache = SpeechCache(tmp_path, tts.synthesize)
    return PersonaSpeaker(None, persona, tts, cache, out=lambda s: None), tts, cache


def test_fala_de_inicio_vem_do_cache_quando_existe(tmp_path):
    sp, tts, cache = make_speaker(tmp_path)
    assert sp.warm_up() == 4  # 2 falas x 2 personagens
    tts.said.clear()
    sp.say_moment("alfred", "inicio")
    assert tts.said == [] and len(tts.files) == 1  # tocou o áudio guardado, sem sintetizar na hora
    assert tts.synth.calls.count("alfred-inicio") == 1


def test_sem_cache_fala_agora_e_guarda_quando_ocioso(tmp_path):
    sp, tts, cache = make_speaker(tmp_path)
    sp.say_moment("donna", "inicio")
    assert tts.said == ["donna-inicio"] and tts.files == []
    sp.flush_pending()
    assert cache.lookup("donna", "donna-inicio", sp.fingerprint()) is not None
    sp.say_moment("donna", "inicio")
    assert len(tts.files) == 1  # na segunda vez já vem do cache


def test_so_o_momento_inicio_usa_cache_e_a_voz_troca_com_o_personagem(tmp_path):
    sp, tts, _ = make_speaker(tmp_path)
    sp.say_moment("alfred", "erro")
    assert tts.said == ["alfred-erro"] and sp._to_cache == []
    sp.say_moment("donna", "erro")
    assert [v.pitch for v in tts.used] == [-2, 2]  # a voz de cada personagem foi aplicada
    sp.say_moment("donna", "concluir")
    assert len(tts.used) == 2  # sem reconfigurar quando o personagem é o mesmo


def test_voz_indisponivel_nao_derruba(tmp_path):
    sp, tts, _ = make_speaker(tmp_path)
    msgs = []
    sp.out = msgs.append

    def boom(v):
        raise NotImplementedError("nuvem")

    tts.use = boom
    sp.apply_voice("alfred")
    assert "indisponível" in msgs[0]


# ---------- TTS: SAPI (tom por XML, síntese em arquivo), Piper, nuvem ----------


class FakeSapiVoice:
    def __init__(self):
        self.log, self.Rate, self.AudioOutputStream = [], 0, "padrao"
        self.Voice = types.SimpleNamespace(GetDescription=lambda: "Voz padrão")
        self.voices = [("Microsoft Maria", "416;pt-BR"), ("Microsoft Daniel", "416;pt-BR"), ("Microsoft David", "409;en-US")]

    def GetVoices(self):
        items = [types.SimpleNamespace(GetAttribute=lambda k, lang=l: lang, GetDescription=lambda n=n: n) for n, l in self.voices]
        return types.SimpleNamespace(Count=len(items), Item=lambda i: items[i])

    def Speak(self, text, flags):
        self.log.append((text, flags, self.AudioOutputStream))

    def WaitUntilDone(self, ms):
        return True


@pytest.fixture
def sapi(monkeypatch):
    obj = FakeSapiVoice()
    streams = []

    class Stream:
        def __init__(self):
            self.Format = types.SimpleNamespace(Type=0)
            streams.append(self)

        def Open(self, path, mode):
            self.path = path
            Path(path).write_bytes(b"RIFF" + b"\0" * 100)

        def Close(self):
            self.closed = True

    def dispatch(name):
        return Stream() if name == "SAPI.SpFileStream" else obj

    client = types.ModuleType("win32com.client")
    client.Dispatch = dispatch
    monkeypatch.setitem(sys.modules, "pythoncom", types.SimpleNamespace(CoInitialize=lambda: None))
    monkeypatch.setitem(sys.modules, "win32com", types.SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    return obj, streams


def test_sapi_configure_voz_velocidade_e_tom(sapi):
    obj, _ = sapi
    t = SapiTTS(rate=2)
    t.configure(Voice(voice="daniel", pitch=4, rate=3), base_rate=2)
    assert obj.Rate == 5 and t.voice_name == "Microsoft Daniel"  # velocidade geral + a do personagem
    t.speak("Olá & <tudo> bem")
    t.wait_idle(2)
    text, flags, _ = obj.log[-1]
    assert text == '<pitch absmiddle="4">Olá &amp; &lt;tudo&gt; bem</pitch>' and flags == 1 | 8  # XML escapado
    t.configure(Voice(pitch=0), 0)
    t.speak("simples")
    t.wait_idle(2)
    assert obj.log[-1][:2] == ("simples", 1)  # sem tom: texto puro
    t.close()


def test_sapi_voz_inexistente_avisa_e_mantem_a_anterior(sapi):
    t = SapiTTS()
    t.configure(Voice(voice="Zira"), 0)
    assert "não encontrada" in t.voice_name
    t.close()


def test_sapi_sintetiza_para_arquivo_sem_falar(sapi, tmp_path):
    obj, streams = sapi
    t = SapiTTS()
    out = tmp_path / "x.wav"
    assert t.synthesize("Pois não.", out) is True and out.is_file()
    assert streams[0].closed and obj.AudioOutputStream == "padrao"  # restaurou a saída normal
    assert obj.log[-1][0] == "Pois não." and obj.log[-1][2] is streams[0]  # falou para o arquivo
    t.close()


def test_piper_gera_com_o_modelo_do_personagem_e_toca(tmp_path):
    calls, played = [], []

    def runner(cmd, input, check, capture_output, creationflags=0):
        calls.append((cmd, input))
        Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"RIFF" + b"\0" * 100)

    t = PiperTTS("piper.exe", runner, lambda p, c: played.append(p.name), tmp_dir=tmp_path)
    t.configure(Voice(engine="piper", voice="C:/vozes/pt_BR-faber.onnx", rate=2), base_rate=2)
    t.speak("Olá")
    t.wait_idle(2)
    cmd, text = calls[0]
    assert cmd[:3] == ["piper.exe", "--model", "C:/vozes/pt_BR-faber.onnx"] and text == "Olá".encode()
    assert cmd[cmd.index("--length_scale") + 1] == "0.8" and played and t.voice_name == "pt_BR-faber"
    assert not list(tmp_path.glob("*.wav"))  # o temporário é apagado
    out = tmp_path / "cache.wav"
    assert t.synthesize("Oi", out) and out.is_file()
    t.close()


def test_piper_sem_modelo_da_erro_claro_na_sintese(tmp_path):
    t = PiperTTS("piper", lambda *a, **k: None, lambda p, c: None, tmp_dir=tmp_path)
    with pytest.raises(RuntimeError, match="Piper sem voz"):
        t.synthesize("x", tmp_path / "x.wav")
    t.close()


def test_manager_um_provedor_por_motor_e_voz_por_personagem():
    made, configured = [], []

    class P:
        def __init__(self, name):
            self.name, self.on_start, self.voice_name = name, None, name

        def configure(self, voice, base_rate):
            configured.append((self.name, voice.voice, base_rate))

        def speak(self, t): ...
        def stop(self): ...
        def close(self): ...
        def wait_idle(self, timeout=None): ...

    def fac(name):
        def f(v):
            made.append(name)
            return P(name)

        return f

    m = TTSManager(3, {"sapi": fac("sapi"), "piper": fac("piper")})
    m.use(Voice(engine="sapi", voice="Maria"))
    m.use(Voice(engine="sapi", voice="Daniel"))
    m.use(Voice(engine="piper", voice="m.onnx"))
    assert made == ["sapi", "piper"]  # sapi foi criado uma vez só
    assert configured == [("sapi", "Maria", 3), ("sapi", "Daniel", 3), ("piper", "m.onnx", 3)]
    with pytest.raises(RuntimeError, match="desconhecido"):
        m.use(Voice(engine="xyz"))


def test_vozes_de_nuvem_usam_o_provedor_da_nuvem():
    made = []

    class _Fake:
        on_start = None
        voice_name = ""

        def configure(self, voice, base_rate): ...
        def stop(self): ...

    m = TTSManager(factories={"descricao": lambda v: made.append("d") or _Fake(), "propria": lambda v: made.append("p") or _Fake()})
    m.use(Voice(engine="descricao", voice="abc"))
    m.use(Voice(engine="propria", voice="xyz"))
    assert made == ["d", "p"]
    assert set(ttsmod.default_factories()) == {"sapi", "piper", "kokoro", "descricao", "propria"}


def test_sapi_fora_do_windows_da_erro_claro(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="só existe no Windows"):
        TTSManager().use(Voice())
