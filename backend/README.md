# DressMe avatar generation backend

Local FastAPI service that runs Blender 5.4 headless with the MPFB2 extension to
regenerate the avatar GLB from adjustable body parameters. Binds to 127.0.0.1 only.

## Requirements (already set up on this machine)

- Python 3.12
- Blender 5.4.0-alpha (portable) with the MPFB2 extension enabled:
  `C:\Users\maria\Downloads\blender-5.4.0-alpha+main.29ff43161222-windows.amd64-release\blender-5.4.0-alpha+main.29ff43161222-windows.amd64-release\blender.exe`
- Source scene: `C:\Users\maria\Desktop\5eme esprit\avatar.blend` (contains the MPFB basemesh)

Paths can be overridden with env vars `BLENDER_PATH`, `AVATAR_BLEND`, `GENERATED_DIR`, `JOB_TIMEOUT_SECONDS`.

## Install

    cd "C:\Users\maria\Desktop\5eme esprit\Dressme\backend"
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt

## Run

    cd "C:\Users\maria\Desktop\5eme esprit\Dressme\backend"
    venv\Scripts\activate
    uvicorn main:app --host 127.0.0.1 --port 8000

Keep this terminal open while using "Generate Avatar" in the app.

## API

- `GET /api/health` -> `{"ok": true, "blenderExists": true, "blendExists": true}`
- `POST /api/avatar/generate` with body `{"targets": {"muscle": 0.7}}`
  - Whitelisted params (each a float 0.0-1.0): `gender age muscle weight height proportions cupsize firmness`
  - `409` if a job is already running, `422` for invalid input, `500` for Blender errors (message includes a log tail), `504` on timeout
  - Response: `{"jobId": "...", "url": "/models/generated/avatar_<jobId>.glb", "params": {...}, "bytes": N, "elapsedSeconds": N}`

## How a job runs

1. Request targets are validated (whitelist + bounds) and written to `temp/params_<id>.json` — values are never interpolated into Python code.
2. `blender --background avatar.blend --python blender/generate_avatar.py -- --params ... --output ...` runs as a subprocess with a 300 s timeout.
3. The script sets the whitelisted MPFB `HumanObjectProperties`, runs `TargetService.reapply_macro_details`, stages an export copy, bakes shape keys, and exports GLB.
4. Output is validated (non-empty, `glTF` magic bytes) in `temp/`, then moved to `DressMe UI Blueprint/public/models/generated/avatar_<id>.glb` where Vite serves it.
5. The original `public/models/avatar.glb` is never touched.

## Customize My Avatar -> MPFB parameters (v1)

The Customize page has sliders for all eight whitelisted MPFB parameters, each
`0.00`-`1.00` with `0.50` as the neutral default:

`gender age height weight muscle proportions cupsize firmness`

Only parameters that differ from neutral are listed in the "Will apply" preview, but all
eight are sent. Four are pre-filled from the photo pose estimate (heuristic, uncalibrated):

| Photo metric (MediaPipe pose) | MPFB parameter | Rule |
| --- | --- | --- |
| shoulder / hip widths | `muscle` | `0.5 + (shoulderToHip - 1.3) * 0.6` |
| torso / leg lengths | `proportions` | `0.5 + (0.75 - torsoToLeg) * 1.2` |
| leg length / body height | `height` | `0.5 + (legToHeight - 0.53) * 4` |
| (shoulder + hip width) / body height | `weight` | `0.5 + (widthRatio - 0.35) * 5` |

The other four are NOT derived from the photo:

- `gender`, `age` — self-reported via quick-pick buttons on the page.
- `cupsize`, `firmness` — manual sliders only.

A single uncalibrated 2D photo cannot measure a body, so these are rough shape hints, not
measurements, and the page labels them as low confidence. Estimation constants and the
mapping live in `DressMe UI Blueprint/src/lib/avatarApi.ts` (`estimatesFromMetrics`); the
raw metrics come from `DressMe UI Blueprint/src/lib/pose.ts` (`BodyMetrics`).

## Test from a terminal

    curl -X POST http://127.0.0.1:8000/api/avatar/generate -H "Content-Type: application/json" -d "{\"targets\": {\"weight\": 0.2}}"
