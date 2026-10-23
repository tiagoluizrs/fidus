"""Voz na nuvem pelo ElevenLabs: "voz por descrição" e "sua própria voz" (clonagem com consentimento).

Só biblioteca padrão. Cada pessoa usa a PRÓPRIA chave de API (guardada no cofre do Windows), então a conta, a cota e a voz
clonada ficam com ela. O texto que o Fidus fala (e, na clonagem, a gravação) sai do computador: a tela avisa antes.

Endpoints conferidos na documentação oficial (https://elevenlabs.io/docs/api-reference); ainda não testados com uma conta real.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error
import urllib.request
import uuid
import wave
from collections.abc import Callable
from pathlib import Path

from .tts import QueuedTTS, play_wav

BASE = "https://api.elevenlabs.io"
SAMPLE_RATE = 22_050
TTS_MODEL = "eleven_multilingual_v2"  # inclui português do Brasil
DESIGN_TEXT = "Olá, eu sou o seu assistente. Estou aqui para ajudar com a sua agenda, os seus e-mails e o que mais você precisar hoje."


class CloudVoiceError(RuntimeError):
    pass


def pcm_to_wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class ElevenLabsClient:
    def __init__(self, key: Callable[[], str | None], opener: Callable = urllib.request.urlopen, timeout_s: float = 60.0):
        self._key, self._open, self.timeout_s = key, opener, timeout_s

    # ---- chamadas ----

    def design_previews(self, description: str, text: str | None = None) -> list[dict]:
        """Gera prévias de uma voz a partir da descrição. Devolve [{id, wav}]."""
        description = description.strip()
        if len(description) < 20:
            raise CloudVoiceError("Descreva a voz com mais detalhes (pelo menos 20 caracteres).")
        body: dict = {"voice_description": description[:1000]}
        body.update({"text": text} if text and 100 <= len(text) <= 1000 else {"text": DESIGN_TEXT.ljust(100, ".")})
        data = self._json("POST", f"/v1/text-to-voice/design?output_format=pcm_{SAMPLE_RATE}", body)
        out = []
        for p in data.get("previews", []):
            media = str(p.get("media_type", "")).lower()
            if "mp3" in media or "mpeg" in media:
                raise CloudVoiceError("O serviço devolveu MP3 em vez de áudio PCM; o plano pode não permitir esse formato.")
            out.append({"id": p["generated_voice_id"], "wav": pcm_to_wav(base64.b64decode(p["audio_base_64"]))})
        if not out:
            raise CloudVoiceError("O serviço não devolveu nenhuma prévia. Tente descrever de outro jeito.")
        return out

    def create_voice(self, name: str, description: str, generated_voice_id: str) -> str:
        data = self._json("POST", "/v1/text-to-voice", {
            "voice_name": name[:60], "voice_description": description[:1000] or name, "generated_voice_id": generated_voice_id,
        })
        return str(data["voice_id"])

    def clone_voice(self, name: str, wav: bytes) -> str:
        """Clonagem instantânea a partir de UMA gravação da própria pessoa."""
        boundary = uuid.uuid4().hex
        parts = [
            _field(boundary, "name", name[:60]),
            _field(boundary, "description", "Voz própria criada pelo Fidus com consentimento de quem gravou."),
            _file(boundary, "files", "amostra.wav", wav),
            f"--{boundary}--\r\n".encode(),
        ]
        data = self._json("POST", "/v1/voices/add", raw=b"".join(parts), content_type=f"multipart/form-data; boundary={boundary}")
        return str(data["voice_id"])

    def delete_voice(self, voice_id: str) -> None:
        self._json("DELETE", f"/v1/voices/{_safe_id(voice_id)}")

    def synthesize(self, voice_id: str, text: str) -> bytes:
        """Fala `text` com a voz; devolve um WAV."""
        pcm = self._request("POST", f"/v1/text-to-speech/{_safe_id(voice_id)}?output_format=pcm_{SAMPLE_RATE}",
                            json.dumps({"text": text, "model_id": TTS_MODEL}).encode(), "application/json")
        return pcm_to_wav(pcm)

    # ---- interno ----

    def _json(self, method: str, path: str, body: dict | None = None, raw: bytes | None = None, content_type: str = "application/json") -> dict:
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        reply = self._request(method, path, payload, content_type if payload is not None else None)
        try:
            return json.loads(reply) if reply else {}
        except ValueError as e:
            raise CloudVoiceError("Resposta inesperada do serviço de voz.") from e

    def _request(self, method: str, path: str, payload: bytes | None, content_type: str | None) -> bytes:
        key = self._key()
        if not key:
            raise CloudVoiceError("Falta a chave de API do serviço de voz (Configurações > Personagem > Voz).")
        headers = {"xi-api-key": key, "User-Agent": "Fidus"}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(BASE + path, data=payload, headers=headers, method=method)
        try:
            with self._open(req, timeout=self.timeout_s) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise CloudVoiceError(_http_message(e)) from e
        except OSError as e:
            raise CloudVoiceError("Não consegui falar com o serviço de voz. Confira a internet.") from e


def _safe_id(voice_id: str) -> str:
    if not voice_id or not all(c.isalnum() or c in "-_" for c in voice_id):
        raise CloudVoiceError("Identificador de voz inválido.")
    return voice_id


def _field(boundary: str, name: str, value: str) -> bytes:
    return f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()


def _file(boundary: str, name: str, filename: str, data: bytes) -> bytes:
    head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: audio/wav\r\n\r\n'
    return head.encode() + data + b"\r\n"


def _http_message(e: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(e.read()).get("detail")
        detail = detail.get("message") if isinstance(detail, dict) else (detail if isinstance(detail, str) else "")
    except (ValueError, OSError, AttributeError):
        detail = ""
    if e.code == 401:
        return "A chave de API do serviço de voz não foi aceita. Confira se copiou inteira."
    if e.code in (402, 403):
        return "O seu plano do serviço de voz não permite isso (por exemplo, clonar voz ou criar vozes). " + (detail or "")
    if e.code == 429:
        return "Você atingiu o limite de uso do serviço de voz. Espere um pouco ou veja o seu plano."
    return f"O serviço de voz respondeu com erro {e.code}. {detail or ''}".strip()


class CloudTTS(QueuedTTS):
    """Fala usando uma voz criada no ElevenLabs. `voice.voice` é o id da voz na conta da pessoa."""

    def __init__(self, client: ElevenLabsClient, player: Callable | None = None, tmp_dir: Path | None = None):
        super().__init__()
        self.client, self.player = client, player or play_wav
        self.voice_id = ""
        self.last_error = ""
        import tempfile

        self._tmp = Path(tmp_dir) if tmp_dir else Path(tempfile.gettempdir())
        self._start()

    def _configure(self, voice, base_rate: int) -> None:
        self.voice_id = voice.voice
        self.voice_name = "voz na nuvem"

    def _wav(self, text: str) -> bytes:
        if not self.voice_id:
            raise CloudVoiceError("Este personagem ainda não tem uma voz criada. Crie em Configurações > Personagem > Voz.")
        return self.client.synthesize(self.voice_id, text)

    def _say(self, text: str, cancelled: Callable[[], bool]) -> None:
        out = self._tmp / f"fidus-cloud-{id(self)}.wav"
        try:
            out.write_bytes(self._wav(text))
            self.last_error = ""
            self.player(out, cancelled)
        except CloudVoiceError as e:  # a conversa segue (sem voz) em vez de derrubar o motor
            self.last_error = str(e)
            print(f"[voz] {e}", file=sys.stderr)
        finally:
            out.unlink(missing_ok=True)

    def _play(self, path: Path, cancelled: Callable[[], bool]) -> None:
        self.player(path, cancelled)

    def _synth(self, text: str, path: Path) -> bool:
        path.write_bytes(self._wav(text))
        return True
