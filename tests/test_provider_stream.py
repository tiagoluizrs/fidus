from types import SimpleNamespace as NS

from fidus.core.providers.anthropic import AnthropicProvider
from fidus.core.providers.base import Message


class FakeStream:
    text_stream = iter(["Olá", ", mundo"])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return NS(content=[NS(type="text", text="Olá, mundo"), NS(type="tool_use", id="t1", name="x", input={"a": 1})])


def test_complete_stream_entrega_trechos_e_monta_a_resposta():
    p = AnthropicProvider("m")
    seen = {}

    def stream(**kw):
        seen.update(kw)
        return FakeStream()

    p._client = NS(messages=NS(stream=stream))
    chunks = []
    r = p.complete_stream("sys", [Message("user", text="oi")], [], chunks.append)
    assert chunks == ["Olá", ", mundo"]
    assert r.text == "Olá, mundo" and r.tool_calls[0].name == "x"
    assert seen["model"] == "m" and "tools" not in seen
