"""Operações das telas de Configurações no núcleo: personagens, memória, contas, privacidade, sobre e configurações."""

import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from fidus.core import secrets as vault
from fidus.core.actionlog import ActionLog
from fidus.core.bridge.commands import CoreCommands
from fidus.core.bridge.core_state import CoreState
from fidus.core.bridge.settings_schema import InvalidSetting, validate_all
from fidus.core.config import apply_live, load_config, threshold_for_sensitivity
from fidus.core.memory.service import get_memory
from fidus.core.orchestrator import Orchestrator
from fidus.core.persona import PersonaService
from fidus.core.providers.base import Response
from fidus.core.tools.base import ToolError
from fidus.core.tools.memoria import TOOL as memoria

from conftest import FakeProvider
from test_services import FakeSlackHttp, FakeVault


class Sink:
    has_clients = True

    def __init__(self):
        self.seen = []

    def emit(self, type, **d):
        self.seen.append((type, d))


@pytest.fixture
def cmds(config, tmp_path, monkeypatch):
    monkeypatch.setenv("FIDUS_HOME", str(config.data_dir))
    monkeypatch.setenv("FIDUS_CONFIG", str(tmp_path / "nao.toml"))
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    sink = Sink()
    persona = PersonaService(config)
    c = CoreCommands(config, CoreState(config, persona, sink), persona=persona)
    c.sink = sink
    return c


def call(c, cmd, /, **args):
    return c.handle(cmd, args)


# ---------- personagens ----------


def test_lista_e_perfil_completo_com_padroes(cmds):
    lst = call(cmds, "characters", op="list")["characters"]
    assert [c["id"] for c in lst] == ["alfred", "donna", "jarbis"] and lst[0]["is_default"] and not lst[0]["edited"]
    p = call(cmds, "characters", op="get", id="alfred")
    assert p["personality"]["controls"]["formalidade"] == {"value": 90, "default": 90}
    assert set(p["phrases"]) == {"inicio", "concluir", "confirmar", "erro", "despedida"}
    assert len(p["phrases"]["inicio"]["items"]) == 7 and p["address"]["mode"] == "fixed" and "{saudacao}" in p["variables"]
    assert p["voice"]["engine"] == "sapi" and p["ring"]["dark"]


def test_slider_restaurar_controle_e_personalidade(cmds):
    p = call(cmds, "characters", op="set_control", id="donna", control="humor", value=90)
    assert p["personality"]["controls"]["humor"] == {"value": 90, "default": 55} and p["edited"]
    assert ("characters_changed", {"id": "donna"}) in cmds.sink.seen
    p = call(cmds, "characters", op="reset_control", id="donna", control="humor")
    assert p["personality"]["controls"]["humor"]["value"] == 55 and not p["edited"]
    call(cmds, "characters", op="set_style", id="donna", style="mais_seco")
    call(cmds, "characters", op="set_extra", id="donna", text="Seja breve")
    p = call(cmds, "characters", op="reset_personality", id="donna")
    assert p["personality"]["base_style"] == "padrao" and p["personality"]["extra"] == ""


def test_frases_editar_apagar_adicionar_ativar_restaurar(cmds):
    call(cmds, "characters", op="item_edit", id="alfred", list="inicio", item="inicio1", text="Fale.")
    call(cmds, "characters", op="item_enable", id="alfred", list="inicio", item="inicio2", enabled=False)
    call(cmds, "characters", op="item_delete", id="alfred", list="inicio", item="inicio3")
    p = call(cmds, "characters", op="item_add", id="alfred", list="inicio", text="Nova frase.")
    items = {i["id"]: i for i in p["phrases"]["inicio"]["items"]}
    assert items["inicio1"]["text"] == "Fale." and items["inicio1"]["origin"] == "editada"
    assert items["inicio2"]["enabled"] is False and "inicio3" not in items
    assert [d["id"] for d in p["phrases"]["inicio"]["deleted"]] == ["inicio3"]
    assert any(i["origin"] == "usuario" for i in items.values())
    p = call(cmds, "characters", op="restore_deleted", id="alfred", list="inicio")
    assert not p["phrases"]["inicio"]["deleted"]
    p = call(cmds, "characters", op="reset_list", id="alfred", list="inicio")
    assert len(p["phrases"]["inicio"]["items"]) == 7 and all(i["origin"] == "padrao" and i["enabled"] for i in p["phrases"]["inicio"]["items"])


