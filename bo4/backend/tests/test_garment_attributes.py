"""Tests de garment_attributes.py (règles d'extraction, ISSUE-04b-data).

Ces tests vérifient le comportement des règles sur des phrases du catalogue.
Ils ne mesurent PAS la précision réelle des règles sur l'ensemble du catalogue.
"""

import pytest

from garment_attributes import GarmentAttributes, extract_attributes
from outfit_engine import CATEGORY_WARMTH, WARMTH_LEVELS

# (prod_name, detail_desc, category, warmth, warmth_source, evidence, ignored)
WARMTH_CASES = [
    # Indices forts
    ("Huffel puffer jacket", "Short, padded jacket in woven fabric with a lined hood. Lined.",
     "jacket", "heavy", "text", ("puffer", "padded"), ()),
    ("", "Padded jacket with a zip down the front.",
     "jacket", "heavy", "text", ("Padded",), ()),
    ("", "Jacket with a filling of 70% recycled down and 30% recycled feathers.",
     "jacket", "heavy", "text", ("70% recycled down",), ()),
    ("", "Jacket with down and feathers filling.",
     "jacket", "heavy", "text", ("down and feathers",), ()),
    ("", "Coat in faux fur. Lined.",
     "coat", "heavy", "text", ("faux fur",), ()),
    ("", "PADDED JACKET", "jacket", "heavy", "text", ("PADDED",), ()),
    # "lightweight puffer" : seule combinaison incompatible résolue (mi-saison)
    ("", "Lightweight puffer jacket in a quilted weave with a detachable hood.",
     "jacket", "medium", "text", ("puffer", "quilted", "Lightweight"), ()),
    # Faux amis et éléments décoratifs
    ("", "Single-breasted jacket with padded shoulders and notch lapels.",
     "blazer", "unknown", "none", (), ("padded shoulders",)),
    ("", "Shirt in cotton with a collar and buttons down the front.",
     "shirt", "unknown", "none", (), ()),
    ("", "Long-sleeved shirt with a button-down collar.",
     "shirt", "unknown", "none", (), ()),
    ("", "Biker jacket in imitation leather with quilted sections on the shoulders.",
     "jacket", "unknown", "none", (), ("quilted sections",)),
    ("", "Jacket in cotton twill with a faux fur trim on the hood.",
     "jacket", "unknown", "none", (), ("faux fur trim",)),
    ("", "Jacket in washed denim with a pile collar and press-studs.",
     "jacket", "unknown", "none", (), ("pile collar",)),
    ("", "Padded parka with a detachable hood with a faux fur trim.",
     "jacket", "heavy", "text", ("Padded", "parka"), ("faux fur trim",)),
    ("", "Padded jacket with a mesh lining.",
     "jacket", "heavy", "text", ("Padded",), ("mesh lining",)),
    ("", "Jacket in wool-look fabric.",
     "jacket", "unknown", "none", (), ("wool-look",)),
    # "wool blend unlined" : intersection {medium, heavy} & {light, medium}
    ("", "Coat in a felted wool blend with notch lapels. Unlined.",
     "coat", "medium", "text", ("wool", "Unlined"), ()),
    # Indices partiels : pas de "medium" par défaut
    ("", "Coat in a felted wool blend with notch lapels. Lined.",
     "coat", "unknown", "text_partial", ("wool",), ()),
    ("", "Padded gilet with a stand-up collar.",
     "jacket", "unknown", "text_partial", ("Padded",), ()),
    # Texte contradictoire
    ("", "Padded jacket in thin, airy nylon.",
     "jacket", "unknown", "text_contradictory", ("Padded", "thin", "airy"), ()),
    # Léger
    ("", "Jacket in linen with notch lapels.",
     "jacket", "light", "text", ("linen",), ()),
    # Texte restreint par la catégorie
    ("", "Jumper in a soft, fine knit with ribbing.",
     "sweater", "medium", "text_and_category", ("fine knit",), ()),
    ("", "Joggers in sweatshirt fabric, brushed inside.",
     "trousers", "medium", "text_and_category", ("brushed inside",), ()),
    # Conflits texte / catégorie : conservés, pas forcés
    ("", "Cable-knit jumper in lightweight cotton.",
     "sweater", "unknown", "text_conflict", ("lightweight",), ()),
    ("", "Cycling shorts in padded jersey.",
     "shorts", "unknown", "text_conflict", ("padded",), ()),
    # Sans catégorie : le texte seul décide
    ("", "Jacket in linen.", None, "light", "text", ("linen",), ()),
    # Sans texte
    (None, None, "jacket", "unknown", "none", (), ()),
    ("", "", "shirt", "unknown", "none", (), ()),
]


@pytest.mark.parametrize(
    "prod_name, desc, category, warmth, source, evidence, ignored", WARMTH_CASES
)
def test_warmth_rules(prod_name, desc, category, warmth, source, evidence, ignored):
    result = extract_attributes(prod_name, desc, category)
    assert (result.warmth, result.warmth_source) == (warmth, source)
    assert result.warmth_evidence == evidence
    assert result.ignored_evidence == ignored


