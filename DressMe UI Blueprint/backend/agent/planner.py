"""Shopping planner: from a goal and a budget to an ordered list of purchases that close the most needs.

This is the agentic layer on top of the Wardrobe Gaps rules. It reuses what already exists (coverage rules, the
learning-to-rank model, the user's "I need this / Not relevant" answers) and adds the three things the single-context
view cannot do:

    1. PLAN     a language model reads the user's goal in plain words and picks which contexts matter and the budget.
    2. COMBINE  a deterministic optimiser looks for the pieces that close needs in SEVERAL contexts at once (one
                leather jacket can serve a dinner and a sport warm-up) and picks them by gain per dinar.
    3. COMPARE  the plan is measured against the simple method (the first gap of each context) with the same rules.

The language model never decides what is missing and never changes a score: the rules do, as before. It only reads
the request and phrases the result. Without a key, or when it fails, defaults and a fixed sentence are used, so the
plan always works.

Token budget: at most TWO small requests per run (read the goal, phrase the summary), none when the user left the
goal empty, and results are cached for ten minutes.
"""

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable

from xgboost_ranker import rank_gap_candidates

from .coverage import ALL_YEAR, GOALS, compute_coverage, get_requirement
from .learning import active_model_path
from .memory import AgentMemory
from .tools import load_profile, load_wardrobe, score_candidates, source_info

logger = logging.getLogger("dressme.bo3.planner")

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
TIMEOUT_SECONDS = 15
DEFAULT_MAX_ITEMS = 6
HARD_MAX_ITEMS = 8
MAX_BUDGET_TND = 100_000
CACHE_SECONDS = 600
CACHE_ENTRIES = 64
PRICE_NOTE = "Prices are estimated ranges for a mid-range Tunisian shop, not live shop prices."

# Estimated price range (TND) per subcategory, with a default per category. Honest estimates, labelled as such.
CATEGORY_PRICE = {"top": (30, 90), "bottom": (50, 140), "dress": (80, 250), "outerwear": (150, 450),
                  "shoes": (90, 300), "accessory": (20, 120), "other": (40, 120)}
