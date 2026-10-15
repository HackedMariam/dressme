"""Persistence: Supabase (Postgres + Storage) in production, local JSON fallback for dev.

Every read/write is scoped to a user id, so one user can never see or change
another user's wardrobe even though the backend uses the service_role key.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone

from . import config


def item_folder(user_id: str, item_id: str) -> str:
    return f"{user_id}/{item_id}"


class SupabaseStore:
    kind = "supabase"

    def __init__(self) -> None:
        from supabase import create_client

        self.db = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        self.bucket = config.SUPABASE_BUCKET

    def upload(self, path: str, data: bytes, content_type: str) -> str:
        self.db.storage.from_(self.bucket).upload(
            path, data, {"content-type": content_type, "upsert": "true"})
        return self.db.storage.from_(self.bucket).get_public_url(path).rstrip("?")

    def download(self, path: str) -> bytes:
        return self.db.storage.from_(self.bucket).download(path)

    def insert_item(self, row: dict) -> dict:
        return self.db.table("items").insert(row).execute().data[0]

    def list_items(self, user_id: str) -> list[dict]:
        return (self.db.table("items").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).execute().data)

    def get_item(self, user_id: str, item_id: str) -> dict | None:
        rows = (self.db.table("items").select("*").eq("id", item_id).eq("user_id", user_id)
                .limit(1).execute().data)
        return rows[0] if rows else None

    def update_item(self, user_id: str, item_id: str, patch: dict) -> dict:
        return (self.db.table("items").update(patch).eq("id", item_id).eq("user_id", user_id)
                .execute().data[0])

    def delete_item(self, user_id: str, item_id: str) -> None:
        self.db.table("items").delete().eq("id", item_id).eq("user_id", user_id).execute()
        folder = item_folder(user_id, item_id)
        try:
            self.db.storage.from_(self.bucket).remove([f"{folder}/original.jpg", f"{folder}/cutout.png"])
        except Exception:
            pass

    def insert_corrections(self, rows: list[dict]) -> None:
        if rows:
            self.db.table("corrections").insert(rows).execute()

    def list_corrections(self, user_id: str) -> list[dict]:
        rows = (self.db.table("corrections").select("item_id, field, items!inner(user_id)")
                .eq("items.user_id", user_id).execute().data)
        return [{"item_id": r["item_id"], "field": r["field"]} for r in rows]


class LocalStore:
    """Same interface, stores everything under backend/local_data (served at /files)."""
    kind = "local"

    def __init__(self) -> None:
        self.root = config.LOCAL_DATA_DIR
        (self.root / "files").mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "db.json"
        self._lock = threading.Lock()
        if not self.db_path.exists():
            self._save({"items": [], "corrections": []})

    def _load(self) -> dict:
        return json.loads(self.db_path.read_text(encoding="utf-8"))

    def _save(self, d: dict) -> None:
        tmp = self.db_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.db_path)  # atomic: a crash never leaves a half-written db

    def _file(self, path: str):
        f = (self.root / "files" / path).resolve()
        if not str(f).startswith(str((self.root / "files").resolve())):
            raise ValueError("invalid path")
        return f

    def upload(self, path: str, data: bytes, content_type: str) -> str:
        f = self._file(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        return f"{config.PUBLIC_API_URL}/files/{path}"

    def download(self, path: str) -> bytes:
        return self._file(path).read_bytes()

    def insert_item(self, row: dict) -> dict:
        with self._lock:
            d = self._load()
            row = {"id": row.get("id") or str(uuid.uuid4()),
                   "created_at": datetime.now(timezone.utc).isoformat(), **row}
            d["items"].insert(0, row)
            self._save(d)
            return row

    def list_items(self, user_id: str) -> list[dict]:
        return [i for i in self._load()["items"] if i.get("user_id") == user_id]

    def get_item(self, user_id: str, item_id: str) -> dict | None:
        return next((i for i in self.list_items(user_id) if i["id"] == item_id), None)

    def update_item(self, user_id: str, item_id: str, patch: dict) -> dict:
        with self._lock:
            d = self._load()
            for i in d["items"]:
                if i["id"] == item_id and i.get("user_id") == user_id:
                    i.update(patch)
                    self._save(d)
                    return i
            raise KeyError(item_id)

    def delete_item(self, user_id: str, item_id: str) -> None:
        with self._lock:
            d = self._load()
            d["items"] = [i for i in d["items"] if not (i["id"] == item_id and i.get("user_id") == user_id)]
            d["corrections"] = [c for c in d["corrections"] if c["item_id"] != item_id]
            self._save(d)
        folder = self._file(item_folder(user_id, item_id))
        for name in ("original.jpg", "cutout.png"):
            (folder / name).unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass

    def insert_corrections(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self._lock:
            d = self._load()
            now = datetime.now(timezone.utc).isoformat()
            d["corrections"].extend({"created_at": now, **r} for r in rows)
            self._save(d)

    def list_corrections(self, user_id: str) -> list[dict]:
        mine = {i["id"] for i in self.list_items(user_id)}
        return [c for c in self._load()["corrections"] if c["item_id"] in mine]


_store = None


def get_store():
    global _store
    if _store is None:
        _store = SupabaseStore() if config.USE_SUPABASE else LocalStore()
    return _store
