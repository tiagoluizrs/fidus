"""Voz neural local Kokoro (inclui voz feminina em português): baixa o modelo e as vozes, conferindo o SHA-256.

Só endereços fixos (GitHub, por HTTPS) e arquivos com hash conhecido. Nada é baixado sem o usuário pedir.
"""

from __future__ import annotations

import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .piper_setup import PiperStore, Progress, SetupError

_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODEL_URL = f"{_BASE}/kokoro-v1.0.int8.onnx"  # versão compacta (~88 MB)
MODEL_SHA256 = "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"
VOICES_URL = f"{_BASE}/voices-v1.0.bin"
VOICES_SHA256 = "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"

# Vozes do Kokoro lidas em português do Brasil.
VOICES: dict[str, dict] = {
    "pf_dora": {"label": "Dora (feminina)"},
    "pm_alex": {"label": "Alex (masculina)"},
    "pm_santa": {"label": "Santa (masculina, grave)"},
    # Vozes britânicas lendo português: saem com sotaque inglês (bom para um mordomo).
    "bm_george": {"label": "George (britânico, maduro)"},
    "bm_fable": {"label": "Fable (britânico, contador de histórias)"},
    "bm_lewis": {"label": "Lewis (britânico, firme)"},
    "bm_daniel": {"label": "Daniel (britânico, jovem)"},
}
DEFAULT_VOICE = "pf_dora"


class KokoroStore(PiperStore):
    """Pasta `kokoro/` dentro dos dados do usuário."""

    @property
    def model(self) -> Path:
        return self.root / "kokoro-v1.0.int8.onnx"

    @property
    def voices_file(self) -> Path:
        return self.root / "voices-v1.0.bin"

    def installed(self) -> bool:
        return self.model.is_file() and self.voices_file.is_file()

    def status(self) -> dict:
        try:
            import kokoro_onnx  # noqa: F401

            lib = True
        except ImportError:
            lib = False
        return {
            "supported": lib,
            "installed": self.installed(),
            "download_mb": 116,
            "voices": [{"id": vid, "label": v["label"], "installed": self.installed()} for vid, v in VOICES.items()],
        }

    def install(self, progress: Progress | None = None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._download(VOICES_URL, self.voices_file, VOICES_SHA256, None)
        try:
            self._download(MODEL_URL, self.model, MODEL_SHA256, progress)
        except SetupError:
            self.voices_file.unlink(missing_ok=True)  # não deixa pela metade
            raise

    def remove(self) -> None:
        for p in (self.model, self.voices_file):
            p.unlink(missing_ok=True)


_engine_lock = threading.Lock()
_engine: tuple[str, object] | None = None


def load_engine(store: KokoroStore):
    """Carrega o modelo uma vez só (leva ~1 s) e reaproveita nas falas seguintes."""
    global _engine
    with _engine_lock:
        key = str(store.model)
        if _engine is None or _engine[0] != key:
            if not store.installed():
                raise RuntimeError("A voz Kokoro ainda não foi instalada: instale em Configurações > Personagem > Voz.")
            from kokoro_onnx import Kokoro

            _engine = (key, Kokoro(str(store.model), str(store.voices_file)))
        return _engine[1]