def test_tratamento_modo_voz_e_restaurar_tudo(cmds):
    p = call(cmds, "characters", op="set_address_mode", id="alfred", mode="random")
    assert p["address"]["mode"] == "random"
    p = call(cmds, "characters", op="item_add", id="alfred", list="tratamentos", text="Doutor", contexts=["formal", "xxx"])
    assert [i["contexts"] for i in p["address"]["items"] if i["text"] == "Doutor"] == [["formal"]]  # contexto inválido some
    p = call(cmds, "characters", op="set_voice", id="alfred", engine="piper", voice="C:/v.onnx", pitch=3, rate=-2)
    assert p["voice"]["engine"] == "piper" and p["voice"]["pitch"] == 3
    p = call(cmds, "characters", op="reset_voice", id="alfred")
    assert p["voice"]["engine"] == "sapi"
    p = call(cmds, "characters", op="reset", id="alfred")
    assert not p["edited"] and len(p["address"]["items"]) == 2


@pytest.mark.parametrize("op,args", [
    ("get", {"id": "batman"}), ("set_control", {"id": "alfred", "control": "humor", "value": "alto"}),
    ("set_control", {"id": "alfred", "control": "simpatia", "value": 5}), ("set_control", {"id": "alfred", "value": 5}),
    ("item_add", {"id": "alfred", "list": "inicio", "text": "  "}), ("item_add", {"id": "alfred", "list": "inicio", "text": "x" * 400}),
    ("item_add", {"id": "alfred", "list": "outra", "text": "x"}), ("item_enable", {"id": "alfred", "list": "inicio", "item": "inicio1", "enabled": "sim"}),
    ("set_voice", {"id": "alfred", "engine": "nuvem"}), ("set_voice", {"id": "alfred", "pitch": "alto"}), ("voar", {"id": "alfred"}),
    ("set_style", {"id": "alfred", "style": "agressivo"}),
])
def test_entradas_invalidas_de_personagem_sao_recusadas(cmds, config, op, args):
    with pytest.raises((ValueError, KeyError)):
        call(cmds, "characters", op=op, **args)
    assert not (config.characters_dir / "alfred.json").exists()  # e nada foi gravado


def test_ouvir_amostra_e_vozes_sem_nucleo_real(cmds):
    assert call(cmds, "characters", op="preview", id="donna")["spoken"] is False
    assert call(cmds, "voices")["voices"] == []


class FakeTTS:
    base_rate = 0

    def __init__(self):
        self.said = []

    def speak(self, t):
        self.said.append(t)

    def list_voices(self, engine="sapi"):
        return ["Microsoft Maria", "Microsoft Daniel"]


def test_ouvir_amostra_usa_a_voz_do_personagem(cmds):
    from types import SimpleNamespace

    applied = []
    tts = FakeTTS()
    cmds.loop = SimpleNamespace(speaker=SimpleNamespace(tts=tts, apply_voice=applied.append), tts=tts)
    r = call(cmds, "characters", op="preview", id="jarbis")
    assert r == {"spoken": True, "text": "Olá, eu sou Jarbis."} and applied == ["jarbis"] and tts.said == ["Olá, eu sou Jarbis."]
    assert call(cmds, "voices")["voices"] == ["Microsoft Maria", "Microsoft Daniel"]


# ---------- memória ----------


def test_memoria_buscar_adicionar_editar_e_origem(cmds):
    e = call(cmds, "memory", op="add", text="Gosta de café", section="perfil", tag="pessoal")["entry"]
    assert e["source"] == "usuario" and e["tag"] == "pessoal"
    memoria.run({"acao": "adicionar", "texto": "Corre na terça"}, cmds.config)
    rows = call(cmds, "memory", op="list")
    assert {r["source"] for r in rows["entries"]} == {"usuario", "aprendida"} and rows["learn"] is True
    assert [r["text"] for r in call(cmds, "memory", op="list", query="cafe")["entries"]] == ["Gosta de café"]  # sem acento
    call(cmds, "memory", op="edit", id=e["id"], text="Gosta de chá")
    assert call(cmds, "memory", op="list", query="chá")["entries"][0]["id"] == e["id"]
    assert ("memory_changed", {}) in cmds.sink.seen


