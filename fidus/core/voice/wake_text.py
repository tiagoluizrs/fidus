"""Reconhece, no TEXTO de uma fala, o chamado de um personagem ("ei Alfred, que horas são?")."""

from __future__ import annotations

import difflib
import re
import unicodedata


def _norm(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def match_wake(text: str, names: dict[str, str]) -> tuple[str | None, str]:
    """Procura o nome de um personagem nas primeiras palavras. Aceita variações de como o Whisper escreve ("Alfredo",
    "Dona", "Jarbas"). Devolve (id do personagem ou None, o resto do pedido)."""
    words = text.split()
    normalized = {cid: _norm(name) for cid, name in names.items()}
    for i, word in enumerate(words[:4]):
        token = re.sub(r"\W", "", _norm(word))
        if not token:
            continue
        hit = difflib.get_close_matches(token, list(normalized.values()), n=1, cutoff=0.72)
        if hit:
            cid = next(c for c, n in normalized.items() if n == hit[0])
            return cid, " ".join(words[i + 1:]).lstrip(" ,.:;!?-—").strip()
    return None, text
