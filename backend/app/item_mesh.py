"""Per-item 3D asset pipeline.

Two providers are supported:

* ``cutout-2.5d`` (default) - a fast CPU-only Blender extrusion of the cutout
  silhouette with the cutout as its texture.
* ``hunyuan3d`` - the official ``tencent/Hunyuan3D-2.1`` Hugging Face Space,
  which reconstructs a textured mesh from the cutout. It needs ``HF_TOKEN`` and
  takes roughly one to two minutes per item.

The work is serialised in one background thread because both providers are
heavy. If the Hugging Face call fails, the worker falls back to the 2.5D mesh so
an item still gets a usable preview.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import logging
import queue
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

import httpx

from . import config
from .storage import get_store, item_folder

log = logging.getLogger("dressme.item_mesh")

RESULT_RE = re.compile(r"^ITEM_MESH_RESULT (\{.*\})$", re.MULTILINE)
TEXTURE_RESULT_RE = re.compile(r"^ITEM_TEXTURE_RESULT (\{.*\})$", re.MULTILINE)
NORMALIZE_RESULT_RE = re.compile(r"^ITEM_NORMALIZE_RESULT (\{.*\})$", re.MULTILINE)
GROUP_SLOTS = {
    "Tops": "top",
    "Bottoms": "bottom",
    "Dresses": "dress",
    "Outerwear": "outerwear",
    "Shoes": "shoes",
    "Bags": "bag",
    "Accessories": "accessory",
}

_queue: "queue.Queue[tuple[str, str, str]]" = queue.Queue()
_pending: set[str] = set()
_pending_lock = threading.Lock()
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()


def mesh_builder_available() -> bool:
    return (
        config.ITEM_MESH_SCRIPT.is_file()
        and config.ITEM_NORMALIZE_SCRIPT.is_file()
        and config.BLENDER_PATH.is_file()
    )


def hf_3d_configured() -> bool:
    return bool(config.HF_TOKEN) and importlib.util.find_spec("gradio_client") is not None


def available_providers() -> list[str]:
    providers: list[str] = []
    if mesh_builder_available():
        providers.append("cutout-2.5d")
    if hf_3d_configured():
        providers.append("hunyuan3d")
    return providers


def _store():
    return get_store()


def _set_status(user_id: str, item_id: str, patch: dict) -> None:
    try:
        _store().update_item(user_id, item_id, patch)
    except Exception:  # noqa: BLE001 - mesh status is best effort
        log.warning("Could not update mesh status for item %s", item_id, exc_info=True)


def _ensure_worker() -> None:
    global _worker
    if _worker and _worker.is_alive():
        return
    with _worker_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="item-mesh-worker", daemon=True)
        _worker.start()


def enqueue_item_mesh(
    user_id: str,
    item_id: str,
    force: bool = False,
    provider: str | None = None,
) -> bool:
    """Queue a mesh build. Returns False when the item already has a fresh mesh."""
    provider = (provider or config.ITEM_MESH_PROVIDER or "cutout-2.5d").strip().lower()
    if provider not in config.MESH_PROVIDERS:
        raise ValueError(f"Unknown 3D provider '{provider}'. Allowed: {list(config.MESH_PROVIDERS)}")
    if provider not in available_providers():
        raise RuntimeError(f"The '{provider}' 3D provider is not available on this server.")

    key = f"{user_id}:{item_id}"
    with _pending_lock:
        if key in _pending:
            return False
        _pending.add(key)

    item = _store().get_item(user_id, item_id)
    if not item:
        with _pending_lock:
            _pending.discard(key)
        return False
    if not force and item.get("mesh_status") == "ready" and item.get("mesh_url"):
        with _pending_lock:
            _pending.discard(key)
        return False

    _set_status(user_id, item_id, {
        "mesh_status": "queued",
        "mesh_error": None,
    })
    _queue.put((user_id, item_id, provider))
    _ensure_worker()
    return True


def _worker_loop() -> None:
    while True:
        user_id, item_id, provider = _queue.get()
        key = f"{user_id}:{item_id}"
        try:
            _build(user_id, item_id, provider)
        except Exception as exc:  # noqa: BLE001 - keep the queue alive
            log.exception("Item mesh build failed for %s", item_id)
            _set_status(user_id, item_id, {
                "mesh_status": "failed",
                "mesh_error": str(exc)[:900],
            })
        finally:
            with _pending_lock:
                _pending.discard(key)
            _queue.task_done()


def _download_cutout(item: dict) -> bytes:
    folder = item_folder(str(item["user_id"]), str(item["id"]))
    try:
        return _store().download(f"{folder}/cutout.png")
    except Exception:  # noqa: BLE001 - fall back to the stored URL
        pass

    url = str(item.get("cutout_url") or "").strip()
    if not url:
        raise RuntimeError("This item has no cutout image to build a 3D mesh from.")
    if url.startswith("data:"):
        header, _, encoded = url.partition(",")
        if ";base64" not in header:
            raise RuntimeError("Unsupported cutout data URL.")
        return base64.b64decode(encoded)
    if url.startswith("http://") or url.startswith("https://"):
        response = httpx.get(url, timeout=20.0, follow_redirects=True)
        response.raise_for_status()
        return response.content
    raise RuntimeError("Could not download the item cutout.")


def _build(user_id: str, item_id: str, provider: str) -> None:
    store = _store()
    item = store.get_item(user_id, item_id)
    if not item:
        return

    _set_status(user_id, item_id, {"mesh_status": "building", "mesh_error": None})
    cutout = _download_cutout(item)

    config.ITEM_MESH_WORK_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{item_id[:8]}-", dir=config.ITEM_MESH_WORK_DIR))
    cutout_path = work / "cutout.png"
    cutout_path.write_bytes(cutout)

    try:
        if provider == "hunyuan3d":
            try:
                glb_path, meta = _run_hunyuan3d(cutout_path, work)
                source = meta.pop("source", f"hunyuan3d:{config.HF_3D_SPACE}")
            except Exception as exc:  # noqa: BLE001 - keep the fast fallback available
                log.warning("Hunyuan3D failed for %s; falling back to 2.5D: %s", item_id, exc)
                glb_path, meta = _run_cutout(cutout_path, work, item)
                source = "cutout-2.5d"
                meta = {
                    **meta,
                    "provider": "cutout-2.5d",
                    "requested_provider": "hunyuan3d",
                    "fallback_reason": str(exc)[:500],
                }
        else:
            glb_path, meta = _run_cutout(cutout_path, work, item)
            source = "cutout-2.5d"

        glb_path, normalize_meta = _normalize_mesh(
            glb_path,
            work,
            GROUP_SLOTS.get(str(item.get("category_group") or ""), "accessory"),
        )
        meta = {**meta, "normalization": normalize_meta}
        glb_bytes = glb_path.read_bytes()
        if glb_bytes[:4] != b"glTF":
            raise RuntimeError("The 3D provider produced an invalid GLB file.")

        folder = item_folder(user_id, item_id)
        mesh_url = store.upload(f"{folder}/mesh.glb", glb_bytes, "model/gltf-binary")
        version = int(item.get("mesh_version") or 0) + 1
        _set_status(user_id, item_id, {
            "mesh_url": mesh_url,
            "mesh_status": "ready",
            "mesh_source": source,
            "mesh_version": version,
            "mesh_meta": {**meta, "bytes": len(glb_bytes)},
            "mesh_error": None,
        })
        log.info("Built %s mesh for item %s (%s bytes)", source, item_id, len(glb_bytes))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_cutout(cutout_path: Path, work: Path, item: dict) -> tuple[Path, dict]:
    output_path = work / "mesh.glb"
    slot = GROUP_SLOTS.get(str(item.get("category_group") or ""), "accessory")
    cmd = [
        str(config.BLENDER_PATH),
        "--background",
        "--python",
        str(config.ITEM_MESH_SCRIPT),
        "--",
        "--cutout",
        str(cutout_path),
        "--output",
        str(output_path),
        "--slot",
        slot,
        "--grid",
        str(config.ITEM_MESH_GRID),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.ITEM_MESH_TIMEOUT_SECONDS,
        shell=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    matches = RESULT_RE.findall(combined)
    result = None
    if matches:
        try:
            result = json.loads(matches[-1])
        except json.JSONDecodeError:
            result = None

    if proc.returncode != 0 or not result or not result.get("ok"):
        detail = (result or {}).get("error") or f"Blender exited with code {proc.returncode}"
        tail = "\n".join(combined.strip().splitlines()[-6:])
        raise RuntimeError(f"{detail} | {tail}")

    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError("Blender did not produce a mesh file.")
    meta = {
        **{key: result.get(key) for key in ("slot", "grid", "faces", "width", "height", "depth", "thickness")},
        "provider": "cutout-2.5d",
    }
    return output_path, meta


def _normalize_mesh(mesh_path: Path, work: Path, slot: str) -> tuple[Path, dict]:
    output_path = work / "normalized_mesh.glb"
    cmd = [
        str(config.BLENDER_PATH),
        "--background",
        "--python",
        str(config.ITEM_NORMALIZE_SCRIPT),
        "--",
        "--mesh",
        str(mesh_path),
        "--output",
        str(output_path),
        "--slot",
        slot,
        "--target-faces",
        str(config.ITEM_MESH_TARGET_FACES),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.ITEM_MESH_TIMEOUT_SECONDS,
        shell=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    matches = NORMALIZE_RESULT_RE.findall(combined)
    result = None
    if matches:
        try:
            result = json.loads(matches[-1])
        except json.JSONDecodeError:
            result = None
    if proc.returncode != 0 or not result or not result.get("ok"):
        detail = (result or {}).get("error") or f"Blender exited with code {proc.returncode}"
        tail = "\n".join(combined.strip().splitlines()[-6:])
        raise RuntimeError(f"Mesh normalization failed: {detail} | {tail}")
    if not output_path.is_file() or output_path.read_bytes()[:4] != b"glTF":
        raise RuntimeError("Mesh normalization did not produce a valid GLB.")
    return output_path, {
        "objects": result.get("objects"),
        "faces_before": result.get("faces_before"),
        "faces": result.get("faces"),
        "dimensions": result.get("dimensions"),
        "slot": result.get("slot"),
    }


def _hunyuan_client():
    from gradio_client import Client

    return Client(
        config.HF_3D_SPACE,
        hf_token=config.HF_TOKEN,
        verbose=False,
        httpx_kwargs={"timeout": min(float(config.HF_3D_TIMEOUT_SECONDS), 300.0)},
    )


def _call_hunyuan(cutout_path: Path, work: Path, api_name: str,
                  steps: int, octree: int) -> tuple[Path, dict]:
    from gradio_client import handle_file

    params: dict[str, Any] = {
        "image": handle_file(str(cutout_path)),
        "mv_image_front": None,
        "mv_image_back": None,
        "mv_image_left": None,
        "mv_image_right": None,
        "steps": steps,
        "guidance_scale": 5.0,
        "seed": 1234,
        "octree_resolution": octree,
        "check_box_rembg": True,
        "num_chunks": 8000,
        "randomize_seed": True,
    }
    if config.HF_3D_SPACE.rstrip("/").lower() == "tencent/hunyuan3d-2":
        params["caption"] = config.HF_3D_CAPTION

    job = _hunyuan_client().submit(**params, api_name=api_name)
    result = job.result(timeout=config.HF_3D_TIMEOUT_SECONDS)

    source = _find_file(result, ".glb")
    if not source:
        raise RuntimeError("Hunyuan3D did not return a GLB file.")
    name = api_name.strip("/").replace("/", "_") or "mesh"
    destination = work / f"hunyuan3d_{name}.glb"
    shutil.copyfile(source, destination)
    return destination, _extract_stats(result)


def _texture_mesh(mesh_path: Path, cutout_path: Path, work: Path) -> tuple[Path, dict]:
    output_path = work / "textured_from_shape.glb"
    cmd = [
        str(config.BLENDER_PATH),
        "--background",
        "--python",
        str(config.ITEM_TEXTURE_SCRIPT),
        "--",
        "--mesh",
        str(mesh_path),
        "--texture",
        str(cutout_path),
        "--output",
        str(output_path),
        "--target-faces",
        str(config.HF_3D_TARGET_FACES),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.ITEM_MESH_TIMEOUT_SECONDS,
        shell=False,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    matches = TEXTURE_RESULT_RE.findall(combined)
    result = None
    if matches:
        try:
            result = json.loads(matches[-1])
        except json.JSONDecodeError:
            result = None
    if proc.returncode != 0 or not result or not result.get("ok"):
        detail = (result or {}).get("error") or f"Blender exited with code {proc.returncode}"
        tail = "\n".join(combined.strip().splitlines()[-5:])
        raise RuntimeError(f"{detail} | {tail}")
    if not output_path.is_file() or output_path.read_bytes()[:4] != b"glTF":
        raise RuntimeError("The local texturing pass did not produce a valid GLB.")
    return output_path, {
        "texture": result.get("texture"),
        "faces_before": result.get("faces_before"),
        "faces": result.get("faces"),
    }


def _run_hunyuan3d(cutout_path: Path, work: Path) -> tuple[Path, dict]:
    """Try Hunyuan3D textured output, then shape-only + local cutout texture."""
    errors: list[str] = []
    try:
        path, meta = _call_hunyuan(
            cutout_path,
            work,
            config.HF_3D_API_NAME,
            config.HF_3D_STEPS,
            config.HF_3D_OCTREE_RESOLUTION,
        )
        if config.HF_3D_API_NAME.rstrip("/").endswith("shape_generation"):
            textured, texture_meta = _texture_mesh(path, cutout_path, work)
            meta = {**meta, **texture_meta, "textured": True, "local_texture": True}
            return textured, {**meta, "source": f"hunyuan3d:{config.HF_3D_SPACE}:shape+cutout"}
        meta["textured"] = True
        return path, {**meta, "source": f"hunyuan3d:{config.HF_3D_SPACE}"}
    except Exception as exc:  # noqa: BLE001 - try the cheaper shape-only path
        errors.append(f"textured: {exc}")
        log.warning("Hunyuan3D textured call failed: %s", exc)
        if not config.HF_3D_SHAPE_FALLBACK:
            raise RuntimeError("; ".join(errors)[:1200]) from exc

    try:
        path, meta = _call_hunyuan(
            cutout_path,
            work,
            "/shape_generation",
            min(5, max(1, config.HF_3D_STEPS)),
            min(196, max(32, config.HF_3D_OCTREE_RESOLUTION)),
        )
        textured, texture_meta = _texture_mesh(path, cutout_path, work)
        meta = {
            **meta,
            **texture_meta,
            "textured": True,
            "local_texture": True,
            "shape_only_fallback": True,
            "source": f"hunyuan3d:{config.HF_3D_SPACE}:shape+cutout",
        }
        return textured, meta
    except Exception as exc:  # noqa: BLE001 - caller falls back to 2.5D
        errors.append(f"shape: {exc}")

    raise RuntimeError("; ".join(errors)[:1200])


def _find_file(value: Any, suffix: str) -> str | None:
    suffix = suffix.lower()
    if isinstance(value, dict):
        nested = value.get("value")
        if isinstance(nested, str) and nested.lower().endswith(suffix) and Path(nested).is_file():
            return nested
        for item in value.values():
            found = _find_file(item, suffix)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _find_file(item, suffix)
            if found:
                return found
    elif isinstance(value, str) and value.lower().endswith(suffix) and Path(value).is_file():
        return value
    return None


def _extract_stats(value: Any) -> dict:
    if isinstance(value, dict):
        if "number_of_faces" in value:
            return {
                "provider": "hunyuan3d",
                "model": value.get("model"),
                "params": value.get("params"),
                "faces": value.get("number_of_faces"),
                "vertices": value.get("number_of_vertices"),
                "provider_time": value.get("time"),
            }
        for item in value.values():
            stats = _extract_stats(item)
            if stats:
                return stats
    elif isinstance(value, (list, tuple)):
        for item in value:
            stats = _extract_stats(item)
            if stats:
                return stats
    return {"provider": "hunyuan3d"}


def mesh_fields(item: dict) -> dict:
    return {
        "mesh_url": item.get("mesh_url"),
        "mesh_status": item.get("mesh_status") or "none",
        "mesh_source": item.get("mesh_source"),
        "mesh_version": item.get("mesh_version") or 0,
        "mesh_meta": item.get("mesh_meta"),
        "mesh_error": item.get("mesh_error"),
    }
