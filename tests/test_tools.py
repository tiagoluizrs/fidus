import pytest

from fidus.core.tools import abrir_app, buscar_arquivos
from fidus.core.tools.base import Risk, ToolError
from fidus.core.tools.registry import load_tools


def test_registro_descobre_as_ferramentas():
    tools = load_tools()
    assert set(tools) == {"abrir_app", "buscar_arquivos", "agenda", "email", "rascunho_email", "chat", "memoria"}
    for t in tools.values():
        assert t.description and t.parameters["type"] == "object"
    assert tools["abrir_app"].risk is Risk.ESCRITA
    assert tools["buscar_arquivos"].risk is Risk.LEITURA
    assert tools["agenda"].risk_for({"acao": "ler"}) is Risk.LEITURA
    assert tools["email"].risk is Risk.LEITURA


# ---- abrir_app (o lançamento real é mockado; validar no Windows) ----


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(abrir_app, "_launch", calls.append)
    return calls


def test_abrir_app_da_lista(config, launched):
    tool = abrir_app.TOOL
    assert tool.preapproved({"nome": "Bloco de Notas"}, config)
    assert "aberto" in tool.run({"nome": "bloco de notas"}, config)
    assert launched == ["notepad.exe"]


def test_abrir_app_fora_da_lista_nao_e_preaprovado(config, launched):
    assert not abrir_app.TOOL.preapproved({"nome": "regedit"}, config)


@pytest.mark.parametrize("nome", ["C:\\Windows\\x.exe", "https://evil.com", "calc.exe && del *", "a b", "../x"])
def test_abrir_app_rejeita_caminhos_urls_e_comandos(config, launched, nome):
    with pytest.raises(ToolError):
        abrir_app.TOOL.run({"nome": nome}, config)
    assert launched == []


# ---- buscar_arquivos ----


def test_busca_so_nas_pastas_liberadas(config, tmp_path):
    root = config.allowed_folders[0]
    (root / "sub").mkdir()
    (root / "sub" / "Relatorio Final.txt").write_text("x")
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "relatorio secreto.txt").write_text("x")

    out = buscar_arquivos.TOOL.run({"consulta": "relatorio"}, config)
    assert "Relatorio Final.txt" in out
    assert "secreto" not in out


def test_busca_recusa_pasta_nao_liberada(config, tmp_path):
    with pytest.raises(ToolError):
        buscar_arquivos.TOOL.run({"consulta": "x", "pasta": str(tmp_path)}, config)


def test_busca_recusa_fuga_com_ponto_ponto(config):
    escape = str(config.allowed_folders[0] / ".." )
    with pytest.raises(ToolError):
        buscar_arquivos.TOOL.run({"consulta": "x", "pasta": escape}, config)


def test_busca_nao_segue_link_simbolico_para_fora(config, tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "segredo.txt").write_text("x")
    link = config.allowed_folders[0] / "atalho"
    try:
        link.symlink_to(fora, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("sem suporte a links simbólicos")
    assert "segredo" not in buscar_arquivos.TOOL.run({"consulta": "segredo"}, config)


def test_busca_sem_pastas_configuradas(config):
    config.allowed_folders = []
    with pytest.raises(ToolError):
        buscar_arquivos.TOOL.run({"consulta": "x"}, config)


def test_busca_respeita_limite(config):
    root = config.allowed_folders[0]
    for i in range(10):
        (root / f"doc{i}.txt").write_text("x")
    out = buscar_arquivos.TOOL.run({"consulta": "doc", "max_resultados": 3}, config)
    assert len(out.splitlines()) == 3
