"""Piper (instalação guiada) e voz na nuvem (ElevenLabs): tudo com servidores e arquivos falsos, sem rede."""

import base64
import hashlib
import io
import json
import urllib.error
import wave
import zipfile
from pathlib import Path

import pytest

from fidus.core.characters.models import Voice
from fidus.core.voice import piper_setup
from fidus.core.voice.elevenlabs import BASE, CloudTTS, CloudVoiceError, ElevenLabsClient, pcm_to_wav
from fidus.core.voice.piper_setup import PiperStore, SetupError


class Resp:
    def __init__(self, body: bytes, headers=None):
        self._b, self.headers = io.BytesIO(body), headers or {"Content-Length": str(len(body))}

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(routes: dict[str, bytes]):
    seen = []

    def opener(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        seen.append(req)
        return Resp(routes[url])

    opener.seen = seen
    return opener


# ---------------- Piper ----------------


def fake_voice(monkeypatch, vid="pt_BR-faber-medium"):
    onnx, meta = b"modelo-falso", b'{"audio": {}}'
    v = dict(piper_setup.VOICES[vid])
    v["onnx_sha256"], v["json_sha256"] = hashlib.sha256(onnx).hexdigest(), hashlib.sha256(meta).hexdigest()
    monkeypatch.setitem(piper_setup.VOICES, vid, v)
    return {v["url"] + ".onnx": onnx, v["url"] + ".onnx.json": meta}


def test_baixa_a_voz_confere_o_hash_e_lista_como_instalada(tmp_path, monkeypatch):
    routes = fake_voice(monkeypatch)
    store = PiperStore(tmp_path, opener_for(routes))
    got = []
    store.download_voice("pt_BR-faber-medium", lambda d, t: got.append((d, t)))
    assert store.installed_voices() == ["pt_BR-faber-medium"] and got
    assert store.model_path("pt_BR-faber-medium").read_bytes() == b"modelo-falso"
    assert not list(tmp_path.rglob("*.part"))
    store.remove_voice("pt_BR-faber-medium")
    assert store.installed_voices() == []


def test_arquivo_com_hash_diferente_e_descartado(tmp_path, monkeypatch):
    routes = fake_voice(monkeypatch)
    url = piper_setup.VOICES["pt_BR-faber-medium"]["url"] + ".onnx"
    routes[url] = b"adulterado"
    store = PiperStore(tmp_path, opener_for(routes))
    with pytest.raises(SetupError, match="não confere"):
        store.download_voice("pt_BR-faber-medium")
    assert store.installed_voices() == [] and not list(tmp_path.rglob("*.onnx*"))  # nada fica pela metade


def test_falha_de_rede_vira_mensagem_clara(tmp_path):
    def opener(req, timeout=None):
        raise urllib.error.URLError("sem internet")

    with pytest.raises(SetupError, match="Não consegui baixar"):
        PiperStore(tmp_path, opener).download_voice("pt_BR-cadu-medium")


def test_voz_desconhecida_e_recusada(tmp_path):
    with pytest.raises(SetupError):
        PiperStore(tmp_path).download_voice("../../etc/passwd")
    with pytest.raises(SetupError):
        PiperStore(tmp_path).remove_voice("x")


def test_instala_o_programa_e_recusa_zip_com_caminho_suspeito(tmp_path, monkeypatch):
    monkeypatch.setattr(piper_setup.sys, "platform", "win32")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("piper/piper.exe", b"MZ")
        z.writestr("piper/espeak-ng-data/x", b"1")
    data = buf.getvalue()
    monkeypatch.setattr(piper_setup, "PIPER_SHA256", hashlib.sha256(data).hexdigest())
    store = PiperStore(tmp_path, opener_for({piper_setup.PIPER_URL: data}))
    store.install_piper()
    assert store.exe.is_file() and (store.exe.parent / "espeak-ng-data" / "x").is_file()
    assert store.status()["installed"] and not (tmp_path / "piper.tmp").exists()

    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../fora.txt", b"x")
    monkeypatch.setattr(piper_setup, "PIPER_SHA256", hashlib.sha256(evil.getvalue()).hexdigest())
    with pytest.raises(SetupError, match="suspeito"):
        PiperStore(tmp_path / "o", opener_for({piper_setup.PIPER_URL: evil.getvalue()})).install_piper()
    assert not (tmp_path / "o" / "fora.txt").exists() and not (tmp_path / "fora.txt").exists()


def test_so_https_e_so_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(piper_setup.sys, "platform", "linux")
    with pytest.raises(SetupError, match="HTTPS"):
        PiperStore(tmp_path)._download("http://exemplo.com/x", tmp_path / "x", "0" * 64, None)
    with pytest.raises(SetupError, match="só para Windows"):
        PiperStore(tmp_path).install_piper()


def test_catalogo_tem_hashes_validos():
    for vid, v in piper_setup.VOICES.items():
        assert vid.startswith("pt_BR-") and v["url"].startswith("https://huggingface.co/rhasspy/piper-voices/")
        assert len(v["onnx_sha256"]) == 64 and len(v["json_sha256"]) == 64
    assert piper_setup.PIPER_URL.startswith("https://github.com/rhasspy/piper/releases/") and len(piper_setup.PIPER_SHA256) == 64


def test_piper_tts_usa_o_id_da_voz_do_catalogo(tmp_path, monkeypatch):
    from fidus.core.voice.tts import PiperTTS

    routes = fake_voice(monkeypatch)
    store = PiperStore(tmp_path, opener_for(routes))
    store.download_voice("pt_BR-faber-medium")
    store.exe.parent.mkdir(parents=True, exist_ok=True)
    store.exe.write_bytes(b"MZ")
    calls = []

    def runner(cmd, input, check, capture_output, creationflags=0):
        calls.append(cmd)
        Path(cmd[cmd.index("--output_file") + 1]).write_bytes(b"RIFF")

    t = PiperTTS(runner=runner, player=lambda p, c: None, tmp_dir=tmp_path, store=store)
    t.configure(Voice(engine="piper", voice="pt_BR-faber-medium"), 0)
    assert t.synthesize("Oi", tmp_path / "x.wav")
    assert calls[0][0] == str(store.exe) and calls[0][2] == str(store.voices_dir / "pt_BR-faber-medium.onnx")
    t.close()


def test_piper_sem_voz_instalada_avisa_onde_instalar(tmp_path):
    from fidus.core.voice.tts import PiperTTS

    t = PiperTTS(runner=lambda *a, **k: None, player=lambda p, c: None, tmp_dir=tmp_path, store=PiperStore(tmp_path))
    t.configure(Voice(engine="piper", voice="pt_BR-faber-medium"), 0)
    with pytest.raises(RuntimeError, match="Configurações"):
        t.synthesize("x", tmp_path / "x.wav")
    t.close()


# ---------------- ElevenLabs ----------------


def wav_of(seconds=0.1):
    return pcm_to_wav(b"\0\0" * int(22050 * seconds))


def client(routes, key="k" * 30):
    op = opener_for(routes)
    return ElevenLabsClient(lambda: key, op), op


def test_pcm_vira_wav_valido():
    w = wave.open(io.BytesIO(wav_of()))
    assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (22050, 1, 2)


def test_design_gera_previas_em_wav_e_envia_a_chave_no_cabecalho():
    reply = {"previews": [{"generated_voice_id": "g1", "audio_base_64": base64.b64encode(b"\0\0" * 100).decode(), "media_type": "audio/pcm"}], "text": "t"}
    c, op = client({BASE + "/v1/text-to-voice/design?output_format=pcm_22050": json.dumps(reply).encode()})
    out = c.design_previews("Masculina, grave e calma. Elegante, de sotaque britânico, ritmo pausado.")
    assert out[0]["id"] == "g1" and out[0]["wav"][:4] == b"RIFF"
    req = op.seen[0]
    assert req.get_header("Xi-api-key") == "k" * 30 and req.get_method() == "POST"
    assert json.loads(req.data)["voice_description"].startswith("Masculina")
    assert 100 <= len(json.loads(req.data)["text"]) <= 1000


def test_descricao_curta_demais_e_recusada_e_mp3_tambem():
    c, _ = client({})
    with pytest.raises(CloudVoiceError, match="mais detalhes"):
        c.design_previews("grave")
    reply = {"previews": [{"generated_voice_id": "g", "audio_base_64": "AA==", "media_type": "audio/mpeg"}]}
    c, _ = client({BASE + "/v1/text-to-voice/design?output_format=pcm_22050": json.dumps(reply).encode()})
    with pytest.raises(CloudVoiceError, match="MP3"):
        c.design_previews("x" * 30)


def test_cria_voz_apaga_e_fala():
    c, op = client({
        BASE + "/v1/text-to-voice": b'{"voice_id": "v123"}',
        BASE + "/v1/voices/v123": b'{"status": "ok"}',
        BASE + "/v1/text-to-speech/v123?output_format=pcm_22050": b"\0\0" * 50,
    })
    assert c.create_voice("Fidus Alfred", "grave", "g1") == "v123"
    assert json.loads(op.seen[0].data) == {"voice_name": "Fidus Alfred", "voice_description": "grave", "generated_voice_id": "g1"}
    c.delete_voice("v123")
    assert op.seen[1].get_method() == "DELETE"
    assert c.synthesize("v123", "Olá")[:4] == b"RIFF"
    assert json.loads(op.seen[2].data) == {"text": "Olá", "model_id": "eleven_multilingual_v2"}


def test_clonagem_envia_a_gravacao_em_multipart():
    c, op = client({BASE + "/v1/voices/add": b'{"voice_id": "clone1", "requires_verification": false}'})
    assert c.clone_voice("Minha voz", wav_of()) == "clone1"
    req = op.seen[0]
    assert req.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="files"; filename="amostra.wav"' in req.data and b'name="name"' in req.data and b"RIFF" in req.data


def test_id_de_voz_suspeito_e_recusado():
    c, _ = client({})
    for bad in ("../x", "a/b", "", "a?b"):
        with pytest.raises(CloudVoiceError):
            c.delete_voice(bad)


@pytest.mark.parametrize("code,trecho", [(401, "não foi aceita"), (403, "plano"), (429, "limite")])
def test_erros_do_servico_viram_mensagens_claras(code, trecho):
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b'{"detail": {"message": "detalhe"}}'))

    with pytest.raises(CloudVoiceError, match=trecho):
        ElevenLabsClient(lambda: "k" * 30, opener).synthesize("v1", "oi")


