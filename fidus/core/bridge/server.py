"""Servidor WebSocket local do núcleo.

- Só em 127.0.0.1, porta aleatória.
- Token aleatório gerado a cada inicialização e entregue só ao Electron (pela saída padrão do processo filho).
- Navegadores são recusados: qualquer requisição com cabeçalho Origin é rejeitada (impede ataque por página web).
- O primeiro quadro precisa ser `auth` com o token, em 5 s; senão a conexão é fechada.
"""

from __future__ import annotations

import asyncio
import hmac
import secrets
import threading
from collections.abc import Callable
from typing import Any

from .protocol import AUTH_TIMEOUT_S, MAX_MESSAGE_BYTES, PROTOCOL_VERSION, ProtocolError, decode, encode, parse_command

CommandHandler = Callable[[str, dict[str, Any]], dict[str, Any] | None]


def new_token() -> str:
    return secrets.token_urlsafe(32)


class Bridge:
    def __init__(self, on_command: CommandHandler, snapshot: Callable[[], dict[str, Any]], token: str | None = None, host: str = "127.0.0.1", port: int = 0):
        self.token = token or new_token()
        self.host, self.port = host, port
        self._on_command, self._snapshot = on_command, snapshot
        self._clients: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stop: asyncio.Event | None = None
        self._error: Exception | None = None

    # ---- ciclo de vida ----

    def start(self) -> int:
        """Sobe o servidor em um thread próprio e devolve a porta."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="fidus-bridge")
        self._thread.start()
        self._started.wait(10)
        if self._error:
            raise RuntimeError(f"Não consegui abrir o servidor local: {self._error}")
        return self.port

    def stop(self) -> None:
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as e:  # falha ao abrir a porta
            self._error = e
            self._started.set()

    async def _serve(self) -> None:
        from websockets.asyncio.server import serve  # pesado: só aqui

        self._loop, self._stop = asyncio.get_running_loop(), asyncio.Event()
        async with serve(self._handler, self.host, self.port, origins=[None], max_size=MAX_MESSAGE_BYTES,
                         compression=None, ping_interval=20, ping_timeout=20) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._started.set()
            await self._stop.wait()

    # ---- conexões ----

    @property
    def has_clients(self) -> bool:
        return bool(self._clients)

    async def _handler(self, ws) -> None:
        try:
            first = decode(await asyncio.wait_for(ws.recv(), AUTH_TIMEOUT_S))
            ok = first.get("type") == "auth" and hmac.compare_digest(str(first.get("token", "")), self.token)
        except (asyncio.TimeoutError, ProtocolError, Exception):
            ok = False
        if not ok:
            await ws.close(4401, "não autorizado")
            return
        self._clients.add(ws)
        try:
            await ws.send(encode({"type": "ready", "protocol": PROTOCOL_VERSION, "snapshot": self._snapshot()}))
            async for raw in ws:
                await self._on_message(ws, raw)
        except Exception:
            pass
        finally:
            self._clients.discard(ws)

    async def _on_message(self, ws, raw) -> None:
        try:
            cid, name, args = parse_command(decode(raw))
        except ProtocolError as e:
            await ws.send(encode({"type": "reply", "id": None, "ok": False, "error": str(e)}))
            return
        try:
            data = await asyncio.get_running_loop().run_in_executor(None, self._on_command, name, args)
            await ws.send(encode({"type": "reply", "id": cid, "ok": True, "data": data or {}}))
        except Exception as e:  # um comando com erro não derruba a conexão
            await ws.send(encode({"type": "reply", "id": cid, "ok": False, "error": f"{type(e).__name__}: {e}"}))

    # ---- eventos (qualquer thread) ----

    def emit(self, type: str, **data) -> None:
        if not self._clients or not self._loop:
            return
        text = encode({"type": type, **data})
        asyncio.run_coroutine_threadsafe(self._broadcast(text), self._loop)

    async def _broadcast(self, text: str) -> None:
        for ws in list(self._clients):
            try:
                await ws.send(text)
            except Exception:
                self._clients.discard(ws)
