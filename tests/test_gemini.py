import io
import json
import urllib.error

import pytest

from fidus.core.config import Config
from fidus.core.providers import create_provider, sync_provider
from fidus.core.providers.base import Message, ToolCall, ToolResult, ToolSpec
from fidus.core.providers.gemini import BASE, GeminiError, GeminiProvider, _clean_schema, _to_contents


class Resp:
    def __init__(self, lines):
        self._lines = [line.encode() + b"\n" for line in lines]

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sse(*chunks):
    return Resp([f"data: {json.dumps(c)}" for c in chunks])


def part_chunk(*parts):
    return {"candidates": [{"content": {"role": "model", "parts": list(parts)}}]}


def make(responses, key="AIza" + "x" * 35):
    seen = []

    def opener(req, timeout=None):
        seen.append(req)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    return GeminiProvider("gemini-2.5-flash", lambda: key, opener), seen


AGENDA = ToolSpec(
    "agenda", "Agenda",
    {"type": "object", "additionalProperties": False, "properties": {"acao": {"type": "string", "enum": ["ler"], "default": "ler"}}, "required": ["acao"]},
)


def test_streaming_entrega_texto_em_pedacos_e_manda_a_chave_no_cabecalho():
    p, seen = make([sse(part_chunk({"text": "Bom "}), part_chunk({"text": "dia."}))])
    got = []
    r = p.complete_stream("sys", [Message("user", text="oi")], [], got.append)
    assert got == ["Bom ", "dia."] and r.text == "Bom dia." and not r.tool_calls
    req = seen[0]
    assert req.full_url == f"{BASE}/models/gemini-2.5-flash:streamGenerateContent?alt=sse"
    assert req.get_header("X-goog-api-key").startswith("AIza")
    body = json.loads(req.data)
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]} and body["contents"] == [{"role": "user", "parts": [{"text": "oi"}]}]
    assert "tools" not in body


def test_ferramentas_vao_limpas_e_a_chamada_volta_com_o_dado_bruto():
    raw = {"functionCall": {"name": "agenda", "args": {"acao": "ler"}}, "thoughtSignature": "abc"}
    p, seen = make([sse(part_chunk(raw)), sse(part_chunk({"text": "Nada hoje."}))])
    r = p.complete("s", [Message("user", text="agenda?")], [AGENDA])
    decl = json.loads(seen[0].data)["tools"][0]["functionDeclarations"][0]
    assert decl["name"] == "agenda" and "additionalProperties" not in decl["parameters"] and "default" not in decl["parameters"]["properties"]["acao"]
    assert decl["parameters"]["properties"]["acao"]["enum"] == ["ler"] and decl["parameters"]["required"] == ["acao"]
    call = r.tool_calls[0]
    assert (call.name, call.arguments, call.extra) == ("agenda", {"acao": "ler"}, raw)
    history = [Message("user", text="agenda?"), Message("assistant", tool_calls=[call]), Message("user", tool_results=[ToolResult(call.id, "vazio")])]
    p.complete("s", history, [AGENDA])
    contents = json.loads(seen[1].data)["contents"]
    assert contents[1] == {"role": "model", "parts": [raw]}  # a assinatura volta como veio
    assert contents[2]["parts"][0] == {"functionResponse": {"name": "agenda", "response": {"result": "vazio"}}}


def test_resultado_com_erro_vai_como_error():
    c = ToolCall("g0", "agenda", {})
    out = _to_contents([Message("assistant", tool_calls=[c]), Message("user", tool_results=[ToolResult("g0", "falhou", True)])])
    assert out[1]["parts"][0]["functionResponse"]["response"] == {"error": "falhou"}


def test_nomes_das_propriedades_sao_preservados_ao_limpar_o_esquema():
    schema = {"type": "object", "properties": {"title": {"type": "string", "title": "x"}, "default": {"type": "integer", "default": 3}}, "$schema": "x"}
    assert _clean_schema(schema) == {"type": "object", "properties": {"title": {"type": "string"}, "default": {"type": "integer"}}}


def test_raciocinio_do_modelo_nao_aparece_na_tela():
    p, _ = make([sse(part_chunk({"text": "pensando...", "thought": True}), part_chunk({"text": "Resposta."}))])
    got = []
    r = p.complete_stream("s", [Message("user", text="x")], [], got.append)
    assert got == ["Resposta."] and r.text == "Resposta."


def err(code, msg=""):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(json.dumps({"error": {"message": msg}}).encode()))


@pytest.mark.parametrize("code,msg,trecho", [
    (400, "API key not valid. Please pass a valid API key.", "chave do Gemini não foi aceita"),
    (403, "", "chave do Gemini não foi aceita"),
    (404, "models/x is not found", "não existe"),
    (429, "quota", "limite do plano grátis"),
    (503, "overloaded", "instável"),
])
def test_erros_viram_mensagens_claras(code, msg, trecho):
    p, _ = make([err(code, msg)])
    with pytest.raises(GeminiError, match=trecho):
        p.complete("s", [Message("user", text="x")], [])


def test_sem_chave_e_sem_internet():
    p = GeminiProvider("m", lambda: None)
    with pytest.raises(GeminiError, match="Falta a chave"):
        p.complete("s", [Message("user", text="x")], [])
    p, _ = make([urllib.error.URLError("offline")])
    with pytest.raises(GeminiError, match="Confira a internet"):
        p.complete("s", [Message("user", text="x")], [])


def test_pedido_bloqueado_pelo_filtro_explica():
    p, _ = make([sse({"promptFeedback": {"blockReason": "SAFETY"}})])
    with pytest.raises(GeminiError, match="recusou"):
        p.complete("s", [Message("user", text="x")], [])


def test_provedor_e_troca_ao_vivo():
    cfg = Config(provider="gemini", gemini_model="gemini-2.5-pro")
    p = create_provider(cfg)
    assert p.kind == "gemini" and p.model == "gemini-2.5-pro"

    class O:
        provider = create_provider(Config())

    o = O()
    assert sync_provider(o, cfg) is True and o.provider.kind == "gemini"
    cfg.gemini_model = "gemini-2.5-flash"
    assert sync_provider(o, cfg) is False and o.provider.model == "gemini-2.5-flash"
