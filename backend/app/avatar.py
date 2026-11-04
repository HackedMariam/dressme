"""3D avatar and virtual try-on, built on fal.ai (one API key, pay per use): https://fal.ai

- create_avatar: a full-body photo of the user -> image-to-3D (Hunyuan3D) -> a textured 3D model (GLB) of the person.
- try_on:        the same photo + the cut-out of a wardrobe piece -> FASHN try-on (2D, the person wearing it)
                 -> image-to-3D -> the person wearing it, in 3D.

Each call takes seconds to a couple of minutes, so the API runs them as background jobs the browser polls.

Privacy: the photo goes to fal.ai (and FASHN through it) after the user's consent. DressMe keeps the photo, the 3D
models and the try-on images in a private bucket scoped to the user, and `delete_all` removes everything.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

import httpx
from PIL import Image, ImageOps

from . import config

log = logging.getLogger("dressme.avatar")

MAX_SIDE = 1536
# BO1 wardrobe group -> FASHN try-on category (tryon-v1.6 covers tops, bottoms and one-pieces)
TRYON_CATEGORY = {"Tops": "tops", "Outerwear": "tops", "Bottoms": "bottoms", "Dresses": "one-pieces"}
GLB_MAGIC = b"glTF"


class AvatarError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def is_configured() -> bool:
    return bool(config.FAL_KEY)


def tryon_category(item: dict) -> str | None:
    """The FASHN category for a wardrobe item, or None when try-on does not support it (shoes, bags...)."""
    return TRYON_CATEGORY.get(item.get("category_group") or "")


# ---------------------------------------------------------------------------------------- images
def normalize_photo(data: bytes) -> bytes:
    """A bounded JPEG: EXIF orientation applied, transparency flattened onto white."""
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[3])
            img = flat
        else:
            img = img.convert("RGB")
    except Exception as error:
        raise AvatarError(400, "Unreadable image. Use a JPG, PNG, WEBP or HEIC photo.") from error
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


MAX_REMOTE_IMAGE = 8 * 1024 * 1024


def tryon_category_for_group(group: str) -> str | None:
    return TRYON_CATEGORY.get(group)


def fetch_remote_image(url: str) -> bytes:
    """Download a shop photo for a try-on. https only, public hosts only, no redirects, size capped:
    the URL comes from the browser, so it must never be able to reach the server's own network."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise AvatarError(400, "The garment image must be an https link.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except OSError as error:
        raise AvatarError(400, "The garment image host could not be resolved.") from error
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise AvatarError(400, "The garment image must be on a public website.")
    try:
        with httpx.stream("GET", url, timeout=15, follow_redirects=False,
                          headers={"User-Agent": "Mozilla/5.0 DressMe"}) as response:
            if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                raise AvatarError(400, "The garment link is not an image.")
            data = b""
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > MAX_REMOTE_IMAGE:
                    raise AvatarError(400, "The garment image is too large.")
    except httpx.HTTPError as error:
        raise AvatarError(502, "Could not download the garment image.") from error
    return data


