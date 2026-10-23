"""Adaptador do Google Agenda para `CalendarService`. Leitura por padrão; criar/alterar só com a escrita liberada."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import Config
from . import google_auth
from .base import CalendarEvent, NotConnected


class GoogleCalendar:
    def __init__(self, config: Config, service=None):
        self.config = config
        self._service = service

    @property
    def service(self):
        if self._service is None:
            from googleapiclient.discovery import build  # pesado: só aqui

            creds = google_auth.credentials(self.config, "calendar")
            self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _require_write(self) -> None:
        write_scope = google_auth.scopes_for("calendar", True)[0]
        if not self.config.accounts.google_calendar_write or write_scope not in google_auth.granted_scopes("calendar"):
            raise NotConnected(
                "A escrita na agenda não está liberada. Rode: uv run fidus accounts connect agenda --escrita"
            )

    def list_events(self, start: date, days: int, limit: int = 50) -> list[CalendarEvent]:
        tz = datetime.now().astimezone().tzinfo
        t_min = datetime.combine(start, datetime.min.time(), tzinfo=tz)
        result = (
            self.service.events()
            .list(calendarId="primary", timeMin=t_min.isoformat(), timeMax=(t_min + timedelta(days=days)).isoformat(),
                  singleEvents=True, orderBy="startTime", maxResults=limit)
            .execute()
        )
        return [_to_event(e) for e in result.get("items", [])]

    def create_event(self, title: str, start: datetime, end: datetime, location: str = "") -> CalendarEvent:
        self._require_write()
        body = {"summary": title, "start": {"dateTime": _iso(start)}, "end": {"dateTime": _iso(end)}}
        if location:
            body["location"] = location
        return _to_event(self.service.events().insert(calendarId="primary", body=body).execute())

    def update_event(self, event_id, title=None, start=None, end=None, location=None) -> CalendarEvent:
        self._require_write()
        body: dict = {}
        if title is not None:
            body["summary"] = title
        if start is not None:
            body["start"] = {"dateTime": _iso(start)}
        if end is not None:
            body["end"] = {"dateTime": _iso(end)}
        if location is not None:
            body["location"] = location
        return _to_event(self.service.events().patch(calendarId="primary", eventId=event_id, body=body).execute())


def _iso(dt: datetime) -> str:
    return (dt if dt.tzinfo else dt.astimezone()).isoformat()


def _to_event(e: dict) -> CalendarEvent:
    start, end = e.get("start", {}), e.get("end", {})
    if "dateTime" in start:
        return CalendarEvent(e.get("id", ""), e.get("summary", "(sem título)"), datetime.fromisoformat(start["dateTime"]),
                             datetime.fromisoformat(end["dateTime"]), False, e.get("location", ""))
    return CalendarEvent(e.get("id", ""), e.get("summary", "(sem título)"), date.fromisoformat(start["date"]),
                         date.fromisoformat(end["date"]), True, e.get("location", ""))
