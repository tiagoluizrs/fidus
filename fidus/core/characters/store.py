"""Perfis de personagem em arquivos.

- Padrões: `fidus/defaults/characters/<id>.json`. Nunca são sobrescritos.
- Edições do usuário: `<pasta de dados>/characters/<id>.json`, só com o que mudou. Valem sobre o padrão.
- Restaurar = apagar a edição correspondente; o padrão continua intacto.
"""

from __future__ import annotations

import copy
import json
import re
import secrets
from pathlib import Path

from .models import ADDRESS_MODES, CONTROLS, MOMENTS, STYLES, Item, Personality, Profile, Voice

DEFAULTS_DIR = Path(__file__).resolve().parents[2] / "defaults" / "characters"
ADDRESS = "tratamentos"  # nome da "lista" dos tratamentos, ao lado das falas por momento


class CharacterStore:
    def __init__(self, user_dir: Path, defaults_dir: Path = DEFAULTS_DIR):
        self.user_dir, self.defaults_dir = Path(user_dir), Path(defaults_dir)

    # ---------- leitura ----------

    def ids(self) -> list[str]:
        ids = sorted(p.stem for p in self.defaults_dir.glob("*.json"))
        return sorted(ids, key=lambda i: (not self._default(i)["default"], bool(self._default(i).get("custom")), i))  # o padrão primeiro, o personalizado por último

    def _default(self, cid: str) -> dict:
        path = self.defaults_dir / f"{cid}.json"
        if not path.is_file():
            raise KeyError(f"Personagem '{cid}' não existe.")
        return json.loads(path.read_text(encoding="utf-8"))

    def _user(self, cid: str) -> dict:
        path = self.user_dir / f"{cid}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def _save_user(self, cid: str, data: dict) -> None:
        self.user_dir.mkdir(parents=True, exist_ok=True)
        path = self.user_dir / f"{cid}.json"
        data = _prune(data)
        if not data:
            path.unlink(missing_ok=True)
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def load(self, cid: str) -> Profile:
        d, u = self._default(cid), self._user(cid)
        pers_d, pers_u = d["personality"], u.get("personality", {})
        controls = {**pers_d["controls"], **{k: v for k, v in pers_u.get("controls", {}).items() if k in CONTROLS}}
        personality = Personality(
            base_style=pers_u.get("base_style", pers_d["base_style"]),
            controls={k: int(controls[k]) for k in CONTROLS if k in controls},
            persona=pers_d["persona"],
            extra=pers_u.get("extra", pers_d.get("extra", "")),
        )
        addr_d, addr_u = d["address"], u.get("address", {})
        voice = {**d["voice"], **u.get("voice", {})}
        custom = bool(d.get("custom"))
        name = str(u.get("name") or d["name"]) if custom else d["name"]
        return Profile(
            id=d["id"], name=name, call=f"ei {name}" if custom else d["call"], summary=d["summary"], default=d["default"], ring=d["ring"],
            customizable=custom,
            personality=personality,
            address_mode=addr_u.get("mode", addr_d["mode"]),
            address_fixed=addr_u.get("fixed", addr_d["fixed"]),
            address=_merge(addr_d["items"], addr_u.get("items", {})),
            phrases={m: _merge(d["phrases"].get(m, []), u.get("phrases", {}).get(m, {})) for m in MOMENTS},
            voice=Voice(**{k: voice[k] for k in ("engine", "voice", "pitch", "rate")}, description=str(voice.get("description", "")), effect=str(voice.get("effect", "")),
                         timbre=int(voice.get("timbre", 0)), edge=int(voice.get("edge", 0)),
                         pronunciations=str(voice.get("pronunciations", ""))),
        )

    def load_all(self) -> dict[str, Profile]:
        return {i: self.load(i) for i in self.ids()}

    def set_name(self, cid: str, name: str) -> None:
        """Nome do personagem personalizado (é com ele que se chama: “ei <nome>”). Os três padrões não mudam de nome."""
        if not self._default(cid).get("custom"):
            raise ValueError("Só o personagem personalizado pode mudar de nome.")
        name = " ".join(name.split())
        if not (1 <= len(name) <= 24) or not re.fullmatch(r"[\wÀ-ÿ' -]+", name):
            raise ValueError("Use de 1 a 24 letras, números ou espaços no nome.")
        self._mutate(cid, lambda u: u.__setitem__("name", name))

    def default_id(self) -> str:
        return next(i for i in self.ids() if self._default(i)["default"])

    # ---------- personalidade ----------

    def set_control(self, cid: str, control: str, value: int) -> None:
        if control not in CONTROLS:
            raise ValueError(f"Controle inválido: {control}. Use: {', '.join(CONTROLS)}")
        self._mutate(cid, lambda u: u.setdefault("personality", {}).setdefault("controls", {}).__setitem__(control, max(0, min(100, int(value)))))

    def reset_control(self, cid: str, control: str) -> None:
        self._mutate(cid, lambda u: u.get("personality", {}).get("controls", {}).pop(control, None))

    def set_style(self, cid: str, style: str) -> None:
        if style not in STYLES:
            raise ValueError(f"Estilo inválido: {style}. Use: {', '.join(STYLES)}")
        self._mutate(cid, lambda u: u.setdefault("personality", {}).__setitem__("base_style", style))

    def set_extra(self, cid: str, text: str) -> None:
        self._mutate(cid, lambda u: u.setdefault("personality", {}).__setitem__("extra", text.strip()[:2000]))

    def reset_personality(self, cid: str) -> None:
        self._mutate(cid, lambda u: u.pop("personality", None))

    # ---------- listas (falas por momento e tratamentos) ----------

    def _list_override(self, u: dict, name: str) -> dict:
        if name == ADDRESS:
            return u.setdefault("address", {}).setdefault("items", {})
        if name not in MOMENTS:
            raise ValueError(f"Momento inválido: {name}. Use: {', '.join(MOMENTS)}")
        return u.setdefault("phrases", {}).setdefault(name, {})

    def _default_ids(self, cid: str, name: str) -> set[str]:
        d = self._default(cid)
        src = d["address"]["items"] if name == ADDRESS else d["phrases"].get(name, [])
        return {i["id"] for i in src}

    def edit_item(self, cid: str, name: str, item_id: str, text: str) -> None:
        text = text.strip()
        if not text:
            raise ValueError("O texto não pode ser vazio.")

        def fn(u):
            ov = self._list_override(u, name)
            if item_id in self._default_ids(cid, name):
                ov.setdefault("edited", {})[item_id] = text
            else:
                for a in ov.get("added", []):
                    if a["id"] == item_id:
                        a["text"] = text
                        return
                raise KeyError(f"Item '{item_id}' não existe.")

        self._mutate(cid, fn)

    def set_enabled(self, cid: str, name: str, item_id: str, enabled: bool) -> None:
        def fn(u):
            ov = self._list_override(u, name)
            for a in ov.get("added", []):
                if a["id"] == item_id:
                    a["enabled"] = enabled
                    return
            off = [i for i in ov.get("disabled", []) if i != item_id]
            ov["disabled"] = off if enabled else off + [item_id]

        self._mutate(cid, fn)

    def delete_item(self, cid: str, name: str, item_id: str) -> None:
        def fn(u):
            ov = self._list_override(u, name)
            if item_id in self._default_ids(cid, name):
                ov["deleted"] = sorted(set(ov.get("deleted", [])) | {item_id})  # o padrão fica no disco, só some da lista
            else:
                ov["added"] = [a for a in ov.get("added", []) if a["id"] != item_id]

        self._mutate(cid, fn)

    def add_item(self, cid: str, name: str, text: str, contexts: list[str] | None = None) -> str:
        text = text.strip()
        if not text:
            raise ValueError("O texto não pode ser vazio.")
        new_id = f"u_{secrets.token_hex(4)}"

        def fn(u):
            entry = {"id": new_id, "text": text, "enabled": True}
            if name == ADDRESS:
                entry["contexts"] = list(contexts or [])
            self._list_override(u, name).setdefault("added", []).append(entry)

        self._mutate(cid, fn)
        return new_id

    def deleted_items(self, cid: str, name: str) -> list[Item]:
        """Padrões que o usuário apagou (para o 'Restaurar apagadas')."""
        d = self._default(cid)
        src = d["address"]["items"] if name == ADDRESS else d["phrases"].get(name, [])
        ov = self._list_override({"address": self._user(cid).get("address", {}), "phrases": self._user(cid).get("phrases", {})}, name)
        gone = set(ov.get("deleted", []))
        return [Item(i["id"], i["text"], True, "padrao", i.get("contexts", [])) for i in src if i["id"] in gone]

    def restore_deleted(self, cid: str, name: str) -> None:
        self._mutate(cid, lambda u: self._list_override(u, name).pop("deleted", None))

    def reset_list(self, cid: str, name: str) -> None:
        """'Restaurar frases padrão': volta a lista inteira ao padrão (edições, apagadas, desativadas e adicionadas)."""

        def fn(u):
            if name == ADDRESS:
                u.get("address", {}).pop("items", None)
            else:
                u.get("phrases", {}).pop(name, None)

        self._mutate(cid, fn)

    # ---------- tratamento e voz ----------

    def set_address_mode(self, cid: str, mode: str, fixed: str | None = None) -> None:
        if mode not in ADDRESS_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use: {', '.join(ADDRESS_MODES)}")

        def fn(u):
            a = u.setdefault("address", {})
            a["mode"] = mode
            if fixed is not None:
                a["fixed"] = fixed.strip()

        self._mutate(cid, fn)

    def set_voice(self, cid: str, **fields) -> None:
        allowed = {"engine", "voice", "pitch", "rate", "description", "effect", "timbre", "edge", "pronunciations"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Campos de voz inválidos: {', '.join(sorted(bad))}")
        if "pitch" in fields:
            fields["pitch"] = max(-10, min(10, int(fields["pitch"])))
        if "rate" in fields:
            fields["rate"] = max(-10, min(10, int(fields["rate"])))
        for k in ("timbre", "edge"):
            if k in fields:
                fields[k] = max(-10, min(10, int(fields[k])))
        self._mutate(cid, lambda u: u.setdefault("voice", {}).update(fields))

    def reset_voice(self, cid: str) -> None:
        self._mutate(cid, lambda u: u.pop("voice", None))

    # ---------- personagem inteiro ----------

    def reset_character(self, cid: str) -> None:
        self._default(cid)  # valida que existe
        (self.user_dir / f"{cid}.json").unlink(missing_ok=True)

    def has_user_edits(self, cid: str) -> bool:
        return (self.user_dir / f"{cid}.json").is_file()

    def _mutate(self, cid: str, fn) -> None:
        self._default(cid)
        u = copy.deepcopy(self._user(cid))
        fn(u)
        self._save_user(cid, u)


def _merge(default_items: list[dict], ov: dict) -> list[Item]:
    deleted, disabled, edited = set(ov.get("deleted", [])), set(ov.get("disabled", [])), ov.get("edited", {})
    out: list[Item] = []
    for i in default_items:
        if i["id"] in deleted:
            continue
        text = edited.get(i["id"], i["text"])
        out.append(Item(i["id"], text, i["id"] not in disabled and i.get("enabled", True),
                        "editada" if text != i["text"] else "padrao", list(i.get("contexts", []))))
    for a in ov.get("added", []):
        out.append(Item(a["id"], a["text"], a.get("enabled", True), "usuario", list(a.get("contexts", []))))
    return out


def _prune(d):
    """Remove chaves vazias para o arquivo do usuário conter só o que realmente difere do padrão."""
    if isinstance(d, dict):
        cleaned = {k: _prune(v) for k, v in d.items()}
        return {k: v for k, v in cleaned.items() if v not in ({}, [], None)}
    return d
