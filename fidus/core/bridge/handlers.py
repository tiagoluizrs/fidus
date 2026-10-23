"""Operações que as telas de Configurações pedem ao núcleo: personagens, memória, contas, privacidade e "sobre".

Cada comando do protocolo recebe `{op: "...", ...}`. Tudo é validado aqui; a interface nunca grava direto em disco.
"""

from __future__ import annotations

import json
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


class Handlers:
    def __init__(self, config, state, persona, loop=None, save_settings: Callable[[dict], None] | None = None):
        self.config, self.state, self.persona, self.loop = config, state, persona, loop
        self.store: CharacterStore = persona.store
        self.save_settings = save_settings or (lambda patch: None)

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
            "voice": {"engine": pr.voice.engine, "voice": pr.voice.voice, "pitch": pr.voice.pitch, "rate": pr.voice.rate,
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
            fields = {k: a[k] for k in ("engine", "voice", "pitch", "rate") if k in a}
            if "engine" in fields and fields["engine"] not in ("sapi", "piper", "descricao"):
                raise ValueError("Motor de voz inválido.")
            if "voice" in fields:
                fields["voice"] = str(fields["voice"])[:300]
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
            self._connect_google(service, write)
            return {"started": True, "message": "Autorize no navegador que vai abrir."}
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

        def work() -> None:
            try:
                google_auth.connect(self.config, svc, write)
                self.save_settings({("contas.google.agenda_escrita" if service == "agenda" else "contas.google.gmail_rascunhos"): write})
                self.emit("accounts", service=service, status="connected", message="")
            except Exception as e:  # falta o credentials.json, o usuário fechou o navegador, etc.
                self.emit("accounts", service=service, status="error", message=str(e))

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

    def api_key(self, op: str = "status", value: str = "") -> dict:
        """Chave da Anthropic. Nunca volta para a tela: só `stored` (guardada ou não) e de onde vem."""
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

    def _refresh_provider_key(self) -> None:
        orch = getattr(getattr(self.loop, "handler", None), "orchestrator", None)
        prov = getattr(orch, "provider", None)
        if prov is not None and hasattr(prov, "_client"):
            prov._api_key, prov._client = None, None  # a próxima chamada usa a chave nova
