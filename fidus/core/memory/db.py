"""SQLite do Fidus: histórico da conversa e resumos periódicos.

Com `sqlcipher3` instalado e uma chave no Gerenciador de Credenciais, o arquivo é criptografado (SQLCipher).
Sem isso, cai no SQLite comum e avisa no log. A chave nunca fica em arquivo.
"""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

DB_KEY_NAME = "DB_KEY"

SCHEMA = """
CREATE TABLE IF NOT EXISTS mensagens (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sessao TEXT NOT NULL, personagem TEXT NOT NULL,
  papel TEXT NOT NULL, texto TEXT NOT NULL, ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resumos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sessao TEXT NOT NULL, ate_mensagem INTEGER NOT NULL,
  texto TEXT NOT NULL, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_msg_sessao ON mensagens(sessao, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path, key: str | None = None, driver=None):
        self.path, self.encrypted = Path(path), False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._con = self._open(key, driver)
        self._con.executescript(SCHEMA)
        self._con.commit()

    def _open(self, key, driver):
        if key:
            if driver is None:
                import sqlcipher3 as driver  # type: ignore[no-redef]
            con = driver.connect(str(self.path), check_same_thread=False)
            con.execute(f"PRAGMA key = \"x'{key}'\"")  # chave bruta em hexadecimal
            con.execute("SELECT count(*) FROM sqlite_master")  # falha aqui se a chave estiver errada
            self.encrypted = True
            return con
        return sqlite3.connect(str(self.path), check_same_thread=False)

    def close(self) -> None:
        self._con.close()

    # ---- histórico ----

    def add_message(self, sessao: str, personagem: str, papel: str, texto: str) -> int:
        cur = self._con.execute(
            "INSERT INTO mensagens(sessao, personagem, papel, texto, ts) VALUES (?,?,?,?,?)",
            (sessao, personagem, papel, texto, _now()),
        )
        self._con.commit()
        return cur.lastrowid

    def messages(self, sessao: str | None = None, limit: int = 100) -> list[dict]:
        q, args = "SELECT id, sessao, personagem, papel, texto, ts FROM mensagens", []
        if sessao:
            q, args = q + " WHERE sessao = ?", [sessao]
        rows = self._con.execute(q + " ORDER BY id DESC LIMIT ?", [*args, limit]).fetchall()
        return [dict(zip(("id", "sessao", "personagem", "papel", "texto", "ts"), r)) for r in reversed(rows)]

    def count_messages(self, sessao: str) -> int:
        return self._con.execute("SELECT count(*) FROM mensagens WHERE sessao = ?", (sessao,)).fetchone()[0]

    # ---- resumos ----

    def add_summary(self, sessao: str, ate_mensagem: int, texto: str) -> None:
        self._con.execute(
            "INSERT INTO resumos(sessao, ate_mensagem, texto, ts) VALUES (?,?,?,?)", (sessao, ate_mensagem, texto, _now())
        )
        self._con.commit()

    def latest_summary(self, sessao: str) -> tuple[int, str] | None:
        row = self._con.execute(
            "SELECT ate_mensagem, texto FROM resumos WHERE sessao = ? ORDER BY id DESC LIMIT 1", (sessao,)
        ).fetchone()
        return (row[0], row[1]) if row else None

    def clear_history(self) -> int:
        n = self._con.execute("SELECT count(*) FROM mensagens").fetchone()[0]
        self._con.executescript("DELETE FROM mensagens; DELETE FROM resumos;")
        self._con.commit()
        return n


def open_database(
    path: Path,
    mode: str = "auto",
    get_secret: Callable[[str], str | None] | None = None,
    set_secret: Callable[[str, str], None] | None = None,
    log=None,
    driver=None,
) -> Database:
    """`mode`: 'auto' (criptografa se der), 'sim' (exige criptografia) ou 'nao'."""
    if get_secret is None or set_secret is None:
        from ..secrets import get_secret, set_secret

    def warn(reason: str) -> None:
        if log:
            log.event("memoria_sem_criptografia", motivo=reason)

    if mode == "nao":
        return Database(path)
    try:
        if driver is None:
            import sqlcipher3  # noqa: F401
            driver = sqlcipher3
        key = get_secret(DB_KEY_NAME)
        if not key:
            key = secrets.token_hex(32)
            set_secret(DB_KEY_NAME, key)
            if get_secret(DB_KEY_NAME) != key:
                raise RuntimeError("não consegui guardar a chave no cofre do sistema")
        if Path(path).exists() and _is_plain(path):
            _migrate_plain(path, key, driver)
        return Database(path, key, driver)
    except Exception as e:
        if mode == "sim":
            raise RuntimeError(f"Criptografia da memória exigida, mas indisponível: {e}") from e
        warn(f"{type(e).__name__}: {e}")
        return Database(path)


def _is_plain(path: Path) -> bool:
    return Path(path).read_bytes()[:16] == b"SQLite format 3\x00"


def _migrate_plain(path: Path, key: str, driver) -> None:
    """Converte um banco comum já existente em um banco criptografado (mesmo arquivo)."""
    path = Path(path)
    tmp = path.with_suffix(".enc")
    tmp.unlink(missing_ok=True)
    con = driver.connect(str(path))
    try:
        con.execute(f"ATTACH DATABASE '{tmp}' AS enc KEY \"x'{key}'\"")
        con.execute("SELECT sqlcipher_export('enc')")
        con.execute("DETACH DATABASE enc")
    finally:
        con.close()
    tmp.replace(path)
