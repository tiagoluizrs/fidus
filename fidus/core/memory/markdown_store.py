"""Memória em arquivos Markdown que o usuário pode abrir e editar: perfil.md, rotinas.md, contatos.md, projetos/.

Cada lembrança é um item de lista com um comentário HTML de metadados no fim:
    - Gosta de café sem açúcar. <!-- id=a1b2c3d4 tag=pessoal ts=2026-10-23 -->
Linhas editadas à mão, sem o comentário, continuam valendo (ganham um id estável derivado do texto).
Qualquer outra linha do arquivo (títulos, notas) é preservada ao reescrever.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SECTIONS = ("perfil", "rotinas", "contatos")
SOURCES = ("usuario", "aprendida")
TAGS = ("geral", "pessoal", "trabalho")
MAX_TEXT = 500
_ITEM = re.compile(r"^(?P<indent>\s*)[-*]\s+(?P<text>.*?)(?:\s*<!--\s*(?P<meta>.*?)\s*-->)?\s*$")
_META = re.compile(r"(\w+)=(\S+)")
_SLUG = re.compile(r"[^a-z0-9_-]+")


@dataclass
class Entry:
    id: str
    section: str
    text: str
    tag: str | None = None
    ts: str = ""
    src: str = "usuario"  # usuario (você disse) | aprendida (o Fidus guardou sozinho)


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in plain if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", normalize(text)) if len(t) > 1]


def clean_section(section: str) -> str:
    section = section.strip().lower().replace("\\", "/")
    if section in SECTIONS:
        return section
    if section.startswith("projetos/"):
        name = section.split("/", 1)[1]
        if ".." in name or "/" in name:  # sem subpastas nem tentativa de sair da pasta de memória
            raise ValueError(f"Seção inválida: '{section}'.")
        slug = _SLUG.sub("-", name).strip("-")
        if slug:
            return f"projetos/{slug}"
    raise ValueError(f"Seção inválida: '{section}'. Use perfil, rotinas, contatos ou projetos/<nome>.")


class MarkdownMemory:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, section: str) -> Path:
        path = (self.root / f"{clean_section(section)}.md").resolve()
        if self.root.resolve() not in path.parents:  # nunca sai da pasta de memória
            raise ValueError("Seção inválida.")
        return path

    def sections(self) -> list[str]:
        found = [s for s in SECTIONS if self._path(s).is_file()]
        pdir = self.root / "projetos"
        if pdir.is_dir():
            found += [f"projetos/{p.stem}" for p in sorted(pdir.glob("*.md"))]
        return found

    # ---------- leitura ----------

    def _parse(self, section: str) -> tuple[list[str], list[Entry | None]]:
        path = self._path(section)
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        entries: list[Entry | None] = []
        for line in lines:
            m = _ITEM.match(line)
            if not m or not m.group("text").strip():
                entries.append(None)
                continue
            meta = dict(_META.findall(m.group("meta") or ""))
            text = m.group("text").strip()
            eid = meta.get("id") or "x" + hashlib.sha1(text.encode()).hexdigest()[:7]
            entries.append(Entry(eid, section, text, meta.get("tag"), meta.get("ts", ""), meta.get("src", "usuario")))
        return lines, entries

    def list(self, section: str | None = None, tag: str | None = None) -> list[Entry]:
        out: list[Entry] = []
        for s in [section] if section else self.sections():
            out += [e for e in self._parse(s)[1] if e and (tag is None or e.tag == tag)]
        return out

    def get(self, entry_id: str) -> Entry | None:
        return next((e for e in self.list() if e.id == entry_id), None)

    def search(self, query: str, limit: int = 8, section: str | None = None) -> list[Entry]:
        """Pontua por palavras em comum (sem acento e sem diferenciar maiúsculas), palavras raras valem mais."""
        entries = self.list(section)
        q = set(tokens(query))
        if not q or not entries:
            return []
        docs = [set(tokens(e.text + " " + (e.tag or ""))) for e in entries]
        scored = []
        for e, d in zip(entries, docs):
            hits = q & d
            if hits:
                weight = sum(1 + 1 / (1 + sum(t in dd for dd in docs)) for t in hits)
                scored.append((weight, e))
        return [e for _, e in sorted(scored, key=lambda x: -x[0])[:limit]]

    # ---------- escrita ----------

    def _format(self, e: Entry) -> str:
        meta = f"id={e.id}" + (f" tag={e.tag}" if e.tag else "") + (f" ts={e.ts}" if e.ts else "") + (f" src={e.src}" if e.src != "usuario" else "")
        return f"- {e.text} <!-- {meta} -->"

    def _write(self, section: str, lines: list[str]) -> None:
        path = self._path(section)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(path)

    def add(self, section: str, text: str, tag: str | None = None, source: str = "usuario") -> Entry:
        section, text = clean_section(section), " ".join(text.split())[:MAX_TEXT]
        if not text:
            raise ValueError("O texto não pode ser vazio.")
        if tag and tag not in TAGS:
            raise ValueError(f"Etiqueta inválida: {tag}. Use: {', '.join(TAGS)}")
        lines, _ = self._parse(section)
        if not lines:
            lines = [f"# {section.split('/')[-1].capitalize()}", ""]
        entry = Entry(secrets.token_hex(4), section, text, tag, date.today().isoformat(), source if source in SOURCES else "usuario")
        self._write(section, lines + [self._format(entry)])
        return entry

    def edit(self, entry_id: str, text: str | None = None, tag: str | None = None, clear_tag: bool = False) -> Entry:
        for section in self.sections():
            lines, entries = self._parse(section)
            for i, e in enumerate(entries):
                if e and e.id == entry_id:
                    if text is not None:
                        e.text = " ".join(text.split())[:MAX_TEXT]
                        if not e.text:
                            raise ValueError("O texto não pode ser vazio.")
                    if tag is not None:
                        if tag not in TAGS:
                            raise ValueError(f"Etiqueta inválida: {tag}. Use: {', '.join(TAGS)}")
                        e.tag = tag
                    if clear_tag:
                        e.tag = None
                    if e.id.startswith("x"):  # lembrança escrita à mão ganha um id explícito ao ser editada
                        e.id = secrets.token_hex(4)
                    lines[i] = self._format(e)
                    self._write(section, lines)
                    return e
        raise KeyError(f"Lembrança '{entry_id}' não existe.")

    def delete(self, entry_id: str) -> Entry:
        for section in self.sections():
            lines, entries = self._parse(section)
            for i, e in enumerate(entries):
                if e and e.id == entry_id:
                    self._write(section, lines[:i] + lines[i + 1 :])
                    return e
        raise KeyError(f"Lembrança '{entry_id}' não existe.")

    def delete_all(self) -> int:
        n = len(self.list())
        for s in self.sections():
            self._path(s).unlink(missing_ok=True)
        return n

    def export_markdown(self) -> str:
        parts = ["# Memória do Fidus\n"]
        for s in self.sections():
            parts.append(f"\n## {s}\n")
            for e in self._parse(s)[1]:
                if e:
                    parts.append(f"- {e.text}" + (f" _(etiqueta: {e.tag})_" if e.tag else ""))
        return "\n".join(parts) + "\n"
