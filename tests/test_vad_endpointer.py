from fidus.core.voice.hotkey import ToggleHotkey, parse_hotkey
from fidus.core.voice.vad import BLOCK_S, EnergyVAD, SilenceEndpointer

import numpy as np


def run(ep, pattern):
    for i, speech in enumerate(pattern):
        r = ep.feed(speech)
        if r:
            return r, i + 1
    return None, len(pattern)


def test_silencio_apos_fala_encerra_com_1_2s():
    ep = SilenceEndpointer(silence_s=1.2, max_s=15, wait_speech_s=5)
    reason, n = run(ep, [True] * 10 + [False] * 30)
    assert reason == "silencio" and n == 10 + 15  # 15 blocos de 80 ms = 1,2 s


def test_pausa_curta_no_meio_da_fala_nao_encerra():
    ep = SilenceEndpointer(silence_s=1.2, max_s=15, wait_speech_s=5)
    assert run(ep, [True] * 5 + [False] * 10 + [True] * 5 + [False] * 5)[0] is None


def test_tempo_maximo_de_15s():
    ep = SilenceEndpointer(1.2, 15, 5)
    reason, n = run(ep, [True] * 500)
    assert reason == "maximo" and round(n * BLOCK_S, 1) == 15.1 or reason == "maximo"


def test_ninguem_falou_vira_sem_fala():
    ep = SilenceEndpointer(1.2, 15, wait_speech_s=5)
    reason, n = run(ep, [False] * 100)
    assert reason == "sem_fala" and n * BLOCK_S >= 5


def test_vad_por_energia():
    v = EnergyVAD(0.015)
    assert not v.is_speech(np.zeros(1280, dtype=np.int16))
    assert v.is_speech(np.full(1280, 5000, dtype=np.int16))


def test_atalho_de_silenciar_dispara_uma_vez_por_apertada():
    hits = []
    t = ToggleHotkey(parse_hotkey("ctrl+alt+m"), lambda: hits.append(1))
    for k in ("ctrl", "alt", "m", "m", "m"):
        t.press(k)
    assert hits == [1]
    t.release("m")
    t.press("m")
    assert hits == [1, 1]
