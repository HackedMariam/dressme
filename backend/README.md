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
- `POST /api/avatar/generate` with body `{"targets": {"muscle": 0.7, "legLength": 0.65}, "details": {"measure-waist-circ-incr": 0.2}, "outfit": ["turtleneck", "jeans", "boots"], "height_cm": 172}`
  - Whitelisted params (each a float 0.0-1.0): `gender age muscle weight height proportions cupsize firmness legLength`
  - Optional `height_cm` (140-220): after shaping, the Blender scripts uniformly scale the character to this real-world height and report it in `metrics.heightMeters`.
  - Optional `details`: up to 128 whitelisted MPFB detail targets (each 0.0-1.0), e.g. `measure-waist-circ-incr`, `measure-hips-circ-decr`, `torso-scale-depth-incr`, `measure-thigh-circ-incr`. The allowlist lives in `backend/mpfb_targets.json` and is validated in `backend/mpfb_details.py`. Macro names are rejected here; use `targets` for those.
  - `legLength` is applied by the Blender scripts after MPFB shaping (a dedicated post-process, not an MPFB macro).
  - Detail targets are loaded after the macros and before the export copy, so the GLB and any garments are built from the adjusted body.
  - Optional `outfit`: ordered list of garment ids from the shared catalogue. Omit or send `[]` for a bare body.
  - Slot rules: one item per slot (`top`, `bottom`, `dress`, `outerwear`, `shoes`); a dress cannot be combined with a top or bottom.
  - `409` if a job is already running, `422` for invalid input, `500` for Blender errors (message includes a log tail), `504` on timeout
  - Response: `{"jobId": "...", "url": "/models/generated/avatar_<jobId>.glb", "params": {...}, "details": {...}, "outfit": [...], "bytes": N, "elapsedSeconds": N, "metrics": {"shoulderToHip": 1.31, "torsoToLeg": 0.74, "heightMeters": 1.72}}`
  - With an `outfit`, the dressed generator runs instead of the bare-body one (same request/response shape).
  - Wardrobe-driven try-on: send `wardrobe_item_ids` (UUIDs from `public.items`) instead of `outfit`. The backend verifies the Supabase JWT, loads only that user's items, maps each category to a garment template, and uses the item's `color_hex`.
  - Local development without Supabase can send `wardrobe_items` with `{wardrobe_item_id, template, label, color_hex, category}`.
  - Every successful generation is saved as the user's last avatar. The response includes `items`, `saved`, `savedAt`, and `saveError`.
  - Old generated GLBs are deleted after `GENERATED_TTL_HOURS` (default 24h) on the next job; saved avatars are never deleted by that cleanup.
- `GET /api/avatar/me` with the Supabase access token -> the last saved avatar (`found`, `targets`, `details`, `outfit`, `metrics`, signed `url`).
- `DELETE /api/avatar/me` -> remove the saved avatar.
- Auth/storage: set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the repo-root `.env`. Without them the backend runs in single-user local mode (`AUTH_ENABLED=False`) and saves under `backend/local_data/avatars/`.
- Apply `supabase/migrations/20261026120000_wardrobe_items.sql` and `20261026121000_user_avatars.sql`. The `avatars` Storage bucket must exist; the backend also has a Storage-metadata fallback if `public.user_avatars` has not been migrated yet.

## How a job runs

1. Request targets and details are validated (whitelist + bounds) and written to `temp/params_<id>.json` and `temp/details_<id>.json` — values are never interpolated into Python code.
2. `blender --background avatar.blend --python blender/generate_avatar.py -- --params ... --details ... --output ...` runs as a subprocess with a 300 s timeout.
3. The script sets the whitelisted MPFB `HumanObjectProperties`, runs `TargetService.reapply_macro_details`, loads the detail targets with `TargetService.load_target`, stages an export copy, bakes shape keys, and exports GLB.
4. Output is validated (non-empty, `glTF` magic bytes) in `temp/`, then moved to `DressMe UI Blueprint/public/models/generated/avatar_<id>.glb` where Vite serves it.
5. The original `public/models/avatar.glb` is never touched.

## Customize My Avatar -> MPFB parameters (v3)

The primary capture path is a **front + side photo pair**. Both photos stay in the
browser: MediaPipe Pose finds the landmarks, MediaPipe Image Segmenter extracts the
silhouettes, and the user's height scales the pixel measurements to centimetres. The
questionnaire remains as a local fallback. The measurements are mapped onto the avatar
like this:

