"""Persistent memory backed by SQLite.

Stores: key/value facts (survive across sessions), and a rolling conversation
log. This is the agent's long-term memory — no session restrictions, it all
persists on disk under the base directory.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Memory:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # The web UI serializes access with a lock but serves requests on worker
        # threads, so the connection must be transferable between those threads.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                role TEXT,
                content TEXT
            )"""
        )
        self._conn.commit()

    # ---- key/value memory ----
    def set(self, key: str, value: Any) -> None:
        value = json.dumps(value, default=str)
        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO kv(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, ts),
        )
        self._conn.commit()

    def get(self, key: str, default=None):
        row = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def all_kv(self) -> dict:
        return {
            r["key"]: (lambda v: (json.loads(v) if v.startswith(("{", "[")) else v))(r["value"])
            for r in self._conn.execute("SELECT key, value FROM kv")
        }

    # ---- conversation history ----
    def log(self, role: str, content: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute("INSERT INTO history(ts, role, content) VALUES(?,?,?)", (ts, role, content))
        self._conn.commit()

    def recent(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT role, content FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_history(self) -> None:
        self._conn.execute("DELETE FROM history")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
