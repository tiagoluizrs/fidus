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


CLAUDE_MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5")
GEMINI_MODELS = ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite")  # todos têm plano grátis (com limites)

SCHEMA: dict[str, Rule] = {
    # --- Geral / aparência (a interface aplica) ---
    "app.tema": Rule("choice", choices=("sistema", "claro", "escuro")),
    "app.idioma": Rule("choice", choices=("pt-BR",)),
    "app.iniciar_com_windows": Rule("bool"),
    "app.icone_bandeja": Rule("bool"),
    "app.icone": Rule("choice", choices=("escuro", "claro", "colorido")),  # arte do ícone na bandeja e nas janelas
    "app.janela_inatividade_s": Rule("int", 3, 60),
    # --- Chamados ---
    "chamados.personagem_padrao": Rule("choice", choices=("alfred", "donna", "jarbis")),
    "chamados.som_ao_ouvir": Rule("bool"),
    "chamados.modo": Rule("choice", choices=("auto", "voz", "modelo")),  # como o Fidus percebe o "ei Alfred"
    "chamados.sensibilidade": Rule("int", 0, 100),
    "chamados.esperar_fala_s": Rule("float", 2, 15),
    "chamados.silencio_fim_s": Rule("float", 0.5, 5),
    "chamados.continuacao_s": Rule("float", 0, 30),
    "chamados.atalho_silenciar": Rule("str", max_len=40),
    # --- Voz ---
    "voz.atalho": Rule("str", max_len=40),
    "voz.atalho_ativo": Rule("bool"),
    "voz.microfone": Rule("str", max_len=120),
    "voz.modelo_whisper": Rule("choice", choices=("base", "small", "medium")),
    "voz.idioma": Rule("choice", choices=("pt-BR",)),
    "voz.velocidade_voz": Rule("int", -10, 10),
    "voz.responder_em_voz": Rule("bool"),
    "voz.tempo_confirmacao_s": Rule("float", 3, 30),
    # --- Você e personagens ---
    "usuario.nome": Rule("str", max_len=60),
    "usuario.sobrenome": Rule("str", max_len=60),
    "usuario.genero": Rule("choice", choices=("homem", "mulher", "neutro")),  # define "senhor"/"senhora" nos tratamentos
    "personagens.falar_inicio": Rule("bool"),
    "personagens.falar_despedida": Rule("bool"),
    # --- Modelo de IA ---
    "modelo.provedor": Rule("choice", choices=("claude", "gemini", "local")),
    "modelo.gemini": Rule("str", max_len=80),
    "modelo.claude": Rule("str", max_len=80),
    "modelo.local": Rule("str", max_len=100),  # nome do modelo no Ollama (ex.: qwen3:8b)
    "modelo.local_url": Rule("str", max_len=100),  # só endereços da própria máquina
    "modelo.local_acoes": Rule("bool"),  # liberar ações de escrita com o modelo local
    "modelo.local_acoes_ciente": Rule("bool"),  # o usuário marcou que entende os riscos
    "geral.max_chamadas_ferramenta": Rule("int", 1, 30),
    # --- Memória ---
    "memoria.perguntar_antes_de_guardar": Rule("bool"),
    "memoria.aprender": Rule("bool"),
    "memoria.max_contexto_chars": Rule("int", 200, 6000),
    # --- Privacidade ---
    "privacidade.registrar_acoes": Rule("bool"),
    "privacidade.guardar_log_dias": Rule("int", 1, 3650),
    "privacidade.guardar_historico": Rule("bool"),
    "privacidade.avisar_microfone": Rule("bool"),
    "arquivos.pastas_liberadas": Rule("strlist", max_len=500),
}

# Chaves que só valem depois de reiniciar o núcleo (o Whisper, o microfone e os atalhos são abertos na partida).
RESTART_REQUIRED = {"chamados.modo", "voz.modelo_whisper", "voz.microfone", "voz.atalho", "chamados.atalho_silenciar", "voz.idioma"}


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


def validate_all(key: str, value: Any) -> Any:
    return extra_check(key, validate(key, value))