def test_memoria_apagar_exige_confirmacao_explicita(cmds):
    e = call(cmds, "memory", op="add", text="Importante")["entry"]
    with pytest.raises(ValueError, match="confirmação"):
        call(cmds, "memory", op="delete", id=e["id"])
    with pytest.raises(ValueError, match="confirmação"):
        call(cmds, "memory", op="delete_all")
    assert len(call(cmds, "memory", op="list")["entries"]) == 1
    call(cmds, "memory", op="delete", id=e["id"], confirm=True)
    assert call(cmds, "memory", op="list")["entries"] == []


def test_memoria_exportar_markdown_e_apagar_tudo(cmds):
    call(cmds, "memory", op="add", text="A")
    call(cmds, "memory", op="add", text="B", section="rotinas")
    out = call(cmds, "memory", op="export")
    assert out["filename"].endswith(".md") and "## perfil" in out["markdown"] and "- B" in out["markdown"]
    assert call(cmds, "memory", op="delete_all", confirm=True)["deleted"]["lembrancas"] == 2
    with pytest.raises((ValueError, KeyError)):
        call(cmds, "memory", op="add", text="x", section="../fora")


def test_aprendizado_desligado_bloqueia_o_modelo_mas_nao_voce(cmds, config):
    call(cmds, "set_settings", patch={"memoria.aprender": False})
    assert config.memory.learn is False
    with pytest.raises(ToolError, match="desligado"):
        memoria.precheck({"acao": "adicionar", "texto": "x"}, config)
    assert memoria.precheck({"acao": "buscar"}, config) is None  # ler continua
    assert call(cmds, "memory", op="add", text="eu mesmo escrevi")["entry"]  # pela tela, sempre pode


# ---------- contas ----------


def test_contas_listam_servicos_e_os_em_breve(cmds, monkeypatch):
    FakeVault().install(monkeypatch)
    r = call(cmds, "accounts", op="list")
    s = {x["id"]: x for x in r["services"]}
    assert [x["name"] for x in r["services"]] == ["Gmail", "Outlook", "Slack", "Teams", "Google Agenda", "Microsoft Agenda"]
    assert all(s[i].get("coming_soon") for i in ("outlook", "teams", "msagenda"))
    assert s["gmail"]["connected"] is False and s["slack"]["write"] is False and r["google_credentials"] is False


def test_conectar_slack_valida_guarda_no_cofre_e_desconecta(cmds, config, monkeypatch):
    fv = FakeVault().install(monkeypatch)
    from fidus.core.services import slack as slack_mod

    monkeypatch.setattr(slack_mod.Slack, "__init__", lambda self, cfg, token=None, http=None: (setattr(self, "config", cfg), setattr(self, "_token", token), setattr(self, "_http", FakeSlackHttp()), setattr(self, "_users", {}), setattr(self, "_allowed_cache", None))[0])
    with pytest.raises(ValueError):
        call(cmds, "accounts", op="connect", service="slack")  # sem token
    r = call(cmds, "accounts", op="connect", service="slack", token="xoxp-abc", write=False)
    assert fv.d["SLACK_TOKEN"] == "xoxp-abc" and {x["id"]: x for x in r["services"]}["slack"]["connected"]
    assert "xoxp-abc" not in json.dumps(r)  # o token nunca volta para a tela
    assert ("accounts", {"service": "slack", "status": "connected", "message": "Acme"}) in cmds.sink.seen
    call(cmds, "accounts", op="channel_add", service="slack", name="#geral")
    call(cmds, "accounts", op="channel_add", service="slack", name="projeto")
    r = call(cmds, "accounts", op="channel_remove", service="slack", name="geral")
    assert {x["id"]: x for x in r["services"]}["slack"]["channels"] == ["projeto"]
    r = call(cmds, "accounts", op="disconnect", service="slack")
    assert "SLACK_TOKEN" not in fv.d and not {x["id"]: x for x in r["services"]}["slack"]["connected"]


