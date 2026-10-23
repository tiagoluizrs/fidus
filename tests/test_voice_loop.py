"""Laço de voz com tudo falso: STT, TTS e modelo em streaming."""

import json

import numpy as np

from fidus.core.actionlog import ActionLog
from fidus.core.config import Config
from fidus.core.orchestrator import Orchestrator
from fidus.core.providers.base import Response, ToolCall
from fidus.core.voice.loop import VoiceLoop

from conftest import FakeProvider


class FakeSTT:
    def __init__(self, text):
        self.text, self.loaded = text, False

    def load(self):
        self.loaded = True

    def transcribe(self, audio):
        return self.text


class FakeTTS:
    def __init__(self):
        self.on_start, self.spoken, self.stopped = None, [], 0

    def speak(self, text):
        if not self.spoken and self.on_start:
            self.on_start()
        self.spoken.append(text)

    def wait_idle(self, timeout=None): ...
    def stop(self):
        self.stopped += 1

    def close(self): ...


class StreamingProvider(FakeProvider):
    """Entrega o texto em pedaços pequenos, como a API faz."""

    def __init__(self, responses, chunks):
        super().__init__(responses)
        self.chunks = chunks

    def complete_stream(self, system, messages, tools, on_text):
        r = self.complete(system, messages, tools)
        for c in self.chunks if not r.tool_calls else [r.text]:
            if c:
                on_text(c)
        return r


def audio(seconds=1.0):
    return np.zeros(int(16000 * seconds), dtype="float32")


def make(config, provider, heard="o que tenho hoje"):
    orch = Orchestrator(config, provider, lambda p: True, tools={}, log=ActionLog(config.log_path))
    tts = FakeTTS()
    return VoiceLoop(config, orch, FakeSTT(heard), tts, recorder=None, log=ActionLog(config.log_path), out=lambda s: None), tts


def test_fala_frase_a_frase_durante_o_streaming(config, capsys):
    chunks = ["Bom dia", ". Você tem ", "duas reuniões", ". A primeira é às 9h", "."]
    provider = StreamingProvider([Response("".join(chunks))], chunks)
    loop, tts = make(config, provider)
    loop.handle_audio(audio(), speech_end=0.0)
    assert tts.spoken == ["Bom dia.", "Você tem duas reuniões.", "A primeira é às 9h."]


def test_registra_as_tres_latencias_e_memoria(config):
    chunks = ["Oi", "."]
    loop, _ = make(config, StreamingProvider([Response("Oi.")], chunks))
    import time

    loop.handle_audio(audio(), speech_end=time.perf_counter())
    ev = [json.loads(l) for l in config.log_path.read_text().splitlines()]
    m = next(e for e in ev if e["type"] == "metricas_pedido")
    assert m["a_fala_ate_texto_s"] is not None
    assert m["b_texto_ate_primeira_palavra_s"] is not None
    assert m["c_fala_ate_inicio_da_voz_s"] is not None
    assert m["rss_mb"] > 0
    assert "texto" not in m  # o que você disse não vai para o log, só o tamanho


def test_gravacao_curta_demais_e_ignorada(config):
    loop, tts = make(config, StreamingProvider([], []))
    loop.handle_audio(audio(0.1), speech_end=0.0)
    assert tts.spoken == [] and not config.log_path.exists()


def test_sem_fala_reconhecida_nao_chama_o_modelo(config):
    provider = StreamingProvider([], [])
    loop, tts = make(config, provider, heard="")
    loop.handle_audio(audio(), speech_end=0.0)
    assert provider.calls == [] and tts.spoken == []


def test_erro_do_modelo_vira_fala_e_nao_derruba(config):
    class Boom(FakeProvider):
        def complete_stream(self, *a, **k):
            raise RuntimeError("sem rede")

    loop, tts = make(config, Boom([]))
    loop.handle_audio(audio(), speech_end=0.0)
    assert tts.spoken == ["Desculpe, algo deu errado."]


def test_texto_antes_e_depois_da_ferramenta_nao_cola(config):
    from fidus.core.tools.base import Risk, Tool

    class Eco(Tool):
        name, description, parameters, risk = "eco", "d", {"type": "object"}, Risk.LEITURA

        def run(self, args, config):
            return "ok"

    provider = StreamingProvider(
        [Response("Vou verificar", [ToolCall("1", "eco", {})]), Response("Pronto.")], ["Pronto."]
    )
    orch = Orchestrator(config, provider, lambda p: True, tools={"eco": Eco()}, log=ActionLog(config.log_path))
    tts = FakeTTS()
    loop = VoiceLoop(config, orch, FakeSTT("x"), tts, None, ActionLog(config.log_path), out=lambda s: None)
    loop.handle_audio(audio(), 0.0)
    assert tts.spoken == ["Vou verificar", "Pronto."]
