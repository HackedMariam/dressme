"""Interactive page for trying the BO3 XGBoost ranker."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from xgboost_ranker import FEATURES, rank_gap_candidates

DEMO_MODEL_PATH = BACKEND_DIR / "models" / "bo3_gap_ranker_synthetic_demo.json"

FEATURE_HELP = {
    "coverage_deficit": "How much of this need is missing (1 = fully missing).",
    "use_frequency": "How often the user needs this item.",
    "season_relevance": "How relevant the item is to the selected season or activity.",
    "outfit_gain": "Estimated increase in compatible outfits if added.",
    "preference_match": "How well it matches the user's preferences.",
    "redundancy_score": "Duplication risk (1 = highly redundant).",
}

DEFAULT_ROWS = [
    {
        "candidate_id": "waterproof_jacket",
        "coverage_deficit": 0.90,
        "use_frequency": 0.80,
        "season_relevance": 0.95,
        "outfit_gain": 0.78,
        "preference_match": 0.76,
        "redundancy_score": 0.12,
    },
    {
        "candidate_id": "waterproof_shoes",
        "coverage_deficit": 0.82,
        "use_frequency": 0.72,
        "season_relevance": 0.88,
        "outfit_gain": 0.66,
        "preference_match": 0.82,
        "redundancy_score": 0.16,
    },
    {
        "candidate_id": "thermal_layer",
        "coverage_deficit": 0.68,
        "use_frequency": 0.55,
        "season_relevance": 0.79,
        "outfit_gain": 0.71,
        "preference_match": 0.73,
        "redundancy_score": 0.21,
    },
    {
        "candidate_id": "scarf",
        "coverage_deficit": 0.52,
        "use_frequency": 0.46,
        "season_relevance": 0.65,
        "outfit_gain": 0.38,
        "preference_match": 0.70,
        "redundancy_score": 0.48,
    },
]

st.set_page_config(page_title="BO3 XGBoost Ranker", page_icon="🧥", layout="wide")
st.title("BO3 XGBoost ranker tester")
st.write(
    "Edit possible wardrobe gaps and their BO3 feature values, then see how the "
    "ranker orders them."
)
st.warning(
    "This demo model was trained on synthetic examples. Its scores are for "
    "ordering candidates only; they are not probabilities or validated user preferences."
)

if not DEMO_MODEL_PATH.is_file():
    st.error(f"Demo model not found: {DEMO_MODEL_PATH}")
    st.stop()

with st.form("xgboost_ranker_form"):
    edited_rows = st.data_editor(
        pd.DataFrame(DEFAULT_ROWS),
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        column_config={
            "candidate_id": st.column_config.TextColumn(
                "Candidate gap", help="A short identifier for the possible missing item."
            ),
            **{
                feature: st.column_config.NumberColumn(
                    feature.replace("_", " ").title(),
                    help=FEATURE_HELP[feature],
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                    format="%.2f",
                )
                for feature in FEATURES
            },
        },
        key="xgboost_candidates_editor",
    )
    submitted = st.form_submit_button("Rank candidate gaps", type="primary")

if submitted:
    candidates = edited_rows.to_dict(orient="records")
    candidates = [
        candidate
        for candidate in candidates
        if str(candidate.get("candidate_id", "")).strip()
    ]

    if len(candidates) < 2:
        st.error("Enter at least two candidate gaps so the model can rank them.")
    else:
        try:
            ranked = rank_gap_candidates(candidates, model_path=DEMO_MODEL_PATH)
        except (TypeError, ValueError, FileNotFoundError) as error:
            st.error(f"Could not rank candidates: {error}")
        else:
            st.subheader("Ranked gaps")
            st.success(f"Top-ranked candidate: **{ranked[0]['candidate_id']}**")
            results = pd.DataFrame(ranked)[["rank", "candidate_id", "ranking_score"]]
            st.dataframe(
                results,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "rank": st.column_config.NumberColumn("Rank", format="%d"),
                    "candidate_id": st.column_config.TextColumn("Candidate gap"),
                    "ranking_score": st.column_config.NumberColumn(
                        "Ranking score", format="%.4f"
                    ),
                },
            )
            st.bar_chart(results.set_index("candidate_id")["ranking_score"])
            st.caption(
                "A higher score means the model placed the candidate higher in this "
                "list. It is not a confidence percentage."
            )
