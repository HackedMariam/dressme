"""Contrôles par le CODE (déterministes) : contrat, ancrage, règles métier, citations, routage, robustesse, performance.

Chaque contrôle renvoie un CheckResult. Un échec ici ne peut pas être effacé par le LLM-juge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .adapters import AGENTS, Reply
from .config import VALID_STATES

CRITERIA = ("contract", "grounding", "rules", "citations", "routing", "robustness", "performance")

# Pièces interdites en dress code business / formal : minijupe, épaules dénudées, short.
BUSINESS_FORBIDDEN = re.compile(r"\b(mini|off[- ]?shoulder|bare[- ]shoulder|strapless|shorts?)\b", re.I)
CITATION = re.compile(r"\[S(\d+)\]")
DONT_KNOW = re.compile(r"(i don'?t know|je ne sais pas|no (relevant )?(source|information)|not (enough|covered)|"
                       r"cannot answer|can'?t answer|ne peux pas|aucune (source|information))", re.I)
INFEASIBLE_HINT = re.compile(r"(infeasible|impossible|cannot|can'?t|no solution|not possible|alternativ|relax|"
                             r"assoupli|too many|trop de|ne tient pas|doesn'?t fit)", re.I)
CRASH_HINT = re.compile(r"(traceback|internal server error|exception|stack ?trace)", re.I)


@dataclass
class CheckResult:
    criterion: str
    name: str
    passed: bool
    reason: str = ""


@dataclass
class Ctx:
    """Ce que les contrôles savent de l'utilisatrice : sa vraie garde-robe (items BO1) et les changements vus."""
    wardrobe: list[dict] = field(default_factory=list)
    changed_ids: list[str] = field(default_factory=list)    # pièces modifiées pendant ce pas (comparaison avant/après)
    foreign_probe: Any = None                                # id -> statut HTTP de GET /api/items/{id} (facultatif)

    def __post_init__(self):
        self.by_id = {str(i.get("id")): i for i in self.wardrobe}
        self.by_name = {str(i.get("name", "")).strip().lower(): i for i in self.wardrobe if i.get("name")}


