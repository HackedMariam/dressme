"""Génère l'outil d'annotation HTML autonome du pilote.

Le fichier produit (data/annotation_pilote.html) contient les images encodées
en base64 : il s'ouvre par double-clic, sans serveur, sans Internet et sans
dépendance. Seules les informations nécessaires à l'annotateur y figurent
(liste blanche) : aucun score, rang, tercile, strate ni explication du moteur.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m evaluation.annotation_pack
"""

import argparse
import base64
import io
import json
from pathlib import Path

from PIL import Image

from evaluation.common import CATALOG_CSV, DATA_HM_DIR, OUTPUT_DIR, read_csv, sha256_file

SEASON_LABELS = {"spring": "Printemps", "summer": "Été", "autumn": "Automne", "winter": "Hiver"}
OCCASION_LABELS = {"university": "Université", "work": "Travail", "evening": "Soirée", "casual": "Décontracté"}

# Seuls champs exposés à l'annotateur.
SAMPLE_KEYS = {"id", "season", "occasion", "items"}
ITEM_KEYS = {"image", "name", "type", "description"}


def annotator_payload(manifest_rows, catalog_rows):
    """Données montrées à l'annotateur : liste blanche stricte."""
    catalog = {r["article_id"]: r for r in catalog_rows}
    samples = []
    for row in sorted(manifest_rows, key=lambda r: r["sample_id"]):
        items = []
        for article_id in row["article_ids"].split("|"):
            product = catalog[article_id]
            items.append({
                "image": article_id,
                "name": product["prod_name"],
                "type": product["product_type_name"],
                "description": product["detail_desc"],
            })
        samples.append({
            "id": row["sample_id"],
            "season": SEASON_LABELS[row["season"]],
            "occasion": OCCASION_LABELS[row["occasion"]],
            "items": items,
        })
    return samples


def embed_images(manifest_rows, images_root):
    """{article_id: data URI} pour toutes les images du manifeste."""
    images = {}
    for row in manifest_rows:
        for article_id, path in zip(row["article_ids"].split("|"), row["image_paths"].split("|")):
            if article_id not in images:
                data = (Path(images_root) / path).read_bytes()
                images[article_id] = "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
    return images


def verify_embedded_images(images):
    """Décode chaque image intégrée ; renvoie {article_id: (largeur, hauteur)}."""
    sizes = {}
    for article_id, uri in images.items():
        raw = base64.b64decode(uri.split(",", 1)[1])
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            sizes[article_id] = image.size
    return sizes


def render_html(samples, images, manifest_sha256):
    data = json.dumps({"samples": samples, "images": images, "manifest": manifest_sha256},
                      ensure_ascii=False).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__DATA__", data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=OUTPUT_DIR / "manifeste_pilote.csv")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "annotation_pilote.html")
    args = parser.parse_args()

    manifest = read_csv(args.manifest)
    samples = annotator_payload(manifest, read_csv(CATALOG_CSV))
    images = embed_images(manifest, DATA_HM_DIR)
    sizes = verify_embedded_images(images)
    html = render_html(samples, images, sha256_file(args.manifest)[:12])
    args.output.write_text(html, encoding="utf-8")
    print(f"Outil d'annotation : {args.output} ({len(samples)} tenues, {len(images)} images "
          f"vérifiées, {args.output.stat().st_size / 1e6:.1f} Mo)")
    print("Tailles d'image :", sorted(set(sizes.values())))


