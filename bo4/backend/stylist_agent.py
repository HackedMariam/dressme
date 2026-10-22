"""Stylist Agent BO4 (I79 + I80) orchestré avec LangGraph.

Graphe :

    START -> extract_intent --(occasion inconnue)--> clarify -> END
                    |      +--(retour « j'aime la 2 »)--> record_feedback (I76) --> END
                    |                                       +--(« je n'aime pas la 1 »)--> get_weather
                    v
             get_weather (I71 : Open-Meteo, prévision de la ville et du jour demandés)
                    |
                    v
             fetch_wardrobe (BO1, GET /api/items) --(BO1 indisponible)--> respond
                    |
                    v
             apply_constraints (I84 : contraintes obligatoires)
                    |
                    v
             recommend (BO4 : outfit_engine.recommend_outfits, I78 : régénération,
                        I77 : bonus de personnalisation d'après les retours)
                    |
                    v
             respond -> END

Garanties :
- Le LLM (Ollama, local) sert UNIQUEMENT à extraire l'intention en JSON. Un extracteur
  à règles prend le relais si Ollama est indisponible ou renvoie un JSON invalide.
- La réponse est construite à partir des tenues classées par BO4, elles-mêmes composées
  uniquement de vêtements lus dans BO1 : l'agent ne peut pas inventer de vêtement.
- La mémoire de conversation (occasion, contraintes, tenues déjà montrées) est gérée
  par le checkpointer LangGraph, par fil de discussion (thread_id).
- BO5 (RAG) n'est pas encore branché : aucun appel n'est simulé.

Utilisation (PowerShell, depuis backend/) :
    .\\.venv\\Scripts\\python.exe stylist_agent.py --graph            # schéma Mermaid
    .\\.venv\\Scripts\\python.exe stylist_agent.py --trace            # chat + trace des nodes
    .\\.venv\\Scripts\\python.exe stylist_agent.py --fallback tests\\fixtures\\bo1_items_sample.json
    Options : --no-llm (règles seules), --no-weather (saison selon la date), --city Paris
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict

import bo1_api_adapter
import stylist_feedback

OCCASIONS = ("university", "work", "evening", "casual")
SEASONS = ("spring", "summer", "autumn", "winter")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("STYLIST_LLM_MODEL", "qwen2.5:3b")
DEFAULT_CITY = os.environ.get("STYLIST_CITY", "Tunis")
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# « à Paris », « in London »… sur le message d'origine (majuscule obligatoire).
CITY_PATTERN = r"(?:^|\s)(?:à|a|au|in)\s+([A-ZÀ-Ý][\w'-]+(?:[\s-][A-ZÀ-Ý][\w'-]+)?)"
CITY_STOPWORDS = {"esprit", "demain", "midi", "minuit"}
RAIN_ALERT = 60  # probabilité de pluie (%) à partir de laquelle on prévient

# Groupes de vêtements qu'on peut exclure, exprimés en catégories BO4.
EXCLUDABLE_CATEGORIES = {
    "outerwear": {"jacket", "blazer", "coat", "cardigan"},
    "dress": {"dress"},
    "skirt": {"skirt"},
    "shorts": {"shorts"},
    "jeans": {"jeans"},
}

COLOR_WORDS = {
    "noir": "black", "black": "black", "blanc": "white", "white": "white",
    "gris": "grey", "grey": "grey", "gray": "grey", "rouge": "red", "red": "red",
    "bleu": "blue", "blue": "blue", "rose": "pink", "pink": "pink",
    "vert": "green", "green": "green", "beige": "beige", "marron": "brown",
    "brown": "brown", "jaune": "yellow", "yellow": "yellow", "violet": "purple",
    "purple": "purple", "orange": "orange", "bordeaux": "burgundy", "burgundy": "burgundy",
}
COLOR_ALIASES = {"grey": {"grey", "gray"}}

CATEGORY_WORDS = {
    "veste": "outerwear", "vestes": "outerwear", "blazer": "outerwear", "manteau": "outerwear",
    "doudoune": "outerwear", "jacket": "outerwear", "jackets": "outerwear", "coat": "outerwear",
    "robe": "dress", "robes": "dress", "dress": "dress", "dresses": "dress",
    "jupe": "skirt", "jupes": "skirt", "skirt": "skirt",
    "short": "shorts", "shorts": "shorts",
    "jean": "jeans", "jeans": "jeans",
}
# Contraintes comprises mais pas encore gérées par le moteur BO4 (pas de chaussures).
UNSUPPORTED_WORDS = {
    "talon": "chaussures", "talons": "chaussures", "heels": "chaussures",
    "chaussure": "chaussures", "chaussures": "chaussures", "shoes": "chaussures",
    "baskets": "chaussures", "sneakers": "chaussures", "bottes": "chaussures",
    "sac": "accessoires", "bijoux": "accessoires", "accessoires": "accessoires",
}

OCCASION_PATTERNS = {
    "work": r"\b(travail|bureau|boulot|entretien|reunion|professionnel\w*|stage|soutenance|"
            r"work|office|interview|meeting|business)\b",
    "university": r"\b(universite|univ|fac|cours|ecole|campus|classe|examen|university|college|class)\b",
    "evening": r"\b(soiree|fete|diner|mariage|anniversaire|rendez[- ]vous|gala|party|"
               r"date night|wedding|dinner|evening)\b",
    "casual": r"\b(decontracte\w*|week[- ]?end|balade|promenade|shopping|detente|casual|"
              r"sortie entre amis)\b",
}
# Mots-clés d'occasion ambigus : seuls, ils ne priment pas sur une autre occasion proposée par le LLM
# (« rendez-vous avec la DRH » n'est pas une soirée, « meeting my girlfriend's parents » n'est pas du travail).
AMBIGUOUS_OCCASION_WORDS = {"rendez-vous", "meeting"}
SEASON_PATTERNS = {
    "winter": r"\b(hiver|winter|il fait froid|froid|neige|snow|cold)\b",
    "summer": r"\b(en ete|cet ete|l'ete|d'ete|summer|canicule|il fait chaud)\b",
    "spring": r"\b(printemps|spring)\b",
    "autumn": r"\b(automne|autumn|fall)\b",
}
# Retour sur une tenue proposée : « j'aime la 2 », « je n'aime pas la tenue 1 ».
DISLIKE_WORDS = r"je n'aime pas|j'aime pas|pas fan|pas pour moi|pas convaincue?|bof|dislike|nul"
LIKE_WORDS = r"j'aime bien|j'aime|j'adore|me plait|like|parfait|super|valide"
# Rang d'une tenue : chiffre ou ordinal (texte déjà sans accents). « derniere » dépend du tour précédent.
RANK_WORDS = r"\d|premiere|deuxieme|troisieme|derniere"
ORDINAL_RANKS = {"premiere": 1, "deuxieme": 2, "troisieme": 3}
DISLIKE_PATTERN = rf"\b({DISLIKE_WORDS})\b\D{{0,25}}?\b({RANK_WORDS})\b"
LIKE_PATTERN = rf"\b({LIKE_WORDS})\b\D{{0,25}}?\b({RANK_WORDS})\b"
# Rang avant le verdict : « la 2 me plait », « la 3, bof ».
DISLIKE_AFTER_RANK = rf"\b({RANK_WORDS})\b\D{{0,15}}?\b({DISLIKE_WORDS})\b"
LIKE_AFTER_RANK = rf"\b({RANK_WORDS})\b\D{{0,15}}?\b({LIKE_WORDS})\b"
ANOTHER_PATTERN = (r"\b(une autre|un autre|autre tenue|autre chose|autres propositions|"
                   r"another|something else|je n'aime pas|pas celle|change|tu as mieux)\b")
# Dress code (I83) : niveau exigé, déduit du message ou de l'occasion.
DRESS_CODE_PATTERNS = {
    "formal": r"\b(formel\w*|tres habille\w*|habille\w*|gala|mariage|ceremonie|black tie|formal|wedding)\b",
    "business": r"\b(entretien|interview|soutenance|jury|business|costume|professionnel\w*)\b",
    "smart_casual": r"\b(smart casual|chic decontracte\w*|chic)\b",
    "casual": r"\b(decontracte\w*|casual|detendu\w*)\b",
}
DEFAULT_DRESS_CODE = {"university": "casual", "work": "smart_casual", "evening": "smart_casual",
                      "casual": "casual"}
# (formalité moyenne minimale de la tenue, formalité minimale de chaque pièce), échelle BO1 1..5.
DRESS_CODE_RULES = {"casual": (None, None), "smart_casual": (2.5, None), "business": (3.0, 2),
                    "formal": (4.0, 3)}
NEGATION_PATTERN = (r"\b(?:(?:sans|pas de|rien de|aucune?|ni|no|without|not|nor)\s+|pas d'"
                    r"|evite[rz]?\s+(?:(?:le|la|les|de|des)\s+|l')?)"
                    r"(\w+)")


# --------------------------------------------------------------------------------------
# État du graphe
# --------------------------------------------------------------------------------------
class StylistState(TypedDict, total=False):
    user_message: str                 # message du tour courant
    history: list[dict]               # [{"role": "user"|"assistant", "content": str}]
    request: dict                     # occasion, season, contraintes (mémorisé entre tours)
    wardrobe: list[dict]              # vêtements BO4 issus de BO1
    wardrobe_report: dict
    candidates: list[dict]            # vêtements restants après contraintes
    excluded: list[str]               # noms des vêtements exclus par les contraintes
    outfits: list[dict]               # tenues retenues pour ce tour
    shown: list[list[str]]            # tenues déjà proposées (ids), pour la régénération
    last_outfits: list[list[str]]     # tenues du dernier tour proposant des tenues (rang 1, 2, 3)
    feedback_note: str                # accusé de réception d'un retour (I76)
    dress_code_relaxed: bool         # aucune tenue conforme : on montre les plus proches
    weather: dict                     # prévision utilisée au dernier tour (si disponible)
    advice: dict                      # conseil BO5 du tour : {"question", "answer", "sources"}
    error: str
    response: str
    trace: list[str]                  # journal des nodes du tour courant


# --------------------------------------------------------------------------------------
# Extraction d'intention
# --------------------------------------------------------------------------------------
def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).replace("’", "'")


def _first_match(text: str, patterns: dict[str, str]) -> Optional[str]:
    best: tuple[int, str] | None = None
    for label, pattern in patterns.items():
        match = re.search(pattern, text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), label)
    return best[1] if best else None


def _rank(word: str, last_count: Optional[int] = None) -> int:
    """Chiffre, ordinal, ou « derniere » = rang le plus élevé du tour précédent (sinon 3)."""
    if word.isdigit():
        return int(word)
    if word == "derniere":
        return last_count or 3
    return ORDINAL_RANKS[word]


def extract_feedback(text: str, last_count: Optional[int] = None) -> Optional[dict]:
    """Retour sur une tenue numérotée (texte déjà normalisé par _plain)."""
    for verdict, before, after in (("dislike", DISLIKE_PATTERN, DISLIKE_AFTER_RANK),
                                   ("like", LIKE_PATTERN, LIKE_AFTER_RANK)):
        match = re.search(before, text)
        if match:
            return {"verdict": verdict, "rank": _rank(match.group(2), last_count)}
        match = re.search(after, text)
        if match:
            return {"verdict": verdict, "rank": _rank(match.group(1), last_count)}
    return None


def _occasion_matches(text: str) -> list[tuple[int, str, str]]:
    """Tous les mots-clés d'occasion trouvés : (position, occasion, mot)."""
    found = []
    for label, pattern in OCCASION_PATTERNS.items():
        for match in re.finditer(pattern, text):
            found.append((match.start(), label, match.group(0).replace(" ", "-")))
    return sorted(found)


