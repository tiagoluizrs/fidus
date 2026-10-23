"""Log local de ações (JSON por linha). Sem telemetria: nada sai do computador."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MAX_FIELD = 200


class ActionLog:
    def __init__(self, path: Path):
        self.path = path

    def record(self, *, tool: str, risk: str, args: dict, decision: str, result: str = "") -> None:
        # O resultado completo não é gravado (pode ter e-mails/eventos): só um resumo curto.
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": tool,
            "risk": risk,
            "args": args,
            "decision": decision,
            "result": result[:MAX_FIELD],
        }
        self._append(entry)

    def event(self, kind: str, **fields) -> None:
        """Evento que não é ação de ferramenta (ex.: métricas de latência e memória)."""
        self._append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "type": kind, **fields})

    def _append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