def test_conflict_preserves_text_levels():
    """Un vêtement léger dans une catégorie "chaude" : le texte est conservé."""
    result = extract_attributes("", "Cable-knit jumper in lightweight cotton.", "sweater")
    assert result.warmth == "unknown"
    assert result.text_warmth_levels == ("light",)
    assert not set(result.text_warmth_levels) & set(CATEGORY_WARMTH["sweater"])


def test_partial_preserves_text_levels():
    result = extract_attributes("", "Coat in a felted wool blend. Lined.", "coat")
    assert result.text_warmth_levels == ("medium", "heavy")


def test_padded_shoulders_never_heavy():
    for category in ("blazer", "jacket", "top", None):
        result = extract_attributes("", "Jacket with padded shoulders and shoulder pads.", category)
        assert result.warmth != "heavy"
        assert result.warmth_evidence == ()


@pytest.mark.parametrize("desc", [
    "Shirt with buttons down the front.",
    "Cardigan with press-studs down the front.",
    "Dress with a zip down the back.",
    "Trousers with pleats down the legs.",
    "Jumper with frills down the sleeves.",
])
def test_down_as_direction_is_never_insulation(desc):
    assert extract_attributes("", desc, "jacket").warmth_source == "none"


# (prod_name, detail_desc, sleeve_length, sleeve_source)
SLEEVE_CASES = [
    ("Legolas SS", "Short-sleeved shirt in a patterned viscose weave.", "short", "text"),
    ("", "Jumper with long raglan sleeves and ribbing.", "long", "text"),
    ("", "Blouse with long, wide sleeves.", "long", "text"),
    ("", "Long-sleeved top in jersey.", "long", "text"),
    ("", "Jacket with wide, 3/4-length sleeves.", "three_quarter", "text"),
    ("", "Sleeveless top in jersey.", "sleeveless", "text"),
    ("", "Top with narrow shoulder straps.", "sleeveless", "text"),
    ("", "Padded gilet with a stand-up collar.", "sleeveless", "text"),
    # Une longueur explicite l'emporte sur les bretelles
    ("", "Off-the-shoulder top with narrow shoulder straps and short sleeves.", "short", "text"),
    # Conflits conservés
    ("", "Set with a sleeveless top and a shirt with long sleeves.", "unknown", "text_conflict"),
    ("", "Top with short sleeves and a jacket with long sleeves.", "unknown", "text_conflict"),
    # "Short" qualifie le vêtement, pas les manches
    ("", "Short, padded jacket in woven fabric.", "unknown", "none"),
    ("", "Jumper with frills down the sleeves.", "unknown", "none"),
    (None, None, "unknown", "none"),
]


@pytest.mark.parametrize("prod_name, desc, sleeve, source", SLEEVE_CASES)
def test_sleeve_rules(prod_name, desc, sleeve, source):
    result = extract_attributes(prod_name, desc)
    assert (result.sleeve_length, result.sleeve_source) == (sleeve, source)


def test_sleeve_conflict_keeps_evidence():
    result = extract_attributes("", "Set with a sleeveless top and a shirt with long sleeves.")
    assert set(result.sleeve_evidence) == {"long sleeves", "sleeveless"}


# ---------------------------------------------------------------------------
# Propriétés : provenance, pas d'invention
# ---------------------------------------------------------------------------

ALL_TEXTS = [(c[0], c[1], c[2]) for c in WARMTH_CASES] + [(c[0], c[1], None) for c in SLEEVE_CASES]


@pytest.mark.parametrize("prod_name, desc, category", ALL_TEXTS)
def test_evidence_is_exact_input_text(prod_name, desc, category):
    text = f"{prod_name or ''} {desc or ''}"
    result = extract_attributes(prod_name, desc, category)
    for fragment in result.warmth_evidence + result.ignored_evidence + result.sleeve_evidence:
        assert fragment in text


@pytest.mark.parametrize("prod_name, desc, category", ALL_TEXTS)
def test_resolved_warmth_respects_category_range(prod_name, desc, category):
    result = extract_attributes(prod_name, desc, category)
    assert result.warmth in WARMTH_LEVELS + ("unknown",)
    if result.warmth != "unknown":
        assert result.warmth_source in ("text", "text_and_category")
        assert result.warmth in CATEGORY_WARMTH.get(category, WARMTH_LEVELS)
    else:
        assert result.warmth_source not in ("text", "text_and_category")


def test_deterministic_and_immutable():
    args = ("Huffel puffer jacket", "Short, padded jacket. Lined.", "jacket")
    first = extract_attributes(*args)
    assert first == extract_attributes(*args)
    with pytest.raises(AttributeError):
        first.warmth = "light"


def test_default_is_unknown():
    assert GarmentAttributes() == extract_attributes(None, None)
