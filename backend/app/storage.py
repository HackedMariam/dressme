"""Persistence: Supabase (Postgres + Storage) in production, local JSON fallback for dev.

Every read/write is scoped to a user id, so one user can never see or change
another user's wardrobe even though the backend uses the service_role key.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone

from . import config
from .enricher import color_family_of

log = logging.getLogger("dressme.storage")
_MISSING_COLUMN = re.compile(r"Could not find the '(\w+)' column")


def _fill_defaults(row: dict) -> dict:
    """Values that can be derived when an older database doesn't store them."""
    if row and not row.get("color_family") and row.get("color_name"):
        row["color_family"] = color_family_of(row["color_name"])
    return row


def item_folder(user_id: str, item_id: str) -> str:
    return f"{user_id}/{item_id}"


class SupabaseStore:
    kind = "supabase"

    def __init__(self) -> None:
        from supabase import create_client

        self.db = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        self.bucket = config.SUPABASE_BUCKET
        self.missing_columns: set[str] = set()

    def _write(self, fn, row: dict) -> list[dict]:
        """Run an insert/update; if the table lacks a column (older schema), drop it and retry."""
        from postgrest.exceptions import APIError

        row = {k: v for k, v in row.items() if k not in self.missing_columns}
        while True:
            try:
                return fn(row).execute().data
            except APIError as e:
                m = _MISSING_COLUMN.search(str(e))
                if not m or m.group(1) not in row:
                    raise
                col = m.group(1)
                self.missing_columns.add(col)
                log.warning("Column items.%s is missing in Supabase: saving without it. "
                            "Run supabase/schema.sql again to add it.", col)
                row.pop(col)

    def upload(self, path: str, data: bytes, content_type: str) -> str:
        self.db.storage.from_(self.bucket).upload(
            path, data, {"content-type": content_type, "upsert": "true"})
        return self.db.storage.from_(self.bucket).get_public_url(path).rstrip("?")

    def download(self, path: str) -> bytes:
        return self.db.storage.from_(self.bucket).download(path)

    def insert_item(self, row: dict) -> dict:
        saved = self._write(lambda r: self.db.table("items").insert(r), row)[0]
        return _fill_defaults({**row, **saved})

    def list_items(self, user_id: str) -> list[dict]:
        rows = (self.db.table("items").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).execute().data)
        return [_fill_defaults(r) for r in rows]

    def get_item(self, user_id: str, item_id: str) -> dict | None:
        rows = (self.db.table("items").select("*").eq("id", item_id).eq("user_id", user_id)
                .limit(1).execute().data)
        return _fill_defaults(rows[0]) if rows else None

    def update_item(self, user_id: str, item_id: str, patch: dict) -> dict:
        def run(r):
            return self.db.table("items").update(r).eq("id", item_id).eq("user_id", user_id)

        stored = {k: v for k, v in patch.items() if k not in self.missing_columns}
        rows = self._write(run, stored) if stored else []
        item = rows[0] if rows else self.get_item(user_id, item_id)
        if item is None:
            raise KeyError(item_id)
        return _fill_defaults({**item, **patch})

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

    # -- private per-user files (avatar, try-ons): a private bucket that only the backend can read -----
    def _private(self):
        if not getattr(self, "_private_ready", False):
            try:
                self.db.storage.get_bucket(config.AVATAR_BUCKET)
            except Exception:
                try:
                    self.db.storage.create_bucket(config.AVATAR_BUCKET, options={"public": False})
                except Exception:
                    log.exception("Could not create the private bucket %s", config.AVATAR_BUCKET)
            self._private_ready = True
        return self.db.storage.from_(config.AVATAR_BUCKET)

    def private_put(self, path: str, data: bytes, content_type: str) -> None:
        self._private().upload(path, data, {"content-type": content_type, "upsert": "true"})

    def private_get(self, path: str) -> bytes | None:
        try:
            return self._private().download(path)
        except Exception:
            log.debug("private file %s not found", path, exc_info=True)
            return None

    def private_list(self, prefix: str) -> list[str]:
        try:
            return [entry["name"] for entry in self._private().list(prefix)]
        except Exception:
            log.debug("could not list %s", prefix, exc_info=True)
            return []

    def private_delete(self, paths: list[str]) -> None:
        if paths:
            try:
                self._private().remove(paths)
            except Exception:
                log.exception("Could not delete private files %s", paths)


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

    # -- private per-user files (same interface as SupabaseStore) ------------------------------------
    def _private_file(self, path: str):
        base = (self.root / "private").resolve()
        f = (base / path).resolve()
        if base not in f.parents and f != base:
            raise ValueError("invalid path")
        return f

    def private_put(self, path: str, data: bytes, content_type: str) -> None:
        f = self._private_file(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)

    def private_get(self, path: str) -> bytes | None:
        f = self._private_file(path)
        return f.read_bytes() if f.is_file() else None

    def private_list(self, prefix: str) -> list[str]:
        d = self._private_file(prefix)
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def private_delete(self, paths: list[str]) -> None:
        for path in paths:
            self._private_file(path).unlink(missing_ok=True)


_store = None


def get_store():
    global _store
    if _store is None:
        _store = SupabaseStore() if config.USE_SUPABASE else LocalStore()
    return _store
