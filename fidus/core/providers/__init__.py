from __future__ import annotations

from ..config import Config
from .base import Provider


def create_provider(config: Config) -> Provider:
    from .anthropic import AnthropicProvider  # import preguiçoso

    return AnthropicProvider(config.model)
