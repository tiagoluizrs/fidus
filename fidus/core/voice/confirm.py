"""Confirmação por voz: o Fidus pergunta falando e entende "sim" ou "não". Na dúvida, cai no teclado."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

from ..permissions import Confirmer

_YES = {"sim", "claro", "pode", "confirmo", "isso", "ok", "okay", "autorizo", "positivo", "permito", "vai", "manda"}
_NO = {"nao", "negativo", "cancela", "cancelar", "para", "pare", "nunca", "jamais", "deixa"}


def _tokens(text: str) -> list[str]:
    plain = unicodedata.normalize("NFD", text.lower())
    plain = "".join(c for c in plain if unicodedata.category(c) != "Mn")
    return "".join(c if c.isalnum() or c.isspace() else " " for c in plain).split()


def parse_yes_no(text: str | None) -> bool | None:
    """True = sim, False = não, None = não entendi ou ambíguo ("pode não"). Ambíguo nunca vale como sim."""
    if not text:
        return None
    words = set(_tokens(text))
    yes, no = bool(words & _YES), bool(words & _NO)
    if yes == no:
        return None
    return yes


class VoiceConfirmer:
    """Implementa `Confirmer`. `speak` fala e espera terminar; `listen(timeout)` devolve o texto ouvido ou None."""

    def __init__(
        self,
        speak: Callable[[str], None],
        listen: Callable[[float], str | None],
        fallback: Confirmer,
        timeout_s: float = 8.0,
        notify: Callable[[str], None] = print,
        intro: Callable[[], str] | None = None,
    ):
        self.speak, self.listen, self.fallback = speak, listen, fallback
        self.timeout_s, self.notify = timeout_s, notify
        self.intro = intro  # fala do personagem para o momento "confirmar" (ex.: "Posso prosseguir, senhor?")

    def __call__(self, prompt: str) -> bool:
        answer = None
        try:
            lead = (self.intro() if self.intro else "") or ""
            self.speak(f"{lead} {prompt} Diga sim ou não.".strip())
            answer = parse_yes_no(self.listen(self.timeout_s))
        except Exception as e:  # microfone ocupado, falha do STT etc.: nunca decide sozinho
            self.notify(f"(confirmação por voz falhou: {type(e).__name__})")
        if answer is not None:
            return answer
        self.notify("Não entendi a resposta por voz. Responda no teclado.")
        return self.fallback(prompt)
