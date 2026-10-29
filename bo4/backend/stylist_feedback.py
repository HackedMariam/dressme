"""Feedback utilisateur (I76) et profil de style personnel (I77) du Stylist Agent.

- I76 : chaque 👍 / 👎 sur une tenue est enregistré (fichier JSON local, sans base de données).
- I77 : un profil est calculé à partir de ces retours (affinité par vêtement et par couleur) ;
  il donne un BONUS de personnalisation ajouté au score du moteur BO4 pour reclasser les tenues.
  Une tenue explicitement rejetée n'est plus jamais reproposée.

C'est une personnalisation heuristique et explicable, pas un modèle appris : les poids sont
des choix de conception, faciles à justifier et à ajuster.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Optional

ITEM_WEIGHT = 3.0        # points de bonus par unité d'affinité d'un vêtement
COLOR_WEIGHT = 1.0       # points de bonus par unité d'affinité d'une couleur
ITEM_CAP, COLOR_CAP = 2, 3
BONUS_CAP = 10.0         # le bonus total reste dans [-10, +10] points sur 100
DISLIKE_WEIGHT = 0.5     # un 👎 vise une COMBINAISON (déjà écartée) : pénalité réduite sur chaque pièce


class FeedbackStore:
    """Stockage des retours. Sans chemin : en mémoire (tests). Avec chemin : fichier JSON."""

    def __init__(self, path: Optional[str | Path] = None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._records: list[dict] = []
        if self.path and self.path.is_file():
            self._records = json.loads(self.path.read_text(encoding="utf-8")).get("records", [])

    def add(self, verdict: str, items: list[dict], occasion: Optional[str] = None,
            user: str = "local") -> dict:
        if verdict not in {"like", "dislike"}:
            raise ValueError("verdict doit valoir 'like' ou 'dislike'")
        record = {
            "user": user, "verdict": verdict, "occasion": occasion,
            "item_ids": sorted(str(item["id"]) for item in items),
            "items": [{"id": str(item["id"]), "name": item.get("name"), "color": item.get("color")}
                      for item in items],
            "at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        with self._lock:
            self._records.append(record)
            if self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps({"records": self._records}, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        return record

    def records(self, user: str = "local") -> list[dict]:
        return [r for r in self._records if r.get("user") == user]

    def disliked_outfits(self, user: str = "local") -> set[frozenset]:
        return {frozenset(r["item_ids"]) for r in self.records(user) if r["verdict"] == "dislike"}

    def profile(self, user: str = "local") -> dict:
        item_affinity: dict[str, float] = {}
        color_affinity: dict[str, float] = {}
        names: dict[str, str] = {}
        for record in self.records(user):
            delta = 1.0 if record["verdict"] == "like" else -DISLIKE_WEIGHT
            for item in record["items"]:
                item_affinity[item["id"]] = item_affinity.get(item["id"], 0) + delta
                names[item["id"]] = item.get("name") or item["id"]
            for color in {item.get("color") for item in record["items"]} - {None, "unknown"}:
                color_affinity[color] = color_affinity.get(color, 0) + delta
        records = self.records(user)
        return {
            "likes": sum(r["verdict"] == "like" for r in records),
            "dislikes": sum(r["verdict"] == "dislike" for r in records),
            "item_affinity": item_affinity,
            "color_affinity": color_affinity,
            "liked_items": [names[i] for i, v in sorted(item_affinity.items(), key=lambda kv: -kv[1]) if v > 0][:5],
            "disliked_items": [names[i] for i, v in sorted(item_affinity.items(), key=lambda kv: kv[1]) if v < 0][:5],
        }


def _clamp(value: float, cap: float) -> float:
    return max(-cap, min(cap, value))


def personal_bonus(items: list[dict], profile: Optional[dict]) -> float:
    """Bonus (en points sur 100) d'une tenue d'après le profil de l'utilisateur."""
    if not profile or not (profile["likes"] or profile["dislikes"]):
        return 0.0
    bonus = 0.0
    for item in items:
        bonus += ITEM_WEIGHT * _clamp(profile["item_affinity"].get(str(item["id"]), 0), ITEM_CAP)
    for color in {item.get("color") for item in items}:
        bonus += COLOR_WEIGHT * _clamp(profile["color_affinity"].get(color, 0), COLOR_CAP)
    return round(_clamp(bonus, BONUS_CAP), 1)
