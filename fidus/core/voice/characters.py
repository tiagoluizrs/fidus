"""Registro de personagens. Aqui só o nome; a personalidade de cada um vem na etapa 3."""

from __future__ import annotations

from ..config import WakeWord

CHARACTERS = ("alfred", "donna", "jarbis")
DEFAULT_CHARACTER = "alfred"  # também é quem responde ao atalho de teclado


def character_for(word: WakeWord | None, default: str = DEFAULT_CHARACTER) -> str:
    """Personagem chamado por uma palavra; sem palavra (atalho) ou personagem desconhecido, o padrão."""
    name = (word.character if word else default).lower()
    return name if name in CHARACTERS else default
