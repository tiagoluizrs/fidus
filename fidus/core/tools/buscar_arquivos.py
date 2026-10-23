"""buscar_arquivos: procura por nome, somente dentro das pastas liberadas na configuração."""

from __future__ import annotations

import os
from pathlib import Path

from .base import Risk, Tool, ToolError

MAX_RESULTS = 50
MAX_SCANNED = 100_000


def is_within(path: Path, roots: list[Path]) -> bool:
    """True se `path`, já resolvido (sem `..` nem links), está dentro de alguma pasta liberada."""
    resolved = path.resolve()
    return any(resolved == r or r in resolved.parents for r in roots)


class BuscarArquivos(Tool):
    name = "buscar_arquivos"
    description = (
        "Procura arquivos pelo nome nas pastas liberadas pelo usuário. "
        "Devolve só os caminhos; não lê o conteúdo."
    )
    parameters = {
        "type": "object",
        "properties": {
            "consulta": {"type": "string", "description": "Palavras que o nome do arquivo deve conter"},
            "pasta": {"type": "string", "description": "Subpasta liberada onde procurar (opcional)"},
            "max_resultados": {"type": "integer", "description": "Padrão 20, máximo 50"},
        },
        "required": ["consulta"],
    }
    risk = Risk.LEITURA
    untrusted = True  # nomes de arquivo são dados de terceiros

    def run(self, args, config) -> str:
        roots = [r.resolve() for r in config.allowed_folders]
        if not roots:
            raise ToolError("Nenhuma pasta liberada. Configure 'pastas_liberadas' no fidus.toml.")
        terms = str(args.get("consulta", "")).lower().split()
        if not terms:
            raise ToolError("Informe o que procurar.")
        limit = max(1, min(int(args.get("max_resultados") or 20), MAX_RESULTS))

        if args.get("pasta"):
            start = Path(str(args["pasta"])).expanduser()
            if not is_within(start, roots):
                raise ToolError("Essa pasta não está liberada para busca.")
            search_roots = [start.resolve()]
        else:
            search_roots = roots

        found: list[str] = []
        scanned = 0
        for root in search_roots:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                for name in filenames + dirnames:
                    scanned += 1
                    if all(t in name.lower() for t in terms):
                        found.append(str(Path(dirpath) / name))
                        if len(found) >= limit:
                            return "\n".join(found)
                if scanned > MAX_SCANNED:
                    break
        return "\n".join(found) if found else "Nenhum arquivo encontrado."


TOOL = BuscarArquivos()
