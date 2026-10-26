"""
Provider-neutral agent toolset: plain Python functions + JSON schemas - the single source of truth for
the GPT and the Claude agents. Each call is recorded so the UI can show the agent's steps; tools that
produce visuals (outfits, products, duplicate groups, verdict) also attach "cards" the UI renders.
"""

import inspect
import json
from typing import Callable, Dict, List, Optional

from features import FeatureSet, FEATURE_METHODS
from wardrobe_builder import fits

WARDROBE_PARAMS = {"wardrobe", "wardrobe_items", "items"}
CATEGORIES = ["shirts", "pants", "dresses", "shoes", "outerwear", "accessories"]
OCCASIONS = ["wedding", "interview", "office", "party", "date", "gym", "hiking", "beach", "casual"]
SEASONS = ["winter", "spring", "summer", "fall"]


class AgentActions:
    """What the agent may change for a user: it saves outfits directly, and turns wardrobe changes into
    proposals the user approves or rejects (main.py executes them on approval)"""

    def __init__(self, save_outfit: Callable[..., Dict], propose: Callable[..., Dict]):
        self.save_outfit = save_outfit   # (name, item_ids, occasion, score) -> outfit
        self.propose = propose           # (kind, title, detail, payload) -> pending action


def build_tools(engine, wardrobe: List[Dict], record: Callable[..., str], profile: Optional[Dict] = None,
                actions: Optional[AgentActions] = None):
    """Return {name: (function, json_schema_function_spec)}.
    record(tool, input, output, cards=None) stores the step and returns the JSON text given to the model."""
    from wardrobe_insights import (DRESS_CODE, _slim, analyze_wardrobe, compare_pieces, compose_outfits,
                                   score_outfit as score_outfit_fn, shopping_suggestions)

    catalog_by_id = {p["id"]: p for p in engine.catalog}
    profile = profile or {}
    gender = profile.get("gender") or "Unspecified"
    has_gender = any(p.get("gender") for p in engine.catalog)
    insights_cache: Dict = {}

    def insights(budget=None):
        key = budget or 0
        if key not in insights_cache:
            insights_cache[key] = analyze_wardrobe(wardrobe, engine, engine.catalog, profile, budget)
        return insights_cache[key]

    def analyze_redundancy(name: str, category: str, color: str, style: str = "casual",
                           material: str = "cotton", use_case: str = "casual", price: float = 0.0) -> str:
        item = {"name": name, "category": category, "color": color, "style": style,
                "material": material, "use_case": use_case, "price": price or None}
        result = engine.analyze(item, wardrobe, lang="fr")
        summary = {k: result[k] for k in ("redundancy_score", "recommendation", "visual_similarity",
                                          "functional_similarity", "category_saturation", "outfit_contribution",
                                          "confidence")}
        summary["similar_owned_items"] = [{k: m.get(k) for k in ("name", "similarity", "color", "style")}
                                          for m in result["similar_items"]]
        summary["catalog_matches"] = [{k: m.get(k) for k in ("name", "brand", "price", "similarity")}
                                      for m in result["catalog_matches"][:3]]
        return record("analyze_redundancy", item, summary)

    def search_catalog(query: str, category: str = "", top_k: int = 5, max_price: float = 0.0) -> str:
        results = engine.search_catalog({"name": query, "category": category}, top_k=30,
                                        same_category=bool(category), max_price=max_price or None)
        by_id = {p["id"]: p for p in engine.catalog}
        results = [r for r in results if fits(by_id.get(r["id"], {}), gender, has_gender)]  # the shopper's gender
        results = results[:max(1, min(int(top_k), 10))]
        slim = [{k: r.get(k) for k in ("id", "name", "brand", "category", "color", "price", "similarity", "image_url")}
                for r in results]
        return record("search_catalog", {"query": query, "category": category, "max_price": max_price}, slim,
                      cards={"suggestions": slim[:4]})

    def get_wardrobe() -> str:
        slim = [{k: w.get(k) for k in ("id", "name", "category", "color", "style", "material", "season", "price")}
                for w in wardrobe]
        return record("get_wardrobe", {}, slim)

    by_id = {w.get("id"): w for w in wardrobe}

    def resolve(ref: str) -> Optional[Dict]:
        """A piece by id, or by name (exact, then partial) - models often quote the name they read"""
        if ref in by_id:
            return by_id[ref]
        text = (ref or "").strip().lower()
        exact = [w for w in wardrobe if (w.get("name") or "").lower() == text]
        partial = [w for w in wardrobe if text and text in (w.get("name") or "").lower()]
        return (exact or partial or [None])[0]

    def resolve_all(refs: List[str]):
        found, missing = [], []
        for ref in refs or []:
            piece = resolve(str(ref))
            (found if piece else missing).append(piece or ref)
        unique = list({p["id"]: p for p in found}.values())
        return unique, missing

    # ---- computations

    def score_outfit(item_ids: List[str]) -> str:
        pieces, missing = resolve_all(item_ids)
        result = score_outfit_fn(pieces, wardrobe)
        result["unknown_pieces"] = missing
        return record("score_outfit", {"item_ids": item_ids}, {k: v for k, v in result.items() if k != "add"} |
                      {"add_suggestions": [p["name"] for p in result["add"]]},
                      cards={"outfit_score": dict(result, pieces=[_slim(p) for p in pieces])})

    def compare_items(item_a: str, item_b: str) -> str:
        a, b = resolve(item_a), resolve(item_b)
        if not a or not b:
            return record("compare_items", {"item_a": item_a, "item_b": item_b},
                          {"error": "piece not found - call get_wardrobe for the exact ids or names"})
        result = compare_pieces(a, b, engine)
        return record("compare_items", {"item_a": a["name"], "item_b": b["name"]},
                      {k: v for k, v in result.items() if k not in ("a", "b")}, cards={"comparison": result})

    # ---- actions (non-destructive ones run directly; changes to the wardrobe wait for the user's approval)

    def save_outfit(name: str, item_ids: List[str], occasion: str = "") -> str:
        pieces, missing = resolve_all(item_ids)
        if actions is None or len(pieces) < 2:
            return record("save_outfit", {"name": name}, {"error": "need at least 2 known pieces" if actions else
                                                          "saving is not available"})
        score = score_outfit_fn(pieces)["score"]
        saved = actions.save_outfit(name[:120], [p["id"] for p in pieces], occasion or None, score)
        return record("save_outfit", {"name": name, "item_ids": [p["id"] for p in pieces]},
                      {"saved": True, "outfit_id": saved["id"], "score": score, "unknown_pieces": missing},
                      cards={"saved_outfit": dict(saved, pieces=[_slim(p) for p in pieces])})

    def propose_remove_items(item_ids: List[str], reason: str) -> str:
        pieces, missing = resolve_all(item_ids)
        if actions is None or not pieces:
            return record("propose_remove_items", {"item_ids": item_ids}, {"error": "no known piece to remove"})
        names = ", ".join(p["name"] for p in pieces)
        proposal = actions.propose("remove_items", f"Retirer {len(pieces)} pièce{'s' if len(pieces) > 1 else ''} : {names}"[:200],
                                   reason, {"item_ids": [p["id"] for p in pieces], "pieces": [_slim(p) for p in pieces]})
        return record("propose_remove_items", {"item_ids": [p["id"] for p in pieces], "reason": reason},
                      {"proposal_id": proposal["id"], "status": "pending - waiting for the user's approval",
                       "unknown_pieces": missing}, cards={"proposals": [proposal]})

    def propose_add_items(product_ids: List[str], reason: str) -> str:
        products = [catalog_by_id[p] for p in product_ids or [] if p in catalog_by_id]
        if actions is None or not products:
            return record("propose_add_items", {"product_ids": product_ids}, {"error": "no known catalog product"})
        names = ", ".join(p["name"] for p in products)
        proposal = actions.propose("add_items", f"Ajouter {len(products)} pièce{'s' if len(products) > 1 else ''} : {names}"[:200],
                                   reason, {"product_ids": [p["id"] for p in products],
                                            "pieces": [_slim(dict(p, color=p.get("primary_color"))) for p in products]})
        return record("propose_add_items", {"product_ids": [p["id"] for p in products], "reason": reason},
                      {"proposal_id": proposal["id"], "status": "pending - waiting for the user's approval"},
                      cards={"proposals": [proposal]})

    def get_wardrobe_insights() -> str:
        report = insights()
        compact = {k: report.get(k) for k in ("pieces", "health", "scores", "composition", "extra_pieces", "seasons", "style")}
        compact["duplicate_groups"] = [{"pieces": [i["name"] for i in g["items"]], "keep": g["items"][0]["name"],
                                        "similarity": g["similarity"]} for g in report.get("duplicates", [])]
        compact["palette"] = report.get("palette") and {k: report["palette"][k] for k in ("neutral_share", "harmony", "accents")}
        compact["outfits"] = report.get("outfits") and {"good_outfits": report["outfits"]["good_outfits"],
                                                        "orphans": [o["name"] for o in report["outfits"]["orphans"]],
                                                        "stars": [s["name"] for s in report["outfits"]["stars"]]}
        compact["tips"] = [{"title": t["title"], "detail": t["detail"]} for t in report.get("tips", [])]
        return record("get_wardrobe_insights", {}, compact,
                      cards={"insights": {"health": report.get("health"), "scores": report.get("scores"),
                                          "tips": report.get("tips", [])[:6]},
                             "duplicates": report.get("duplicates", [])[:6]})

    def suggest_outfits(occasion: str = "casual", season: str = "") -> str:
        from agent import OCCASIONS as OCC, parse_season

        _, label, styles, avoid = OCC.get(occasion, OCC["casual"])
        season = season if season in SEASONS else parse_season("")
        composed = compose_outfits(wardrobe, styles, avoid, season, dress_code=DRESS_CODE.get(occasion, "casual"))
        return record("suggest_outfits", {"occasion": occasion, "season": season},
                      {"occasion": label, "season": season, "possible": composed["possible"],
                       "outfits": [[f"{p['name']} ({p['category']})" for p in o["pieces"]] for o in composed["outfits"]],
                       "missing_categories": composed["missing"]},
                      cards={"outfits": composed["outfits"]})

    def plan_shopping(budget: float = 0.0) -> str:
        report = insights(budget or None)
        low = [r for r in report.get("composition", []) if r["status"] == "low"]
        high = [r["label"] for r in report.get("composition", []) if r["status"] == "high"]
        suggestions = shopping_suggestions(wardrobe, engine.catalog, report.get("composition", []), profile, budget or None)
        return record("plan_shopping", {"budget": budget},
                      {"gaps": [{"category": r["label"], "have": r["have"], "advised": r["ideal"]} for r in low],
                       "do_not_buy": high + [g["category"] for g in report.get("duplicates", [])],
                       "products": [{k: p.get(k) for k in ("name", "brand", "price", "reason")} for p in suggestions]},
                      cards={"suggestions": suggestions})

    def plan_declutter() -> str:
        report = insights()
        groups = report.get("duplicates", [])
        return record("plan_declutter", {},
                      {"duplicate_groups": [{"keep": g["items"][0]["name"], "remove": [i["name"] for i in g["items"][1:]]}
                                            for g in groups],
                       "orphans": [o["name"] for o in (report.get("outfits") or {}).get("orphans", [])]},
                      cards={"duplicates": groups[:6]})

    def list_features() -> str:
        catalog = {}
        for fid, name in FEATURE_METHODS.items():
            func = getattr(FeatureSet, name)
            params = [p for p in inspect.signature(func).parameters if p not in WARDROBE_PARAMS]
            catalog[fid] = {"name": name, "params": params, "doc": (func.__doc__ or "").strip().splitlines()[0]}
        return record("list_features", {}, catalog)

    def run_feature(feature_id: int, arguments_json: str = "{}") -> str:
        func = FeatureSet.get_feature(int(feature_id))
        if func is None:
            return record("run_feature", {"feature_id": feature_id}, {"error": f"Unknown feature {feature_id}"})
        try:
            kwargs = json.loads(arguments_json or "{}")
            if not isinstance(kwargs, dict):
                raise ValueError("arguments_json must be a JSON object")
            params = inspect.signature(func).parameters
            # Models often pass the item's fields flat for item-based features: wrap them
            if "item" in params and "item" not in kwargs:
                kwargs = {"item": kwargs}
            for param in params:
                if param in WARDROBE_PARAMS and param not in kwargs:
                    kwargs[param] = wardrobe
            output = func(**kwargs)
        except Exception as e:  # reported to the model so it can fix its input
            output = {"error": f"{type(e).__name__}: {e}"}
        return record("run_feature", {"feature_id": feature_id, "arguments": arguments_json}, output)

    def spec(name, description, properties, required):
        return {"type": "function", "function": {
            "name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}}

    s = {"type": "string"}
    return {
        "get_wardrobe_insights": (get_wardrobe_insights, spec(
            "get_wardrobe_insights",
            "Full diagnosis of the shopper's wardrobe: health score 0-100, composition vs the ideal for their gender, "
            "duplicate groups (which piece to keep), color palette, versatility (harmonious outfits, orphan pieces), "
            "season coverage and prioritized tips. Start here for any question about the wardrobe as a whole.", {}, [])),
        "analyze_redundancy": (analyze_redundancy, spec(
            "analyze_redundancy",
            "Should the shopper buy this item? Runs the redundancy pipeline (CLIP similarity with owned pieces, "
            "0-100 redundancy score, buy/consider/skip). Use English attribute values.",
            {"name": s, "category": {"type": "string", "enum": CATEGORIES},
             "color": {**s, "description": "english color, e.g. navy"}, "style": s, "material": s, "use_case": s,
             "price": {"type": "number", "description": "price, 0 if unknown"}},
            ["name", "category", "color"])),
        "suggest_outfits": (suggest_outfits, spec(
            "suggest_outfits", "Compose up to 3 harmonious outfits from the pieces the shopper OWNS for an occasion and season.",
            {"occasion": {"type": "string", "enum": OCCASIONS}, "season": {"type": "string", "enum": SEASONS}}, ["occasion"])),
        "plan_shopping": (plan_shopping, spec(
            "plan_shopping", "What is worth buying: real gaps for this wardrobe and gender, categories NOT to buy, "
            "and matching catalog products (within the budget if given).",
            {"budget": {"type": "number", "description": "total budget in $, 0 = none"}}, [])),
        "plan_declutter": (plan_declutter, spec(
            "plan_declutter", "What to sell or donate: duplicate groups (keep the most versatile piece) and pieces that "
            "match nothing.", {}, [])),
        "search_catalog": (search_catalog, spec(
            "search_catalog", "Semantic (CLIP) search in the real product catalog, filtered for the shopper's gender. "
            "Use it to find a specific product, compare offers or prices.",
            {"query": {**s, "description": "English description, e.g. black leather chelsea boots"},
             "category": s, "top_k": {"type": "integer"}, "max_price": {"type": "number", "description": "0 = no limit"}},
            ["query"])),
        "get_wardrobe": (get_wardrobe, spec(
            "get_wardrobe", "List every piece the shopper owns, with its id (use the ids with the tools below).", {}, [])),
        "score_outfit": (score_outfit, spec(
            "score_outfit", "Synergy score 0-100 of a set of OWNED pieces (color harmony, completeness, style and season "
            "coherence, doubled roles), with feedback and owned pieces that would complete it.",
            {"item_ids": {"type": "array", "items": s, "description": "ids (or exact names) from get_wardrobe"}}, ["item_ids"])),
        "compare_items": (compare_items, spec(
            "compare_items", "Similarity score between two OWNED pieces (CLIP image + text, attributes) and whether "
            "they are duplicates.", {"item_a": {**s, "description": "id or name"}, "item_b": {**s, "description": "id or name"}},
            ["item_a", "item_b"])),
        "save_outfit": (save_outfit, spec(
            "save_outfit", "ACTION - save an outfit of owned pieces to the user's Outfit Studio. Only when the user asks "
            "to save or keep a look.",
            {"name": {**s, "description": "short French name, e.g. Entretien d'hiver"},
             "item_ids": {"type": "array", "items": s}, "occasion": {"type": "string", "enum": OCCASIONS}},
            ["name", "item_ids"])),
        "propose_remove_items": (propose_remove_items, spec(
            "propose_remove_items", "ACTION (needs approval) - propose removing owned pieces, e.g. the extra pieces of a "
            "duplicate group. Creates a proposal card the user approves or rejects; nothing is removed yet.",
            {"item_ids": {"type": "array", "items": s}, "reason": {**s, "description": "one French sentence"}},
            ["item_ids", "reason"])),
        "propose_add_items": (propose_add_items, spec(
            "propose_add_items", "ACTION (needs approval) - propose adding catalog products the user says they bought. "
            "Creates a proposal card; nothing is added yet.",
            {"product_ids": {"type": "array", "items": s, "description": "catalog ids from search_catalog"},
             "reason": {**s, "description": "one French sentence"}}, ["product_ids", "reason"])),
        "list_features": (list_features, spec("list_features", "List the 31 analysis features and their parameters.", {}, [])),
        "run_feature": (run_feature, spec(
            "run_feature",
            "Run one of the 31 features by id (e.g. 17 color harmony, 23 quality, 24 sustainability, 25 resale, "
            "29 care, 31 market price). Wardrobe parameters are filled automatically. "
            'Item-based features (20, 23, 24, 25, 29, 31) take {"item": {"name", "category", "color", "material", "price"}}; '
            'feature 17 takes {"colors": [...]}.',
            {"feature_id": {"type": "integer"},
             "arguments_json": {**s, "description": 'JSON object, e.g. {"item": {"name": "White sneakers", "material": "leather", "price": 120}}'}},
            ["feature_id"])),
    }


def anthropic_tools(tools: Dict) -> List[Dict]:
    """The same tools in the Anthropic Messages API format"""
    return [{"name": spec["function"]["name"], "description": spec["function"]["description"],
             "input_schema": spec["function"]["parameters"]} for _, spec in tools.values()]
