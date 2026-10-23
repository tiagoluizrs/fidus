"""Adaptador do Slack para `ChatService`, direto na API Web (sem dependência nova).

Token de usuário no Gerenciador de Credenciais (SLACK_TOKEN). Só lê e responde nos canais/conversas permitidos
(`[contas.slack] canais_permitidos`); responder exige `escrita = true` e a ferramenta sempre pede confirmação.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime

from .. import secrets as vault
from ..config import Config
from .base import Channel, ChatMessage, NotConnected, clip

API = "https://slack.com/api/"
_ERRORS = {
    "invalid_auth": "O token do Slack é inválido ou foi revogado.",
    "token_revoked": "O token do Slack foi revogado.",
    "not_authed": "Falta o token do Slack.",
    "missing_scope": "O app do Slack não tem o escopo necessário. Veja docs/INTEGRACOES.md.",
    "channel_not_found": "Canal não encontrado (ou o app não participa dele).",
    "not_in_channel": "O app não participa deste canal.",
}


def _http(url: str, data: bytes | None, headers: dict) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (https fixo)
        return json.loads(r.read().decode("utf-8"))


class Slack:
    _cache_key: tuple[str, ...] = ()

    def __init__(self, config: Config, token: str | None = None, http: Callable[[str, bytes | None, dict], dict] = _http):
        self.config = config
        self._token = token
        self._http = http
        self._users: dict[str, str] = {}
        self._allowed_cache: list[Channel] | None = None

    @property
    def token(self) -> str:
        tok = self._token or vault.get_secret(vault.SLACK_TOKEN)
        if not tok:
            raise NotConnected("Slack não conectado. Rode: uv run fidus accounts connect slack")
        return tok

    def _call(self, method: str, params: dict | None = None, post: bool = False) -> dict:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"Authorization": f"Bearer {self.token}"}
        if post:
            data = json.dumps(params).encode()
            headers["Content-Type"] = "application/json; charset=utf-8"
            out = self._http(API + method, data, headers)
        else:
            out = self._http(API + method + "?" + urllib.parse.urlencode(params), None, headers)
        if not out.get("ok"):
            err = out.get("error", "erro_desconhecido")
            raise NotConnected(_ERRORS.get(err, f"Erro do Slack: {err}"))
        return out

    def _user_name(self, uid: str) -> str:
        if uid not in self._users:
            try:
                u = self._call("users.info", {"user": uid})["user"]
                self._users[uid] = u.get("real_name") or u.get("name") or uid
            except NotConnected:
                self._users[uid] = uid
        return self._users[uid]

    def channels(self) -> list[Channel]:
        key = tuple(self.config.accounts.slack_channels)
        if self._allowed_cache is None or key != self._cache_key:  # lista mudou na tela: não usa a antiga
            self._cache_key = key
            wanted = {c.lower().lstrip("#") for c in self.config.accounts.slack_channels}
            found: list[Channel] = []
            cursor = None
            for _ in range(5):  # no máximo 5 páginas
                out = self._call("conversations.list", {"types": "public_channel,private_channel,mpim,im", "limit": 200, "cursor": cursor})
                for c in out.get("channels", []):
                    name = c.get("name") or (self._user_name(c["user"]) if c.get("is_im") else c["id"])
                    if {c["id"].lower(), name.lower()} & wanted:
                        found.append(Channel(c["id"], name, bool(c.get("is_private") or c.get("is_im") or c.get("is_mpim"))))
                cursor = out.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            self._allowed_cache = found
        return self._allowed_cache

    def _resolve(self, channel: str) -> Channel:
        key = channel.strip().lower().lstrip("#")
        for attempt in range(2):
            for c in self.channels():
                if key in {c.id.lower(), c.name.lower()}:
                    return c
            self._allowed_cache = None  # não achou: confere de novo no Slack (canal novo, ou o app ganhou acesso agora)
        raise NotConnected(f"'{channel}' não está na lista de canais permitidos ([contas.slack] canais_permitidos).")

    def read(self, channel: str, limit: int, text_chars: int) -> list[ChatMessage]:
        ch = self._resolve(channel)
        msgs = self._call("conversations.history", {"channel": ch.id, "limit": limit}).get("messages", [])
        out = []
        for m in msgs[:limit]:
            when = datetime.fromtimestamp(float(m["ts"])).strftime("%d/%m %H:%M") if "ts" in m else ""
            author = self._user_name(m["user"]) if m.get("user") else (m.get("username") or "bot")
            out.append(ChatMessage(m.get("ts", ""), ch.name, author, clip(m.get("text", ""), text_chars), when))
        return out

    def reply(self, channel: str, text: str, thread_ts: str | None = None) -> str:
        if not self.config.accounts.slack_write:
            raise NotConnected("Responder no Slack não está liberado. Ative `escrita = true` em [contas.slack] "
                               "ou rode: uv run fidus accounts connect slack --escrita")
        ch = self._resolve(channel)
        out = self._call("chat.postMessage", {"channel": ch.id, "text": text[:2000], "thread_ts": thread_ts}, post=True)
        return out.get("ts", "")