def extract_city(message: str) -> Optional[str]:
    match = re.search(CITY_PATTERN, message)
    if not match or _plain(match.group(1)) in CITY_STOPWORDS:
        return None
    return match.group(1)


def extract_with_rules(message: str, last_count: Optional[int] = None) -> dict:
    """Extraction déterministe (FR/EN) : sert de secours et de garde-fou au LLM.
    `last_count` : nombre de tenues proposées au tour précédent (pour « la dernière »)."""
    text = _plain(message)
    occasion_matches = _occasion_matches(text)
    result: dict[str, Any] = {
        "occasion": _first_match(text, OCCASION_PATTERNS),
        # Mot-clé ayant donné l'occasion, et vrai si TOUS les mots-clés trouvés sont ambigus.
        "occasion_keyword": occasion_matches[0][2] if occasion_matches else None,
        "occasion_ambiguous": bool(occasion_matches)
                              and all(word in AMBIGUOUS_OCCASION_WORDS for _, _, word in occasion_matches),
        "season": _first_match(text, SEASON_PATTERNS),
        "when": "tomorrow" if re.search(r"\b(demain|tomorrow)\b", text)
        else "today" if re.search(r"\b(aujourd'hui|ce soir|today|tonight)\b", text) else None,
        "exclude_categories": [],
        "exclude_colors": [],
        "unsupported": [],
        "wants_another": bool(re.search(ANOTHER_PATTERN, text)),
        "dress_code": _first_match(text, DRESS_CODE_PATTERNS),
        "city": extract_city(message),
        "feedback": extract_feedback(text, last_count),
    }
    if result["feedback"] and result["feedback"]["verdict"] == "dislike":
        result["wants_another"] = True
    for match in re.finditer(NEGATION_PATTERN, text):
        for word in match.group(1).split():
            if word in CATEGORY_WORDS and CATEGORY_WORDS[word] not in result["exclude_categories"]:
                result["exclude_categories"].append(CATEGORY_WORDS[word])
            elif word in COLOR_WORDS and COLOR_WORDS[word] not in result["exclude_colors"]:
                result["exclude_colors"].append(COLOR_WORDS[word])
            elif word in UNSUPPORTED_WORDS and word not in result["unsupported"]:
                result["unsupported"].append(word)
    return result


LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "occasion": {"type": ["string", "null"], "enum": [*OCCASIONS, None]},
        "season": {"type": ["string", "null"], "enum": [*SEASONS, None]},
        "exclude_categories": {"type": "array", "items": {"type": "string",
                                                          "enum": list(EXCLUDABLE_CATEGORIES)}},
        "exclude_colors": {"type": "array", "items": {"type": "string"}},
        "wants_another": {"type": "boolean"},
    },
    "required": ["occasion", "season", "exclude_categories", "exclude_colors", "wants_another"],
}

LLM_SYSTEM_PROMPT = (
    "Tu extrais la demande vestimentaire d'un utilisateur en JSON. "
    "occasion : university (cours, fac), work (travail, entretien, réunion, stage), "
    "evening (soirée, fête, dîner, mariage), casual (week-end, balade, shopping), "
    "ou null si l'occasion n'est pas mentionnée. Ne devine jamais l'occasion. "
    "season : spring, summer, autumn, winter, ou null si elle n'est pas mentionnée. "
    "exclude_categories : parmi outerwear, dress, skirt, shorts, jeans, seulement si "
    "l'utilisateur les refuse explicitement. exclude_colors : couleurs refusées, en anglais. "
    "wants_another : true si l'utilisateur rejette la proposition précédente ou en veut une autre. "
    "Réponds uniquement avec le JSON."
)


def ollama_extract(message: str, timeout: float = 60.0) -> Optional[dict]:
    """Extraction par LLM local (Ollama, sortie JSON contrainte). None en cas d'échec."""
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": LLM_SCHEMA,
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": LLM_SYSTEM_PROMPT},
                     {"role": "user", "content": message}],
    }
    request = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return json.loads(payload["message"]["content"])
    except Exception:  # Ollama arrêté, modèle absent, JSON invalide...
        return None


def validate_llm_output(raw: Any) -> Optional[dict]:
    """Ne garde que les valeurs autorisées : le LLM ne peut rien injecter d'autre."""
    if not isinstance(raw, dict):
        return None
    occasion = raw.get("occasion") if raw.get("occasion") in OCCASIONS else None
    season = raw.get("season") if raw.get("season") in SEASONS else None
    categories = [c for c in raw.get("exclude_categories") or [] if c in EXCLUDABLE_CATEGORIES]
    colors = [COLOR_WORDS[c] for c in (str(x).lower() for x in raw.get("exclude_colors") or [])
              if c in COLOR_WORDS]
    return {"occasion": occasion, "season": season, "exclude_categories": categories,
            "exclude_colors": colors, "wants_another": raw.get("wants_another") is True}


NEGATION_CUES = r"\b(sans|pas|rien|aucune?|ni|no|without|not|nor|never|jamais|evite[rz]?)\b|\bpas d'"
SEASON_CUES = (r"\b(hiver|winter|ete|summer|printemps|spring|automne|autumn|fall|froid|chaud|"
               r"neige|canicule|pluie|cold|hot|snow|rain)\b")
# « aime » seul n'est plus un indice (« j'aime bien la premiere » n'est pas un rejet).
ANOTHER_CUES = (r"\bn'aime\b|\baime pas\b|\bpas convaincue?\b|"
                r"\b(mieux|autres?|change\w*|different\w*|another|else|other)\b")


