"""Long-term agent memory in SQLite, mirroring the Supabase conversation tables."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "agent_memory.sqlite3"

SCHEMA = """
create table if not exists conversations (
  id text primary key,
  user_id text not null,
  title text not null,
  created_at text not null
);
create table if not exists messages (
  id text primary key,
  conversation_id text not null references conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at text not null
);
create table if not exists gap_analyses (
  id text primary key,
  user_id text not null,
  conversation_id text,
  goal text not null,
  result_json text not null,
  created_at text not null
);
create table if not exists ranker_feedback (
  user_id text not null,
  goal text not null,
  candidate_id text not null,
  features_json text not null,
  relevance integer not null check (relevance between 0 and 3),
  created_at text not null,
  primary key (user_id, goal, candidate_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AgentMemory:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def start_conversation(self, user_id: str, title: str = "Wardrobe gaps") -> str:
        conversation_id = str(uuid.uuid4())
        with self.connection:
            self.connection.execute(
                "insert into conversations values (?, ?, ?, ?)",
                (conversation_id, user_id, title, _now()),
            )
        return conversation_id

    def owns_conversation(self, conversation_id: str, user_id: str) -> bool:
        return self.connection.execute(
            "select 1 from conversations where id = ? and user_id = ?", (conversation_id, user_id)
        ).fetchone() is not None

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        with self.connection:
            self.connection.execute(
                "insert into messages values (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), conversation_id, role, content, _now()),
            )

    def save_gap_analysis(
        self, user_id: str, conversation_id: str | None, goal: str, result: dict[str, Any]
    ) -> None:
        with self.connection:
            self.connection.execute(
                "insert into gap_analyses values (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, conversation_id, goal, json.dumps(result), _now()),
            )

    def set_feedback(
        self, user_id: str, goal: str, candidate_id: str, features: dict[str, float], relevance: int
    ) -> None:
        """Latest label per user, goal and candidate wins."""
        with self.connection:
            self.connection.execute(
                "insert or replace into ranker_feedback values (?, ?, ?, ?, ?, ?)",
                (user_id, goal, candidate_id, json.dumps(features), relevance, _now()),
            )

    def delete_feedback(self, user_id: str, goal: str, candidate_id: str) -> None:
        with self.connection:
            self.connection.execute(
                "delete from ranker_feedback where user_id = ? and goal = ? and candidate_id = ?",
                (user_id, goal, candidate_id),
            )

    def list_feedback(self, user_id: str | None = None) -> list[dict[str, Any]]:
        query = "select * from ranker_feedback" + (" where user_id = ?" if user_id else "")
        rows = self.connection.execute(query, (user_id,) if user_id else ()).fetchall()
        return [
            {
                "user_id": row["user_id"],
                "goal": row["goal"],
                "candidate_id": row["candidate_id"],
                "features": json.loads(row["features_json"]),
                "relevance": row["relevance"],
            }
            for row in rows
        ]

    def past_gap_analyses(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "select goal, result_json, created_at from gap_analyses "
            "where user_id = ? order by created_at desc limit ?",
            (user_id, limit),
        ).fetchall()
        return [
            {
                "goal": row["goal"],
                "created_at": row["created_at"],
                "top_gaps": [gap["name"] for gap in json.loads(row["result_json"])["ranked_gaps"][:3]],
            }
            for row in rows
        ]
