"""Fidus no terminal.

  uv run fidus                    conversa por texto
  uv run fidus "pedido"           comando único por texto
  uv run fidus voice              laço de voz (segure o atalho para falar)
  uv run fidus say "texto"        testa a voz
  uv run fidus mics               lista os microfones
  uv run fidus --check-key        testa a chave da Anthropic
"""

from __future__ import annotations

import argparse
import sys

COMMANDS = {"voice", "say", "mics"}


def _cmd_mics() -> int:
    from .core.config import load_config
    from .core.voice.audio import list_devices, resolve_device

    config = load_config()
    devices = list_devices()
    try:
        chosen = resolve_device(config.voice.microphone, devices)
    except ValueError as e:
        chosen = None
        print(f"Aviso: {e}")
    for d in devices:
        marks = ("  [padrão do sistema]" if d["default"] else "") + ("  [escolhido no fidus.toml]" if d["index"] == chosen else "")
        print(f"{d['index']:>3}  {d['name']}{marks}")
    print('\nPara escolher, ponha em fidus.toml:  [voz]  microfone = "<índice ou parte do nome>"')
    return 0


def _cmd_say(text: str) -> int:
    from .core.config import load_config
    from .core.voice.sentences import clean_for_speech
    from .core.voice.tts import create_tts

    config = load_config()
    tts = create_tts(config.voice.speech_rate)
    print(f"Voz: {getattr(tts, 'voice_name', '?')}")
    tts.speak(clean_for_speech(text))
    tts.wait_idle()
    tts.close()
    return 0


def _cmd_voice() -> int:
    from .core.config import load_config
    from .core.voice.loop import build_voice_loop

    build_voice_loop(load_config()).run()
    return 0


def _text_mode(args) -> int:
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

    def ask(text: str) -> None:
        fidus.run(text, on_text=lambda chunk: print(chunk, end="", flush=True))  # streaming
        print()

    if args.pedido:
        ask(" ".join(args.pedido))
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
                print("fidus> ", end="", flush=True)
                ask(text)
            except Exception as e:
                print(f"\nErro: {type(e).__name__}: {e}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in COMMANDS:
        cmd, rest = argv[0], argv[1:]
        if cmd == "mics":
            try:
                return _cmd_mics()
            except OSError as e:  # PortAudio ausente (no Windows vem embutido no pacote sounddevice)
                print(f"Não consegui acessar o áudio: {e}", file=sys.stderr)
                return 1
        if cmd == "say":
            if not rest:
                print('Uso: fidus say "texto"', file=sys.stderr)
                return 2
            return _cmd_say(" ".join(rest))
        return _cmd_voice()

    parser = argparse.ArgumentParser(prog="fidus", description="Assistente Fidus", epilog=__doc__)
    parser.add_argument("pedido", nargs="*", help="comando único; sem ele, abre o modo conversa")
    parser.add_argument("--check-key", action="store_true", help="testa se a chave da Anthropic funciona")
    return _text_mode(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