def ground_llm_output(clean: dict, message: str) -> tuple[dict, list[str]]:
    """Garde-fou anti-hallucination : une valeur proposée par le LLM n'est acceptée que si
    le message contient un indice correspondant. L'occasion reste libre (c'est l'apport du LLM),
    mais les contraintes, qui RETIRENT des vêtements, doivent être explicitement demandées."""
    text = _plain(message)
    words = set(re.findall(r"\w+", text))
    negated = bool(re.search(NEGATION_CUES, text))
    grounded, rejected = dict(clean), []

    categories = []
    for category in clean["exclude_categories"]:
        if negated and any(CATEGORY_WORDS.get(w) == category for w in words):
            categories.append(category)
        else:
            rejected.append(f"exclusion {category}")
    colors = []
    for color in clean["exclude_colors"]:
        if negated and any(COLOR_WORDS.get(w) == color for w in words):
            colors.append(color)
        else:
            rejected.append(f"exclusion couleur {color}")
    grounded["exclude_categories"], grounded["exclude_colors"] = categories, colors

    if clean["season"] and not re.search(SEASON_CUES, text):
        rejected.append(f"saison {clean['season']}")
        grounded["season"] = None
    if clean["wants_another"] and not re.search(ANOTHER_CUES, text):
        rejected.append("demande d'une autre tenue")
        grounded["wants_another"] = False
    return grounded, rejected


def dress_code_check(items: list[dict], code: Optional[str]) -> tuple[bool, Optional[float]]:
    """Vérifie une tenue contre un dress code avec le champ `formality` (1..5) fourni par BO1.
    Renvoie (conforme, formalité moyenne). Sans aucune formalité connue : non vérifiable, accepté."""
    levels = [item["formality"] for item in items
              if isinstance(item.get("formality"), (int, float)) and not isinstance(item.get("formality"), bool)]
    if not levels:
        return True, None
    mean = sum(levels) / len(levels)
    if not code:
        return True, round(mean, 1)
    min_mean, min_item = DRESS_CODE_RULES[code]
    ok = (min_mean is None or mean >= min_mean) and (min_item is None or min(levels) >= min_item)
    return ok, round(mean, 1)


class WeatherError(RuntimeError):
    """Prévision météo indisponible (réseau, ville inconnue, jour hors prévision)."""


def _get_json(url: str, params: dict, timeout: float) -> dict:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def open_meteo_forecast(city: str, day: dt.date, timeout: float = 6.0) -> dict:
    """Prévision journalière Open-Meteo (gratuit, sans clé) pour une ville et un jour."""
    try:
        places = _get_json(GEOCODING_URL, {"name": city, "count": 1, "language": "fr", "format": "json"},
                           timeout).get("results") or []
        if not places:
            raise WeatherError(f"ville inconnue : {city}")
        place = places[0]
        daily = _get_json(FORECAST_URL, {
            "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto",
            "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max",
            "forecast_days": 7}, timeout)["daily"]
        index = daily["time"].index(day.isoformat())
    except WeatherError:
        raise
    except ValueError as exc:
        raise WeatherError(f"pas de prévision pour le {day.isoformat()}") from exc
    except Exception as exc:  # réseau, JSON inattendu...
        raise WeatherError(f"Open-Meteo injoignable : {exc}") from exc
    rain = (daily.get("precipitation_probability_max") or [None] * len(daily["time"]))[index]
    return {"city": place.get("name", city), "date": day.isoformat(),
            "t_min": daily["temperature_2m_min"][index], "t_max": daily["temperature_2m_max"][index],
            "rain_probability": rain}


def season_from_temperature(t_min: float, t_max: float, month: int) -> str:
    """Traduit la température prévue en « saison » comprise par le moteur BO4.
    Moyenne <= 10 °C : hiver ; >= 22 °C : été ; sinon mi-saison (printemps ou automne selon le mois)."""
    mean = (t_min + t_max) / 2
    if mean <= 10:
        return "winter"
    if mean >= 22:
        return "summer"
    return "spring" if 3 <= month <= 8 else "autumn"


def merge_occasion(rules: dict, llm_occasion: Optional[str]) -> Optional[str]:
    """Occasion des règles en priorité, sauf si elle ne repose que sur un mot-clé ambigu
    (rendez-vous, meeting) et que le LLM propose une autre occasion valide."""
    occasion = rules.get("occasion")
    if (occasion and rules.get("occasion_ambiguous") and llm_occasion in OCCASIONS
            and llm_occasion != occasion):
        return llm_occasion
    return occasion or llm_occasion


def season_for(date: dt.date) -> str:
    """Saison météorologique de l'hémisphère nord (pas de météo réelle : I71 non implémenté)."""
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(date.month, "autumn")


def _union(*lists: list) -> list:
    out: list = []
    for values in lists:
        for value in values or []:
            if value not in out:
                out.append(value)
    return out


