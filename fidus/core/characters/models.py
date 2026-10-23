"""Modelos de dados de um personagem já resolvido (padrão + edições do usuário)."""

from __future__ import annotations

from dataclasses import dataclass, field

MOMENTS = ("inicio", "concluir", "confirmar", "erro", "despedida")
CONTROLS = ("formalidade", "humor", "aspereza", "iniciativa", "detalhe")
STYLES = ("padrao", "mais_seco", "mais_engracado", "mais_aspero", "personalizado")
ADDRESS_MODES = ("random", "fixed", "context")
VARIABLES = ("tratamento", "nome", "sobrenome", "periodo", "hora", "dia", "saudacao")


@dataclass
class Item:
    """Uma frase ou um tratamento. `origin`: padrao, editada (texto mudou) ou usuario (adicionada)."""

    id: str
    text: str
    enabled: bool = True
    origin: str = "padrao"
    contexts: list[str] = field(default_factory=list)  # só para tratamentos


@dataclass
class Voice:
    engine: str = "sapi"  # sapi | piper | descricao
    voice: str = ""  # parte do nome da voz (vazio = a do sistema); no Piper, o caminho do modelo .onnx
    pitch: int = 0  # -10 a 10
    rate: int = 0  # -10 a 10, somado à velocidade geral


@dataclass
class Personality:
    base_style: str = "padrao"
    controls: dict[str, int] = field(default_factory=dict)
    persona: str = ""
    extra: str = ""


@dataclass
class Profile:
    id: str
    name: str
    call: str
    summary: str
    default: bool
    ring: dict[str, list[str]]
    personality: Personality
    address_mode: str
    address_fixed: str
    address: list[Item]
    phrases: dict[str, list[Item]]
    voice: Voice
