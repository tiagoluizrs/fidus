"""Instalação guiada do Piper (voz neural local): baixa o programa e as vozes em português, sempre conferindo o SHA-256.

Só endereços fixos (GitHub e Hugging Face, por HTTPS) e só arquivos com hash conhecido: um arquivo diferente do
esperado é descartado antes de ser usado. Nada é baixado sem o usuário pedir.
"""

from __future__ import annotations

import hashlib
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

Progress = Callable[[int, int], None]  # (bytes baixados, total; 0 se desconhecido)

PIPER_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
PIPER_SHA256 = "f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea"
LINUX_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"  # teste no Docker/Linux
LINUX_SHA256 = "a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992"
_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR"

# Vozes pt-BR do catálogo oficial do Piper (todas masculinas, qualidade média). Hash do .onnx = SHA-256 do arquivo LFS.
VOICES: dict[str, dict] = {
    "pt_BR-faber-medium": {
        "label": "Faber", "size_mb": 63, "url": f"{_HF}/faber/medium/pt_BR-faber-medium",
        "onnx_sha256": "858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7",
        "json_sha256": "7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f",
    },
    "pt_BR-cadu-medium": {
        "label": "Cadu", "size_mb": 63, "url": f"{_HF}/cadu/medium/pt_BR-cadu-medium",
        "onnx_sha256": "765f0809a6ea9035d4a6d0d008dbf8876e68b2dd32029312672fa8f405bdb535",
        "json_sha256": "5fe03aa3d4901880554905b12075713cd552598c8a350455a1ec73f8b4e6be19",
    },
    "pt_BR-jeff-medium": {
        "label": "Jeff", "size_mb": 63, "url": f"{_HF}/jeff/medium/pt_BR-jeff-medium",
        "onnx_sha256": "3a6f4c46355813c2b7bbc4d16b6d13d60ed72074b952a393baace82a7d0c94b5",
        "json_sha256": "7bf8145b572b36806f5ce0f1d3322b6711975bc7d0473e8d36fced4a9ec0030d",
    },
}


class SetupError(RuntimeError):
    pass


class PiperStore:
    """Pasta do Piper dentro dos dados do usuário: `piper/` (programa) e `voices/` (modelos)."""

    def __init__(self, root: Path, opener: Callable = urllib.request.urlopen):
        self.root = Path(root)
        self._open = opener

    @property
    def exe(self) -> Path:
        return self.root / "piper" / ("piper.exe" if sys.platform == "win32" else "piper")

    @property
    def voices_dir(self) -> Path:
        return self.root / "voices"

    def model_path(self, voice: str) -> Path | None:
        """`voice` pode ser um id do catálogo ou (compatibilidade) o caminho de um .onnx. None se não existe."""
        if voice in VOICES:
            p = self.voices_dir / f"{voice}.onnx"
            return p if p.is_file() and p.with_suffix(".onnx.json").is_file() else None
        p = Path(voice).expanduser()
        return p if p.suffix == ".onnx" and p.is_file() else None

    def installed_voices(self) -> list[str]:
        return [v for v in VOICES if self.model_path(v)]

    def status(self) -> dict:
        return {
            "supported": _package() is not None,  # Windows x64 (app instalado) ou Linux x86_64 (teste no Docker)
            "installed": self.exe.is_file(),
            "download_mb": 22,
            "voices": [
                {"id": vid, "label": v["label"], "size_mb": v["size_mb"], "installed": self.model_path(vid) is not None}
                for vid, v in VOICES.items()
            ],
        }

    # ---- instalar ----

    def install_piper(self, progress: Progress | None = None) -> None:
        pkg = _package()
        if pkg is None:
            raise SetupError("O instalador do Piper não está disponível para este sistema (só Windows e Linux x86_64).")
        url, sha, kind = pkg
        zip_path = self.root / "piper.pkg.part"
        self._download(url, zip_path, sha, progress)
        target = self.root / "piper"
        tmp = self.root / "piper.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            (_safe_extract_tar if kind == "tar" else _safe_extract)(zip_path, tmp)
            inner = tmp / "piper"  # o pacote traz tudo dentro de uma pasta "piper"
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(inner if inner.is_dir() else tmp), str(target))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            zip_path.unlink(missing_ok=True)
        if not self.exe.is_file():
            raise SetupError("O pacote do Piper não trouxe o programa.")

    def download_voice(self, voice: str, progress: Progress | None = None) -> None:
        if voice not in VOICES:
            raise SetupError(f"Voz desconhecida: {voice}")
        v = VOICES[voice]
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self._download(v["url"] + ".onnx.json", self.voices_dir / f"{voice}.onnx.json", v["json_sha256"], None)
        try:
            self._download(v["url"] + ".onnx", self.voices_dir / f"{voice}.onnx", v["onnx_sha256"], progress)
        except SetupError:
            (self.voices_dir / f"{voice}.onnx.json").unlink(missing_ok=True)  # não deixa uma voz pela metade
            raise

    def remove_voice(self, voice: str) -> None:
        if voice not in VOICES:
            raise SetupError(f"Voz desconhecida: {voice}")
        for ext in (".onnx", ".onnx.json"):
            (self.voices_dir / f"{voice}{ext}").unlink(missing_ok=True)

    # ---- interno ----

    def _download(self, url: str, dest: Path, sha256: str, progress: Progress | None) -> None:
        if not url.startswith("https://"):
            raise SetupError("Só downloads por HTTPS.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part") if dest.suffix != ".part" else dest
        digest = hashlib.sha256()
        try:
            with self._open(urllib.request.Request(url, headers={"User-Agent": "Fidus"}), timeout=60) as resp, open(part, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        except OSError as e:
            part.unlink(missing_ok=True)
            raise SetupError(f"Não consegui baixar ({e}). Confira a internet e tente de novo.") from e
        if digest.hexdigest() != sha256:
            part.unlink(missing_ok=True)
            raise SetupError("O arquivo baixado não confere com o esperado (hash diferente). Descartei por segurança.")
        if part != dest:
            part.replace(dest)


def _package() -> tuple[str, str, str] | None:
    """(endereço, sha256, formato) do programa do Piper para este sistema, ou None se não há."""
    if sys.platform == "win32":
        return PIPER_URL, PIPER_SHA256, "zip"
    if sys.platform.startswith("linux") and platform.machine().lower() in ("x86_64", "amd64"):
        return LINUX_URL, LINUX_SHA256, "tar"
    return None


def _safe_extract_tar(tar_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(tar_path) as t:
        for m in t.getmembers():
            if not (root / m.name).resolve().is_relative_to(root) or m.issym() and not (root / m.name).parent.joinpath(m.linkname).resolve().is_relative_to(root) or m.isdev():
                raise SetupError("Pacote com caminho suspeito; abortei.")
        t.extractall(dest, filter="data")  # mantém a permissão de execução e recusa o que for perigoso


def _safe_extract(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not (root / name).resolve().is_relative_to(root):
                raise SetupError("Pacote com caminho suspeito; abortei.")
        z.extractall(dest)
