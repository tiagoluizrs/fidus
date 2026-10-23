"""`fidus daemon`: o núcleo como processo de fundo para o Electron.

Protocolo de inicialização: o servidor local sobe primeiro e a linha
    FIDUS_READY {"port": 51234, "token": "...", "protocol": 1}
sai na saída padrão (só o Electron, que é o processo pai, a lê). Depois carrega o Whisper e o resto; o progresso vai
pelo evento `status`.
"""

from __future__ import annotations

import json
import sys
import threading

from ..config import Config
from .commands import CoreCommands
from .core_state import CoreState, StateTap
from .protocol import PROTOCOL_VERSION
from .server import Bridge


def run_daemon(config: Config, simulated: bool = False, out=None, include_test: bool = False, ready_event: threading.Event | None = None, watch_stdin: bool = False, headless: bool = False) -> int:
    from ..persona import PersonaService

    out = out or sys.stdout
    persona = PersonaService(config)
    holder: dict = {}
    stop_event = threading.Event()

    def handler(name, args):
        return holder["commands"].handle(name, args)

    bridge = Bridge(handler, lambda: holder["state"].snapshot())
    state = CoreState(config, persona, bridge)
    tap = StateTap(bridge, state)
    state.events = tap
    holder["state"] = state

    if simulated:
        from .simulated import SimulatedCommands

        holder["commands"] = SimulatedCommands(config, state, persona=persona, on_quit=stop_event.set)
    else:
        holder["commands"] = CoreCommands(config, state, persona=persona, on_quit=stop_event.set)

    if watch_stdin:
        # O Electron mantém o stdin aberto. Se ele morrer, o stdin fecha e o núcleo encerra sozinho (sem processo órfão).
        def watch() -> None:
            try:
                while sys.stdin.read(1024):
                    pass
            except Exception:
                pass
            holder["commands"].cmd_quit()

        threading.Thread(target=watch, daemon=True, name="fidus-stdin").start()

    port = bridge.start()
    print("FIDUS_READY " + json.dumps({"port": port, "token": bridge.token, "protocol": PROTOCOL_VERSION}), file=out, flush=True)
    if ready_event:
        ready_event.set()

    if simulated:
        state.set_status("ready")
        try:
            stop_event.wait()
        except KeyboardInterrupt:
            pass
        bridge.stop()
        return 0

    if headless:  # núcleo real, sem áudio: pedidos por texto (Docker/navegador)
        from .headless import HeadlessLoop

        try:
            loop = HeadlessLoop(config, tap, state)
            holder["commands"].loop, holder["commands"].broker = loop, loop.broker
            holder["commands"].on_quit = lambda: (stop_event.set(), loop.request_stop())
            holder["commands"].h.loop = loop
            state.set_status("ready")
            stop_event.wait()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            state.set_status("error", f"{type(e).__name__}: {e}")
            print(f"Erro no núcleo: {e}", file=sys.stderr, flush=True)
            stop_event.wait(5)
            return 1
        finally:
            bridge.stop()
        return 0

    try:
        from ..voice.listen_build import build_listen_loop

        loop = build_listen_loop(config, include_test, events=tap, broker_events=tap)
        holder["commands"].loop = loop
        holder["commands"].broker = loop.broker
        holder["commands"].on_quit = lambda: (stop_event.set(), loop.request_stop())
        state.set_status("ready")
        loop.run()  # bloqueia até Ctrl+C ou o comando `quit`
    except KeyboardInterrupt:
        pass
    except Exception as e:  # o Electron mostra a mensagem
        state.set_status("error", f"{type(e).__name__}: {e}")
        print(f"Erro no núcleo: {e}", file=sys.stderr, flush=True)
        stop_event.wait(5)  # dá tempo de a interface ler o erro
        return 1
    finally:
        bridge.stop()
    return 0