def extra_check(key: str, value: Any) -> Any:
    """Validações que dependem do conteúdo (atalho válido, modelo com nome razoável, pastas que existem)."""
    import re
    from pathlib import Path

    if key in ("voz.atalho", "chamados.atalho_silenciar"):
        from ..voice.hotkey import parse_hotkey

        try:
            parse_hotkey(value)
        except ValueError as e:
            raise InvalidSetting(f"{key}: {e}") from e
    elif key == "modelo.claude" and not re.fullmatch(r"claude-[a-z0-9][a-z0-9.\-]{2,70}", value):
        raise InvalidSetting("modelo.claude: use um nome de modelo como claude-sonnet-5-5")
    elif key == "modelo.gemini" and not re.fullmatch(r"gemini-[a-z0-9][a-z0-9.\-]{2,60}", value):
        raise InvalidSetting("modelo.gemini: use um nome como gemini-2.5-flash")
    elif key == "modelo.local" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/\-]{0,98}", value):
        raise InvalidSetting("modelo.local: use um nome do Ollama como qwen3:8b")
    elif key == "modelo.local_url":
        from ..providers.ollama import check_local_url

        try:
            return check_local_url(value)
        except ValueError as e:
            raise InvalidSetting(f"modelo.local_url: {e}") from e
    elif key == "arquivos.pastas_liberadas":
        out = []
        for raw in value:
            p = Path(raw).expanduser()
            if not p.is_dir():
                raise InvalidSetting(f"arquivos.pastas_liberadas: a pasta não existe: {raw}")
            out.append(str(p.resolve()))
        return out
    return value


def effective(config) -> dict[str, Any]:
    """Valor em vigor de cada chave da tabela (o que a tela mostra), já com padrões e fidus.toml aplicados."""
    w, v, m, p, a, c = config.wake, config.voice, config.memory, config.privacy, config.app, config.characters
    return {
        "app.tema": a.theme, "app.idioma": a.language, "app.iniciar_com_windows": a.start_with_windows,
        "app.icone_bandeja": a.tray_icon, "app.icone": a.icon, "app.janela_inatividade_s": a.ring_idle_s,
        "chamados.personagem_padrao": w.default_character, "chamados.modo": w.mode, "chamados.som_ao_ouvir": w.beep,
        "chamados.sensibilidade": config.sensitivity if config.sensitivity is not None else 60,
        "chamados.esperar_fala_s": w.wait_speech_s, "chamados.silencio_fim_s": w.silence_s,
        "chamados.continuacao_s": w.followup_s, "chamados.atalho_silenciar": w.mute_hotkey,
        "voz.atalho": v.hotkey, "voz.atalho_ativo": v.hotkey_enabled, "voz.microfone": v.microphone,
        "voz.modelo_whisper": v.whisper_model, "voz.idioma": v.language, "voz.velocidade_voz": v.speech_rate,
        "voz.responder_em_voz": v.speak_replies, "voz.tempo_confirmacao_s": v.confirm_timeout_s,
        "usuario.nome": config.user.name, "usuario.sobrenome": config.user.surname, "usuario.genero": config.user.gender,
        "personagens.falar_inicio": c.speak_start, "personagens.falar_despedida": c.speak_farewell,
        "modelo.provedor": config.provider, "modelo.claude": config.model, "modelo.gemini": config.gemini_model, "modelo.local": config.local_model,
        "modelo.local_url": config.local_url, "modelo.local_acoes": config.local_actions,
        "modelo.local_acoes_ciente": config.local_actions_ack, "geral.max_chamadas_ferramenta": config.max_tool_calls,
        "memoria.perguntar_antes_de_guardar": m.ask_before_saving, "memoria.aprender": m.learn,
        "memoria.max_contexto_chars": m.max_context_chars,
        "privacidade.registrar_acoes": p.log_actions, "privacidade.guardar_log_dias": p.log_days,
        "privacidade.guardar_historico": p.keep_history, "privacidade.avisar_microfone": p.mic_notice,
        "arquivos.pastas_liberadas": [str(x) for x in config.allowed_folders],
    }