SUBCATEGORY_PRICE = {
    "coat": (250, 600), "parka": (200, 500), "puffer": (180, 450), "trench": (180, 420), "rain_jacket": (100, 250),
    "windbreaker": (80, 200), "track_jacket": (70, 160), "fleece": (60, 150), "hoodie": (50, 120), "blazer": (150, 380),
    "suit_jacket": (350, 900), "denim_jacket": (100, 240), "leather_jacket": (300, 800), "bomber_jacket": (100, 250),
    "light_jacket": (90, 220), "sneakers": (100, 300), "hiking_boots": (150, 400), "boots": (150, 400),
    "ankle_boots": (130, 350), "heels": (90, 250), "pumps": (90, 250), "sandals": (50, 160), "espadrilles": (40, 100),
    "slides": (25, 70), "loafers": (120, 300), "derbies": (150, 350), "oxfords": (150, 350), "socks": (10, 35),
    "tights": (10, 40), "gloves": (25, 90), "scarf": (25, 100), "umbrella": (15, 50), "belt": (30, 120), "hat": (25, 80),
    "cap": (25, 70), "sunglasses": (40, 200), "tote": (60, 200), "clutch": (50, 180), "evening_bag": (60, 200),
    "backpack": (60, 200), "gym_bag": (50, 150), "beach_bag": (30, 90), "headband": (8, 25), "tie": (30, 100),
    "jewelry": (30, 200), "swimwear": (40, 120), "sports_top": (25, 70), "t-shirt": (20, 60), "leggings": (35, 100),
    "shorts": (30, 80), "joggers": (40, 100), "evening_dress": (150, 450), "cocktail_dress": (120, 320),
}
# French names used ONLY to search Tunisian shops (the shops are indexed in French). The browser never sends text.
SUBCATEGORY_FR = {
    "coat": "manteau en laine", "parka": "parka", "puffer": "doudoune", "trench": "trench", "rain_jacket": "veste imperméable",
    "windbreaker": "veste coupe-vent", "track_jacket": "veste de survêtement", "fleece": "pull polaire", "hoodie": "sweat à capuche",
    "blazer": "blazer", "suit_jacket": "veste de costume", "denim_jacket": "veste en jean", "leather_jacket": "veste en cuir",
    "bomber_jacket": "bomber", "light_jacket": "veste légère", "sneakers": "baskets", "hiking_boots": "chaussures de randonnée",
    "boots": "bottes", "ankle_boots": "bottines", "heels": "chaussures à talons", "pumps": "escarpins", "sandals": "sandales",
    "espadrilles": "espadrilles", "slides": "claquettes", "loafers": "mocassins", "derbies": "chaussures derby",
    "oxfords": "chaussures richelieu", "socks": "chaussettes", "tights": "collants", "gloves": "gants hiver",
    "scarf": "écharpe", "umbrella": "parapluie", "belt": "ceinture en cuir", "hat": "chapeau", "cap": "casquette",
    "sunglasses": "lunettes de soleil", "tote": "sac cabas", "clutch": "pochette de soirée", "evening_bag": "pochette de soirée",
    "backpack": "sac à dos", "gym_bag": "sac de sport", "beach_bag": "sac de plage", "headband": "bandeau de sport",
    "tie": "cravate", "jewelry": "bijoux", "swimwear": "maillot de bain", "sports_top": "t-shirt de sport",
    "t-shirt": "t-shirt", "leggings": "legging", "shorts": "short", "joggers": "jogging", "evening_dress": "robe de soirée",
    "cocktail_dress": "robe cocktail", "linen_trousers": "pantalon en lin", "linen_shirt": "chemise en lin",
    "tank_top": "débardeur", "skirt": "jupe", "trousers": "pantalon", "chinos": "chino", "blouse": "blouse", "shirt": "chemise",
    "sweater": "pull", "cardigan": "gilet", "turtleneck": "pull col roulé", "polo": "polo", "jeans": "jean",
}

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_runs: dict[str, list[float]] = {}
MAX_RUNS_PER_MINUTE = 8


class RateLimited(Exception):
    pass


def check_rate(user_id: str) -> None:
    """A run costs up to two model requests: a user cannot start more than a few per minute."""
    now = time.time()
    with _lock:
        recent = [t for t in _runs.get(user_id, []) if now - t < 60]
        if len(recent) >= MAX_RUNS_PER_MINUTE:
            raise RateLimited("Too many plans in a minute, please wait a little.")
        _runs[user_id] = [*recent, now]


def price_range(category: str, subcategory: str) -> tuple[int, int]:
    return SUBCATEGORY_PRICE.get(subcategory) or CATEGORY_PRICE.get(category, (40, 150))


def piece_name(category: str, subcategory: str) -> str:
    return (subcategory or category).replace("_", " ").capitalize()


def shop_search_text(category: str, subcategory: str) -> str | None:
    """The French words to look for in Tunisian shops, or None when the piece is not in the catalogue above."""
    return SUBCATEGORY_FR.get(subcategory)


# --- the language model (two small, optional requests) ---------------------------------------------------------

def llm_enabled() -> bool:
    if os.getenv("BO3_LLM_PLANNER", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _chat(prompt: str, max_tokens: int, json_mode: bool) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL), timeout=TIMEOUT_SECONDS, max_retries=1)
    kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}} if json_mode else {}
    reply = client.chat.completions.create(model=os.getenv("LLM_MODEL", DEFAULT_MODEL), temperature=0, max_tokens=max_tokens,
                                           messages=[{"role": "user", "content": prompt}], **kwargs)
    return reply.choices[0].message.content or ""


