import json

import pytest

from fidus import cli_data


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FIDUS_HOME", str(tmp_path))
    monkeypatch.setenv("FIDUS_CONFIG", str(tmp_path / "nao_existe.toml"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(fn, *args):
    return fn(list(args))


def test_character_list_e_show(capsys):
    assert run(cli_data.cmd_character, "list") == 0
    out = capsys.readouterr().out
    assert "alfred" in out and "[padrão]" in out and "ei Donna" in out and "jarbis" in out
    run(cli_data.cmd_character, "show", "alfred")
    out = capsys.readouterr().out
    assert "formalidade" in out and "inicio" in out and "despedida" in out and "[inicio1]" in out
    assert run(cli_data.cmd_character, "show", "batman") == 1


def test_character_set_reset(capsys, home):
    run(cli_data.cmd_character, "set", "donna", "--controle", "humor=90", "--estilo", "mais_seco", "--tom", "3")
    run(cli_data.cmd_character, "show", "donna")
    out = capsys.readouterr().out
    assert "humor        90   (padrão 55)" in out and "estilo: mais_seco" in out and "[editado]" in out
    run(cli_data.cmd_character, "reset", "donna", "--controle", "humor")
    run(cli_data.cmd_character, "show", "donna")
    assert "humor        55\n" in capsys.readouterr().out
    run(cli_data.cmd_character, "reset", "donna", "--tudo")
    assert not (home / "characters" / "donna.json").exists()


def test_character_reset_exige_dizer_o_que_restaurar():
    with pytest.raises(SystemExit):
        run(cli_data.cmd_character, "reset", "donna")  # sem flag: não apaga nada por acidente


def test_character_phrase_e_apagadas(capsys):
    run(cli_data.cmd_character, "phrase", "alfred", "erro", "delete", "erro1")
    run(cli_data.cmd_character, "show", "alfred")
    assert "1 padrão apagada(s)" in capsys.readouterr().out
    run(cli_data.cmd_character, "reset", "alfred", "--apagadas", "erro")
    run(cli_data.cmd_character, "show", "alfred")
    assert "padrão apagada" not in capsys.readouterr().out


def test_character_default_vai_para_settings(home):
    run(cli_data.cmd_character, "default", "jarbis")
    assert json.loads((home / "settings.json").read_text())["chamados"]["personagem_padrao"] == "jarbis"
    from fidus.core.config import load_config

    assert load_config().wake.default_character == "jarbis"  # o padrão que responde ao atalho


def test_memory_cli(capsys):
    run(cli_data.cmd_memory, "add", "Gosta", "de", "café", "--etiqueta", "pessoal")
    run(cli_data.cmd_memory, "add", "Reunião às 9h", "--secao", "rotinas")
    run(cli_data.cmd_memory, "list")
    out = capsys.readouterr().out
    assert "Gosta de café" in out and "(rotinas)" in out
    run(cli_data.cmd_memory, "search", "cafe")
    out = capsys.readouterr().out
    assert "Gosta de café" in out and "Reunião" not in out
    eid = out.split("]")[0].strip("[")
    assert run(cli_data.cmd_memory, "delete", eid, "--sim") == 0
    run(cli_data.cmd_memory, "list", "--secao", "perfil")
    assert "Nada encontrado" in capsys.readouterr().out
    assert run(cli_data.cmd_memory, "add", "x", "--secao", "../fora") == 1


def test_memory_delete_pergunta_e_respeita_o_nao(capsys, monkeypatch):
    run(cli_data.cmd_memory, "add", "Importante")
    eid = capsys.readouterr().out.split("id ")[1].strip(").\n")
    monkeypatch.setattr("builtins.input", lambda p: "n")
    run(cli_data.cmd_memory, "delete", eid)
    run(cli_data.cmd_memory, "list")
    assert "Importante" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda p: "s")
    run(cli_data.cmd_memory, "delete", eid)
    run(cli_data.cmd_memory, "list")
    assert "Nada encontrado" in capsys.readouterr().out


def test_user_set(capsys):
    run(cli_data.cmd_user, "set", "--nome", "Ana", "--sobrenome", "Lima")
    assert "nome: Ana   sobrenome: Lima" in capsys.readouterr().out
