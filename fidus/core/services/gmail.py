"""Adaptador do Gmail para `EmailService`: buscar, ler trechos e criar RASCUNHO. Não existe envio aqui."""

from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from html.parser import HTMLParser

from ..config import Config
from . import google_auth
from .base import EmailItem, NotConnected, clip

_ADDR = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    return " ".join("".join(p.parts).split())


def _headers(msg: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _body_text(payload: dict) -> str:
    """Texto do corpo (prefere text/plain; senão HTML sem marcação). Anexos são ignorados."""
    found: dict[str, str] = {}

    def walk(part: dict) -> None:
        if part.get("filename"):  # anexo
            return
        mime, data = part.get("mimeType", ""), part.get("body", {}).get("data")
        if data and mime in ("text/plain", "text/html"):
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            found.setdefault(mime, raw)
        for sub in part.get("parts", []):
            walk(sub)

    walk(payload)
    if "text/plain" in found:
        return " ".join(found["text/plain"].split())
    return html_to_text(found["text/html"]) if "text/html" in found else ""


class Gmail:
    def __init__(self, config: Config, service=None):
        self.config = config
        self._service = service

    @property
    def service(self):
        if self._service is None:
            from googleapiclient.discovery import build  # pesado: só aqui

            self._service = build("gmail", "v1", credentials=google_auth.credentials(self.config, "gmail"), cache_discovery=False)
        return self._service

    def _item(self, msg: dict, snippet: str) -> EmailItem:
        h = _headers(msg)
        return EmailItem(msg["id"], h.get("from", ""), h.get("subject", "(sem assunto)"), h.get("date", ""),
                         snippet, "UNREAD" in msg.get("labelIds", []))

    def search(self, query: str, limit: int, snippet_chars: int) -> list[EmailItem]:
        users = self.service.users()
        listing = users.messages().list(userId="me", q=query, maxResults=limit).execute()
        items = []
        for ref in listing.get("messages", [])[:limit]:
            msg = users.messages().get(userId="me", id=ref["id"], format="metadata",
                                       metadataHeaders=["From", "Subject", "Date"]).execute()
            items.append(self._item(msg, clip(msg.get("snippet", ""), snippet_chars)))
        return items

    def read(self, email_id: str, max_chars: int) -> EmailItem:
        msg = self.service.users().messages().get(userId="me", id=email_id, format="full").execute()
        return self._item(msg, clip(_body_text(msg.get("payload", {})), max_chars))

    def create_draft(self, to: str, subject: str, body: str, reply_to_id: str | None = None) -> str:
        write_scope = google_auth.scopes_for("gmail", True)[-1]
        if not self.config.accounts.gmail_drafts or write_scope not in google_auth.granted_scopes("gmail"):
            raise NotConnected("Criar rascunhos não está liberado. Rode: uv run fidus accounts connect gmail --escrita")
        if not _ADDR.match(to.strip()):
            raise NotConnected(f"Destinatário inválido: '{to}'.")
        if "\n" in subject or "\r" in subject:
            raise NotConnected("Assunto inválido.")
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to.strip(), subject.strip()
        msg.set_content(body)
        payload: dict = {}
        if reply_to_id:
            orig = self.service.users().messages().get(userId="me", id=reply_to_id, format="metadata",
                                                       metadataHeaders=["Message-ID", "Subject"]).execute()
            mid = _headers(orig).get("message-id")
            if mid:
                msg["In-Reply-To"], msg["References"] = mid, mid
            payload["threadId"] = orig.get("threadId")
        payload["raw"] = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = self.service.users().drafts().create(userId="me", body={"message": payload}).execute()
        return draft["id"]