def read_goal(objective: str) -> dict[str, Any] | None:
    """The user's words -> {"goals": [ids], "budget_tnd": number|None, "max_items": int|None, "rationale": str}.
    Only values that pass validation are kept. None when the model is unavailable or answers badly."""
    if not (objective.strip() and llm_enabled()):
        return None
    contexts = {goal_id: f"{goal['label']} ({goal['season']})" for goal_id, goal in GOALS.items()}
    prompt = (
        "A user wants to plan clothing purchases. Read their goal and choose which of these contexts matter.\n"
        f"Contexts: {json.dumps(contexts)}\n"
        f"User goal (any language): {json.dumps(objective.strip()[:300])}\n"
        'Reply as JSON only: {"goals": ["context_id"], "budget_tnd": number or null, "max_items": integer or null, '
        '"rationale": "one short sentence in the user\'s language"}. Use only the context ids above. '
        "budget_tnd is only a budget the user wrote (Tunisian dinars), otherwise null."
    )
    try:
        data = json.loads(_chat(prompt, 180, json_mode=True))
    except Exception as error:
        logger.warning("planner could not read the goal: %s: %s", type(error).__name__, str(error)[:120])
        return None
    goals = [g for g in data.get("goals", []) if g in GOALS] if isinstance(data.get("goals"), list) else []
    budget = data.get("budget_tnd")
    budget = float(budget) if isinstance(budget, (int, float)) and not isinstance(budget, bool) and 0 < budget <= MAX_BUDGET_TND else None
    items = data.get("max_items")
    items = items if isinstance(items, int) and not isinstance(items, bool) and 1 <= items <= HARD_MAX_ITEMS else None
    rationale = " ".join(str(data.get("rationale") or "").split())[:200]
    return {"goals": list(dict.fromkeys(goals)), "budget_tnd": budget, "max_items": items, "rationale": rationale}


def write_summary(plan: dict[str, Any], objective: str) -> str | None:
    """Two sentences that phrase the numbers of the plan. The model gets the result, never the wardrobe."""
    if not (objective.strip() and llm_enabled() and plan["purchases"]):
        return None    # no goal written: nothing to phrase back, the fixed sentence is enough
    facts = {
        "purchases": [{"piece": p["name"], "estimated_tnd": p["price_tnd"]["estimate"], "closes_needs": len(p["closes"]),
                       "contexts": sorted({c["goal_label"] for c in p["closes"]})} for p in plan["purchases"]],
        "total_tnd": plan["totals"]["estimated_cost"], "budget_tnd": plan["budget_tnd"],
        "needs_closed": plan["totals"]["needs_closed"], "simple_method_closes": plan["baseline"]["needs_closed"],
    }
    prompt = (
        "Write 2 short sentences (max 55 words) presenting this shopping plan to the user, with a friendly stylist "
        "tone. Use ONLY these facts, invent nothing, mention that prices are estimates. Reply in the language of the "
        f"user's goal (default English).\nUser goal: {json.dumps(objective.strip()[:200])}\nFacts: {json.dumps(facts)}"
    )
    try:
        text = " ".join(_chat(prompt, 160, json_mode=False).split())
    except Exception as error:
        logger.warning("planner could not phrase the summary: %s: %s", type(error).__name__, str(error)[:120])
        return None
    return text[:500] or None


def template_summary(plan: dict[str, Any]) -> str:
    totals, base = plan["totals"], plan["baseline"]
    if not plan["purchases"]:
        return plan.get("note") or "Nothing to buy for these contexts."
    return (f"{totals['pieces']} piece{'s' if totals['pieces'] != 1 else ''} for about {totals['estimated_cost']} TND close "
            f"{totals['needs_closed']} needs, against {base['needs_closed']} with the simple one-gap-per-context method. "
            "Prices are estimates.")


# --- the optimiser (deterministic) ------------------------------------------------------------------------------

def _gap_weights(ranked: list[dict[str, Any]], labels: dict[tuple[str, str], int], goal: str) -> dict[str, float]:
    """Importance of each open need: 1.5 for the best-ranked down to 0.5 for the last; x1.5 if the user said "I need
    this"; dropped if they said "Not relevant"."""
    weights = {}
    for gap in ranked:
        label = labels.get((goal, gap["candidate_id"]))
        if label == 0:
            continue
        weight = 1.5 - (gap["rank"] - 1) / max(1, len(ranked) - 1) if len(ranked) > 1 else 1.0
        weights[gap["candidate_id"]] = weight * (1.5 if label == 3 else 1.0)
    return weights


