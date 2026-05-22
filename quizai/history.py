"""Persistent Q&A history backed by SQLite.

Thread-safe through a per-call connection pattern (each call opens its own
connection — SQLite handles concurrent access within the same process fine
for our low write volume).
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from quizai.logger import get_logger

log = get_logger(__name__)

DB_PATH = Path.home() / ".quizai" / "history.db"

# A single Lock serialises writes. Reads are concurrent.
_write_lock = threading.Lock()


@dataclass
class HistoryEntry:
    id: int
    timestamp: str  # ISO 8601 UTC
    source: str  # "screen", "manual"
    question: str
    answer: str
    explanation: str
    model: str


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                model TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_ts ON history(timestamp DESC)")
        conn.commit()


def add_entry(
    *,
    source: str,
    question: str,
    answer: str,
    explanation: str,
    model: str,
) -> HistoryEntry:
    """Insert a Q&A row and return the stored entry."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _write_lock, _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO history (timestamp, source, question, answer, explanation, model)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts, source, question, answer, explanation, model),
        )
        conn.commit()
        new_id = cur.lastrowid or 0
    return HistoryEntry(
        id=new_id,
        timestamp=ts,
        source=source,
        question=question,
        answer=answer,
        explanation=explanation,
        model=model,
    )


def list_entries(limit: int = 200, search: str | None = None) -> list[HistoryEntry]:
    """Return entries newest-first, optionally filtered by substring."""
    sql = "SELECT * FROM history"
    params: tuple = ()
    if search:
        sql += " WHERE question LIKE ? OR answer LIKE ?"
        like = f"%{search}%"
        params = (like, like)
    sql += " ORDER BY id DESC LIMIT ?"
    params = (*params, limit)
    try:
        with _connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist yet — caller forgot init_db(). Recover silently.
        init_db()
        with _connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    return [_row_to_entry(r) for r in rows]


def get_entry(entry_id: int) -> HistoryEntry | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(row) if row else None


def delete_entry(entry_id: int) -> None:
    with _write_lock, _connect() as conn:
        conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))
        conn.commit()


def clear_all() -> None:
    with _write_lock, _connect() as conn:
        conn.execute("DELETE FROM history")
        conn.commit()


def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        id=row["id"],
        timestamp=row["timestamp"],
        source=row["source"],
        question=row["question"],
        answer=row["answer"],
        explanation=row["explanation"],
        model=row["model"],
    )
