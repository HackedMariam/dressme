# FashionCLIP for wardrobe gaps

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

`xgboost_ranker.py` uses XGBoost Learning-to-Rank to order candidates that the BO3
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
backend/.venv/Scripts/python.exe backend/train_bo3_ranker.py --data backend/data/bo3_ranker_feedback.csv
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

## BO3 gap agent in the React app

The agent (`agent/`) is exposed by `api.py` and shown in the frontend under
**Wardrobe Gaps** (`src/features/wardrobegaps/`) and on the Dashboard card.
Copy `backend/.env.example` to `backend/.env` and set `LLM_API_KEY`. Then, from
`DressMe UI Blueprint/`, run in two terminals:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn api:app --app-dir backend --port 8001
pnpm dev
```

Vite proxies `/api/bo3` to `http://127.0.0.1:8001` (override with `BO3_API_URL`); the rest of `/api` goes to the BO1 backend on port 8000.
`GET /api/bo3/gaps` runs the deterministic pipeline without the LLM;
`POST /api/bo3/chat` runs the tool-calling agent. The wardrobe is still
`data/sample_wardrobe.json` until it is read from BO1's `items` table.