def _open_needs(user_id: str, goals: list[str], wardrobe, profile, labels) -> list[dict[str, Any]]:
    """Every open need of the chosen contexts, with what could close it and how much it matters."""
    department = profile.get("department")
    model = active_model_path(user_id)
    needs: list[dict[str, Any]] = []
    for goal in goals:
        coverage = compute_coverage(wardrobe, goal, department)
        if not coverage["candidates"]:
            continue
        ranked = rank_gap_candidates(score_candidates(goal, coverage["candidates"], wardrobe, profile), model_path=model)
        weights = _gap_weights(ranked, labels, goal)
        season = GOALS[goal]["season"]
        for gap in ranked:
            if gap["candidate_id"] not in weights:
                continue
            requirement = get_requirement(goal, gap["candidate_id"], department)
            options = []
            for condition in requirement["match"]:
                for sub in condition.get("subcategories") or [""]:
                    options.append((condition["category"], sub))
            needs.append({
                "goal": goal, "goal_label": GOALS[goal]["label"], "candidate_id": gap["candidate_id"], "name": gap["name"],
                "season": None if season == ALL_YEAR else season, "weight": weights[gap["candidate_id"]],
                "remaining": max(1, gap["required_count"] - gap["owned_count"]), "options": list(dict.fromkeys(options)),
            })
    return needs


def _covers(piece: tuple[str, str, str | None], need: dict[str, Any]) -> bool:
    """A piece bought for a season serves the needs of that season and the all-year ones."""
    category, sub, season = piece
    return (category, sub) in need["options"] and (need["season"] is None or need["season"] == season)


def _pieces(needs: list[dict[str, Any]]) -> list[tuple[str, str, str | None]]:
    return list(dict.fromkeys((c, s, need["season"]) for need in needs for c, s in need["options"]))


def _gain(piece, needs, remaining) -> tuple[float, list[dict[str, Any]]]:
    """Importance moved forward by this piece: a share of each need it advances (a need of 3 pairs of socks moves by a
    third), plus a bonus when it closes the need, so closing needs beats starting many."""
    hit = [n for n in needs if remaining[id(n)] > 0 and _covers(piece, n)]
    gain = sum(n["weight"] / n["remaining"] + (0.5 * n["weight"] if remaining[id(n)] == 1 else 0) for n in hit)
    return gain, hit


def _cost(piece) -> float:
    low, high = price_range(piece[0], piece[1])
    return (low + high) / 2


def optimise(needs: list[dict[str, Any]], budget: float | None, max_items: int,
             first: Callable[[list[dict[str, Any]]], list[tuple[str, str, str | None]]] | None = None,
             per_dinar: bool = True) -> list[dict[str, Any]]:
    """Greedy choice of pieces by gain per dinar (by gain alone without a budget or with per_dinar=False). `first`
    forces the pieces of the simple method so both are measured with the same rules."""
    remaining = {id(n): n["remaining"] for n in needs}
    left, chosen = budget, []
    candidates = _pieces(needs)
    forced = list(first(needs)) if first else None
    while len(chosen) < max_items:
        best = None
        for piece in (forced if forced is not None else candidates):
            gain, hit = _gain(piece, needs, remaining)
            cost = _cost(piece)
            if gain <= 0 or (left is not None and cost > left):
                continue
            score = (gain / cost if (budget is not None and per_dinar) else gain, -cost)
            if best is None or score > best[0]:
                best = (score, piece, hit, cost, gain)
        if best is None:
            break
        _, piece, hit, cost, gain = best
        for need in hit:
            remaining[id(need)] -= 1
        chosen.append({"piece": piece, "cost": cost, "hit": hit, "done": [n for n in hit if remaining[id(n)] == 0],
                       "gain": round(gain, 2)})
        if left is not None:
            left -= cost
        if forced is not None:
            forced.remove(piece)
    return chosen


