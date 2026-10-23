"""Escolha de falas e tratamentos: sorteio sem repetir a anterior, variáveis e regras de pular."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime

from .models import Item, Profile

_VAR = re.compile(r"\{(\w+)\}")
_WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


@dataclass
class UserInfo:
    name: str = ""
    surname: str = ""


def time_variables(now: datetime) -> dict[str, str]:
    h = now.hour
    periodo, saudacao = ("manhã", "Bom dia") if 5 <= h < 12 else ("tarde", "Boa tarde") if 12 <= h < 18 else ("noite", "Boa noite")
    hora = f"{h}h" if now.minute == 0 else f"{h}h{now.minute:02d}"
    return {"periodo": periodo, "saudacao": saudacao, "hora": hora, "dia": _WEEKDAYS[now.weekday()]}


def render(template: str, values: dict[str, str]) -> str | None:
    """Preenche {variáveis}. Devolve None se alguma não tiver valor (a frase deve ser pulada)."""
    missing = False

    def sub(m: re.Match) -> str:
        nonlocal missing
        v = values.get(m.group(1), "")
        if not v:
            missing = True
        return v

    out = _VAR.sub(sub, template)
    return None if missing else re.sub(r"\s+", " ", out).strip()


class PhraseEngine:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self._last: dict[tuple[str, str], str] = {}  # (personagem, lista) -> id do último sorteado

    # ---- tratamento ----

    def address_candidates(self, profile: Profile, moment: str | None, user: UserInfo, now: datetime, context: str | None = None) -> list[str]:
        base = {"nome": user.name, "sobrenome": user.surname, **time_variables(now)}
        items = [i for i in profile.address if i.enabled]
        if profile.address_mode == "fixed":
            r = render(profile.address_fixed, base) if profile.address_fixed else None
            return [r] if r else []
        wanted = {c for c in (moment, context) if c}
        if profile.address_mode == "context":
            specific = [i for i in items if wanted & set(i.contexts)]
            general = [i for i in items if not i.contexts]
            items = specific or general or items
        rendered = [(i, render(i.text, base)) for i in items]
        return [r for _, r in rendered if r]

    def _pick_address(self, profile: Profile, moment: str, user: UserInfo, now: datetime, context: str | None) -> str | None:
        cands = self.address_candidates(profile, moment, user, now, context)
        if not cands:
            return None
        key = (profile.id, "tratamento")
        pool = [c for c in cands if c != self._last.get(key)] or cands  # não repete o anterior
        choice = self.rng.choice(pool)
        self._last[key] = choice
        return choice

    # ---- falas ----

    def pick(self, profile: Profile, moment: str, user: UserInfo, now: datetime | None = None, context: str | None = None) -> str | None:
        now = now or datetime.now()
        tratamento = self._pick_address(profile, moment, user, now, context)
        values = {"tratamento": tratamento or "", "nome": user.name, "sobrenome": user.surname, **time_variables(now)}
        usable: list[tuple[Item, str]] = []
        for item in profile.phrases.get(moment, []):
            if item.enabled and (text := render(item.text, values)):
                usable.append((item, text))
        if not usable:
            return None
        key = (profile.id, moment)
        pool = [u for u in usable if u[0].id != self._last.get(key)] or usable  # sem repetir a anterior
        item, text = self.rng.choice(pool)
        self._last[key] = item.id
        return text

    def all_renderings(self, profile: Profile, moment: str, user: UserInfo, now: datetime | None = None) -> list[str]:
        """Todas as falas possíveis do momento (para pré-gerar o áudio). Sem repetições."""
        now = now or datetime.now()
        out: list[str] = []
        for t in self.address_candidates(profile, moment, user, now) or [""]:
            values = {"tratamento": t, "nome": user.name, "sobrenome": user.surname, **time_variables(now)}
            for item in profile.phrases.get(moment, []):
                if item.enabled and (text := render(item.text, values)) and text not in out:
                    out.append(text)
        return out
