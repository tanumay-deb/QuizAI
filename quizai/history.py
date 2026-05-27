"""Persistent Q&A history backed by SQLite.

Thread-safe through a per-call connection pattern (each call opens its own
connection — SQLite handles concurrent access within the same process fine
for our low write volume).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


def list_entries(
    limit: int = 200,
    search: str | None = None,
    source: str | None = None,
) -> list[HistoryEntry]:
    """Return entries newest-first, optionally filtered by substring and/or source."""
    where: list[str] = []
    params: list = []
    if search:
        where.append("(question LIKE ? OR answer LIKE ? OR explanation LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if source:
        where.append("source = ?")
        params.append(source)
    sql = "SELECT * FROM history"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    try:
        with _connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist yet — caller forgot init_db(). Recover silently.
        init_db()
        with _connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
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


# ============================================================ question cache
_NORMALIZE_RE = re.compile(r"\s+")


def _normalize_question(question: str) -> str:
    """Lowercase + collapse whitespace so trivially-different wordings collide."""
    return _NORMALIZE_RE.sub(" ", (question or "").strip().lower())


def question_hash(question: str) -> str:
    """Stable hash of the normalised question text."""
    return hashlib.sha256(_normalize_question(question).encode("utf-8")).hexdigest()


def find_cached_answer(question: str, max_age_days: int = 7) -> HistoryEntry | None:
    """Return a previous entry with the same normalised question, if recent.

    Looks at every entry within `max_age_days` and compares its hashed question
    to the new one. Hashing rather than `WHERE question = ?` so trivial
    whitespace / case differences still hit the cache.
    """
    if max_age_days <= 0:
        return None
    target = question_hash(question)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat(
        timespec="seconds"
    )
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM history WHERE timestamp >= ? ORDER BY id DESC LIMIT 500",
                (cutoff,),
            ).fetchall()
    except sqlite3.OperationalError:
        init_db()
        return None
    for row in rows:
        if question_hash(row["question"]) == target:
            return _row_to_entry(row)
    return None


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
