"""Extraction d'attributs vestimentaires à partir du texte catalogue (BO4).

Règles heuristiques appliquées à `prod_name` et `detail_desc` (catalogue H&M,
en anglais). Elles donnent une COUVERTURE mesurable, pas une précision
validée : aucune évaluation sur un jeu annoté n'a encore été faite.

Principes :
- une preuve est toujours un extrait exact du texte d'entrée ;
- les faux amis et éléments décoratifs ("padded shoulders", "faux fur trim",
  "quilted sections"...) sont écartés et conservés à part ;
- les indices se combinent par intersection de niveaux plausibles : une
  description contradictoire donne "unknown", jamais un "medium" par défaut ;
- la plage de la catégorie (outfit_engine.CATEGORY_WARMTH) sert seulement à
  départager ; un désaccord texte/catégorie est conservé comme conflit.
"""

import re
from dataclasses import dataclass

from outfit_engine import CATEGORY_WARMTH, WARMTH_LEVELS, normalize


@dataclass(frozen=True)
class GarmentAttributes:
    # light | medium | heavy | unknown
    warmth: str = "unknown"
    # text               : la description seule tranche ;
    # text_and_category  : la description, restreinte par la catégorie, tranche ;
    # text_partial       : indices compatibles avec plusieurs niveaux ;
    # text_conflict      : la description contredit la plage de la catégorie ;
    # text_contradictory : la description contient des indices incompatibles ;
    # none               : aucun indice.
    warmth_source: str = "none"
    warmth_evidence: tuple = ()
    # Niveaux suggérés par le texte seul (conservés même en cas de conflit).
    text_warmth_levels: tuple = ()
    # Mentions écartées (faux amis, éléments décoratifs).
    ignored_evidence: tuple = ()
    # sleeveless | short | three_quarter | long | unknown
    sleeve_length: str = "unknown"
    # text | text_conflict | none
    sleeve_source: str = "none"
    sleeve_evidence: tuple = ()


def _compile(pattern):
    return re.compile(pattern, re.IGNORECASE)


# --- Chaleur ---------------------------------------------------------------

# Mentions qui contiennent un mot "chaud" ou "léger" sans renseigner sur la
# chaleur du vêtement : elles sont masquées avant la recherche d'indices.
IGNORED = _compile(
    r"padded shoulders?|shoulder pads?|lightly padded|padded (?:cups?|bra|straps?)"
    r"|(?:faux fur|fake fur|imitation fur|faux shearling|shearling|pile|teddy|borg|fleece|quilted|padded)"
    r"(?:[- ]trimmed)? (?:trims?|collar|cuffs?|edges?|details?|sections?|panels?|pompoms?|yoke"
    r"|shoulders|elbow patches|appliqu[ée]s?|patch(?:es)?|ear ?flaps)"
    r"|(?:faux fur|fake fur|pile|teddy|borg|fleece)[- ](?:lined|trimmed) hood"
    r"|trimmed with (?:faux fur|fake fur|pile|teddy)"
    r"|(?:mesh|jersey)[- ]lin(?:ed|ing)|(?:mesh|jersey) lining"
    r"|wool[- ]look"
)

STRONG = _compile(
    r"\bpadded\b|\bpadding\b|\bdown[- ]filled\b|\bdown (?:filling|padding)\b"
    r"|\b\d+\s?% (?:recycled )?down\b|\bdown and feathers?\b|\bfeathers? and down\b"
    r"|\b(?:duck|goose) down\b|\bwadding\b|\bwadded\b|\binsulat\w*|\bpuffer\b|\bparka\b"
    r"|\b(?:faux|fake|imitation) fur\b|\bshearling\b"
)
MODERATE = _compile(
    r"\bwool\b|\bfleece\b|\bquilted\b|\bbrushed inside\b|\bchunky\b|\bcashmere\b"
    r"|\bmohair\b|\balpaca\b|\bpile\b|\bteddy\b|\bborg\b|\bthermal\b|\bthick\b"
)
LIGHT = _compile(
    r"\blightweight\b|\blinen\b|\bmesh\b|\bsheer\b|\bthin\b|\bseersucker\b"
    r"|\bchiffon\b|\bvoile\b|\bairy\b"
)
LIGHTISH = _compile(r"\bfine[- ]knit\b|\bunlined\b")
SLEEVELESS_OUTER = _compile(r"\bgilet\b|\bbody ?warmer\b|\bsleeveless\b")

# Niveaux plausibles signalés par chaque groupe d'indices.
CUE_LEVELS = {
    "strong": {"heavy"},
    "moderate": {"medium", "heavy"},
    "light": {"light"},
    "lightish": {"light", "medium"},
}

# --- Manches ---------------------------------------------------------------

