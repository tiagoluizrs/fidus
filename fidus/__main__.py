"""Fidus no terminal.

  uv run fidus                    conversa por texto
  uv run fidus "pedido"           comando único por texto
  uv run fidus voice              laço de voz (segure o atalho para falar)
  uv run fidus listen             laço com palavra de ativação ("ei Alfred") e push-to-talk
  uv run fidus wake-test          mostra a pontuação de cada palavra em tempo real (ajuste de limiares)
  uv run fidus wake-bench [seg]   mede CPU e memória da escuta passiva (padrão 60 s)
  (opções de listen/wake-test/wake-bench: --somente-teste usa o modelo pronto "hey jarvis")
  uv run fidus say "texto"        testa a voz
  uv run fidus mics               lista os microfones
  uv run fidus character list|show|reset|default|set|phrase   personagens (personalidade, frases, voz)
  uv run fidus memory list|search|add|edit|delete|export|forget-all   memória única
  uv run fidus user show|set      seu nome (usado nas falas)
  uv run fidus secrets set|get|delete|list|migrate   chaves no Gerenciador de Credenciais do Windows
  uv run fidus accounts list|connect|disconnect|channels   Google Agenda, Gmail e Slack
  uv run fidus daemon [--simulado]   núcleo em segundo plano para a interface Electron (o app inicia este comando)
  uv run fidus --check-key        testa a chave da Anthropic
"""

from __future__ import annotations

import argparse
import sys

COMMANDS = {"voice", "say", "mics", "listen", "wake-test", "wake-bench", "character", "memory", "user", "secrets", "accounts", "daemon", "selftest"}


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


def _cmd_say(text: str, character: str | None = None) -> int:
    from .core.config import load_config
    from .core.persona import PersonaService
    from .core.voice.sentences import clean_for_speech
    from .core.voice.tts import TTSManager

    config = load_config()
    persona = PersonaService(config)
    cid = persona.resolve_id(character)
    tts = TTSManager(config.voice.speech_rate, data_dir=config.data_dir)
    tts.use(persona.voice(cid))  # a voz do personagem
    print(f"Personagem: {cid}   Voz: {tts.voice_name}")
    tts.speak(clean_for_speech(text))
    tts.wait_idle()
    tts.close()
    return 0


def _cmd_voice() -> int:
    from .core.config import load_config
    from .core.voice.loop import build_voice_loop

    build_voice_loop(load_config()).run()
    return 0


def _cmd_listen(include_test: bool) -> int:
    from .core.config import load_config
    from .core.voice.listen_build import build_listen_loop

    build_listen_loop(load_config(), include_test).run()
    return 0


def _cmd_wake_test(include_test: bool, synthetic: bool) -> int:
    from .core.config import load_config
    from .core.voice.bench import SyntheticStream
    from .core.voice.listen_build import run_wake_test

    return run_wake_test(load_config(), include_test, stream_factory=SyntheticStream if synthetic else None)


def _cmd_wake_bench(rest: list[str], include_test: bool, synthetic: bool) -> int:
    from .core.config import load_config
    from .core.voice.bench import run_bench

    nums = [a for a in rest if not a.startswith("--")]
    return run_bench(load_config(), float(nums[0]) if nums else 60.0, include_test, synthetic)


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

    from .core.assistant import build_assistant
    from .core.permissions import cli_confirmer

    fidus, persona, _ = build_assistant(config, cli_confirmer, provider=provider)
    character = persona.resolve_id(args.personagem)

    def ask(text: str) -> None:
        fidus.run(text, on_text=lambda chunk: print(chunk, end="", flush=True), personagem_ativo=character)  # streaming
        print()

    if args.pedido:
        ask(" ".join(args.pedido))
        return 0

    print(f"Fidus ({config.model}), falando como {character}. Digite 'sair' para encerrar.")
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


SELFTEST_MODULES = ["anthropic", "keyring", "numpy", "sounddevice", "faster_whisper", "openwakeword (enxuto)", "sqlcipher3", "websockets",
                    "googleapiclient.discovery", "google_auth_oauthlib.flow", "psutil", "pynput.keyboard", "win32com.client"]


def _cmd_selftest() -> int:
    """Confere se as bibliotecas pesadas (importadas só quando usadas) estão no pacote. Usado para validar o instalador."""
    import importlib

    bad = 0
    for name in SELFTEST_MODULES:
        if name == "win32com.client" and sys.platform != "win32":
            continue
        try:
            if name.startswith("openwakeword"):  # o Fidus importa sem scikit-learn (voice/oww.py); o pacote também não o leva
                from .core.voice.oww import import_openwakeword

                import_openwakeword()
            else:
                importlib.import_module(name)
            print(f"ok      {name}")
        except Exception as e:  # noqa: BLE001 - queremos listar todas as falhas, não parar na primeira
            bad += 1
            print(f"FALHOU  {name}: {type(e).__name__}: {e}")
    from .core.characters.store import CharacterStore  # noqa: F401  (confere também os dados empacotados)
    from .core.config import load_config

    cfg = load_config()
    ids = CharacterStore(cfg.characters_dir).ids()
    print(f"personagens: {', '.join(ids) or 'nenhum'}")
    bad += 0 if len(ids) >= 3 else 1
    print(f"dados em: {cfg.data_dir}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in COMMANDS:
        cmd, rest = argv[0], argv[1:]
        if cmd == "selftest":
            return _cmd_selftest()
        if cmd == "daemon":
            from .core.bridge.daemon import run_daemon
            from .core.config import load_config

            return run_daemon(load_config(), simulated="--simulado" in rest, include_test="--somente-teste" in rest, watch_stdin="--stdin-watch" in rest)
        if cmd in {"secrets", "accounts"}:
            from . import cli_accounts

            return getattr(cli_accounts, f"cmd_{cmd}")(rest)
        if cmd in {"character", "memory", "user"}:
            from . import cli_data

            return getattr(cli_data, f"cmd_{cmd}")(rest)
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
            who = None
            if "--personagem" in rest:
                i = rest.index("--personagem")
                who = rest[i + 1] if i + 1 < len(rest) else None
                rest = rest[:i] + rest[i + 2 :]
            return _cmd_say(" ".join(rest), who)
        include_test, synthetic = "--somente-teste" in rest, "--sem-microfone" in rest
        if cmd == "listen":
            return _cmd_listen(include_test)
        if cmd == "wake-test":
            return _cmd_wake_test(include_test, synthetic)
        if cmd == "wake-bench":
            return _cmd_wake_bench(rest, include_test, synthetic)
        return _cmd_voice()

    parser = argparse.ArgumentParser(prog="fidus", description="Assistente Fidus", epilog=__doc__)
    parser.add_argument("pedido", nargs="*", help="comando único; sem ele, abre o modo conversa")
    parser.add_argument("--check-key", action="store_true", help="testa se a chave da Anthropic funciona")
    parser.add_argument("--personagem", help="alfred, donna ou jarbis (padrão: o personagem padrão)")
    return _text_mode(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
