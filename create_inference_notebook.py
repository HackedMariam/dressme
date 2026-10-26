"""Generator script for the clean, lightweight inference-only Kaggle Notebook:
'dressme_agent_inference.ipynb'.
Loads the fine-tuned LoRA adapter directly from Hugging Face and runs autonomous inference.
"""

import json
from pathlib import Path

def build_inference_notebook():
    cells = []

    def add_md(source: str):
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in source.strip().split("\n")]
        })

    def add_code(source: str):
        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [line + "\n" for line in source.strip().split("\n")]
        })

    # =========================================================================
    # CELL 1: HEADER & INSTRUCTIONS
    # =========================================================================
    add_md(r"""# 👗 DressMe Autonomous Fashion Agent: Live Inference
### Production Agent Pipeline: YOLO Vision + Wardrobe Tools + Fine-Tuned Qwen 3B (Hugging Face)

- **Model**: Base `Qwen/Qwen2.5-3B-Instruct` + Fine-Tuned LoRA from **Hugging Face**
- **User Inputs**: Only **Image URL / Path**, **Price**, **Budget**, and **Natural Prompt** (e.g. *"Can I wear this to work?"*).
- **Auto-Inference**: Style and occasion are inferred automatically from your prompt and YOLO visual garment detection.
- **Output**: Machine-readable JSON document for downstream LLM interpretation.""")

    # =========================================================================
    # CELL 2: DEPENDENCIES & GPU SETUP
    # =========================================================================
    add_code(r"""# Step 1: Install runtime dependencies (Fast, ~40 seconds)
!pip install -q --upgrade "transformers>=4.45.0" "peft>=0.12.0" "bitsandbytes>=0.43.0" "accelerate>=0.34.0" ultralytics xgboost opencv-python pydantic

import os
import re
import json
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import torch
import numpy as np
from PIL import Image

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device.upper()} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})")
if torch.cuda.is_available():
    print(f"VRAM:   {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")""")

    # =========================================================================
    # CELL 3: LOAD PROJECT TOOLS & ASSETS
    # =========================================================================
    add_code(r"""# Step 2: Resolve Project Assets & Import Domain Tools
import sys

def resolve_path(rel_name: str) -> Path:
    known_roots = [
        Path("/kaggle/input/datasets/meriemgharbi123/smart-purchasing/smart_purchasing"),
        Path("/kaggle/input/datasets/meriemgharbi123/smart-purchasing"),
        Path("/kaggle/input/smart-purchasing/smart_purchasing"),
        Path("/kaggle/input/smart-purchasing"),
        Path("/kaggle/working/smart_purchasing"),
        Path("/kaggle/working"),
        Path("/content/dressme/smart_purchasing"),
        Path("/content/smart_purchasing"),
        Path("/content"),
        Path("smart_purchasing"),
        Path("."),
    ]
    for root in known_roots:
        target = root / rel_name
        if target.exists():
            return target.resolve()
    if Path("/kaggle/input").exists():
        for match in Path("/kaggle/input").rglob(Path(rel_name).name):
            if str(match).replace("\\", "/").endswith(rel_name.replace("\\", "/")):
                return match.resolve()
    if Path("/content").exists():
        for match in Path("/content").rglob(Path(rel_name).name):
            if str(match).replace("\\", "/").endswith(rel_name.replace("\\", "/")):
                return match.resolve()
    return Path(rel_name).resolve()

WARDROBE_PATH = resolve_path("wardrobe.csv")
PROJECT_DIR   = WARDROBE_PATH.parent

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Import your real domain tools directly from the project
from schemas import CandidateItem, Garment
from color_similarity import ColorSimilarityService, compare_colors
from ml_model import predict_purchase_ml
from tools import (
    find_similar_items,
    check_outfit_compatibility,
    analyze_wardrobe_gaps,
    calculate_purchase_value,
    analyze_item,
)
from agent import PurchaseAgent

# Initialize wardrobe repository
wardrobe_loader = PurchaseAgent(wardrobe_file=str(WARDROBE_PATH))
WARDROBE_GARMENTS = wardrobe_loader.wardrobe
print(f"Loaded {len(WARDROBE_GARMENTS)} wardrobe garments from {WARDROBE_PATH.name}")
print(f"Imported tools from: {PROJECT_DIR}")""")

    # =========================================================================
    # CELL 4: LOAD FINE-TUNED MODEL FROM HUGGING FACE
    # =========================================================================
    add_code(r"""# Step 3: Load Fine-Tuned Agent from Hugging Face
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

# =============================================================================
# 🔑 HUGGING FACE REPOSITORY (Public, 0 secrets needed):
# =============================================================================
HF_LORA_REPO = "meriemgharbi123/dressme_qwen3b_lora"
BASE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

if torch.cuda.is_available():
    print(f"1. GPU Detected ({torch.cuda.get_device_name(0)}). Loading Base Model in 4-bit...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True
    )
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True
    )
else:
    print("1. Running on CPU. Loading Base Model in float32...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        torch_dtype=torch.float32,
        device_map={"": "cpu"},
        trust_remote_code=True
    )

print(f"2. Attaching Fine-Tuned LoRA Adapter from: {HF_LORA_REPO}...")
try:
    agent_model = PeftModel.from_pretrained(base_model, HF_LORA_REPO)
    print("Successfully attached your Hugging Face fine-tuned LoRA adapter!")
except Exception as e:
    print(f"Notice: Could not load from '{HF_LORA_REPO}' ({e}). Falling back to local adapter if available...")
    local_lora = resolve_path("dressme_qwen3b_lora")
    if local_lora.exists():
        agent_model = PeftModel.from_pretrained(base_model, str(local_lora))
        print("Loaded local LoRA adapter successfully.")
    else:
        agent_model = base_model
        print("Using base model directly.")""")

    # =========================================================================
    # CELL 5: AUTONOMOUS AGENT PIPELINE & INTENT PARSER
    # =========================================================================
    add_code(r'''# Step 4: Autonomous Agent Pipeline & Natural Language Intent Parser

SYSTEM_PROMPT = (
    "You are DressMe Shopping Assistant, an expert AI fashion and wardrobe consultant. "
    "Evaluate whether the user should buy the proposed clothing item based on their wardrobe, "
    "preferences, tool results, and budget. Return ONLY a valid JSON object with fields: "
    "decision (BUY, DON'T BUY, CONSIDER), score (0-100), reasons (list), and uncertainties (list)."
)

OCCASION_KEYWORDS = {
    "work": ("work", ["formal", "smart_casual"]),
    "office": ("work", ["formal", "smart_casual"]),
    "meeting": ("work", ["formal", "smart_casual"]),
    "business": ("work", ["formal", "smart_casual"]),
    "formal": ("formal_event", ["formal"]),
    "wedding": ("formal_event", ["formal", "evening"]),
    "dinner": ("dinner", ["smart_casual", "formal"]),
    "date": ("dinner", ["smart_casual"]),
    "party": ("party", ["party", "evening"]),
    "casual": ("casual_outing", ["casual"]),
    "weekend": ("casual_outing", ["casual"]),
    "everyday": ("casual_outing", ["casual"]),
    "gym": ("gym", ["sporty"])
}

def infer_occasion_and_style(user_prompt: str, detected_category: str) -> Tuple[str, List[str]]:
    """Infers occasion and style from the user's natural prompt, falling back to garment defaults."""
    prompt_lower = user_prompt.lower()
    for kw, (occ, styles) in OCCASION_KEYWORDS.items():
        if re.search(r'\b' + kw + r'\b', prompt_lower):
            return occ, styles

    # Fallback based on category
    cat = detected_category.lower().replace("-", "_")
    if cat in ["jacket", "blazer", "coat"]:
        return "work", ["formal", "smart_casual"]
    if cat in ["dress"]:
        return "dinner", ["formal", "evening"]
    return "casual_outing", ["casual"]

def evaluate_clothing_request(
    image_path: str,
    price: float,
    budget: float,
    user_prompt: str = "Should I buy this?"
) -> str:
    """
    Autonomous Fashion Agent:
    1. Downloads image if web URL
    2. Runs YOLO segmentation + CIEDE2000 dominant color
    3. Infers occasion & style from user prompt automatically
    4. Executes wardrobe combinatorics, duplicate check & XGBoost tools
    5. Fine-tuned Qwen 3B reasons over findings and outputs clean JSON
    """
    # 1. Download image if URL
    local_image = str(image_path)
    if local_image.startswith("http://") or local_image.startswith("https://"):
        import tempfile
        local_image = os.path.join(tempfile.gettempdir(), "downloaded_garment.jpg")
        req = urllib.request.Request(image_path, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(local_image, "wb") as f:
            f.write(resp.read())

    # 2. Computer Vision Analysis (YOLO segmentation + CIEDE2000)
    cand = CandidateItem(category="unknown", image_path=local_image, price=price, budget=budget)
    vision_data = analyze_item(cand)
    category = vision_data.get("category", "top")
    color = vision_data.get("color", "black")

    # 3. Automatically infer occasion and style from the natural prompt
    occasion, styles = infer_occasion_and_style(user_prompt, category)
    cand.category = category
    cand.color = color
    cand.target_occasion = occasion
    cand.style = styles

    # 4. Execute Domain Tools
    sims = find_similar_items(cand, WARDROBE_GARMENTS, top_k=3)
    top_sim = sims[0].similarity_score if sims else 0.0
    redundancy_pct = round(top_sim * 100.0, 1)

    outfits = check_outfit_compatibility(cand, WARDROBE_GARMENTS, target_occasion=occasion)
    comp_count = outfits.get("compatible_count", 0)
    avg_score = outfits.get("average_score", 70.0)

    # Extract paired garment IDs and detailed outfit combinations
    matching_outfits = []
    paired_item_ids = []
    outfit_desc_lines = []
    for combo in outfits.get("combinations", []):
        combo_items = []
        item_labels = []
        for g in combo.paired_garments:
            combo_items.append({
                "item_id": g.id,
                "name": g.name,
                "category": g.category,
                "color": g.color
            })
            if g.id not in paired_item_ids:
                paired_item_ids.append(g.id)
            item_labels.append(f"{g.id} ({g.name})")
        matching_outfits.append({
            "outfit_id": combo.outfit_id,
            "description": combo.description,
            "compatibility_score": combo.compatibility_score,
            "paired_items": combo_items
        })
        outfit_desc_lines.append(f"{combo.outfit_id}: " + " + ".join(item_labels))

    paired_ids_str = ", ".join(paired_item_ids) if paired_item_ids else "None"
    outfit_summary = "; ".join(outfit_desc_lines) if outfit_desc_lines else "None"

    gap_res = analyze_wardrobe_gaps(cand, WARDROBE_GARMENTS)
    gap_score = gap_res.gap_fill_score

    penalty = min(25.0, round(((price - budget) / budget) * 20.0, 2)) if budget > 0 and price > budget else 0.0

    ml_res = predict_purchase_ml(
        outfit_compatibility=avg_score,
        wardrobe_gap=gap_score,
        redundancy=redundancy_pct,
        versatility=min(100.0, 50.0 + comp_count * 15.0),
        style_match=80.0,
        budget_penalty=penalty
    )

    val_res = calculate_purchase_value(
        outfit_compatibility_score=avg_score,
        wardrobe_gap_score=gap_score,
        versatility_score=min(100.0, 50.0 + comp_count * 15.0),
        personal_style_score=80.0,
        redundancy_score=redundancy_pct,
        price=price,
        budget=budget,
        ml_decision=ml_res["ml_decision"],
        ml_confidence=ml_res["confidence"]
    )

    # 5. Formulate Context for Fine-Tuned Qwen 3B
    scenario_prompt = (
        f"Scenario ID: IMG-{int(time.time())%10000}\n"
        f"Proposed Item: {color.title()} {category.title()} (Image Analysis), Price: ${price:.0f}, Style: {', '.join(styles)}\n"
        f"User Budget: ${budget:.0f}, Preferred Style: {', '.join(styles)}\n"
        f"User Question: \"{user_prompt}\"\n"
        f"Category Evaluation Focus: autonomous_full_loop\n"
        f"Wardrobe Context: User has {len(WARDROBE_GARMENTS)} items in wardrobe.\n"
        f"Tool analysis: Redundancy={redundancy_pct}%, Outfits={comp_count}.\n"
        f"Matching Outfits in Wardrobe: {outfit_summary}\n"
        f"Compatible Garment IDs: [{paired_ids_str}]\n"
        f"GapScore={gap_score:.1f}, CalculatedScore={val_res.overall_score:.1f}, ML_Decision={ml_res['ml_decision']}.\n"
        f"Instruction: In your reasons, cite the exact item IDs (e.g. {paired_ids_str}) of the clothes that pair into complete outfits."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": scenario_prompt}
    ]
    prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt_text, return_tensors="pt").to(agent_model.device)

    with torch.no_grad():
        outputs = agent_model.generate(
            **inputs,
            max_new_tokens=180,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id
        )

    raw_response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()

    # Parse JSON from model
    cleaned = raw_response
    if "```" in cleaned:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if m: cleaned = m.group(1).strip()
    m = re.search(r"(\{[\s\S]*\})", cleaned)
    if m: cleaned = m.group(1).strip()
    try:
        agent_output = json.loads(cleaned)
    except Exception:
        agent_output = {"decision": val_res.decision.value, "score": val_res.overall_score, "reasons": [raw_response], "uncertainties": []}

    # 6. Structured JSON Document for Downstream LLM
    final_payload = {
        "status": "success",
        "user_query": user_prompt,
        "candidate_item": {
            "image_source": str(image_path),
            "detected_category": category,
            "detected_color": color,
            "inferred_occasion": occasion,
            "inferred_style": styles,
            "price": price,
            "budget": budget
        },
        "tool_evidence": {
            "redundancy_score": redundancy_pct,
            "closest_wardrobe_match": sims[0].garment.name if sims else None,
            "compatible_outfits_count": comp_count,
            "matching_wardrobe_item_ids": paired_item_ids,
            "matching_outfits": matching_outfits,
            "wardrobe_gap_score": gap_score,
            "xgboost_prediction": ml_res["ml_decision"],
            "xgboost_confidence": ml_res["confidence"],
            "deterministic_score": val_res.overall_score,
            "budget_penalty": penalty
        },
        "agent_verdict": {
            "decision": agent_output.get("decision", val_res.decision.value),
            "score": agent_output.get("score", val_res.overall_score),
            "matching_item_ids": paired_item_ids,
            "reasons": agent_output.get("reasons", []),
            "uncertainties": agent_output.get("uncertainties", [])
        }
    }

    return json.dumps(final_payload, indent=2)

print("Autonomous Agent Pipeline ready.")''')

    # =========================================================================
    # CELL 6: INTERACTIVE TESTER (ONLY 4 INPUTS)
    # =========================================================================
    add_code(r"""# Step 5: Interactive Testing Playground (Runs in ~3 seconds)
# You only need: Image URL or Path, Price, Budget, and your Natural Question!

result_json = evaluate_clothing_request(
    image_path="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQuFucmwpSu49mBKKfTp4NJHMMZsKI9YuuM16xSn2Fmt15lRUCez5qvMy0&s=10",
    price=35.0,
    budget=50.0,
    user_prompt="Should I buy this black t-shirt for casual weekend wear?"
)

print(result_json)""")

    # Save notebook
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"codemirror_mode": {"name": "ipython", "version": 3}, "file_extension": ".py", "mimetype": "text/x-python", "name": "python", "nbconvert_exporter": "python", "pygments_lexer": "ipython3", "version": "3.10.12"}
        },
        "nbformat": 4,
        "nbformat_minor": 5
    }

    dest_paths = [
        Path(__file__).resolve().parent / "dressme_agent_inference.ipynb",
        Path(__file__).resolve().parent / "smart_purchasing" / "dressme_agent_inference.ipynb"
    ]

    for p in dest_paths:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
        print(f"Saved inference notebook to: {p}")

if __name__ == "__main__":
    build_inference_notebook()
