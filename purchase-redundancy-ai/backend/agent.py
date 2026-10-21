"""
Autonomous shopping agent.

Missions:
- "purchase":  should I buy this item? (photo and/or free text and/or structured fields)
- "audit":     review my whole wardrobe (health score, duplicate groups, balance, colors, versatility, tips)
- "outfits":   what to wear for an occasion / season, from the pieces I own
- "shopping":  what is worth buying (gaps, budget) - and what not to buy
- "declutter": what to sell or donate (duplicates, pieces that match nothing)
- "ask":       free question - routed to the right mission (local) or answered by the LLM with tools,
               with the conversation history (multi-turn)

The agent plans its steps, executes them with the project's tools (CLIP vision, redundancy
engine, 31 features, catalog search) and streams progress events. When Claude is available it
runs as a Claude tool-use agent (Claude chooses the tools); otherwise a local planner executes
the same toolset deterministically, so the agent always works.

Events (dicts, streamed as NDJSON by the API):
  {"type": "start", "mission", "mode", "plan": [{"id", "title"}]}
  {"type": "step", "id", "title", "status": "running" | "done" | "skipped", "summary"?, "data"?}
  {"type": "final", "verdict", "headline", "reasons", "actions", "suggestions", "answer", "report"}
  {"type": "error", "message"}
"""

import json
import logging
import re
import threading
import queue
import time
from typing import Dict, Iterator, List, Optional

import numpy as np

from features import FeatureSet, NEUTRAL_COLORS
from wardrobe_insights import DRESS_CODE, analyze_wardrobe, compose_outfits, shopping_suggestions

logger = logging.getLogger(__name__)

# ============================================================================
# Lightweight text understanding (French + English)
# ============================================================================

CATEGORY_WORDS = {
    "shirts": ["chemise", "t-shirt", "tshirt", "tee", "polo", "pull", "sweat", "hoodie", "top", "débardeur",
               "cardigan", "shirt", "sweater", "blouse", "henley", "tank"],
    "pants": ["pantalon", "jean", "jeans", "short", "legging", "jogging", "chino", "pants", "trousers", "shorts"],
    "dresses": ["robe", "dress"],
    "shoes": ["chaussure", "chaussures", "basket", "baskets", "botte", "bottes", "bottine", "sandale", "mocassin",
              "talon", "escarpin", "sneaker", "sneakers", "shoes", "boots", "heels", "loafers", "sandals"],
    "outerwear": ["veste", "manteau", "blouson", "doudoune", "blazer", "gilet", "imperméable", "parka",
                  "jacket", "coat", "puffer", "vest", "raincoat", "windbreaker"],
    "accessories": ["sac", "ceinture", "chapeau", "casquette", "écharpe", "montre", "lunettes", "portefeuille",
                    "gants", "cravate", "bijou", "collier", "bag", "belt", "hat", "scarf", "watch", "sunglasses",
                    "wallet", "gloves", "tie", "jewelry"],
}
COLOR_WORDS = {
    "noir": "black", "noire": "black", "blanc": "white", "blanche": "white", "gris": "gray", "grise": "gray",
    "bleu marine": "navy", "marine": "navy", "bleu": "blue", "bleue": "blue", "rouge": "red", "rose": "pink",
    "vert": "green", "verte": "green", "kaki": "khaki", "beige": "beige", "crème": "cream", "orange": "orange",
    "jaune": "yellow", "violet": "purple", "violette": "purple", "bordeaux": "burgundy", "marron": "brown",
    "camel": "tan", "doré": "gold", "argent": "silver", "turquoise": "turquoise", "corail": "coral",
    # plural forms ("des baskets blanches")
    "noirs": "black", "noires": "black", "blancs": "white", "blanches": "white", "grises": "gray",
    "bleus": "blue", "bleues": "blue", "rouges": "red", "roses": "pink", "verts": "green", "vertes": "green",
    "jaunes": "yellow", "violets": "purple", "violettes": "purple", "beiges": "beige",
}
MATERIAL_WORDS = {"coton": "cotton", "laine": "wool", "cuir": "leather", "lin": "linen", "soie": "silk",
                  "denim": "denim", "daim": "suede", "polyester": "polyester", "nylon": "nylon", "polaire": "fleece"}
STYLE_WORDS = {"décontracté": "casual", "casual": "casual", "habillé": "formal", "formel": "formal",
               "sport": "sporty", "sportif": "sporty", "classique": "classic", "vintage": "vintage",
               "minimaliste": "minimalist", "streetwear": "streetwear", "bureau": "business", "chic": "classic"}
ENGLISH = {c: c for c in list(COLOR_WORDS.values()) + ["cotton", "wool", "leather", "linen", "silk", "suede"]}

VERDICT_FR = {"buy": "Achat conseillé", "consider": "À réfléchir", "skip": "Inutile — vous l'avez déjà"}
CATEGORY_FR = {"shirts": "hauts", "pants": "bas", "dresses": "robes", "shoes": "chaussures",
               "outerwear": "vestes & manteaux", "accessories": "accessoires"}


def _find(text: str, words) -> Optional[str]:
    for word in sorted(words, key=len, reverse=True):
        if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text):
            return word
    return None


