"""Quais configurações a interface pode gravar (em settings.json) e quais valores são aceitos.

Qualquer chave fora desta tabela é recusada: a interface não grava nada arbitrário no núcleo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Rule:
    kind: str  # "bool" | "int" | "float" | "str" | "choice" | "strlist"
    lo: float | None = None
    hi: float | None = None
    choices: tuple[str, ...] = ()
    max_len: int = 200


SCHEMA: dict[str, Rule] = {
    "chamados.personagem_padrao": Rule("choice", choices=("alfred", "donna", "jarbis")),
    "chamados.som_ao_ouvir": Rule("bool"),
    "usuario.nome": Rule("str", max_len=60),
    "usuario.sobrenome": Rule("str", max_len=60),
    "personagens.falar_inicio": Rule("bool"),
    "personagens.falar_despedida": Rule("bool"),
}


class InvalidSetting(ValueError):
    pass


def validate(key: str, value: Any, schema: dict[str, Rule] = SCHEMA) -> Any:
    rule = schema.get(key)
    if rule is None:
        raise InvalidSetting(f"Configuração não permitida: {key}")
    k = rule.kind
    if k == "bool":
        if not isinstance(value, bool):
            raise InvalidSetting(f"{key}: use verdadeiro ou falso")
        return value
    if k in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidSetting(f"{key}: use um número")
        value = int(value) if k == "int" else float(value)
        if (rule.lo is not None and value < rule.lo) or (rule.hi is not None and value > rule.hi):
            raise InvalidSetting(f"{key}: valor fora do intervalo {rule.lo} a {rule.hi}")
        return value
    if k == "str":
        if not isinstance(value, str) or len(value) > rule.max_len:
            raise InvalidSetting(f"{key}: texto inválido ou grande demais")
        return value.strip()
    if k == "choice":
        if value not in rule.choices:
            raise InvalidSetting(f"{key}: use um destes: {', '.join(rule.choices)}")
        return value
    if k == "strlist":
        if not isinstance(value, list) or not all(isinstance(v, str) and len(v) <= rule.max_len for v in value) or len(value) > 100:
            raise InvalidSetting(f"{key}: use uma lista de textos")
        return [v.strip() for v in value if v.strip()]
    raise InvalidSetting(f"{key}: regra desconhecida")