# --------------------------------------------------------------------------------------
# Nodes (fonctions pures sur l'état : testables sans LangGraph)
# --------------------------------------------------------------------------------------
def make_nodes(llm: Optional[Callable[[str], Any]] = ollama_extract,
               wardrobe_loader: Optional[Callable[[], tuple[list[dict], dict]]] = None,
               engine: Any = None,
               today: Optional[Callable[[], dt.date]] = None,
               weather: Optional[Callable[[str, dt.date], dict]] = None,
               default_city: str = DEFAULT_CITY,
               feedback_store: Optional[stylist_feedback.FeedbackStore] = None,
               advice: Optional[Callable[[str], dict]] = None) -> dict[str, Callable]:
    if wardrobe_loader is None:
        wardrobe_loader = bo1_api_adapter.load_wardrobe_from_bo1
    if engine is None:
        import outfit_engine as engine  # noqa: PLW0127 (import paresseux)
    today = today or dt.date.today
    weather_cache: dict[tuple[str, str], dict] = {}

    def extract_intent(state: StylistState) -> dict:
        message = state["user_message"]
        rules = extract_with_rules(message, len(state.get("last_outfits") or []) or None)
        llm_result = validate_llm_output(llm(message)) if llm else None
        source = "llm+règles" if llm_result else "règles"
        rejected: list[str] = []
        if llm_result:
            llm_result, rejected = ground_llm_output(llm_result, message)
            if rejected:
                source += f", LLM ignoré pour : {', '.join(rejected)}"
        llm_result = llm_result or {}

        previous = state.get("request") or {}
        wants_another = rules["wants_another"] or llm_result.get("wants_another", False)
        occasion = merge_occasion(rules, llm_result.get("occasion")) or previous.get("occasion")
        explicit_season = rules["season"] or llm_result.get("season")
        when = rules["when"] or previous.get("when")
        if explicit_season:
            season, season_source = explicit_season, "demandée"
        elif previous.get("season_source") == "demandée":
            season, season_source = previous["season"], "demandée"
        else:
            day = today() + dt.timedelta(days=1 if when == "tomorrow" else 0)
            season, season_source = season_for(day), "déduite de la date"

        if rules["dress_code"]:
            dress_code, dress_code_source = rules["dress_code"], "déduit du message"
        elif (previous.get("dress_code_source") == "déduit du message"
              and occasion == previous.get("occasion")):
            dress_code, dress_code_source = previous["dress_code"], "déduit du message"
        else:
            dress_code = DEFAULT_DRESS_CODE.get(occasion)
            dress_code_source = "par défaut pour l'occasion"

        request = {
            "occasion": occasion,
            "dress_code": dress_code,
            "dress_code_source": dress_code_source,
            "season": season,
            "season_source": season_source,
            "when": when,
            "city": rules["city"] or previous.get("city"),
            "exclude_categories": _union(previous.get("exclude_categories"),
                                         rules["exclude_categories"],
                                         llm_result.get("exclude_categories")),
            "exclude_colors": _union(previous.get("exclude_colors"), rules["exclude_colors"],
                                     llm_result.get("exclude_colors")),
            "unsupported": _union(previous.get("unsupported"), rules["unsupported"]),
            "unsupported_now": rules["unsupported"],
            "wants_another": wants_another,
            "feedback": rules["feedback"],
        }
        history = list(state.get("history") or []) + [{"role": "user", "content": message}]
        summary = {k: request[k] for k in ("occasion", "season", "dress_code", "exclude_categories",
                                           "exclude_colors", "unsupported", "wants_another")}
        return {"request": request, "history": history, "error": "",
                "trace": [f"extract_intent [{source}] -> {summary}"]}

    def record_feedback(state: StylistState) -> dict:
        request = state["request"]
        feedback = request["feedback"]
        last = state.get("last_outfits") or []
        rank, verdict = feedback["rank"], feedback["verdict"]
        trace = state.get("trace", [])
        verb = "aimes" if verdict == "like" else "n'aimes pas"
        if not 1 <= rank <= len(last):
            note = f"Je ne trouve pas de tenue n° {rank} dans mes dernières propositions."
            line = f"record_feedback -> rang {rank} introuvable ({len(last)} tenue(s) proposée(s))"
        elif feedback_store is None:
            note = f"C'est noté pour la tenue {rank}, mais l'enregistrement des retours est désactivé."
            line = "record_feedback -> stockage désactivé"
        else:
            by_id = {str(item["id"]): item for item in state.get("wardrobe") or []}
            items = [by_id[i] for i in last[rank - 1] if i in by_id]
            feedback_store.add(verdict, items, request.get("occasion"))
            labels = display_names(state.get("wardrobe") or [])
            names = " + ".join(labels[str(item["id"])] for item in items)
            note = f"C'est noté : tu {verb} la tenue {rank} ({names})."
            if verdict == "like":
                note += " Tes prochaines propositions en tiendront compte."
            line = f"record_feedback -> {verdict} enregistré pour la tenue {rank} : {names}"
        history = list(state.get("history") or []) + [{"role": "assistant", "content": note}]
        return {"feedback_note": note, "response": note, "history": history, "outfits": [],
                "trace": trace + [line]}

    def clarify(state: StylistState) -> dict:
        question = ("Pour quelle occasion veux-tu cette tenue ? Par exemple : cours à l'université, "
                    "travail ou entretien, soirée, ou sortie décontractée.")
        history = list(state.get("history") or []) + [{"role": "assistant", "content": question}]
        return {"response": question, "history": history, "outfits": [],
                "trace": state.get("trace", []) + ["clarify -> question posée (occasion manquante)"]}

    def get_weather(state: StylistState) -> dict:
        request = dict(state["request"])
        trace = state.get("trace", [])
        if request["season_source"] == "demandée":
            return {"weather": {}, "trace": trace + ["get_weather -> saison demandée explicitement : pas d'appel"]}
        if weather is None:
            return {"weather": {}, "trace": trace + ["get_weather -> météo désactivée : saison déduite de la date"]}
        day = today() + dt.timedelta(days=1 if request.get("when") == "tomorrow" else 0)
        city = request.get("city") or default_city
        key = (city.lower(), day.isoformat())
        try:
            forecast = weather_cache.get(key) or weather(city, day)
        except Exception as exc:  # WeatherError ou erreur inattendue : on garde la saison de la date
            return {"weather": {}, "trace": trace + [f"get_weather -> indisponible ({exc}) : saison déduite de la date"]}
        weather_cache[key] = forecast
        season = season_from_temperature(forecast["t_min"], forecast["t_max"], day.month)
        request["season"] = season
        request["season_source"] = (f"météo {forecast['city']} le {day:%d/%m} : "
                                    f"{forecast['t_min']:.0f} à {forecast['t_max']:.0f} °C")
        line = (f"get_weather -> Open-Meteo {forecast['city']} {day.isoformat()} : "
                f"{forecast['t_min']}-{forecast['t_max']} °C, pluie {forecast.get('rain_probability')} % "
                f"=> saison {season}")
        return {"request": request, "weather": forecast, "trace": trace + [line]}

    def fetch_wardrobe(state: StylistState) -> dict:
        try:
            wardrobe, report = wardrobe_loader()
        except bo1_api_adapter.BO1UnavailableError as exc:
            return {"error": f"Je n'arrive pas à lire ta garde-robe (BO1) : {exc}",
                    "wardrobe": [], "wardrobe_report": {},
                    "trace": state.get("trace", []) + [f"fetch_wardrobe -> ERREUR BO1 : {exc}"]}
        line = (f"fetch_wardrobe -> {report.get('kept')} vêtements utilisables sur "
                f"{report.get('received')} (source : {report.get('source', 'BO1')})")
        return {"wardrobe": wardrobe, "wardrobe_report": report,
                "trace": state.get("trace", []) + [line]}

    def apply_constraints(state: StylistState) -> dict:
        request = state["request"]
        banned_categories = set().union(*(EXCLUDABLE_CATEGORIES[c]
                                          for c in request["exclude_categories"]))
        banned_colors = set().union(*(COLOR_ALIASES.get(c, {c}) for c in request["exclude_colors"]))
        candidates, excluded = [], []
        for item in state.get("wardrobe") or []:
            color_tokens = set(re.split(r"[\s_]+", str(item.get("color", "")).lower()))
            if item.get("category") in banned_categories or color_tokens & banned_colors:
                excluded.append(item["name"])
            else:
                candidates.append(item)
        line = f"apply_constraints -> {len(candidates)} gardés, {len(excluded)} exclus {excluded}"
        return {"candidates": candidates, "excluded": excluded,
                "trace": state.get("trace", []) + [line]}

    def recommend(state: StylistState) -> dict:
        request = state["request"]
        shown = [list(ids) for ids in (state.get("shown") or [])] if request["wants_another"] else []
        already = {frozenset(ids) for ids in shown}
        try:
            ranked = engine.recommend_outfits(state.get("candidates") or [],
                                              occasion=request["occasion"],
                                              season=request["season"], top_k=30)
        except ValueError as exc:
            ranked = []
            state_trace = f"recommend -> ERREUR moteur : {exc}"
        else:
            state_trace = None
        code = request.get("dress_code")
        candidates = state.get("candidates") or []
        profile = feedback_store.profile() if feedback_store else None
        rejected = feedback_store.disliked_outfits() if feedback_store else set()
        annotated = []
        for outfit in ranked:
            ids = frozenset(_outfit_ids(outfit))
            if ids in already or ids in rejected:
                continue
            items = _outfit_items(outfit, candidates)
            ok, level = dress_code_check(items, code)
            bonus = stylist_feedback.personal_bonus(items, profile)
            annotated.append({**outfit, "dress_code_ok": ok, "formality": level, "personal_bonus": bonus,
                              "personal_score": round(float(outfit["score"]) + bonus, 1)})
        # Tri stable : à score personnalisé égal, l'ordre du moteur BO4 est conservé.
        annotated.sort(key=lambda o: -o["personal_score"])
        compliant = [o for o in annotated if o["dress_code_ok"]]
        relaxed = bool(annotated) and not compliant
        fresh = diversify(compliant or annotated, k=3)
        shown = shown + [sorted(_outfit_ids(o)) for o in fresh]
        line = state_trace or (f"recommend -> {len(ranked)} tenues classées par BO4, dress code {code} : "
                               f"{len(compliant)}/{len(annotated)} conformes, {len(fresh)} retenues "
                               f"(déjà montrées : {len(already)}, rejetées : {len(rejected)}, "
                               f"profil : {profile['likes'] if profile else 0} like / "
                               f"{profile['dislikes'] if profile else 0} dislike)")
        return {"outfits": fresh, "shown": shown, "dress_code_relaxed": relaxed,
                "last_outfits": [_outfit_ids(o) for o in fresh] or state.get("last_outfits", []),
                "trace": state.get("trace", []) + [line]}

    def style_advice(state: StylistState) -> dict:
        """BO5 (RAG), optionnel : un conseil de style sur la tenue n° 1. Ne choisit jamais de
        vêtement ; en cas d'échec, la réponse continue sans conseil."""
        trace = state.get("trace", [])
        if advice is None:
            return {"advice": {}, "trace": trace + ["style_advice -> BO5 désactivé"]}
        outfits = state.get("outfits") or []
        if not outfits:
            return {"advice": {}, "trace": trace + ["style_advice -> aucune tenue, pas de conseil"]}
        question = advice_question(state)
        try:
            result = advice(question)
            answer = str(result.get("answer") or "").strip()
            sources = [str(s) for s in result.get("sources") or []]
        except Exception as exc:  # BO5 arrêté, HTTP, JSON inattendu, faux client de test...
            return {"advice": {}, "trace": trace + [f"style_advice -> BO5 indisponible ({exc})"]}
        if not answer:
            return {"advice": {}, "trace": trace + ["style_advice -> BO5 n'a pas renvoyé de conseil"]}
        return {"advice": {"question": question, "answer": answer, "sources": sources},
                "trace": trace + [f"style_advice -> conseil BO5 reçu ({len(sources)} source(s))"]}

    def respond(state: StylistState) -> dict:
        text = format_response(state)
        history = list(state.get("history") or []) + [{"role": "assistant", "content": text}]
        return {"response": text, "history": history,
                "trace": state.get("trace", []) + ["respond -> réponse construite depuis les tenues BO4"]}

    return {"extract_intent": extract_intent, "record_feedback": record_feedback, "clarify": clarify,
            "get_weather": get_weather,
            "fetch_wardrobe": fetch_wardrobe,
            "apply_constraints": apply_constraints, "recommend": recommend,
            "style_advice": style_advice, "respond": respond}