SHORT_SLEEVES = _compile(r"\bshort[- ]sleeved\b|\bshort(?:,? [\w-]+){0,2} sleeves?\b|\bcap sleeves?\b")
LONG_SLEEVES = _compile(r"\blong[- ]sleeved\b|\blong(?:,? [\w-]+){0,2} sleeves?\b")
THREE_QUARTER_SLEEVES = _compile(r"(?:3/4|three-quarter)[- ]length sleeves?")
EXPLICIT_SLEEVELESS = _compile(r"\bsleeveless\b|\bstrapless\b")
STRAPS = _compile(r"\bshoulder straps\b|\bspaghetti straps\b|\bgilet\b|\bbody ?warmer\b")


def _matches(pattern, text, masked):
    """Extraits exacts trouvés hors des zones masquées."""
    found = []
    for m in pattern.finditer(text):
        if not any(start < m.end() and m.start() < end for start, end in masked):
            found.append(m.group(0))
    return found


def _extract_warmth(text, category):
    masked = [m.span() for m in IGNORED.finditer(text)]
    ignored = tuple(text[start:end] for start, end in masked)

    cues = {
        "strong": _matches(STRONG, text, masked),
        "moderate": _matches(MODERATE, text, masked),
        "light": _matches(LIGHT, text, masked),
        "lightish": _matches(LIGHTISH, text, masked),
    }
    evidence = tuple(e for group in cues.values() for e in group)
    if not evidence:
        return GarmentAttributes(ignored_evidence=ignored)

    levels = set(WARMTH_LEVELS)
    for group, found in cues.items():
        if found:
            group_levels = CUE_LEVELS[group]
            if group == "strong" and SLEEVELESS_OUTER.search(text):
                # Rembourré mais sans manches (gilet) : chaud, sans plus de précision.
                group_levels = {"medium", "heavy"}
            levels &= group_levels

    if not levels:
        # Seule combinaison incompatible résolue : un isolant explicitement
        # "lightweight" (ex. "lightweight puffer") est un vêtement de mi-saison.
        only_lightweight = (
            cues["strong"]
            and cues["light"]
            and not cues["lightish"]
            and all(e.lower() == "lightweight" for e in cues["light"])
        )
        if not only_lightweight:
            return GarmentAttributes(
                warmth_source="text_contradictory",
                warmth_evidence=evidence,
                ignored_evidence=ignored,
            )
        levels = {"medium"}

    text_levels = tuple(level for level in WARMTH_LEVELS if level in levels)
    category_levels = set(CATEGORY_WARMTH.get(normalize(category), WARMTH_LEVELS))
    narrowed = levels & category_levels

    if not narrowed:
        warmth, source = "unknown", "text_conflict"
    elif len(narrowed) > 1:
        warmth, source = "unknown", "text_partial"
    elif len(levels) == 1:
        warmth, source = narrowed.pop(), "text"
    else:
        warmth, source = narrowed.pop(), "text_and_category"

    return GarmentAttributes(
        warmth=warmth,
        warmth_source=source,
        warmth_evidence=evidence,
        text_warmth_levels=text_levels,
        ignored_evidence=ignored,
    )


def _extract_sleeves(text):
    lengths = {
        "short": [m.group(0) for m in SHORT_SLEEVES.finditer(text)],
        "long": [m.group(0) for m in LONG_SLEEVES.finditer(text)],
        "three_quarter": [m.group(0) for m in THREE_QUARTER_SLEEVES.finditer(text)],
    }
    found = {k: v for k, v in lengths.items() if v}
    sleeveless = [m.group(0) for m in EXPLICIT_SLEEVELESS.finditer(text)]
    straps = [m.group(0) for m in STRAPS.finditer(text)]
    evidence = tuple(e for group in found.values() for e in group) + tuple(sleeveless)

    if len(found) > 1 or (found and sleeveless):
        return "unknown", "text_conflict", evidence
    if found:
        return next(iter(found)), "text", evidence
    if sleeveless or straps:
        # Une longueur explicite l'emporte sur les bretelles ("off-the-shoulder").
        return "sleeveless", "text", tuple(sleeveless) + tuple(straps)
    return "unknown", "none", ()


def extract_attributes(prod_name, detail_desc, category=None):
    """Attributs déduits du nom et de la description d'un article."""
    text = ". ".join(part.strip() for part in (prod_name or "", detail_desc or "") if part and part.strip())
    warmth = _extract_warmth(text, category)
    sleeve_length, sleeve_source, sleeve_evidence = _extract_sleeves(text)
    return GarmentAttributes(
        warmth=warmth.warmth,
        warmth_source=warmth.warmth_source,
        warmth_evidence=warmth.warmth_evidence,
        text_warmth_levels=warmth.text_warmth_levels,
        ignored_evidence=warmth.ignored_evidence,
        sleeve_length=sleeve_length,
        sleeve_source=sleeve_source,
        sleeve_evidence=sleeve_evidence,
    )
