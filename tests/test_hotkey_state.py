from types import SimpleNamespace

import pytest

from fidus.core.voice.hotkey import PushToTalk, key_name, parse_hotkey


def make(spec="ctrl+alt+space"):
    events = []
    ptt = PushToTalk(parse_hotkey(spec), lambda: events.append("start"), lambda: events.append("stop"))
    return ptt, events


def test_parse_normaliza_nomes():
    assert parse_hotkey("Control + ALT+Espaco") == {"ctrl", "alt", "space"}
    with pytest.raises(ValueError):
        parse_hotkey("  ")


def test_segurar_grava_e_soltar_envia():
    ptt, ev = make()
    for k in ("ctrl", "alt"):
        ptt.press(k)
    assert ev == []  # combinação incompleta
    ptt.press("space")
    assert ev == ["start"] and ptt.recording
    ptt.release("space")
    assert ev == ["start", "stop"] and not ptt.recording


def test_auto_repeat_nao_reinicia():
    ptt, ev = make()
    for k in ("ctrl", "alt", "space", "space", "space"):
        ptt.press(k)
    assert ev == ["start"]


def test_soltar_qualquer_tecla_da_combinacao_envia_uma_vez():
    ptt, ev = make()
    for k in ("ctrl", "alt", "space"):
        ptt.press(k)
    ptt.release("ctrl")
    ptt.release("alt")
    ptt.release("space")
    assert ev == ["start", "stop"]


def test_tecla_estranha_nao_dispara_nem_para():
    ptt, ev = make()
    ptt.press("a")
    ptt.release("a")
    assert ev == []
    for k in ("ctrl", "alt", "space"):
        ptt.press(k)
    ptt.press("a")
    ptt.release("a")
    assert ev == ["start"] and ptt.recording


def test_pode_gravar_de_novo_depois_de_soltar():
    ptt, ev = make("f9")
    ptt.press("f9")
    ptt.release("f9")
    ptt.press("f9")
    ptt.release("f9")
    assert ev == ["start", "stop", "start", "stop"]


def test_segurar_antes_de_completar_e_completar_depois():
    ptt, ev = make()
    ptt.press("space")  # espaço sozinho é só digitação
    ptt.press("ctrl")
    ptt.press("alt")
    assert ev == ["start"]  # o espaço já estava pressionado: a combinação fecha ao entrar o último modificador


def test_key_name_do_pynput_por_duck_typing():
    assert key_name(SimpleNamespace(name="ctrl_l")) == "ctrl"
    assert key_name(SimpleNamespace(name="space")) == "space"
    assert key_name(SimpleNamespace(name=None, char="A")) == "a"
    assert key_name(SimpleNamespace(name=None, char=None)) is None
