"""Configuração: variáveis de ambiente (.env em desenvolvimento) + fidus.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_TOOL_CALLS = 8

# Apps que abrem sem confirmação (nome falado -> comando do Windows).
DEFAULT_APPS = {
    "bloco de notas": "notepad.exe",
    "calculadora": "calc.exe",
    "paint": "mspaint.exe",
    "explorador de arquivos": "explorer.exe",
}


@dataclass
class VoiceConfig:
    hotkey: str = "ctrl+alt+space"
    microphone: str = ""  # índice ou parte do nome; vazio = padrão do sistema
    whisper_model: str = "small"
    compute_type: str = "int8"
    device: str = "cpu"
    language: str = "pt-BR"
    speech_rate: int = 0  # -10 a 10 (SAPI)
    confirm_timeout_s: float = 8.0
    save_debug_audio: bool = False  # desligado: o áudio fica só na memória
    max_record_s: float = 30.0
    min_record_s: float = 0.3  # gravações menores são descartadas (toque acidental)

    @property
    def whisper_language(self) -> str:
        return self.language.split("-")[0].lower()  # pt-BR -> pt


@dataclass
class Config:
    model: str = DEFAULT_MODEL
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    allowed_folders: list[Path] = field(default_factory=list)
    allowed_apps: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_APPS))
    data_dir: Path = field(default_factory=lambda: Path.home() / ".fidus")
    voice: VoiceConfig = field(default_factory=VoiceConfig)

    @property
    def debug_audio_dir(self) -> Path:
        return self.data_dir / "debug_audio"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "actions.log"

    @property
    def google_credentials_path(self) -> Path:
        return self.data_dir / "credentials.json"

    @property
    def google_token_path(self) -> Path:
        return self.data_dir / "token.json"


def _find_config_file(data_dir: Path) -> Path | None:
    explicit = os.environ.get("FIDUS_CONFIG")
    candidates = [Path(explicit)] if explicit else [Path("fidus.toml"), data_dir / "fidus.toml"]
    return next((p for p in candidates if p.is_file()), None)


def load_config() -> Config:
    from dotenv import load_dotenv  # só desenvolvimento; em produção a chave vem do keyring

    load_dotenv()
    cfg = Config(
        model=os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL),
        data_dir=Path(os.environ.get("FIDUS_HOME", Path.home() / ".fidus")),
    )
    path = _find_config_file(cfg.data_dir)
    if path is None:
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg.max_tool_calls = int(data.get("geral", {}).get("max_chamadas_ferramenta", cfg.max_tool_calls))
    folders = data.get("arquivos", {}).get("pastas_liberadas", [])
    cfg.allowed_folders = [Path(f).expanduser().resolve() for f in folders]
    cfg.allowed_apps.update({k.lower(): v for k, v in data.get("apps", {}).get("permitidos", {}).items()})
    _apply_voice(cfg.voice, data.get("voz", {}))
    return cfg


def _apply_voice(v: VoiceConfig, d: dict) -> None:
    v.hotkey = str(d.get("atalho", v.hotkey))
    v.microphone = str(d.get("microfone", v.microphone))
    v.whisper_model = str(d.get("modelo_whisper", v.whisper_model))
    v.compute_type = str(d.get("compute_type", v.compute_type))
    v.device = str(d.get("dispositivo", v.device))
    v.language = str(d.get("idioma", v.language))
    v.speech_rate = max(-10, min(10, int(d.get("velocidade_voz", v.speech_rate))))
    v.confirm_timeout_s = float(d.get("tempo_confirmacao_s", v.confirm_timeout_s))
    v.save_debug_audio = bool(d.get("salvar_audio_debug", v.save_debug_audio))
