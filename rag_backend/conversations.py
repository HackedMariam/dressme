"""Small SQLite conversation store for the stylist chat.

Keeps the API stateless across workers while still giving each conversation a
persistent history. Swap for Postgres/Redis if you need multi-host scale.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from config import get_settings


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConversationStore:
    def __init__(self, path: Path | None = None):
        self.path = path or get_settings().conversations_db
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists conversations (
                    id text primary key,
                    created_at text not null,
                    updated_at text not null
                );

                create table if not exists messages (
                    id integer primary key autoincrement,
                    conversation_id text not null
                        references conversations(id) on delete cascade,
                    role text not null check (role in ('user', 'assistant')),
                    content text not null,
                    sources text,
                    citations text,
                    rewritten_query text,
                    created_at text not null
                );

                create index if not exists messages_conversation_idx
                    on messages(conversation_id, id);
                """
            )

    def create(self) -> str:
        conversation_id = str(uuid.uuid4())
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "insert into conversations (id, created_at, updated_at) "
                "values (?, ?, ?)",
                (conversation_id, timestamp, timestamp),
            )
        return conversation_id

    def exists(self, conversation_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "select 1 from conversations where id = ?",
                (conversation_id,),
            ).fetchone()
        return row is not None

    def get_or_create(self, conversation_id: str | None) -> str:
        if conversation_id and self.exists(conversation_id):
            return conversation_id
        return self.create()

    def append(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        sources: list[dict] | None = None,
        citations: list[dict] | None = None,
        rewritten_query: str | None = None,
    ) -> None:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "insert or ignore into conversations "
                "(id, created_at, updated_at) values (?, ?, ?)",
                (conversation_id, timestamp, timestamp),
            )
            connection.execute(
                "insert into messages "
                "(conversation_id, role, content, sources, citations, "
                "rewritten_query, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    role,
                    content,
                    json.dumps(sources or [], ensure_ascii=False),
                    json.dumps(citations or [], ensure_ascii=False),
                    rewritten_query,
                    timestamp,
                ),
            )
            connection.execute(
                "update conversations set updated_at = ? where id = ?",
                (timestamp, conversation_id),
            )

    def messages(
        self, conversation_id: str, limit: int = 100
    ) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "select role, content, sources, citations, "
                "rewritten_query, created_at from messages "
                "where conversation_id = ? order by id limit ?",
                (conversation_id, limit),
            ).fetchall()

        return [
            {
                "role": row["role"],
                "content": row["content"],
                "sources": json.loads(row["sources"] or "[]"),
                "citations": json.loads(row["citations"] or "[]"),
                "rewritten_query": row["rewritten_query"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def history(self, conversation_id: str, limit: int = 8) -> list[dict]:
        messages = self.messages(conversation_id, limit=limit)
        return [
            {"role": item["role"], "content": item["content"]}
            for item in messages
        ]

    def delete(self, conversation_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "delete from conversations where id = ?",
                (conversation_id,),
            )
        return cursor.rowcount > 0
