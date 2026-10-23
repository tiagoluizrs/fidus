from __future__ import annotations

from ..config import Config
from .base import Provider


def create_provider(config: Config) -> Provider:
    if config.provider == "local":
        from .ollama import OllamaProvider  # import preguiçoso

        return OllamaProvider(config.local_model, config.local_url)
    if config.provider == "gemini":
        from .. import secrets as vault
        from .gemini import GeminiProvider

        return GeminiProvider(config.gemini_model, lambda: vault.get_secret(vault.GEMINI_KEY))
    from .anthropic import AnthropicProvider

    return AnthropicProvider(config.model)


def sync_provider(orch, config: Config) -> bool:
    """Alinha o provedor em uso com a configuração (troca de provedor ou de modelo, sem reiniciar). True se trocou."""
    current = orch.provider
    kind = getattr(current, "kind", None)  # provedores sem `kind` (dublês de teste) só têm o modelo ajustado
    if kind is not None and kind != config.provider:
        orch.provider = create_provider(config)
        return True
    if hasattr(current, "model"):
        current.model = config.local_model if kind == "local" else config.gemini_model if kind == "gemini" else config.model
    if config.provider == "local" and hasattr(current, "url") and current.url != config.local_url:
        orch.provider = create_provider(config)
        return True
    return False
