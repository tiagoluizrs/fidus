"""Camada de permissão. Vive fora do modelo: vale igual para qualquer provedor."""

from __future__ import annotations

from collections.abc import Callable

from .config import Config
from .tools.base import Risk, Tool

Confirmer = Callable[[str], bool]


def cli_confirmer(prompt: str) -> bool:
    return input(f"{prompt} [s/n] ").strip().lower() in {"s", "sim", "y", "yes"}


def needs_confirmation(tool: Tool, args: dict, config: Config) -> bool:
    if tool.risk is Risk.LEITURA:
        return False
    if tool.risk is Risk.ESCRITA and tool.preapproved(args, config):
        return False
    return True  # irreversível: sempre pergunta, nenhuma ferramenta pode dispensar


def ask(tool: Tool, args: dict, confirm: Confirmer) -> bool:
    shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return confirm(f"Fidus quer executar {tool.name} ({tool.risk.value}): {shown}. Permitir?")
