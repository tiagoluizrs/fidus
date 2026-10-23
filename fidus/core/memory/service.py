"""Memória única, compartilhada entre os personagens: Markdown (lembranças) + SQLite (histórico e resumos)."""

from __future__ import annotations

from ..actionlog import ActionLog
from ..config import Config
from .db import Database, open_database
from .markdown_store import Entry, MarkdownMemory

_cache: dict[str, MemoryService] = {}


def get_memory(config: Config) -> MemoryService:
    """Uma instância por pasta de dados, para a ferramenta `memoria`, o orquestrador e a CLI compartilharem."""
    key = str(config.data_dir)
    if key not in _cache:
        _cache[key] = MemoryService(config)
    return _cache[key]


class MemoryService:
    def __init__(self, config: Config, db: Database | None = None):
        self.config = config
        self.md = MarkdownMemory(config.memory_dir)
        self._db = db

    @property
    def db(self) -> Database:  # só abre (e cria) o banco quando alguém precisa
        if self._db is None:
            self._db = open_database(self.config.db_path, self.config.memory.encrypt, log=ActionLog(self.config.log_path))
        return self._db

    # ---- trecho relevante para o prompt ----

    def context_for(self, query: str, max_chars: int | None = None) -> str:
        """Só o que importa para este pedido, com limite de tamanho: o perfil (até 40 % do limite)
        e as lembranças que casam com o pedido. Nunca a memória inteira."""
        budget = max_chars if max_chars is not None else self.config.memory.max_context_chars
        lines: list[str] = []
        used: set[str] = set()
        total = 0

        def add(e: Entry, cap: int) -> bool:
            nonlocal total
            line = f"- [{e.section}] {e.text}" + (f" ({e.tag})" if e.tag else "")
            if total + len(line) + 1 > cap:
                return False
            lines.append(line)
            used.add(e.id)
            total += len(line) + 1
            return True

        for e in self.md.list("perfil"):
            if not add(e, int(budget * 0.4)):
                break
        for e in self.md.search(query, limit=12):
            if e.id not in used and not add(e, budget):
                break
        return "\n".join(lines)

    # ---- atalhos ----

    def forget_everything(self) -> dict:
        return {"lembrancas": self.md.delete_all(), "mensagens": self.db.clear_history()}
