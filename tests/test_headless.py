import threading
import time

import pytest

from conftest import FakeProvider
from fidus.core.bridge.commands import CoreCommands
from fidus.core.bridge.core_state import CoreState
from fidus.core.bridge.headless import HeadlessLoop
from fidus.core.persona import PersonaService
from fidus.core.providers.base import Response, ToolCall


class Sink:
    has_clients = True

    def __init__(self):
        self.seen = []

    def emit(self, type, **d):
        self.seen.append((type, d))

    def types(self):
        return [t for t, _ in self.seen]


def make(config, responses, monkeypatch, tmp_path):
    monkeypatch.setenv("FIDUS_HOME", str(config.data_dir))
    monkeypatch.setenv("FIDUS_CONFIG", str(tmp_path / "nao.toml"))
    config.data_dir.mkdir(parents=True, exist_ok=True)
    sink = Sink()
    persona = PersonaService(config)
    state = CoreState(config, persona, sink)
    cmds = CoreCommands(config, state, persona=persona)
    loop = HeadlessLoop(config, sink, state, provider=FakeProvider(responses))
    cmds.loop, cmds.broker = loop, loop.broker
    cmds.h.loop = loop
    return cmds, loop, sink


def wait(pred, t=3):
    end = time.time() + t
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_pedido_por_texto_vira_estados_e_legendas(config, monkeypatch, tmp_path):
    cmds, loop, sink = make(config, [Response("Bom dia.")], monkeypatch, tmp_path)
    assert cmds.handle("ask", {"text": "oi"})["started"] is True
    assert wait(lambda: ("state", {"state": "idle", "mic": "off"}) in sink.seen)
    states = [d["state"] for t, d in sink.seen if t == "state"]
    assert states[:2] == ["listening", "thinking"] and states[-1] == "idle"
    caps = [(d["role"], d["text"], d["final"]) for t, d in sink.seen if t == "caption"]
    assert caps[0] == ("user", "oi", True) and ("assistant", "", True) in caps


def test_ask_vazio_ou_ocupado_e_recusado(config, monkeypatch, tmp_path):
    cmds, loop, sink = make(config, [Response("ok")], monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="Digite"):
        cmds.handle("ask", {"text": "  "})
    loop._busy.acquire()
    with pytest.raises(ValueError, match="Ainda estou"):
        cmds.handle("ask", {"text": "oi"})
    loop._busy.release()


def test_erro_do_modelo_aparece_como_evento_e_o_nucleo_continua(config, monkeypatch, tmp_path):
    cmds, loop, sink = make(config, [], monkeypatch, tmp_path)  # sem respostas: o provedor falso levanta IndexError
    cmds.handle("ask", {"text": "oi"})
    assert wait(lambda: "error" in sink.types() and ("state", {"state": "idle", "mic": "off"}) in sink.seen)
    cmds.handle("ask", {"text": "de novo"})  # a trava foi liberada


def test_ask_sem_modo_headless_explica(config, monkeypatch, tmp_path):
    monkeypatch.setenv("FIDUS_HOME", str(config.data_dir))
    config.data_dir.mkdir(parents=True, exist_ok=True)
    persona = PersonaService(config)
    cmds = CoreCommands(config, CoreState(config, persona, Sink()), persona=persona)
    with pytest.raises(ValueError, match="--headless"):
        cmds.handle("ask", {"text": "oi"})


