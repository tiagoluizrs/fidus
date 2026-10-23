"""Adaptador do Gemini (Google AI Studio). Só biblioteca padrão: HTTP direto na API `generateContent`.

A chave é da própria pessoa (cofre do Windows). No plano GRÁTIS o Google pode usar o conteúdo enviado para melhorar os
produtos dele: a tela avisa antes de escolher este provedor.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable

from .base import Message, Response, ToolCall, ToolSpec

BASE = "https://generativelanguage.googleapis.com/v1beta"
MAX_TOKENS = 1024
# O Gemini aceita só um subconjunto do JSON Schema nas ferramentas: o resto é removido antes de enviar.
_SCHEMA_KEYS = {"type", "format", "description", "nullable", "enum", "properties", "required", "items", "minItems", "maxItems", "minimum", "maximum", "anyOf"}


class GeminiError(RuntimeError):
    pass


_NOT_CHAT = re.compile(r"(tts|live|embed|image|audio|robotics|transcribe|native|computer-use|veo|imagen|aqa|learnlm|vision|translate)", re.I)


def list_models(key: str, opener: Callable = urllib.request.urlopen, timeout_s: float = 20.0) -> list[str]:
    """Modelos que ESTA chave pode usar para conversar (a lista do Google muda com o tempo), do melhor para o pior."""
    req = urllib.request.Request(f"{BASE}/models?pageSize=200", headers={"x-goog-api-key": key})
    try:
        with opener(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise GeminiError(_http_message(e)) from e
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, ValueError) as e:
        raise GeminiError("Não consegui falar com o Gemini. Confira a internet.") from e
    names = []
    for m in data.get("models", []):
        name = str(m.get("name", "")).removeprefix("models/")
        if name.startswith("gemini-") and "generateContent" in (m.get("supportedGenerationMethods") or []) and not _NOT_CHAT.search(name):
            names.append(name)
    return sorted(set(names), key=_rank, reverse=True)


def _rank(name: str) -> tuple:
    """Prefere o 'flash' (rápido, grátis e bom o bastante) estável e mais novo; 'lite' e 'preview' ficam depois."""
    version = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return ("flash" in name and "lite" not in name, not re.search(r"preview|exp", name), float(version.group(1)) if version else 0.0, "pro" in name)


class GeminiProvider:
    kind = "gemini"
    local = False

    def __init__(self, model: str, key: Callable[[], str | None], opener: Callable = urllib.request.urlopen, timeout_s: float = 120.0):
        self.model = model
        self._key, self._open, self.timeout_s = key, opener, timeout_s

    # ---- API do provedor ----

    def complete(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> Response:
        return self._generate(system, messages, tools, None)

    def complete_stream(self, system: str, messages: list[Message], tools: list[ToolSpec], on_text: Callable[[str], None]) -> Response:
        return self._generate(system, messages, tools, on_text)

    def check_key(self) -> str:
        r = self._generate("Responda apenas: ok", [Message("user", text="ok")], [], None)
        return r.text

    def _generate(self, system, messages, tools, on_text, _retry: bool = True) -> Response:
        key = self._key()
        if not key:
            raise GeminiError("Falta a chave do Gemini (Configurações > Modelo de IA).")
        body: dict = {
            "systemInstruction": {"parts": [{"text": str(system)}]},
            "contents": _to_contents(messages),
            "generationConfig": {"maxOutputTokens": MAX_TOKENS},
        }
        if tools:
            body["tools"] = [{"functionDeclarations": [{"name": t.name, "description": t.description, "parameters": _clean_schema(t.parameters)} for t in tools]}]
        url = f"{BASE}/models/{self.model}:streamGenerateContent?alt=sse"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
        text: list[str] = []
        calls: list[ToolCall] = []
        try:
            with self._open(req, timeout=self.timeout_s) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = json.loads(line[5:].strip() or "{}")
                    for cand in chunk.get("candidates", []):
                        for part in (cand.get("content") or {}).get("parts", []):
                            if part.get("thought"):  # resumo do raciocínio do modelo: não vai para a tela
                                continue
                            if "functionCall" in part:
                                fc = part["functionCall"]
                                calls.append(ToolCall(f"gemini_{len(calls)}", str(fc.get("name", "")), dict(fc.get("args") or {}), extra=part))
                            elif part.get("text"):
                                text.append(part["text"])
                                if on_text:
                                    on_text(part["text"])
                    if chunk.get("promptFeedback", {}).get("blockReason"):
                        raise GeminiError("O Gemini recusou este pedido (conteúdo bloqueado pelo filtro dele).")
        except urllib.error.HTTPError as e:
            if e.code == 404 and _retry and (best := self._best_available(key)):
                self.model = best  # o modelo salvo não existe para esta chave: usa o melhor que ela enxerga e tenta de novo
                return self._generate(system, messages, tools, on_text, _retry=False)
            raise GeminiError(_http_message(e)) from e
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise GeminiError("Não consegui falar com o Gemini. Confira a internet.") from e
        return Response(text="".join(text), tool_calls=calls)

    def _best_available(self, key: str) -> str | None:
        try:
            models = list_models(key, self._open)
        except GeminiError:
            return None
        return models[0] if models and self.model not in models else None


def _clean_schema(node):
    """Mantém só o que o Gemini entende. Os NOMES das propriedades são preservados (só as palavras do esquema são filtradas)."""
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k not in _SCHEMA_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {name: _clean_schema(sub) for name, sub in v.items()}
        elif k == "anyOf" and isinstance(v, list):
            out[k] = [_clean_schema(sub) for sub in v]
        elif k == "items":
            out[k] = _clean_schema(v)
        else:
            out[k] = v
    return out


def _to_contents(messages: list[Message]) -> list[dict]:
    names: dict[str, str] = {}
    out: list[dict] = []
    for m in messages:
        if m.role == "assistant":
            parts: list[dict] = [{"text": m.text}] if m.text else []
            for c in m.tool_calls:
                names[c.id] = c.name
                parts.append(c.extra if c.extra else {"functionCall": {"name": c.name, "args": c.arguments}})
            out.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif m.tool_results:
            out.append({"role": "user", "parts": [
                {"functionResponse": {"name": names.get(r.call_id, ""), "response": {"error" if r.is_error else "result": r.content}}} for r in m.tool_results
            ]})
        else:
            out.append({"role": "user", "parts": [{"text": m.text}]})
    return out


def _http_message(e: urllib.error.HTTPError) -> str:
    try:
        detail = str(json.loads(e.read()).get("error", {}).get("message", ""))
    except (ValueError, OSError, AttributeError):
        detail = ""
    low = detail.lower()
    if e.code in (400, 401, 403) and ("api key" in low or "api_key" in low or e.code in (401, 403)):
        return "A chave do Gemini não foi aceita. Confira se copiou inteira (Google AI Studio > Get API key)."
    if e.code == 404:
        return "Esse modelo do Gemini não existe ou não está disponível para a sua chave. Escolha outro."
    if e.code == 429:
        return "Você atingiu o limite do plano grátis do Gemini. Espere um pouco, troque de modelo ou use outro provedor."
    if e.code >= 500:
        return "O Gemini está instável agora. Tente de novo em instantes."
    return f"O Gemini respondeu com erro {e.code}. {detail}".strip()
