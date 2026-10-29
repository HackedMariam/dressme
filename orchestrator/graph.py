"""Orchestrateur DressMe : un graphe LangGraph qui envoie chaque demande au bon service.

    START -> route_intent -> [stylist | wardrobe | purchase | knowledge | clarify] -> respond -> END

- route_intent : règles FR/EN d'abord ; si elles ne tranchent pas (aucun indice, ou plusieurs routes possibles),
  qwen2.5:3b via Ollama en JSON contraint. Garde-fou : seules les routes autorisées sont acceptées, et quand les
  règles ont trouvé des indices, le LLM doit choisir parmi elles. Sinon : clarify.
- stylist   : BO4 Stylist POST /api/chat (même jeton, même thread_id).
- wardrobe  : BO1 GET /api/items, réponse par des faits (comptes, filtres catégorie / couleur). /api/agent/search
  n'est pas utilisé : il exige une OPENAI_API_KEY côté BO1.
- purchase  : Purchase Redundancy POST /analyze, avec la garde-robe BO1 de l'utilisateur.
- knowledge : BO5 POST /ask avec la question traduite en anglais par qwen ; seules les sources citées sont
  affichées, et les titres « z-library », « .indb », « Slide 1 » sont masqués.

Mémoire : checkpointer par <user_id>:<thread_id>. Le jeton passe par la configuration du tour (clé __bo1_token,
objet au contenu masqué), jamais par l'état : LangGraph ne copie pas les clés en « __ » dans les métadonnées.
"""
from __future__ import annotations

import collections
import json
import re
import unicodedata
from typing import Any, Callable, Optional, TypedDict

try:  # LangGraph n'injecte la configuration du tour que dans un paramètre typé RunnableConfig.
    from langchain_core.runnables import RunnableConfig
except ImportError:  # pragma: no cover
    RunnableConfig = dict

from services import CallResult, Gateway, load_modules, load_services

ROUTES = ("stylist", "wardrobe", "purchase", "knowledge", "clarify")
SERVICE_ROUTES = ROUTES[:4]
DEFAULT_USER = "local"
TOKEN_KEY = "__bo1_token"


# --------------------------------------------------------------------------------------
# Jeton et configuration du tour (même technique que bo4/backend/stylist_agent.py)
# --------------------------------------------------------------------------------------
class RequestToken:
    """Jeton du tour : jamais dans l'état, contenu masqué dans repr()."""
    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "RequestToken(***)"


def turn_config(thread_id: str, user_id: str = DEFAULT_USER, token: Optional[str] = None) -> dict:
    configurable: dict[str, Any] = {"thread_id": f"{user_id}:{thread_id}", "user_id": user_id,
                                    "conversation_id": thread_id}
    if token:
        configurable[TOKEN_KEY] = RequestToken(token)
    return {"configurable": configurable}


def _configurable(config: Optional[RunnableConfig]) -> dict:
    return (config or {}).get("configurable") or {}


def request_token(config: Optional[RunnableConfig]) -> Optional[str]:
    token = _configurable(config).get(TOKEN_KEY)
    return token.reveal() if isinstance(token, RequestToken) else None


def conversation_id(config: Optional[RunnableConfig]) -> str:
    return str(_configurable(config).get("conversation_id") or "default")


# --------------------------------------------------------------------------------------
# Routage par règles
# --------------------------------------------------------------------------------------
def plain(text: str) -> str:
    """Minuscules, sans accents, apostrophes droites."""
    text = unicodedata.normalize("NFKD", text.lower().replace("’", "'"))
    return "".join(c for c in text if not unicodedata.combining(c))


ROUTE_PATTERNS = {
    "stylist": r"\b(que|quoi) (porter|mettre)\b|\btenues?\b|\blooks?\b|\boutfits?\b|\bm'habiller\b|"
               r"\bs'habiller\b|\bwhat (should i |can i |to )?wear\b|\bwhat do i wear\b",
    "wardrobe": r"\best-ce que j'ai\b|\bai-je\b|\bj'ai combien\b|\bcombien (de|d')|\bmes vetements\b|"
                r"\bma garde-robe\b|\bmon placard\b|\bdo i (have|own)\b|\bmy (clothes|wardrobe|closet)\b|"
                r"\bhow many\b",
    "purchase": r"\bachet\w*|\bachat\b|\bbuy(ing)?\b|\bdoublons?\b|\bduplicates?\b|\bredondan\w*|"
                r"\bredundan\w*|\bworth (it|buying)\b|\bvaut le coup\b",
    "knowledge": r"\bcomment (porter|assortir|associer|choisir|entretenir|laver|styliser)\b|\bconseils?\b|"
                 r"\bpourquoi\b|\bhow (do i |to |should i |can i )?(wear|style|match|pair|care for)\b|"
                 r"\bwhy\b|\btips?\b|\badvice\b|\bquelles? couleurs?\b|\bwhich colou?rs?\b",
}
GREETING = r"^\s*(bonjour|salut|hello|hi|hey|coucou|bonsoir|merci|thanks?)\s*[!.?]*\s*$"
# Suite d'une conversation avec le Stylist : « une autre », « j'aime la 2 »...
FOLLOW_UP = (r"\b(une autre|un autre|autre chose|another|something else|j'aime|je n'aime|n'aime pas|"
             r"i like|i don't like|la (premiere|deuxieme|troisieme|1|2|3)|number [123])\b")
CHOICE = {"1": "stylist", "2": "wardrobe", "3": "purchase", "4": "knowledge"}


def rule_candidates(message: str, modules: Optional[dict] = None) -> list[str]:
    """Routes indiquées par les mots-clés : routes internes, puis modules externes (services.yaml). Un module
    désactivé n'est gardé que s'il est le seul indice (pour dire qu'il n'est pas encore branché)."""
    text = plain(message)
    found = [route for route, pattern in ROUTE_PATTERNS.items() if re.search(pattern, text)]
    enabled, disabled = [], []
    for module in (modules or {}).values():
        if any(re.search(pattern, text) for pattern in module.keywords):
            (enabled if module.enabled else disabled).append(module.route)
    found += enabled
    return found or disabled