# --------------------------------------------------------------------------------------------- extraction
def _walk_items(node: Any, found: list[dict]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("items", "capsule_items", "selected_items") and isinstance(value, list):
                found.extend(v for v in value if isinstance(v, dict))
            _walk_items(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_items(value, found)


ID_KEYS = ("closest_item_id", "similar_item_id")       # identifiants cités à plat (Similar Agent, anti-doublon)


def _walk_id_keys(node: Any, found: list[dict]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ID_KEYS and value:
                found.append({"id": value, "name": key})
            _walk_id_keys(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_id_keys(value, found)


def item_refs(reply: Reply) -> list[dict]:
    """Toutes les pièces citées par la réponse (listes « items », ou identifiants « closest_item_id »), sans doublons."""
    found: list[dict] = []
    _walk_items(reply.data, found)
    _walk_id_keys(reply.data, found)
    seen, out = set(), []
    for ref in found:
        key = (ref.get("id"), ref.get("name"))
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def resolve(ref: dict, ctx: Ctx) -> dict | None:
    """La pièce de la garde-robe désignée par l'identifiant ; par le nom seulement si la réponse n'a pas d'identifiant."""
    if ref.get("id") is not None:
        return ctx.by_id.get(str(ref["id"]))
    label = str(ref.get("name") or ref.get("label") or "").strip().lower()
    if label in ctx.by_name:
        return ctx.by_name[label]
    for name, item in ctx.by_name.items():
        if label and (label in name or name in label):
            return item
    return None


def outfits_of(reply: Reply, ctx: Ctx) -> list[list[dict]]:
    """Tenues de la réponse, chaque pièce résolue vers la garde-robe ({"_unknown": ref} si elle n'y est pas)."""
    outfits = reply.data.get("outfits") if isinstance(reply.data, dict) else None
    if not outfits and isinstance(reply.data, dict) and isinstance(reply.data.get("items"), list) and reply.data["items"]:
        outfits = [{"items": reply.data["items"]}]            # l'AI Stylist répond par UNE tenue : la liste « items »
    result = []
    for outfit in outfits or []:
        pieces = outfit.get("items") if isinstance(outfit, dict) else None
        result.append([resolve(p, ctx) or {"_unknown": p} for p in (pieces or []) if isinstance(p, dict)])
    return result


CLASS_TO_GROUP = {"top": "Tops", "sweater": "Tops", "vest": "Tops", "jacket": "Outerwear", "coat": "Outerwear",
                  "pants": "Bottoms", "shorts": "Bottoms", "skirt": "Bottoms", "dress": "Dresses", "shoe": "Shoes"}


def group_of(item: dict) -> str:
    """Groupe BO1 de la pièce (Tops, Bottoms, Dresses, Outerwear, Shoes...) : le champ, sinon celui de la catégorie."""
    return str(item.get("group") or item.get("category_group") or CLASS_TO_GROUP.get(str(item.get("category", "")), ""))


def temperature_c(weather: dict | None) -> float | None:
    if not isinstance(weather, dict):
        return None
    value = weather.get("temp_max", weather.get("temp"))
    if not isinstance(value, (int, float)):
        return None
    return (value - 32) * 5 / 9 if str(weather.get("unit", "C")).upper().startswith("F") else float(value)


# --------------------------------------------------------------------------------------------- contrat
def check_contract(expect: dict, reply: Reply) -> list[CheckResult]:
    out = [CheckResult("contract", "état valide", reply.state in VALID_STATES,
                       f"état « {reply.state} » hors completed / input-required / failed"
                       if reply.state not in VALID_STATES else "")]
    wanted = expect.get("state")
    if wanted:
        allowed = wanted if isinstance(wanted, list) else [wanted]
        out.append(CheckResult("contract", "état attendu", reply.state in allowed,
                               f"état « {reply.state} », attendu « {' ou '.join(allowed)} »" if reply.state not in allowed else ""))
    if reply.state == "completed":
        out.append(CheckResult("contract", "réponse non vide", bool(reply.text.strip() or reply.data),
                               "état completed mais ni texte ni données"))
    for key in expect.get("required_fields") or []:
        present = key in reply.data and reply.data[key] not in (None, "")
        out.append(CheckResult("contract", f"champ « {key} »", present, f"champ obligatoire « {key} » absent"))
    return out


# --------------------------------------------------------------------------------------------- ancrage
def check_grounding(reply: Reply, ctx: Ctx) -> list[CheckResult]:
    out = []
    for ref in item_refs(reply):
        label = f"{ref.get('name') or '?'} ({ref.get('id')})"
        if resolve(ref, ctx) is not None:
            out.append(CheckResult("grounding", f"pièce {label}", True))
            continue
        reason = "absente de la garde-robe de l'utilisatrice (inventée ou d'une autre utilisatrice)"
        if ctx.foreign_probe and ref.get("id") is not None and ctx.foreign_probe(str(ref["id"])) == 200:
            reason = "pièce d'une autre utilisatrice lisible : fuite d'isolation"
        out.append(CheckResult("grounding", f"pièce {label}", False, reason))
    return out


# --------------------------------------------------------------------------------------------- règles métier
def rule_complete_outfit(reply: Reply, ctx: Ctx, expect: dict) -> list[CheckResult]:
    outfits = outfits_of(reply, ctx)
    if not outfits:
        return [CheckResult("rules", "tenue complète", False, "aucune tenue dans la réponse")]
    cold = expect.get("cold")
    temperature = temperature_c((reply.data or {}).get("weather"))
    if cold is None and temperature is not None:
        cold = temperature <= 15
    layer_needed = bool(cold or expect.get("rain"))
    out = []
    for number, outfit in enumerate(outfits, 1):
        groups = {group_of(p) for p in outfit if "_unknown" not in p}
        problems = []
        if any("_unknown" in p for p in outfit):
            problems.append("pièce inconnue de la garde-robe")
        if "Dresses" not in groups and not ({"Tops", "Bottoms"} <= groups):
            problems.append("ni robe, ni haut + bas")
        if "Shoes" not in groups and any(group_of(i) == "Shoes" for i in ctx.wardrobe):
            problems.append("pas de chaussures")
        if layer_needed and "Outerwear" not in groups:
            problems.append("pas de couche supplémentaire alors qu'il fait froid ou qu'il pleut")
        out.append(CheckResult("rules", f"tenue {number} complète", not problems, ", ".join(problems)))
    return out


RAIN_ANNOUNCED = re.compile(r"(pluie|pleut|rain|showers?)", re.I)


def rule_layer_when_rain_announced(reply: Reply, ctx: Ctx) -> list[CheckResult]:
    """Si la réponse annonce de la pluie, chaque tenue doit avoir une couche extérieure (la pluie ne se commande pas :
    on ne l'exige donc que lorsque l'agent lui-même la mentionne)."""
    if not RAIN_ANNOUNCED.search(reply.text):
        return [CheckResult("rules", "couche si pluie annoncée", True, "pas de pluie annoncée : contrôle non applicable")]
    out = []
    for number, outfit in enumerate(outfits_of(reply, ctx), 1):
        has_layer = any(group_of(p) == "Outerwear" for p in outfit if "_unknown" not in p)
        out.append(CheckResult("rules", f"couche tenue {number} (pluie annoncée)", has_layer,
                               "pluie annoncée mais aucune veste dans la tenue" if not has_layer else ""))
    return out or [CheckResult("rules", "couche si pluie annoncée", False, "pluie annoncée mais aucune tenue")]


def rule_dress_code(reply: Reply, ctx: Ctx, expect: dict) -> list[CheckResult]:
    out = []
    for number, outfit in enumerate(outfits_of(reply, ctx), 1):
        bad = []
        for piece in outfit:
            known = "_unknown" not in piece
            name = str(piece.get("name") if known else piece["_unknown"].get("name") or "")
            label = " ".join(str(piece.get(k, "")) for k in ("name", "subcategory", "category")) if known else name
            if BUSINESS_FORBIDDEN.search(label):
                bad.append(name)
        out.append(CheckResult("rules", f"dress code tenue {number}", not bad,
                               "pièce interdite en business : " + ", ".join(bad) if bad else ""))
    if not out:
        out.append(CheckResult("rules", "dress code", True, "aucune tenue à contrôler"))
    return out


def rule_no_change_without_confirmation(reply: Reply, ctx: Ctx) -> list[CheckResult]:
    ok = reply.state == "input-required" and not ctx.changed_ids and not (reply.data or {}).get("updated")
    return [CheckResult("rules", "aucune modification sans confirmation", ok,
                        f"état « {reply.state} », {len(ctx.changed_ids)} pièce(s) modifiée(s) avant toute confirmation"
                        if not ok else "")]


def rule_nothing_changed(ctx: Ctx) -> list[CheckResult]:
    return [CheckResult("rules", "garde-robe inchangée", not ctx.changed_ids,
                        f"{len(ctx.changed_ids)} pièce(s) modifiée(s)" if ctx.changed_ids else "")]


def rule_change_applied(reply: Reply, ctx: Ctx) -> list[CheckResult]:
    ok = bool(ctx.changed_ids) or bool((reply.data or {}).get("updated"))
    return [CheckResult("rules", "modification appliquée après confirmation", ok, "aucune modification après le « oui »")]


def rule_trip_constraints(reply: Reply) -> list[CheckResult]:
    """Cas infaisable : l'agent doit le dire (état non completed, ou texte explicite), pas relâcher en silence."""
    data = reply.data or {}
    explicit = (reply.state != "completed" or bool(INFEASIBLE_HINT.search(reply.text))
                or str(data.get("optimization_status", "")).upper() == "INFEASIBLE"
                or bool(data.get("suggestions")) or bool(data.get("errors")))
    return [CheckResult("rules", "contrainte non relâchée en silence", explicit,
                        "réponse completed sans signaler que la contrainte ne tient pas" if not explicit else "")]


def rule_refuses(reply: Reply) -> list[CheckResult]:
    sourced = bool(reply.data.get("sources")) and bool(CITATION.search(reply.text))
    ok = bool(DONT_KNOW.search(reply.text)) and not sourced
    return [CheckResult("rules", "refus (« I don't know »)", ok,
                        "l'agent répond au lieu de refuser une question sans source" if not ok else "")]


def rule_has_citations(reply: Reply) -> list[CheckResult]:
    count = len(CITATION.findall(reply.text)) or (1 if reply.data.get("sources") else 0)
    return [CheckResult("rules", "réponse sourcée", count > 0, "aucune source citée" if count == 0 else "")]


def rule_finds_items(reply: Reply, ctx: Ctx, expect: dict) -> list[CheckResult]:
    found = [r for r in item_refs(reply) if resolve(r, ctx) is not None]
    needed = int(expect.get("min_items", 1))
    return [CheckResult("rules", "pièces trouvées", len(found) >= needed,
                        f"{len(found)} pièce(s) trouvée(s), {needed} attendue(s)" if len(found) < needed else "")]


RULES = {
    "complete_outfit": lambda reply, ctx, expect: rule_complete_outfit(reply, ctx, expect),
    "dress_code_business": lambda reply, ctx, expect: rule_dress_code(reply, ctx, expect),
    "no_change_without_confirmation": lambda reply, ctx, expect: rule_no_change_without_confirmation(reply, ctx),
    "change_applied": lambda reply, ctx, expect: rule_change_applied(reply, ctx),
    "layer_when_rain_announced": lambda reply, ctx, expect: rule_layer_when_rain_announced(reply, ctx),
    "nothing_changed": lambda reply, ctx, expect: rule_nothing_changed(ctx),
    "trip_constraints": lambda reply, ctx, expect: rule_trip_constraints(reply),
    "refuses": lambda reply, ctx, expect: rule_refuses(reply),
    "has_citations": lambda reply, ctx, expect: rule_has_citations(reply),
    "finds_items": lambda reply, ctx, expect: rule_finds_items(reply, ctx, expect),
}


def check_rules(expect: dict, reply: Reply, ctx: Ctx) -> list[CheckResult]:
    out = []
    for name in expect.get("rules") or []:
        if name not in RULES:
            out.append(CheckResult("rules", name, False, "règle inconnue dans le jeu de test"))
        elif reply.state == "failed" and name != "refuses":
            out.append(CheckResult("rules", name, False, "l'agent a échoué : règle non vérifiable"))
        else:
            out.extend(RULES[name](reply, ctx, expect))
    return out


# --------------------------------------------------------------------------------------------- citations
def available_markers(reply: Reply) -> set[int]:
    """Numéros de [S#] réellement renvoyés : « citations[].marker » de BO5, sinon l'ordre de « sources »."""
    data = reply.data or {}
    markers = {int(m) for c in data.get("citations") or [] if isinstance(c, dict)
               for m in re.findall(r"\d+", str(c.get("marker", "")))}
    if markers:
        return markers
    sources = data.get("sources") or []
    for source in sources:
        if isinstance(source, dict) and source.get("marker"):
            markers.update(int(m) for m in re.findall(r"\d+", str(source["marker"])))
    return markers or set(range(1, len(sources) + 1))


def check_citations(reply: Reply) -> list[CheckResult]:
    cited = sorted({int(n) for n in CITATION.findall(reply.text)})
    if not cited:
        return []
    available = available_markers(reply)
    missing = [n for n in cited if n not in available]
    return [CheckResult("citations", "chaque [S#] correspond à une source renvoyée", not missing,
                        "citation(s) sans source : " + ", ".join(f"[S{n}]" for n in missing) if missing else "")]


# --------------------------------------------------------------------------------------------- routage
def check_routing(expect: dict, reply: Reply) -> list[CheckResult]:
    wanted = expect.get("route")
    if not wanted:
        return []
    return [CheckResult("routing", "route attendue", reply.route == wanted,
                        f"route « {reply.route} », attendue « {wanted} »" if reply.route != wanted else "")]


# --------------------------------------------------------------------------------------------- robustesse
def check_robustness(expect: dict, reply: Reply) -> list[CheckResult]:
    server_error = (reply.http_status or 0) >= 500
    out = [CheckResult("robustness", "aucune erreur HTTP 5xx", not server_error, f"HTTP {reply.http_status}" if server_error else ""),
           CheckResult("robustness", "aucune trace d'erreur dans la réponse", not CRASH_HINT.search(reply.text),
                       "texte d'erreur technique montré à l'utilisatrice" if CRASH_HINT.search(reply.text) else "")]
    if expect.get("service_down"):
        ok = reply.state == "failed" and not server_error
        out.append(CheckResult("robustness", "service arrêté : échec propre (failed)", ok,
                               f"état « {reply.state} », HTTP {reply.http_status}" if not ok else ""))
    return out


# --------------------------------------------------------------------------------------------- performance
def check_performance(agent: str, expect: dict, reply: Reply) -> list[CheckResult]:
    limit = float(expect.get("max_latency_s") or (90 if AGENTS[agent].llm else 15))
    seconds = reply.latency_ms / 1000
    return [CheckResult("performance", f"latence ≤ {limit:.0f} s", seconds <= limit,
                        f"{seconds:.1f} s" if seconds > limit else "")]


def run_checks(agent: str, expect: dict, reply: Reply, ctx: Ctx) -> list[CheckResult]:
    """Tous les contrôles du code pour un pas de test. Réponse « failed » : ni ancrage ni citations à vérifier."""
    results = check_contract(expect, reply) + check_robustness(expect, reply) + check_routing(expect, reply)
    if reply.state != "failed":
        results += check_grounding(reply, ctx) + check_citations(reply)
    results += check_rules(expect, reply, ctx)
    results += check_performance(agent, expect, reply)
    return results
