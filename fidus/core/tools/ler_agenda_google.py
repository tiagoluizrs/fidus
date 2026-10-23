"""ler_agenda_google: lê eventos do Google Agenda. Somente leitura (escopo calendar.readonly)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .base import Risk, Tool, ToolError

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
MAX_DAYS = 14


def _get_service(config):
    """Autentica via OAuth (token local) e devolve o cliente. Imports pesados só aqui."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    token = config.google_token_path
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not config.google_credentials_path.exists():
                raise ToolError(
                    f"Falta o arquivo de credenciais OAuth em {config.google_credentials_path}. Veja o README."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(config.google_credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json(), encoding="utf-8")
        try:
            token.chmod(0o600)
        except OSError:
            pass
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _format(event: dict) -> str:
    start, end = event.get("start", {}), event.get("end", {})
    if "dateTime" in start:
        s = datetime.fromisoformat(start["dateTime"]).strftime("%d/%m %H:%M")
        e = datetime.fromisoformat(end["dateTime"]).strftime("%H:%M")
        when = f"{s}–{e}"
    else:
        when = f"{date.fromisoformat(start['date']).strftime('%d/%m')} dia inteiro"
    line = f"{when} | {event.get('summary', '(sem título)')}"
    if event.get("location"):
        line += f" | {event['location']}"
    return line  # a descrição do evento não é enviada: só o necessário


class LerAgendaGoogle(Tool):
    name = "ler_agenda_google"
    description = "Lê os eventos do Google Agenda a partir de uma data (padrão: hoje). Somente leitura."
    parameters = {
        "type": "object",
        "properties": {
            "inicio": {"type": "string", "description": "Data inicial AAAA-MM-DD (padrão: hoje)"},
            "dias": {"type": "integer", "description": f"Quantos dias ler, 1 a {MAX_DAYS} (padrão 1)"},
        },
    }
    risk = Risk.LEITURA
    untrusted = True  # títulos e locais de eventos podem trazer instruções escondidas

    def run(self, args, config) -> str:
        try:
            first = date.fromisoformat(args["inicio"]) if args.get("inicio") else date.today()
        except ValueError as e:
            raise ToolError("Data inválida; use AAAA-MM-DD.") from e
        days = max(1, min(int(args.get("dias") or 1), MAX_DAYS))
        tz = datetime.now().astimezone().tzinfo
        t_min = datetime.combine(first, datetime.min.time(), tzinfo=tz)
        t_max = t_min + timedelta(days=days)

        service = _get_service(config)
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=t_min.isoformat(),
                timeMax=t_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
        )
        events = result.get("items", [])
        return "\n".join(_format(e) for e in events) if events else "Nenhum evento no período."


TOOL = LerAgendaGoogle()
