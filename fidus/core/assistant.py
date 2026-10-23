"""Monta o assistente completo (orquestrador + personagens + memória) para os comandos de texto e de voz."""

from __future__ import annotations

from .actionlog import ActionLog
from .characters.speech_cache import SpeechCache
from .config import Config
from .memory.service import get_memory
from .orchestrator import Orchestrator
from .permissions import Confirmer
from .persona import PersonaService
from .providers import create_provider


def build_assistant(config: Config, confirm: Confirmer, provider=None, log: ActionLog | None = None):
    """Devolve (orquestrador, persona, memória)."""
    memory = get_memory(config)
    persona = PersonaService(config, memory=memory)
    orch = Orchestrator(
        config, provider or create_provider(config), confirm, log=log or ActionLog(config.log_path), persona=persona, memory=memory
    )
    return orch, persona, memory


def build_speaker(config: Config, persona, tts_manager, out=print):
    """PersonaSpeaker com o cache de falas de início em disco."""
    from .voice.persona_speech import PersonaSpeaker

    cache = SpeechCache(config.speech_cache_dir, lambda text, path: tts_manager.synthesize(text, path))
    return PersonaSpeaker(config, persona, tts_manager, cache, out)