def parse_item_text(message: str) -> Dict:
    """Extract category / color / material / style / price from a free-text request"""
    text = (message or "").lower()
    item: Dict = {}
    for category, words in CATEGORY_WORDS.items():
        word = _find(text, words)
        if word:
            item["category"] = category
            item["noun"] = word
            break
    color = _find(text, list(COLOR_WORDS) + [c for c in ENGLISH if c in NEUTRAL_COLORS or c in COLOR_WORDS.values()])
    if color:
        item["color"] = COLOR_WORDS.get(color, color)
    material = _find(text, list(MATERIAL_WORDS) + list(MATERIAL_WORDS.values()))
    if material:
        item["material"] = MATERIAL_WORDS.get(material, material)
    style = _find(text, list(STYLE_WORDS))
    if style:
        item["style"] = STYLE_WORDS[style]
    price = re.search(r"(\d+(?:[.,]\d{1,2})?)\s?(?:€|eur|euros?|\$|usd|dollars?)|[$€]\s?(\d+(?:[.,]\d{1,2})?)", text)
    if price:
        item["price"] = float((price.group(1) or price.group(2)).replace(",", "."))
    return item

# Occasions: French/English words -> (label, preferred styles, styles to avoid)
OCCASIONS = {
    "wedding": (["mariage", "wedding", "cérémonie", "baptême"], "un mariage", {"formal", "classic"}, {"sporty"}),
    "interview": (["entretien", "interview", "recrutement"], "un entretien", {"formal", "classic", "business", "minimalist"}, {"sporty"}),
    "office": (["bureau", "travail", "boulot", "office", "réunion"], "le bureau", {"formal", "classic", "business", "casual"}, {"sporty"}),
    "party": (["soirée", "fête", "party", "anniversaire", "club"], "une soirée", {"formal", "casual", "trendy"}, set()),
    "date": (["rendez-vous", "rdv", "date", "dîner", "restaurant"], "un rendez-vous", {"casual", "classic", "formal"}, {"sporty"}),
    "gym": (["sport", "salle", "gym", "running", "footing", "musculation"], "le sport", {"sporty"}, {"formal"}),
    "hiking": (["randonnée", "rando", "hiking", "montagne"], "une randonnée", {"sporty", "casual"}, {"formal"}),
    "beach": (["plage", "vacances", "beach", "piscine"], "la plage", {"casual", "sporty"}, {"formal"}),
    "casual": (["week-end", "weekend", "tous les jours", "quotidien", "décontracté", "casual"], "le quotidien", {"casual", "sporty"}, set()),
}
SEASON_WORDS = {"hiver": "winter", "winter": "winter", "été": "summer", "summer": "summer", "printemps": "spring",
                "spring": "spring", "automne": "fall", "fall": "fall", "froid": "winter", "chaud": "summer"}
INTENT_WORDS = {
    "outfits": ["porter", "tenue", "tenues", "look", "outfit", "m'habiller", "habiller", "assortir", "associer"],
    "declutter": ["trier", "tri", "vendre", "revendre", "donner", "désencombrer", "jeter", "ranger", "en trop", "doublons"],
    "shopping": ["acheter quoi", "quoi acheter", "manque", "manquent", "liste d'achat", "liste de courses", "budget",
                 "besoin de quoi", "compléter", "que dois-je acheter", "shopping"],
    "audit": ["audit", "analyse ma garde", "analyser ma garde", "bilan", "état de ma garde", "score", "diagnostic"],
}


def route_intent(message: str) -> str:
    """Free text -> mission (local mode). An item description defaults to the purchase decision."""
    text = (message or "").lower()
    for mission in ("declutter", "shopping", "audit", "outfits"):
        if any(word in text for word in INTENT_WORDS[mission]):
            return mission
    if any(_find(text, words) for _, (words, *_rest) in OCCASIONS.items()):
        return "outfits"
    return "purchase" if parse_item_text(text).get("category") else "audit"


def parse_occasion(message: str):
    text = (message or "").lower()
    for key, (words, label, styles, avoid) in OCCASIONS.items():
        if _find(text, words):
            return key, label, styles, avoid
    words, label, styles, avoid = OCCASIONS["casual"]
    return "casual", label, styles, avoid


def parse_season(message: str) -> str:
    text = (message or "").lower()
    for word, season in SEASON_WORDS.items():
        if _find(text, [word]):
            return season
    month = time.localtime().tm_mon
    return "winter" if month in (12, 1, 2) else "spring" if month in (3, 4, 5) else "summer" if month in (6, 7, 8) else "fall"

# ============================================================================
# Agent
# ============================================================================

