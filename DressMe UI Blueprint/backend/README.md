# BO3: wardrobe gap agent

| Where | What |
|---|---|
| `api.py` | HTTP API used by the React app (`/api/bo3/*`), authenticated with the user's Supabase session |
| `agent/coverage.py` | rules: which pieces a goal needs and which are missing |
| `agent/tools.py`, `agent/wardrobe_source.py` | candidate scoring; the signed-in user's wardrobe (BO1 `items`) or the sample |
| `xgboost_ranker.py`, `agent/learning.py` | the learning-to-rank model, its CSV training, and retraining from user feedback |
| `agent/gap_agent.py` | the tool-calling LLM agent and the optional GPT styling summary |
| `agent/memory.py` | per-user feedback and conversations (SQLite, Git-ignored) |
| `fashionclip.py`, `app.py`, `pages/` | FashionCLIP embeddings and the standalone Streamlit demo |

## FashionCLIP

Official pretrained model: https://huggingface.co/patrickjohncyh/fashion-clip

Pinned model revision: `7e3ba62ce16b379a1ab479346b66f192e76f51b7`.
The download includes the original model card with its usage and licensing information.
Weights live in `backend/models/fashionclip/` and are excluded from Git.
Only the SafeTensors weights are downloaded, avoiding duplicate PyTorch/ONNX weights.

Use Python 3.11 or newer. From the repository root, using PowerShell:

```powershell
python backend/download_fashionclip.py
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python.exe -m streamlit run backend/app.py
```

The Streamlit demo lets you upload a clothing image, enter one candidate
description per line, and rank the descriptions by FashionCLIP similarity.
It runs the model locally on CPU by default. Similarity is a retrieval signal;
it does not determine whether an item is a real wardrobe gap.

Example from a Python script inside `backend/`:

```python
from fashionclip import FashionCLIPEncoder

encoder = FashionCLIPEncoder()  # CPU by default; use device="cuda" if available.
texts = encoder.encode_text(["a waterproof jacket", "a white shirt"])
images = encoder.encode_images(["path/to/garment.jpg"])
similarities = images @ texts.T
print(similarities.tolist())
```

The outputs are normalized embeddings. Their dot product measures similarity,
not outfit compatibility or whether an item is genuinely missing. The BO3
ranker below sorts gap candidates after the coverage engine has generated them.

## BO3 gap ranking

`xgboost_ranker.py` uses XGBoost Learning-to-Rank (and trains it) to order candidates that the BO3
coverage rules have already identified. It does not decide whether a gap
exists. Its feature inputs are normalized from `0` to `1`:

- `coverage_deficit`: how much of the requirement is uncovered.
- `use_frequency`: how often the user needs this context.
- `season_relevance`: how relevant the candidate is to the requested season.
- `outfit_gain`: estimated outfit increase from BO4.
- `preference_match`: match with the user's preferences.
- `redundancy_score`: duplication risk from BO2; higher means more redundant.

Copy `backend/data/bo3_ranker_feedback_template.csv` and label each candidate
shown in a user-context query. Keep the same `query_id` for candidates shown
for the same context. Use relevance labels `0` (not useful) through `3` (very
useful). Each query needs at least two candidates with different labels, and
training needs at least two query groups. Use explicit feedback where possible;
a click alone does not necessarily mean a suggestion was useful.

Train the ranker from the repository root:

```powershell
backend/.venv/Scripts/python.exe backend/xgboost_ranker.py --data backend/data/bo3_ranker_feedback.csv
```

This creates the local, Git-ignored model at
`backend/models/bo3_gap_ranker.json`. Then pass candidates generated for one
user context to the ranker:

```python
from xgboost_ranker import rank_gap_candidates

ranked = rank_gap_candidates([
    {
        "candidate_id": "rain_outerwear",
        "name": "Rain-protective outerwear",
        "coverage_deficit": 1.0,
        "use_frequency": 0.9,
        "season_relevance": 1.0,
        "outfit_gain": 0.7,
        "preference_match": 0.8,
        "redundancy_score": 0.0,
    },
    # Add the other gap candidates for this same user context.
])
```

The returned `ranking_score` is for ordering candidates, not a probability.
The ranker needs real labeled examples before it can learn meaningful
preferences; the CSV template alone is not a trained model.

The demo is a standalone local test UI; it is not connected to the existing Vite
frontend or Supabase.

When the Streamlit demo is running, open **XGBoost Ranker** from the sidebar to
edit candidate features and try the locally trained synthetic BO3 ranker.

## Goals (the activity filters)

Goals are data: `GOALS` in `agent/coverage.py`. Today: winter work, hot summer days, formal event, gym and
sport, hiking and outdoors, beach and pool, dinner or date night. To add one, add an entry there (requirements
match pieces by `category` plus `subcategories` and/or `tags` such as the `sport` occasion; use
`"season": ALL_YEAR` for an activity that does not depend on the weather), add its label to `GOAL_DESIGN` in
`src/features/wardrobegaps/WardrobeGapsPage.tsx`, and add the occasion to `occasion_frequency` in
`data/sample_profile.json`. The agent's prompt and the goal list in the UI follow `GOALS` automatically.
Keywords that turn a BO1 piece into a subcategory (`sports_top`, `leggings`, `gym_bag`…) are in
`agent/wardrobe_source.py`.

## BO3 gap agent in the React app

The agent (`agent/`) is exposed by `api.py` and shown in the frontend under
**Wardrobe Gaps** (`src/features/wardrobegaps/`) and on the Dashboard card.
Set `OPENAI_API_KEY` (or `LLM_API_KEY`) in the repository-root `.env` (a `backend/.env` still works and wins). Then, from
`DressMe UI Blueprint/`, run in two terminals:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn api:app --app-dir backend --port 8001
pnpm dev
```

Vite proxies `/api/bo3` to `http://127.0.0.1:8001` (override with `BO3_API_URL`); the rest of `/api` goes to the BO1 backend on port 8000.
`GET /api/bo3/gaps` runs the deterministic pipeline without the LLM (`interpret=true` adds a GPT
styling summary, about 5 s longer); `POST /api/bo3/chat` runs the tool-calling agent.

Every route except `/api/health` and `/api/bo3/goals` needs the signed-in user's Supabase session
(`Authorization: Bearer <token>`, sent by the React app). BO3 then loads that user's pieces from BO1's
`items` table, and keeps feedback and conversations per user. Without Supabase configured it serves the
shared demo user and `data/sample_wardrobe.json`.

## Synthetic demo model

`data/bo3_synthetic_training_demo.csv` contains invented examples for demonstrating the learning-to-rank
pipeline: 140 fictional user-context scenarios and 840 candidate gaps. Its relevance labels were generated
from a handwritten scoring formula with noise, then graded relative to the other candidates of each
scenario. No real user feedback was used.

`models/bo3_gap_ranker_synthetic_demo.json` is a real XGBoost ranker file trained on that simulated data.
It demonstrates the training and inference format only: its scores do not establish real-world accuracy
and are not a validated DressMe model. It is the model used until feedback retrains a real one.

Retrain it from the repository root:

```powershell
backend/.venv/Scripts/python.exe backend/xgboost_ranker.py `
  --data backend/data/bo3_synthetic_training_demo.csv `
  --output backend/models/bo3_gap_ranker_synthetic_demo.json
```
