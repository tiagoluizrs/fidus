"""Edições de configuração feitas pelo Fidus (CLI e, depois, a interface), em `settings.json` na pasta de dados.

Têm as mesmas seções do `fidus.toml` e valem sobre ele. O `fidus.toml` nunca é reescrito.
"""

from __future__ import annotations

import json
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def set_value(path: Path, dotted: str, value) -> None:
    """`set_value(p, "chamados.personagem_padrao", "donna")`."""
    data = read(path)
    node, keys = data, dotted.split(".")
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def unset_value(path: Path, dotted: str) -> None:
    data = read(path)
    node, keys = data, dotted.split(".")
    for k in keys[:-1]:
        node = node.get(k, {})
    node.pop(keys[-1], None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
