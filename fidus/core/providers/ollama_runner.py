"""Liga e desliga o Ollama por conta do Fidus: escolher o modelo local sobe o servidor; trocar de provedor o encerra.

Só encerra o que o próprio Fidus iniciou: se o Ollama já estava aberto (app do Ollama, outro programa), ele é deixado em paz.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

_lock = threading.Lock()
_proc: subprocess.Popen | None = None


def is_up(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/version", timeout=timeout):
            return True
    except Exception:
        return False


def find_binary() -> str | None:
    if found := shutil.which("ollama"):
        return found
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "")
        for p in (Path(base) / "Programs" / "Ollama" / "ollama.exe", Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe"):
            if p.is_file():
                return str(p)
    return None


def ensure_running(url: str, wait_s: float = 20.0) -> bool:
    """Garante que o Ollama responde em `url`. Sobe `ollama serve` (sem janela) se preciso. False se não deu."""
    global _proc
    if is_up(url):
        return True
    with _lock:
        if is_up(url):
            return True
        if _proc is None or _proc.poll() is not None:
            exe = find_binary()
            if not exe:
                return False
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                _proc = subprocess.Popen(
                    [exe, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
                )
            except OSError:
                _proc = None
                return False
    end = time.time() + wait_s
    while time.time() < end:
        if is_up(url):
            return True
        if _proc is not None and _proc.poll() is not None:
            return False
        time.sleep(0.4)
    return False


def stop() -> bool:
    """Encerra o Ollama se (e só se) foi o Fidus que o iniciou. True se encerrou."""
    global _proc
    with _lock:
        proc, _proc = _proc, None
    if proc is None or proc.poll() is not None:
        return False
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    return True


atexit.register(stop)
