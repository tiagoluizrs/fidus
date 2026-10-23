"""Chaves e tokens: Gerenciador de Credenciais do Windows (keyring) primeiro; `.env` só em desenvolvimento.

Nomes conhecidos: ANTHROPIC_API_KEY, SLACK_TOKEN, DB_KEY (chave do SQLCipher) e GOOGLE_TOKEN_<serviço>.
Nada aqui grava segredo em arquivo.
"""

from __future__ import annotations

import os

SERVICE = "fidus"
ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
SLACK_TOKEN = "SLACK_TOKEN"
KNOWN = [ANTHROPIC_KEY, SLACK_TOKEN, "DB_KEY", "GOOGLE_TOKEN_calendar", "GOOGLE_TOKEN_gmail"]


class VaultUnavailable(RuntimeError):
    """O cofre do sistema não está disponível (ex.: Linux sem Secret Service)."""


def _keyring():
    try:
        import keyring

        return keyring
    except Exception as e:  # pragma: no cover
        raise VaultUnavailable(f"keyring indisponível: {e}") from e


def get_vault_secret(name: str) -> str | None:
    """Só o cofre, sem cair no ambiente."""
    try:
        return _keyring().get_password(SERVICE, name) or None
    except Exception:
        return None


def get_secret(name: str) -> str | None:
    """Cofre primeiro; se não houver, a variável de ambiente (que o `.env` preenche em desenvolvimento)."""
    return get_vault_secret(name) or os.environ.get(name) or None


def set_secret(name: str, value: str) -> None:
    try:
        _keyring().set_password(SERVICE, name, value)
    except VaultUnavailable:
        raise
    except Exception as e:
        raise VaultUnavailable(f"não consegui gravar no cofre do sistema: {e}") from e


def delete_secret(name: str) -> bool:
    """True se existia e foi apagado."""
    if get_vault_secret(name) is None:
        return False
    try:
        _keyring().delete_password(SERVICE, name)
    except Exception as e:
        raise VaultUnavailable(f"não consegui apagar do cofre: {e}") from e
    return True


def mask(value: str) -> str:
    """Mostra só o começo e o fim, nunca o segredo inteiro."""
    return "*" * len(value) if len(value) <= 8 else f"{value[:4]}…{value[-2:]} ({len(value)} caracteres)"


def get_anthropic_key() -> str | None:
    return get_secret(ANTHROPIC_KEY)
