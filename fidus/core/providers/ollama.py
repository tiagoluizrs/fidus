"""Adaptador do Ollama (modelo local). Só biblioteca padrão: nenhuma dependência nova.

Fala apenas com o próprio computador (`127.0.0.1`/`localhost`): nada do que o modelo recebe sai da máquina.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

from .base import Message, Response, ToolCall, ToolSpec

DEFAULT_URL = "http://127.0.0.1:11434"
MAX_TOKENS = 1024
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def check_local_url(url: str) -> str:
    """Só endereços da própria máquina. Evita mandar a conversa para um servidor de fora por engano (ou por ataque)."""
    parts = urlsplit(url.strip())
    if parts.scheme != "http" or (parts.hostname or "") not in LOCAL_HOSTS or parts.username or parts.password:
        raise ValueError("O endereço do Ollama precisa ser do próprio computador (http://127.0.0.1:11434).")
    return f"http://{parts.hostname if parts.hostname != '::1' else '[::1]'}:{parts.port or 11434}"


class OllamaError(RuntimeError):
    pass


class OllamaProvider:
    kind = "local"
    local = True  # o orquestrador limita as ações deste provedor enquanto o usuário não liberar (ver config)

    def __init__(self, model: str, url: str = DEFAULT_URL, timeout_s: float = 120.0):
        self.model = model
        self.url = check_local_url(url)
        self.timeout_s = timeout_s

    # ---- API do provedor ----

    def complete(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Response:
        return self._chat(system, messages, tools, None)

    def complete_stream(
        self, system: str, messages: list[Message], tools: list[ToolSpec], on_text: Callable[[str], None]
    ) -> Response:
        return self._chat(system, messages, tools, on_text)

    def _chat(self, system, messages, tools, on_text) -> Response:
        body = {
            "model": self.model,
            "stream": True,
            "messages": [{"role": "system", "content": str(system)}, *_to_api(messages)],
            "options": {"num_predict": MAX_TOKENS},
        }
        if tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools
            ]
        text: list[str] = []
        held: list[str] = []  # modelos pequenos às vezes ESCREVEM a chamada de ferramenta como JSON no texto: seguramos para conferir
        calls: list[ToolCall] = []
        try:
            with self._open("/api/chat", body) as resp:
                for raw in resp:
                    if not raw.strip():
                        continue
                    chunk = json.loads(raw)
                    if chunk.get("error"):
                        raise OllamaError(_friendly(str(chunk["error"]), self.model))
                    msg = chunk.get("message") or {}
                    if msg.get("content"):
                        piece = msg["content"]
                        text.append(piece)
                        if on_text:
                            if held or ("".join(text).lstrip().startswith("{") and tools):
                                held.append(piece)
                            else:
                                on_text(piece)
                    for tc in msg.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):  # alguns modelos devolvem o JSON como texto
                            args = _loads_dict(args)
                        calls.append(ToolCall(f"local_{len(calls)}", str(fn.get("name", "")), dict(args)))
        except urllib.error.HTTPError as e:
            raise OllamaError(_friendly(_http_error_text(e), self.model)) from e
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise OllamaError(
                f"Não consegui falar com o Ollama em {self.url}. Ele está aberto? (Abra o app do Ollama ou rode `ollama serve`.)"
            ) from e
        full = "".join(text)
        if tools and not calls and full.lstrip().startswith("{") and (as_call := _text_tool_call(full, {t.name for t in tools})):
            return Response(text="", tool_calls=[as_call])
        if held and on_text:
            on_text("".join(held))  # era só texto que começava com "{"
        return Response(text=full, tool_calls=calls)

    # ---- utilitários para a tela de Configurações ----

    def list_models(self) -> list[str]:
        """Nomes dos modelos já baixados. Lança OllamaError se o Ollama não estiver rodando."""
        return list_models(self.url)

    def _open(self, path: str, body: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=self.timeout_s)  # noqa: S310 - endereço validado por check_local_url


def list_models(url: str = DEFAULT_URL, timeout_s: float = 3.0) -> list[str]:
    url = check_local_url(url)
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=timeout_s) as resp:  # noqa: S310
            data = json.loads(resp.read())
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError) as e:
        raise OllamaError(f"O Ollama não respondeu em {url}.") from e
    return sorted(str(m.get("name")) for m in data.get("models", []) if m.get("name"))


MODEL_NAME = __import__("re").compile(r"[A-Za-z0-9][A-Za-z0-9._:/\-]{0,98}")


def pull_model(url: str, model: str, progress=None, opener=urllib.request.urlopen, timeout_s: float = 3600.0) -> None:
    """Baixa um modelo pelo próprio Ollama (o mesmo que `ollama pull`). `progress(feito, total)` em bytes."""
    url = check_local_url(url)
    if not MODEL_NAME.fullmatch(model):
        raise OllamaError("Nome de modelo inválido. Use algo como llama3.2:3b.")
    req = urllib.request.Request(url + "/api/pull", data=json.dumps({"model": model, "stream": True}).encode(), headers={"Content-Type": "application/json"})
    try:
        with opener(req, timeout=timeout_s) as resp:
            ok = False
            for raw in resp:
                if not raw.strip():
                    continue
                chunk = json.loads(raw)
                if chunk.get("error"):
                    raise OllamaError(_friendly(str(chunk["error"]), model))
                if progress and chunk.get("total"):
                    progress(int(chunk.get("completed", 0)), int(chunk["total"]))
                ok = ok or chunk.get("status") == "success"
            if not ok:
                raise OllamaError(f"O download de {model} não terminou. Tente de novo.")
    except urllib.error.HTTPError as e:
        raise OllamaError(_friendly(_http_error_text(e), model)) from e
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise OllamaError(f"Não consegui falar com o Ollama em {url}. Ele está aberto?") from e


def _to_api(messages: list[Message]) -> list[dict]:
    """Converte o histórico. O Ollama não usa ids: o resultado de uma ferramenta aponta para ela pelo nome."""
    names: dict[str, str] = {}
    out: list[dict] = []
    for m in messages:
        if m.role == "assistant":
            entry: dict = {"role": "assistant", "content": m.text}
            if m.tool_calls:
                entry["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in m.tool_calls]
                names.update({c.id: c.name for c in m.tool_calls})
            out.append(entry)
        elif m.tool_results:
            out += [{"role": "tool", "tool_name": names.get(r.call_id, ""), "content": r.content} for r in m.tool_results]
        else:
            out.append({"role": "user", "content": m.text})
    return out


def _text_tool_call(text: str, names: set[str]) -> ToolCall | None:
    """Reconhece "{"type":"function","function":{"name":...,"parameters":{...}}}" (ou só {"name":...,"parameters":...}) no texto."""
    data = _loads_dict(text.strip())
    fn = data.get("function") if isinstance(data.get("function"), dict) else data
    name = fn.get("name")
    args = fn.get("parameters", fn.get("arguments", {}))
    if isinstance(args, str):
        args = _loads_dict(args)
    if isinstance(name, str) and name in names and isinstance(args, dict):
        return ToolCall("local_text_0", name, dict(args))
    return None


def _loads_dict(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _http_error_text(e: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(e.read()).get("error", e.reason))
    except (ValueError, OSError):
        return str(e.reason)


def _friendly(error: str, model: str) -> str:
    low = error.lower()
    if "not found" in low:
        return f"O modelo '{model}' não está baixado. No terminal: ollama pull {model}"
    if "file does not exist" in low or "manifest" in low and "pull" in low:
        return f"O modelo '{model}' não existe no catálogo do Ollama. Confira o nome (ex.: llama3.2:3b)."
    if "does not support tools" in low:
        return f"O modelo '{model}' não suporta ferramentas. Escolha outro (por exemplo qwen3:8b ou llama3.1:8b)."
    return f"O Ollama respondeu com erro: {error}"
