# DressMe — Smart Purchasing Shopper Agent 🛍️👗

An autonomous, tool-augmented **AI Personal Shopper Agent** designed for the **DressMe** smart wardrobe ecosystem.

Powered by a hybrid compound architecture: **Python deterministic tools** (vision, CIEDE2000 color physics, wardrobe retrieval, combinatorial outfit generation, scoring formula) paired with **Qwen (via local Ollama)** for natural, grounded conversational reasoning.

---

## 🌟 Key Capabilities

1. **Perceptual Color Science (CIEDE2000)**:
   - Eliminates naive exact-string matching. Understands that *cream*, *ivory*, and *off-white* are closely related tints of white, while recognizing that *camel* and *white* are distinct, complementary neutrals.
   - Converts sRGB $\to$ CIEXYZ $\to$ CIELAB (D65 illuminant) and calculates human perceptual distance ($\Delta E_{00}$).
   - Color definitions are completely extensible via [`data/colors.json`](./data/colors.json).

2. **Domain-Grounded Redundancy Engine**:
   - **Cross-category safety**: Garments with similar colors but different categories (e.g., a *cream skirt* vs. an owned *white shirt*) are never classified as redundant because they serve different wardrobe roles.
   - **Subtype & style matching**: Flags genuine duplicates (e.g., buying a *cream formal shirt* when you already own a *white formal shirt*).

3. **Autonomous Checkpointing & Information Gathering**:
   - When an item has a price but the user's budget is missing, the agent autonomously pauses execution, saves a checkpoint to disk, and asks for clarification.
   - Once the user answers (e.g. *"My budget is $150"*), the agent seamlessly resumes and finishes the evaluation.

4. **Interactive GUI with 5-Star Rating**:
   - Desktop interface featuring an image file picker, auto-detection of garment attributes, 5-star visual rating (`★★★☆☆`), score breakdown, compatible outfit pairings, and dual toggle buttons for AI reasoning and deterministic fallback.

---

## 🏗️ Architecture: Compound AI System

```
                      ┌──────────────────────────────────────────────┐
                      │             EVALUATION REQUEST               │
                      │   (Garment image, category, prompt, budget)  │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │          1. VISION ATTRIBUTE EXTRACTION      │
                      │          `analyze_item` (PIL / Color)        │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │     2. WARDROBE RETRIEVAL & REDUNDANCY       │
                      │     `find_similar_items` (CIEDE2000 ΔE)      │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │        3. OUTFIT COMPATIBILITY ENGINE        │
                      │      `check_outfit_compatibility`            │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │          4. WARDROBE GAP ANALYSIS            │
                      │          `analyze_wardrobe_gaps`             │
                      └──────────────────────┬───────────────────────┘
                                             │
                           Budget missing?   │   Budget known
                       ┌─────────────────────┴───────────────────────┐
                       ▼                                             ▼
          ┌─────────────────────────┐                   ┌─────────────────────────┐
          │  PAUSE & ASK FOR INPUT  │                   │  5. DETERMINISTIC MATH  │
          │ (Save session state to  │                   │  `calculate_purchase_   │
          │ disk checkpoint)        │                   │   value` (Formula S)    │
          └─────────────────────────┘                   └────────────┬────────────┘
                                                                     │
                                                                     ▼
                                                        ┌─────────────────────────┐
                                                        │  QWEN LOCAL LLM VOICE   │
                                                        │ Synthesizes grounded    │
                                                        │ advice answering user   │
                                                        └─────────────────────────┘
```

---

## 📊 Deterministic Scoring Formula

To ensure 100% mathematical consistency without LLM hallucination, Python computes the grounded purchase score $S \in [0, 100]$:

$$S = 0.30 \cdot O + 0.20 \cdot G + 0.20 \cdot V + 0.15 \cdot P + 0.15 \cdot (100 - R) - \text{BudgetPenalty}$$

Where:
- $O$ = Outfit Compatibility Score ($0 - 100$)
- $G$ = Wardrobe Gap / Coverage Score ($0 - 100$)
- $V$ = Versatility Score ($0 - 100$)
- $P$ = Personal Style Match ($0 - 100$)
- $R$ = Closet Redundancy / Duplicate Risk ($0 - 100$)
- $\text{BudgetPenalty}$ = Penalty dynamically applied when price exceeds specified budget