# --------------------------------------------------------------------------------------
# LLM (Ollama, JSON contraint) et garde-fou
# --------------------------------------------------------------------------------------
ROUTE_SCHEMA = {"type": "object", "properties": {"route": {"type": "string", "enum": list(ROUTES)}},
                "required": ["route"]}
ROUTE_PROMPT = (
    "You route messages for DressMe, a fashion assistant. Answer with JSON {\"route\": ...}.\n"
    "stylist: the user wants an outfit from their wardrobe for an occasion.\n"
    "wardrobe: the user asks what they own (counts, whether they have an item).\n"
    "purchase: the user asks whether to buy an item or if it duplicates what they own.\n"
    "knowledge: the user asks for general style advice or an explanation (how to wear, why, which colours).\n"
    "clarify: the request is unclear or unrelated to clothing."
)
TRANSLATE_SCHEMA = {"type": "object", "properties": {"english": {"type": "string"}}, "required": ["english"]}
TRANSLATE_PROMPT = ("Translate the user's fashion question into natural English. Keep garment names precise "
                    "(col roule = turtleneck, veste = jacket, jupe = skirt). Answer with JSON {\"english\": ...}.")

# Termes de vêtement que qwen2.5:3b laisse parfois en français dans sa traduction (« black col roule »).
# Remplacés après la traduction, accents ou non ; l'ordre compte (« mini-jupe » avant « jupe »).
GLOSSARY = (
    (r"cols? roul[eé]s?", "turtleneck"), (r"mini-?jupes?", "mini skirt"), (r"jupes?", "skirt"),
    (r"pantalons?", "trousers"), (r"vestes?", "jacket"), (r"blousons?", "jacket"), (r"manteaux?", "coat"),
    (r"pulls?", "sweater"), (r"chemises?", "shirt"), (r"robes?", "dress"), (r"chaussures?", "shoes"),
    (r"[ée]cossaise?s?", "plaid"),
    # pièces et matières de l'avis d'achat (Purchase Redundancy compare des textes en anglais)
    (r"chemisiers?", "blouse"), (r"hauts?", "top"), (r"gilets?", "cardigan"), (r"bermudas?", "shorts"),
    (r"baskets?", "sneakers"), (r"bottines?", "ankle boots"), (r"bottes?", "boots"), (r"escarpins?", "pumps"),
    (r"sacs?", "bag"), (r"ceintures?", "belt"), (r"montres?", "watch"), (r"lunettes?", "glasses"),
    (r"collants?", "tights"), (r"[ée]charpes?", "scarf"), (r"foulards?", "scarf"), (r"chapeaux?", "hat"),
    (r"bonnets?", "beanie"), (r"casquettes?", "cap"),
    (r"cuir", "leather"), (r"laine", "wool"), (r"coton", "cotton"), (r"lin", "linen"), (r"soie", "silk"),
    (r"daim", "suede"), (r"cachemire", "cashmere"), (r"velours", "velvet"),
)


def apply_glossary(text: str) -> str:
    for pattern, english in GLOSSARY:
        text = re.sub(rf"\b{pattern}\b", english, text, flags=re.IGNORECASE)
    return text


# llm(system, message, schema) -> dict JSON, ou None (Ollama arrêté, JSON invalide...)
LLM = Callable[[str, str, dict], Optional[dict]]


def ollama_llm(gateway: Gateway, trace: list[str], node: str) -> LLM:
    """Appel Ollama en JSON contraint ; chaque appel ajoute sa ligne à la trace du node."""
    model = gateway.services["ollama"].extra.get("model", "qwen2.5:3b")
    keep_alive = gateway.services["ollama"].extra.get("keep_alive", "30m")   # modèle gardé en mémoire

    def call(system: str, message: str, schema: dict) -> Optional[dict]:
        body = {"model": model, "stream": False, "format": schema, "keep_alive": keep_alive,
                "options": {"temperature": 0},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}]}
        result = gateway.call("ollama", "POST", "/api/chat", body)
        trace.append(f"{node} -> {result.trace()}")
        if not result.ok or not isinstance(result.data, dict):
            return None
        try:
            return json.loads(result.data["message"]["content"])
        except (KeyError, TypeError, ValueError):
            return None
    return call


def ground_route(raw: Any, candidates: list[str], extra_routes: tuple = ()) -> tuple[Optional[str], Optional[str]]:
    """Garde-fou : (route acceptée, motif de rejet). Valeur hors liste (routes internes et modules externes
    activés), ou hors des indices trouvés par les règles quand il y en a : rejetée."""
    route = raw.get("route") if isinstance(raw, dict) else None
    if route not in ROUTES and route not in extra_routes:
        return None, f"valeur non autorisée {route!r}"
    if candidates and route not in candidates and route != "clarify":
        return None, f"{route} hors des indices {candidates}"
    return route, None


def route_prompt_and_schema(modules: Optional[dict]) -> tuple[str, dict, tuple]:
    """Prompt et schéma JSON du routage, étendus aux modules externes ACTIVÉS."""
    enabled = [m for m in (modules or {}).values() if m.enabled]
    extra = tuple(m.route for m in enabled)
    prompt = ROUTE_PROMPT + "".join(f"\n{m.route}: {m.description or m.label}." for m in enabled)
    schema = {"type": "object", "properties": {"route": {"type": "string", "enum": list(ROUTES) + list(extra)}},
              "required": ["route"]}
    return prompt, schema, extra


