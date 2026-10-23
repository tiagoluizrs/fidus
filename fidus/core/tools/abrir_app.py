"""abrir_app: abre um aplicativo. Apps da lista da configuração abrem direto; os demais pedem confirmação."""

from __future__ import annotations

import os
import subprocess
import sys

from .base import Risk, Tool, ToolError


def _launch(command: str) -> None:
    """Abre pelo shell do Windows. Fora do Windows só existe para desenvolvimento."""
    if sys.platform == "win32":
        os.startfile(command)  # type: ignore[attr-defined]
    else:
        subprocess.Popen([command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class AbrirApp(Tool):
    name = "abrir_app"
    description = (
        "Abre um aplicativo do computador pelo nome (ex.: 'bloco de notas', 'calculadora'). "
        "Não executa comandos nem abre endereços ou arquivos."
    )
    parameters = {
        "type": "object",
        "properties": {"nome": {"type": "string", "description": "Nome do aplicativo"}},
        "required": ["nome"],
    }
    risk = Risk.ESCRITA

    def preapproved(self, args, config) -> bool:
        return str(args.get("nome", "")).strip().lower() in config.allowed_apps

    def run(self, args, config) -> str:
        nome = str(args.get("nome", "")).strip()
        if not nome:
            raise ToolError("Informe o nome do aplicativo.")
        command = config.allowed_apps.get(nome.lower())
        if command is None:
            # Fora da lista: só nomes simples de executável (nada de caminhos, URLs ou argumentos).
            if any(c in nome for c in ':/\\ "\'&|<>;'):
                raise ToolError(f"'{nome}' não é um nome de aplicativo válido.")
            command = nome
        try:
            _launch(command)
        except OSError as e:
            raise ToolError(f"Não consegui abrir '{nome}': {e}") from e
        return f"Aplicativo '{nome}' aberto."


TOOL = AbrirApp()
