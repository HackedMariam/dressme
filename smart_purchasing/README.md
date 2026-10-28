# DressMe — Smart Purchasing Fashion Agent

Production AI fashion inference pipeline combining:
- **Computer Vision:** YOLO segmentation model (`dressme_best.pt`) & CIEDE2000 dominant color extraction.
- **Wardrobe Intelligence:** Combinatorics outfit pairing, gap analysis & XGBoost purchase classification (`xgb_purchase_model.json`).
- **Reasoning Agent:** Fine-tuned Qwen reasoning via Hugging Face Serverless API (0 GB download, 0 MB RAM overload).

---

## 🛠️ The 5 Specialized Tools

| # | Tool Name | What It Does & What It Returns |
|---|---|---|
| **1** | **`analyze_item`** | Extracts dominant color hue (via PIL) and feature embedding vector from product image using YOLO segmentation. |
| **2** | **`find_similar_items`** | Queries owned closet for duplicate pieces and calculates functional redundancy. |
| **3** | **`check_outfit_compatibility`** | Checks how many existing outfits the item pairs with. Returns: *"This item is compatible with X outfit(s) in your wardrobe (Average compatibility: Y%)"*. |
| **4** | **`analyze_wardrobe_gaps`** | Identifies wardrobe coverage priorities (essential gap, color diversity, or low-priority duplicate). |
| **5** | **`calculate_purchase_value`** | Deterministic score formula: <br>$$S = 0.30\cdot O + 0.20\cdot G + 0.20\cdot V + 0.15\cdot P + 0.15\cdot (100 - R) - \text{BudgetPenalty}$$ |

---

## 🖥️ How to Run

### ⚡ Step 1: Install Dependencies (Required Before Running)
Before running `inference.py`, you must install all project dependencies:
```bash
pip install -r requirements.txt
```
*(Optionally, copy `.env.example` to `.env` and add your free Hugging Face token `HF_TOKEN=hf_...` to enable cloud Qwen reasoning).*

---

### 🚀 Step 2: Run Autonomous Live Inference (CLI)
Runs on **any computer locally (GPU or CPU)** without heavy downloads or RAM overloads:

#### 📥 The 4 Inputs:
1. **`--image`**: Garment image (Web URL or local path). *Optional: defaults to `data/sample_camel_blazer.jpg` if omitted.*
2. **`--price`**: Candidate item price (e.g. `45.0`).
3. **`--budget`**: User's budget (e.g. `60.0`).
4. **`--prompt`**: Natural language question (e.g. `"Can I wear this to work?"`).

```bash
# Option A: From an Internet Image URL
python inference.py --image "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=500" --price 45.0 --budget 60.0 --prompt "Can I wear this to a wedding?"

# Option B: From a Local Image File
python inference.py --image "data/sample_camel_blazer.jpg" --price 80.0 --budget 100.0 --prompt "Is this suitable for office meetings?"

# Option C: Quick Test with Default Fallback Image (no --image needed)
python inference.py --price 35.0 --budget 50.0 --prompt "Should I buy this for casual wear?"

# Option D: Instant Deterministic Test (Vision + XGBoost, skips Qwen load)
python inference.py --skip-llm
```

---

### 🧪 Step 3: Run Unit & Image Tests
```bash
python test_all.py
```

### 🎨 Step 4: Run Perceptual Color Similarity Tests
```bash
python test_color_similarity.py
```
