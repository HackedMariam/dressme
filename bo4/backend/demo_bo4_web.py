"""Mini-interface web de démonstration BO4 (sans PostgreSQL, sans installation).

Garde-robe : 10 vêtements H&M réels à image locale (3 hauts, 3 bas, 2 vestes,
2 robes), lus dans catalog_products.csv et transformés EXACTEMENT
comme wardrobe_db_adapter.load_user_wardrobe (catégorie, couleur, attributs
extraits du texte). Les tenues, scores et explications viennent de la vraie
fonction outfit_engine.recommend_outfits : rien n'est simulé ni modifié.

Lancement (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m uvicorn demo_bo4_web:app --port 8050
puis ouvrir http://127.0.0.1:8050
"""

from html import escape

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from evaluation.common import CATALOG_CSV, DATA_HM_DIR, read_csv
from garment_attributes import extract_attributes
from outfit_engine import OCCASION_STYLES, SEASONS, garment_role, recommend_outfits
from wardrobe_db_adapter import normalize_category, normalize_color

# Sélection variée (couleurs, chaleur, manches) pour que la saison change visiblement le classement.
ARTICLE_IDS = (
    "0108775044", "0702784001", "0674310002",   # hauts : débardeur blanc, pull gris, blouse bordeaux
    "0719952001", "0547522002", "0399201042",   # bas : short noir, jupe vert foncé, pantalon gris
    "0635510002", "0633226002",                 # vestes : doudoune noire, blazer gris
    "0801843006", "0713783002",                 # robes : rose sans manches, rouge manches longues
)
ROLE_FR = {"top": "Haut", "bottom": "Bas", "outerwear": "Veste", "dress": "Robe"}
SEASON_FR = {"spring": "Printemps", "summer": "Été", "autumn": "Automne", "winter": "Hiver"}
OCCASION_FR = {"university": "Université", "work": "Travail", "evening": "Soirée", "casual": "Décontracté"}


def build_wardrobe():
    """Même transformation que load_user_wardrobe, à partir du CSV du catalogue."""
    catalog = {r["article_id"]: r for r in read_csv(CATALOG_CSV)}
    wardrobe = []
    for index, article_id in enumerate(ARTICLE_IDS, 1):
        row = catalog[article_id]
        category = normalize_category(row["product_type_name"])
        attributes = extract_attributes(row["prod_name"], row["detail_desc"], category)
        item = {
            "id": str(index), "article_id": article_id, "name": row["prod_name"],
            "category": category, "color": normalize_color(row["colour_group_name"]), "style": "unknown",
            "image_path": row["image_path"],
            "warmth": attributes.warmth, "warmth_source": attributes.warmth_source,
            "warmth_evidence": list(attributes.warmth_evidence),
            "text_warmth_levels": list(attributes.text_warmth_levels),
            "sleeve_length": attributes.sleeve_length, "sleeve_source": attributes.sleeve_source,
        }
        if garment_role(item) is not None and (DATA_HM_DIR / item["image_path"]).is_file():
            wardrobe.append(item)
    return wardrobe


WARDROBE = build_wardrobe()
IMAGES = {item["article_id"]: DATA_HM_DIR / item["image_path"] for item in WARDROBE}

app = FastAPI(title="DressMe BO4 démo")


@app.get("/img/{article_id}")
def image(article_id: str):
    path = IMAGES.get(article_id)
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg")


def card(item, small=False):
    return (f'<figure class="{"g small" if small else "g"}"><img src="/img/{escape(item["article_id"])}" '
            f'alt="{escape(item["name"])}" loading="lazy"><figcaption><b>{escape(item["name"])}</b>'
            f'<span>{escape(ROLE_FR.get(garment_role(item), ""))} · {escape(item["category"])} · '
            f'{escape(item["color"])}</span></figcaption></figure>')


def options(choices, labels, selected):
    return "".join(f'<option value="{c}"{" selected" if c == selected else ""}>{escape(labels.get(c, c))}</option>'
                   for c in choices)


