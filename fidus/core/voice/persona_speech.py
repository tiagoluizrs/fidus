"""Falas do personagem por momento (início, concluir, confirmar, erro, despedida) e a voz de cada um."""

from __future__ import annotations

from collections.abc import Callable

from ..characters.speech_cache import SpeechCache, voice_fingerprint
from ..config import Config


class PersonaSpeaker:
    """Cola entre o `PersonaService`, o TTS e o cache. Se faltar algo (sem persona, sem TTS), não faz nada."""

    def __init__(self, config: Config, persona, tts, cache: SpeechCache | None = None, out: Callable[[str], None] = print):
        self.config, self.persona, self.tts, self.cache, self.out = config, persona, tts, cache, out
        self._applied: str | None = None
        self._to_cache: list[tuple[str, str]] = []

    def apply_voice(self, character: str | None) -> None:
        """Troca a voz do TTS para a do personagem (só reconfigura quando o personagem muda)."""
        cid = self.persona.resolve_id(character)
        voice = self.persona.voice(cid)
        key = f"{cid}|{voice}"
        if key != self._applied:
            try:
                self.tts.use(voice)
            except Exception as e:  # voz do personagem indisponível: segue com a que estava
                self.out(f"(voz de {cid} indisponível: {e})")
            self._applied = key

    def fingerprint(self) -> str:
        v = getattr(self.tts, "current_voice", None)
        return voice_fingerprint(v, self.tts.base_rate, self.tts.voice_name) if v else ""

    def say_moment(self, character: str | None, moment: str, context: str | None = None, wait: bool = False) -> str | None:
        """Fala uma frase do momento. Início usa o áudio em cache quando existe (resposta na hora)."""
        cid = self.persona.resolve_id(character)
        text = self.persona.phrase(cid, moment, context)
        if not text:
            return None
        if self.config is not None and not self.config.voice.speak_replies:  # "Responder em voz alta" desligado: nada é falado
            return text
        self.apply_voice(cid)
        path = self.cache.lookup(cid, text, self.fingerprint()) if (self.cache and moment == "inicio") else None
        if path is not None:
            self.tts.speak_file(path)
        else:
            self.tts.speak(text)
            if self.cache and moment == "inicio":  # não estava no cache: fala agora e guarda quando estiver ocioso
                self._to_cache.append((cid, text))
        if wait:
            self.tts.wait_idle()
        return text

    def text_for(self, character: str | None, moment: str, context: str | None = None) -> str:
        return self.persona.phrase(self.persona.resolve_id(character), moment, context) or ""

    def flush_pending(self) -> None:
        """Guarda no cache o que foi falado sem cache. Chamar quando o Fidus está ocioso (a voz certa é aplicada)."""
        pending, self._to_cache = self._to_cache, []
        for cid, text in pending:
            self.apply_voice(cid)
            self.cache.get(cid, text, self.fingerprint())
        if pending:
            self._applied = None  # a voz do personagem em uso é reaplicada na próxima fala

    def warm_up(self, characters: list[str] | None = None) -> int:
        """Pré-gera as falas de início de cada personagem. Roda antes de começar a escutar (a 1ª vez demora um pouco)."""
        if not self.cache:
            return 0
        made = 0
        for cid in characters or self.persona.ids():
            self.apply_voice(cid)
            made += self.cache.warm(cid, self.persona.renderings(cid, "inicio"), self.fingerprint())
        self._applied = None
        return made
