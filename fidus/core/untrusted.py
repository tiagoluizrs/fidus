"""Conteúdo externo (e-mail, mensagem, evento, nome de arquivo) entra sempre como dado delimitado."""

from __future__ import annotations

import re

TAG = "dado_externo"
_TAG_RE = re.compile(rf"<\s*/?\s*{TAG}", re.IGNORECASE)


def wrap(source: str, text: str) -> str:
    """Delimita `text` e neutraliza qualquer tentativa de fechar/abrir a tag de dentro dele."""
    safe = _TAG_RE.sub("[tag removida]", text)
    return f'<{TAG} origem="{source}">\n{safe}\n</{TAG}>'


def delimit(tag: str, text: str, **attrs: str) -> str:
    """Delimita texto de qualquer origem (instruções extras, memória, resumo) como dado dentro de `<tag>`.

    Qualquer abertura/fechamento da mesma tag dentro do texto é neutralizado, então o texto não escapa.
    """
    safe = re.sub(rf"<\s*/?\s*{re.escape(tag)}", "[tag removida]", text, flags=re.IGNORECASE)
    extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
    return f"<{tag}{extra}>\n{safe}\n</{tag}>"
