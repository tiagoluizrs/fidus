"""Log local de ações (JSON por linha). Sem telemetria: nada sai do computador."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MAX_FIELD = 200


class ActionLog:
    def __init__(self, path: Path, config=None):
        self.path = path
        self.config = config  # opcional: respeita "Registrar o que o Fidus executa"

    def record(self, *, tool: str, risk: str, args: dict, decision: str, result: str = "") -> None:
        if self.config is not None and not self.config.privacy.log_actions:
            return  # o usuário desligou o registro de ações (eventos técnicos, como métricas, continuam)
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

    def read(self, limit: int = 200) -> list[dict]:
        """Últimas entradas (mais recentes primeiro). Linhas ilegíveis são ignoradas."""
        import json as _json

        if not self.path.is_file():
            return []
        out: list[dict] = []
        for line in reversed(self.path.read_text(encoding="utf-8").splitlines()):
            try:
                out.append(_json.loads(line))
            except ValueError:
                continue
            if len(out) >= limit:
                break
        return out

    def prune(self, days: int) -> int:
        """Apaga do arquivo o que é mais velho que `days` dias. Devolve quantas linhas saíram."""
        import json as _json
        from datetime import timedelta

        if days <= 0 or not self.path.is_file():
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        keep, dropped = [], 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                ts = datetime.fromisoformat(_json.loads(line)["ts"])
            except (ValueError, KeyError, TypeError):
                keep.append(line)
                continue
            if ts >= cutoff:
                keep.append(line)
            else:
                dropped += 1
        if dropped:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
            tmp.replace(self.path)
        return dropped