def test_conectar_google_sem_credenciais_avisa_pelo_evento(cmds, config, monkeypatch):
    FakeVault().install(monkeypatch)
    r = call(cmds, "accounts", op="connect", service="gmail", write=True)
    assert r["started"] is True
    import time

    for _ in range(50):
        if any(t == "accounts" for t, _ in cmds.sink.seen):
            break
        time.sleep(0.05)
    ev = next(d for t, d in cmds.sink.seen if t == "accounts")
    assert ev["status"] == "error" and "credenciais OAuth" in ev["message"]
    with pytest.raises(ValueError):
        call(cmds, "accounts", op="connect", service="outlook")


# ---------- privacidade ----------


def test_pastas_liberadas_so_aceita_pastas_que_existem(cmds, config, tmp_path):
    docs = tmp_path / "Documentos"
    docs.mkdir()
    r = call(cmds, "set_settings", patch={"arquivos.pastas_liberadas": [str(docs)]})
    assert config.allowed_folders == [docs.resolve()] and "arquivos.pastas_liberadas" in r["saved"]
    assert call(cmds, "privacy")["folders"] == [str(docs.resolve())]
    with pytest.raises(InvalidSetting, match="não existe"):
        call(cmds, "set_settings", patch={"arquivos.pastas_liberadas": [str(tmp_path / "fantasma")]})
    assert config.allowed_folders == [docs.resolve()]  # a recusa não mexeu em nada


def test_log_de_acoes_ligado_desligado_e_validade(cmds, config):
    log = ActionLog(config.log_path, config)
    log.record(tool="t", risk="leitura", args={}, decision="permitido")
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat(timespec="seconds")
    with config.log_path.open("a") as f:
        f.write(json.dumps({"ts": old, "tool": "velha", "risk": "leitura", "args": {}, "decision": "permitido", "result": ""}) + "\n")
    assert {e["tool"] for e in call(cmds, "privacy", op="log")["entries"]} == {"t", "velha"}
    assert call(cmds, "privacy", op="prune_log")["removed"] == 1  # 30 dias é o padrão
    assert {e["tool"] for e in call(cmds, "privacy", op="log")["entries"]} == {"t"}
    call(cmds, "set_settings", patch={"privacidade.registrar_acoes": False})
    log.record(tool="nova", risk="leitura", args={}, decision="permitido")  # desligado: não grava
    assert {e["tool"] for e in call(cmds, "privacy", op="log")["entries"]} == {"t"}
    call(cmds, "set_settings", patch={"privacidade.guardar_log_dias": 7})
    assert config.privacy.log_days == 7


def test_historico_so_e_guardado_se_a_opcao_estiver_ligada(cmds, config):
    mem = get_memory(config)
    orch = Orchestrator(config, FakeProvider([Response("oi"), Response("oi de novo")]), lambda p: True, tools={}, persona=cmds.persona, memory=mem)
    orch.run("primeira")
    assert mem.db.count_messages(orch.session) == 2
    call(cmds, "set_settings", patch={"privacidade.guardar_historico": False})
    orch.run("segunda")
    assert mem.db.count_messages(orch.session) == 2  # a segunda conversa não foi guardada


def test_exportar_meus_dados_nao_leva_segredos(cmds, config, tmp_path, monkeypatch):
    fv = FakeVault().install(monkeypatch)
    fv.d["SLACK_TOKEN"] = "xoxp-segredo"
    call(cmds, "memory", op="add", text="Lembrança")
    call(cmds, "characters", op="set_control", id="donna", control="humor", value=80)
    call(cmds, "set_settings", patch={"usuario.nome": "Ana"})
    get_memory(config).db.add_message("s", "alfred", "user", "olá")
    config.google_credentials_path.write_text('{"installed": {"client_secret": "SEGREDO"}}')
    out = tmp_path / "meus-dados.zip"
    r = call(cmds, "privacy", op="export", path=str(out))
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        blob = b"".join(z.read(n) for n in names)
    assert {"memoria/perfil.md", "personagens/donna.json", "configuracoes.json", "historico.json"} <= set(names)
    assert b"xoxp-segredo" not in blob and b"SEGREDO" not in blob and b"client_secret" not in blob
    assert "credentials.json" not in " ".join(names) and r["path"] == str(out)
    for bad in (tmp_path / "x.txt", tmp_path / "pasta_que_nao_existe" / "x.zip", ""):
        with pytest.raises(ValueError):
            call(cmds, "privacy", op="export", path=str(bad))


