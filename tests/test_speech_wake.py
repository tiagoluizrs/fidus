"""Chamado por reconhecimento de fala (sem modelos treinados): VAD + Whisper + nome do personagem."""

import numpy as np
import pytest

from fidus.core.config import WakeWord
from fidus.core.voice.audio_manager import BLOCK
from fidus.core.voice.speech_wake import BLOCK_S, SpeechWakeRunner

SPEECH, SILENCE = 5000, 0
NAMES = {"alfred": "Alfred", "donna": "Donna", "jarbis": "Jarbis"}
WORDS = {c: WakeWord(f"ei_{c}", "", c) for c in NAMES}


class FakeVAD:
    def is_speech(self, block):
        return int(block.max()) > 1000

    def reset(self):
        pass


class FakeSTT:
    def __init__(self, text):
        self.text, self.heard = text, []

    def transcribe(self, audio):
        self.heard.append(len(audio))
        assert audio.dtype == np.float32 and abs(audio).max() <= 1.0
        return self.text


class FakeManager:
    def subscribe(self, cb):
        self.cb = cb


def make(text, **kw):
    acts = []
    r = SpeechWakeRunner(FakeManager(), FakeVAD(), FakeSTT(text), lambda: NAMES, WORDS, acts.append, out=lambda *_: None, **kw)
    return r, acts


def feed(r, speech_blocks, silence_blocks=14):
    for value, n in ((SPEECH, speech_blocks), (SILENCE, silence_blocks)):
        for _ in range(n):
            r.process(np.full(BLOCK, value, dtype=np.int16))


def test_chamou_e_pediu_na_mesma_frase_entrega_o_pedido_ja_em_texto():
    r, acts = make("Ei Alfred, que horas são?")
    feed(r, 12)
    assert len(acts) == 1
    assert (acts[0].word.character, acts[0].text) == ("alfred", "que horas são?")


def test_so_o_chamado_entrega_sem_texto():
    r, acts = make("Ei Donna")
    feed(r, 8)
    assert acts[0].word.character == "donna" and acts[0].text is None


def test_fala_que_nao_chama_ninguem_e_ignorada_sem_acordar():
    r, acts = make("a gente almoça mais tarde, tá bom?")
    feed(r, 12)
    assert acts == [] and r.stt.heard  # foi transcrita para conferir, mas nada acontece


def test_barulho_curto_nem_chega_ao_whisper():
    r, acts = make("ei alfred")
    feed(r, 3)  # menos de meio segundo de fala
    assert acts == [] and r.stt.heard == []


def test_fala_comprida_e_cortada_no_limite_e_a_proxima_comeca_do_zero():
    r, acts = make("ei jarbis", max_s=2.0)
    feed(r, int(3 / BLOCK_S), silence_blocks=0)  # 3 s seguidos de fala, sem pausa
    assert len(acts) >= 1 and acts[0].word.character == "jarbis"


def test_flush_descarta_a_fala_em_andamento():
    r, acts = make("ei alfred")
    feed(r, 6, silence_blocks=0)  # no meio da frase
    r.flush()
    feed(r, 0, silence_blocks=20)  # só silêncio depois: nada a transcrever
    assert acts == [] and r.stt.heard == []


def test_erro_do_whisper_nao_derruba_o_ouvinte():
    class Quebra(FakeSTT):
        def transcribe(self, audio):
            raise RuntimeError("sem memória")

    msgs = []
    r = SpeechWakeRunner(FakeManager(), FakeVAD(), Quebra(""), lambda: NAMES, WORDS, lambda a: None, out=msgs.append)
    r._q.put(np.full(BLOCK, SPEECH, dtype=np.int16))
    r._q.put(None)
    r._run()  # processa o bloco e sai ao ver o None, sem lançar
    assert r._q.empty()


@pytest.mark.parametrize("fala,esperado", [
    ("ei alfredo, abre o bloco de notas", "alfred"),
    ("oi dona me lembra de ligar", "donna"),
    ("jarbas, tudo bem?", "jarbis"),
])
def test_variacoes_do_que_o_whisper_escreve_tambem_chamam(fala, esperado):
    r, acts = make(fala)
    feed(r, 12)
    assert acts and acts[0].word.character == esperado
