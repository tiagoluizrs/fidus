import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from fidus.core.config import Config
from fidus.core.orchestrator import Orchestrator
from fidus.core.providers import create_provider, sync_provider
from fidus.core.providers.base import Message, ToolCall, ToolResult, ToolSpec
from fidus.core.providers.ollama import OllamaError, OllamaProvider, check_local_url, list_models
from fidus.core.tools.base import Risk, Tool


class FakeOllama:
    """Servidor local que imita /api/chat (NDJSON) e /api/tags."""

    def __init__(self, replies: list[list[dict]] | None = None, models=("qwen3:8b",), status=200, error=None):
        self.requests: list[dict] = []
        outer = self
        self.replies = list(replies or [])

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = json.dumps({"models": [{"name": m} for m in models]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                outer.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                if error:
                    self.send_response(status)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": error}).encode())
                    return
                self.send_response(200)
                self.end_headers()
                for chunk in outer.replies.pop(0):
                    self.wfile.write(json.dumps(chunk).encode() + b"\n")

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake():
    made = []

    def make(**kw):
        f = FakeOllama(**kw)
        made.append(f)
        return f

    yield make
    for f in made:
        f.close()


def chunk(text="", calls=None, done=False):
    msg = {"role": "assistant", "content": text}
    if calls:
        msg["tool_calls"] = calls
    return {"message": msg, "done": done}


def test_streaming_entrega_o_texto_em_pedacos(fake):
    f = fake(replies=[[chunk("Bom "), chunk("dia."), chunk(done=True)]])
    got: list[str] = []
    r = OllamaProvider("qwen3:8b", f.url).complete_stream("sys", [Message("user", text="oi")], [], got.append)
    assert got == ["Bom ", "dia."] and r.text == "Bom dia." and not r.tool_calls
    sent = f.requests[0]
    assert sent["model"] == "qwen3:8b" and sent["stream"] is True
    assert sent["messages"][0] == {"role": "system", "content": "sys"}
    assert sent["messages"][1] == {"role": "user", "content": "oi"}
    assert "tools" not in sent


def test_ferramentas_vao_e_voltam_no_formato_do_ollama(fake):
    f = fake(replies=[[chunk(calls=[{"function": {"name": "hora", "arguments": {"fuso": "BR"}}}], done=True)], [chunk("São 10h.")]])
    p = OllamaProvider("m", f.url)
    spec = ToolSpec("hora", "Diz a hora", {"type": "object", "properties": {}})
    r = p.complete("s", [Message("user", text="que horas?")], [spec])
    assert f.requests[0]["tools"] == [{"type": "function", "function": {"name": "hora", "description": "Diz a hora", "parameters": spec.parameters}}]
    call = r.tool_calls[0]
    assert (call.name, call.arguments) == ("hora", {"fuso": "BR"}) and call.id

    history = [
        Message("user", text="que horas?"),
        Message("assistant", tool_calls=[call]),
        Message("user", tool_results=[ToolResult(call.id, "10:00")]),
    ]
    p.complete("s", history, [spec])
    msgs = f.requests[1]["messages"]
    assert msgs[2]["tool_calls"] == [{"function": {"name": "hora", "arguments": {"fuso": "BR"}}}]
    assert msgs[3] == {"role": "tool", "tool_name": "hora", "content": "10:00"}


def test_argumentos_em_texto_viram_dict(fake):
    f = fake(replies=[[chunk(calls=[{"function": {"name": "x", "arguments": '{"a": 1}'}}]), chunk(done=True)]])
    r = OllamaProvider("m", f.url).complete("s", [Message("user", text="x")], [])
    assert r.tool_calls[0].arguments == {"a": 1}


def test_ollama_fechado_da_mensagem_clara():
    with pytest.raises(OllamaError, match="Ele está aberto"):
        OllamaProvider("m", "http://127.0.0.1:9", timeout_s=2).complete("s", [Message("user", text="oi")], [])


def test_modelo_nao_baixado_diz_o_comando(fake):
    f = fake(status=404, error="model 'foo' not found")
    with pytest.raises(OllamaError, match="ollama pull foo"):
        OllamaProvider("foo", f.url).complete("s", [Message("user", text="oi")], [])


def test_modelo_sem_ferramentas_explica(fake):
    f = fake(status=400, error="registry.ollama.ai/x does not support tools")
    with pytest.raises(OllamaError, match="não suporta ferramentas"):
        OllamaProvider("x", f.url).complete("s", [Message("user", text="oi")], [])


def test_lista_de_modelos(fake):
    f = fake(models=("qwen3:8b", "llama3.1:8b"))
    assert list_models(f.url) == ["llama3.1:8b", "qwen3:8b"]
    with pytest.raises(OllamaError):
        list_models("http://127.0.0.1:9", timeout_s=1)


@pytest.mark.parametrize("url", ["http://exemplo.com:11434", "https://127.0.0.1:11434", "http://192.168.0.5:11434", "http://u:p@127.0.0.1:11434", "ftp://localhost"])
def test_so_aceita_endereco_da_propria_maquina(url):
    with pytest.raises(ValueError):
        check_local_url(url)
    with pytest.raises(ValueError):
        OllamaProvider("m", url)


def test_enderecos_locais_normalizados():
    assert check_local_url("http://localhost") == "http://localhost:11434"
    assert check_local_url("http://127.0.0.1:8080/x") == "http://127.0.0.1:8080"


# ---- escolha do provedor e troca ao vivo ----


def test_create_e_sync_provider():
    cfg = Config()
    assert create_provider(cfg).kind == "claude"
    cfg.provider = "local"
    cfg.local_model = "llama3.1:8b"
    p = create_provider(cfg)
    assert p.kind == "local" and p.model == "llama3.1:8b"

    class O:
        provider = create_provider(Config())

    o = O()
    assert sync_provider(o, cfg) is True and o.provider.kind == "local"
    cfg.local_model = "outro:1b"
    assert sync_provider(o, cfg) is False and o.provider.model == "outro:1b"
    cfg.provider = "claude"
    assert sync_provider(o, cfg) is True and o.provider.kind == "claude"


# ---- o modelo local só lê, a menos que o usuário libere ----


class Escreve(Tool):
    name, description, parameters = "escreve", "grava", {"type": "object", "properties": {}}
    risk = Risk.ESCRITA
    ran = 0

    def run(self, args, config):
        Escreve.ran += 1
        return "gravou"


class Le(Tool):
    name, description, parameters = "le", "lê", {"type": "object", "properties": {}}
    risk = Risk.LEITURA

    def run(self, args, config):
        return "li"


class Scripted:
    kind, local = "local", True

    def __init__(self, calls):
        self.calls = calls

    def complete(self, system, messages, tools):
        from fidus.core.providers.base import Response

        if any(m.tool_results for m in messages):
            return Response("fim")
        return Response("", [ToolCall("1", n, {}) for n in self.calls])


def run(tmp_path, tool_names, **cfg_over):
    cfg = Config(data_dir=tmp_path)
    cfg.__dict__.update(cfg_over)
    asked: list[str] = []
    o = Orchestrator(cfg, Scripted(tool_names), lambda p: asked.append(p) or True, tools={"escreve": Escreve(), "le": Le()})
    o.run("faz")
    results = [r for m in o.history for r in m.tool_results]
    return results, asked


def test_local_bloqueia_escrita_por_padrao(tmp_path):
    Escreve.ran = 0
    (res,), asked = run(tmp_path, ["escreve"])
    assert res.is_error and "limitado a leitura" in res.content
    assert Escreve.ran == 0 and asked == []  # nem chega a perguntar


def test_local_le_normalmente(tmp_path):
    (res,), asked = run(tmp_path, ["le"])
    assert res.content == "li" and not res.is_error and asked == []


@pytest.mark.parametrize("acoes,ciente", [(True, False), (False, True)])
def test_liberar_exige_toggle_e_ciencia(tmp_path, acoes, ciente):
    Escreve.ran = 0
    (res,), _ = run(tmp_path, ["escreve"], local_actions=acoes, local_actions_ack=ciente)
    assert res.is_error and Escreve.ran == 0


def test_liberado_ainda_pede_confirmacao(tmp_path):
    Escreve.ran = 0
    (res,), asked = run(tmp_path, ["escreve"], local_actions=True, local_actions_ack=True)
    assert res.content == "gravou" and Escreve.ran == 1
    assert len(asked) == 1  # a confirmação continua valendo: vem da camada de permissão, não do modelo


def test_claude_nao_e_afetado(tmp_path):
    class Claude(Scripted):
        kind, local = "claude", False

    cfg = Config(data_dir=tmp_path)
    Escreve.ran = 0
    o = Orchestrator(cfg, Claude(["escreve"]), lambda p: True, tools={"escreve": Escreve()})
    o.run("faz")
    assert Escreve.ran == 1


# ---- baixar modelos pelo painel ----


def test_baixa_modelo_com_progresso(fake):
    from fidus.core.providers.ollama import pull_model

    f = fake(replies=[[{"status": "pulling manifest"}, {"status": "downloading", "total": 100, "completed": 40}, {"status": "downloading", "total": 100, "completed": 100}, {"status": "success"}]])
    seen = []
    pull_model(f.url, "llama3.2:3b", lambda d, t: seen.append((d, t)))
    assert seen == [(40, 100), (100, 100)] and f.requests[0] == {"model": "llama3.2:3b", "stream": True}


def test_baixar_modelo_que_nao_existe_ou_nao_terminou_explica(fake):
    from fidus.core.providers.ollama import pull_model

    f = fake(replies=[[{"error": "pull model manifest: file does not exist"}]])
    with pytest.raises(OllamaError, match="não existe no catálogo"):
        pull_model(f.url, "inexistente:1b")
    f2 = fake(replies=[[{"status": "downloading", "total": 10, "completed": 3}]])
    with pytest.raises(OllamaError, match="não terminou"):
        pull_model(f2.url, "x:1b")


def test_nome_de_modelo_invalido_e_ollama_fechado(fake):
    from fidus.core.providers.ollama import pull_model

    with pytest.raises(OllamaError, match="inválido"):
        pull_model("http://127.0.0.1:9", "a b; rm -rf /")
    with pytest.raises(OllamaError, match="Ele está aberto"):
        pull_model("http://127.0.0.1:9", "llama3.2:3b", timeout_s=2)


# ---- modelos pequenos que escrevem a chamada de ferramenta como texto ----

AGENDA = ToolSpec("agenda", "Agenda", {"type": "object", "properties": {}})


def test_chamada_de_ferramenta_escrita_como_texto_vira_chamada_de_verdade(fake):
    txt = '{"type":"function","function":{"name":"agenda","parameters":{"acao":"ler","dias":1}}}'
    f = fake(replies=[[chunk(txt[:30]), chunk(txt[30:]), chunk(done=True)]])
    got: list[str] = []
    r = OllamaProvider("m", f.url).complete_stream("s", [Message("user", text="x")], [AGENDA], got.append)
    assert got == [] and r.text == ""  # o JSON cru não vai para a tela
    assert (r.tool_calls[0].name, r.tool_calls[0].arguments) == ("agenda", {"acao": "ler", "dias": 1})


def test_texto_que_comeca_com_chave_mas_nao_e_ferramenta_chega_inteiro(fake):
    f = fake(replies=[[chunk('{"nome": "x"} e mais'), chunk(" texto.", done=True)]])
    got: list[str] = []
    r = OllamaProvider("m", f.url).complete_stream("s", [Message("user", text="x")], [AGENDA], got.append)
    assert "".join(got) == '{"nome": "x"} e mais texto.' and not r.tool_calls


def test_nome_de_ferramenta_inexistente_no_texto_nao_vira_chamada(fake):
    txt = '{"name":"apaga_tudo","parameters":{}}'
    f = fake(replies=[[chunk(txt, done=True)]])
    r = OllamaProvider("m", f.url).complete("s", [Message("user", text="x")], [AGENDA])
    assert not r.tool_calls and "inválida" in r.text and "apaga_tudo" not in r.text  # nunca executa nem mostra o JSON


def test_sem_streaming_tambem_reconhece_a_chamada_escrita_como_texto(fake):
    f = fake(replies=[[chunk('{"name":"agenda","arguments":{"acao":"ler"}}', done=True)]])
    r = OllamaProvider("m", f.url).complete("s", [Message("user", text="x")], [AGENDA])
    assert r.tool_calls[0].name == "agenda" and r.text == ""


def test_json_de_ferramenta_dentro_de_bloco_de_codigo_ou_com_frase_antes_vira_chamada(fake):
    for txt in ('```json\n{"name":"agenda","arguments":{"acao":"ler"}}\n```', 'Claro! {"name":"agenda","parameters":{"acao":"ler"}}'):
        f = fake(replies=[[chunk(txt, done=True)]])
        r = OllamaProvider("m", f.url).complete("s", [Message("user", text="x")], [AGENDA])
        assert r.tool_calls and r.tool_calls[0].name == "agenda" and r.text == ""


def test_chamada_invalida_nunca_mostra_json_cru(fake):
    f = fake(replies=[[chunk('{"type":"function","name":"inexistente","parameters":{}}', done=True)]])
    got: list[str] = []
    r = OllamaProvider("m", f.url).complete_stream("s", [Message("user", text="x")], [AGENDA], got.append)
    assert not r.tool_calls and "inválida" in r.text and "{" not in r.text and "".join(got) == r.text


# ---- modelos que "pensam" (qwen3) ----


def test_raciocinio_think_nunca_chega_a_tela_mesmo_em_pedacos(fake):
    from fidus.core.providers.ollama import ThinkFilter

    f = fake(replies=[[chunk("<thi"), chunk("nk>vou pensar</th"), chunk("ink>\nOlá"), chunk(", tudo bem!", done=True)]])
    got: list[str] = []
    r = OllamaProvider("qwen3:8b", f.url).complete_stream("s", [Message("user", text="oi")], [], got.append)
    assert r.text == "Olá, tudo bem!" and "".join(got) == "Olá, tudo bem!"
    t = ThinkFilter()
    assert t.feed("a<b") + t.feed("> c") + t.flush() == "a<b> c"  # "<" solto não some


def test_qwen3_vai_sem_raciocinio_e_outros_modelos_nao_recebem_a_opcao(fake):
    f = fake(replies=[[chunk("ok", done=True)], [chunk("ok", done=True)]])
    OllamaProvider("qwen3:8b", f.url).complete("s", [Message("user", text="x")], [])
    OllamaProvider("llama3.1:8b", f.url).complete("s", [Message("user", text="x")], [])
    assert f.requests[0]["think"] is False and "think" not in f.requests[1]


def test_runner_sobe_o_ollama_fechado_e_so_encerra_o_que_ele_abriu(monkeypatch):
    from fidus.core.providers import ollama_runner as r

    up = {"v": False}
    started = []

    class P:
        def poll(self):
            return None

        def terminate(self):
            started.append("terminate")

        def wait(self, timeout=None): ...

    monkeypatch.setattr(r, "is_up", lambda url, timeout=1.5: up["v"])
    monkeypatch.setattr(r, "find_binary", lambda: "ollama")
    monkeypatch.setattr(r.subprocess, "Popen", lambda *a, **k: (started.append("popen"), up.__setitem__("v", True), P())[2])
    monkeypatch.setattr(r, "_proc", None)
    assert r.ensure_running("http://127.0.0.1:11434") and started == ["popen"]
    assert r.stop() and started == ["popen", "terminate"]
    assert not r.stop()  # nada mais a encerrar


def test_runner_nao_encerra_ollama_que_ja_estava_aberto(monkeypatch):
    from fidus.core.providers import ollama_runner as r

    monkeypatch.setattr(r, "is_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(r, "_proc", None)
    assert r.ensure_running("http://127.0.0.1:11434") and not r.stop()
