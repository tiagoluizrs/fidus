from fidus.core.voice.sentences import SentenceSplitter, clean_for_speech


def feed_all(chunks):
    sp = SentenceSplitter()
    out = []
    for c in chunks:
        out += sp.feed(c)
    if (rest := sp.flush()):
        out.append(rest)
    return out


def test_divide_em_frases():
    assert feed_all(["Olá. Tudo bem? Sim!"]) == ["Olá.", "Tudo bem?", "Sim!"]


def test_frase_so_sai_quando_fecha_mesmo_em_pedacos():
    sp = SentenceSplitter()
    assert sp.feed("Você tem du") == []
    assert sp.feed("as reuniões hoje") == []
    assert sp.feed(". A primeira") == ["Você tem duas reuniões hoje."]
    assert sp.flush() == "A primeira"


def test_nao_corta_decimal_nem_abreviacao():
    assert feed_all(["O valor é 3.5 reais. Fale com o Dr. Silva agora. Ok."]) == [
        "O valor é 3.5 reais.",
        "Fale com o Dr. Silva agora.",
        "Ok.",
    ]


def test_ponto_no_fim_do_buffer_espera_o_proximo_trecho():
    sp = SentenceSplitter()
    assert sp.feed("Pronto.") == []  # pode ser "Pronto.5" ou "Dr."; só fecha ao ver o espaço
    assert sp.feed(" Mais") == ["Pronto."]


def test_quebra_de_linha_fecha_frase():
    assert feed_all(["Vou abrir o app\n", "Pronto"]) == ["Vou abrir o app", "Pronto"]


def test_limpa_markdown():
    assert clean_for_speech("**Reunião** às `9h`\n- item") == "Reunião às 9h item"
    assert feed_all(["## Título\n", "- um\n", "- dois\n"]) == ["Título", "um", "dois"]


def test_flush_vazio():
    assert SentenceSplitter().flush() is None
