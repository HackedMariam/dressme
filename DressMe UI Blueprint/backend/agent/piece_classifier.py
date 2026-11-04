"""Gives a canonical subcategory to the pieces whose name the keyword rules of wardrobe_source.py do not know.

The problem: BO1 writes names such as "mac", "culottes" or "fanny pack". The rules of coverage.py only know a closed
list of subcategories (coat, trousers, bag...), and a piece with an unknown name counts for no need at all.

How it works
    1. The keyword rules always go first. This module only sees what they left unrecognised.
    2. The category (jacket -> outerwear) comes from the detector and is trusted. Only the subcategory is asked.
    3. The language model must choose from OUR closed list for that category, or answer "unknown". Anything else
       it says is rejected, so it can never invent a subcategory. In a trial on 25 unseen names it was right 20
       times, said "unknown" 5 times and was never wrong (FashionCLIP text: 6 confident mistakes, see the history).
    4. One request carries all the unknown names of a wardrobe, and every answer, "unknown" included, is saved in
       data/piece_classes_cache.json: a name is asked once, whoever owns it.
    5. Only the category and the subcategory text are sent. No user id, no photo, no other piece, no personal data.
    6. Any problem (no key, offline, bad answer) leaves the piece exactly as it was before: nothing is guessed, and
       a failed request is not cached, so it is tried again later.

The language model never decides what is missing: it only files a piece in a box the rules already know.
"""

import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHE_FILE = DATA_DIR / "piece_classes_cache.json"      # gitignored: {"category|text|labels": "coat" | "unknown"}

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
TIMEOUT_SECONDS = 12
MAX_PIECES_PER_REQUEST = 40
UNKNOWN = "unknown"
# A name that only repeats the category carries no information ("top", "bag"): asking about it would be a guess.
GENERIC_WORDS = {"top", "tops", "bottom", "bottoms", "bag", "shoe", "shoes", "jacket", "dress", "accessory",
                 "accessories", "outerwear", "item", "piece", "clothing", "other", "unknown", "garment"}

logger = logging.getLogger("dressme.bo3.pieces")
_lock = threading.Lock()
_cache: dict[str, str] | None = None


def enabled() -> bool:
    """On when a language-model key exists. BO3_LLM_SUBCATEGORIES=0 turns it off."""
    if os.getenv("BO3_LLM_SUBCATEGORIES", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def clean_text(value: Any) -> str:
    """The piece's own words, lower-cased and without symbols, cut to a sane length."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' -]+", " ", str(value or "").lower())).strip()[:60]


def is_informative(category: str, text: str) -> bool:
    words = set(text.replace("-", " ").split())
    return bool(words) and not words <= (GENERIC_WORDS | {category})


def _key(category: str, text: str, labels: Sequence[str]) -> str:
    # The list is part of the key: when the vocabulary grows, an old "unknown" is asked again.
    return f"{category}|{text}|{hashlib.sha1(','.join(sorted(labels)).encode()).hexdigest()[:8]}"


def _load() -> dict[str, str]:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save() -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError:
        pass   # the cache is a bonus: never fail a wardrobe load because it cannot be written


def _ask(pieces: list[tuple[str, str]], canonical: Mapping[str, Sequence[str]]) -> dict[tuple[str, str], str]:
    """One request for several unknown names. Returns only the answers that passed validation."""
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        timeout=TIMEOUT_SECONDS,
        max_retries=1,
    )
    allowed = {category: list(canonical[category]) for category in {c for c, _ in pieces}}
    prompt = (
        "You file wardrobe pieces into a fixed list of subcategories. For each piece pick the ONE best subcategory "
        "from the allowed list of its category. Answer \"unknown\" when no subcategory clearly fits: a wrong answer "
        "is worse than \"unknown\".\n"
        f"Allowed subcategories per category: {json.dumps(allowed)}\n"
        f"Pieces: {json.dumps([{'id': i, 'category': c, 'name': t} for i, (c, t) in enumerate(pieces)])}\n"
        'Reply as JSON only: {"answers": [{"id": 0, "subcategory": "..."}]}'
    )
    reply = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL), temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    answers: dict[tuple[str, str], str] = {}
    for row in json.loads(reply.choices[0].message.content).get("answers", []):
        try:
            category, text = pieces[int(row["id"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        choice = str(row.get("subcategory", "")).strip()
        answers[(category, text)] = choice if choice in allowed[category] else UNKNOWN   # never an invented value
    return answers


def classify_many(pieces: Sequence[tuple[str, str]], canonical: Mapping[str, Sequence[str]]) -> dict[tuple[str, str], str]:
    """{(category, text): canonical subcategory} for the pieces that got a real answer ("unknown" is left out)."""
    wanted = [(c, t) for c, t in dict.fromkeys(pieces) if c in canonical and is_informative(c, t)]
    if not wanted:
        return {}
    found: dict[tuple[str, str], str] = {}
    with _lock:
        cache = _load()
        todo = []
        for category, text in wanted:
            known = cache.get(_key(category, text, canonical[category]))
            if known is None:
                todo.append((category, text))
            elif known != UNKNOWN:
                found[(category, text)] = known
        if todo and enabled():
            for start in range(0, len(todo), MAX_PIECES_PER_REQUEST):
                batch = todo[start:start + MAX_PIECES_PER_REQUEST]
                try:
                    answers = _ask(batch, canonical)
                except Exception as error:      # offline, bad key, malformed reply: leave the pieces untouched
                    logger.warning("piece classification skipped: %s: %s", type(error).__name__, str(error)[:120])
                    break
                for (category, text), choice in answers.items():
                    cache[_key(category, text, canonical[category])] = choice
                    if choice != UNKNOWN:
                        found[(category, text)] = choice
            _save()
    return found