def route_after_intent(state: StylistState) -> str:
    request = state["request"]
    if request.get("feedback"):
        return "record_feedback"
    return "clarify" if not request.get("occasion") else "get_weather"


def route_after_feedback(state: StylistState) -> str:
    request = state["request"]
    return "get_weather" if request["wants_another"] and request.get("occasion") else "end"


def route_after_fetch(state: StylistState) -> str:
    return "respond" if state.get("error") else "apply_constraints"


def _outfit_ids(outfit: dict) -> list[str]:
    return [str(item["id"]) if isinstance(item, dict) else str(item) for item in outfit.get("items", [])]


MAX_OVERLAP = 0.5  # I89 : part maximale de pièces communes entre deux tenues proposées ensemble
MIN_PROPOSALS = 2  # I89 : on ne complète avec des tenues trop proches que jusqu'à ce minimum


def overlap(a: list[str], b: list[str]) -> float:
    """Part de pièces communes, rapportée à la plus petite tenue (1.0 = l'une contient l'autre)."""
    a, b = set(a), set(b)
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def diversify(outfits: list[dict], k: int = 3, max_overlap: float = MAX_OVERLAP,
              min_proposals: int = MIN_PROPOSALS) -> list[dict]:
    """I89 : sélection gloutonne dans l'ordre du classement. Une tenue trop proche d'une tenue
    déjà retenue est repoussée ; on ne complète avec elle que jusqu'à `min_proposals` tenues :
    mieux vaut 2 tenues vraiment différentes que 3 presque identiques.
    Le résultat est trié par `personal_score` décroissant (sinon `score`), tri stable."""
    picked, postponed = [], []
    for outfit in outfits:
        if len(picked) == k:
            break
        ids = _outfit_ids(outfit)
        if any(overlap(ids, _outfit_ids(p)) > max_overlap for p in picked):
            postponed.append(outfit)
        else:
            picked.append(outfit)
    selected = picked + postponed[:max(0, min(k, min_proposals) - len(picked))]
    return sorted(selected, key=lambda o: -float(o["personal_score"] if "personal_score" in o
                                                  else o.get("score", 0)))


