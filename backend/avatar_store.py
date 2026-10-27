"""Per-user avatar persistence.

Production uses Supabase Postgres (``user_avatars``) and a private Storage
bucket. Local development keeps the same interface backed by a JSON file and
the Vite public folder.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import settings

_client = None
_client_lock = threading.Lock()
_store: "AvatarStore | None" = None
_store_lock = threading.Lock()

AVATAR_COLUMNS = {
    "user_id",
    "targets",
    "details",
    "outfit",
    "metrics",
    "glb_path",
    "glb_bytes",
    "height_cm",
    "generated_at",
    "updated_at",
}


def get_supabase():
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                if not settings.SUPABASE_CONFIGURED:
                    raise RuntimeError(
                        "Supabase is not configured. Set SUPABASE_URL and "
                        "SUPABASE_SERVICE_ROLE_KEY."
                    )
                from supabase import create_client

                _client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SERVICE_ROLE_KEY,
                )
    return _client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signed_url(response: Any) -> str:
    if isinstance(response, dict):
        return str(
            response.get("signedURL")
            or response.get("signedUrl")
            or response.get("signed_url")
            or ""
        )
    return str(
        getattr(response, "signed_url", "")
        or getattr(response, "signedURL", "")
        or ""
    )


class AvatarStore:
    kind = "unknown"

    def list_owned_items(self, user_id: str, item_ids: list[str]) -> list[dict]:
        raise NotImplementedError

    def save_avatar(self, user_id: str, payload: dict, glb: bytes) -> dict:
        raise NotImplementedError

    def get_avatar(self, user_id: str) -> dict | None:
        raise NotImplementedError

    def delete_avatar(self, user_id: str) -> None:
        raise NotImplementedError


class SupabaseAvatarStore(AvatarStore):
    kind = "supabase"

    def __init__(self) -> None:
        self.db = get_supabase()
        self.bucket = settings.AVATAR_BUCKET

    def list_owned_items(self, user_id: str, item_ids: list[str]) -> list[dict]:
        if not item_ids:
            return []
        response = (
            self.db.table(settings.ITEMS_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .in_("id", item_ids)
            .execute()
        )
        return list(response.data or [])

    def _path(self, user_id: str) -> str:
        return f"{user_id}/last.glb"

    def _metadata_path(self, user_id: str) -> str:
        return f"{user_id}/last.json"

    def _save_metadata_fallback(self, row: dict) -> None:
        """Keep the last-avatar metadata next to the GLB when the table is absent."""
        data = json.dumps(row, ensure_ascii=False).encode("utf-8")
        # `application/octet-stream` is allowed by the private avatars bucket even
        # when the bucket's MIME allow-list has not been extended to application/json.
        self.db.storage.from_(self.bucket).upload(
            self._metadata_path(str(row["user_id"])),
            data,
            {"content-type": "application/octet-stream", "upsert": "true"},
        )

    def save_avatar(self, user_id: str, payload: dict, glb: bytes) -> dict:
        path = self._path(user_id)
        self.db.storage.from_(self.bucket).upload(
            path,
            glb,
            {"content-type": "model/gltf-binary", "upsert": "true"},
        )
        row = {
            "user_id": user_id,
            **payload,
            "glb_path": path,
            "glb_bytes": len(glb),
            "updated_at": _now_iso(),
        }
        db_row = {key: value for key, value in row.items() if key in AVATAR_COLUMNS}
        try:
            result = (
                self.db.table(settings.AVATARS_TABLE)
                .upsert(db_row, on_conflict="user_id")
                .execute()
            )
            saved = dict((result.data or [row])[0])
        except Exception:  # noqa: BLE001 - migration may not be applied yet
            self._save_metadata_fallback(row)
            saved = dict(row)
        saved["url"] = self._signed_url(path)
        return saved

    def _signed_url(self, path: str) -> str:
        response = self.db.storage.from_(self.bucket).create_signed_url(
            path,
            settings.SIGNED_URL_TTL_SECONDS,
        )
        return _signed_url(response)

    def _read_metadata_fallback(self, user_id: str) -> dict | None:
        try:
            data = self.db.storage.from_(self.bucket).download(
                self._metadata_path(user_id)
            )
            row = json.loads(data.decode("utf-8"))
            return row if isinstance(row, dict) else None
        except Exception:  # noqa: BLE001 - no fallback metadata yet
            return None

    def get_avatar(self, user_id: str) -> dict | None:
        row: dict | None = None
        try:
            response = (
                self.db.table(settings.AVATARS_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            rows = list(response.data or [])
            if rows:
                row = dict(rows[0])
        except Exception:  # noqa: BLE001 - table may not be migrated yet
            row = None

        if row is None:
            row = self._read_metadata_fallback(user_id)
        if row is None:
            return None

        row["url"] = self._signed_url(row.get("glb_path") or self._path(user_id))
        return row

    def delete_avatar(self, user_id: str) -> None:
        paths = [self._path(user_id), self._metadata_path(user_id)]
        try:
            self.db.storage.from_(self.bucket).remove(paths)
        except Exception:  # noqa: BLE001 - storage may already be empty
            pass
        try:
            self.db.table(settings.AVATARS_TABLE).delete().eq("user_id", user_id).execute()
        except Exception:  # noqa: BLE001 - table may not be migrated yet
            pass


class LocalAvatarStore(AvatarStore):
    kind = "local"

    def __init__(self, generated_dir: Path) -> None:
        self.root = settings.LOCAL_AVATAR_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.root / "avatars.json"
        self.generated_dir = generated_dir
        self._lock = threading.Lock()
        if not self.metadata_path.exists():
            self._write({})

    def _read(self) -> dict:
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        tmp = self.metadata_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.metadata_path)

    def list_owned_items(self, user_id: str, item_ids: list[str]) -> list[dict]:
        return []

    def _file(self, user_id: str) -> Path:
        safe = "".join(ch for ch in user_id if ch.isalnum() or ch in "-_") or "local"
        return self.generated_dir / "users" / safe / "last.glb"

    def _url(self, user_id: str) -> str:
        safe = "".join(ch for ch in user_id if ch.isalnum() or ch in "-_") or "local"
        return f"/models/generated/users/{safe}/last.glb"

    def save_avatar(self, user_id: str, payload: dict, glb: bytes) -> dict:
        target = self._file(user_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(glb)
        row = {
            "user_id": user_id,
            **payload,
            "glb_path": str(target),
            "glb_bytes": len(glb),
            "generated_at": payload.get("generated_at") or _now_iso(),
            "updated_at": _now_iso(),
            "url": self._url(user_id),
        }
        with self._lock:
            data = self._read()
            data[user_id] = row
            self._write(data)
        return row

    def get_avatar(self, user_id: str) -> dict | None:
        with self._lock:
            row = self._read().get(user_id)
        if not isinstance(row, dict):
            return None
        result = dict(row)
        result["url"] = self._url(user_id)
        return result

    def delete_avatar(self, user_id: str) -> None:
        self._file(user_id).unlink(missing_ok=True)
        with self._lock:
            data = self._read()
            data.pop(user_id, None)
            self._write(data)


def get_avatar_store(generated_dir: Path) -> AvatarStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                if settings.SUPABASE_CONFIGURED:
                    _store = SupabaseAvatarStore()
                else:
                    _store = LocalAvatarStore(generated_dir)
    return _store
