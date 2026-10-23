"""Divide o texto que chega em streaming em frases, para a voz começar sem esperar o fim."""

from __future__ import annotations

import re

_END = re.compile(r"[.!?…]+[\"')\]]*(?=\s)|\n+")
_ABBREV = {"dr", "dra", "sr", "sra", "srta", "prof", "profa", "av", "etc", "ex", "obs", "nº", "n"}
_MARKDOWN = re.compile(r"[*_`#>]+|^\s*[-•]\s+", re.MULTILINE)


def clean_for_speech(text: str) -> str:
    """Tira marcação de Markdown e espaços repetidos, que a voz leria em voz alta."""
    return re.sub(r"\s+", " ", _MARKDOWN.sub("", text)).strip()


class SentenceSplitter:
    """Acumula trechos e devolve cada frase assim que ela fecha. `flush()` entrega o resto."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> list[str]:
        self._buf += chunk
        out: list[str] = []
        start = 0
        for m in _END.finditer(self._buf):
            end = m.end()
            piece = self._buf[start:end]
            if self._is_abbreviation(piece):
                continue
            start = end
            if (s := clean_for_speech(piece)):
                out.append(s)
        self._buf = self._buf[start:]
        return out

    def flush(self) -> str | None:
        rest, self._buf = clean_for_speech(self._buf), ""
        return rest or None

    @staticmethod
    def _is_abbreviation(piece: str) -> bool:
        stripped = piece.rstrip()
        if not stripped.endswith(".") or stripped.endswith(".."):
            return False
        last = stripped.rsplit(None, 1)[-1].rstrip(".").lower()
        return last in _ABBREV