def decide_route(message: str, state: dict, llm: Optional[LLM],
                 modules: Optional[dict] = None) -> tuple[str, str, list[str]]:
    """(route, source, indices). Règles, puis suite de conversation, puis LLM avec garde-fou."""
    text = plain(message)
    pending = state.get("pending_question")
    if pending and (choice := re.match(r"^\s*([1-4])\b", text)):
        return CHOICE[choice.group(1)], "réponse à la question de clarification", []
    candidates = rule_candidates(message, modules)
    if len(candidates) == 1:
        return candidates[0], "règles", candidates
    if not candidates and re.search(GREETING, text):
        return "clarify", "règles (salutation)", []
    if not candidates and state.get("last_route") == "stylist" and re.search(FOLLOW_UP, text):
        return "stylist", "suite de la conversation", []
    if llm is None:
        return "clarify", "règles ambiguës, LLM désactivé", candidates
    prompt, schema, extra = route_prompt_and_schema(modules)
    route, rejected = ground_route(llm(prompt, message, schema), candidates, extra)
    if route is None:
        return "clarify", f"LLM rejeté ({rejected or 'pas de réponse'})", candidates
    return route, "LLM qwen2.5:3b", candidates


# --------------------------------------------------------------------------------------
# Vocabulaire vêtements / couleurs (FR, EN) -> catégories BO1 et couleurs BO1
# --------------------------------------------------------------------------------------
GARMENT_WORDS = {
    "top": r"\b(hauts?|tops?|t-shirts?|tee-shirts?|chemises?|chemisiers?|blouses?|shirts?|col roules?|turtlenecks?)\b",
    "sweater": r"\b(pulls?|sweaters?|jumpers?|gilets?|cardigans?)\b",
    "jacket": r"\b(vestes?|blousons?|manteaux?|manteau|jackets?|coats?|blazers?|trench)\b",
    "pants": r"\b(pantalons?|jeans?|pants|trousers|chinos?)\b",
    "shorts": r"\b(shorts?|bermudas?)\b",
    "skirt": r"\b(jupes?|mini-jupes?|minijupes?|skirts?)\b",
    "dress": r"\b(robes?|dress(es)?)\b",
    "shoe": r"\b(chaussures?|baskets?|sneakers?|bottes?|bottines?|shoes?|boots?|escarpins?)\b",
    "bag": r"\b(sacs?|bags?|tote)\b",
    "belt": r"\b(ceintures?|belts?)\b",
    "watch": r"\b(montres?|watch(es)?)\b",
    "glasses": r"\b(lunettes?|glasses|sunglasses)\b",
    "tights": r"\b(collants?|tights)\b",
    "scarf": r"\b(echarpes?|foulards?|scarf|scarves)\b",
    "hat": r"\b(chapeaux?|bonnets?|casquettes?|hats?|caps?)\b",
}
CATEGORY_FR = {"top": "hauts", "sweater": "pulls", "jacket": "vestes", "pants": "pantalons", "shorts": "shorts",
               "skirt": "jupes", "dress": "robes", "shoe": "chaussures", "bag": "sacs", "belt": "ceintures",
               "watch": "montres", "glasses": "lunettes", "tights": "collants", "scarf": "écharpes",
               "hat": "chapeaux", "vest": "gilets sans manches", "headband": "bandeaux", "glove": "gants",
               "sock": "chaussettes", "umbrella": "parapluies"}
COLOR_WORDS = {
    "black": r"\b(noire?s?|black)\b", "white": r"\b(blanche?s?|white)\b", "grey": r"\b(grise?s?|gr[ae]y)\b",
    "beige": r"\b(beiges?)\b", "brown": r"\b(marron|brune?s?|brown|chocolat|chocolate|camel)\b",
    "blue": r"\b(bleue?s?|blue|marine|navy)\b", "red": r"\b(rouges?|red|bordeaux|burgundy)\b",
    "green": r"\b(verte?s?|green|olive|kaki|khaki)\b", "pink": r"\b(roses?|pink)\b",
    "yellow": r"\b(jaunes?|yellow)\b", "purple": r"\b(violette?s?|purple)\b",
}
COLOR_FR = {"black": "noir", "white": "blanc", "grey": "gris", "beige": "beige", "brown": "marron", "blue": "bleu",
            "red": "rouge", "green": "vert", "pink": "rose", "yellow": "jaune", "purple": "violet"}
# Couleur BO1 (color_name) -> famille ci-dessus
COLOR_FAMILY = {"charcoal": "grey", "light grey": "grey", "dark grey": "grey", "gray": "grey", "navy": "blue",
                "denim blue": "blue", "light blue": "blue", "chocolate": "brown", "camel": "brown", "tan": "brown",
                "burgundy": "red", "maroon": "red", "olive": "green", "khaki": "green", "cream": "white",
                "off white": "white", "ivory": "white"}


def find_categories(message: str) -> list[str]:
    """Catégories BO1 citées, dans l'ordre du message."""
    text = re.sub(r"garde-robes?", " ", plain(message))   # « garde-robe » ne veut pas dire « robe »
    found = [(m.start(), cat) for cat, pattern in GARMENT_WORDS.items() if (m := re.search(pattern, text))]
    return [cat for _, cat in sorted(found)]


def find_colors(message: str) -> list[str]:
    text = plain(message)
    return [color for color, pattern in COLOR_WORDS.items() if re.search(pattern, text)]


def color_family(color_name: Any) -> str:
    name = str(color_name or "").lower().strip()
    if name in COLOR_FAMILY:
        return COLOR_FAMILY[name]
    for family in COLOR_WORDS:
        if family in name.split():
            return family
    return name


def is_french(message: str) -> bool:
    text = plain(message)
    return bool(re.search(r"\b(je|j'|est-ce|que|quel(le)?s?|comment|pourquoi|une?|des|mes|ma|mon|pour|avec|"
                          r"acheter|porter|tenue)\b", text)) and not re.search(r"\b(the|should|what|how|my)\b", text)


# --------------------------------------------------------------------------------------
# Purchase Redundancy : conversion BO1 -> modèle ClothingItemRequest de Purchase Redundancy
# --------------------------------------------------------------------------------------
PURCHASE_CATEGORY = {"top": "shirts", "sweater": "shirts", "vest": "shirts", "pants": "pants", "shorts": "pants",
                     "skirt": "pants", "dress": "dresses", "jacket": "outerwear", "shoe": "shoes"}
PURCHASE_MAX_ITEMS = 500  # limite de son API


def purchase_category(bo1_category: Any) -> str:
    return PURCHASE_CATEGORY.get(str(bo1_category or "").lower(), "accessories")