class AutonomousAgent:
    def __init__(self, engine, image_processor, llm=None):
        self.engine = engine
        self.image_processor = image_processor
        self.llm = llm

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, mission: str, wardrobe: List[Dict], message: str = "", item: Optional[Dict] = None,
            image: Optional[str] = None, budget: Optional[float] = None, mode: str = "auto",
            profile: Optional[Dict] = None, history: Optional[List[Dict]] = None) -> Iterator[Dict]:
        profile = profile or {}
        use_claude = mode in ("claude", "llm") or (mode == "auto" and self.llm is not None and self.llm.available)
        if use_claude and (self.llm is None or not self.llm.available):
            yield {"type": "error", "message": f"IA indisponible : {getattr(self.llm, 'error', None)}"}
            return
        try:
            if use_claude:
                for event in self._run_claude(mission, wardrobe, message, item or {}, image, budget, profile, history):
                    if event["type"] == "error" and mode == "auto":
                        # the LLM failed (no credits, network...) -> the local planner takes over
                        yield {"type": "notice", "message": f"{event['message']} — l'agent local prend le relais."}
                        break
                    yield event
                else:
                    return
            if mission == "ask":
                mission = "purchase" if (image or item) else route_intent(message)
            if budget is None and mission == "shopping":  # "j'ai 150 $" -> budget
                budget = parse_item_text(message).get("price")
            if mission == "audit":
                yield from self._audit(wardrobe, budget, profile)
            elif mission == "outfits":
                yield from self._outfits(wardrobe, message, profile)
            elif mission == "shopping":
                yield from self._shopping(wardrobe, budget, profile)
            elif mission == "declutter":
                yield from self._declutter(wardrobe, profile)
            else:
                yield from self._purchase(wardrobe, message, item or {}, image, budget)
        except Exception as e:
            logger.exception("Agent failure")
            yield {"type": "error", "message": f"{type(e).__name__}: {e}"}

    # ------------------------------------------------------------------
    # Local planner - purchase mission
    # ------------------------------------------------------------------

    def _purchase(self, wardrobe: List[Dict], message: str, item: Dict, image: Optional[str],
                  budget: Optional[float]) -> Iterator[Dict]:
        plan = [("understand", "Comprendre la demande"),
                ("vision", "Analyser la photo (CLIP)"),
                ("wardrobe", "Inspecter votre garde-robe"),
                ("redundancy", "Chercher les doublons"),
                ("compat", "Tester les associations de tenues"),
                ("market", "Comparer avec le marché"),
                ("quality", "Évaluer qualité & durabilité"),
                ("decide", "Prendre la décision")]
        yield {"type": "start", "mission": "purchase", "mode": "local", "plan": [{"id": i, "title": t} for i, t in plan]}

        # 1. Understand the request
        yield self._running("understand", plan)
        parsed = parse_item_text(message)
        candidate = {k: v for k, v in parsed.items() if k != "noun"}
        candidate.update({k: v for k, v in (item or {}).items() if v not in (None, "", 0)})
        yield self._done("understand", plan, self._describe_parsed(parsed, item), {"parsed": parsed})

        # 2. Vision
        image_embedding = None
        if image:
            yield self._running("vision", plan)
            analysis = self.image_processor.process_image(image)
            if analysis.get("status") != "success":
                yield {"type": "error", "message": f"Photo illisible : {analysis.get('error')}"}
                return
            attrs = analysis["attributes"]
            image_embedding = np.asarray(analysis["embedding_full"], dtype=np.float32)
            detected = {
                "category": attrs.get("category") if attrs.get("category") not in (None, "unknown") else None,
                "color": attrs.get("primary_color") if attrs.get("primary_color") != "unknown" else None,
                "style": attrs.get("style") if attrs.get("style") not in (None, "unknown") else None,
                "material": attrs.get("material_appearance") if attrs.get("material_appearance") not in (None, "unknown") else None,
            }
            for k, v in detected.items():   # text/fields given by the user win over the photo
                if v and not candidate.get(k):
                    candidate[k] = v
            conf = attrs.get("category_confidence") or 0
            summary = (f"Je vois : {CATEGORY_FR.get(detected['category'], detected['category'] or '?')} "
                       f"({conf:.0%} sûr), couleur {detected['color'] or '?'}, style {detected['style'] or '?'}, "
                       f"aspect {detected['material'] or '?'}.")
            yield self._done("vision", plan, summary, {"attributes": {k: attrs.get(k) for k in
                             ("category", "category_confidence", "primary_color", "style", "material_appearance")},
                             "colors": analysis.get("colors")})
        else:
            yield self._skipped("vision", plan, "Pas de photo fournie.")

        if not candidate.get("category"):
            yield {"type": "error", "message": "Je n'ai pas compris quel article analyser. Ajoutez une photo "
                                               "ou décrivez-le (ex. « chemise bleue en coton à 45 € »)."}
            return
        candidate.setdefault("color", "unknown")
        candidate.setdefault("style", "casual")
        candidate.setdefault("material", "cotton")
        candidate.setdefault("use_case", "casual")
        candidate.setdefault("name", self._name_for(candidate, parsed.get("noun")))

        # 3. Wardrobe
        yield self._running("wardrobe", plan)
        counts: Dict[str, int] = {}
        for w in wardrobe:
            counts[w.get("category")] = counts.get(w.get("category"), 0) + 1
        same_cat = counts.get(candidate["category"], 0)
        yield self._done("wardrobe", plan,
                         f"{len(wardrobe)} pièces, dont {same_cat} dans la catégorie {CATEGORY_FR.get(candidate['category'])}.",
                         {"total": len(wardrobe), "by_category": counts})

        # 4. Redundancy
        yield self._running("redundancy", plan)
        result = self.engine.analyze(candidate, wardrobe, image_embedding=image_embedding, lang="fr")
        top = result["similar_items"][0] if result["similar_items"] else None
        summary = (f"Score de redondance {result['redundancy_score']}/100. "
                   + (f"Très proche de « {top['name']} » ({top['similarity']:.0%})." if top else "Aucun doublon trouvé."))
        yield self._done("redundancy", plan, summary, {
            "redundancy_score": result["redundancy_score"], "recommendation": result["recommendation"],
            "similar_items": result["similar_items"][:3]})

        # 5. Outfit compatibility
        yield self._running("compat", plan)
        colors = [w.get("color") for w in wardrobe if w.get("color")]
        harmony = FeatureSet.feature_17_color_harmony(colors + [candidate["color"]])
        with_new = FeatureSet.feature_27_outfit_matching(wardrobe + [dict(candidate, name=candidate["name"])], max_outfits=50)
        new_outfits = [o for o in with_new if candidate["name"] in o["pieces"]]
        good_new = [o for o in new_outfits if o["harmony_score"] >= 0.7]
        yield self._done("compat", plan,
                         f"Crée {len(good_new)} nouvelle(s) tenue(s) harmonieuse(s) ; harmonie des couleurs {harmony['harmony_score']:.0%}.",
                         {"new_outfits": good_new[:4], "harmony": harmony["harmony_score"]})

        # 6. Market
        yield self._running("market", plan)
        market = FeatureSet.feature_31_market_intelligence(candidate) if candidate.get("price") else None
        cheaper = []
        if candidate.get("price"):
            cheaper = self.engine.search_catalog(candidate, top_k=3, max_price=candidate["price"] * 0.8)
        if market and market.get("price_position"):
            summary = (f"Prix {candidate['price']:.0f} : positionnement {self._fr_position(market['price_position'])} "
                       f"(médiane du marché {market['price_stats']['median']:.0f}).")
        else:
            summary = "Prix non indiqué — je montre les modèles les plus proches du catalogue."
        yield self._done("market", plan, summary, {"market": market, "similar_products": result["catalog_matches"][:4],
                                                    "cheaper": cheaper})

        # 7. Quality
        yield self._running("quality", plan)
        quality = FeatureSet.feature_23_quality_assessment(candidate)
        sustain = FeatureSet.feature_24_sustainability_tracking(candidate)
        yield self._done("quality", plan,
                         f"Qualité estimée {quality['quality_score']}/100, durabilité {sustain['sustainability_score']}/100 "
                         f"({ {v: k for k, v in MATERIAL_WORDS.items()}.get(candidate['material'], candidate['material'])})).",
                         {"quality": quality, "sustainability": sustain})

        # 8. Decide
        yield self._running("decide", plan)
        score = result["redundancy_score"]
        reasons, actions = [], []
        if top:
            reasons.append(f"Vous possédez déjà « {top['name']} » ({top['similarity']:.0%} similaire).")
        else:
            reasons.append("Rien d'équivalent dans votre garde-robe.")
        if result["category_saturation"] >= 80:
            reasons.append(f"Catégorie saturée : {same_cat} pièces de {CATEGORY_FR.get(candidate['category'])}.")
            score += 5
        if len(good_new) >= 3:
            reasons.append(f"Il s'associe bien : {len(good_new)} nouvelles tenues possibles.")
            score -= 10
        elif wardrobe and not good_new and candidate["category"] in ("shirts", "pants", "shoes"):
            reasons.append("Il s'associe mal avec vos pièces actuelles.")
            score += 5
        if market and market.get("price_position") == "premium" and quality["quality_score"] < 70:
            reasons.append("Prix élevé pour une qualité moyenne.")
            score += 10
        if budget and candidate.get("price") and candidate["price"] > budget:
            reasons.append(f"Dépasse votre budget ({candidate['price']:.0f} > {budget:.0f}).")
            score += 15
        score = int(max(0, min(100, score)))
        verdict = self.engine.recommendation_for(score)

        if verdict == "skip" and top:
            actions.append(f"Portez plutôt « {top['name']} » — {result['alternatives'][0]['styling_tip'] if result['alternatives'] else ''}")
        if cheaper and verdict != "skip":
            actions.append(f"Moins cher et similaire : « {cheaper[0]['name']} » ({cheaper[0]['brand']}) à {cheaper[0]['price']:.0f}.")
        if verdict == "buy":
            actions.append("Vous pouvez l'acheter — ajoutez-le ensuite à votre garde-robe.")
        if verdict == "consider":
            actions.append("Attendez quelques jours : si le besoin persiste, achetez-le.")

        headline = f"{VERDICT_FR[verdict]} — {candidate['name']}"
        answer = self._claude_summary(headline, reasons, actions) or " ".join(reasons + actions)
        yield self._done("decide", plan, f"{VERDICT_FR[verdict]} (score final {score}/100).", {"final_score": score})

        yield {"type": "final", "mission": "purchase", "verdict": verdict, "headline": headline,
               "score": score, "reasons": reasons, "actions": actions,
               "item": candidate, "image_used": image is not None,
               "similar_owned": result["similar_items"][:3],
               "suggestions": (cheaper or result["catalog_matches"])[:4],
               "answer": answer}

    # ------------------------------------------------------------------
    # Local planner - wardrobe audit mission
    # ------------------------------------------------------------------

    def _insights(self, wardrobe, profile, budget=None):
        return analyze_wardrobe(wardrobe, self.engine, self.engine.catalog, profile, budget)

    def _audit(self, wardrobe: List[Dict], budget: Optional[float], profile: Dict) -> Iterator[Dict]:
        plan = [("load", "Charger la garde-robe et le profil"),
                ("duplicates", "Regrouper les pièces en double"),
                ("balance", "Comparer la composition à l'idéal"),
                ("harmony", "Analyser couleurs & style"),
                ("outfits", "Mesurer la polyvalence (tenues possibles)"),
                ("shopping", "Chercher ce qui manque vraiment"),
                ("report", "Rédiger le diagnostic")]
        yield {"type": "start", "mission": "audit", "mode": "local", "plan": [{"id": i, "title": t} for i, t in plan]}

        yield self._running("load", plan)
        if len(wardrobe) < 2:
            yield {"type": "error", "message": "Ajoutez au moins 2 pièces à votre garde-robe pour lancer un audit."}
            return
        gender_fr = {"Women": "femme", "Men": "homme"}.get(profile.get("gender"), "profil mixte")
        yield self._done("load", plan, f"{len(wardrobe)} pièces chargées ({gender_fr}).", {"total": len(wardrobe)})

        yield self._running("duplicates", plan)
        report = self._insights(wardrobe, profile, budget)
        dups = report["duplicates"]
        yield self._done("duplicates", plan,
                         f"{len(dups)} groupe(s) de doublons, {report['extra_pieces']} pièce(s) en trop." if dups
                         else "Aucun doublon — bravo.", {"duplicates": dups[:6]})

        yield self._running("balance", plan)
        low = [r for r in report["composition"] if r["status"] == "low"]
        high = [r for r in report["composition"] if r["status"] == "high"]
        yield self._done("balance", plan,
                         f"Équilibre {report['scores']['balance']}/100 — " +
                         (", ".join(f"peu de {r['label']}" for r in low) or "aucun manque") + " ; " +
                         (", ".join(f"trop de {r['label']}" for r in high) or "aucun excès") + ".",
                         {"composition": report["composition"]})

        yield self._running("harmony", plan)
        pal = report["palette"]
        yield self._done("harmony", plan,
                         f"{round(pal['neutral_share'] * 100)} % de neutres, harmonie {report['scores']['harmony']}/100, "
                         f"style dominant {report['style']['dominant'] or '?'}.", {"palette": pal, "style": report["style"]})

        yield self._running("outfits", plan)
        out = report["outfits"]
        yield self._done("outfits", plan,
                         f"{out['good_outfits']} tenues harmonieuses possibles ; {out['orphan_count']} pièce(s) orpheline(s).",
                         {"examples": out["examples"][:4], "stars": out["stars"]})

        yield self._running("shopping", plan)
        yield self._done("shopping", plan,
                         f"{len(report['suggestions'])} suggestion(s) ciblée(s)." if report["suggestions"]
                         else "Rien d'indispensable à acheter.", {"suggestions": report["suggestions"]})

        yield self._running("report", plan)
        reasons = [t["title"] + " — " + t["detail"] for t in report["tips"] if t["severity"] in ("high", "medium")][:4]
        actions = [t["detail"] for t in report["tips"] if t["severity"] == "low"][:3]
        headline = f"Diagnostic de votre garde-robe — santé {report['health']}/100"
        answer = self._claude_summary(headline, reasons, actions) or " ".join(reasons + actions)
        yield self._done("report", plan, "Diagnostic prêt.")
        yield {"type": "final", "mission": "audit", "verdict": None, "headline": headline, "score": report["health"],
               "reasons": reasons, "actions": actions, "duplicates": dups[:6], "outfits": out["examples"][:4],
               "suggestions": report["suggestions"], "insights": {"health": report["health"], "scores": report["scores"],
                                                                  "tips": report["tips"][:6]}, "answer": answer}

    def _outfits(self, wardrobe: List[Dict], message: str, profile: Dict) -> Iterator[Dict]:
        plan = [("understand", "Comprendre l'occasion et la saison"),
                ("select", "Sélectionner les pièces adaptées"),
                ("compose", "Composer des tenues harmonieuses"),
                ("complete", "Vérifier ce qui manque"),
                ("report", "Présenter les tenues")]
        yield {"type": "start", "mission": "outfits", "mode": "local", "plan": [{"id": i, "title": t} for i, t in plan]}

        yield self._running("understand", plan)
        key, label, styles, avoid = parse_occasion(message)
        season = parse_season(message)
        season_fr = {"winter": "l'hiver", "summer": "l'été", "spring": "le printemps", "fall": "l'automne"}[season]
        yield self._done("understand", plan, f"Tenues pour {label}, en {season_fr}.", {"occasion": key, "season": season})

        yield self._running("select", plan)
        composed = compose_outfits(wardrobe, styles, avoid, season, dress_code=DRESS_CODE.get(key, "casual"))
        yield self._done("select", plan, f"{composed['pool']} pièces adaptées sur {len(wardrobe)}.", {"pieces": composed["pool"]})

        yield self._running("compose", plan)
        chosen, missing = composed["outfits"], composed["missing"]
        yield self._done("compose", plan, f"{len(chosen)} tenue(s) composée(s) sur {composed['possible']} possibles.",
                         {"outfits": chosen})

        yield self._running("complete", plan)
        gaps = [{"category": c, "label": CATEGORY_FR[c], "have": 0, "ideal": 1, "status": "low"} for c in missing]
        suggestions = shopping_suggestions(wardrobe, self.engine.catalog, gaps, profile, per_gap=2)
        yield self._done("complete", plan,
                         "Il manque : " + ", ".join(CATEGORY_FR[c] for c in missing) + "." if missing
                         else "Vous avez tout ce qu'il faut.", {"missing": missing, "suggestions": suggestions})

        yield self._running("report", plan)
        reasons = [f"Tenue {n}: " + " + ".join(p["name"] for p in o["pieces"]) for n, o in enumerate(chosen, 1)]
        actions = ([f"Pour {label}, il vous manque des {', '.join(CATEGORY_FR[c] for c in missing)} adapté(e)s."]
                   if missing else ["Préparez la tenue la veille et vérifiez l'entretien des pièces."])
        if not chosen:
            reasons = [f"Je n'ai pas trouvé de tenue complète et harmonieuse pour {label} en {season_fr}."]
        headline = f"Que porter pour {label} ?"
        answer = self._claude_summary(headline, reasons, actions) or " ".join(reasons + actions)
        yield self._done("report", plan, "Tenues prêtes.")
        yield {"type": "final", "mission": "outfits", "verdict": None, "headline": headline, "score": None,
               "reasons": reasons, "actions": actions, "outfits": chosen, "suggestions": suggestions, "answer": answer}

    def _shopping(self, wardrobe: List[Dict], budget: Optional[float], profile: Dict) -> Iterator[Dict]:
        plan = [("analyze", "Analyser la garde-robe"),
                ("gaps", "Identifier les vrais manques"),
                ("avoid", "Repérer ce qu'il ne faut PAS racheter"),
                ("budget", "Répartir le budget"),
                ("products", "Choisir des produits du catalogue")]
        yield {"type": "start", "mission": "shopping", "mode": "local", "plan": [{"id": i, "title": t} for i, t in plan]}

        yield self._running("analyze", plan)
        report = self._insights(wardrobe, profile, budget)
        if report["empty"]:
            yield {"type": "error", "message": "Votre garde-robe est vide : ajoutez d'abord vos pièces (ou une garde-robe de départ)."}
            return
        yield self._done("analyze", plan, f"{report['pieces']} pièces, santé {report['health']}/100.")

        yield self._running("gaps", plan)
        low = [r for r in report["composition"] if r["status"] == "low"]
        winter_gap = report["seasons"]["winter"]["outerwear"] == 0
        yield self._done("gaps", plan, ("Manques : " + ", ".join(f"{r['label']} ({r['have']}/{r['ideal']})" for r in low))
                         if low else "Aucun manque important.", {"composition": report["composition"]})

        yield self._running("avoid", plan)
        avoid = [r["label"] for r in report["composition"] if r["status"] == "high"]
        avoid += [CATEGORY_FR.get(g["category"], g["category"]) for g in report["duplicates"]
                  if CATEGORY_FR.get(g["category"], g["category"]) not in avoid]
        yield self._done("avoid", plan, ("N'achetez plus de : " + ", ".join(avoid) + ".") if avoid else "Rien à éviter.",
                         {"avoid": avoid})

        yield self._running("budget", plan)
        allocation = {}
        if budget and low:
            weights = {r["category"]: r["ideal"] - r["have"] for r in low}
            total = sum(weights.values())
            allocation = {CATEGORY_FR[c]: round(budget * w / total) for c, w in weights.items()}
        yield self._done("budget", plan, ("Budget : " + ", ".join(f"{k} {v} $" for k, v in allocation.items()))
                         if allocation else "Pas de budget indiqué — je montre les meilleures options.",
                         {"allocation": allocation})

        yield self._running("products", plan)
        suggestions = report["suggestions"]
        yield self._done("products", plan, f"{len(suggestions)} produit(s) proposé(s).", {"suggestions": suggestions})

        reasons = [f"Il vous manque {r['ideal'] - r['have']} {r['label']}." for r in low] or ["Votre garde-robe est complète."]
        if winter_gap:
            reasons.append("Aucune veste chaude pour l'hiver.")
        actions = ([f"N'achetez plus de {', '.join(avoid)} : vous en avez assez."] if avoid else []) + \
                  ([f"Répartition conseillée : {', '.join(f'{k} {v} $' for k, v in allocation.items())}."] if allocation else [])
        headline = "Votre liste d'achats utiles"
        answer = self._claude_summary(headline, reasons, actions) or " ".join(reasons + actions)
        yield {"type": "final", "mission": "shopping", "verdict": None, "headline": headline, "score": report["health"],
               "reasons": reasons, "actions": actions, "suggestions": suggestions, "answer": answer}

    def _declutter(self, wardrobe: List[Dict], profile: Dict) -> Iterator[Dict]:
        plan = [("analyze", "Analyser la garde-robe"),
                ("duplicates", "Trouver les doublons à garder / retirer"),
                ("orphans", "Trouver les pièces qui ne s'associent à rien"),
                ("report", "Préparer la liste de tri")]
        yield {"type": "start", "mission": "declutter", "mode": "local", "plan": [{"id": i, "title": t} for i, t in plan]}

        yield self._running("analyze", plan)
        report = self._insights(wardrobe, profile)
        if report["empty"]:
            yield {"type": "error", "message": "Votre garde-robe est vide."}
            return
        yield self._done("analyze", plan, f"{report['pieces']} pièces analysées.")

        yield self._running("duplicates", plan)
        dups = report["duplicates"]
        by_id = {w["id"]: w for w in wardrobe}
        to_remove = []
        for group in dups:
            keep = by_id.get(group["keep"], {})
            for extra_id in group["extra"]:
                piece = by_id.get(extra_id)
                if piece:
                    resale = FeatureSet.feature_25_resale_value(piece) if piece.get("price") else None
                    to_remove.append({"id": piece["id"], "name": piece["name"], "image_url": piece.get("image_url"),
                                      "category": piece.get("category"), "reason": f"Doublon de « {keep.get('name')} »",
                                      "resale": resale.get("estimated_resale") if resale else None})
        yield self._done("duplicates", plan, f"{len(to_remove)} pièce(s) en double à retirer.", {"duplicates": dups})

        yield self._running("orphans", plan)
        orphans = report["outfits"]["orphans"]
        yield self._done("orphans", plan, f"{report['outfits']['orphan_count']} pièce(s) difficile(s) à associer.",
                         {"orphans": orphans})

        yield self._running("report", plan)
        reasons = [f"{p['name']} — {p['reason']}" for p in to_remove[:6]]
        if orphans:
            reasons.append(f"{len(orphans)} pièce(s) ne s'associent à rien : gardez-les seulement si vous les portez.")
        actions = ["Revendez les pièces en bon état (Vinted, Leboncoin), donnez les autres.",
                   "Ne rachetez pas ces catégories avant d'avoir porté ce que vous gardez."] if to_remove else \
                  ["Rien à retirer : votre garde-robe ne contient pas de doublon."]
        headline = f"Tri de votre garde-robe — {len(to_remove)} pièce(s) à retirer"
        answer = self._claude_summary(headline, reasons, actions) or " ".join(reasons + actions)
        yield self._done("report", plan, "Liste prête.")
        yield {"type": "final", "mission": "declutter", "verdict": None, "headline": headline, "score": report["scores"]["uniqueness"],
               "reasons": reasons, "actions": actions, "duplicates": dups[:6], "to_remove": to_remove,
               "orphans": orphans, "suggestions": [], "answer": answer}

    # ------------------------------------------------------------------
    # Claude-driven mode (tool use) - events forwarded from a worker thread
    # ------------------------------------------------------------------

    MISSION_PROMPTS = {
        "audit": "Fais un diagnostic complet de ma garde-robe : santé, doublons, équilibre, couleurs, conseils.",
        "outfits": "Propose-moi des tenues avec mes pièces.",
        "shopping": "Que devrais-je acheter (et ne pas acheter) pour compléter ma garde-robe ?",
        "declutter": "Quelles pièces devrais-je revendre ou donner ?",
        "purchase": "Dois-je acheter cet article ?",
        "ask": "Aide-moi avec ma garde-robe.",
    }

    def _run_claude(self, mission: str, wardrobe: List[Dict], message: str, item: Dict,
                    image: Optional[str], budget: Optional[float], profile: Optional[Dict] = None,
                    history: Optional[List[Dict]] = None) -> Iterator[Dict]:
        events: "queue.Queue" = queue.Queue()
        profile = profile or {}
        prompt_parts = [message or self.MISSION_PROMPTS.get(mission, self.MISSION_PROMPTS["ask"])]
        if mission not in ("ask", "purchase"):
            prompt_parts.append(f"(Mission demandée : {mission})")
        if item:
            prompt_parts.append(f"Article indiqué : {json.dumps(item, ensure_ascii=False)}")
        if budget:
            prompt_parts.append(f"Budget : {budget}")
        if image:
            analysis = self.image_processor.process_image(image)
            if analysis.get("status") == "success":
                attrs = analysis["attributes"]
                prompt_parts.append("Photo fournie, attributs détectés par CLIP : " + json.dumps(
                    {k: attrs.get(k) for k in ("category", "category_confidence", "primary_color", "style", "material_appearance")}))
        prompt_parts.append("Réponds en français.")

        analyzed: List[Dict] = []  # items the LLM ran analyze_redundancy on
        cards: Dict = {}            # visuals collected from the tools the LLM called (outfits, products, duplicates)

        def on_step(step):
            if step["tool"] == "analyze_redundancy":
                analyzed.append(step["input"])
            for key, value in (step.get("cards") or {}).items():
                cards.setdefault(key, value)
            title, summary = self._describe_tool_step(step)
            events.put({"type": "step", "id": f"t{step['n']}", "title": title, "status": "done", "summary": summary})

        def worker():
            try:
                result = self.llm.run_agent("\n".join(prompt_parts), wardrobe, self.engine, image=image,
                                            on_step=on_step, profile=profile, history=history)
                final = {"type": "final", "mission": mission, "verdict": None,
                         "headline": f"Réponse de l'agent {self._llm_name()}",
                         "reasons": [], "actions": [], "suggestions": [], "answer": result["answer"],
                         "usage": result["usage"], **cards}
                insights = cards.get("insights")
                if insights and insights.get("health") is not None:
                    final["headline"] = f"Diagnostic — santé {insights['health']}/100"
                elif cards.get("outfits"):
                    final["headline"] = "Tenues proposées"
                elif cards.get("duplicates"):
                    final["headline"] = "Tri de votre garde-robe"
                elif cards.get("suggestions"):
                    final["headline"] = "Achats utiles"
                if analyzed:  # give the report the same visuals as the local agent (gauge, owned items, offers)
                    item = analyzed[-1]
                    check = self.engine.analyze(item, wardrobe, lang="fr")
                    final.update(verdict=check["recommendation"], score=check["redundancy_score"],
                                 headline=f"{self._llm_name()} — {item.get('name')}",
                                 similar_owned=check["similar_items"][:3],
                                 suggestions=check["catalog_matches"][:4])
                events.put(final)
            except Exception as e:  # surfaced to the client
                self.llm.handle_api_error(e)
                reason = self.llm.error if not self.llm.available else str(e)
                events.put({"type": "error", "message": f"{self._llm_name()} indisponible : {reason}"})
            finally:
                events.put(None)

        yield {"type": "start", "mission": mission, "mode": self.llm.provider, "model": self.llm.model, "plan": []}
        threading.Thread(target=worker, daemon=True).start()
        while True:
            event = events.get()
            if event is None:
                break
            yield event

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _claude_summary(self, headline: str, reasons: List[str], actions: List[str]) -> Optional[str]:
        """Optional: let Claude phrase the final answer (local decisions stay unchanged)"""
        if self.llm is None or not self.llm.available:
            return None
        try:
            return self.llm.summarize(headline, reasons, actions)
        except Exception as e:  # phrasing is optional - never lose the verdict over it
            logger.warning(f"LLM summary failed, keeping the local text: {e}")
            return None

    @staticmethod
    def _describe_tool_step(step: Dict):
        """Human-readable (French) title + summary for a tool call made by the LLM"""
        tool, args = step["tool"], step.get("input") or {}
        if tool == "analyze_redundancy":
            price = f" · {args['price']:g} $" if args.get("price") else ""
            details = " · ".join(str(args[k]) for k in ("category", "color", "material") if args.get(k))
            return "Chercher les doublons", f"{args.get('name')} ({details}){price}"
        if tool == "search_catalog":
            limit = f", max {args['max_price']:g} $" if args.get("max_price") else ""
            return "Chercher dans le catalogue", f"« {args.get('query')} »{limit}"
        if tool == "get_wardrobe":
            return "Lire la garde-robe", "Liste des pièces possédées"
        if tool == "get_wardrobe_insights":
            return "Diagnostiquer la garde-robe", "Santé, doublons, équilibre, couleurs, polyvalence"
        if tool == "suggest_outfits":
            return "Composer des tenues", f"Occasion : {args.get('occasion') or 'quotidien'}" + (
                f", saison : {args['season']}" if args.get("season") else "")
        if tool == "plan_shopping":
            return "Préparer la liste d'achats", f"Budget : {args['budget']:g} $" if args.get("budget") else "Sans budget"
        if tool == "plan_declutter":
            return "Préparer le tri", "Doublons et pièces orphelines"
        if tool == "list_features":
            return "Lister les analyses disponibles", "31 analyses"
        if tool == "run_feature":
            names = {17: "Harmonie des couleurs", 20: "Tendance", 23: "Qualité", 24: "Durabilité",
                     25: "Valeur de revente", 27: "Associations de tenues", 29: "Entretien", 31: "Prix du marché"}
            fid = int(args.get("feature_id") or 0)
            return f"Analyse : {names.get(fid, f'n° {fid}')}", f"feature {fid}"
        return tool, json.dumps(args, ensure_ascii=False)[:120]

    def _llm_name(self) -> str:
        return {"openai": "GPT", "claude": "Claude"}.get(getattr(self.llm, "provider", ""), "IA")

    @staticmethod
    def _title(step_id: str, plan) -> str:
        return dict(plan)[step_id]

    def _running(self, step_id, plan):
        return {"type": "step", "id": step_id, "title": self._title(step_id, plan), "status": "running"}

    def _done(self, step_id, plan, summary, data=None):
        return {"type": "step", "id": step_id, "title": self._title(step_id, plan), "status": "done",
                "summary": summary, "data": data or {}, "t": time.time()}

    def _skipped(self, step_id, plan, summary):
        return {"type": "step", "id": step_id, "title": self._title(step_id, plan), "status": "skipped", "summary": summary}

    @staticmethod
    def _fr_position(position: str) -> str:
        return {"budget": "petit prix", "mid-range": "milieu de gamme", "premium": "haut de gamme"}.get(position, position)

    @staticmethod
    def _describe_parsed(parsed: Dict, item: Optional[Dict]) -> str:
        found = {k: v for k, v in parsed.items() if k != "noun"}
        found.update({k: v for k, v in (item or {}).items() if v not in (None, "", 0)})
        if not found:
            return "Pas de description exploitable — je m'appuie sur la photo."
        colors = {c: forms[0] for c, forms in AutonomousAgent.COLOR_FORMS.items()}
        materials = {v: k for k, v in MATERIAL_WORDS.items()}
        styles = {v: k for k, v in STYLE_WORDS.items()}
        parts = []
        if found.get("category"):
            parts.append(CATEGORY_FR.get(found["category"], found["category"]))
        if found.get("color"):
            parts.append(f"couleur {colors.get(found['color'], found['color'])}")
        if found.get("material"):
            parts.append(f"en {materials.get(found['material'], found['material'])}")
        if found.get("style"):
            parts.append(f"style {styles.get(found['style'], found['style'])}")
        if found.get("price"):
            parts.append(f"prix {found['price']:g}")
        return "Compris : " + ", ".join(parts) + "."

    FEMININE = {"chemise", "robe", "veste", "chaussure", "chaussures", "basket", "baskets", "botte", "bottes",
                "bottine", "sandale", "ceinture", "montre", "écharpe", "casquette", "doudoune", "parka", "blouse",
                "cravate", "lunettes", "veste", "sacoche"}
    # colors named after nouns never agree ("des bottes orange", "des pulls marron")
    INVARIABLE_COLORS = {"orange", "kaki", "bordeaux", "marron", "camel", "crème", "bleu marine"}
    COLOR_FORMS = {  # english -> (masculine, feminine)
        "black": ("noir", "noire"), "white": ("blanc", "blanche"), "gray": ("gris", "grise"), "blue": ("bleu", "bleue"),
        "green": ("vert", "verte"), "purple": ("violet", "violette"), "navy": ("bleu marine", "bleu marine"),
        "red": ("rouge", "rouge"), "pink": ("rose", "rose"), "beige": ("beige", "beige"), "orange": ("orange", "orange"),
        "yellow": ("jaune", "jaune"), "khaki": ("kaki", "kaki"), "burgundy": ("bordeaux", "bordeaux"),
        "brown": ("marron", "marron"), "tan": ("camel", "camel"), "cream": ("crème", "crème"),
    }

    @staticmethod
    def _color_fr(color: str, noun: str) -> str:
        forms = AutonomousAgent.COLOR_FORMS.get(color)
        if not forms:
            return color or ""
        word = noun.lower()
        adjective = forms[1] if word in AutonomousAgent.FEMININE else forms[0]
        invariable = adjective in AutonomousAgent.INVARIABLE_COLORS
        if word.endswith("s") and not invariable and not adjective.endswith("s") and " " not in adjective:
            adjective += "s"
        return adjective

    @staticmethod
    def _name_for(item: Dict, noun: Optional[str]) -> str:
        nouns = {"shirts": "Haut", "pants": "Pantalon", "dresses": "Robe", "shoes": "Chaussures",
                 "outerwear": "Veste", "accessories": "Accessoire"}
        base = (noun or nouns.get(item["category"], "Article")).capitalize()
        material_fr = {v: k for k, v in MATERIAL_WORDS.items()}
        color = AutonomousAgent._color_fr(item.get("color"), base) if item.get("color") not in (None, "unknown") else ""
        material = material_fr.get(item.get("material"), "")
        return " ".join(p for p in (base, color, f"en {material}" if material else "") if p).strip()
