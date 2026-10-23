"""Camada de permissão. Vive fora do modelo: vale igual para qualquer provedor."""

from __future__ import annotations

from collections.abc import Callable

from .config import Config
from .tools.base import Risk, Tool

Confirmer = Callable[[str], bool]


def cli_confirmer(prompt: str) -> bool:
    return input(f"{prompt} Permitir? [s/n] ").strip().lower() in {"s", "sim", "y", "yes"}


def needs_confirmation(tool: Tool, args: dict, config: Config, tainted: bool = False) -> bool:
    """`tainted`: neste comando já entrou conteúdo externo (e-mail, evento...). Aí nada é dispensado de confirmação,
    porque o pedido pode ter sido plantado por quem escreveu o conteúdo."""
    risk = tool.risk_for(args)
    if risk is Risk.LEITURA:
        return False
    if risk is Risk.ESCRITA and not tainted and tool.preapproved(args, config):
        return False
    return True  # irreversível: sempre pergunta, nenhuma ferramenta pode dispensar


def ask(tool: Tool, args: dict, confirm: Confirmer) -> bool:
    shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return confirm(f"Fidus quer executar {tool.name} ({tool.risk_for(args).value}): {shown}.")
