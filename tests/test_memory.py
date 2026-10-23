import json
import sys

import pytest

from fidus.core.actionlog import ActionLog
from fidus.core.config import Config
from fidus.core.memory.db import Database, open_database
from fidus.core.memory.markdown_store import MarkdownMemory, clean_section, tokens
from fidus.core.memory.service import MemoryService
from fidus.core.persona import PersonaService


@pytest.fixture
def md(tmp_path):
    return MarkdownMemory(tmp_path / "memoria")


def test_adicionar_listar_editar_apagar(md):
    e = md.add("perfil", "Gosta de café sem açúcar", "pessoal")
    md.add("rotinas", "Reunião semanal na segunda às 9h")
    assert {x.section for x in md.list()} == {"perfil", "rotinas"}
    assert [x.id for x in md.list(tag="pessoal")] == [e.id]
    md.edit(e.id, "Prefere chá")
    assert md.get(e.id).text == "Prefere chá" and md.get(e.id).tag == "pessoal"
    md.delete(e.id)
    assert md.get(e.id) is None and len(md.list()) == 1


def test_arquivo_e_markdown_legivel_e_preserva_o_que_o_usuario_escreveu(md):
    md.add("perfil", "Mora em Recife")
    path = md.root / "perfil.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nTexto solto que o usuário escreveu.\n- Tem um gato chamado Bolt\n", encoding="utf-8")
    assert any(e.text == "Tem um gato chamado Bolt" for e in md.list("perfil"))  # linha à mão vale
    new = md.add("perfil", "Trabalha à noite")
    content = path.read_text(encoding="utf-8")
    assert "Texto solto que o usuário escreveu." in content and "# Perfil" in content
    hand = next(e for e in md.list("perfil") if "gato" in e.text)
    edited = md.edit(hand.id, "Tem dois gatos")  # editar uma linha à mão a promove a id explícito
    assert "id=" + edited.id in path.read_text(encoding="utf-8") and "Texto solto" in path.read_text(encoding="utf-8")
    assert md.get(new.id)


def test_busca_ignora_acento_e_caixa_e_ordena_por_relevancia(md):
    md.add("perfil", "Gosta de CAFÉ sem açúcar")
    md.add("rotinas", "Toma café com leite às 8h e depois corre")
    md.add("contatos", "João é o dentista")
    r = md.search("cafe")
    assert {e.section for e in r} == {"perfil", "rotinas"} and all("caf" in e.text.lower() for e in r)
    assert md.search("dentista joao")[0].section == "contatos"
    assert md.search("zzz") == [] and md.search("") == []


def test_secoes_validas_e_sem_fuga_de_pasta(md):
    assert clean_section("Projetos/Fidus App") == "projetos/fidus-app"
    for bad in ("../x", "projetos/../../x", "segredos", "/etc/passwd", "projetos/"):
        with pytest.raises(ValueError):
            clean_section(bad)
    e = md.add("projetos/fidus", "Lançar a v1")
    assert (md.root / "projetos" / "fidus.md").is_file() and e.section == "projetos/fidus"
    with pytest.raises(ValueError):
        md.add("perfil", "x", tag="segredo")  # etiqueta fora da lista
    with pytest.raises(ValueError):
        md.add("perfil", "   ")


def test_etiquetas_nao_mudam_o_conteudo_buscado_por_assunto(md):
    md.add("perfil", "Gosta de jazz", "pessoal")
    md.add("perfil", "Gosta de jazz também", "trabalho")
    assert len(md.search("jazz")) == 2


def test_exportar_e_apagar_tudo(md):
    md.add("perfil", "A")
    md.add("rotinas", "B", "trabalho")
    out = md.export_markdown()
    assert "## perfil" in out and "- A" in out and "etiqueta: trabalho" in out
    assert md.delete_all() == 2 and md.list() == []


# ---------- contexto no prompt: só o relevante, com limite ----------


def test_contexto_so_traz_o_relevante_e_respeita_o_limite(config):
    mem = MemoryService(config)
    mem.md.add("perfil", "Chama-se Ana e mora em Recife")
    mem.md.add("contatos", "Carlos é o dentista, telefone 9999")
    mem.md.add("rotinas", "Corrida toda terça de manhã")
    ctx = mem.context_for("quando é a minha corrida?")
    assert "Corrida toda terça" in ctx and "Ana" in ctx  # relevante + perfil
    assert "dentista" not in ctx  # o que não tem relação não vai ao modelo
    small = mem.context_for("quando é a minha corrida?", max_chars=40)
    assert len(small) <= 40


