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

- `GET /api/health` -> `{"ok": true, "blenderExists": true, "blendExists": true, "dressedScriptExists": true, "allowedGarments": [...], "slots": [...]}`
- `POST /api/avatar/generate` with body `{"targets": {"muscle": 0.7, "legLength": 0.65}, "outfit": ["turtleneck", "jeans", "boots"]}`
  - Whitelisted params (each a float 0.0-1.0): `gender age muscle weight height proportions cupsize firmness legLength`
  - `legLength` is applied by the Blender scripts after MPFB shaping (a dedicated post-process, not an MPFB macro).
  - Optional `outfit`: ordered list of garment ids from the shared catalogue. Omit or send `[]` for a bare body.
  - Slot rules: one item per slot (`top`, `bottom`, `dress`, `outerwear`, `shoes`); a dress cannot be combined with a top or bottom.
  - `409` if a job is already running, `422` for invalid input, `500` for Blender errors (message includes a log tail), `504` on timeout
  - Response: `{"jobId": "...", "url": "/models/generated/avatar_<jobId>.glb", "params": {...}, "outfit": [...], "bytes": N, "elapsedSeconds": N, "metrics": {"shoulderToHip": 1.31, "torsoToLeg": 0.74, "heightMeters": 1.72}}`
  - With an `outfit`, the dressed generator runs instead of the bare-body one (same request/response shape).
  - Old generated GLBs are deleted after `GENERATED_TTL_HOURS` (default 24h) on the next job; temp files older than 1h are cleaned too.

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
are sent. Values are pre-filled from the photo pose estimate only when the relevant metric
passed the reliability checks:

| Photo metric (MediaPipe pose) | Parameter | Rule |
| --- | --- | --- |
| shoulder / hip widths | `muscle` | `0.5 + (shoulderToHip - 1.3) * 0.6` |
| torso / leg lengths | `legLength` | `0.5 + (0.75 - torsoToLeg) * 1.25` |
| leg length / body height | `height` | `0.5 + (legToHeight - 0.53) * 4` |
| (shoulder + hip width) / body height | `weight` | `0.5 + (widthRatio - 0.35) * 5` |

The other controls are NOT derived from the photo:

- `gender`, `age` — self-reported via quick-pick buttons on the page.
- `proportions`, `cupsize`, `firmness` — manual sliders only.

A single uncalibrated 2D photo cannot measure a body, so these are rough shape hints, not
measurements. The page now shows which values are photo-derived and rejects sideways
photos where width ratios are unreliable. Estimation constants and the mapping live in
`DressMe UI Blueprint/src/lib/avatarApi.ts` (`estimatesFromMetrics`); raw metrics and
reliability flags come from `DressMe UI Blueprint/src/lib/pose.ts`.

The Customize page also runs one closed-loop correction pass: after generation the
backend reports the ratios the body actually achieved (`metrics`), the frontend nudges
`muscle`/`legLength`, and Blender regenerates once so the avatar's proportions track the
photo more closely.

## Test from a terminal

    curl -X POST http://127.0.0.1:8000/api/avatar/generate -H "Content-Type: application/json" -d "{\"targets\": {\"weight\": 0.2}}"

## Avatar audit (stable format)

`backend/blender/audit_avatar.py` inspects `avatar.blend`. Current findings:

- One mesh object `Human` (MPFB2 basemesh), **no armature**. It has `joint-*` vertex
  groups that weight MPFB's joint cubes (8 verts each) - these give exact anatomical
  landmarks - plus a `MASK` modifier `Hide helpers`.
- **11 shape keys** (`$md-$as-$fe-$yn`, culture/sex/cup macro morphs) - the morph data.
- 19,158 verts / 18,486 polys / 36,972 tris, one `UVMap`, **no materials**.
- Identity transform, Z-up, ~1.66 m tall standing on Z=0, faces -Y, width 1.05 m.
- The export pipeline **bakes shape keys**, so the GLB is a static mesh: no skeleton,
  no morph targets. Same topology every regeneration.

## Garments & try-on

Garments are **created from the body surface**, not imported assets (no license
concerns). The catalogue lives in `DressMe UI Blueprint/src/lib/garments.json` and is
read by both the frontend and the Blender generator, so ids, slots, labels, colors and
regions cannot drift apart. `backend/blender/generate_dressed_avatar.py`:

1. Reads the joint-cube landmarks (via an evaluated copy with the mask disabled).
2. Classifies every skin vertex to the nearest anatomical bone segment.
3. Keeps the vertices for a garment region (torso+short sleeves for the tee, hips to
   ankle for trousers, torso+full sleeves for the layering pieces, feet for boots),
   offsets them outward along their normals, and solidifies.
4. Applies the optional torso/leg post-process before building garments, so the shells
   follow the actual leg length.
5. Assigns a Principled material and exports avatar + garments as one GLB.

Because each garment is re-derived from the *actual generated body*, it fits every
body shape by construction. Tested across slim / neutral / broad configs (body height
1.43 m -> 2.09 m): the shell offset stayed constant (tee ~12 mm, trousers ~14 mm,
jacket ~28 mm). This is the deformation strategy for the MVP - shared skinning weights
and morph targets are not needed while the avatar is rebuilt per request.

The base outfit shown before the first generation lives at
`DressMe UI Blueprint/public/models/dressed_avatar.glb`.

`backend/blender/render_preview.py` renders front / three-quarter / side PNGs of any
GLB - useful for eyeballing fit:

    blender --background --python blender/render_preview.py -- --glb model.glb --out previews\\m
