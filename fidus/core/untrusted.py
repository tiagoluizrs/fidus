"""Conteúdo externo (e-mail, mensagem, evento, nome de arquivo) entra sempre como dado delimitado."""

from __future__ import annotations

import re

TAG = "dado_externo"
_TAG_RE = re.compile(rf"<\s*/?\s*{TAG}", re.IGNORECASE)


def wrap(source: str, text: str) -> str:
    """Delimita `text` e neutraliza qualquer tentativa de fechar/abrir a tag de dentro dele."""
    safe = _TAG_RE.sub("[tag removida]", text)
    return f'<{TAG} origem="{source}">\n{safe}\n</{TAG}>'