**Hard Constraint**: If an exact duplicate in category, style, and color is detected ($R \ge 85$), the score is strictly capped at $\le 40/100$ and the verdict is forced to **SKIP**.

---

## 🎨 Perceptual Color Similarity Matrix

Representative perceptual distance ($\Delta E_{00}$) and normalized similarity values:

| Color Pair | Delta E ($\Delta E_{00}$) | Similarity Score | Qualitative Relationship |
| :--- | :---: | :---: | :--- |
| **White vs. Ivory** | 5.96 | **89.3%** | Closely related tints (warm white vs optical white) |
| **White vs. Cream** | 7.94 | **85.7%** | Relatively close tints (pale butter vs optical white) |
| **White vs. Off-White** | 1.94 | **96.5%** | Near indistinguishable chalky tint |
| **White vs. Camel** | 29.43 | **32.9%** | Distinct, contrasting neutrals (complementary pairing) |
| **Camel vs. Tan** | 7.54 | **86.4%** | Closely related warm brown hues |
| **Camel vs. Khaki** | 8.82 | **84.1%** | Earthy golden-brown tonal variation |
| **Navy vs. Light Blue**| 74.28 | **23.2%** | Same family ("blue"), high luminance contrast |
| **Black vs. White** | 94.36 | **3.4%** | Opposite ends of luminance space |

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) (Optional, for local LLM reasoning):
  ```bash
  ollama serve
  ollama pull qwen2.5:1.5b
  ```
  *(Note: If Ollama is not installed or offline, the agent automatically runs in rule-based fallback mode).*

### 2. Installation
```bash
cd smart_purchasing
pip install -r requirements.txt
```

### 3. Running the Desktop Application
Launch the graphical interface:
```bash
python gui_run.py
```
- Click **"Browse Image..."** to select any clothing picture.
- Adjust category, detected color, style, price, and budget.
- Click **"Evaluate with Qwen"** to see the 5-star rating, verdict, and personal shopper recommendation!

### 4. Running Benchmarks & Verification
- **Run Perceptual Color Test Suite**:
  ```bash
  python test_color_similarity.py
  ```
- **Run Color Demonstration & Scenarios**:
  ```bash
  python evaluate_colors.py
  ```
- **Run Full 15-Sample Data Science Benchmark**:
  ```bash
  python evaluate_metrics.py
  ```
- **Run Full Regression Test Suite**:
  ```bash
  python test_all.py
  ```

### 5. Running the FastAPI Web API
```bash
uvicorn main:app --reload --port 8000
```
- Interactive Swagger Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Endpoint: `POST /api/v1/purchase/evaluate`

---

## 📁 Repository Structure

```text
smart_purchasing/
├── agent.py                 # Multi-step Shopper Agent orchestrator & checkpointing
├── color_similarity.py      # CIELAB & CIEDE2000 perceptual color comparison service
├── tools.py                 # The 5 specialized tools (vision, retrieval, outfits, gaps, formula)
├── schemas.py               # Pydantic v2 domain schemas and request/response models
├── gui_run.py               # Desktop GUI application with 5-star rating & image picker
├── evaluate_colors.py       # Color comparison benchmark demonstration script
├── evaluate_metrics.py      # 15-case data science benchmark suite (Accuracy, Confusion Matrix, MAE)
├── test_color_similarity.py # Unit tests covering CIEDE2000 requirements and cross-category safety
├── test_all.py              # Main regression unit test suite
├── demo_shopper.py          # Interactive terminal CLI demo
├── main.py                  # FastAPI REST API server
├── wardrobe.csv             # 50-garment primary wardrobe dataset
├── requirements.txt         # Core dependencies
└── data/
    ├── colors.json          # Representative RGB coordinates & color family definitions
    ├── sample_wardrobe.json # JSON fallback wardrobe
    ├── test_benchmark.json  # 15 evaluation ground-truth test cases
    └── sample_camel_blazer.jpg # Sample image for quick testing
```
