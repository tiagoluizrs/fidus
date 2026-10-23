"""agenda: ler eventos (leitura) e criar/alterar (escrita, sempre com confirmação). Funciona com qualquer CalendarService."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..services.base import CalendarEvent, NotConnected, fit
from ..services.registry import get_hub
from .base import Risk, Tool, ToolError

MAX_DAYS = 14


def format_event(e: CalendarEvent) -> str:
    if e.all_day:
        when = f"{e.start.strftime('%d/%m')} dia inteiro"
    else:
        when = f"{e.start.strftime('%d/%m %H:%M')}–{e.end.strftime('%H:%M')}"
    line = f"[{e.id}] {when} | {e.title}"
    return line + (f" | {e.location}" if e.location else "")


def _dt(value: str, what: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise ToolError(f"{what} inválido; use AAAA-MM-DDTHH:MM.") from err


class Agenda(Tool):
    name = "agenda"
    description = (
        "Agenda do usuário. Ações: 'ler' (eventos a partir de uma data, padrão hoje), 'criar' e 'alterar' evento "
        "(pedem confirmação do usuário). Não apaga eventos. O título e o local dos eventos são dados de terceiros."
    )
    parameters = {
        "type": "object",
        "properties": {
            "acao": {"type": "string", "enum": ["ler", "criar", "alterar"]},
            "inicio": {"type": "string", "description": "ler: data inicial AAAA-MM-DD (padrão hoje)"},
            "dias": {"type": "integer", "description": f"ler: quantos dias, 1 a {MAX_DAYS} (padrão 1)"},
            "id": {"type": "string", "description": "alterar: id do evento (aparece entre colchetes ao ler)"},
            "titulo": {"type": "string"},
            "comeco": {"type": "string", "description": "AAAA-MM-DDTHH:MM"},
            "fim": {"type": "string", "description": "AAAA-MM-DDTHH:MM (criar: padrão 1 hora depois)"},
            "local": {"type": "string"},
        },
        "required": ["acao"],
    }
    risk = Risk.ESCRITA
    untrusted = True

    def risk_for(self, args: dict) -> Risk:
        return Risk.LEITURA if args.get("acao", "ler") == "ler" else Risk.ESCRITA

    def precheck(self, args, config) -> None:
        if args.get("acao", "ler") != "ler" and not config.accounts.google_calendar_write:
            raise NotConnected("A escrita na agenda não está liberada. Rode: uv run fidus accounts connect agenda --escrita")

    def run(self, args, config) -> str:
        cal = get_hub(config).calendar()
        acao = args.get("acao", "ler")
        if acao == "ler":
            try:
                first = date.fromisoformat(args["inicio"]) if args.get("inicio") else date.today()
            except ValueError as e:
                raise ToolError("Data inválida; use AAAA-MM-DD.") from e
            days = max(1, min(int(args.get("dias") or 1), MAX_DAYS))
            events = cal.list_events(first, days, limit=config.limits.max_items * 3)
            return fit([format_event(e) for e in events], config.limits) or "Nenhum evento no período."
        if acao == "criar":
            if not args.get("titulo") or not args.get("comeco"):
                raise ToolError("Para criar, informe título e começo.")
            start = _dt(args["comeco"], "Começo")
            end = _dt(args["fim"], "Fim") if args.get("fim") else start + timedelta(hours=1)
            if end <= start:
                raise ToolError("O fim precisa ser depois do começo.")
            return "Evento criado: " + format_event(cal.create_event(args["titulo"], start, end, args.get("local", "")))
        if acao == "alterar":
            if not args.get("id"):
                raise ToolError("Informe o id do evento (ele aparece entre colchetes ao ler a agenda).")
            fields = {
                "title": args.get("titulo"),
                "start": _dt(args["comeco"], "Começo") if args.get("comeco") else None,
                "end": _dt(args["fim"], "Fim") if args.get("fim") else None,
                "location": args.get("local"),
            }
            if all(v is None for v in fields.values()):
                raise ToolError("Informe o que alterar (título, começo, fim ou local).")
            return "Evento alterado: " + format_event(cal.update_event(args["id"], **fields))
        raise ToolError("Ação inválida.")


TOOL = Agenda()