@app.get("/", response_class=HTMLResponse)
def home(season: str = Query("autumn"), occasion: str = Query("university")):
    """Recalcule les recommandations à CHAQUE requête (aucun cache)."""
    if season not in SEASONS or occasion not in OCCASION_STYLES:
        raise HTTPException(status_code=422, detail="saison ou occasion inconnue")
    ranked = recommend_outfits(WARDROBE, occasion=occasion, season=season, top_k=1000, diversify=False)
    top3 = recommend_outfits(WARDROBE, occasion=occasion, season=season, top_k=3)
    outfits = []
    for rank, outfit in enumerate(top3, 1):
        scores = "".join(f'<div><span>{label}</span><b>{outfit[key]:.1f}</b></div>' for label, key in
                         (("Couleur ×0,30", "color_score"), ("Style ×0,20", "style_score"),
                          ("Occasion ×0,30", "occasion_score"), ("Saison ×0,20", "season_score")))
        reasons = "".join(f"<li>{escape(line)}</li>" for line in outfit["explanations"])
        outfits.append(
            f'<article class="outfit"><header><h3>Tenue n°{rank}</h3><p class="score">{outfit["score"]:.2f}'
            f'<small>/ 100</small></p></header><div class="row">{"".join(card(i, True) for i in outfit["items"])}'
            f'</div><div class="scores">{scores}</div><ul>{reasons}</ul></article>')
    occasion_inactive = all(i.get("style", "unknown") == "unknown" for i in WARDROBE)
    note = ('<p class="note">Critère Occasion actuellement inactif : les styles des vêtements ne sont pas '
            'renseignés (<code>style=unknown</code>), donc le score Occasion reste à 60 quelle que soit '
            "l'occasion choisie.</p>") if occasion_inactive else ""
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>DressMe BO4 démo</title>
<style>
:root {{ --bg:#f5f6f8; --card:#fff; --ink:#1b2330; --muted:#5d6675; --line:#dde1e7; --accent:#2c5d8f; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.5 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:20px 16px 48px; display:grid; gap:24px; }}
h1 {{ margin:0; font-size:1.7rem; }} h2 {{ margin:0 0 10px; font-size:1.15rem; }} h3 {{ margin:0; }}
.muted {{ color:var(--muted); }}
form {{ display:flex; flex-wrap:wrap; gap:12px; align-items:end; background:var(--card); border:1px solid var(--line);
  border-radius:10px; padding:14px; }}
label {{ display:grid; gap:4px; font-weight:600; }} select, button {{ font:inherit; padding:8px 10px; border-radius:8px;
  border:1px solid var(--line); }} button {{ background:var(--accent); color:#fff; border-color:var(--accent); cursor:pointer; }}
.wardrobe {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(130px, 1fr)); gap:12px; }}
.g {{ margin:0; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
.g img {{ width:100%; aspect-ratio:2/3; object-fit:contain; background:#fff; display:block; }}
.g figcaption {{ padding:8px; display:grid; gap:2px; font-size:.82rem; }} .g span {{ color:var(--muted); }}
.outfits {{ display:grid; gap:16px; }}
.outfit {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; display:grid; gap:12px; }}
.outfit header {{ display:flex; justify-content:space-between; align-items:baseline; }}
.score {{ margin:0; font-size:1.8rem; font-weight:700; color:var(--accent); }} .score small {{ font-size:.9rem; color:var(--muted); }}
.row {{ display:flex; flex-wrap:wrap; gap:12px; }} .small {{ width:160px; }}
.scores {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; }}
.scores div {{ background:var(--bg); border-radius:8px; padding:8px; display:grid; }} .scores span {{ color:var(--muted); font-size:.8rem; }}
@media (max-width:600px) {{ .scores {{ grid-template-columns:repeat(2, minmax(0,1fr)); }} .small {{ width:46%; }} }}
ul {{ margin:0; padding-left:18px; }}
.note {{ margin:0; font-size:.85rem; color:var(--muted); border-left:3px solid var(--line); padding-left:10px; }}
</style></head><body><main>
<header><h1>DressMe · BO4 · Recommandation de tenues</h1>
<p class="muted">Moteur réel <code>recommend_outfits</code> · score heuristique sur 100 (pas une probabilité) =
0,30 couleur + 0,20 style + 0,30 occasion + 0,20 saison.</p></header>
<form method="get"><label>Saison<select name="season" onchange="this.form.submit()">{options(SEASONS, SEASON_FR, season)}</select></label>
<label>Occasion<select name="occasion" onchange="this.form.submit()">{options(OCCASION_STYLES, OCCASION_FR, occasion)}</select></label>
<button type="submit">Recommander</button></form>
{note}
<section><h2>Garde-robe ({len(WARDROBE)} vêtements)</h2><div class="wardrobe">{"".join(card(i) for i in WARDROBE)}</div></section>
<section><h2>Top 3 · {escape(SEASON_FR[season])} · {escape(OCCASION_FR[occasion])}</h2>
<p class="muted">{len(ranked)} combinaisons évaluées par le moteur ; top 3 diversifié.</p>
<div class="outfits">{"".join(outfits)}</div></section>
</main></body></html>"""
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})