HTML_TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Annotation DressMe</title>
<style>
:root { --bg:#f7f6f3; --card:#ffffff; --text:#1d1d1f; --muted:#5f6368; --line:#d9d6cf;
        --accent:#2f5d50; --accent-text:#ffffff; --warn:#8a4b00; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#151614; --card:#1f201d; --text:#ecebe6; --muted:#a8a69f; --line:#3a3a35;
          --accent:#7fb8a4; --accent-text:#10201b; --warn:#f0b26b; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 16px; }
h1 { font-size: 1.4rem; margin: .2rem 0 1rem; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
.muted { color:var(--muted); }
.chips { display:flex; gap:8px; flex-wrap:wrap; margin:.5rem 0 1rem; }
.chip { border:1px solid var(--line); border-radius:999px; padding:4px 12px; font-weight:600; }
.items { display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px; }
.item img { width:100%; height:300px; object-fit:contain; background:#fff; border-radius:8px; border:1px solid var(--line); }
.item h3 { font-size:1rem; margin:.4rem 0 .1rem; }
.item details { font-size:.9rem; color:var(--muted); }
table.rating { width:100%; border-collapse:collapse; }
table.rating td, table.rating th { padding:8px 4px; border-bottom:1px solid var(--line); text-align:center; }
table.rating td:first-child, table.rating th:first-child { text-align:left; }
table.rating label { display:inline-flex; flex-direction:column; align-items:center; cursor:pointer; min-width:36px; }
.scale { font-size:.8rem; color:var(--muted); }
.flags label { display:block; margin:.3rem 0; }
textarea { width:100%; min-height:60px; background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:8px; font:inherit; }
input[type=text] { font:inherit; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--text); }
button { font:inherit; padding:10px 16px; border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:var(--accent-text); cursor:pointer; }
button.secondary { background:transparent; color:var(--text); border-color:var(--line); }
button:disabled { opacity:.45; cursor:not-allowed; }
.nav { display:flex; gap:8px; flex-wrap:wrap; justify-content:space-between; align-items:center; }
.warn { color:var(--warn); }
.hidden { display:none; }
@media (max-width: 600px) { .item img { height:220px; } table.rating label { min-width:28px; } }
</style>
</head>
<body>
<main>
  <h1>Annotation de tenues — pilote DressMe</h1>

  <section id="start" class="card">
    <p>Vous allez juger <strong><span id="total"></span> tenues</strong>, chacune pour une saison et une occasion.
       Pour chaque tenue, notez cinq critères de <strong>1 (pas du tout)</strong> à <strong>5 (tout à fait)</strong> :</p>
    <ol>
      <li><strong>Harmonie visuelle</strong> — les pièces vont-elles bien ensemble à l'œil ?</li>
      <li><strong>Cohérence de style</strong> — les pièces appartiennent-elles à un même registre ?</li>
      <li><strong>Occasion</strong> — porteriez-vous cette tenue pour l'occasion indiquée ?</li>
      <li><strong>Saison</strong> — cette tenue convient-elle à la saison indiquée ?</li>
      <li><strong>Qualité globale</strong> — recommanderiez-vous cette tenue à une amie, pour ce contexte ?</li>
    </ol>
    <p class="muted">Les vêtements sont présentés séparément : imaginez-les portés ensemble. Il n'y a pas de bonne réponse.
       Si vous ne pouvez pas juger, cochez « Image illisible » ou « Tenue impossible à évaluer ».</p>
    <p><label for="annotator">Votre pseudonyme (pas votre nom) :</label><br>
       <input type="text" id="annotator" maxlength="32" placeholder="par ex. A1" autocomplete="off">
       <button id="begin">Commencer</button></p>
    <p id="start-error" class="warn hidden">Pseudonyme : 1 à 32 caractères parmi lettres, chiffres, - et _.</p>
  </section>

  <section id="annotate" class="hidden">
    <div class="card">
      <div class="nav">
        <strong id="progress"></strong>
        <span class="muted">Pseudonyme : <span id="who"></span></span>
      </div>
      <div class="chips"><span class="chip" id="season"></span><span class="chip" id="occasion"></span></div>
      <div class="items" id="items"></div>
    </div>

    <div class="card">
      <table class="rating" id="rating">
        <thead><tr><th>Critère</th><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th></tr></thead>
        <tbody></tbody>
      </table>
      <p class="scale">1 = pas du tout · 2 = plutôt non · 3 = mitigé · 4 = plutôt oui · 5 = tout à fait</p>
      <div class="flags">
        <label><input type="checkbox" id="illisible"> Image illisible</label>
        <label><input type="checkbox" id="impossible"> Tenue impossible à évaluer</label>
      </div>
      <label for="comment" class="muted">Commentaire (facultatif)</label>
      <textarea id="comment"></textarea>
    </div>

    <div class="nav">
      <button class="secondary" id="prev">← Précédente</button>
      <span id="missing" class="warn"></span>
      <button id="next">Suivante →</button>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="nav">
        <span class="muted" id="done-count"></span>
        <button class="secondary" id="export">Exporter mes réponses (CSV)</button>
      </div>
    </div>
  </section>
</main>

<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const CRITERIA = [
  ["harmonie", "Harmonie visuelle"],
  ["style", "Cohérence de style"],
  ["occasion", "Adéquation à l'occasion"],
  ["saison", "Adéquation à la saison"],
  ["globale", "Qualité globale"],
];
const byId = Object.fromEntries(DATA.samples.map(s => [s.id, s]));
let annotator = "", order = [], position = 0, answers = {};

function hash32(text) {               // FNV-1a
  let h = 0x811c9dc5;
  for (const ch of text) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
  return h >>> 0;
}
function mulberry32(seed) {
  return function () {
    seed = (seed + 0x6D2B79F5) >>> 0;
    let t = seed;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shuffledIds(name) {          // ordre propre à chaque pseudonyme, reproductible
  const ids = DATA.samples.map(s => s.id).sort();
  const rand = mulberry32(hash32("dressme-pilote|" + name));
  for (let i = ids.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [ids[i], ids[j]] = [ids[j], ids[i]];
  }
  return ids;
}
function storageKey() { return "dressme-pilote-" + DATA.manifest + "-" + annotator; }
function save() { try { localStorage.setItem(storageKey(), JSON.stringify(answers)); } catch (e) {} }
function load() {
  try { return JSON.parse(localStorage.getItem(storageKey()) || "{}") || {}; } catch (e) { return {}; }
}

function current() { return answers[order[position]] || (answers[order[position]] = {}); }
function complete(a) { return a && (a.illisible || a.impossible || CRITERIA.every(([k]) => a[k])); }

function render() {
  const sample = byId[order[position]];
  const answer = current();
  document.getElementById("progress").textContent = `Tenue ${position + 1} / ${order.length}`;
  document.getElementById("season").textContent = "Saison : " + sample.season;
  document.getElementById("occasion").textContent = "Occasion : " + sample.occasion;
  const items = document.getElementById("items");
  items.replaceChildren(...sample.items.map(item => {
    const box = document.createElement("div"); box.className = "item";
    const img = document.createElement("img");
    img.src = DATA.images[item.image]; img.alt = item.type + " — " + item.name; img.loading = "eager";
    const title = document.createElement("h3"); title.textContent = item.type + " · " + item.name;
    const details = document.createElement("details");
    const summary = document.createElement("summary"); summary.textContent = "Description";
    const text = document.createElement("p"); text.textContent = item.description;
    details.append(summary, text);
    box.append(img, title, details);
    return box;
  }));
  const body = document.querySelector("#rating tbody");
  body.replaceChildren(...CRITERIA.map(([key, label]) => {
    const row = document.createElement("tr");
    const name = document.createElement("td"); name.textContent = label; row.append(name);
    for (let v = 1; v <= 5; v++) {
      const cell = document.createElement("td");
      const lab = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio"; input.name = key; input.value = v; input.checked = answer[key] === v;
      input.setAttribute("aria-label", `${label} : ${v}`);
      input.addEventListener("change", () => { current()[key] = v; stamp(); });
      lab.append(input); cell.append(lab); row.append(cell);
    }
    return row;
  }));
  document.getElementById("illisible").checked = !!answer.illisible;
  document.getElementById("impossible").checked = !!answer.impossible;
  document.getElementById("comment").value = answer.commentaire || "";
  document.getElementById("prev").disabled = position === 0;
  document.getElementById("next").textContent = position === order.length - 1 ? "Terminer" : "Suivante →";
  updateStatus();
  window.scrollTo(0, 0);
}
function stamp() { current().horodatage = new Date().toISOString(); save(); updateStatus(); }
function updateStatus() {
  const done = order.filter(id => complete(answers[id])).length;
  document.getElementById("done-count").textContent = `${done} / ${order.length} tenues complètes`;
  document.getElementById("missing").textContent = "";
}

function csvCell(value) {
  const text = value === undefined || value === null ? "" : String(value);
  return /[",\n\r;]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}
function exportCsv() {
  const header = ["annotateur", "sample_id", "ordre_presentation", "harmonie", "style", "occasion",
                  "saison", "globale", "image_illisible", "impossible_a_evaluer", "commentaire",
                  "horodatage", "version_manifeste"];
  const lines = [header.join(",")];
  order.forEach((id, index) => {
    const a = answers[id] || {};
    lines.push([annotator, id, index + 1, a.harmonie, a.style, a.occasion, a.saison, a.globale,
                a.illisible ? 1 : 0, a.impossible ? 1 : 0, a.commentaire, a.horodatage, DATA.manifest]
               .map(csvCell).join(","));
  });
  const done = order.filter(id => complete(answers[id])).length;
  if (done < order.length && !confirm(`${order.length - done} tenue(s) incomplète(s). Exporter quand même ?`)) return;
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `annotations_pilote_${annotator}.csv`;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

document.getElementById("total").textContent = DATA.samples.length;
document.getElementById("begin").addEventListener("click", () => {
  const name = document.getElementById("annotator").value.trim();
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(name)) { document.getElementById("start-error").classList.remove("hidden"); return; }
  annotator = name; order = shuffledIds(name); answers = load(); position = 0;
  document.getElementById("who").textContent = name;
  document.getElementById("start").classList.add("hidden");
  document.getElementById("annotate").classList.remove("hidden");
  render();
});
document.getElementById("illisible").addEventListener("change", e => { current().illisible = e.target.checked; stamp(); });
document.getElementById("impossible").addEventListener("change", e => { current().impossible = e.target.checked; stamp(); });
document.getElementById("comment").addEventListener("input", e => { current().commentaire = e.target.value; stamp(); });
document.getElementById("prev").addEventListener("click", () => { if (position > 0) { position--; render(); } });
document.getElementById("next").addEventListener("click", () => {
  if (!complete(current())) {
    document.getElementById("missing").textContent = "Notez les 5 critères, ou cochez une case « impossible ».";
    return;
  }
  if (position < order.length - 1) { position++; render(); }
  else { document.getElementById("missing").textContent = "Terminé ! Pensez à exporter vos réponses."; }
});
document.getElementById("export").addEventListener("click", exportCsv);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
