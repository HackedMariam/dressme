"""FashionCLIP second opinion on the coverage rules.

The rules in coverage.py stay the source of truth. This check asks, for every owned item,
which garment description it is closest to, and flags requirements where FashionCLIP and
the rules disagree (e.g. a mis-tagged coat the rules do not see).
"""

from typing import Any, Callable, Sequence

from .coverage import GOALS

# Raw text-text cosines are noisy (everything scores 0.5-0.85), so an item is assigned to its
# best label among many instead of being compared with a fixed threshold per requirement.
MIN_SIMILARITY = 0.6
MIN_MARGIN = 0.02

GENERIC_LABELS = [
    "a t-shirt", "a pair of jeans", "a dress", "a skirt", "a handbag", "sneakers", "sunglasses",
    "a scarf", "a belt", "a leather jacket", "a blazer", "a hoodie", "a cardigan",
    "a pair of shorts", "sandals", "a watch", "a necklace",
]


def _labels(goal_id: str) -> list[str]:
    """Goal requirements first, then every other goal's pieces and generic garments as distractors."""
    labels = [r["description"] for r in GOALS[goal_id]["requirements"]]
    others = [r["description"] for g in GOALS.values() for r in g["requirements"]]
    return list(dict.fromkeys(labels + others + GENERIC_LABELS))


def semantic_review(
    goal_id: str,
    wardrobe: Sequence[dict[str, Any]],
    coverage: dict[str, Any],
    encoder: Any,
    describe: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    """Compare FashionCLIP's item assignment with the rule-based coverage of one goal."""
    goal = GOALS[goal_id]
    labels = _labels(goal_id)
    label_vectors = encoder.encode_text(labels)
    item_vectors = encoder.encode_text([describe(item) for item in wardrobe])
    scores = item_vectors @ label_vectors.T

    assigned: dict[str, list[dict[str, Any]]] = {r["description"]: [] for r in goal["requirements"]}
    for item, row in zip(wardrobe, scores.tolist()):
        order = sorted(range(len(labels)), key=row.__getitem__, reverse=True)
        best, runner_up = row[order[0]], row[order[1]]
        label = labels[order[0]]
        if label in assigned and best >= MIN_SIMILARITY and best - runner_up >= MIN_MARGIN:
            assigned[label].append({"item": item, "similarity": round(best, 4)})

    rule_gaps = {c["candidate_id"] for c in coverage["candidates"]}
    rule_matches = {c["candidate_id"]: c["matched_items"] for c in coverage["covered"] + coverage["candidates"]}
    findings = []
    for requirement in goal["requirements"]:
        season_ok = [
            m for m in assigned[requirement["description"]]
            if not requirement.get("check_season", True) or goal["season"] in m["item"].get("seasons", [])
        ]
        names = [m["item"]["name"] for m in season_ok]
        if requirement["id"] in rule_gaps and names:
            verdict = "possible_false_gap"
        elif requirement["id"] not in rule_gaps and not names:
            verdict = "weak_coverage"
        else:
            continue
        findings.append(
            {
                "candidate_id": requirement["id"],
                "name": requirement["name"],
                "verdict": verdict,
                "rule_items": rule_matches[requirement["id"]],
                "fashionclip_items": names,
                "best_similarity": max((m["similarity"] for m in season_ok), default=None),
            }
        )
    return {"method": "fashionclip", "disagreements": findings}