def display_names(wardrobe: list[dict]) -> dict[str, str]:
    """Nom affiché par vêtement. Deux vêtements BO1 au même nom (« Charcoal Jacket ») sont
    distingués par un numéro, pour que deux tenues différentes ne semblent pas identiques."""
    counts: dict[str, int] = {}
    for item in wardrobe:
        counts[item.get("name")] = counts.get(item.get("name"), 0) + 1
    seen: dict[str, int] = {}
    names = {}
    for item in wardrobe:
        name = item.get("name") or str(item["id"])
        if counts[item.get("name")] > 1:
            seen[name] = seen.get(name, 0) + 1
            name = f"{name} n° {seen[name]}"
        names[str(item["id"])] = name
    return names


def advice_question(state: StylistState) -> str:
    """Question posée à BO5 sur la tenue n° 1, avec les noms affichés des vêtements."""
    request = state["request"]
    wardrobe = state.get("wardrobe") or []
    labels = display_names(wardrobe)
    items = _outfit_items(state["outfits"][0], wardrobe)
    names = " + ".join(labels[str(item["id"])] for item in items)
    occasion = OCCASION_FR.get(request.get("occasion"), request.get("occasion") or "une occasion")
    code = request.get("dress_code")
    dress_code = DRESS_CODE_FR.get(code, code) if code else "non précisé"
    return f"Quels conseils de style pour porter {names} pour {occasion}, dress code {dress_code} ?"


def _outfit_items(outfit: dict, wardrobe: list[dict]) -> list[dict]:
    by_id = {str(item["id"]): item for item in wardrobe}
    return [by_id[i] for i in _outfit_ids(outfit) if i in by_id]


def _explanations(outfit: dict) -> list[str]:
    raw = outfit.get("explanations")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, dict):
        return [str(v) for v in raw.values()]
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return []


OCCASION_FR = {"university": "université", "work": "travail", "evening": "soirée",
               "casual": "décontracté"}
SEASON_FR = {"spring": "printemps", "summer": "été", "autumn": "automne", "winter": "hiver"}
DRESS_CODE_FR = {"casual": "décontracté", "smart_casual": "smart casual", "business": "business",
                 "formal": "formel"}
EXCLUDE_FR = {"outerwear": "vestes et manteaux", "dress": "robes", "skirt": "jupes",
              "shorts": "shorts", "jeans": "jeans"}


