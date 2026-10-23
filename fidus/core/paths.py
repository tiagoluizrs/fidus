"""Onde ficam os dados do usuário (e a migração da pasta antiga `~/.fidus`)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def legacy_data_dir(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".fidus"


def default_data_dir(env: dict[str, str] | None = None, platform: str | None = None, home: Path | None = None) -> Path:
    """`FIDUS_HOME` se definido; no Windows `%APPDATA%\\Fidus`; nos demais sistemas `~/.fidus`."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if env.get("FIDUS_HOME"):
        return Path(env["FIDUS_HOME"])
    if platform == "win32" and env.get("APPDATA"):
        return Path(env["APPDATA"]) / "Fidus"
    return legacy_data_dir(home)


def migrate_legacy(new: Path, legacy: Path) -> bool:
    """Copia a pasta antiga para a nova na primeira execução. Nunca apaga a antiga (isso é decisão do usuário).

    Só migra se a nova ainda não tem dados (a subpasta `app`, do Electron, não conta) e a antiga tem conteúdo. Devolve True se copiou.
    """
    try:
        if new.resolve() == legacy.resolve() or not legacy.is_dir() or not any(legacy.iterdir()):
            return False
        if new.exists() and any(p.name != "app" for p in new.iterdir()):  # "app" é do Electron e já existe quando o núcleo sobe
            return False
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy, new, dirs_exist_ok=True, ignore=shutil.ignore_patterns("debug_audio", "speech_cache"))
        return True
    except OSError:
        return False  # sem migração não é motivo para o Fidus não abrir; os dados antigos continuam onde estão
