"""Contrato de uma ferramenta: nome, descrição, parâmetros e nível de risco."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import Config


class Risk(str, Enum):
    LEITURA = "leitura"
    ESCRITA = "escrita"
    IRREVERSIVEL = "irreversível"


class ToolError(Exception):
    """Erro esperado; a mensagem volta ao modelo como resultado da ferramenta."""


class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema do objeto de argumentos
    risk: Risk
    untrusted: bool = False  # True: a saída é conteúdo externo e vai ao modelo como dado delimitado

    def preapproved(self, args: dict, config: Config) -> bool:
        """Só vale para ESCRITA: permite dispensar a confirmação em casos já liberados na configuração."""
        return False

    def run(self, args: dict, config: Config) -> str:
        raise NotImplementedError