MATERIAL_WORDS = {
    "leather": r"\b(cuir|leather)\b", "wool": r"\b(laine|wool)\b", "cotton": r"\b(coton|cotton)\b",
    "linen": r"\b(lin|linen)\b", "silk": r"\b(soie|silk)\b", "suede": r"\b(daim|suede)\b",
    "cashmere": r"\b(cachemire|cashmere)\b", "velvet": r"\b(velours|velvet)\b", "denim": r"\b(denim)\b",
}


def bo1_to_purchase(item: dict) -> dict:
    """Pièce BO1 -> ClothingItemRequest. style vaut toujours null : l'article demandé n'a pas de style connu, et
    Purchase Redundancy remplace un style absent par « casual » ; comparer « minimalist » à ce « casual » inventé
    écarte à tort la pièce possédée. null (et non absent) neutralise le style des deux côtés."""
    seasons = item.get("seasons") or []
    out = {"id": str(item.get("id"))[:64], "name": str(item.get("name") or item.get("category") or "item")[:160],
           "category": purchase_category(item.get("category")),
           "color": str(item.get("color_name") or "")[:60] or None,
           "material": str(item.get("material") or "")[:60] or None,
           "season": str(seasons[0])[:60] if seasons else None,
           "description": str(item.get("description") or "")[:500] or None}
    return {k: v for k, v in out.items() if v is not None} | {"style": None}


def new_item_from_message(message: str) -> Optional[dict]:
    """Article à acheter, en anglais comme les pièces BO1 : « veste en cuir noire à 80 € » ->
    {name: "black leather jacket", category: "outerwear", color: "black", material: "leather", price: 80.0}."""
    categories = find_categories(message)
    if not categories:
        return None
    category, colors = categories[0], find_colors(message)
    text = re.sub(r"garde-robes?", " ", plain(message))
    garment = apply_glossary(re.search(GARMENT_WORDS[category], text).group(0))
    material = next((m for m, pattern in MATERIAL_WORDS.items() if re.search(pattern, text)), None)
    item = {"name": " ".join(filter(None, [colors[0] if colors else None, material, garment])),
            "category": purchase_category(category), "style": None}
    if colors:
        item["color"] = colors[0]
    if material:
        item["material"] = material
    if price := re.search(r"(\d+(?:[.,]\d+)?)\s*(€|eur|euros?|\$|dollars?|dt|dinars?)", text):
        item["price"] = float(price.group(1).replace(",", "."))
    return item


def purchase_label(message: str, new_item: dict) -> str:
    """Article tel que l'utilisateur l'a écrit, pour l'affichage : « col roulé noir », « veste en cuir noire » ;
    question en anglais (ou mots introuvables) : le nom anglais envoyé à /analyze."""
    original = unicodedata.normalize("NFC", message).lower().replace("’", "'")
    text = re.sub(r"garde-robes?", lambda m: " " * len(m.group(0)), plain(message))
    categories = find_categories(message)
    if not is_french(message) or not categories or len(text) != len(original):
        return new_item["name"]

    def written(pattern: str) -> Optional[str]:     # mêmes positions : plain() ne fait que retirer les accents
        found = re.search(pattern, text)
        return original[found.start():found.end()] if found else None

    material = next((written(p) for m, p in MATERIAL_WORDS.items() if m == new_item.get("material")), None)
    color = written(COLOR_WORDS[new_item["color"]]) if new_item.get("color") in COLOR_WORDS else None
    return " ".join(filter(None, [written(GARMENT_WORDS[categories[0]]), f"en {material}" if material else None,
                                  color]))


def purchase_request(new_item: dict, bo1_items: list, language: str, use_llm: bool) -> dict:
    """Corps de POST /analyze. Purchase Redundancy compare les textes « couleur matière style nom » : une matière
    absente de l'article demandé est aussi retirée des pièces BO1, sinon ses mots (« wool knit ») diluent à eux
    seuls la similarité. Elle reste comptée comme inconnue (neutre) dans son score d'attributs."""
    wardrobe_items = [bo1_to_purchase(i) for i in bo1_items][:PURCHASE_MAX_ITEMS]
    if "material" not in new_item:
        wardrobe_items = [{k: v for k, v in i.items() if k != "material"} for i in wardrobe_items]
    return {"new_item": new_item, "wardrobe_items": wardrobe_items, "use_llm": use_llm, "language": language}


# --------------------------------------------------------------------------------------
# BO5 : sources citées, titres masqués
# --------------------------------------------------------------------------------------
MASKED_TITLE = re.compile(r"z-library|\.indb|slide 1", re.IGNORECASE)


def cited_sources(payload: dict) -> tuple[list[str], int]:
    """Titres des sources CITÉES (pas toutes les sources renvoyées), sans doublon ; les titres signalés sont
    masqués et comptés à part."""
    shown, masked, seen = [], 0, set()
    for citation in payload.get("citations") or []:
        title = str(citation.get("title") or citation.get("source") or "").strip()
        page = citation.get("page")
        if not title or title in seen:
            continue
        seen.add(title)
        if MASKED_TITLE.search(title) or MASKED_TITLE.search(str(citation.get("source") or "")):
            masked += 1
            continue
        shown.append(f"{title}" + (f" (p. {page})" if page is not None else ""))
    return shown, masked


