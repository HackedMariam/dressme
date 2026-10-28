"""Évaluation humaine (E2-h) des 4 images déjà analysées par Qwen3-VL 2B.

Deux étapes :
- `build` : formulaire HTML autonome, EN AVEUGLE (images + taxonomie E2
  uniquement ; aucune prédiction, aucune métadonnée H&M) et manifeste.
- `compare` : après l'annotation, compare le CSV exporté aux prédictions
  enregistrées (lues seulement à ce moment-là).

Aucune inférence ; prompt, modèle et taxonomie inchangés ; les dossiers de
résultats précédents sont lus, jamais modifiés. Tout est écrit dans
output_human_eval/, sans écraser de fichier existant.

`certainty` n'est jamais une vérité terrain : l'humain y donne SA certitude sur
ses propres réponses ; elle est rapportée à part, hors des scores.

Usage (depuis backend/) :
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.human_eval build
    .\\.venv\\Scripts\\python.exe -m experiments.qwen3vl_e2.human_eval compare --annotations <fichier.csv>
"""

import argparse
import base64
import collections
import csv
import hashlib
import json
import sys
from pathlib import Path

from evaluation.common import DATA_HM_DIR, sha256_file
from experiments.qwen3vl_e2.run_microbench import load_selection
from experiments.qwen3vl_e2.taxonomy import (DIMENSIONS, EXPLORATORY, ORDINAL, TAXONOMY_VERSION,
                                             taxonomy_fingerprint)

E2_DIR = Path(__file__).resolve().parent
HUMAN_DIR = E2_DIR / "output_human_eval"
FORM_FILE = "annotation_e2_humaine.html"
MANIFEST_FILE = "manifest.json"
# Prédictions retenues (seuls appels réussis avec num_predict=2048, num_ctx=6144).
PREDICTION_SOURCES = {
    "0840606004": ("output_single_check", "single_check.json"),
    "0781758009": ("output_mini3_v4", "results.jsonl"),
    "0783144006": ("output_mini3_v4", "results.jsonl"),
    "0801843006": ("output_mini3_v4", "results.jsonl"),
}
ARTICLES = tuple(sorted(PREDICTION_SOURCES))
SCORED = tuple(d for d in DIMENSIONS if d != "certainty")
WITH_ALTERNATIVE = SCORED
YES_NO = {"oui": True, "non": False}

# Questions en français pour l'humain : mêmes définitions que celles du modèle.
HELP_FR = {
    "category": "Quel type de vêtement est montré ?",
    "primary_color": "Quelle couleur couvre la plus grande surface du vêtement ?",
    "pattern": "Quel dessin de couleurs est imprimé ou tissé ? Une texture seule n'est pas un motif : "
               "une surface d'une seule couleur est « Uni », quelle que soit sa texture.",
    "material_appearance": "À quoi ressemble le tissu ? Jugez l'apparence, pas la composition.",
    "fit": "Quelle est la silhouette par rapport au corps ? Ce n'est pas un style.",
    "style": "Quel registre de style domine ? (dimension exploratoire)",
    "formality": "Quel est le contexte le plus habillé dans lequel on peut raisonnablement le porter ? "
                 "Ne la déduisez pas de la seule catégorie.",
    "thickness": "Quelle épaisseur paraît-il avoir (transparence, volume, rembourrage, grosse maille) ?",
    "certainty": "VOTRE certitude globale sur VOS réponses pour ce vêtement. Elle n'est pas comparée comme "
                 "une vérité : elle sert seulement à repérer les cas difficiles.",
}
RULES_FR = [
    "Les dimensions sont indépendantes : une dentelle fleurie = motif « Fleuri » ET matière « Dentelle ».",
    "Le motif décrit un dessin de couleurs ; une surface d'une seule couleur est « Uni », même texturée.",
    "La coupe décrit la silhouette, jamais un style.",
    "La formalité ne se déduit jamais de la seule catégorie (une robe n'est pas forcément habillée).",
    "Répondez uniquement d'après la photo ; « Non visible » quand elle ne permet pas de décider.",
]


