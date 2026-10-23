"""Chaves: Gerenciador de Credenciais do Windows (keyring) primeiro, .env só em desenvolvimento."""

from __future__ import annotations

import os

SERVICE = "fidus"
ANTHROPIC_KEY = "ANTHROPIC_API_KEY"


def get_secret(name: str) -> str | None:
    try:
        import keyring

        value = keyring.get_password(SERVICE, name)
        if value:
            return value
    except Exception:  # sem backend (ex.: Linux sem cofre): cai no ambiente
        pass
    return os.environ.get(name) or None


def set_secret(name: str, value: str) -> None:
    import keyring

    keyring.set_password(SERVICE, name, value)


def get_anthropic_key() -> str | None:
    return get_secret(ANTHROPIC_KEY)
