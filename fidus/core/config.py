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
class Config:
    model: str = DEFAULT_MODEL
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    allowed_folders: list[Path] = field(default_factory=list)
    allowed_apps: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_APPS))
    data_dir: Path = field(default_factory=lambda: Path.home() / ".fidus")

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
    return cfg
