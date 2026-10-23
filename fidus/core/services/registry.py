"""Escolhe o adaptador de cada serviço pela configuração. Cada adaptador só é importado quando usado."""

from __future__ import annotations

from collections.abc import Callable

from ..config import Config
from .base import CalendarService, ChatService, EmailService, NotConnected


class ServiceHub:
    def __init__(self, config: Config, factories: dict[str, Callable[[Config], object]] | None = None):
        self.config = config
        self._factories = factories or {}
        self._cache: dict[str, object] = {}

    def _get(self, kind: str, provider: str):
        key = f"{kind}:{provider}"
        if key not in self._cache:
            factory = self._factories.get(key) or _default_factories().get(key)
            if factory is None:
                raise NotConnected(f"Não há suporte ao serviço '{provider}' para {kind}. Veja docs/INTEGRACOES.md.")
            self._cache[key] = factory(self.config)
        return self._cache[key]

    def calendar(self) -> CalendarService:
        return self._get("calendar", self.config.accounts.calendar)  # type: ignore[return-value]

    def email(self) -> EmailService:
        return self._get("email", self.config.accounts.email)  # type: ignore[return-value]

    def chat(self) -> ChatService:
        return self._get("chat", self.config.accounts.chat)  # type: ignore[return-value]


def _default_factories() -> dict[str, Callable[[Config], object]]:
    def google_calendar(cfg):
        from .google_calendar import GoogleCalendar

        return GoogleCalendar(cfg)

    def gmail(cfg):
        from .gmail import Gmail

        return Gmail(cfg)

    def slack(cfg):
        from .slack import Slack

        return Slack(cfg)

    return {"calendar:google": google_calendar, "email:gmail": gmail, "chat:slack": slack}


_hubs: dict[str, ServiceHub] = {}


def get_hub(config: Config) -> ServiceHub:
    key = str(config.data_dir)
    if key not in _hubs:
        _hubs[key] = ServiceHub(config)
    return _hubs[key]


def set_hub(config: Config, hub: ServiceHub | None) -> None:
    """Para testes e para trocar adaptadores (ex.: um servidor MCP no futuro)."""
    if hub is None:
        _hubs.pop(str(config.data_dir), None)
    else:
        _hubs[str(config.data_dir)] = hub