# Marqueurs de citation de BO5 ([S1], [S2, S3], [S1][S4]) et renvois aux figures des livres sources : utiles au
# contrôle mais illisibles pour l'utilisateur. La réponse reste en anglais ; les sources sont listées à part.
_MARKER = r"\[\s*S\s*\d+(?:\s*[,;&]\s*S?\s*\d+)*\s*\]"
_FIGURE = r"(?:figures?|fig\.)\s*\d+[a-z]?"
BO5_CLEANUP = (
    (rf"\s*\([^()]*\b{_FIGURE}[^()]*\)", ""),                                        # (Figure 69 from [S5])
    (rf",?\s*(?:as\s+)?(?:shown|seen|illustrated|depicted|pictured)\s+in\s+{_FIGURE}", ""),
    (rf"\s*\b(?:see|refer to|check)\s+{_FIGURE}(?:\s+for\s+(?:details|more(?:\s+\w+)?))?\s*[.!]?", ""),  # See FIGURE 12…
    (rf"\b{_FIGURE}(?:\s+(?:from|in|of)\s+{_MARKER})?", ""),                        # FIGURE 12 from [S2]
    (rf"\b(?:from|in|according to|see|per|as (?:mentioned|suggested|noted|shown) in|based on)\s+"
     rf"{_MARKER}(?:\s*(?:and|,)\s*{_MARKER})*\s*,?\s*", ""),                         # From [S1], we learn
    (rf"\s*{_MARKER}", ""),
    (r"\(\s*\)", ""),
    (r"[ \t]{2,}", " "),
    (r"[ \t]+([,.;:!?])", r"\1"),
    (r",\s*\.", "."),
    (r"[ \t]+$", ""),
    (r"^[ \t]*(?:[-*•]|\d+[.)])[ \t]*(?:\n|\Z)", ""),                            # puce vidée par le nettoyage
)


def clean_bo5_answer(text: str) -> str:
    for pattern, repl in BO5_CLEANUP:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE | re.MULTILINE)
    # Majuscule en début de phrase ou de ligne quand le renvoi supprimé la portait (« From [S1], we… »).
    text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------------------------------
# Modules externes : contrat wardrobe_items (orchestrator/integration_contract.md) et requêtes configurables
# --------------------------------------------------------------------------------------
# Champs d'une ligne BO1 `items` transmis aux modules. Ni user_id, ni champs internes (détection, confiance).
WARDROBE_FIELDS = ("id", "name", "category", "category_group", "subcategory", "color_name", "color_hex",
                   "color_family", "pattern", "material", "seasons", "style", "occasions", "formality", "warmth",
                   "description", "tags", "needs_review", "status", "image_url", "cutout_url", "created_at")
LIST_FIELDS = {"seasons", "occasions", "tags"}


def contract_item(row: dict) -> dict:
    item = {field: row.get(field) for field in WARDROBE_FIELDS}
    for field in LIST_FIELDS:
        item[field] = list(item[field] or [])
    item["needs_review"] = bool(item["needs_review"])
    item["id"] = str(item["id"])
    return item


_VAR = re.compile(r"\$([a-z_]+)")


def uses_var(template: Any, name: str) -> bool:
    if isinstance(template, str):
        return f"${name}" in template
    if isinstance(template, dict):
        return any(uses_var(v, name) for v in template.values())
    if isinstance(template, list):
        return any(uses_var(v, name) for v in template)
    return False


def render_template(template: Any, ctx: dict) -> Any:
    """Remplace les variables du modèle de requête : "$x" seul garde le type de la valeur (liste, nombre…) ;
    "$x" dans un texte est remplacé par sa forme texte."""
    if isinstance(template, dict):
        return {k: render_template(v, ctx) for k, v in template.items()}
    if isinstance(template, list):
        return [render_template(v, ctx) for v in template]
    if isinstance(template, str):
        whole = re.fullmatch(r"\$([a-z_]+)", template)
        if whole:
            return ctx.get(whole.group(1))
        return _VAR.sub(lambda m: "" if ctx.get(m.group(1)) is None else str(ctx[m.group(1)]), template)
    return template


def get_path(data: Any, path: str) -> Any:
    for key in path.split("."):
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
            data = data[int(key)]
        else:
            return None
    return data


class _Blank(dict):
    def __missing__(self, key):
        return "?"


def render_module_response(spec: dict, data: Any, label: str) -> str:
    """Texte markdown d'une réponse de module, selon `response` de services.yaml."""
    lines: list[str] = []
    for field in spec.get("fields") or []:
        value = get_path(data, field["path"])
        if value not in (None, "", []):
            lines.append(f"**{field['label']}** : {value}{field.get('suffix', '')}")
    listing = spec.get("list")
    if listing:
        items = get_path(data, listing["path"]) or []
        if isinstance(items, list) and items:
            lines.append("")
            for item in items[: int(listing.get("limit", 10))]:
                lines.append(listing["format"].format_map(_Blank(item)) if isinstance(item, dict) else f"- {item}")
    for path in spec.get("text") or []:
        value = get_path(data, path)
        if isinstance(value, list):
            value = "\n".join(f"- {v}" for v in value if v not in (None, ""))
        if value not in (None, ""):
            lines += ["", str(value)]
    text = "\n".join(lines).strip()
    return text or f"Réponse reçue de {label} (aucun champ d'affichage configuré)."


def message_context(message: str) -> dict:
    text = plain(message)
    url = re.search(r"https?://\S+", message)
    price = re.search(r"(\d+(?:[.,]\d+)?)\s*(€|eur|euros?|\$|dt|dinars?)", text)
    budget = re.search(r"budget\D{0,15}(\d+(?:[.,]\d+)?)", text)
    return {"message": message, "language": "French" if is_french(message) else "English",
            "first_url": url.group(0).rstrip(".,;)") if url else None,
            "price": float(price.group(1).replace(",", ".")) if price else None,
            "budget": float(budget.group(1).replace(",", ".")) if budget else None}


# --------------------------------------------------------------------------------------
# État du graphe
# --------------------------------------------------------------------------------------
class OrchestratorState(TypedDict, total=False):
    user_message: str
    history: list[dict]            # [{"role", "content", "route"}]
    route: str                     # route choisie pour ce tour
    route_source: str              # règles, LLM, suite de conversation...
    candidates: list[str]          # routes indiquées par les règles
    pending_question: str          # question en attente d'une clarification
    last_route: str                # dernière route de service (pour « une autre »)
    result: dict                   # carte du service : {service, label, ok, text, details}
    response: str
    trace: list[str]


def new_turn(message: str) -> dict:
    return {"user_message": message, "route": "", "route_source": "", "candidates": [], "result": {},
            "response": "", "trace": []}


def _line(state: dict, node: str, text: str) -> list[str]:
    return list(state.get("trace") or []) + [f"{node} -> {text}"]


