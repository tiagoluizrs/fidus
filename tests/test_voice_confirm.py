import pytest

from fidus.core.voice.confirm import VoiceConfirmer, parse_yes_no


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Sim", True), ("sim, pode", True), ("Claro!", True), ("confirmo", True),
        ("Não", False), ("nao, cancela", False), ("Negativo.", False),
        ("pode não", None), ("sim, não", None),  # ambíguo nunca vale como sim
        ("hmm talvez", None), ("", None), (None, None),
    ],
)
def test_parse_yes_no(texto, esperado):
    assert parse_yes_no(texto) is esperado


def make(heard, fallback_answer=True):
    spoken, fallback_calls, notes = [], [], []

    def listen(timeout):
        if isinstance(heard, Exception):
            raise heard
        return heard

    def fallback(prompt):
        fallback_calls.append(prompt)
        return fallback_answer

    c = VoiceConfirmer(spoken.append, listen, fallback, timeout_s=3, notify=notes.append)
    return c, spoken, fallback_calls


def test_sim_por_voz_nao_usa_teclado():
    c, spoken, fb = make("sim")
    assert c("Abrir regedit?") is True
    assert "Abrir regedit?" in spoken[0] and "sim ou não" in spoken[0]
    assert fb == []


def test_nao_por_voz():
    c, _, fb = make("não")
    assert c("x") is False and fb == []


def test_timeout_cai_no_teclado():
    c, _, fb = make(None, fallback_answer=False)
    assert c("x") is False and fb == ["x"]


def test_resposta_confusa_cai_no_teclado():
    c, _, fb = make("pode não", fallback_answer=True)
    assert c("x") is True and fb == ["x"]


def test_erro_do_microfone_cai_no_teclado_e_nunca_aprova_sozinho():
    c, _, fb = make(RuntimeError("mic ocupado"), fallback_answer=False)
    assert c("x") is False and fb == ["x"]


def test_repassa_o_tempo_limite():
    seen = []
    c = VoiceConfirmer(lambda t: None, lambda t: seen.append(t) or "sim", lambda p: False, timeout_s=5, notify=print)
    c("x")
    assert seen == [5]