def test_acoes_sem_volta_exigem_confirmacao_e_apagar_tudo_limpa_tudo(cmds, config, monkeypatch):
    fv = FakeVault().install(monkeypatch)
    fv.d.update({"SLACK_TOKEN": "x", "DB_KEY": "k", "ANTHROPIC_API_KEY": "sk"})
    call(cmds, "memory", op="add", text="Algo")
    call(cmds, "characters", op="set_control", id="donna", control="humor", value=80)
    get_memory(config).db.add_message("s", "alfred", "user", "olá")
    ActionLog(config.log_path, config).record(tool="t", risk="leitura", args={}, decision="permitido")
    for op in ("clear_history", "clear_log", "clear_all"):
        with pytest.raises(ValueError, match="confirmação"):
            call(cmds, "privacy", op=op)
    assert get_memory(config).md.list() and config.db_path.exists()  # nada foi apagado sem o confirm
    assert call(cmds, "privacy", op="clear_history", confirm=True)["deleted"] == 1
    done = call(cmds, "privacy", op="clear_all", confirm=True)
    assert done["lembrancas"] == 1 and done["chaves"] == 3 and fv.d == {}
    assert not config.db_path.exists() and not config.log_path.exists() and not config.characters_dir.exists()


def test_sobre_e_diagnostico_sem_dados_pessoais(cmds, config):
    a = call(cmds, "about")
    assert a["version"] == "0.1.0" and a["model"] == "claude-sonnet-5-5" and a["characters"] == ["alfred", "donna", "jarbis"]
    d = call(cmds, "about", op="diagnostics")["diagnostics"]
    call(cmds, "memory", op="add", text="SEGREDO-PESSOAL")
    d2 = call(cmds, "about", op="diagnostics")["diagnostics"]
    assert "SEGREDO-PESSOAL" not in d2 and "version: 0.1.0" in d


# ---------- configurações novas ----------


def test_toda_chave_nova_e_validada_e_aplicada_ao_vivo(cmds, config):
    r = call(cmds, "set_settings", patch={
        "app.tema": "escuro", "app.janela_inatividade_s": 10, "app.iniciar_com_windows": True, "app.icone_bandeja": False,
        "voz.responder_em_voz": False, "voz.atalho_ativo": False, "voz.velocidade_voz": 3, "chamados.sensibilidade": 100,
        "chamados.esperar_fala_s": 8, "memoria.aprender": False, "privacidade.avisar_microfone": False,
        "modelo.claude": "claude-haiku-5-5", "geral.max_chamadas_ferramenta": 5})
    assert config.app.theme == "escuro" and config.app.ring_idle_s == 10 and config.app.start_with_windows and not config.app.tray_icon
    assert config.voice.speak_replies is False and config.voice.hotkey_enabled is False and config.voice.speech_rate == 3
    assert config.wake.wait_speech_s == 8 and config.memory.learn is False and config.privacy.mic_notice is False
    assert config.model == "claude-haiku-5-5" and config.max_tool_calls == 5
    assert all(w.threshold == 0.3 for w in config.wake.words)  # sensibilidade 100 = acorda mais fácil
    assert r["restart_required"] == []


def test_chaves_que_exigem_reiniciar_sao_avisadas(cmds):
    r = call(cmds, "set_settings", patch={"voz.modelo_whisper": "medium", "voz.microfone": "USB", "usuario.nome": "Ana"})
    assert r["restart_required"] == ["voz.microfone", "voz.modelo_whisper"]


