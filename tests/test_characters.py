import hashlib
import json
import random
from datetime import datetime

import pytest

from fidus.core.characters.models import CONTROLS, MOMENTS
from fidus.core.characters.phrases import PhraseEngine, UserInfo, render, time_variables
from fidus.core.characters.store import ADDRESS, DEFAULTS_DIR, CharacterStore


@pytest.fixture
def store(tmp_path):
    return CharacterStore(tmp_path / "user_chars")


def digest():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DEFAULTS_DIR.glob("*.json")}


# ---------- perfis padrão ----------


@pytest.mark.parametrize("cid", ["alfred", "donna", "jarbis"])
def test_perfil_padrao_completo(store, cid):
    p = store.load(cid)
    assert p.call == f"ei {p.name}" and set(p.personality.controls) == set(CONTROLS)
    assert all(0 <= v <= 100 for v in p.personality.controls.values())
    for m in MOMENTS:
        assert len(p.phrases[m]) >= 6, f"{cid}/{m} tem menos de 6 frases"
    assert len(p.ring["dark"]) == 3 and len(p.ring["light"]) == 3
    assert p.voice.engine == "sapi"


def test_alfred_e_o_padrao_e_os_tres_sao_diferentes(store):
    assert store.ids()[0] == "alfred" and store.default_id() == "alfred"
    c = {i: store.load(i).personality.controls for i in store.ids()}
    assert c["alfred"]["formalidade"] > c["donna"]["formalidade"]
    assert c["donna"]["iniciativa"] > c["alfred"]["iniciativa"]
    texts = {i: {x.text for m in MOMENTS for x in store.load(i).phrases[m]} for i in store.ids()}
    assert not (texts["alfred"] & texts["donna"]) and not (texts["donna"] & texts["jarbis"])


def test_personagem_inexistente(store):
    with pytest.raises(KeyError):
        store.load("batman")


# ---------- edições do usuário e restauração ----------


def test_edicoes_ficam_so_na_pasta_do_usuario_e_o_padrao_nunca_muda(store):
    before = digest()
    store.set_control("donna", "humor", 90)
    store.set_style("donna", "mais_seco")
    store.edit_item("donna", "inicio", "inicio1", "Diga logo.")
    store.delete_item("donna", "erro", "erro2")
    store.add_item("donna", "concluir", "Pronto, chefe.")
    store.set_voice("donna", pitch=5)
    assert digest() == before  # nenhum arquivo padrão foi tocado
    user = json.loads((store.user_dir / "donna.json").read_text())
    assert user["personality"]["controls"] == {"humor": 90}  # só o que mudou
    assert "alfred.json" not in [p.name for p in store.user_dir.iterdir()]


def test_edicao_do_usuario_vale_sobre_o_padrao(store):
    store.set_control("alfred", "formalidade", 10)
    store.edit_item("alfred", "inicio", "inicio1", "Fala.")
    p = store.load("alfred")
    assert p.personality.controls["formalidade"] == 10
    first = next(i for i in p.phrases["inicio"] if i.id == "inicio1")
    assert first.text == "Fala." and first.origin == "editada"


def test_controle_e_limitado_a_0_100_e_valida_nome(store):
    store.set_control("alfred", "humor", 500)
    assert store.load("alfred").personality.controls["humor"] == 100
    with pytest.raises(ValueError):
        store.set_control("alfred", "simpatia", 5)


def test_restaurar_controle_individual(store):
    original = store.load("jarbis").personality.controls["humor"]
    store.set_control("jarbis", "humor", 5)
    store.set_control("jarbis", "detalhe", 5)
    store.reset_control("jarbis", "humor")
    c = store.load("jarbis").personality.controls
    assert c["humor"] == original and c["detalhe"] == 5  # só o humor voltou


def test_apagar_e_restaurar_apagadas(store):
    store.delete_item("alfred", "erro", "erro1")
    store.delete_item("alfred", "erro", "erro2")
    assert len(store.load("alfred").phrases["erro"]) == 4
    assert [i.id for i in store.deleted_items("alfred", "erro")] == ["erro1", "erro2"]
    store.restore_deleted("alfred", "erro")
    assert len(store.load("alfred").phrases["erro"]) == 6 and store.deleted_items("alfred", "erro") == []


