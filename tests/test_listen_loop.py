"""Máquina de estados do laço de escuta, com microfone, VAD, STT e voz falsos."""

import json
import threading
import time

import numpy as np
import pytest

from fidus.core.actionlog import ActionLog
from fidus.core.config import Config, WakeWord
from fidus.core.voice.audio_manager import BLOCK, AudioManager
from fidus.core.voice.indicator import Indicator
from fidus.core.voice.listen_loop import ListenLoop, State
from fidus.core.voice.wakeword import Activation

DONNA = WakeWord("ei_donna", "ei_donna.onnx", "donna")
SPEECH, SILENCE = 5000, 0


class FakeStream:
    def __init__(self, cb): ...
    def start(self): ...
    def stop(self): ...
    def close(self): ...


class FakeVAD:
    def is_speech(self, block):
        return bool(block.max() > 1000)

    def reset(self): ...


class Handler:
    def __init__(self):
        self.calls = []

    def handle_audio(self, audio, speech_end, personagem="alfred"):
        self.calls.append((audio, speech_end, personagem))


class FakeTTS:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1

    def close(self): ...


class Rig:
    def __init__(self, config, tmp_path):
        config.data_dir = tmp_path / "data"
        config.wake.followup_s = 0.4  # 5 blocos: o teste não demora
        config.wake.wait_speech_s = 0.4
        self.config = config
        self.manager = AudioManager(stream_factory=FakeStream)
        self.manager.start()
        self.handler, self.tts, self.shown, self.said = Handler(), FakeTTS(), [], []
        self.loop = ListenLoop(
            config, self.manager, None, FakeVAD(), self.handler, self.tts,
            Indicator(self.shown.append), ActionLog(config.log_path), out=self.said.append,
            beep_fn=lambda: self.said.append("BIP"),
        )

    def feed_script(self, script):
        """Alimenta blocos (valor, quantidade) depois que a gravação abrir; depois só silêncio até o laço acabar."""
        def go():
            t0 = time.time()
            while self.manager.state != "recording" and time.time() - t0 < 3:
                time.sleep(0.001)
            for value, n in script:
                for _ in range(n):
                    self.manager.feed(np.full(BLOCK, value, dtype=np.int16))
                    time.sleep(0.0005)
            while not self.done.is_set():
                self.manager.feed(np.zeros(BLOCK, dtype=np.int16))
                time.sleep(0.0005)

        self.done = threading.Event()
        threading.Thread(target=go, daemon=True).start()

    def wake(self, word=DONNA, script=((SPEECH, 6), (SILENCE, 30))):
        self.feed_script(script)
        self.loop.dispatch(("wake", Activation(word, 0.9, time.perf_counter())))
        self.done.set()


@pytest.fixture
def rig(config, tmp_path):
    return Rig(config, tmp_path)


def log_events(config):
    return [json.loads(l) for l in config.log_path.read_text().splitlines()]


def test_chamado_grava_ate_o_silencio_transcreve_e_volta_a_dormir(rig):
    rig.wake()
    audio, speech_end, personagem = rig.handler.calls[0]
    assert len(rig.handler.calls) == 1
    assert personagem == "donna"  # ei_donna -> personagem donna
    assert audio.dtype == np.float32 and len(audio) >= 6 * BLOCK
    assert rig.loop.state is State.SLEEPING and rig.manager.state == "passive"
    assert any("aguardando continuação" in m for m in rig.said)
    assert any("voltando a dormir" in m for m in rig.said)


def test_chamado_e_personagem_vao_para_o_log_com_o_tempo_ate_gravar(rig):
    rig.wake()
    ev = next(e for e in log_events(rig.config) if e["type"] == "chamado")
    assert ev["palavra"] == "ei_donna" and ev["personagem"] == "donna" and ev["somente_teste"] is False
    assert 0 <= ev["deteccao_ate_gravacao_s"] < 1


def test_continuacao_sem_chamar_de_novo(rig):
    # fala, silêncio curto de 1,2 s, e uma segunda fala dentro dos 5 s de continuação
    rig.config.wake.followup_s = 5.0
    rig.wake(script=((SPEECH, 6), (SILENCE, 17), (SPEECH, 6), (SILENCE, 30)))
    assert len(rig.handler.calls) == 2
    assert [c[2] for c in rig.handler.calls] == ["donna", "donna"]  # mesmo personagem na continuação