def best_plan(needs: list[dict[str, Any]], budget: float | None, max_items: int) -> list[dict[str, Any]]:
    """The better of two greedy strategies (cheapest gain first, biggest gain first): more needs closed, then more
    importance moved, then a lower cost. A greedy rule alone can be beaten on a tight budget by the other one."""
    options = [optimise(needs, budget, max_items, per_dinar=True)]
    if budget is not None:
        options.append(optimise(needs, budget, max_items, per_dinar=False))
    return max(options, key=lambda chosen: (len({id(n) for s in chosen for n in s["done"]}),
                                            sum(s["gain"] for s in chosen), -sum(s["cost"] for s in chosen)))


def _simple_method(needs: list[dict[str, Any]]) -> list[tuple[str, str, str | None]]:
    """What a user would do without the planner: the first piece listed for the first open need of each context."""
    pieces, seen = [], set()
    for need in needs:
        if need["goal"] in seen:
            continue
        seen.add(need["goal"])
        category, sub = need["options"][0]
        pieces.append((category, sub, need["season"]))
    return pieces


def _totals(chosen: list[dict[str, Any]], needs_total: int) -> dict[str, Any]:
    closed = {id(n) for step in chosen for n in step["done"]}
    return {"pieces": len(chosen), "estimated_cost": round(sum(s["cost"] for s in chosen)), "needs_closed": len(closed),
            "needs_open_before": needs_total}


# --- the run ----------------------------------------------------------------------------------------------------