def test_restaurar_lista_desfaz_tudo_da_lista_mas_so_dela(store):
    store.edit_item("donna", "inicio", "inicio1", "x")
    store.delete_item("donna", "inicio", "inicio2")
    store.add_item("donna", "inicio", "nova")
    store.set_enabled("donna", "inicio", "inicio3", False)
    store.add_item("donna", "erro", "outra")
    store.reset_list("donna", "inicio")
    p = store.load("donna")
    assert [i.text for i in p.phrases["inicio"]][:2] == ["Fala, {tratamento}.", "Pode dizer. O tempo é curto."]
    assert len(p.phrases["inicio"]) == 7 and all(i.enabled for i in p.phrases["inicio"])
    assert any(i.text == "outra" for i in p.phrases["erro"])  # outra lista intacta


def test_restaurar_personagem_inteiro_remove_o_arquivo_do_usuario(store):
    store.set_control("donna", "humor", 1)
    store.add_item("donna", ADDRESS, "chefa")
    store.set_voice("donna", rate=3)
    assert store.has_user_edits("donna")
    store.reset_character("donna")
    assert not store.has_user_edits("donna")
    assert store.load("donna").personality.controls["humor"] == 55


def test_restaurar_voz_e_personalidade(store):
    store.set_voice("alfred", voice="Daniel", pitch=4)
    store.set_extra("alfred", "seja breve")
    store.set_style("alfred", "mais_aspero")
    store.reset_voice("alfred")
    assert store.load("alfred").voice.voice == "" and store.load("alfred").personality.extra == "seja breve"
    store.reset_personality("alfred")
    p = store.load("alfred").personality
    assert p.extra == "" and p.base_style == "padrao"


def test_adicionar_ativar_desativar(store):
    new_id = store.add_item("alfred", "despedida", "Até breve.")
    assert next(i for i in store.load("alfred").phrases["despedida"] if i.id == new_id).origin == "usuario"
    store.set_enabled("alfred", "despedida", new_id, False)
    store.set_enabled("alfred", "despedida", "despedida1", False)
    p = store.load("alfred").phrases["despedida"]
    assert not next(i for i in p if i.id == new_id).enabled and not p[0].enabled
    store.set_enabled("alfred", "despedida", "despedida1", True)
    assert store.load("alfred").phrases["despedida"][0].enabled
    store.delete_item("alfred", "despedida", new_id)  # apagar uma adicionada some de vez
    assert all(i.id != new_id for i in store.load("alfred").phrases["despedida"])


# ---------- sorteio e variáveis ----------

NOW = datetime(2026, 10, 23, 14, 30)  # sexta-feira, 14h30


def test_sorteio_nunca_repete_a_anterior():
    store = CharacterStore.__new__(CharacterStore)
    store.defaults_dir, store.user_dir = DEFAULTS_DIR, DEFAULTS_DIR / "_nao_existe"
    p = store.load("jarbis")
    eng = PhraseEngine(random.Random(1))
    for moment in MOMENTS:
        picks = [eng.pick(p, moment, UserInfo("Ana", "Lima"), NOW) for _ in range(300)]
        assert all(a != b for a, b in zip(picks, picks[1:])), moment


def test_variaveis_de_tempo():
    assert time_variables(datetime(2026, 10, 23, 8, 0)) == {"periodo": "manhã", "saudacao": "Bom dia", "hora": "8h", "dia": "sexta-feira"}
    assert time_variables(NOW)["periodo"] == "tarde" and time_variables(NOW)["hora"] == "14h30"
    assert time_variables(datetime(2026, 10, 24, 22, 5)) == {"periodo": "noite", "saudacao": "Boa noite", "hora": "22h05", "dia": "sábado"}


def test_render_preenche_e_pula_quando_falta_variavel():
    v = {"nome": "Ana", "sobrenome": ""}
    assert render("Oi, {nome}.", v) == "Oi, Ana."
    assert render("Sr. {sobrenome}", v) is None  # sem sobrenome: pula
    assert render("{inexistente}", v) is None


def test_frase_com_variavel_sem_valor_e_pulada(store):
    eng = PhraseEngine(random.Random(0))
    p = store.load("alfred")  # "Pois não, {nome}?" só existe com nome
    sem_nome = {eng.pick(p, "inicio", UserInfo(), NOW) for _ in range(200)}
    assert not any("{" in (t or "") or "  " in (t or "") or ", ?" in (t or "") for t in sem_nome)
    assert "Pois não, ?" not in sem_nome and "Pois não, Ana?" not in sem_nome
    com_nome = {eng.pick(p, "inicio", UserInfo("Ana"), NOW) for _ in range(200)}
    assert "Pois não, Ana?" in com_nome