@pytest.mark.parametrize("key,value", [
    ("app.tema", "roxo"), ("app.janela_inatividade_s", 1), ("chamados.sensibilidade", 101), ("voz.velocidade_voz", 11),
    ("voz.modelo_whisper", "gigante"), ("voz.atalho", "   "), ("modelo.claude", "gpt-5"), ("modelo.claude", "claude-../x"),
    ("modelo.provedor", "gpt"), ("privacidade.guardar_log_dias", 0), ("arquivos.pastas_liberadas", "C:/x"), ("chaves.anthropic", "sk"),
    ("voz.responder_em_voz", "sim"), ("modelo.local", "qwen3 8b; rm"), ("modelo.local_url", "http://exemplo.com:11434"),
    ("modelo.local_acoes", "sim"),
])
def test_valores_invalidos_sao_recusados(key, value):
    with pytest.raises(InvalidSetting):
        validate_all(key, value)


def test_sensibilidade_vira_limiar_e_o_limiar_do_toml_tem_prioridade(config, tmp_path, monkeypatch):
    assert [threshold_for_sensitivity(s) for s in (0, 60, 100)] == [0.8, 0.5, 0.3]
    f = tmp_path / "fidus.toml"
    f.write_text('[chamados]\nsensibilidade = 100\n[chamados.palavras.ei_donna]\nlimiar = 0.9\n')
    monkeypatch.setenv("FIDUS_CONFIG", str(f))
    monkeypatch.setenv("FIDUS_HOME", str(tmp_path))
    w = {x.id: x.threshold for x in load_config().wake.words}
    assert w["ei_alfred"] == 0.3 and w["ei_donna"] == 0.9


def test_aplicar_ao_vivo_atualiza_o_mesmo_objeto_da_palavra(config, tmp_path, monkeypatch):
    """O detector guarda os mesmos objetos WakeWord: mudar o limiar tem que valer sem recarregar o detector."""
    monkeypatch.setenv("FIDUS_HOME", str(tmp_path))
    monkeypatch.setenv("FIDUS_CONFIG", str(tmp_path / "x.toml"))
    word = config.wake.words[0]
    fresh = load_config()
    fresh.wake.words[0].threshold = 0.77
    apply_live(config, fresh)
    assert config.wake.words[0] is word and word.threshold == 0.77


def test_efeitos_em_tempo_de_execucao_modelo_do_provedor_e_voz(cmds, config):
    from types import SimpleNamespace

    provider = SimpleNamespace(model="claude-sonnet-5-5")
    speaker = SimpleNamespace(_applied="x")
    tts = SimpleNamespace(base_rate=0)
    cmds.loop = SimpleNamespace(handler=SimpleNamespace(orchestrator=SimpleNamespace(provider=provider)), tts=tts, speaker=speaker)
    call(cmds, "set_settings", patch={"modelo.claude": "claude-opus-5-5", "voz.velocidade_voz": -4})
    assert provider.model == "claude-opus-5-5" and tts.base_rate == -4 and speaker._applied is None


def test_responder_em_voz_desligado_nao_fala_e_atalho_desligado_nao_grava(config):
    from test_listen_loop import Rig

    config.voice.speak_replies = False
    from fidus.core.voice.persona_speech import PersonaSpeaker

    class T:
        spoken = []

        def speak(self, t):
            self.spoken.append(t)

    t = T()
    sp = PersonaSpeaker(config, PersonaService(config), t, None, out=lambda s: None)
    assert sp.say_moment("alfred", "erro") and t.spoken == []  # a frase existe, só não é falada
    config.voice.speak_replies = True
    sp.say_moment("alfred", "erro")
    assert len(t.spoken) == 1


# ---------- valores efetivos, microfones e chave da API ----------


def test_get_settings_traz_os_valores_em_vigor_e_as_opcoes(cmds, config):
    r = call(cmds, "get_settings")
    e = r["effective"]
    assert set(e) == set(r["schema"])  # toda chave permitida tem um valor em vigor
    assert e["app.tema"] == "sistema" and e["chamados.sensibilidade"] == 60 and e["voz.modelo_whisper"] == "small"
    assert e["modelo.claude"] == "claude-sonnet-5-5" and r["claude_models"][0] == "claude-sonnet-5-5"
    call(cmds, "set_settings", patch={"voz.velocidade_voz": 4})
    assert call(cmds, "get_settings")["effective"]["voz.velocidade_voz"] == 4
    assert call(cmds, "get_settings")["settings"]["voz"]["velocidade_voz"] == 4