def _failure(label: str, call: CallResult, token_sent: bool = True, login_label: Optional[str] = None) -> str:
    """Message d'échec. 401/403 sans jeton : l'utilisateur n'est pas connecté (« Connecte-toi… ») ;
    avec un jeton : il est expiré ou refusé (« reconnecte-toi »)."""
    if call.status is None:
        return f"{call.error}. Réessaie quand le service est démarré."
    if call.status in (401, 403) and not token_sent:
        return f"Connecte-toi pour utiliser {login_label or label}."
    if call.status in (401, 403):
        return f"{label} refuse la connexion (HTTP {call.status}) : reconnecte-toi."
    return call.error or f"{label} a répondu HTTP {call.status}."


def _needs_login(call: CallResult, token_sent: bool) -> bool:
    """Vrai si la page doit proposer le bouton de connexion (service protégé, aucun jeton envoyé)."""
    return call.status in (401, 403) and not token_sent


# --------------------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------------------
def make_nodes(gateway: Gateway, llm: Any, use_llm_for_purchase: bool = False,
               modules: Optional[dict] = None) -> dict:
    """`llm` : "ollama", None (règles seules) ou une fonction (system, message, schema) -> dict | None.
    `modules` : modules externes (services.yaml, section modules), appelés par le node « external »."""
    modules = modules or {}

    def llm_for(trace: list[str], node: str) -> Optional[LLM]:
        if llm is None:
            return None
        if llm == "ollama":
            return ollama_llm(gateway, trace, node)

        def call(system: str, message: str, schema: dict) -> Optional[dict]:
            out = llm(system, message, schema)
            trace.append(f"{node} -> LLM fourni : {'réponse' if out else 'aucune réponse'}")
            return out
        return call

    def route_intent(state: OrchestratorState) -> dict:
        message = state["user_message"]
        llm_trace: list[str] = []
        route, source, candidates = decide_route(message, dict(state), llm_for(llm_trace, "route_intent"), modules)
        if route != "clarify" and source == "réponse à la question de clarification":
            message = state.get("pending_question") or message
        text = f"{route} [{source}" + (f", indices : {', '.join(candidates)}" if candidates else "") + "]"
        update = {"route": route, "route_source": source, "candidates": candidates, "user_message": message,
                  "trace": list(state.get("trace") or []) + llm_trace + [f"route_intent -> {text}"]}
        if route != "clarify":
            update["pending_question"] = ""
        return update

    def switched_off(route: str, service: str, state: OrchestratorState) -> Optional[dict]:
        """Service de base désactivé dans services.yaml (enabled: false) : message clair, aucun appel."""
        conf = gateway.services[service]
        if conf.extra.get("enabled", True) is not False:
            return None
        result = {"service": route, "label": conf.label, "ok": False, "details": {},
                  "text": f"{conf.label} n'est pas encore disponible dans cette version de DressMe "
                          "(désactivé dans services.yaml)."}
        return {"result": result, "last_route": route,
                "trace": _line(state, route, f"{service} désactivé dans services.yaml, aucun appel")}

    def stylist(state: OrchestratorState, config: Optional[RunnableConfig] = None) -> dict:
        if off := switched_off("stylist", "stylist", state):
            return off
        label = gateway.services["stylist"].label
        token = request_token(config)
        call = gateway.call("stylist", "POST", "/api/chat",
                            {"message": state["user_message"], "thread_id": conversation_id(config)}, token=token)
        if call.ok and isinstance(call.data, dict):
            outfits = [{"rank": o.get("rank"), "score": o.get("score"),
                        "items": [i.get("name") for i in o.get("items") or []]} for o in call.data.get("outfits") or []]
            result = {"service": "stylist", "label": label, "ok": True, "text": call.data.get("response") or "",
                      "details": {"outfits": outfits, "visited": call.data.get("visited") or []}}
        else:
            result = {"service": "stylist", "label": label, "ok": False,
                      "text": _failure(label, call, bool(token), "le Stylist"),
                      "details": {"login_required": _needs_login(call, bool(token))}}
        return {"result": result, "last_route": "stylist", "trace": _line(state, "stylist", call.trace())}

    def wardrobe(state: OrchestratorState, config: Optional[RunnableConfig] = None) -> dict:
        if off := switched_off("wardrobe", "bo1", state):
            return off
        label = gateway.services["bo1"].label
        token = request_token(config)
        call = gateway.call("bo1", "GET", "/api/items", token=token)
        if not call.ok or not isinstance(call.data, list):
            result = {"service": "wardrobe", "label": label, "ok": False,
                      "text": _failure(label, call, bool(token), "ta garde-robe"),
                      "details": {"login_required": _needs_login(call, bool(token))}}
            return {"result": result, "last_route": "wardrobe", "trace": _line(state, "wardrobe", call.trace())}
        items = call.data
        message = state["user_message"]
        categories, colors = find_categories(message), find_colors(message)
        by_cat = collections.Counter(str(i.get("category")) for i in items)
        lines = [f"Ta garde-robe BO1 contient {len(items)} vêtement(s)."]
        if categories or colors:
            matches = [i for i in items
                       if (not categories or i.get("category") in categories)
                       and (not colors or color_family(i.get("color_name")) in colors)]
            what = " et ".join(CATEGORY_FR.get(c, c) for c in categories) or "vêtements"
            tint = f" ({', '.join(COLOR_FR.get(c, c) for c in colors)})" if colors else ""
            if matches:
                names = ", ".join(str(i.get("name")) for i in matches[:8])
                lines.append(f"{what.capitalize()}{tint} : {len(matches)} — {names}"
                             + (" …" if len(matches) > 8 else "") + ".")
            else:
                lines.append(f"{what.capitalize()}{tint} : aucun dans ta garde-robe.")
        else:
            top = ", ".join(f"{n} {CATEGORY_FR.get(c, c)}" for c, n in by_cat.most_common(6))
            lines.append(f"Répartition : {top}.")
        review = sum(bool(i.get("needs_review")) for i in items)
        if review:
            lines.append(f"{review} vêtement(s) sont marqués « à vérifier » par la détection BO1.")
        details = {"total": len(items), "by_category": dict(by_cat), "filters": {"categories": categories,
                                                                                  "colors": colors}}
        result = {"service": "wardrobe", "label": label, "ok": True, "text": "\n".join(lines), "details": details}
        return {"result": result, "last_route": "wardrobe", "trace": _line(state, "wardrobe", call.trace())}

    def purchase(state: OrchestratorState, config: Optional[RunnableConfig] = None) -> dict:
        if off := switched_off("purchase", "purchase", state):
            return off
        label = gateway.services["purchase"].label
        message = state["user_message"]
        new_item = new_item_from_message(message)
        trace = list(state.get("trace") or [])
        if new_item is None:
            result = {"service": "purchase", "label": label, "ok": False, "details": {},
                      "text": "Quel article veux-tu acheter ? Précise le type et la couleur "
                              "(par exemple « une veste en cuir noire à 80 € »)."}
            return {"result": result, "last_route": "purchase",
                    "trace": trace + ["purchase -> article non reconnu, aucun appel"]}
        token = request_token(config)
        wardrobe_call = gateway.call("bo1", "GET", "/api/items", token=token)
        trace.append(f"purchase -> {wardrobe_call.trace()}")
        if not wardrobe_call.ok or not isinstance(wardrobe_call.data, list):
            text = _failure(gateway.services["bo1"].label, wardrobe_call, bool(token), "l'avis d'achat") + \
                " Sans ta garde-robe, l'analyse d'achat n'aurait pas de sens."
            result = {"service": "purchase", "label": label, "ok": False, "text": text,
                      "details": {"login_required": _needs_login(wardrobe_call, bool(token))}}
            return {"result": result, "last_route": "purchase", "trace": trace}
        body = purchase_request(new_item, wardrobe_call.data, "French" if is_french(message) else "English",
                                use_llm_for_purchase)
        wardrobe_items = body["wardrobe_items"]
        call = gateway.call("purchase", "POST", "/analyze", body)
        trace.append(f"purchase -> {call.trace()}")
        if not call.ok or not isinstance(call.data, dict):
            result = {"service": "purchase", "label": label, "ok": False, "text": _failure(label, call), "details": {}}
            return {"result": result, "last_route": "purchase", "trace": trace}
        data = call.data
        similar = [f"{s.get('name')} ({round(100 * float(s.get('similarity') or 0))} %)"
                   for s in (data.get("similar_items") or [])[:3]]
        item_label = purchase_label(message, new_item)
        # une phrase d'introduction, puis l'avis de Purchase tel quel (verdict, pièces proches, score) : pas de
        # synthèse qui le répète ; sans explication, la synthèse courte le remplace
        if is_french(message):
            lines = [f"Avis de Purchase Redundancy sur « {item_label} », comparé aux {len(wardrobe_items)} pièces "
                     f"de ta garde-robe :"]
        else:
            lines = [f"Purchase Redundancy's opinion on \"{item_label}\", compared with the {len(wardrobe_items)} "
                     f"items in your wardrobe:"]
        if data.get("explanation"):
            lines.append(str(data["explanation"]))
        else:
            verdict = {"buy": "tu peux l'acheter", "consider": "à réfléchir",
                       "skip": "inutile, tu as déjà l'équivalent"}
            lines.append(f"Redondance : {data.get('redundancy_score')}/100 → "
                         f"{verdict.get(data.get('recommendation'), data.get('recommendation'))}."
                         + (" Pièces proches : " + ", ".join(similar) + "." if similar else ""))
        details = {"new_item": new_item, "item_label": item_label, "redundancy_score": data.get("redundancy_score"),
                   "recommendation": data.get("recommendation"), "similar_items": similar,
                   "wardrobe_sent": len(wardrobe_items)}
        result = {"service": "purchase", "label": label, "ok": True, "text": "\n".join(lines), "details": details}
        return {"result": result, "last_route": "purchase", "trace": trace}

    def knowledge(state: OrchestratorState) -> dict:
        if off := switched_off("knowledge", "bo5", state):
            return off
        label = gateway.services["bo5"].label
        message = state["user_message"]
        trace = list(state.get("trace") or [])
        question, translated = message, False
        translator = llm_for(trace, "knowledge")
        if is_french(message) and translator is not None:
            raw = translator(TRANSLATE_PROMPT, message, TRANSLATE_SCHEMA)
            english = raw.get("english") if isinstance(raw, dict) else None
            if isinstance(english, str) and 0 < len(english.strip()) <= 500:
                question, translated = apply_glossary(english.strip()), True
                trace.append("knowledge -> question traduite en anglais par qwen2.5:3b")
            else:
                trace.append("knowledge -> traduction indisponible : question envoyée telle quelle")
        call = gateway.call("bo5", "POST", "/ask", {"question": question, "top_k": 5})
        trace.append(f"knowledge -> {call.trace()}")
        if not call.ok or not isinstance(call.data, dict):
            result = {"service": "knowledge", "label": label, "ok": False, "text": _failure(label, call), "details": {}}
            return {"result": result, "last_route": "knowledge", "trace": trace}
        sources, masked = cited_sources(call.data)
        answer = clean_bo5_answer(str(call.data.get("answer") or ""))
        lines = [answer, ""]
        if sources:
            lines += ["**Sources citées**"] + [f"- {source}" for source in sources]
            if masked:
                lines += ["", f"{masked} autre(s) source(s) citée(s) au titre peu fiable masquée(s)."]
        elif masked:
            lines.append(f"*{masked} source(s) citée(s), toutes au titre peu fiable (masquées) : conseil à vérifier.*")
        else:
            lines.append("*Aucune source citée : conseil à prendre avec prudence.*")
        details = {"question_sent": question, "translated": translated, "grounded": bool(call.data.get("grounded")),
                   "answer": answer, "language": "en", "sources": sources, "masked_sources": masked}
        result = {"service": "knowledge", "label": label, "ok": True, "text": "\n".join(lines), "details": details}
        return {"result": result, "last_route": "knowledge", "trace": trace}

    def clarify(state: OrchestratorState) -> dict:
        text = ("Je n'ai pas bien compris ta demande. Tu veux :\n"
                "1. une tenue pour une occasion (BO4 Stylist) ;\n"
                "2. savoir ce que tu as dans ta garde-robe ;\n"
                "3. un avis avant d'acheter un vêtement ;\n"
                "4. un conseil de style général ?\n"
                "Réponds par 1, 2, 3 ou 4, ou reformule.")
        result = {"service": "clarify", "label": "Clarification", "ok": True, "text": text, "details": {}}
        return {"result": result, "pending_question": state["user_message"],
                "trace": _line(state, "clarify", "question posée à l'utilisateur")}

    def external(state: OrchestratorState, config: Optional[RunnableConfig] = None) -> dict:
        """Module externe générique : vérifie qu'il est activé et répond, lui envoie la garde-robe BO1 de
        l'utilisateur (wardrobe_items) dans la requête décrite par services.yaml, puis met la réponse en forme."""
        name = state["route"].split(":", 1)[1]
        module = modules.get(name)
        trace = list(state.get("trace") or [])
        if module is None:
            result = {"service": "external", "label": name, "ok": False, "details": {},
                      "text": f"Module « {name} » inconnu dans services.yaml."}
            return {"result": result, "trace": trace + [f"external -> module {name} inconnu"]}
        label = module.label

        def done(ok: bool, text: str, details: Optional[dict] = None) -> dict:
            result = {"service": "external", "label": label, "ok": ok, "text": text,
                      "details": {"module": name, **(details or {})}}
            return {"result": result, "last_route": state["route"], "trace": trace}

        if not module.enabled:
            trace.append(f"external -> {name} désactivé dans services.yaml, aucun appel")
            return done(False, f"Le module {label} n'est pas encore branché à l'orchestrateur : il doit d'abord "
                               f"exposer {module.method} {module.path} selon le contrat d'intégration "
                               f"(orchestrator/integration_contract.md). Il est désactivé dans services.yaml.")
        if module.health:
            health = gateway.call(name, "GET", module.health, timeout=min(3.0, module.timeout))
            trace.append(f"external -> {health.trace()}")
            if not health.ok:
                return done(False, f"{label} ne répond pas pour l'instant ({module.url}) : "
                                   "réessaie quand le service est démarré.")
        ctx = {**message_context(state["user_message"]), "user_id": _configurable(config).get("user_id"),
               "thread_id": conversation_id(config)}
        if uses_var(module.request, "wardrobe_items"):
            token_sent = bool(request_token(config))
            items_call = gateway.call("bo1", "GET", "/api/items", token=request_token(config))
            trace.append(f"external -> {items_call.trace()}")
            if not items_call.ok or not isinstance(items_call.data, list):
                return done(False, _failure(gateway.services["bo1"].label, items_call, token_sent, label)
                            + f" Sans ta garde-robe, {label} ne peut pas répondre.",
                            {"login_required": _needs_login(items_call, token_sent)})
            ctx["wardrobe_items"] = [contract_item(row) for row in items_call.data]
        body = render_template(module.request, ctx) if module.method != "GET" else None
        call = gateway.call(name, module.method, module.path, body,
                            token=request_token(config) if module.forward_token else None)
        trace.append(f"external -> {call.trace()}")
        if not call.ok:
            return done(False, _failure(label, call))
        return done(True, render_module_response(module.response, call.data, label),
                    {"wardrobe_sent": len(ctx.get("wardrobe_items") or [])})

    def respond(state: OrchestratorState) -> dict:
        result = state.get("result") or {}
        text = result.get("text") or "Je n'ai pas de réponse."
        history = list(state.get("history") or []) + [
            {"role": "user", "content": state["user_message"]},
            {"role": "assistant", "content": text, "route": state.get("route")}]
        return {"response": text, "history": history[-40:],
                "trace": _line(state, "respond", f"réponse de {result.get('label', 'l’orchestrateur')}")}

    return {"route_intent": route_intent, "stylist": stylist, "wardrobe": wardrobe, "purchase": purchase,
            "knowledge": knowledge, "external": external, "clarify": clarify, "respond": respond}