class HumanEvalError(RuntimeError):
    pass


def form_version():
    payload = json.dumps({"taxonomy": taxonomy_fingerprint(), "help": HELP_FR, "rules": RULES_FR,
                          "articles": ARTICLES}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def annotation_items(selection=None, images_root=DATA_HM_DIR):
    """Les 4 images exactes, vérifiées par SHA-256 contre la sélection E2."""
    by_id = {i["article_id"]: i for i in (load_selection() if selection is None else selection)}
    items = []
    for article_id in ARTICLES:
        if article_id not in by_id:
            raise HumanEvalError(f"{article_id} absent de la sélection E2")
        entry = by_id[article_id]
        path = Path(images_root) / entry["image_path"]
        digest = sha256_file(path)
        if digest != entry["image_sha256"]:
            raise HumanEvalError(f"image modifiée : {path}")
        items.append({"article_id": article_id, "image_path": entry["image_path"], "image_sha256": digest,
                      "file": path})
    return items


def form_payload(items):
    """Liste blanche : identifiants, images, questions et valeurs de la taxonomie. Rien d'autre."""
    questions = [{"id": dim, "label": spec["label_fr"], "help": HELP_FR[dim],
                  "options": [{"value": v, "label": label} for v, label in spec["values"].items()],
                  "alternative": dim in WITH_ALTERNATIVE}
                 for dim, spec in DIMENSIONS.items()]
    entries = [{"id": i["article_id"],
                "image": "data:image/jpeg;base64," + base64.b64encode(Path(i["file"]).read_bytes()).decode("ascii")}
               for i in items]
    return {"version": form_version(), "taxonomy_version": TAXONOMY_VERSION, "rules": RULES_FR,
            "questions": questions, "items": entries}


def render(payload):
    return TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))


def prediction_files(root=E2_DIR):
    return sorted({Path(root) / folder / name for folder, name in PREDICTION_SOURCES.values()})