def test_microfones_sem_audio_nao_quebram(cmds):
    r = call(cmds, "devices")
    assert r["devices"] == [] or all({"index", "name", "default"} <= set(d) for d in r["devices"])


def test_chave_da_api_vai_para_o_cofre_e_nunca_volta(cmds, monkeypatch):
    fv = FakeVault().install(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert call(cmds, "api_key") == {"stored": False, "source": "nenhuma"}
    for bad in ("", "abc", "sk-ant-curta", "sk-ant-com espaço dentro da chave aqui"):
        with pytest.raises(ValueError):
            call(cmds, "api_key", op="set", value=bad)
    r = call(cmds, "api_key", op="set", value="sk-ant-api03-" + "x" * 30)
    assert r == {"stored": True, "source": "cofre"} and fv.d["ANTHROPIC_API_KEY"].startswith("sk-ant-")
    assert "sk-ant" not in json.dumps(call(cmds, "api_key"))
    assert call(cmds, "api_key", op="delete") == {"stored": False, "source": "nenhuma"}


def test_trocar_a_chave_faz_o_provedor_ler_a_nova(cmds, monkeypatch):
    from types import SimpleNamespace

    FakeVault().install(monkeypatch)
    prov = SimpleNamespace(_api_key="velha", _client=object())
    cmds.loop = SimpleNamespace(handler=SimpleNamespace(orchestrator=SimpleNamespace(provider=prov)))
    call(cmds, "api_key", op="set", value="sk-ant-api03-" + "y" * 30)
    assert prov._client is None and prov._api_key is None


# ---------- modelo local (Ollama) ----------


def test_liberar_acoes_do_modelo_local_exige_a_ciencia_dos_riscos(cmds, config):
    with pytest.raises(ValueError, match="entende os riscos"):
        call(cmds, "set_settings", patch={"modelo.local_acoes": True})
    assert not config.local_actions_allowed
    call(cmds, "set_settings", patch={"modelo.local_acoes": True, "modelo.local_acoes_ciente": True})  # os dois juntos
    assert config.local_actions_allowed
    call(cmds, "set_settings", patch={"modelo.local_acoes_ciente": False})  # tirar a ciência desliga a liberação
    e = call(cmds, "get_settings")["effective"]
    assert e["modelo.local_acoes"] is False and e["modelo.local_acoes_ciente"] is False and not config.local_actions_allowed


def test_trocar_para_o_modelo_local_atualiza_o_provedor_e_avisa_a_tela(cmds, config):
    from types import SimpleNamespace

    from fidus.core.providers.anthropic import AnthropicProvider

    orch = SimpleNamespace(provider=AnthropicProvider("claude-sonnet-5-5"))
    cmds.loop = SimpleNamespace(handler=SimpleNamespace(orchestrator=orch))
    call(cmds, "set_settings", patch={"modelo.provedor": "local", "modelo.local": "llama3.1:8b"})
    assert orch.provider.kind == "local" and orch.provider.model == "llama3.1:8b"
    assert ("model", {"provider": "local", "name": "llama3.1:8b", "where": "Neste computador"}) in cmds.sink.seen
    call(cmds, "set_settings", patch={"modelo.provedor": "claude"})
    assert orch.provider.kind == "claude"
    assert cmds.sink.seen[-2] == ("model", {"provider": "claude", "name": config.model, "where": "Nuvem"})


def test_lista_de_modelos_locais_sem_ollama_nao_quebra(cmds):
    r = call(cmds, "set_settings", patch={"modelo.local_url": "http://127.0.0.1:9"})
    r = call(cmds, "local_models")
    assert r["running"] is False and r["models"] == [] and r["suggested"]


# ---------- voz: Piper e nuvem ----------


def test_piper_status_e_voz_desconhecida(cmds):
    st = call(cmds, "piper")
    assert st["installed"] is False and [v["id"] for v in st["voices"]][0].startswith("pt_BR-") and st["busy"] is False
    with pytest.raises(ValueError, match="desconhecida"):
        call(cmds, "piper", op="download_voice", voice="../x")
    with pytest.raises(ValueError):
        call(cmds, "piper", op="zzz")


def test_download_em_segundo_plano_avisa_pelos_eventos(cmds, monkeypatch):
    import time

    from fidus.core.voice import piper_setup

    def fake(self, voice, progress=None):
        progress and progress(5, 10)
        self.voices_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(piper_setup.PiperStore, "download_voice", fake)
    assert call(cmds, "piper", op="download_voice", voice="pt_BR-faber-medium") == {"started": True}
    for _ in range(100):
        if any(t == "voice_setup" and d["state"] == "done" for t, d in cmds.sink.seen):
            break
        time.sleep(0.02)
    states = [d["state"] for t, d in cmds.sink.seen if t == "voice_setup"]
    assert states[-1] == "done" and "progress" in states
    assert call(cmds, "piper")["busy"] is False


def test_chave_do_servico_de_voz_vai_para_o_cofre_e_nunca_volta(cmds, monkeypatch):
    fv = FakeVault().install(monkeypatch)
    assert call(cmds, "voice_cloud")["has_key"] is False
    with pytest.raises(ValueError, match="não parece"):
        call(cmds, "voice_cloud", op="set_key", value="curta")
    st = call(cmds, "voice_cloud", op="set_key", value="k" * 32)
    assert st["has_key"] is True and "k" * 32 not in str(st)
    assert fv.d.get(vault.ELEVENLABS_KEY) == "k" * 32
    assert call(cmds, "voice_cloud", op="clear_key")["has_key"] is False


def test_clonar_exige_consentimento_e_gravacao(cmds, monkeypatch):
    FakeVault().install(monkeypatch)
    with pytest.raises(ValueError, match="consente"):
        call(cmds, "voice_cloud", op="clone", id="alfred")
    with pytest.raises(ValueError, match="Grave a sua voz"):
        call(cmds, "voice_cloud", op="clone", id="alfred", consent=True)
    with pytest.raises(ValueError, match="núcleo real"):
        call(cmds, "voice_cloud", op="record_sample")


def test_criar_voz_por_descricao_salva_no_personagem_e_apagar_volta_ao_padrao(cmds, monkeypatch):
    FakeVault().install(monkeypatch)
    calls = []

    class Eleven:
        def design_previews(self, d):
            calls.append(("design", d))
            return [{"id": "g1", "wav": b"RIFFxxxx"}]

        def create_voice(self, name, desc, gid):
            calls.append(("create", name, gid))
            return "voz123"

        def delete_voice(self, vid):
            calls.append(("delete", vid))

    monkeypatch.setattr(cmds.h, "_eleven", lambda: Eleven())
    r = call(cmds, "voice_cloud", op="design_preview", description="Masculina, grave e calma, sotaque britânico.")
    assert r["previews"] == [{"id": "g1"}]
    with pytest.raises(ValueError, match="expirou"):
        call(cmds, "voice_cloud", op="save_preview", id="alfred", preview="outra", description="x")
    call(cmds, "voice_cloud", op="save_preview", id="alfred", preview="g1", description="Masculina, grave")
    v = call(cmds, "characters", op="get", id="alfred")["voice"]
    assert (v["engine"], v["voice"], v["description"]) == ("descricao", "voz123", "Masculina, grave")
    call(cmds, "voice_cloud", op="delete_voice", id="alfred")
    assert ("delete", "voz123") in calls
    assert call(cmds, "characters", op="get", id="alfred")["voice"]["engine"] == "sapi"
    with pytest.raises(ValueError, match="desconhecido"):
        call(cmds, "voice_cloud", op="delete_voice", id="naoexiste")


def test_motores_de_voz_aceitos_incluem_a_voz_propria(cmds):
    call(cmds, "characters", op="set_voice", id="donna", engine="propria", voice="v1")
    assert call(cmds, "characters", op="get", id="donna")["voice"]["engine"] == "propria"
    with pytest.raises(ValueError):
        call(cmds, "characters", op="set_voice", id="donna", engine="outro")