NODE_ORDER = ("route_intent", "stylist", "wardrobe", "purchase", "knowledge", "external", "clarify", "respond")


def route_target(state: dict) -> str:
    route = state["route"]
    return "external" if route.startswith("external:") else route


def build_graph(gateway: Optional[Gateway] = None, llm: Any = "ollama", checkpointer: Any = None,
                use_llm_for_purchase: bool = False, modules: Optional[dict] = None):
    """`llm` : "ollama" (par défaut), None (règles seules) ou une fonction (system, message, schema) -> dict.
    `modules` : modules externes ; par défaut la section `modules` de services.yaml."""
    from langgraph.graph import END, START, StateGraph
    from langgraph.checkpoint.memory import InMemorySaver

    gateway = gateway or Gateway(load_services())
    modules = load_modules() if modules is None else modules
    clash = set(modules) & set(gateway.services)
    if clash:
        raise ValueError(f"Nom de module déjà pris par un service : {sorted(clash)}")
    # Passerelle propre à ce graphe (services + modules) : celle de l'appelant n'est pas modifiée.
    gateway = Gateway({**gateway.services, **{m.name: m.service() for m in modules.values()}},
                      transport=gateway.transport)
    nodes = make_nodes(gateway, llm, use_llm_for_purchase, modules)
    builder = StateGraph(OrchestratorState)
    for name, fn in nodes.items():
        builder.add_node(name, fn)
    builder.add_edge(START, "route_intent")
    targets = [*ROUTES, "external"]
    builder.add_conditional_edges("route_intent", route_target, {r: r for r in targets})
    for route in targets:
        builder.add_edge(route, "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def visited_nodes(trace: list[str]) -> list[str]:
    names = [line.split(" -> ", 1)[0].strip() for line in trace]
    return list(dict.fromkeys(n for n in names if n in NODE_ORDER))
