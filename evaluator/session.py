"""Session d'évaluation : le compte de test, sa garde-robe de référence et le suivi des modifications.

Tout passe par les endpoints de BO1 avec le jeton du compte de test : GET /api/items (la vérité terrain de l'ancrage),
PATCH /api/items/{id} (remise en état après un cas de correction confirmée). Aucun accès direct à la base.
"""
from __future__ import annotations

import urllib.parse

from . import auth, config
from .net import call

TAG = "eval-test"
# (nom, catégorie BO1, groupe, sous-catégorie, couleur, matière, style, formalité 1..5, chaleur 1..5)
SHOES = [
    ("Black Leather Oxford Shoes", "shoe", "Shoes", "oxford", "black", "leather", "business", 5, 3),
    ("White Canvas Sneakers", "shoe", "Shoes", "sneakers", "white", "canvas", "casual", 1, 2),
    ("Brown Leather Ankle Boots", "shoe", "Shoes", "ankle boots", "brown", "leather", "classic", 3, 4),
]

TRACKED_FIELDS = ("name", "category", "group", "color_name", "color_family", "pattern", "material", "style",
                  "seasons", "occasions")


class Session:
    def __init__(self, credentials: dict[str, str]):
        self.credentials = credentials
        login = auth.login(credentials)
        self.token, self.user_id = login["token"], login["user_id"]
        self.bo1 = config.URLS["bo1"]

    def wardrobe(self) -> list[dict]:
        status, payload, error, _ = call("GET", f"{self.bo1}/api/items", token=self.token, timeout=30)
        if status != 200 or not isinstance(payload, list):
            raise RuntimeError(f"garde-robe illisible (BO1 /api/items : HTTP {status or error}) : démarrer BO1 d'abord")
        return payload

    def foreign_probe(self, item_id: str) -> int | None:
        """Statut de GET /api/items/{id} : 200 pour un id absent de SA garde-robe = fuite d'isolation."""
        status, _, _, _ = call("GET", f"{self.bo1}/api/items/{item_id}", token=self.token, timeout=15)
        return status

    @staticmethod
    def diff(before: list[dict], after: list[dict]) -> dict[str, dict]:
        """{id: {champ: ancienne valeur}} pour chaque pièce modifiée, ajoutée ou supprimée."""
        old = {str(i.get("id")): i for i in before}
        new = {str(i.get("id")): i for i in after}
        changes: dict[str, dict] = {}
        for item_id in old.keys() | new.keys():
            if item_id not in new:
                changes[item_id] = {"_deleted": True}
            elif item_id not in old:
                changes[item_id] = {"_added": True}
            else:
                fields = {k: old[item_id].get(k) for k in TRACKED_FIELDS if old[item_id].get(k) != new[item_id].get(k)}
                if fields:
                    changes[item_id] = fields
        return changes

    def restore(self, originals: dict[str, dict]) -> list[str]:
        """Remet les champs modifiés par un cas de correction (PATCH BO1, sans re-confirmer). Renvoie les ids remis."""
        restored = []
        for item_id, fields in originals.items():
            patch = {k: v for k, v in fields.items() if not k.startswith("_") and k not in ("name", "group")}
            if not patch:
                continue
            status, _, _, _ = call("PATCH", f"{self.bo1}/api/items/{item_id}", token=self.token,
                                   body={"fields": patch, "confirm": False}, timeout=30)
            if status == 200:
                restored.append(item_id)
        return restored

    def clear_orchestrator_history(self) -> None:
        """L'orchestrateur 8070 enregistre les conversations du compte de test : on les efface (et les goûts)."""
        call("DELETE", f"{config.URLS['orchestrator']}/api/history?reset_profile=true", token=self.token, timeout=30)

    # ------------------------------------------------------------------------------- chaussures de test (facultatif)
    def _rest(self, method: str, query: str = "", body=None, prefer: str = "return=representation"):
        url = f"{self.credentials['SUPABASE_URL'].rstrip('/')}/rest/v1/items{query}"
        return call(method, url, token=self.token, body=body, headers={"apikey": self.credentials["SUPABASE_ANON_KEY"],
                                                                        "Prefer": prefer}, timeout=30)

    def unseed_shoes(self) -> int:
        """Supprime les chaussures de test (tag eval-test) du compte de test, et elles seules."""
        _, deleted, _, _ = self._rest("DELETE", "?" + urllib.parse.urlencode({"tags": f"cs.{{{TAG}}}", "select": "id"}))
        return len(deleted) if isinstance(deleted, list) else 0

    def seed_shoes(self) -> int:
        """Ajoute 3 paires de chaussures au compte de test : la garde-robe e2e n'en contient pas, or une tenue complète en exige."""
        self.unseed_shoes()
        rows = [{"user_id": self.user_id, "name": n, "category": c, "category_group": g, "subcategory": sub,
                 "color_name": color, "color_family": "neutral", "pattern": "solid", "material": m, "seasons": ["autumn", "winter", "spring"],
                 "style": st, "occasions": ["work", "casual"], "formality": f, "warmth": w, "description": f"{n} (compte de test évaluateur)",
                 "tags": [TAG], "needs_review": False, "status": "confirmed", "zone": "floor", "enrichment_source": "eval-test"}
                for n, c, g, sub, color, m, st, f, w in SHOES]
        _, created, _, _ = self._rest("POST", body=rows)
        return len(created) if isinstance(created, list) else 0
