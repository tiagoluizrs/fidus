"""rascunho_email: cria um RASCUNHO no Gmail (escrita, sempre com confirmação). Não existe envio direto na v1."""

from __future__ import annotations

from ..services.base import NotConnected
from ..services.registry import get_hub
from .base import Risk, Tool, ToolError

MAX_BODY = 5000


class RascunhoEmail(Tool):
    name = "rascunho_email"
    description = (
        "Cria um rascunho de e-mail (não envia). O usuário confirma antes e envia por conta própria depois. "
        "Opcionalmente responde a um e-mail existente (responder_a = id)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "para": {"type": "string", "description": "Endereço do destinatário"},
            "assunto": {"type": "string"},
            "corpo": {"type": "string"},
            "responder_a": {"type": "string", "description": "Id do e-mail a ser respondido (opcional)"},
        },
        "required": ["para", "assunto", "corpo"],
    }
    risk = Risk.ESCRITA  # nunca dispensado de confirmação

    def precheck(self, args, config) -> None:
        if not config.accounts.gmail_drafts:
            raise NotConnected("Criar rascunhos não está liberado. Rode: uv run fidus accounts connect gmail --escrita")

    def run(self, args, config) -> str:
        body = str(args.get("corpo", ""))
        if not body.strip():
            raise ToolError("O corpo do e-mail está vazio.")
        draft_id = get_hub(config).email().create_draft(
            str(args.get("para", "")), str(args.get("assunto", "")), body[:MAX_BODY], args.get("responder_a") or None
        )
        return f"Rascunho criado (id {draft_id}). Nada foi enviado: o usuário revisa e envia pelo Gmail."


TOOL = RascunhoEmail()