def test_chamado_sem_fala_nao_chama_o_modelo_e_volta_a_dormir(rig):
    rig.wake(script=((SILENCE, 30),))
    assert rig.handler.calls == [] and rig.loop.state is State.SLEEPING
    assert rig.manager.state == "passive"  # a detecção foi retomada


def test_beep_so_quando_ligado(rig):
    rig.wake()
    assert "BIP" not in rig.said
    rig.config.wake.beep = True
    rig.wake()
    assert "BIP" in rig.said


def test_durante_a_gravacao_a_deteccao_fica_pausada(rig):
    seen = []
    orig = rig.handler.handle_audio

    def spy(*a, **k):
        seen.append(rig.manager.state)
        orig(*a, **k)

    rig.handler.handle_audio = spy
    rig.wake()
    assert seen == ["paused"]  # respondendo: detector pausado, sem ouvir a própria voz


def test_chamado_e_ignorado_se_nao_esta_dormindo_ou_se_esta_silenciado(rig):
    rig.loop.state = State.PROCESSING
    rig.loop.dispatch(("wake", Activation(DONNA, 0.9, 0.0)))
    assert rig.handler.calls == []
    rig.loop.state = State.SLEEPING
    rig.manager.mute()
    rig.loop.dispatch(("wake", Activation(DONNA, 0.9, 0.0)))
    assert rig.handler.calls == [] and rig.manager.state == "muted"


# ---------- atalho (push-to-talk) no mesmo fluxo ----------


def test_atalho_grava_no_mesmo_fluxo_e_responde_como_alfred(rig):
    for _ in range(10):
        rig.manager.feed(np.full(BLOCK, SPEECH, dtype=np.int16))  # pré-roll
    rig.loop.ptt_down()
    assert rig.tts.stops == 1 and rig.manager.state == "recording"
    for _ in range(10):
        rig.manager.feed(np.full(BLOCK, SPEECH, dtype=np.int16))
    rig.loop.ptt_up()
    rig.loop.dispatch(rig.loop.events.get_nowait())
    audio, _, personagem = rig.handler.calls[0]
    assert personagem == "alfred"
    assert len(audio) >= 10 * BLOCK + 6 * BLOCK  # gravação + 0,5 s de pré-roll
    assert rig.manager.state == "passive"


def test_toque_curto_no_atalho_e_descartado(rig):
    rig.loop.ptt_down()
    rig.manager.feed(np.full(BLOCK, SPEECH, dtype=np.int16))
    rig.loop.ptt_up()
    rig.loop.dispatch(rig.loop.events.get_nowait())
    assert rig.handler.calls == []


def test_atalho_ignorado_com_o_microfone_silenciado(rig):
    rig.manager.mute()
    rig.loop.ptt_down()
    assert rig.manager.state == "muted" and any("silenciado" in m for m in rig.said)


# ---------- silenciar e indicador ----------


def test_silenciar_e_reativar_atualiza_o_indicador(rig):
    rig.loop._show()
    rig.loop.toggle_mute()
    assert rig.manager.muted
    rig.loop.toggle_mute()
    assert not rig.manager.muted and rig.manager.state == "passive"
    textos = " ".join(rig.shown)
    assert "ESCUTA PASSIVA" in rig.shown[0]
    assert "SILENCIADO" in textos
    assert "ESCUTA PASSIVA" in rig.shown[-1]


def test_indicador_so_imprime_quando_muda():
    out = []
    ind = Indicator(out.append)
    ind.show("passive")
    ind.show("passive")
    ind.show("recording")
    assert len(out) == 2 and "GRAVANDO" in out[1]


def test_indicador_tem_os_tres_estados_pedidos():
    from fidus.core.voice.indicator import LABELS

    assert "ESCUTA PASSIVA" in LABELS["passive"] and "GRAVANDO" in LABELS["recording"] and "SILENCIADO" in LABELS["muted"]