def test_acao_que_pede_confirmacao_espera_o_clique_e_nega_sem_resposta(config, monkeypatch, tmp_path):
    from fidus.core.tools.base import Risk, Tool

    class Grava(Tool):
        name, description, parameters, risk = "grava", "x", {"type": "object", "properties": {}}, Risk.ESCRITA
        ran = 0

        def run(self, args, config):
            Grava.ran += 1
            return "feito"

    cmds, loop, sink = make(config, [Response("", [ToolCall("1", "grava", {})]), Response("pronto")], monkeypatch, tmp_path)
    loop.orchestrator.tools = {"grava": Grava()}
    loop.broker.timeout_s = 5
    cmds.handle("ask", {"text": "grava"})
    assert wait(lambda: "confirm" in sink.types())
    cid = next(d["id"] for t, d in sink.seen if t == "confirm")
    assert cmds.handle("confirm_reply", {"id": cid, "answer": True}) == {"accepted": True}
    assert wait(lambda: ("state", {"state": "idle", "mic": "off"}) in sink.seen)
    assert Grava.ran == 1


# ---------- fala captada pelo microfone do navegador ----------


def pcm_b64(seconds, value=1000):
    import base64

    import numpy as np

    return base64.b64encode((np.ones(int(16000 * seconds)) * value).astype(np.int16).tobytes()).decode()


class FakeTranscriber:
    def __init__(self, text="que horas são"):
        self.text, self.heard = text, []

    def transcribe(self, audio):
        self.heard.append((len(audio), float(audio.max())))
        return self.text


def test_fala_do_navegador_vira_texto_pelo_whisper_e_segue_o_fluxo_normal(config, monkeypatch, tmp_path):
    cmds, loop, sink = make(config, [Response("Agora são dez horas.")], monkeypatch, tmp_path)
    loop.transcriber = FakeTranscriber()
    assert cmds.handle("ask_audio", {"pcm": pcm_b64(1.0)})["started"] is True
    assert wait(lambda: ("state", {"state": "idle", "mic": "off"}) in sink.seen)
    assert loop.transcriber.heard[0][0] == 16000 and 0 < loop.transcriber.heard[0][1] < 1  # float32 normalizado
    caps = [(d["role"], d["text"], d["final"]) for t, d in sink.seen if t == "caption"]
    assert ("user", "Transcrevendo…", False) in caps and ("user", "que horas são", True) in caps
    assert "".join(c[1] for c in caps if c[0] == "assistant") == "Agora são dez horas."


@pytest.mark.parametrize("pcm,trecho", [("%%%", "inválido"), (pcm_b64(0.1), "curto demais"), (pcm_b64(21), "longo demais")], ids=["base64-ruim", "curto", "longo"])
def test_audio_invalido_e_recusado_antes_de_ocupar_o_nucleo(config, monkeypatch, tmp_path, pcm, trecho):
    cmds, loop, sink = make(config, [], monkeypatch, tmp_path)
    with pytest.raises(ValueError, match=trecho):
        cmds.handle("ask_audio", {"pcm": pcm})
    assert loop._busy.acquire(blocking=False)  # nada ficou travado
    loop._busy.release()


def test_sem_fala_entendida_avisa_e_libera(config, monkeypatch, tmp_path):
    cmds, loop, sink = make(config, [], monkeypatch, tmp_path)
    loop.transcriber = FakeTranscriber("")
    cmds.handle("ask_audio", {"pcm": pcm_b64(1.0)})
    assert wait(lambda: any(t == "error" and "Não entendi" in d["message"] for t, d in sink.seen))
    assert wait(lambda: loop._busy.acquire(blocking=False))


def test_falha_no_whisper_vira_erro_na_tela(config, monkeypatch, tmp_path):
    cmds, loop, sink = make(config, [], monkeypatch, tmp_path)

    class Quebra:
        def transcribe(self, audio):
            raise RuntimeError("sem internet para baixar o modelo")

    loop.transcriber = Quebra()
    cmds.handle("ask_audio", {"pcm": pcm_b64(1.0)})
    assert wait(lambda: any(t == "error" and "sem internet" in d["message"] for t, d in sink.seen))


def test_modo_navegador_nao_finge_ter_microfone(config, monkeypatch, tmp_path):
    cmds, loop, sink = make(config, [], monkeypatch, tmp_path)
    assert cmds.state.snapshot()["mic"] == "off"