def _data_uri(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(normalize_photo(jpeg)).decode()


# ---------------------------------------------------------------------------------------- fal.ai
class FalClient:
    """Queue API: submit a request, poll its status, fetch the result and the files it points to."""

    def __init__(self, api_key: str, timeout: float, *, base_url: str = "https://queue.fal.run",
                 transport=None, poll_interval: float = 2.0) -> None:
        self.http = httpx.Client(headers={"Authorization": f"Key {api_key}"}, timeout=60, transport=transport)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval

    def run(self, model_id: str, inputs: dict) -> dict:
        submitted = self._call("post", f"{self.base_url}/{model_id}", json=inputs)
        status_url, response_url = submitted.get("status_url"), submitted.get("response_url")
        if not status_url or not response_url:
            raise AvatarError(502, "fal.ai did not accept the request. Please try again.")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            state = self._call("get", status_url)
            if state.get("error"):
                raise AvatarError(502, f"fal.ai could not finish: {state['error']}")
            if state.get("status") == "COMPLETED":
                return self._call("get", response_url)
            time.sleep(self.poll_interval)
        raise AvatarError(504, "fal.ai took too long to answer. Please try again.")

    def download(self, url: str) -> bytes:
        try:
            reply = self.http.get(url, timeout=120)
            reply.raise_for_status()
        except httpx.HTTPError as error:
            raise AvatarError(502, "Could not download the file fal.ai generated.") from error
        return reply.content

    def _explain(self, url: str, error: httpx.HTTPError) -> AvatarError:
        """A refused account (no credit, bad key) closes the connection while the photo is still uploading, which looks
        like a network failure. Ask fal.ai a free question to tell the two apart."""
        parts = url.removeprefix(self.base_url).strip("/").split("/")
        probe = f"{self.base_url}/{'/'.join(parts[:2])}/requests/00000000-0000-0000-0000-000000000000/status"
        try:
            reply = self.http.get(probe, timeout=15)
            if reply.status_code in (401, 403):
                return _http_error(reply.status_code, {})
        except httpx.HTTPError:
            pass
        return AvatarError(502, f"Cannot reach fal.ai ({type(error).__name__}). Check the internet connection and try again.")

    def _call(self, method: str, url: str, **kwargs) -> dict:
        try:
            reply = getattr(self.http, method)(url, **kwargs)
        except httpx.HTTPError as error:
            log.warning("fal.ai call failed: %s: %s", type(error).__name__, error)
            raise self._explain(url, error) from error
        try:
            body = reply.json()
        except ValueError:
            body = {}
        if reply.status_code >= 400:
            raise _http_error(reply.status_code, body)
        return body if isinstance(body, dict) else {}


def _http_error(status: int, body: dict) -> AvatarError:
    detail = body.get("detail") if isinstance(body, dict) else None
    text = detail if isinstance(detail, str) else json.dumps(detail) if detail else ""
    if status == 403 and "does not have access to model" in text:
        # The key is valid and funded, but restricted to other models: only the user can fix it in the fal.ai dashboard.
        return AvatarError(503, f"{text}. Create a FAL_KEY with API access to all models "
                                "(fal.ai/dashboard/keys), put it in .env and restart the backend.")
    if status in (401, 403):
        return AvatarError(503, "fal.ai refused the request: check FAL_KEY and that the account has credit (fal.ai/dashboard/billing).")
    if status == 429:
        return AvatarError(429, "fal.ai is busy (rate limit). Try again in a few seconds.")
    if status == 422:
        return AvatarError(422, f"fal.ai rejected the image: {text[:200] or 'invalid input'}")
    return AvatarError(502, f"fal.ai error ({status}) {text[:200]}".strip())


def _client() -> FalClient:
    if not is_configured():
        raise AvatarError(503, "The avatar service is not configured: set FAL_KEY in the server .env.")
    return FalClient(config.FAL_KEY, config.FAL_TIMEOUT)


def image_to_3d(image: bytes) -> bytes:
    """A textured GLB of whatever the image shows (here: a person)."""
    client = _client()
    output = client.run(config.FAL_3D_MODEL, {
        "input_image_url": _data_uri(image),
        "textured_mesh": True,
        "num_inference_steps": 50,
        "guidance_scale": 7.5,
        "octree_resolution": 256,
    })
    url = (output.get("model_mesh") or {}).get("url")
    if not url:
        raise AvatarError(502, "The 3D service returned no model. Please try again.")
    glb = client.download(url)
    if not glb.startswith(GLB_MAGIC):
        raise AvatarError(502, "The 3D service returned an unexpected file. Please try again.")
    return glb


def try_on_image(photo: bytes, garment_png: bytes, category: str) -> bytes:
    """2D step: the person wearing the garment (FASHN try-on)."""
    client = _client()
    output = client.run(config.FAL_TRYON_MODEL, {
        "model_image": _data_uri(photo),
        "garment_image": _data_uri(garment_png),
        "category": category,
        "garment_photo_type": "auto",
        "mode": config.FAL_TRYON_MODE,
        "num_samples": 1,
        "output_format": "png",
    })
    images = output.get("images") or []
    url = images[0].get("url") if images and isinstance(images[0], dict) else None
    if not url:
        raise AvatarError(502, "The try-on service returned no image. Please try again.")
    return client.download(url)


# ---------------------------------------------------------------------------------------- jobs
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_events: dict[tuple[str, str], list[float]] = {}


def check_quota(user_id: str, kind: str, limit: int, window_seconds: float) -> None:
    """Every call costs money: cap how often one user can trigger them."""
    now = time.time()
    with _jobs_lock:
        recent = [t for t in _events.get((user_id, kind), []) if now - t < window_seconds]
        if len(recent) >= limit:
            raise AvatarError(429, f"Limit reached ({limit} {kind} per {max(1, int(window_seconds // 3600))} h). Try again later.")
        recent.append(now)
        _events[(user_id, kind)] = recent


# fal.ai refused the work before doing it (bad or restricted key, rejected image, rate limit): nothing was charged,
# so the attempt must not use up the user's daily or hourly allowance.
REFUNDABLE_STATUSES = {422, 429, 503}


def refund_quota(user_id: str, kind: str, count: int = 1) -> None:
    with _jobs_lock:
        events = _events.get((user_id, kind), [])
        del events[max(0, len(events) - count):]


def start_job(user_id: str, kind: str, work: Callable[[], None],
              quota: tuple[str, int] | None = None) -> str:
    """Run `work` in the background; the browser polls get_job. One job at a time per user.
    `quota` = (kind, units) charged by check_quota: given back if fal.ai refused the work without doing it."""
    with _jobs_lock:
        for job in _jobs.values():
            if job["user_id"] == user_id and job["status"] == "running":
                raise AvatarError(409, "Another generation is already running. Wait for it to finish.")
        for old in [k for k, j in _jobs.items() if time.time() - j["started"] > 3600]:
            _jobs.pop(old)
        job_id = uuid.uuid4().hex[:12]
        _jobs[job_id] = {"id": job_id, "user_id": user_id, "kind": kind, "status": "running", "error": None,
                         "started": time.time()}

    def run() -> None:
        try:
            work()
            outcome = {"status": "done"}
        except AvatarError as error:
            outcome = {"status": "failed", "error": error.message}
            if quota and error.status_code in REFUNDABLE_STATUSES:
                refund_quota(user_id, quota[0], quota[1])
        except Exception:
            log.exception("avatar job %s failed", job_id)
            outcome = {"status": "failed", "error": "Something went wrong while generating. Please try again."}
        with _jobs_lock:
            _jobs[job_id].update(outcome)

    threading.Thread(target=run, name=f"avatar-{job_id}", daemon=True).start()
    return job_id


def get_job(user_id: str, job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job["user_id"] != user_id:
            raise AvatarError(404, "Unknown job")
        return {k: job[k] for k in ("id", "kind", "status", "error")}


def running_job(user_id: str) -> dict | None:
    with _jobs_lock:
        for job in _jobs.values():
            if job["user_id"] == user_id and job["status"] == "running":
                return {k: job[k] for k in ("id", "kind", "status", "error")}
    return None


# ---------------------------------------------------------------------------------------- storage
def _path(user_id: str, name: str) -> str:
    return f"{user_id}/{name}"


def _tryon_path(user_id: str, item_id: str, ext: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", item_id):   # an id from the URL must never reach another folder
        raise AvatarError(404, "No try-on yet")
    return f"{user_id}/tryon/{item_id}.{ext}"


def status(store, user_id: str) -> dict:
    names = store.private_list(user_id)
    exists = "avatar.glb" in names
    meta = {}
    if exists:
        raw = store.private_get(_path(user_id, "meta.json"))
        meta = json.loads(raw) if raw else {}
    tryon_files = store.private_list(f"{user_id}/tryon") if exists else []
    stems = sorted({name.rsplit(".", 1)[0] for name in tryon_files if name.endswith((".png", ".glb"))})
    return {
        "configured": is_configured(),
        "exists": exists,
        "created_at": meta.get("created_at"),
        "tryons": [{"item_id": stem, "has_3d": f"{stem}.glb" in tryon_files} for stem in stems],
        "job": running_job(user_id),
    }


def load_photo(store, user_id: str) -> bytes | None:
    return store.private_get(_path(user_id, "photo.jpg"))


def load_model(store, user_id: str) -> bytes | None:
    return store.private_get(_path(user_id, "avatar.glb"))


def save_avatar(store, user_id: str, photo: bytes, glb: bytes) -> None:
    _clear_tryons(store, user_id)   # try-ons were made on the previous photo
    store.private_put(_path(user_id, "photo.jpg"), photo, "image/jpeg")
    store.private_put(_path(user_id, "avatar.glb"), glb, "model/gltf-binary")
    meta = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provider": "fal.ai"}
    store.private_put(_path(user_id, "meta.json"), json.dumps(meta).encode(), "application/json")


def load_tryon(store, user_id: str, item_id: str, ext: str) -> bytes | None:
    return store.private_get(_tryon_path(user_id, item_id, ext))


def save_tryon(store, user_id: str, item_id: str, data: bytes, ext: str) -> None:
    store.private_put(_tryon_path(user_id, item_id, ext), data,
                      "image/png" if ext == "png" else "model/gltf-binary")


def _clear_tryons(store, user_id: str) -> None:
    store.private_delete([f"{user_id}/tryon/{name}" for name in store.private_list(f"{user_id}/tryon")])


def delete_all(store, user_id: str) -> None:
    _clear_tryons(store, user_id)
    store.private_delete([_path(user_id, name) for name in ("photo.jpg", "avatar.glb", "meta.json")])
