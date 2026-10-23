"""Serviço de personagens: junta perfis, frases, prompt e voz. É o que o orquestrador e os laços de voz usam."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime

from .characters.models import Profile, Voice
from .characters.phrases import PhraseEngine, UserInfo
from .characters.prompt import build_system_prompt
from .characters.store import CharacterStore
from .config import Config
from .memory.service import MemoryService
from .providers.base import SystemPrompt


class PersonaService:
    def __init__(
        self,
        config: Config,
        store: CharacterStore | None = None,
        memory: MemoryService | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.config = config
        self.store = store or CharacterStore(config.characters_dir)
        self.memory = memory
        self.engine = PhraseEngine(rng)
        self.clock = clock

    # ---- perfis ----

    def ids(self) -> list[str]:
        return self.store.ids()

    def default_id(self) -> str:
        wanted = self.config.wake.default_character
        return wanted if wanted in self.ids() else self.store.default_id()

    def resolve_id(self, cid: str | None) -> str:
        return cid if cid in self.ids() else self.default_id()

    def profile(self, cid: str | None) -> Profile:
        return self.store.load(self.resolve_id(cid))

    def user(self) -> UserInfo:
        return UserInfo(self.config.user.name, self.config.user.surname, self.config.user.gender)

    # ---- prompt, falas, voz ----

    def system_prompt(self, cid: str | None, base_rules: str, query: str = "", summary: str = "") -> SystemPrompt:
        context = self.memory.context_for(query) if (self.memory and query) else ""
        return build_system_prompt(self.profile(cid), base_rules, self.user(), self.clock(), context, summary)

    def phrase(self, cid: str | None, moment: str, context: str | None = None) -> str | None:
        """Uma fala do momento, sem repetir a anterior; None se nenhuma puder ser montada (variável sem valor)."""
        return self.engine.pick(self.profile(cid), moment, self.user(), self.clock(), context)

    def renderings(self, cid: str | None, moment: str) -> list[str]:
        return self.engine.all_renderings(self.profile(cid), moment, self.user(), self.clock())

    def voice(self, cid: str | None) -> Voice:
        return self.profile(cid).voice

    def ui_profile(self, cid: str | None) -> dict:
        """O que a interface precisa saber do personagem: nome, chamado e as cores do anel."""
        p = self.profile(cid)
        return {"id": p.id, "name": p.name, "call": p.call, "ring": p.ring}
