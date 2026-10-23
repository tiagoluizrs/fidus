"""Descobre os plugins: cada módulo em tools/ expõe `TOOL`. Nova ferramenta = novo arquivo.

Os módulos só importam bibliotecas pesadas dentro de `run`, então carregar o registro é barato.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import Tool

_SKIP = {"base", "registry"}


def load_tools() -> dict[str, Tool]:
    tools: dict[str, Tool] = {}
    for mod in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if mod.name in _SKIP or mod.name.startswith("_"):
            continue
        tool = importlib.import_module(f"{__package__}.{mod.name}").TOOL
        tools[tool.name] = tool
    return tools