def test_sem_chave_pede_a_chave():
    with pytest.raises(CloudVoiceError, match="chave de API"):
        ElevenLabsClient(lambda: None, opener_for({})).synthesize("v1", "oi")


def test_cloud_tts_fala_e_uma_falha_nao_derruba_o_motor(tmp_path, capsys):
    played = []

    class C:
        def __init__(self):
            self.fail = False

        def synthesize(self, vid, text):
            if self.fail:
                raise CloudVoiceError("cota")
            return wav_of()

    c = C()
    t = CloudTTS(c, player=lambda p, cancel: played.append(p.read_bytes()[:4]), tmp_dir=tmp_path)
    t.configure(Voice(engine="descricao", voice="v1"), 0)
    t.speak("Olá")
    t.wait_idle(2)
    assert played == [b"RIFF"]
    c.fail = True
    t.speak("de novo")
    t.wait_idle(2)
    assert t.last_error == "cota" and "cota" in capsys.readouterr().err
    c.fail = False
    t.speak("voltou")
    t.wait_idle(2)
    assert len(played) == 2 and not list(tmp_path.glob("*.wav"))  # e segue funcionando; sem temporários
    t.close()


def test_cloud_tts_sem_voz_criada_explica(tmp_path):
    t = CloudTTS(ElevenLabsClient(lambda: "k" * 30, opener_for({})), tmp_dir=tmp_path)
    t.configure(Voice(engine="descricao", voice=""), 0)
    with pytest.raises(CloudVoiceError, match="ainda não tem uma voz"):
        t.synthesize("oi", tmp_path / "x.wav")
    t.close()
