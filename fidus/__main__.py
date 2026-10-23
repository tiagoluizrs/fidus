"""Fidus no terminal: `uv run fidus` (conversa) ou `uv run fidus "pedido"` (comando único)."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fidus", description="Assistente Fidus (núcleo no terminal)")
    parser.add_argument("pedido", nargs="*", help="comando único; sem ele, abre o modo conversa")
    parser.add_argument("--check-key", action="store_true", help="testa se a chave da Anthropic funciona")
    args = parser.parse_args(argv)

    from .core.config import load_config
    from .core.providers import create_provider

    config = load_config()
    provider = create_provider(config)

    if args.check_key:
        try:
            print(f"Chave OK. Modelo {config.model} respondeu: {provider.check_key()!r}")
            return 0
        except Exception as e:
            print(f"Falha ao usar a chave: {type(e).__name__}: {e}", file=sys.stderr)
            return 1

    from .core.orchestrator import Orchestrator
    from .core.permissions import cli_confirmer

    fidus = Orchestrator(config, provider, cli_confirmer)

    if args.pedido:
        print(fidus.run(" ".join(args.pedido)))
        return 0

    print(f"Fidus ({config.model}). Digite 'sair' para encerrar.")
    while True:
        try:
            text = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text.lower() in {"sair", "exit", "quit"}:
            return 0
        if text:
            try:
                print(f"fidus> {fidus.run(text)}")
            except Exception as e:
                print(f"fidus> Erro: {type(e).__name__}: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
