"""Chaves e tokens: Gerenciador de Credenciais do Windows (keyring) primeiro; `.env` só em desenvolvimento.

Nomes conhecidos: ANTHROPIC_API_KEY, SLACK_TOKEN, DB_KEY (chave do SQLCipher) e GOOGLE_TOKEN_<serviço>.
Nada aqui grava segredo em arquivo (a única exceção é o FileVault do teste no Docker).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SERVICE = "fidus"
ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
SLACK_TOKEN = "SLACK_TOKEN"
ELEVENLABS_KEY = "ELEVENLABS_API_KEY"
GEMINI_KEY = "GEMINI_API_KEY"
KNOWN = [ANTHROPIC_KEY, SLACK_TOKEN, ELEVENLABS_KEY, GEMINI_KEY, "DB_KEY", "GOOGLE_TOKEN_calendar", "GOOGLE_TOKEN_gmail"]


class VaultUnavailable(RuntimeError):
    """O cofre do sistema não está disponível (ex.: Linux sem Secret Service)."""


class FileVault:
    """Cofre em ARQUIVO, só para o teste no Docker (variável FIDUS_SECRETS_FILE): lá não existe o Gerenciador de
    Credenciais do Windows. No app instalado nunca é usado. O arquivo fica no volume de dados, só com permissão do dono."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)

    def get_password(self, service: str, name: str) -> str | None:
        return self._load().get(f"{service}:{name}")

    def set_password(self, service: str, name: str, value: str) -> None:
        data = self._load()
        data[f"{service}:{name}"] = value
        self._save(data)

    def delete_password(self, service: str, name: str) -> None:
        data = self._load()
        data.pop(f"{service}:{name}", None)
        self._save(data)


def _keyring():
    if os.environ.get("FIDUS_SECRETS_FILE"):
        return FileVault(Path(os.environ["FIDUS_SECRETS_FILE"]))
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