def _fingerprint(user_id: str, wardrobe, labels) -> str:
    raw = json.dumps([user_id, sorted(i["id"] for i in wardrobe), sorted((g, c, v) for (g, c), v in labels.items())])
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def run_plan(memory: AgentMemory, user_id: str, objective: str = "", budget_tnd: float | None = None,
             goals: list[str] | None = None) -> dict[str, Any]:
    """The whole agent run. `steps` lists what was really done, in order, for the interface to play back."""
    objective = " ".join((objective or "").split())[:300]
    wardrobe, profile, source = load_wardrobe(user_id), load_profile(user_id), source_info(user_id)
    labels = {(r["goal"], r["candidate_id"]): r["relevance"] for r in memory.list_feedback(user_id)}
    cache_key = json.dumps([_fingerprint(user_id, wardrobe, labels), objective.lower(), budget_tnd, sorted(goals or [])])
    with _lock:
        hit = _cache.get(cache_key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return {**hit[1], "cached": True}

    if source["source"] in ("empty", "error"):     # nothing to analyse: no need to read the goal, so no model request
        return {"objective": objective, "budget_tnd": budget_tnd, "max_items": DEFAULT_MAX_ITEMS, "plan_source": "default",
                "rationale": "", "goals": [], "wardrobe_source": source, "department": profile.get("department"),
                "price_note": PRICE_NOTE, "cached": False, "purchases": [], "totals": _totals([], 0),
                "baseline": _totals([], 0), "note": source["message"], "summary": source["message"],
                "summary_source": "template", "leftover_budget": budget_tnd,
                "steps": [{"id": "understand", "title": "Understanding your goal", "detail": "no pieces to analyse yet"}]}

    # 1. PLAN: read the goal (the only step that may use the language model; skipped when the goal is empty).
    read = read_goal(objective) if (objective and (not goals or budget_tnd is None)) else None
    chosen_goals = [g for g in (goals or []) if g in GOALS] or (read["goals"] if read else []) or list(GOALS)
    budget = budget_tnd if budget_tnd else (read["budget_tnd"] if read else None)
    max_items = (read or {}).get("max_items") or DEFAULT_MAX_ITEMS
    names = ", ".join(GOALS[g]["label"] for g in chosen_goals[:3]) + ("…" if len(chosen_goals) > 3 else "")
    steps = [{"id": "understand", "title": "Understanding your goal",
              "detail": f"{len(chosen_goals)} context{'s' if len(chosen_goals) != 1 else ''} ({names}) · "
                        + (f"budget {round(budget)} TND" if budget else "no budget set")
                        + (" · goal read by the language model" if read else "")}]

    plan: dict[str, Any] = {
        "objective": objective, "budget_tnd": budget, "max_items": max_items, "plan_source": "ai" if read else "default",
        "rationale": (read or {}).get("rationale", ""), "goals": [{"id": g, "label": GOALS[g]["label"]} for g in chosen_goals],
        "wardrobe_source": source, "department": profile.get("department"), "price_note": PRICE_NOTE, "cached": False,
    }
    # 2. ANALYSE: the existing rules and ranker, once per context.
    needs = _open_needs(user_id, chosen_goals, wardrobe, profile, labels)
    steps.append({"id": "analyse", "title": "Analysing your wardrobe",
                  "detail": f"{len(wardrobe)} pieces · {len(needs)} open need{'s' if len(needs) != 1 else ''} "
                            f"in {len({n['goal'] for n in needs})} context{'s' if len({n['goal'] for n in needs}) != 1 else ''}"})

    # 3. COMBINE: one piece, several needs.
    chosen = best_plan(needs, budget, max_items)
    shared = max((len(s["hit"]) for s in chosen), default=0)
    steps.append({"id": "combine", "title": "Finding pieces that close several needs",
                  "detail": f"{len(_pieces(needs))} possible pieces compared"
                            + (f" · the best one serves {shared} needs" if shared > 1 else "")})

    # 4. BUDGET
    totals = _totals(chosen, len(needs))
    if budget:
        steps.append({"id": "budget", "title": "Fitting the budget",
                      "detail": f"about {totals['estimated_cost']} TND of {round(budget)} TND for {totals['pieces']} piece"
                                f"{'s' if totals['pieces'] != 1 else ''}"})
    else:
        steps.append({"id": "budget", "title": "Fitting the budget",
                      "detail": f"no budget set · {totals['pieces']} best pieces, about {totals['estimated_cost']} TND"})

    # 5. COMPARE with the simple method, measured with the same rules.
    baseline = _totals(optimise(needs, budget, max_items, first=_simple_method), len(needs))
    steps.append({"id": "compare", "title": "Comparing with the simple method",
                  "detail": f"plan closes {totals['needs_closed']} needs, one gap per context closes {baseline['needs_closed']}"})

    plan["purchases"] = [{
        "order": i + 1, "category": s["piece"][0], "subcategory": s["piece"][1], "name": piece_name(s["piece"][0], s["piece"][1]),
        "price_tnd": {"low": price_range(*s["piece"][:2])[0], "high": price_range(*s["piece"][:2])[1], "estimate": round(s["cost"])},
        "gain": s["gain"], "can_search_shops": shop_search_text(*s["piece"][:2]) is not None,
        "closes": [{"goal": n["goal"], "goal_label": n["goal_label"], "candidate_id": n["candidate_id"], "need": n["name"],
                    "completes": n in s["done"]} for n in s["hit"]],
    } for i, s in enumerate(chosen)]
    plan.update(totals=totals, baseline=baseline, steps=steps, leftover_budget=round(budget - totals["estimated_cost"]) if budget else None)
    if not chosen:
        cheapest = min((_cost(p) for p in _pieces(needs)), default=None)
        plan["note"] = ("Every need of these contexts is already covered." if not needs else
                        f"The budget is too low: the cheapest useful piece costs about {round(cheapest)} TND." if cheapest else "")

    # 6. WRITE
    summary = write_summary(plan, objective)
    plan["summary"], plan["summary_source"] = (summary, "ai") if summary else (template_summary(plan), "template")
    plan["steps"].append({"id": "write", "title": "Writing the plan", "detail": "ready"})

    with _lock:
        if len(_cache) >= CACHE_ENTRIES:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[cache_key] = (time.time(), plan)
    return plan
