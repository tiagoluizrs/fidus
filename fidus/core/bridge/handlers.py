"""Operações que as telas de Configurações pedem ao núcleo: personagens, memória, contas, privacidade e "sobre".

Cada comando do protocolo recebe `{op: "...", ...}`. Tudo é validado aqui; a interface nunca grava direto em disco.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import secrets as vault
from .. import settings as settings_io
from ..actionlog import ActionLog
from ..characters.models import CONTROLS, MOMENTS
from ..characters.store import ADDRESS, CharacterStore
from ..memory.markdown_store import SECTIONS, TAGS
from ..memory.service import get_memory
from ..services import google_auth
from ..services.base import NotConnected

VERSION = "0.1.0"
MAX_ITEM = 300
LISTS = (*MOMENTS, ADDRESS)
CONTEXTS = (*MOMENTS, "formal")


def _need(args: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in args]
    if missing:
        raise ValueError(f"Falta o argumento: {', '.join(missing)}")


def _text(value: Any, limit: int = MAX_ITEM) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("O texto não pode ser vazio.")
    if len(value) > limit:
        raise ValueError(f"Texto grande demais (máximo {limit} caracteres).")
    return value.strip()


def _confirmed(args: dict) -> None:
    if args.get("confirm") is not True:
        raise ValueError("Ação sem volta: precisa de confirmação explícita (confirm: true).")


_KEY_CHARS = __import__("re").compile(r"[A-Za-z0-9_\-.~+/=]+")


class Handlers:
    def __init__(self, config, state, persona, loop=None, save_settings: Callable[[dict], None] | None = None):
        self.config, self.state, self.persona, self.loop = config, state, persona, loop
        self.store: CharacterStore = persona.store
        self.save_settings = save_settings or (lambda patch: None)
        self._jobs: set[str] = set()
        self._jobs_lock = __import__("threading").Lock()
        self._previews: dict[str, bytes] = {}  # prévias de voz geradas (só na memória)
        self._sample: bytes | None = None  # gravação da própria voz (só na memória; apagada depois de enviada)
        self._recording = False
        self._oauth_lock = __import__("threading").Lock()
        self._oauth_pending: dict | None = None  # login do Google em andamento (só um por vez: a porta de retorno é fixa no Docker)

    def emit(self, type: str, **data) -> None:
        self.state.events.emit(type, **data)

    # ================================================================== personagens

    def _profile(self, cid: str) -> dict:
        pr = self.store.load(cid)
        d = self.store._default(cid)
        controls = {
            k: {"value": pr.personality.controls[k], "default": d["personality"]["controls"][k]} for k in CONTROLS
        }

        def items(lst):
            return [{"id": i.id, "text": i.text, "enabled": i.enabled, "origin": i.origin, "contexts": i.contexts} for i in lst]

        def gone(name):
            return [{"id": i.id, "text": i.text} for i in self.store.deleted_items(cid, name)]

        return {
            "id": pr.id, "name": pr.name, "call": pr.call, "summary": pr.summary, "ring": pr.ring,
            "is_default": cid == self.persona.default_id(), "edited": self.store.has_user_edits(cid),
            "personality": {"base_style": pr.personality.base_style, "default_style": d["personality"]["base_style"],
                            "controls": controls, "extra": pr.personality.extra},
            "address": {"mode": pr.address_mode, "fixed": pr.address_fixed, "items": items(pr.address), "deleted": gone(ADDRESS)},
            "phrases": {m: {"items": items(pr.phrases[m]), "deleted": gone(m)} for m in MOMENTS},
            "voice": {"engine": pr.voice.engine, "voice": pr.voice.voice, "pitch": pr.voice.pitch, "rate": pr.voice.rate, "description": pr.voice.description,
                      "default": d["voice"]},
            "variables": ["{tratamento}", "{nome}", "{sobrenome}", "{periodo}", "{hora}", "{dia}", "{saudacao}"],
        }

    def characters(self, op: str = "list", **a) -> dict:
        s = self.store
        if op == "list":
            return {"characters": [
                {"id": c, "name": (p := s.load(c)).name, "call": p.call, "summary": p.summary, "ring": p.ring,
                 "is_default": c == self.persona.default_id(), "edited": s.has_user_edits(c)} for c in s.ids()]}
        _need(a, "id")
        cid = a["id"]
        s.load(cid)  # valida que existe
        if op == "get":
            return self._profile(cid)
        if op == "set_control":
            _need(a, "control", "value")
            if isinstance(a["value"], bool) or not isinstance(a["value"], (int, float)):
                raise ValueError("O valor do controle precisa ser um número de 0 a 100.")
            s.set_control(cid, a["control"], int(a["value"]))
        elif op == "reset_control":
            _need(a, "control")
            s.reset_control(cid, a["control"])
        elif op == "set_style":
            _need(a, "style")
            s.set_style(cid, a["style"])
        elif op == "set_extra":
            s.set_extra(cid, str(a.get("text", ""))[:2000])
        elif op == "reset_personality":
            s.reset_personality(cid)
        elif op == "set_address_mode":
            _need(a, "mode")
            s.set_address_mode(cid, a["mode"], None if a.get("fixed") is None else str(a["fixed"])[:60])
        elif op in ("item_edit", "item_enable", "item_delete", "item_add", "restore_deleted", "reset_list"):
            _need(a, "list")
            if a["list"] not in LISTS:
                raise ValueError(f"Lista inválida: {a['list']}")
            lst = a["list"]
            if op == "item_edit":
                _need(a, "item", "text")
                s.edit_item(cid, lst, str(a["item"]), _text(a["text"]))
            elif op == "item_enable":
                _need(a, "item", "enabled")
                if not isinstance(a["enabled"], bool):
                    raise ValueError("'enabled' precisa ser verdadeiro ou falso")
                s.set_enabled(cid, lst, str(a["item"]), a["enabled"])
            elif op == "item_delete":
                _need(a, "item")
                s.delete_item(cid, lst, str(a["item"]))
            elif op == "item_add":
                ctx = [c for c in a.get("contexts", []) if c in CONTEXTS] if lst == ADDRESS else None
                s.add_item(cid, lst, _text(a.get("text")), ctx)
            elif op == "restore_deleted":
                s.restore_deleted(cid, lst)
            else:
                s.reset_list(cid, lst)
        elif op == "set_voice":
            fields = {k: a[k] for k in ("engine", "voice", "pitch", "rate", "description") if k in a}
            if "engine" in fields and fields["engine"] not in ("sapi", "piper", "descricao", "propria"):
                raise ValueError("Motor de voz inválido.")
            if "voice" in fields:
                fields["voice"] = str(fields["voice"])[:300]
            if "description" in fields:
                fields["description"] = str(fields["description"])[:1000]
            for k in ("pitch", "rate"):
                if k in fields and (isinstance(fields[k], bool) or not isinstance(fields[k], (int, float))):
                    raise ValueError(f"'{k}' precisa ser um número de -10 a 10.")
            s.set_voice(cid, **fields)
        elif op == "reset_voice":
            s.reset_voice(cid)
        elif op == "reset":
            s.reset_character(cid)
        elif op == "preview":
            return self._preview(cid, str(a.get("text", "")) or None)
        else:
            raise ValueError(f"Operação desconhecida: {op}")
        self.emit("characters_changed", id=cid)
        return self._profile(cid)

    def _preview(self, cid: str, text: str | None) -> dict:
        """Ouvir amostra: fala uma frase com a voz do personagem (o núcleo simulado não fala)."""
        speaker = getattr(self.loop, "speaker", None)
        if not speaker:
            return {"spoken": False, "reason": "A voz só está disponível com o núcleo real."}
        sample = text or f"Olá, eu sou {self.store.load(cid).name}."
        speaker.apply_voice(cid)
        speaker.tts.speak(sample)
        return {"spoken": True, "text": sample}

    def voices(self, engine: str = "sapi") -> dict:
        tts = getattr(getattr(self.loop, "speaker", None), "tts", None)
        return {"engine": engine, "voices": tts.list_voices(engine) if tts else []}

    # ================================================================== memória

    def memory(self, op: str = "list", **a) -> dict:
        mem = get_memory(self.config).md

        def row(e):
            return {"id": e.id, "section": e.section, "text": e.text, "tag": e.tag, "ts": e.ts, "source": e.src}

        if op == "list":
            q = str(a.get("query", "")).strip()
            rows = mem.search(q, limit=200) if q else mem.list(a.get("section") or None, a.get("tag") or None)
            return {"entries": [row(e) for e in rows], "sections": [*SECTIONS], "tags": [*TAGS],
                    "learn": self.config.memory.learn, "ask_before_saving": self.config.memory.ask_before_saving}
        if op == "add":
            e = mem.add(a.get("section") or "perfil", _text(a.get("text"), 500), a.get("tag") or None, source="usuario")
        elif op == "edit":
            _need(a, "id")
            e = mem.edit(str(a["id"]), _text(a["text"], 500) if "text" in a else None, a.get("tag") or None, clear_tag=a.get("tag") == "")
        elif op == "delete":
            _need(a, "id")
            _confirmed(a)
            e = mem.delete(str(a["id"]))
        elif op == "export":
            return {"markdown": mem.export_markdown(), "filename": "memoria-fidus.md"}
        elif op == "delete_all":
            _confirmed(a)
            n = get_memory(self.config).forget_everything()
            self.emit("memory_changed")
            return {"deleted": n}
        else:
            raise ValueError(f"Operação desconhecida: {op}")
        self.emit("memory_changed")
        return {"entry": row(e)}

    # ================================================================== contas

    def _accounts_status(self) -> dict:
        ac = self.config.accounts
        g_cred = self.config.google_credentials_path.is_file()
        tok = bool(vault.get_secret(vault.SLACK_TOKEN))
        return {
            "google_credentials": g_cred,
            "services": [
                {"id": "gmail", "kind": "email", "name": "Gmail", "connected": google_auth.is_connected("gmail"),
                 "write": ac.gmail_drafts, "write_label": "criar rascunhos"},
                {"id": "outlook", "kind": "email", "name": "Outlook", "coming_soon": True},
                {"id": "slack", "kind": "chat", "name": "Slack", "connected": tok, "write": ac.slack_write,
                 "write_label": "responder mensagens", "channels": list(ac.slack_channels)},
                {"id": "teams", "kind": "chat", "name": "Teams", "coming_soon": True},
                {"id": "agenda", "kind": "calendar", "name": "Google Agenda", "connected": google_auth.is_connected("calendar"),
                 "write": ac.google_calendar_write, "write_label": "criar e alterar eventos"},
                {"id": "msagenda", "kind": "calendar", "name": "Microsoft Agenda", "coming_soon": True},
            ],
        }

    def accounts(self, op: str = "list", **a) -> dict:
        if op == "list":
            return self._accounts_status()
        if op == "google_credentials":  # o credentials.json enviado pela tela (em vez de copiar o arquivo à mão)
            text = str(a.get("json", ""))
            if len(text) > 20000:
                raise ValueError("Arquivo grande demais para ser o credentials.json.")
            try:
                google_auth.validate_client_file(text)
            except NotConnected as e:
                raise ValueError(str(e)) from e
            path = self.config.google_credentials_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            return self._accounts_status()
        if op == "google_credentials_remove":
            self.config.google_credentials_path.unlink(missing_ok=True)
            return self._accounts_status()
        service = a.get("service")
        if service not in ("gmail", "agenda", "slack"):
            raise ValueError("Serviço inválido.")
        if op == "connect":
            write = a.get("write", False) is True
            if service == "slack":
                token = str(a.get("token", "")).strip()
                if not token:
                    raise ValueError("Cole o token de usuário do Slack (xoxp-...).")
                from ..services.slack import Slack

                info = Slack(self.config, token=token)._call("auth.test")  # valida antes de guardar
                vault.set_secret(vault.SLACK_TOKEN, token)
                self.save_settings({"contas.slack.escrita": write})
                self.emit("accounts", service=service, status="connected", message=f"{info.get('team', '')}")
                return self._accounts_status()
            if not self.config.google_credentials_path.is_file():  # antes de abrir qualquer login
                raise ValueError("Envie primeiro o credentials.json do Google, em \"Credenciais do Google\" (acima, na tela de Contas).")
            self._connect_google(service, write)
            return {"started": True, "message": "Autorize no navegador que vai abrir." if not getattr(self.loop, "headless", False) else "Clique no link de autorização que vai aparecer."}
        if op == "disconnect":
            if service == "slack":
                vault.delete_secret(vault.SLACK_TOKEN)
                self.save_settings({"contas.slack.escrita": False})
            else:
                svc = "calendar" if service == "agenda" else "gmail"
                google_auth.disconnect(svc)
                self.save_settings({("contas.google.agenda_escrita" if service == "agenda" else "contas.google.gmail_rascunhos"): False})
            self.emit("accounts", service=service, status="disconnected", message="")
            return self._accounts_status()
        if op in ("channel_add", "channel_remove") and service == "slack":
            name = str(a.get("name", "")).strip().lstrip("#")
            if not name or len(name) > 80:
                raise ValueError("Informe o nome do canal.")
            chans = list(self.config.accounts.slack_channels)
            if op == "channel_add" and name not in chans:
                chans.append(name)
            if op == "channel_remove":
                chans = [c for c in chans if c != name]
            self.save_settings({"contas.slack.canais_permitidos": chans})
            return self._accounts_status()
        raise ValueError(f"Operação desconhecida: {op}")

    def _connect_google(self, service: str, write: bool) -> None:
        svc = "calendar" if service == "agenda" else "gmail"
        with self._oauth_lock:
            pending = self._oauth_pending
            if pending is not None:
                if pending["service"] != service:
                    raise ValueError("Já existe um login do Google em andamento. Conclua-o no navegador ou espere até 5 minutos.")
                if pending["url"]:
                    self.emit("open_url", url=pending["url"])  # segundo clique: mostra o mesmo link de novo, sem abrir outro login
                return
            self._oauth_pending = state = {"service": service, "url": None}

        def remember(url: str) -> None:
            state["url"] = url
            self.emit("open_url", url=url)

        def work() -> None:
            try:
                headless = getattr(self.loop, "headless", False)
                google_auth.connect(self.config, svc, write, open_url=remember if headless else None)
                self.save_settings({("contas.google.agenda_escrita" if service == "agenda" else "contas.google.gmail_rascunhos"): write})
                self.emit("accounts", service=service, status="connected", message="")
            except OSError as e:
                busy = e.errno in (98, 10048)  # porta do retorno do login ocupada
                self.emit("accounts", service=service, status="error", message="A porta do login do Google está ocupada. Reinicie o Fidus e tente de novo." if busy else str(e))
            except Exception as e:  # falta o credentials.json, o usuário fechou o navegador, etc.
                self.emit("accounts", service=service, status="error", message=str(e))
            finally:
                with self._oauth_lock:
                    self._oauth_pending = None

        threading.Thread(target=work, daemon=True, name="fidus-oauth").start()

    # ================================================================== privacidade

    def privacy(self, op: str = "get", **a) -> dict:
        cfg = self.config
        log = ActionLog(cfg.log_path, cfg)
        if op == "get":
            return {
                "folders": [str(p) for p in cfg.allowed_folders], "log_actions": cfg.privacy.log_actions,
                "log_days": cfg.privacy.log_days, "keep_history": cfg.privacy.keep_history, "mic_notice": cfg.privacy.mic_notice,
                "data_dir": str(cfg.data_dir), "log_path": str(cfg.log_path),
            }
        if op == "log":
            rows = [r for r in log.read(min(int(a.get("limit", 100)), 500)) if "decision" in r]  # só ações executadas
            return {"entries": rows}
        if op == "prune_log":
            return {"removed": log.prune(cfg.privacy.log_days)}
        if op == "export":
            return self._export(Path(str(a.get("path", ""))))
        if op == "clear_history":
            _confirmed(a)
            return {"deleted": get_memory(cfg).db.clear_history()}
        if op == "clear_log":
            _confirmed(a)
            cfg.log_path.unlink(missing_ok=True)
            return {"cleared": True}
        if op == "clear_all":
            _confirmed(a)
            return self._clear_all()
        raise ValueError(f"Operação desconhecida: {op}")

    def _export(self, path: Path) -> dict:
        if path.suffix.lower() != ".zip" or not path.parent.is_dir():
            raise ValueError("Escolha um arquivo .zip em uma pasta que exista.")
        cfg, mem = self.config, get_memory(self.config)
        added: list[str] = []
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for base, label in ((cfg.memory_dir, "memoria"), (cfg.characters_dir, "personagens")):
                if base.is_dir():
                    for f in sorted(base.rglob("*")):
                        if f.is_file() and f.suffix in (".md", ".json"):
                            z.write(f, f"{label}/{f.relative_to(base).as_posix()}")
                            added.append(f"{label}/{f.name}")
            if cfg.settings_path.is_file():
                z.write(cfg.settings_path, "configuracoes.json")  # sem segredos: tokens ficam no cofre
                added.append("configuracoes.json")
            if cfg.log_path.is_file():
                z.write(cfg.log_path, "log-de-acoes.jsonl")
                added.append("log-de-acoes.jsonl")
            history = mem.db.messages(limit=100000) if cfg.db_path.exists() else []
            z.writestr("historico.json", json.dumps(history, ensure_ascii=False, indent=2))
            added.append("historico.json")
        return {"path": str(path), "files": added}

    def _clear_all(self) -> dict:
        """Apaga memória, histórico, edições de personagem, cache de voz, log e TODAS as chaves do cofre."""
        import shutil

        cfg, mem = self.config, get_memory(self.config)
        done = {"lembrancas": mem.md.delete_all(), "banco": mem.wipe_database()}
        for d in (cfg.characters_dir, cfg.speech_cache_dir):
            shutil.rmtree(d, ignore_errors=True)
        cfg.log_path.unlink(missing_ok=True)
        cfg.google_token_path.unlink(missing_ok=True)
        keys = 0
        for name in vault.KNOWN:
            try:
                keys += int(vault.delete_secret(name))
            except vault.VaultUnavailable:
                pass
        done["chaves"] = keys
        for k in ("calendar", "gmail"):
            self.config.accounts.google_calendar_write = self.config.accounts.gmail_drafts = self.config.accounts.slack_write = False
        self.emit("memory_changed")
        self.emit("characters_changed", id="*")
        return done

    # ================================================================== sobre

    def about(self, op: str = "get", **a) -> dict:
        cfg = self.config
        info = {
            "version": VERSION, "python": platform.python_version(), "platform": platform.platform(),
            "model": cfg.model, "data_dir": str(cfg.data_dir), "characters": self.store.ids(),
            "whisper": cfg.voice.whisper_model, "frozen": bool(getattr(sys, "frozen", False)),
        }
        if op == "diagnostics":
            # nada de conversas, memória nem chaves: só o necessário para pedir ajuda
            info["diagnostics"] = "\n".join(f"{k}: {v}" for k, v in info.items())
        return info

    # ================================================================== microfones e chave da API

    def devices(self) -> dict:
        try:
            from ..voice.audio import list_devices

            return {"devices": [{"index": d["index"], "name": d["name"], "default": d["default"]} for d in list_devices()]}
        except Exception as e:  # sem PortAudio ou sem microfone
            return {"devices": [], "error": f"{type(e).__name__}"}

    def api_key(self, op: str = "status", value: str = "", provider: str = "claude") -> dict:
        """Chave do provedor (Anthropic ou Gemini). Nunca volta para a tela: só `stored` (guardada ou não) e de onde vem."""
        if provider == "gemini":
            return self._gemini_key(op, value)
        if op == "set":
            key = (value or "").strip()
            if not key.startswith("sk-ant-") or len(key) < 20 or any(c.isspace() for c in key):
                raise ValueError("Isso não parece uma chave da Anthropic (começa com sk-ant-).")
            vault.set_secret(vault.ANTHROPIC_KEY, key)
            self._refresh_provider_key()
        elif op == "delete":
            vault.delete_secret(vault.ANTHROPIC_KEY)
            self._refresh_provider_key()
        elif op != "status":
            raise ValueError(f"Operação desconhecida: {op}")
        in_vault = vault.get_vault_secret(vault.ANTHROPIC_KEY) is not None
        return {"stored": in_vault, "source": "cofre" if in_vault else ("ambiente" if vault.get_secret(vault.ANTHROPIC_KEY) else "nenhuma")}

    def _gemini_key(self, op: str, value: str) -> dict:
        name = vault.GEMINI_KEY
        if op == "set":
            key = (value or "").strip()
            # O formato das chaves do Google muda com o tempo: só conferimos o básico (tamanho e caracteres de uma chave).
            if not 20 <= len(key) <= 400 or not _KEY_CHARS.fullmatch(key) or key.startswith("sk-ant-"):
                raise ValueError("Isso não parece uma chave do Gemini. Copie a chave inteira, sem espaços (aistudio.google.com > Get API key).")
            vault.set_secret(name, key)
        elif op == "delete":
            vault.delete_secret(name)
        elif op != "status":
            raise ValueError(f"Operação desconhecida: {op}")
        in_vault = vault.get_vault_secret(name) is not None
        return {"stored": in_vault, "source": "cofre" if in_vault else ("ambiente" if vault.get_secret(name) else "nenhuma")}

    # ================================================================== voz: Piper (local) e nuvem

    def piper(self, op: str = "status", voice: str = "") -> dict:
        """Instalação guiada do Piper. Baixar roda em segundo plano e avisa pelo evento `voice_setup`."""
        from ..voice.piper_setup import VOICES, PiperStore, SetupError

        store = PiperStore(self.config.data_dir / "piper")
        try:
            if op == "status":
                return {**store.status(), "busy": bool(self._jobs)}
            if op == "install":
                self._job("piper", store.install_piper)
            elif op == "download_voice":
                if voice not in VOICES:
                    raise ValueError(f"Voz desconhecida: {voice}")
                self._job(voice, lambda progress: store.download_voice(voice, progress))
            elif op == "remove_voice":
                store.remove_voice(voice)
                return {**store.status(), "busy": bool(self._jobs)}
            else:
                raise ValueError(f"Operação desconhecida: {op}")
        except SetupError as e:
            raise ValueError(str(e)) from e
        return {"started": True}

    def _job(self, name: str, fn, event: str = "voice_setup") -> None:
        import threading
        import time

        from ..voice.piper_setup import SetupError

        with self._jobs_lock:
            if self._jobs:
                raise ValueError("Já existe um download em andamento. Espere terminar.")
            self._jobs.add(name)
        last = [0.0]

        def progress(done: int, total: int) -> None:
            if time.monotonic() - last[0] > 0.25:
                last[0] = time.monotonic()
                self.emit(event, what=name, state="progress", done=done, total=total)

        def run() -> None:
            try:
                fn(progress)
                self.emit(event, what=name, state="done")
            except (SetupError, OSError, RuntimeError) as e:  # RuntimeError: OllamaError
                self.emit(event, what=name, state="error", message=str(e))
            finally:
                with self._jobs_lock:
                    self._jobs.discard(name)

        threading.Thread(target=run, daemon=True, name="fidus-voice-setup").start()

    def _eleven(self):
        from .. import secrets as vault
        from ..voice.elevenlabs import ElevenLabsClient

        return ElevenLabsClient(lambda: vault.get_secret(vault.ELEVENLABS_KEY))

    def voice_cloud(self, op: str = "status", **a) -> dict:
        """Voz na nuvem (ElevenLabs): a chave é da própria pessoa e nunca volta para a tela."""
        from .. import secrets as vault
        from ..voice.elevenlabs import CloudVoiceError

        try:
            if op == "set_key":
                key = str(a.get("value", "")).strip()
                if len(key) < 20 or any(c.isspace() for c in key):
                    raise ValueError("Isso não parece uma chave de API do serviço de voz.")
                vault.set_secret(vault.ELEVENLABS_KEY, key)
            elif op == "clear_key":
                vault.delete_secret(vault.ELEVENLABS_KEY)
            elif op == "design_preview":
                previews = self._eleven().design_previews(str(a.get("description", "")))[-3:]
                self._previews = {p["id"]: p["wav"] for p in previews}
                return {**self._cloud_status(), "previews": [{"id": p["id"]} for p in previews]}
            elif op == "play_preview":
                wav = self._previews.get(str(a.get("preview", "")))
                if wav is None:
                    raise ValueError("Essa prévia expirou. Gere de novo.")
                self._play_wav_bytes(wav)
            elif op == "save_preview":
                cid, pid = self._char(a), str(a.get("preview", ""))
                if pid not in self._previews:
                    raise ValueError("Essa prévia expirou. Gere de novo.")
                desc = str(a.get("description", ""))
                voice_id = self._eleven().create_voice(f"Fidus {self.store.load(cid).name}", desc, pid)
                self.store.set_voice(cid, engine="descricao", voice=voice_id, description=desc[:1000])
                self._after_voice_change(cid)
            elif op == "record_sample":
                self._record_sample(max(5, min(60, int(a.get("seconds", 30)))))
                return {"started": True}
            elif op == "clone":
                if a.get("consent") is not True:
                    raise ValueError("Marque que você consente em gravar e usar a sua voz.")
                if self._sample is None:
                    raise ValueError("Grave a sua voz primeiro.")
                cid = self._char(a)
                voice_id = self._eleven().clone_voice(f"Fidus {self.store.load(cid).name} (minha voz)", self._sample)
                self.store.set_voice(cid, engine="propria", voice=voice_id, description="")
                self._sample = None  # a gravação não fica guardada no computador
                self._after_voice_change(cid)
            elif op == "delete_voice":
                cid = self._char(a)
                voice = self.store.load(cid).voice
                if voice.engine in ("descricao", "propria") and voice.voice:
                    self._eleven().delete_voice(voice.voice)
                self.store.reset_voice(cid)
                self._after_voice_change(cid)
            elif op != "status":
                raise ValueError(f"Operação desconhecida: {op}")
        except CloudVoiceError as e:
            raise ValueError(str(e)) from e
        return self._cloud_status()

    def _cloud_status(self) -> dict:
        from .. import secrets as vault

        return {
            "has_key": bool(vault.get_secret(vault.ELEVENLABS_KEY)),
            "stored": vault.get_vault_secret(vault.ELEVENLABS_KEY) is not None,
            "has_sample": self._sample is not None,
        }

    def _char(self, a: dict) -> str:
        cid = str(a.get("id", ""))
        if cid not in self.store.ids():
            raise ValueError(f"Personagem desconhecido: {cid}")
        return cid

    def _after_voice_change(self, cid: str) -> None:
        speaker = getattr(self.loop, "speaker", None)
        if speaker:
            speaker.apply_voice(cid)
        self.emit("characters_changed", id=cid)

    def _play_wav_bytes(self, wav: bytes) -> None:
        import tempfile
        import threading
        from pathlib import Path

        from ..voice.tts import play_wav

        def run() -> None:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "previa.wav"
                p.write_bytes(wav)
                play_wav(p)

        threading.Thread(target=run, daemon=True, name="fidus-preview").start()

    def _record_sample(self, seconds: int) -> None:
        """Grava a voz da pessoa pelo microfone que o Fidus já usa (sem abrir outro fluxo). Só fica na memória."""
        import threading
        import time

        import numpy as np

        manager = getattr(self.loop, "manager", None)
        if manager is None:
            raise ValueError("A gravação só funciona com o núcleo real e o microfone ligado.")
        if manager.muted:
            raise ValueError("O microfone está silenciado. Reative para gravar.")
        if self._recording:
            raise ValueError("Já estou gravando.")
        self._recording, self._sample = True, None

        def run() -> None:
            from ..voice.audio_manager import SAMPLE_RATE
            from ..voice.elevenlabs import pcm_to_wav

            cap = manager.open_capture()
            blocks: list = []
            try:
                end = time.monotonic() + seconds
                while (left := end - time.monotonic()) > 0:
                    time.sleep(0.2)
                    blocks.append(cap.drain())
                    self.emit("voice_record", state="recording", elapsed=round(seconds - left, 1), total=seconds)
                blocks.append(cap.drain())
            finally:
                cap.close()
                self._recording = False
            audio = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.int16)
            self._sample = pcm_to_wav(audio.astype(np.int16).tobytes(), SAMPLE_RATE)
            self.emit("voice_record", state="done", elapsed=seconds, total=seconds)

        threading.Thread(target=run, daemon=True, name="fidus-record-sample").start()

    def local_models(self, op: str = "list", model: str = "") -> dict:
        """Modelos já baixados no Ollama (para a tela) e download de modelos novos, com progresso pelo evento `model_pull`."""
        from ..config import DEFAULT_LOCAL_MODEL
        from ..providers.ollama import MODEL_NAME, OllamaError, list_models, pull_model

        if op == "pull":
            model = model.strip()
            if not MODEL_NAME.fullmatch(model):
                raise ValueError("Nome de modelo inválido. Use algo como llama3.2:3b.")
            self._job(model, lambda progress: pull_model(self.config.local_url, model, progress), event="model_pull")
            return {"started": True}
        if op != "list":
            raise ValueError(f"Operação desconhecida: {op}")
        base = {"url": self.config.local_url, "suggested": DEFAULT_LOCAL_MODEL, "busy": bool(self._jobs)}
        try:
            return {**base, "running": True, "models": list_models(self.config.local_url)}
        except OllamaError as e:
            return {**base, "running": False, "models": [], "error": str(e)}

    def _refresh_provider_key(self) -> None:
        orch = getattr(getattr(self.loop, "handler", None), "orchestrator", None)
        prov = getattr(orch, "provider", None)
        if prov is not None and hasattr(prov, "_client"):
            prov._api_key, prov._client = None, None  # a próxima chamada usa a chave nova