| Capture signal | Measurement | MPFB control |
| --- | --- | --- |
| height + front silhouette | shoulder/hip/waist widths, inseam | `height`, `legLength`, `weight`, `proportions` |
| front silhouette | shoulder, upper arm, thigh | `muscle` |
| side silhouette | chest/hip depth | `torso-scale-depth`, `hip-scale-depth` detail targets |
| questionnaire / cup size | bust - underbust | `cupsize` |

The page has sliders for all eight whitelisted MPFB parameters, each `0.00`-`1.00` with
`0.50` as the neutral default: `gender age height weight muscle proportions cupsize
firmness`, plus the advanced detail-target sliders. Only values that differ from
neutral are listed in the "Will apply" preview, but all are sent. The questionnaire
estimator lives in `backend/body_scan.py` (`estimate_measurements` +
`measurements_to_targets`); the frontend photo pipeline lives in
`DressMe UI Blueprint/src/lib/bodyPhotos.ts`, `pose.ts`, and `silhouette.ts`.

The Customize page also runs one closed-loop correction pass: after generation the
backend reports the ratios the body actually achieved (`metrics`), the frontend nudges
`muscle`/`legLength`, and Blender regenerates once so the avatar tracks the captured
proportions more closely.

## Body capture (local)

The Customize page supports two capture flows:

- **Front + side photos** (primary): `analyzeBodyPhotos` runs MediaPipe Pose and the
  selfie segmenter locally, converts silhouette widths to centimetres using the entered
  height, then posts the derived measurements to the backend.
- **Questionnaire** (fallback): the eight-answer form runs entirely in
  `backend/body_scan.py`.

Backend measurement endpoints:

- `GET /api/body/status` -> `{"configured": true, "source": "local-questionnaire"}`
- `POST /api/body/questionnaire` (JSON) -> measurements + MPFB targets
- `POST /api/body/measurements` (JSON photo-derived measurements) -> MPFB targets

Both `/api/body/*` measurement endpoints return `measurements`, `targets`, `ratios`, and
`notes`. The photo path notes that mass/BMI are inferred from silhouette width and that
the side view only nudges torso/hip depth. MediaPipe analysis never leaves the browser.

## Optional GPT-4 Vision second opinion

The photo panel has a separate consent-gated button that sends both photos to the
OpenAI Chat Completions API. It returns relative observations only (narrow/average/broad,
short/average/long) plus confidence values and bounded detail-target suggestions. The
frontend merges those suggestions into the advanced detail sliders; it does not treat
them as centimetres and does not replace the MediaPipe measurements.

Configuration in the repo-root `.env`:

    OPENAI_API_KEY=sk-...
    OPENAI_VISION_MODEL=gpt-4o      # optional; falls back to LLM_MODEL
    LLM_IMAGE_DETAIL=high           # optional
    OPENAI_TIMEOUT_SECONDS=90       # optional

Endpoint:

- `POST /api/body/vision` (multipart `front`, `side`, `height_cm`) -> body shape,
  photo quality, posture, observations, suggested detail values, and notes.
- Returns `503` when `OPENAI_API_KEY` is missing; the local MediaPipe path still works.

## SciPy silhouette fitting

The photo panel can refine the initial avatar against the two photo silhouettes:

- `POST /api/avatar/optimize` starts a background job with `targets`, `details`,
  normalized front/side PNG data URLs, and `maxEvaluations` (8-96, default 36).
- `GET /api/avatar/optimize/{jobId}` returns progress, best score, and the final
  `targets`, `details`, `url`, and IoU/profile metrics.

How it works:

1. The optimizer starts from the current macro + detail sliders.
2. It runs one bounded `scipy.optimize.minimize` (`Powell`) over 4 macros +
   11 local body targets.
3. Every evaluation runs Blender once: it applies the candidate targets, exports the
   GLB, and renders transparent front/side masks in the same process.
4. Photo and rendered masks are cropped to their body bbox and normalized to a 512 px
   tall canvas before comparison, so camera distance does not dominate.
5. The objective combines front/side IoU, width-profile RMSE, and a regularization term
   that keeps values close to the starting sliders. Bounds prevent unrealistic bodies.
6. The best GLB is moved to `public/models/generated/avatar_opt_<id>.glb` and returned to
   the viewer.

A full 36-evaluation run takes roughly 3-5 minutes on this machine (~7 s per Blender
evaluation). The optimizer is a coarse fit, not an exact reconstruction: clothing,
pose, hair, and segmentation noise still limit the result.

The optimized macro targets *and* detail targets are carried into the Try On page, so
the dressed avatar is regenerated from the same personalized body rather than falling
back to macros only. The Customize page also exposes a "Download customized GLB" link.

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