def write_new(path, text):
    path = Path(path)
    if path.exists():
        raise HumanEvalError(f"{path} existe déjà : rien n'est écrasé")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build(output_dir=HUMAN_DIR, items=None, root=E2_DIR):
    """Les fichiers de prédiction ne sont pas analysés : seule leur empreinte SHA-256 va au manifeste
    (pour détecter toute modification avant la comparaison)."""
    items = annotation_items() if items is None else items
    manifest = {
        "form_version": form_version(), "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_sha256": taxonomy_fingerprint(),
        "items": [{k: i[k] for k in ("article_id", "image_path", "image_sha256")} for i in items],
        "prediction_files_sha256": {str(p.relative_to(root)).replace("\\", "/"): sha256_file(p)
                                    for p in prediction_files(root)},
        "note": "Formulaire en aveugle : aucune prédiction ni métadonnée H&M dans le HTML.",
    }
    write_new(Path(output_dir) / FORM_FILE, render(form_payload(items)))
    write_new(Path(output_dir) / MANIFEST_FILE, json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


# ---------------------------------------------------------------------------
# Comparaison (après annotation)
# ---------------------------------------------------------------------------

def load_predictions(manifest, root=E2_DIR):
    """Prédictions Qwen des 4 images ; refuse si un fichier source a changé depuis `build`."""
    for rel, digest in manifest["prediction_files_sha256"].items():
        if sha256_file(Path(root) / rel) != digest:
            raise HumanEvalError(f"fichier de prédictions modifié depuis la préparation : {rel}")
    found = {}
    for article_id, (folder, name) in PREDICTION_SOURCES.items():
        path = Path(root) / folder / name
        if name.endswith(".jsonl"):
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            images = json.loads((path.parent / "metadata.json").read_text(encoding="utf-8"))["images"]
        else:
            report = json.loads(path.read_text(encoding="utf-8"))
            records, images = [report["result"]], {report["article_id"]: report["metadata"]["image_sha256"]}
        record = next((r for r in records if r["article_id"] == article_id), None)
        if record is None or not record.get("schema_valid"):
            raise HumanEvalError(f"pas de prédiction valide pour {article_id} dans {folder}/{name}")
        expected = next(i["image_sha256"] for i in manifest["items"] if i["article_id"] == article_id)
        if images.get(article_id) != expected:
            raise HumanEvalError(f"{article_id} : l'image prédite n'est pas celle annotée")
        found[article_id] = {"attributes": record["attributes"], "source": f"{folder}/{name}"}
    return found


def load_annotations(path, manifest):
    """Valide le CSV exporté ; aucune valeur n'est complétée ou corrigée."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    problems, annotations = [], {}
    annotators = {r.get("annotateur", "") for r in rows}
    if len(annotators) != 1:
        problems.append(f"un seul annotateur attendu par fichier : {sorted(annotators)}")
    if {r.get("version_formulaire") for r in rows} != {manifest["form_version"]}:
        problems.append("version du formulaire différente de celle du manifeste")
    for row in rows:
        article_id = row.get("article_id", "")
        if article_id not in ARTICLES or article_id in annotations:
            problems.append(f"article inattendu ou en double : {article_id!r}")
            continue
        entry = {"primary": {}, "alternative": {}, "exposed": None, "comment": row.get("commentaire", "")}
        for dim in DIMENSIONS:
            value = row.get(dim, "")
            if value not in DIMENSIONS[dim]["values"]:
                problems.append(f"{article_id} {dim} : valeur absente ou hors taxonomie ({value!r})")
            entry["primary"][dim] = value
        for dim in WITH_ALTERNATIVE:
            alt = row.get(f"alt_{dim}", "")
            if alt and (alt not in DIMENSIONS[dim]["values"] or alt == entry["primary"][dim]):
                problems.append(f"{article_id} alt_{dim} : valeur invalide ({alt!r})")
            entry["alternative"][dim] = alt or None
        exposed = row.get("deja_vu_predictions", "")
        if exposed not in YES_NO:
            problems.append(f"{article_id} deja_vu_predictions : « oui » ou « non » attendu ({exposed!r})")
        entry["exposed"] = YES_NO.get(exposed)
        annotations[article_id] = entry
    missing = sorted(set(ARTICLES) - set(annotations))
    if missing:
        problems.append(f"images non annotées : {missing}")
    if problems:
        raise HumanEvalError("annotations invalides :\n  " + "\n  ".join(problems))
    return annotators.pop(), annotations


def ordinal_distance(dim, human, model):
    scale = ORDINAL.get(dim)
    if not scale or human not in scale or model not in scale:
        return None
    return abs(scale.index(human) - scale.index(model))


def compare(annotations, predictions):
    rows = []
    for article_id in ARTICLES:
        human, model = annotations[article_id], predictions[article_id]["attributes"]
        for dim in SCORED:
            h, alt, m = human["primary"][dim], human["alternative"][dim], model[dim]
            rows.append({"article_id": article_id, "attribute": dim, "human": h, "human_alternative": alt,
                         "qwen": m, "strict_match": h == m, "lenient_match": m in {h, alt},
                         "ordinal_distance": ordinal_distance(dim, h, m), "exploratory": dim in EXPLORATORY,
                         "human_saw_predictions": human["exposed"]})
    return rows


def score(rows):
    def block(subset):
        n = len(subset)
        return {"n": n, "strict": sum(r["strict_match"] for r in subset),
                "lenient": sum(r["lenient_match"] for r in subset)}

    by_attribute = {}
    for dim in SCORED:
        subset = [r for r in rows if r["attribute"] == dim]
        distances = [r["ordinal_distance"] for r in subset if r["ordinal_distance"] is not None]
        by_attribute[dim] = {**block(subset), "exploratory": dim in EXPLORATORY,
                             "differences": [{k: r[k] for k in ("article_id", "human", "human_alternative", "qwen")}
                                             for r in subset if not r["strict_match"]]}
        if dim in ORDINAL:
            by_attribute[dim]["ordinal_distances"] = distances
    blind = [r for r in rows if r["human_saw_predictions"] is False]
    return {
        "by_attribute": by_attribute,
        "overall": block(rows),
        "overall_without_style": block([r for r in rows if not r["exploratory"]]),
        "overall_blind_items_only": block(blind),
        "by_item": {a: block([r for r in rows if r["article_id"] == a]) for a in ARTICLES},
    }


def certainty_report(annotations, predictions, rows):
    """Descriptif uniquement : la certitude n'est la vérité de personne."""
    return [{"article_id": a, "human_certainty": annotations[a]["primary"]["certainty"],
             "qwen_certainty": predictions[a]["attributes"]["certainty"],
             "qwen_strict_matches": sum(r["strict_match"] for r in rows if r["article_id"] == a),
             "n_attributes": len(SCORED)} for a in ARTICLES]


def run_compare(annotations_csv, output_dir=HUMAN_DIR, root=E2_DIR):
    output_dir = Path(output_dir)
    manifest = json.loads((output_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    annotator, annotations = load_annotations(annotations_csv, manifest)
    predictions = load_predictions(manifest, root)
    rows = compare(annotations, predictions)
    result = {
        "annotator": annotator, "annotations_sha256": sha256_file(annotations_csv),
        "form_version": manifest["form_version"],
        "prediction_sources": {a: p["source"] for a, p in predictions.items()},
        "scores": score(rows), "certainty": certainty_report(annotations, predictions, rows),
        "exposed_items": sorted(a for a, e in annotations.items() if e["exposed"]),
        "comments": {a: e["comment"] for a, e in annotations.items() if e["comment"]},
        "limits": [
            "1 annotateur et 4 images : comptages indicatifs, aucune exactitude généralisable.",
            "L'annotation humaine est une référence, pas une vérité absolue (un 2e annotateur permettrait un accord).",
            "`style` est exploratoire ; `certainty` est exclue des scores.",
            "Les images marquées déjà vues ne sont pas en aveugle.",
        ],
    }
    write_new(output_dir / f"comparaison_{annotator}.json", json.dumps(result, indent=2, ensure_ascii=False))
    fields = list(rows[0])
    lines = [",".join(fields)] + [",".join(_cell(r[f]) for f in fields) for r in rows]
    write_new(output_dir / f"comparaison_{annotator}.csv", "\n".join(lines) + "\n")
    return result


def _cell(value):
    text = "" if value is None else str(value)
    return '"' + text.replace('"', '""') + '"' if any(c in text for c in ',"\n') else text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    cmp_parser = sub.add_parser("compare")
    cmp_parser.add_argument("--annotations", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            build()
            print(f"Formulaire : {HUMAN_DIR / FORM_FILE}\nManifeste : {HUMAN_DIR / MANIFEST_FILE}")
        else:
            result = run_compare(args.annotations)
            print(json.dumps(result["scores"], indent=2, ensure_ascii=False))
    except HumanEvalError as error:
        sys.exit(str(error))


TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Annotation E2</title>
<style>
:root { --bg:#f7f6f3; --card:#fff; --text:#1d1d1f; --muted:#5f6368; --line:#d9d6cf; --accent:#2f5d50; --accent-text:#fff; --warn:#8a4b00; }
@media (prefers-color-scheme: dark) { :root { --bg:#151614; --card:#1f201d; --text:#ecebe6; --muted:#a8a69f; --line:#3a3a35; --accent:#7fb8a4; --accent-text:#10201b; --warn:#f0b26b; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width:1100px; margin:0 auto; padding:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
.muted { color:var(--muted); }
.layout { display:grid; grid-template-columns: minmax(240px, 380px) 1fr; gap:16px; align-items:start; }
.sticky { position:sticky; top:12px; }
@media (max-width: 760px) { .layout { grid-template-columns: 1fr; } .sticky { position:static; } }
img { width:100%; max-height:560px; object-fit:contain; background:#fff; border:1px solid var(--line); border-radius:8px; }
fieldset { border:1px solid var(--line); border-radius:8px; margin:0 0 12px; padding:8px 12px; }
legend { font-weight:600; padding:0 4px; }
.help { color:var(--muted); font-size:14px; margin:0 0 6px; }
.options { display:grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap:0 12px; }
.options label { cursor:pointer; }
.code { color:var(--muted); font-size:12px; }
select, textarea, input[type=text] { font:inherit; background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:6px 8px; }
textarea { width:100%; min-height:50px; }
.alt { margin-top:6px; font-size:14px; }
button { font:inherit; padding:10px 16px; border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:var(--accent-text); cursor:pointer; }
button.secondary { background:transparent; color:var(--text); border-color:var(--line); }
button:disabled { opacity:.45; cursor:not-allowed; }
.nav { display:flex; gap:8px; flex-wrap:wrap; justify-content:space-between; align-items:center; }
.warn { color:var(--warn); }
.hidden { display:none; }
ul { margin:4px 0; padding-left:20px; }
</style>
</head>
<body>
<main>
  <h1>Annotation des attributs (E2)</h1>
  <section id="start" class="card">
    <p>Pour chacune des <strong><span id="total"></span> images</strong>, décrivez le vêtement selon
       <strong>9 attributs</strong>, en vous fiant uniquement à la photo. Les prédictions du modèle ne sont
       <strong>pas</strong> dans ce fichier.</p>
    <p><strong>Règles</strong></p>
    <ul id="rules"></ul>
    <p class="muted">Pour chaque attribut (sauf la certitude), vous pouvez indiquer une <em>seconde valeur
       acceptable</em> si deux réponses vous semblent également justes. Laissez « aucune » sinon.</p>
    <p class="muted">Pour chaque image, indiquez honnêtement si vous aviez déjà vu les prédictions du modèle :
       ces images seront analysées à part.</p>
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
      <div class="sticky"><img id="photo" alt="Vêtement à annoter"></div>
      <div>
        <div id="questions"></div>
        <fieldset>
          <legend>Aviez-vous déjà vu les prédictions du modèle pour cette image ?</legend>
          <div class="options">
            <label><input type="radio" name="deja_vu_predictions" value="non"> Non</label>
            <label><input type="radio" name="deja_vu_predictions" value="oui"> Oui</label>
          </div>
        </fieldset>
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
  const rand = mulberry32(hash32("dressme-e2h|" + name));
  for (let i = ids.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [ids[i], ids[j]] = [ids[j], ids[i]]; }
  return ids;
}
function storageKey() { return "dressme-e2h-" + DATA.version + "-" + annotator; }
function save() { try { localStorage.setItem(storageKey(), JSON.stringify(answers)); } catch (e) {} }
function load() { try { return JSON.parse(localStorage.getItem(storageKey()) || "{}") || {}; } catch (e) { return {}; } }
function current() { return answers[order[position]] || (answers[order[position]] = {}); }
function complete(a) { return a && DATA.questions.every(q => a[q.id]) && a.deja_vu_predictions; }

function render() {
  const item = byId[order[position]], answer = current();
  document.getElementById("progress").textContent = `Image ${position + 1} / ${order.length}`;
  document.getElementById("photo").src = item.image;
  document.getElementById("questions").replaceChildren(...DATA.questions.map(q => {
    const fs = document.createElement("fieldset");
    const legend = document.createElement("legend"); legend.textContent = q.label; fs.append(legend);
    const help = document.createElement("p"); help.className = "help"; help.textContent = q.help; fs.append(help);
    const grid = document.createElement("div"); grid.className = "options";
    q.options.forEach(opt => {
      const lab = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio"; input.name = q.id; input.value = opt.value; input.checked = answer[q.id] === opt.value;
      input.addEventListener("change", () => { current()[q.id] = opt.value;
        if (current()["alt_" + q.id] === opt.value) delete current()["alt_" + q.id]; stamp(); render(); });
      const code = document.createElement("span"); code.className = "code"; code.textContent = " (" + opt.value + ")";
      lab.append(input, " " + opt.label, code); grid.append(lab);
    });
    fs.append(grid);
    if (q.alternative) {
      const wrap = document.createElement("div"); wrap.className = "alt";
      const sel = document.createElement("select"); sel.setAttribute("aria-label", "Seconde valeur acceptable : " + q.label);
      sel.append(new Option("aucune", ""));
      q.options.filter(o => o.value !== answer[q.id]).forEach(o => sel.append(new Option(o.label, o.value)));
      sel.value = answer["alt_" + q.id] || "";
      sel.addEventListener("change", () => { if (sel.value) current()["alt_" + q.id] = sel.value; else delete current()["alt_" + q.id]; stamp(); });
      wrap.append("Seconde valeur acceptable (facultatif) : ", sel); fs.append(wrap);
    }
    return fs;
  }));
  document.querySelectorAll('input[name="deja_vu_predictions"]').forEach(r => { r.checked = answer.deja_vu_predictions === r.value; });
  document.getElementById("comment").value = answer.commentaire || "";
  document.getElementById("prev").disabled = position === 0;
  document.getElementById("next").textContent = position === order.length - 1 ? "Terminer" : "Suivant →";
  status();
}
function stamp() { current().horodatage = new Date().toISOString(); save(); status(); }
function status() {
  document.getElementById("done-count").textContent = `${order.filter(id => complete(answers[id])).length} / ${order.length} images complètes`;
  document.getElementById("missing").textContent = "";
}
function cell(v) { const t = v === undefined || v === null ? "" : String(v); return /[",\n\r;]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; }
function exportCsv() {
  const alts = DATA.questions.filter(q => q.alternative).map(q => "alt_" + q.id);
  const header = ["annotateur", "article_id", "ordre_presentation", ...DATA.questions.map(q => q.id), ...alts,
                  "deja_vu_predictions", "commentaire", "horodatage", "version_formulaire"];
  const lines = [header.join(",")];
  order.forEach((id, i) => { const a = answers[id] || {};
    lines.push([annotator, id, i + 1, ...DATA.questions.map(q => a[q.id]), ...alts.map(k => a[k]),
                a.deja_vu_predictions, a.commentaire, a.horodatage, DATA.version].map(cell).join(",")); });
  const done = order.filter(id => complete(answers[id])).length;
  if (done < order.length && !confirm(`${order.length - done} image(s) incomplète(s). Exporter quand même ?`)) return;
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
  link.download = `annotations_e2_${annotator}.csv`; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

document.getElementById("total").textContent = DATA.items.length;
document.getElementById("rules").replaceChildren(...DATA.rules.map(r => { const li = document.createElement("li"); li.textContent = r; return li; }));
document.getElementById("begin").addEventListener("click", () => {
  const name = document.getElementById("annotator").value.trim();
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(name)) { document.getElementById("start-error").classList.remove("hidden"); return; }
  annotator = name; order = shuffledIds(name); answers = load(); position = 0;
  document.getElementById("who").textContent = name;
  document.getElementById("start").classList.add("hidden");
  document.getElementById("annotate").classList.remove("hidden");
  render(); window.scrollTo(0, 0);
});
document.querySelectorAll('input[name="deja_vu_predictions"]').forEach(r => r.addEventListener("change", () => { current().deja_vu_predictions = r.value; stamp(); }));
document.getElementById("comment").addEventListener("input", e => { current().commentaire = e.target.value; stamp(); });
document.getElementById("prev").addEventListener("click", () => { if (position > 0) { position--; render(); window.scrollTo(0, 0); } });
document.getElementById("next").addEventListener("click", () => {
  if (!complete(current())) { document.getElementById("missing").textContent = "Répondez aux 9 attributs et à la question « déjà vu »."; return; }
  if (position < order.length - 1) { position++; render(); window.scrollTo(0, 0); }
  else { document.getElementById("missing").textContent = "Terminé ! Pensez à exporter vos réponses."; }
});
document.getElementById("export").addEventListener("click", exportCsv);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
