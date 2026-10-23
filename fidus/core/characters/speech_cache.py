"""Cache em disco das falas curtas (início): o áudio é gerado uma vez com a voz do personagem e reaproveitado.

A chave é (personagem, frase, voz). Se a frase ou qualquer ajuste de voz muda, o hash muda e o áudio é gerado de
novo; os arquivos que deixaram de valer são removidos por `prune`.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from pathlib import Path

from .models import Voice


def voice_fingerprint(voice: Voice, base_rate: int = 0, voice_name: str = "") -> str:
    return f"{voice.engine}|{voice.voice}|{voice_name}|{voice.pitch}|{voice.rate}|{base_rate}|{voice.effect}|{voice.timbre}|{voice.edge}|{voice.pronunciations}"


class SpeechCache:
    def __init__(self, root: Path, synth: Callable[[str, Path], bool]):
        self.root, self.synth = Path(root), synth
        self._lock = threading.Lock()

    def key(self, character: str, text: str, fingerprint: str) -> str:
        return hashlib.sha256(f"{character}\0{text}\0{fingerprint}".encode()).hexdigest()[:24]

    def path(self, character: str, text: str, fingerprint: str) -> Path:
        return self.root / character / f"{self.key(character, text, fingerprint)}.wav"

    def lookup(self, character: str, text: str, fingerprint: str) -> Path | None:
        p = self.path(character, text, fingerprint)
        return p if p.is_file() and p.stat().st_size > 44 else None

    def get(self, character: str, text: str, fingerprint: str) -> Path | None:
        """Caminho do áudio; gera se ainda não existe. None se o motor não consegue gerar arquivos."""
        if (hit := self.lookup(character, text, fingerprint)) is not None:
            return hit
        p = self.path(character, text, fingerprint)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        with self._lock:  # o motor de voz é um só: gera uma frase por vez
            try:
                ok = self.synth(text, tmp)
            except Exception:
                tmp.unlink(missing_ok=True)
                return None
            if not ok or not tmp.is_file():
                tmp.unlink(missing_ok=True)
                return None
            tmp.replace(p)
        return p

    def warm(self, character: str, texts: list[str], fingerprint: str) -> int:
        """Pré-gera as falas e apaga as antigas deste personagem. Devolve quantas foram geradas agora."""
        made = 0
        keep: set[str] = set()
        for t in texts:
            existed = self.lookup(character, t, fingerprint) is not None
            p = self.get(character, t, fingerprint)
            if p is not None:
                keep.add(p.name)
                made += 0 if existed else 1
        self.prune(character, keep)
        return made

    def prune(self, character: str, keep: set[str]) -> int:
        d = self.root / character
        removed = 0
        if d.is_dir():
            for f in d.glob("*.wav"):
                if f.name not in keep:
                    f.unlink(missing_ok=True)
                    removed += 1
        return removed

    def clear(self) -> int:
        n = 0
        if self.root.is_dir():
            for f in self.root.rglob("*.wav"):
                f.unlink(missing_ok=True)
                n += 1
        return n
