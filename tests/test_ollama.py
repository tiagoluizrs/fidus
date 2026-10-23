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
