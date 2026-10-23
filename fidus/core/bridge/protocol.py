"""Protocolo núcleo <-> interface (versão 1). Documentado em docs/PROTOCOLO.md."""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = 1
AUTH_TIMEOUT_S = 5.0
MAX_MESSAGE_BYTES = 1 << 20  # 1 MB

# Estados que a interface desenha. O núcleo tem mais detalhes (gravando, pausado...), a interface vê só estes.
STATES = ("idle", "listening", "thinking", "speaking", "muted")
MIC_STATES = ("passive", "recording", "paused", "muted", "off")

# Eventos núcleo -> interface (o campo "type" é o nome do evento).
EVENTS = ("ready", "status", "state", "characters_changed", "memory_changed", "accounts", "level", "caption", "character", "confirm", "confirm_done", "model", "calls", "settings", "open_url", "voice_mode", "speak_audio", "conversation", "model_pull", "voice_setup", "voice_record", "error")

# Comandos interface -> núcleo ({"type":"cmd","id":...,"name":...,"args":{...}}).
COMMANDS = (
    "get_state", "mute", "pause", "calls", "set_default_character", "confirm_reply", "get_settings", "set_settings",
    "ping", "quit",
    "characters", "memory", "accounts", "privacy", "about", "voices", "devices", "api_key", "local_models", "piper", "kokoro", "voice_cloud", "ask", "ask_audio", "browser_mic",
    "simulate",  # só no modo simulado (desenvolvimento da interface)
)


class ProtocolError(ValueError):
    """Mensagem malformada."""


def encode(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def decode(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "strict")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("mensagem grande demais")
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProtocolError("JSON inválido") from e
    if not isinstance(msg, dict) or not isinstance(msg.get("type"), str):
        raise ProtocolError("a mensagem precisa ser um objeto com o campo 'type'")
    return msg


def parse_command(msg: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Valida um comando e devolve (id, nome, argumentos)."""
    if msg.get("type") != "cmd":
        raise ProtocolError(f"tipo de mensagem inesperado: {msg.get('type')!r}")
    cid, name, args = msg.get("id"), msg.get("name"), msg.get("args", {})
    if not isinstance(cid, (str, int)) or isinstance(cid, bool):
        raise ProtocolError("comando sem 'id'")
    if name not in COMMANDS:
        raise ProtocolError(f"comando desconhecido: {name!r}")
    if not isinstance(args, dict):
        raise ProtocolError("'args' precisa ser um objeto")
    return str(cid), name, args