def format_response(state: StylistState) -> str:
    """Réponse déterministe : seuls des vêtements présents dans la garde-robe apparaissent."""
    if state.get("error"):
        return state["error"]
    request = state["request"]
    wardrobe = state.get("wardrobe") or []
    lines = [state["feedback_note"]] if state.get("feedback_note") else []
    lines += [f"Contexte : {OCCASION_FR[request['occasion']]}, "
             f"{SEASON_FR[request['season']]} ({request['season_source']})."]
    rain = (state.get("weather") or {}).get("rain_probability")
    if rain is not None and rain >= RAIN_ALERT:
        lines.append(f"Pluie probable ({rain} %) : prévois une veste imperméable ou un parapluie "
                     "(le moteur BO4 ne tient pas encore compte de la pluie).")
    if request.get("dress_code"):
        lines.append(f"Dress code : {DRESS_CODE_FR[request['dress_code']]} "
                     f"({request['dress_code_source']}).")
    if request["exclude_categories"] or request["exclude_colors"]:
        refused = [EXCLUDE_FR[c] for c in request["exclude_categories"]] + request["exclude_colors"]
        lines.append(f"Contraintes respectées : sans {', '.join(refused)} "
                     f"({len(state.get('excluded') or [])} vêtement(s) écarté(s)).")
    if request.get("unsupported_now"):
        lines.append(f"Remarque : « {', '.join(request['unsupported_now'])} » n'est pas encore pris en "
                     "compte, car le moteur BO4 ne gère pas encore les chaussures ni les accessoires.")

    outfits = state.get("outfits") or []
    labels = display_names(wardrobe)
    if not outfits:
        if request["wants_another"]:
            lines.append("Je n'ai plus d'autre tenue différente avec ces critères. "
                         "Tu peux changer d'occasion ou retirer une contrainte.")
        else:
            lines.append("Je ne trouve aucune tenue complète avec les vêtements disponibles et ces "
                         "contraintes.")
        return "\n".join(lines)

    if state.get("dress_code_relaxed"):
        lines.append("Aucune tenue de ta garde-robe ne respecte entièrement ce dress code : "
                     "voici les plus proches.")
    lines.append("Voici d'autres propositions :" if request["wants_another"]
                 else "Voici mes propositions, à partir de ta garde-robe :")
    for rank, outfit in enumerate(outfits, 1):
        items = _outfit_items(outfit, wardrobe)
        names = " + ".join(f"{labels[str(item['id'])]} ({item['category']})" for item in items)
        formality = f", formalité {outfit['formality']}/5" if outfit.get("formality") is not None else ""
        bonus = outfit.get("personal_bonus") or 0
        personal = f", bonus perso {bonus:+.1f}" if bonus else ""
        lines.append(f"{rank}. {names} - score {outfit['score']:.1f}/100{formality}{personal}")
        for explanation in _explanations(outfit)[:2]:
            lines.append(f"   - {explanation}")
    if len(outfits) < 3 and not request["wants_another"]:
        lines.append(f"Je ne propose que {len(outfits)} tenue(s) : les autres combinaisons possibles "
                     "sont trop proches de celles-ci.")
    lines.append("Dis-moi si tu veux une autre tenue ou ajouter une contrainte (ex. « sans veste »).")
    advice = state.get("advice") or {}
    if advice.get("answer"):
        # Séparé des tenues : le conseil BO5 complète la liste des vêtements, il ne la remplace jamais.
        lines += ["", "---", f"Conseil de style (base de connaissances BO5) : {advice['answer']}"]
        if advice.get("sources"):
            lines.append(f"Sources : {' ; '.join(advice['sources'])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Graphe LangGraph
# --------------------------------------------------------------------------------------
def build_graph(llm: Optional[Callable[[str], Any]] = ollama_extract,
                wardrobe_loader: Optional[Callable[[], tuple[list[dict], dict]]] = None,
                engine: Any = None, today: Optional[Callable[[], dt.date]] = None,
                checkpointer: Any = None,
                weather: Optional[Callable[[str, dt.date], dict]] = open_meteo_forecast,
                default_city: str = DEFAULT_CITY,
                feedback_store: Optional[stylist_feedback.FeedbackStore] = None,
                advice: Optional[Callable[[str], dict]] = None):
    from langgraph.graph import END, START, StateGraph
    try:
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError:  # anciennes versions de LangGraph
        from langgraph.checkpoint.memory import MemorySaver as InMemorySaver

    nodes = make_nodes(llm, wardrobe_loader, engine, today, weather, default_city, feedback_store, advice)
    builder = StateGraph(StylistState)
    for name, fn in nodes.items():
        builder.add_node(name, fn)
    builder.add_edge(START, "extract_intent")
    builder.add_conditional_edges("extract_intent", route_after_intent,
                                  {"record_feedback": "record_feedback", "clarify": "clarify",
                                   "get_weather": "get_weather"})
    builder.add_conditional_edges("record_feedback", route_after_feedback,
                                  {"get_weather": "get_weather", "end": END})
    builder.add_edge("get_weather", "fetch_wardrobe")
    builder.add_edge("clarify", END)
    builder.add_conditional_edges("fetch_wardrobe", route_after_fetch,
                                  {"respond": "respond", "apply_constraints": "apply_constraints"})
    builder.add_edge("apply_constraints", "recommend")
    builder.add_edge("recommend", "style_advice")
    builder.add_edge("style_advice", "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def bo5_advice(base_url: Optional[str]) -> Optional[Callable[[str], dict]]:
    """Fonction de conseil branchée sur BO5, ou None (node désactivé) sans URL."""
    if not base_url:
        return None
    import bo5_client  # import paresseux : BO5 reste optionnel

    return lambda question: bo5_client.ask_bo5(question, base_url=base_url)


def new_turn(message: str) -> dict:
    """Entrée d'un tour : on remet à zéro ce qui ne doit pas survivre d'un tour à l'autre."""
    return {"user_message": message, "trace": [], "outfits": [], "response": "", "error": "",
            "weather": {}, "dress_code_relaxed": False, "feedback_note": "", "advice": {}}


def chat(graph, message: str, thread_id: str, show_trace: bool = False) -> str:
    config = {"configurable": {"thread_id": thread_id}}
    if show_trace:
        for update in graph.stream(new_turn(message), config, stream_mode="updates"):
            for node, values in update.items():
                trace = (values or {}).get("trace") or []
                print(f"   [trace] {trace[-1] if trace else node}")
    else:
        graph.invoke(new_turn(message), config)
    return graph.get_state(config).values["response"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Stylist Agent BO4 (LangGraph)")
    parser.add_argument("--graph", action="store_true", help="affiche le graphe au format Mermaid")
    parser.add_argument("--trace", action="store_true", help="affiche le passage dans chaque node")
    parser.add_argument("--bo1-url", default=None, help="URL de BO1 (défaut : $BO1_API_URL ou :8000)")
    parser.add_argument("--fallback", default=None,
                        help="fichier JSON au format /api/items utilisé si BO1 est injoignable")
    parser.add_argument("--no-llm", action="store_true", help="extraction par règles uniquement")
    parser.add_argument("--no-weather", action="store_true", help="saison déduite de la date, sans météo")
    parser.add_argument("--city", default=DEFAULT_CITY, help="ville par défaut pour la météo")
    parser.add_argument("--feedback-file", default="stylist_feedback.json",
                        help="fichier JSON des retours utilisateur (I76/I77)")
    parser.add_argument("--bo5-url", default=None,
                        help="URL de BO5 (RAG) : active le node style_advice (désactivé par défaut)")
    args = parser.parse_args()

    def loader():
        return bo1_api_adapter.load_wardrobe_from_bo1(args.bo1_url, fallback_file=args.fallback)

    graph = build_graph(llm=None if args.no_llm else ollama_extract, wardrobe_loader=loader,
                        weather=None if args.no_weather else open_meteo_forecast, default_city=args.city,
                        feedback_store=stylist_feedback.FeedbackStore(args.feedback_file),
                        advice=bo5_advice(args.bo5_url))
    if args.graph:
        print(graph.get_graph().draw_mermaid())
        return

    thread_id = str(uuid.uuid4())
    print("Stylist DressMe - écris ta demande (ou « quitter »).")
    while True:
        try:
            message = input("\nToi : ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message or _plain(message) in {"quitter", "exit", "quit"}:
            break
        print("\nStylist :\n" + chat(graph, message, thread_id, show_trace=args.trace))


if __name__ == "__main__":
    main()
