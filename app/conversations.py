"""Historial persistente de conversaciones (SQLite local)."""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import config_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, conv_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id, id);
"""


@dataclass
class Conversation:
    id: str
    title: str
    created: float
    updated: float


class ConversationStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (config_dir() / "conversations.db")
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def create(self, title: str = "Conversación nueva") -> Conversation:
        cid, now = uuid.uuid4().hex, time.time()
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO conversations VALUES(?,?,?,?)", (cid, title, now, now))
        return Conversation(cid, title, now, now)

    def list(self) -> list[Conversation]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT id,title,created,updated FROM conversations ORDER BY updated DESC").fetchall()
        return [Conversation(*r) for r in rows]

    def rename(self, cid: str, title: str) -> None:
        title = " ".join(title.split())[:80] or "Conversación"
        with self._lock, self._conn() as c:
            c.execute("UPDATE conversations SET title=? WHERE id=?", (title, cid))

    def delete(self, cid: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM conversations WHERE id=?", (cid,))

    def delete_all(self) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM conversations")

    def add_message(self, cid: str, role: str, content: str) -> None:
        now = time.time()
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO messages(conv_id,role,content,ts) VALUES(?,?,?,?)", (cid, role, content, now))
            c.execute("UPDATE conversations SET updated=? WHERE id=?", (now, cid))

    def delete_last_message(self, cid: str, role: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM messages WHERE id=(SELECT MAX(id) FROM messages WHERE conv_id=? AND role=?)", (cid, role))

    def messages(self, cid: str) -> list[dict]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT role,content FROM messages WHERE conv_id=? ORDER BY id", (cid,)).fetchall()
        return [{"role": r, "content": t} for r, t in rows]


def auto_title(text: str) -> str:
    one = " ".join(text.split())
    return (one[:48] + "…") if len(one) > 48 else (one or "Conversación nueva")


def build_context(system: str, history: list[dict], max_chars: int = 24000) -> tuple[list[dict], bool]:
    """Mensajes para el modelo: sistema + el tramo más reciente que cabe en ``max_chars``.

    No se envía nunca el historial de otras conversaciones. Devuelve (mensajes, recortado).
    """
    kept: list[dict] = []
    total = 0
    for msg in reversed(history):
        size = len(msg["content"])
        if kept and total + size > max_chars:
            break
        kept.append(msg)
        total += size
    kept.reverse()
    trimmed = len(kept) < len(history)
    return [{"role": "system", "content": system}] + kept, trimmed
