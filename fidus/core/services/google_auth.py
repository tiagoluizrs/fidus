"""OAuth do Google com escopos mínimos. Leitura por padrão; escrita só quando liberada, por serviço.

O que fica no Gerenciador de Credenciais é só o necessário para renovar o acesso (refresh token e os dados do cliente
OAuth), em JSON curto. O token de acesso é renovado sob demanda e não é guardado. Nunca vai para arquivo.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .. import secrets as vault
from ..config import Config
from .base import NotConnected

API = "https://www.googleapis.com/auth/"
SCOPES = {
    "calendar": {"read": [API + "calendar.readonly"], "write": [API + "calendar.events"]},
    # O Gmail não tem escopo só de rascunho: gmail.compose também permitiria enviar. O Fidus nunca chama o envio.
    "gmail": {"read": [API + "gmail.readonly"], "write": [API + "gmail.readonly", API + "gmail.compose"]},
}
TOKEN_URI = "https://oauth2.googleapis.com/token"


def secret_name(service: str) -> str:
    return f"GOOGLE_TOKEN_{service}"


def scopes_for(service: str, write: bool) -> list[str]:
    return SCOPES[service]["write" if write else "read"]


def _pack(creds, scopes: list[str]) -> str:
    return json.dumps(
        {"refresh_token": creds.refresh_token, "client_id": creds.client_id, "client_secret": creds.client_secret,
         "token_uri": creds.token_uri or TOKEN_URI, "scopes": scopes},
        separators=(",", ":"),
    )


def connect(config: Config, service: str, write: bool = False, flow_factory: Callable | None = None) -> list[str]:
    """Abre o navegador para autorizar e guarda o refresh token no cofre. Devolve os escopos concedidos."""
    cred_file = config.google_credentials_path
    if not cred_file.is_file():
        raise NotConnected(
            f"Falta o arquivo de credenciais OAuth do Google em {cred_file}. Veja docs/INTEGRACOES.md (passo 1)."
        )
    scopes = scopes_for(service, write)
    if flow_factory is None:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow_factory = InstalledAppFlow.from_client_secrets_file
    flow = flow_factory(str(cred_file), scopes)
    creds = flow.run_local_server(port=0)
    if not creds.refresh_token:
        raise NotConnected("O Google não devolveu um token de renovação. Remova o acesso do Fidus na conta Google e tente de novo.")
    vault.set_secret(secret_name(service), _pack(creds, scopes))
    return scopes


def disconnect(service: str) -> bool:
    return vault.delete_secret(secret_name(service))


def is_connected(service: str) -> bool:
    return vault.get_vault_secret(secret_name(service)) is not None


def granted_scopes(service: str) -> list[str]:
    raw = vault.get_vault_secret(secret_name(service))
    return json.loads(raw)["scopes"] if raw else []


def _migrate_old_token(config: Config, service: str) -> None:
    """A etapa 1 guardava o token do Google Agenda em arquivo. Move para o cofre e apaga o arquivo."""
    old: Path = config.google_token_path
    if service != "calendar" or not old.is_file() or vault.get_vault_secret(secret_name(service)):
        return
    try:
        data = json.loads(old.read_text(encoding="utf-8"))
        packed = json.dumps(
            {"refresh_token": data["refresh_token"], "client_id": data["client_id"], "client_secret": data["client_secret"],
             "token_uri": data.get("token_uri", TOKEN_URI), "scopes": scopes_for("calendar", False)},
            separators=(",", ":"),
        )
        vault.set_secret(secret_name(service), packed)
    except Exception:
        return  # sem cofre ou arquivo estranho: deixa como está
    old.unlink(missing_ok=True)


def credentials(config: Config, service: str, creds_factory: Callable | None = None, refresher: Callable | None = None):
    """Credenciais prontas para uso (acesso renovado). NotConnected se a conta não foi conectada."""
    _migrate_old_token(config, service)
    raw = vault.get_vault_secret(secret_name(service))
    if not raw:
        raise NotConnected(f"Conta Google ({service}) não conectada. Rode: uv run fidus accounts connect {'agenda' if service == 'calendar' else service}")
    d = json.loads(raw)
    if creds_factory is None:
        from google.oauth2.credentials import Credentials as creds_factory  # type: ignore[no-redef]
    creds = creds_factory(None, refresh_token=d["refresh_token"], client_id=d["client_id"],
                          client_secret=d["client_secret"], token_uri=d["token_uri"], scopes=d["scopes"])
    if refresher is None:
        from google.auth.transport.requests import Request

        refresher = lambda c: c.refresh(Request())  # noqa: E731
    try:
        refresher(creds)
    except Exception as e:
        raise NotConnected(f"O acesso do Google ({service}) expirou ou foi revogado. Conecte de novo: uv run fidus accounts connect {service}") from e
    return creds
