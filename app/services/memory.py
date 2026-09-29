from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class MemoryItem:
    id: int
    content: str
    created_at: str


class MemoryStore:
    """Small persistent memory store backed by SQLite."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def add(self, content: str) -> MemoryItem:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory cannot be empty.")

        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO memories (content, created_at) VALUES (?, ?)",
                (clean_content, created_at),
            )
            memory_id = int(cursor.lastrowid)
        return MemoryItem(memory_id, clean_content, created_at)

    def list(self, limit: int = 20) -> list[MemoryItem]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, content, created_at FROM memories ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [MemoryItem(int(r["id"]), r["content"], r["created_at"]) for r in rows]

    def delete(self, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cursor.rowcount > 0