def test_sem_nenhuma_frase_possivel_devolve_none(store):
    for i in store.load("alfred").phrases["inicio"]:
        store.edit_item("alfred", "inicio", i.id, "Olá {sobrenome}")
    assert PhraseEngine().pick(store.load("alfred"), "inicio", UserInfo("Ana"), NOW) is None
    assert PhraseEngine().pick(store.load("alfred"), "inicio", UserInfo("Ana", "Lima"), NOW) == "Olá Lima"


def test_frases_desativadas_nao_sao_sorteadas(store):
    p = store.load("alfred")
    for i in p.phrases["concluir"][1:]:
        store.set_enabled("alfred", "concluir", i.id, False)
    eng = PhraseEngine()
    assert {eng.pick(store.load("alfred"), "concluir", UserInfo(), NOW) for _ in range(20)} == {"Providenciado, senhor."}


def test_modo_de_tratamento_fixo_aleatorio_e_por_contexto(store):
    eng = PhraseEngine(random.Random(3))
    user = UserInfo("Ana", "Lima")
    alfred = store.load("alfred")
    assert eng.address_candidates(alfred, "inicio", user, NOW) == ["senhor"]  # fixo
    store.set_address_mode("alfred", "fixed", "")
    assert eng.address_candidates(store.load("alfred"), "inicio", user, NOW) == []  # fixo vazio: sem tratamento

    donna = store.load("donna")  # aleatório, com {nome} e {nome} {sobrenome}
    assert set(eng.address_candidates(donna, "inicio", user, NOW)) == {"chefe", "Ana", "Ana Lima"}
    assert eng.address_candidates(donna, "inicio", UserInfo(), NOW) == ["chefe"]  # sem nome, só o que dá
    picks = [eng._pick_address(donna, "inicio", user, NOW, None) for _ in range(50)]
    assert all(a != b for a, b in zip(picks, picks[1:]))

    jarbis = store.load("jarbis")  # por contexto
    assert eng.address_candidates(jarbis, "erro", user, NOW) == ["senhor"]
    assert eng.address_candidates(jarbis, "despedida", user, NOW) == ["caro Ana"]
    assert eng.address_candidates(jarbis, "inicio", user, NOW) == ["Ana"]  # sem contexto específico: o geral


def test_todas_as_falas_possiveis_para_pre_gerar(store):
    eng = PhraseEngine()
    texts = eng.all_renderings(store.load("alfred"), "inicio", UserInfo("Ana"), NOW)
    assert "Pois não, senhor." in texts and "Pois não, Ana?" in texts and len(texts) == len(set(texts))


# ---------- tratamento conforme quem fala ----------


def test_tratamento_segue_o_que_a_pessoa_escolheu(store):
    eng = PhraseEngine(random.Random(1))
    alfred, jarbis = store.load("alfred"), store.load("jarbis")
    for gender, expected in [("homem", ["senhor"]), ("mulher", ["senhora"]), ("", ["senhor"])]:
        assert eng.address_candidates(alfred, "inicio", UserInfo(gender=gender), NOW) == expected
    assert "senhora" in eng.address_candidates(jarbis, "erro", UserInfo("Ana", gender="mulher"), NOW)


def test_neutro_usa_o_nome_ou_nada(store):
    eng = PhraseEngine(random.Random(1))
    alfred = store.load("alfred")
    assert eng.address_candidates(alfred, "inicio", UserInfo("Ana", gender="neutro"), NOW) == ["Ana"]
    assert eng.address_candidates(alfred, "inicio", UserInfo(gender="neutro"), NOW) == []
    texts = {eng.pick(alfred, "inicio", UserInfo(gender="neutro"), NOW) for _ in range(40)}
    assert texts and None not in texts and not any("senhor" in t for t in texts)  # ainda fala, sem "senhor"
    assert not any("senhora" in t or "senhor" in t for t in eng.all_renderings(alfred, "inicio", UserInfo("Ana", gender="neutro"), NOW))


def test_so_troca_senhor_e_senhora_e_mantem_o_resto(store):
    eng = PhraseEngine(random.Random(1))
    donna = store.load("donna")  # "chefe" e {nome} não são tratamento por gênero
    assert "chefe" in eng.address_candidates(donna, "inicio", UserInfo("Ana", gender="mulher"), NOW)


@pytest.mark.parametrize("entrada,saida", [
    ("Pois não, {tratamento}.", "Pois não."),
    ("{tratamento}, às ordens.", "Às ordens."),
    ("Feito, {tratamento}?", "Feito?"),
    ("Providenciado, {tratamento}", "Providenciado"),
    ("Sem tratamento.", "Sem tratamento."),
])
def test_sem_tratamento_a_pontuacao_fica_correta(entrada, saida):
    from fidus.core.characters.phrases import without_address

    assert without_address(entrada) == saida
