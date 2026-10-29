"""Formulaire HTML autonome d'annotation humaine des attributs (E1).

Les évaluateurs voient UNIQUEMENT l'image de chaque vêtement (pas de nom, pas
de type, pas de description, comme FashionCLIP) et répondent aux 4 questions,
avec « Incertain » et « Non visible » toujours proposés. Aucune prédiction,
similarité ni marge n'est incluse dans le fichier.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m experiments.fashionclip_e1.annotation_form
"""

import argparse
import base64
import json
from pathlib import Path

from experiments.fashionclip_e1.attributes import ATTRIBUTES, HUMAN_EXTRA_OPTIONS, schema_fingerprint
from experiments.fashionclip_e1.run_e1 import OUTPUT_DIR, load_items

QUESTION_KEYS = {"id", "label", "question", "options"}
ITEM_KEYS = {"id", "image"}


def form_payload(items):
    """Liste blanche : questions + identifiants + images. Rien d'autre."""
    questions = []
    for attribute, spec in ATTRIBUTES.items():
        options = [{"value": cls, "label": info["label_fr"]} for cls, info in spec["classes"].items()]
        options += [{"value": value, "label": label} for value, label in HUMAN_EXTRA_OPTIONS.items()]
        questions.append({"id": attribute, "label": spec["label_fr"], "question": spec["question_fr"],
                          "options": options})
    entries = []
    for item in sorted(items, key=lambda i: i["article_id"]):
        data = Path(item["image_file"]).read_bytes()
        entries.append({"id": item["article_id"],
                        "image": "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")})
    return {"version": schema_fingerprint()[:12], "questions": questions, "items": entries}


def render(payload):
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "annotation_attributs.html")
    args = parser.parse_args()
    items, rejected = load_items()
    if rejected:
        print(f"{len(rejected)} vêtement(s) exclus pour image invalide")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(form_payload(items)), encoding="utf-8")
    print(f"Formulaire : {args.output} ({len(items)} vêtements, {args.output.stat().st_size / 1e6:.1f} Mo)")


TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Attributs vestimentaires</title>
<style>
:root { --bg:#f7f6f3; --card:#fff; --text:#1d1d1f; --muted:#5f6368; --line:#d9d6cf; --accent:#2f5d50; --accent-text:#fff; --warn:#8a4b00; }
@media (prefers-color-scheme: dark) { :root { --bg:#151614; --card:#1f201d; --text:#ecebe6; --muted:#a8a69f; --line:#3a3a35; --accent:#7fb8a4; --accent-text:#10201b; --warn:#f0b26b; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width:900px; margin:0 auto; padding:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
.muted { color:var(--muted); }
.layout { display:grid; grid-template-columns: minmax(220px, 340px) 1fr; gap:16px; align-items:start; }
@media (max-width: 680px) { .layout { grid-template-columns: 1fr; } }
img { width:100%; max-height:480px; object-fit:contain; background:#fff; border:1px solid var(--line); border-radius:8px; }
fieldset { border:1px solid var(--line); border-radius:8px; margin:0 0 12px; padding:8px 12px; }
legend { font-weight:600; padding:0 4px; }
fieldset label { display:block; margin:2px 0; cursor:pointer; }
fieldset label.extra { color:var(--muted); }
textarea, input[type=text] { font:inherit; background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:8px; }
textarea { width:100%; min-height:50px; }
button { font:inherit; padding:10px 16px; border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:var(--accent-text); cursor:pointer; }
button.secondary { background:transparent; color:var(--text); border-color:var(--line); }
button:disabled { opacity:.45; cursor:not-allowed; }
.nav { display:flex; gap:8px; flex-wrap:wrap; justify-content:space-between; align-items:center; }
.warn { color:var(--warn); }
.hidden { display:none; }
</style>
</head>
<body>
<main>
  <h1>Attributs vestimentaires</h1>
  <section id="start" class="card">
    <p>Pour chacun des <strong><span id="total"></span> vêtements</strong>, répondez à 4 questions en vous fiant
       uniquement à la photo : <strong>motif</strong>, <strong>formalité</strong>, <strong>registre de style</strong>
       et <strong>épaisseur apparente</strong>.</p>
    <p class="muted">Il n'y a pas de bonne réponse. Si vous hésitez, choisissez « Incertain » ; si la photo ne permet
       pas de juger, choisissez « Non visible ». Travaillez seul·e, sans chercher d'informations sur les articles.</p>
    <p><label for="annotator">Votre pseudonyme (pas votre nom) :</label><br>
       <input type="text" id="annotator" maxlength="32" placeholder="par ex. A1" autocomplete="off">
       <button id="begin">Commencer</button></p>
    <p id="start-error" class="warn hidden">Pseudonyme : 1 à 32 caractères parmi lettres, chiffres, - et _.</p>
  </section>

  <section id="annotate" class="hidden">
    <div class="card">
      <div class="nav"><strong id="progress"></strong><span class="muted">Pseudonyme : <span id="who"></span></span></div>
    </div>
    <div class="card layout">
      <img id="photo" alt="Vêtement à annoter">
      <div>
        <div id="questions"></div>
        <label for="comment" class="muted">Commentaire (facultatif)</label>
        <textarea id="comment"></textarea>
      </div>
    </div>
    <div class="nav">
      <button class="secondary" id="prev">← Précédent</button>
      <span id="missing" class="warn"></span>
      <button id="next">Suivant →</button>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="nav"><span class="muted" id="done-count"></span>
        <button class="secondary" id="export">Exporter mes réponses (CSV)</button></div>
    </div>
  </section>
</main>

<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("data").textContent);
const byId = Object.fromEntries(DATA.items.map(i => [i.id, i]));
let annotator = "", order = [], position = 0, answers = {};

function hash32(text) { let h = 0x811c9dc5; for (const ch of text) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; } return h >>> 0; }
function mulberry32(seed) { return function () { seed = (seed + 0x6D2B79F5) >>> 0; let t = seed;
  t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function shuffledIds(name) {
  const ids = DATA.items.map(i => i.id).sort();
  const rand = mulberry32(hash32("dressme-e1|" + name));
  for (let i = ids.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [ids[i], ids[j]] = [ids[j], ids[i]]; }
  return ids;
}
function storageKey() { return "dressme-e1-" + DATA.version + "-" + annotator; }
function save() { try { localStorage.setItem(storageKey(), JSON.stringify(answers)); } catch (e) {} }
function load() { try { return JSON.parse(localStorage.getItem(storageKey()) || "{}") || {}; } catch (e) { return {}; } }
function current() { return answers[order[position]] || (answers[order[position]] = {}); }
function complete(a) { return a && DATA.questions.every(q => a[q.id]); }

function render() {
  const item = byId[order[position]], answer = current();
  document.getElementById("progress").textContent = `Vêtement ${position + 1} / ${order.length}`;
  document.getElementById("photo").src = item.image;
  const box = document.getElementById("questions");
  box.replaceChildren(...DATA.questions.map(q => {
    const fs = document.createElement("fieldset");
    const legend = document.createElement("legend"); legend.textContent = q.question; fs.append(legend);
    q.options.forEach(opt => {
      const lab = document.createElement("label");
      if (opt.value === "incertain" || opt.value === "non_visible") lab.className = "extra";
      const input = document.createElement("input");
      input.type = "radio"; input.name = q.id; input.value = opt.value; input.checked = answer[q.id] === opt.value;
      input.addEventListener("change", () => { current()[q.id] = opt.value; stamp(); });
      lab.append(input, " " + opt.label); fs.append(lab);
    });
    return fs;
  }));
  document.getElementById("comment").value = answer.commentaire || "";
  document.getElementById("prev").disabled = position === 0;
  document.getElementById("next").textContent = position === order.length - 1 ? "Terminer" : "Suivant →";
  status(); window.scrollTo(0, 0);
}
function stamp() { current().horodatage = new Date().toISOString(); save(); status(); }
function status() {
  document.getElementById("done-count").textContent = `${order.filter(id => complete(answers[id])).length} / ${order.length} vêtements complets`;
  document.getElementById("missing").textContent = "";
}
function cell(v) { const t = v === undefined || v === null ? "" : String(v); return /[",\n\r;]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; }
function exportCsv() {
  const header = ["annotateur", "article_id", "ordre_presentation", ...DATA.questions.map(q => q.id), "commentaire", "horodatage", "version_formulaire"];
  const lines = [header.join(",")];
  order.forEach((id, i) => { const a = answers[id] || {};
    lines.push([annotator, id, i + 1, ...DATA.questions.map(q => a[q.id]), a.commentaire, a.horodatage, DATA.version].map(cell).join(",")); });
  const done = order.filter(id => complete(answers[id])).length;
  if (done < order.length && !confirm(`${order.length - done} vêtement(s) incomplet(s). Exporter quand même ?`)) return;
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
  link.download = `annotations_attributs_${annotator}.csv`; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

document.getElementById("total").textContent = DATA.items.length;
document.getElementById("begin").addEventListener("click", () => {
  const name = document.getElementById("annotator").value.trim();
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(name)) { document.getElementById("start-error").classList.remove("hidden"); return; }
  annotator = name; order = shuffledIds(name); answers = load(); position = 0;
  document.getElementById("who").textContent = name;
  document.getElementById("start").classList.add("hidden");
  document.getElementById("annotate").classList.remove("hidden");
  render();
});
document.getElementById("comment").addEventListener("input", e => { current().commentaire = e.target.value; stamp(); });
document.getElementById("prev").addEventListener("click", () => { if (position > 0) { position--; render(); } });
document.getElementById("next").addEventListener("click", () => {
  if (!complete(current())) { document.getElementById("missing").textContent = "Répondez aux 4 questions (« Incertain » ou « Non visible » sont possibles)."; return; }
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
