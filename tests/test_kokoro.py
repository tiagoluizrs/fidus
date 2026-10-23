"""Voz Kokoro (feminina), efeito de robô e ajuste de tom, sem baixar nada nem carregar modelos."""

import wave

import numpy as np
import pytest

from fidus.core.characters.models import Voice
from fidus.core.voice import kokoro_setup
from fidus.core.voice.effects import apply_effect, robotize, set_pitch
from fidus.core.voice.kokoro_setup import KokoroStore
from fidus.core.voice.piper_setup import SetupError
from fidus.core.voice.tts import KokoroTTS, pitch_factor


def write_wav(path, sr=16000, seconds=0.5):
    t = np.arange(int(sr * seconds)) / sr
    pcm = (np.sin(2 * np.pi * 220 * t) * 12000).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def info(path):
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.getnframes()


def test_tom_muda_a_taxa_do_cabecalho_sem_mexer_nas_amostras(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p)
    sr, n = info(p)
    set_pitch(p, 1.25)
    assert info(p) == (int(sr * 1.25), n)
    set_pitch(p, 1.0)  # sem mudança: não regrava
    assert info(p)[0] == int(sr * 1.25)


def test_fator_de_tom_e_simetrico_e_limitado():
    assert pitch_factor(0) == 1.0
    assert pitch_factor(10) > 1.3 and pitch_factor(-10) < 0.77
    assert pitch_factor(99) == pitch_factor(10)


def test_efeito_robo_muda_o_som_mas_mantem_duracao_e_volume(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p)
    antes = wave.open(str(p)).readframes(8000)
    apply_effect(p, "robo")
    sr, n = info(p)
    assert (sr, n) == (16000, 8000)
    depois = wave.open(str(p)).readframes(8000)
    assert antes != depois
    assert np.abs(np.frombuffer(depois, dtype=np.int16)).max() <= 32767


def test_efeito_vazio_ou_desconhecido_nao_mexe(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p)
    antes = p.read_bytes()
    apply_effect(p, "")
    apply_effect(p, "xyz")
    assert p.read_bytes() == antes


def test_robotize_nunca_estoura():
    x = np.sin(np.linspace(0, 200, 16000)).astype(np.float32)
    assert np.abs(robotize(x, 16000)).max() <= 0.93


def test_loja_do_kokoro_exige_hash_e_nao_deixa_meia_instalacao(tmp_path):
    store = KokoroStore(tmp_path / "kokoro")
    assert not store.installed()

    def fake_download(url, dest, sha, progress):
        assert url.startswith("https://") and len(sha) == 64
        if url == kokoro_setup.MODEL_URL:
            raise SetupError("hash diferente")
        dest.write_bytes(b"x")

    store._download = fake_download
    with pytest.raises(SetupError):
        store.install()
    assert not store.voices_file.exists() and not store.installed()  # descartou o que tinha baixado


def test_kokoro_fala_com_a_voz_escolhida_velocidade_compensada_e_efeito(tmp_path, monkeypatch):
    calls = {}

    class Engine:
        def create(self, text, voice, speed, lang):
            calls.update(text=text, voice=voice, speed=speed, lang=lang)
            return np.zeros(2400, dtype=np.float32) + 0.1, 24000

    monkeypatch.setattr(kokoro_setup, "load_engine", lambda store: Engine())
    store = KokoroStore(tmp_path / "k")
    tts = KokoroTTS(store, player=lambda *a: None, tmp_dir=tmp_path)
    tts.configure(Voice(engine="kokoro", voice="pf_dora", pitch=10, rate=0, effect="robo"), 0)
    out = tmp_path / "fala.wav"
    assert tts.synthesize("Olá", out)
    assert calls["voice"] == "pf_dora" and calls["lang"] == "pt-br"
    assert calls["speed"] < 1.0  # tom mais agudo acelera o áudio: o Kokoro fala mais devagar para a duração não mudar
    assert info(out)[0] == int(24000 * pitch_factor(10))
    tts.close()


def test_voz_desconhecida_cai_na_feminina_padrao(tmp_path):
    tts = KokoroTTS(KokoroStore(tmp_path / "k"), player=lambda *a: None, tmp_dir=tmp_path)
    tts.configure(Voice(engine="kokoro", voice="inexistente"), 0)
    assert tts.speaker == "pf_dora"
    tts.close()


def test_timbre_aberto_tem_mais_agudos_e_o_fechado_menos_sem_mudar_a_duracao():
    from fidus.core.voice.effects import shape

    sr = 16000
    rng = np.random.default_rng(1)
    x = rng.standard_normal(sr).astype(np.float32) * 0.2

    def bright(y):
        s = np.abs(np.fft.rfft(y))
        f = np.fft.rfftfreq(len(y), 1 / sr)
        return s[f > 4000].sum() / s[f < 1000].sum()

    assert len(shape(x, sr, 6, 0)) == len(x)
    assert bright(shape(x, sr, 8, 0)) > bright(x) > bright(shape(x, sr, -8, 0))


def test_ponta_reforca_so_os_medios_agudos():
    from fidus.core.voice.effects import shape

    sr = 16000
    x = np.random.default_rng(2).standard_normal(sr).astype(np.float32) * 0.2
    s0, s1 = np.abs(np.fft.rfft(x)), np.abs(np.fft.rfft(shape(x, sr, 0, 8)))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    band = (f > 2500) & (f < 3500)
    assert s1[band].sum() / s0[band].sum() > 1.5 * s1[f < 500].sum() / s0[f < 500].sum()


def test_ajustes_zerados_nao_mexem_no_audio(tmp_path):
    from fidus.core.voice.effects import shape_file

    p = tmp_path / "a.wav"
    write_wav(p)
    antes = p.read_bytes()
    shape_file(p, 0, 0)
    assert p.read_bytes() == antes


def test_pronuncia_troca_so_palavras_inteiras_sem_diferenciar_maiusculas():
    from fidus.core.voice.effects import apply_pronunciations

    spec = "Alfred=Al fred; Donna=Dona"
    assert apply_pronunciations("Oi, Alfred! O alfredo chegou. Fale com a DONNA.", spec) == "Oi, Al fred! O alfredo chegou. Fale com a Dona."
    assert apply_pronunciations("Alfred", "") == "Alfred" and apply_pronunciations("x", "sem igual") == "x"


def test_voz_neural_ainda_nao_instalada_cai_na_voz_do_sistema_no_windows(tmp_path, monkeypatch):
    from fidus.core.voice import tts as ttsmod

    made = []

    class Fake:
        on_start = None

        def stop(self): ...

        def configure(self, voice, base_rate):
            made.append(voice.engine)

    monkeypatch.setattr(ttsmod.sys, "platform", "win32")
    m = ttsmod.TTSManager(0, {"sapi": lambda v: Fake(), "kokoro": lambda v: Fake()}, tmp_path)
    m.use(Voice(engine="kokoro", voice="pf_dora"))
    assert made == ["sapi"]  # sem o modelo baixado, o personagem não fica mudo
    (tmp_path / "kokoro").mkdir()
    (tmp_path / "kokoro" / "kokoro-v1.0.int8.onnx").write_bytes(b"x")
    (tmp_path / "kokoro" / "voices-v1.0.bin").write_bytes(b"x")
    m.use(Voice(engine="kokoro", voice="pf_dora"))
    assert made == ["sapi", "kokoro"]
