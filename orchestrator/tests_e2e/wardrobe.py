"""Garde-robe du compte de test (15 pièces, sans images, sans blazer) et accès Supabase du compte de test.

Les lignes sont écrites dans la table `items` avec la clé anon et le JETON du compte de test : la règle RLS
« own items » limite l'écriture à ce compte. Aucune clé service_role, aucun code de BO1 modifié. Chaque ligne porte le
tag `e2e-test` : `unseed` ne supprime que celles-là. Aucun secret ici : les identifiants viennent de .env.test.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

TAG = "e2e-test"

# (nom, catégorie BO1, groupe, sous-catégorie, couleur, matière, style, formalité 1..5, chaleur 1..5)
# Formalités choisies pour que le dress code « business » (moyenne >= 3, chaque pièce >= 2) laisse un petit nombre de
# tenues conformes : de quoi proposer 3 tenues, puis épuiser le choix en quelques « j'aime pas ».
PIECES = [
    ("White Cotton Shirt", "top", "Tops", "shirt", "white", "cotton", "business", 4, 2),
    ("Cream Silk Blouse", "top", "Tops", "blouse", "cream", "100% silk", "elegant", 4, 2),
    ("Light Blue Denim Shirt", "top", "Tops", "shirt", "light blue", "denim", "casual", 1, 2),
    ("Beige Off-Shoulder Sweater", "sweater", "Tops", "off-shoulder sweater", "beige", "wool knit", "romantic", 4, 3),
    ("Burgundy Chunky Hoodie", "sweater", "Tops", "hoodie", "burgundy", "cotton fleece", "casual", 1, 4),
    ("Black T-Shirt", "top", "Tops", "t-shirt", "black", "cotton", "casual", 1, 1),
    ("Black Tailored Trousers", "pants", "Bottoms", "trousers", "black", "wool blend", "business", 4, 3),
    ("Navy Joggers", "pants", "Bottoms", "joggers", "navy", "cotton", "sporty", 1, 2),
    ("Blue Jeans", "pants", "Bottoms", "jeans", "denim blue", "denim", "casual", 1, 3),
    ("Plaid Wool Mini Skirt", "skirt", "Bottoms", "mini skirt", "grey", "wool", "classic", 4, 3),
    ("Black Pleated Midi Skirt", "skirt", "Bottoms", "midi skirt", "black", "polyester", "classic", 4, 2),
    ("Grey Wrap Dress", "dress", "Dresses", "wrap dress", "grey", "jersey", "elegant", 4, 2),
    ("Black Leather Biker Jacket", "jacket", "Outerwear", "biker jacket", "black", "leather", "streetwear", 3, 3),
    ("Olive Military Jacket", "jacket", "Outerwear", "military jacket", "olive", "cotton", "casual", 1, 3),
    ("Navy Denim Skirt", "skirt", "Bottoms", "denim skirt", "navy", "denim", "casual", 1, 2),
]
# Pièces que le dress code business écarte d'office (règles absolues) : minijupe (O3) et pull épaules dénudées (O4)
FORBIDDEN_NAMES = {"Plaid Wool Mini Skirt", "Beige Off-Shoulder Sweater"}
SILK_NAME = "Cream Silk Blouse"
JACKETS = {"Black Leather Biker Jacket", "Olive Military Jacket"}


def rows(user_id: str | None = None) -> list[dict]:
    """Lignes `items` complètes (user_id = le compte de test, exigé par la règle RLS)."""
    out = []
    for name, category, group, subcategory, color, material, style, formality, warmth in PIECES:
        row = {"name": name, "category": category, "category_group": group, "subcategory": subcategory,
               "color_name": color, "color_family": "neutral", "pattern": "solid", "material": material,
               "seasons": ["autumn", "winter", "spring"], "style": style, "occasions": ["work", "casual"],
               "formality": formality, "warmth": warmth, "description": f"{name} (compte de test e2e)",
               "tags": [TAG], "needs_review": False, "status": "confirmed", "zone": "rail",
               "enrichment_source": "e2e-test"}
        if user_id:
            row["user_id"] = user_id
        out.append(row)
    return out


# ---------------------------------------------------------------------------------------------- Supabase
class SupabaseError(RuntimeError):
    pass


def _request(method: str, url: str, anon: str, token: str | None = None, body=None, extra=None):
    headers = {"apikey": anon, "Accept": "application/json", **(extra or {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw) if raw else {}
        except ValueError:
            detail = {}
        raise SupabaseError(f"HTTP {exc.code} {detail.get('code', '')} {str(detail.get('message', ''))[:120]}") from exc
    except urllib.error.URLError as exc:
        raise SupabaseError(f"Supabase injoignable : {type(exc.reason).__name__}") from exc


def login(supabase_url: str, anon: str, email: str, password: str) -> dict:
    """Connexion par l'API Auth (clé anon) : renvoie {access_token, user_id}. Ni le jeton ni le mot de passe ne
    sont jamais affichés ni journalisés."""
    _, data = _request("POST", f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password", anon,
                       body={"email": email, "password": password})
    if not data or not data.get("access_token"):
        raise SupabaseError("connexion refusée : pas de jeton dans la réponse")
    return {"access_token": data["access_token"], "user_id": data["user"]["id"]}


def unseed(supabase_url: str, anon: str, session: dict) -> int:
    """Supprime les vêtements de test (tag e2e-test) du compte de test, et eux seuls."""
    base = f"{supabase_url.rstrip('/')}/rest/v1/items"
    query = urllib.parse.urlencode({"tags": f"cs.{{{TAG}}}", "select": "id"})
    _, deleted = _request("DELETE", f"{base}?{query}", anon, session["access_token"],
                          extra={"Prefer": "return=representation"})
    return len(deleted or [])


def seed(supabase_url: str, anon: str, session: dict) -> int:
    """(Re)crée la garde-robe de test : supprime d'abord les lignes taguées, puis insère les 15 pièces."""
    unseed(supabase_url, anon, session)
    base = f"{supabase_url.rstrip('/')}/rest/v1/items"
    _, created = _request("POST", base, anon, session["access_token"], rows(session["user_id"]),
                          {"Prefer": "return=representation"})
    return len(created or [])