def test_limite_de_tamanho_com_muita_memoria(config):
    mem = MemoryService(config)
    for i in range(60):
        mem.md.add("perfil", f"Fato número {i} sobre o usuário com texto razoável para ocupar espaço")
    for i in range(60):
        mem.md.add("rotinas", f"Rotina {i} café reunião corrida estudo")
    assert len(mem.context_for("café", max_chars=600)) <= 600
    assert len(mem.context_for("café")) <= config.memory.max_context_chars


# ---------- memória compartilhada entre personagens ----------


def test_memoria_compartilhada_entre_personagens(config):
    mem = MemoryService(config)
    persona = PersonaService(config, memory=mem)
    mem.md.add("perfil", "Prefere o café sem açúcar")
    for cid in ("alfred", "donna", "jarbis"):  # todos veem a mesma memória
        assert "café sem açúcar" in str(persona.system_prompt(cid, "REGRAS", "como eu tomo meu café?"))
    mem.md.add("rotinas", "Academia às 7h")  # escrita "por" um personagem aparece para os outros
    assert "Academia às 7h" in str(persona.system_prompt("jarbis", "REGRAS", "que horas é a academia?"))


# ---------- SQLite: histórico e resumos ----------


def test_historico_e_resumos(tmp_path):
    db = Database(tmp_path / "t.db")
    a = db.add_message("s1", "alfred", "user", "oi")
    db.add_message("s1", "donna", "assistant", "olá")
    db.add_message("s2", "alfred", "user", "outra sessão")
    assert [m["texto"] for m in db.messages("s1")] == ["oi", "olá"] and db.count_messages("s1") == 2
    assert db.messages("s1")[1]["personagem"] == "donna"
    assert db.latest_summary("s1") is None
    db.add_summary("s1", a, "resumo 1")
    db.add_summary("s1", a + 1, "resumo 2")
    assert db.latest_summary("s1") == (a + 1, "resumo 2")
    assert db.clear_history() == 3 and db.messages() == []


class FakeSecrets:
    def __init__(self, broken=False):
        self.store, self.broken = {}, broken

    def get(self, name):
        return self.store.get(name)

    def set(self, name, value):
        if self.broken:
            raise RuntimeError("sem cofre")
        self.store[name] = value


def test_criptografia_sqlcipher_de_verdade(tmp_path):
    pytest.importorskip("sqlcipher3")
    sec = FakeSecrets()
    path = tmp_path / "enc.db"
    db = open_database(path, "auto", sec.get, sec.set)
    assert db.encrypted and "DB_KEY" in sec.store and len(sec.store["DB_KEY"]) == 64
    db.add_message("s", "alfred", "user", "segredo guardado")
    db.close()
    raw = path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00" and b"segredo guardado" not in raw  # o arquivo é ilegível sem a chave
    again = open_database(path, "auto", sec.get, sec.set)  # reabre com a chave do cofre
    assert again.messages("s")[0]["texto"] == "segredo guardado"


def test_migra_banco_comum_existente_para_criptografado(tmp_path):
    pytest.importorskip("sqlcipher3")
    path = tmp_path / "m.db"
    plain = Database(path)
    plain.add_message("s", "alfred", "user", "antigo")
    plain.close()
    assert path.read_bytes()[:16] == b"SQLite format 3\x00"
    sec = FakeSecrets()
    db = open_database(path, "auto", sec.get, sec.set)
    assert db.encrypted and db.messages("s")[0]["texto"] == "antigo" and path.read_bytes()[:16] != b"SQLite format 3\x00"


def test_sem_cofre_cai_no_sqlite_comum_e_registra_o_aviso(tmp_path):
    pytest.importorskip("sqlcipher3")
    sec = FakeSecrets(broken=True)
    log = ActionLog(tmp_path / "a.log")
    db = open_database(tmp_path / "x.db", "auto", sec.get, sec.set, log)
    assert not db.encrypted
    ev = json.loads((tmp_path / "a.log").read_text().splitlines()[0])
    assert ev["type"] == "memoria_sem_criptografia" and "cofre" in ev["motivo"]
    with pytest.raises(RuntimeError):
        open_database(tmp_path / "y.db", "sim", sec.get, sec.set)  # "sim" exige criptografia


def test_modo_nao_nunca_criptografa(tmp_path):
    assert not open_database(tmp_path / "n.db", "nao").encrypted
