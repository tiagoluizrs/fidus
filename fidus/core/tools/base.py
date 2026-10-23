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
    taints: bool | None = None  # None = segue `untrusted`. Se True, depois de rodar, o comando deixa de ter ações dispensadas de confirmação

    def risk_for(self, args: dict) -> Risk:
        """Risco desta chamada. Por padrão é o da ferramenta; uma ferramenta com várias ações pode variar."""
        return self.risk

    @property
    def is_tainting(self) -> bool:
        return self.untrusted if self.taints is None else self.taints

    def precheck(self, args: dict, config: Config) -> None:
        """Roda ANTES de pedir confirmação. Levanta ToolError se a ação nem pode acontecer (ex.: escrita não liberada)."""

    def preapproved(self, args: dict, config: Config) -> bool:
        """Só vale para ESCRITA: permite dispensar a confirmação em casos já liberados na configuração."""
        return False

    def run(self, args: dict, config: Config) -> str:
        raise NotImplementedError
