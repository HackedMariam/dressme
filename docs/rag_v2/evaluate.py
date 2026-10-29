"""RAG v2, phase 1 : évaluation de BO5 sur le gold set (gold_set.jsonl), en lecture seule.

Deux modes :
- retrieve : appelle rag.retriever.retrieve() de BO5 (code de la branche rag/try1, utilisé tel quel, lecture
             seule) : la recherche seule, sans réécriture de requête ni génération. À lancer avec le venv de BO5,
             depuis son dossier rag_backend (pour qu'il lise sa propre configuration).
- ask      : POST {BO5}/ask : le chemin réel (réécriture, recherche, génération, citations). BO5 doit tourner.

Pertinence : un passage est pertinent si son titre ou son nom de fichier contient une des sous-chaînes
`expected` de la question (annotations PROVISOIRES : statut draft). Le contenu des passages n'est jamais écrit.

Mesures par question : hit@5, rr@5 (rang réciproque du premier passage pertinent), precision@5, titre signalé
(« z-library », « .indb », « Slide 1 ») parmi les sources ; en mode ask : grounded (au moins une citation),
citation pertinente, titre signalé cité, requête réécrite, latence.

Lancement :
  cd C:\\Users\\Win11\\DressMe-rag-test\\rag_backend
  $env:HF_HUB_OFFLINE = "1"
  .\\.venv-rag\\Scripts\\python.exe C:\\Users\\Win11\\DressMe\\docs\\rag_v2\\evaluate.py --mode retrieve
  .\\.venv-rag\\Scripts\\python.exe C:\\Users\\Win11\\DressMe\\docs\\rag_v2\\evaluate.py --mode ask --bo5 http://127.0.0.1:8010
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD = HERE / "gold_set.jsonl"
RUNS = HERE / "runs"
DONT_KNOW = re.compile(r"\bI don'?t know\b|\bje ne sais pas\b", re.IGNORECASE)
TOP_K = 5
FLAGGED = re.compile(r"z-library|\.indb|slide 1", re.IGNORECASE)


def load_gold(path: Path = GOLD) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def label(row: dict) -> str:
    return f"{row.get('title') or ''} {row.get('source') or ''}".lower()


def is_relevant(row: dict, expected: list[str]) -> bool:
    text = label(row)
    return any(e.lower() in text for e in expected)


def score(rows: list[dict], expected: list[str]) -> dict:
    """Mesures de recherche sur les TOP_K premières lignes (ordre de BO5)."""
    rows = rows[:TOP_K]
    flags = [is_relevant(r, expected) for r in rows]
    first = next((i for i, ok in enumerate(flags, 1) if ok), None)
    return {"hit": first is not None, "rr": round(1 / first, 4) if first else 0.0,
            "precision": round(sum(flags) / len(rows), 4) if rows else 0.0,
            "flagged_title": any(FLAGGED.search(str(r.get("title") or "")) for r in rows),
            "retrieved": [{"title": r.get("title"), "page": r.get("page"), "relevant": ok,
                           "similarity": r.get("similarity")} for r, ok in zip(rows, flags)]}


# ------------------------------------------------------------------ modes
def query_step(kind: str):
    """raw : la question telle quelle ; service : l'étape de requête du code mesuré (rewrite_query sur
    rag/try1, translate_query sur nourhene/rag-v2), comme dans answer_question()."""
    if kind == "raw":
        return lambda question: question
    from rag import rag_service                  # noqa: E402
    if hasattr(rag_service, "translate_query"):
        return rag_service.translate_query
    return lambda question: rag_service.rewrite_query(question, None)


def run_retrieve(gold: list[dict], query: str = "raw", plan: Path | None = None) -> list[dict]:
    """`plan` (corpus_v2_plan.json) : SIMULATION du corpus v2 sans créer la table : 30 meilleurs passages de la
    v1, passages des documents retirés écartés, titres renommés, puis les TOP_K premiers (approximation)."""
    sys.path.insert(0, str(Path.cwd()))          # dossier rag_backend de BO5 (code utilisé tel quel)
    from rag.retriever import retrieve           # noqa: E402
    make_query = query_step(query)
    removed, renamed = set(), {}
    if plan:
        data = json.loads(plan.read_text(encoding="utf-8"))
        removed = {r["document_id"] for r in data["removed"]}
        renamed = {r["document_id"]: r["new_title"] for r in data["renamed"]}
    out = []
    for item in gold:
        start = time.perf_counter()
        text = make_query(item["question"])
        if plan:
            rows = [{**r, "title": renamed.get(r.get("document_id"), r.get("title"))}
                    for r in retrieve(text, top_k=30) if r.get("document_id") not in removed]
        else:
            rows = retrieve(text, top_k=TOP_K)
        out.append({**item, **score(rows, item["expected"]), "query_sent": text,
                    "latency_s": round(time.perf_counter() - start, 2)})
        print(f"{item['id']:24} hit={int(out[-1]['hit'])} rr={out[-1]['rr']:.2f}", flush=True)
    return out


def run_ask(gold: list[dict], bo5: str) -> list[dict]:
    out = []
    for item in gold:
        body = json.dumps({"question": item["question"], "top_k": TOP_K}).encode("utf-8")
        request = urllib.request.Request(f"{bo5.rstrip('/')}/ask", data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data, status = json.loads(response.read().decode("utf-8")), response.status
        except urllib.error.HTTPError as exc:
            data, status = {}, exc.code
        latency = round(time.perf_counter() - start, 2)
        citations = data.get("citations") or []
        result = {**item, **score(data.get("sources") or [], item["expected"]), "status": status,
                  "latency_s": latency, "grounded": bool(data.get("grounded")),
                  "cited_relevant": any(is_relevant(c, item["expected"]) for c in citations),
                  "cited_flagged": any(FLAGGED.search(str(c.get("title") or "")) for c in citations),
                  "n_citations": len(citations), "rewritten_query": data.get("rewritten_query"),
                  "dont_know": bool(DONT_KNOW.search(str(data.get("answer") or "")))}
        out.append(result)
        print(f"{item['id']:24} HTTP {status} hit={int(result['hit'])} cit={result['n_citations']} {latency}s",
              flush=True)
    return out


# ------------------------------------------------------------------ synthèse
def mean(values) -> float:
    values = list(values)
    return round(100 * statistics.mean(values), 1) if values else 0.0


def summarize(results: list[dict], mode: str) -> dict:
    groups = {"tout": results, "fr": [r for r in results if r["lang"] == "fr"],
              "en": [r for r in results if r["lang"] == "en"]}
    summary = {}
    for name, rows in groups.items():
        s = {"n": len(rows), "hit@5": mean(r["hit"] for r in rows), "mrr@5": mean(r["rr"] for r in rows),
             "precision@5": mean(r["precision"] for r in rows),
             "titre_signale_dans_sources": mean(r["flagged_title"] for r in rows),
             "latence_mediane_s": round(statistics.median(r["latency_s"] for r in rows), 2) if rows else None}
        if mode == "ask":
            s.update({"grounded": mean(r["grounded"] for r in rows),
                      "citation_pertinente": mean(r["cited_relevant"] for r in rows),
                      "titre_signale_cite": mean(r["cited_flagged"] for r in rows),
                      "je_ne_sais_pas": mean(r["dont_know"] for r in rows),
                      "http_ok": mean(r["status"] == 200 for r in rows)})
        summary[name] = s
    pairs = {}
    for r in results:
        pairs.setdefault(r["pair"], {})[r["lang"]] = r["hit"]
    summary["paires"] = {"les_deux": sum(p.get("fr") and p.get("en") for p in pairs.values()),
                         "anglais_seulement": sum((not p.get("fr")) and p.get("en") for p in pairs.values()),
                         "francais_seulement": sum(p.get("fr") and (not p.get("en")) for p in pairs.values()),
                         "aucune": sum((not p.get("fr")) and (not p.get("en")) for p in pairs.values())}
    by_theme = {}
    for r in results:
        by_theme.setdefault(r["theme"], []).append(r["hit"])
    summary["hit@5_par_theme"] = {t: mean(v) for t, v in sorted(by_theme.items())}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation RAG v2 (phase 1) sur le gold set")
    parser.add_argument("--mode", choices=["retrieve", "ask"], required=True)
    parser.add_argument("--bo5", default="http://127.0.0.1:8010")
    parser.add_argument("--query", choices=["raw", "service"], default="service",
                        help="mode retrieve : question brute, ou étape de requête du code mesuré")
    parser.add_argument("--name", default=None, help="nom du fichier de résultats (dans runs/)")
    parser.add_argument("--simulate-corpus", type=Path, default=None,
                        help="mode retrieve : simuler le corpus v2 décrit par corpus_v2_plan.json")
    args = parser.parse_args()
    gold = load_gold()
    results = (run_retrieve(gold, args.query, args.simulate_corpus) if args.mode == "retrieve"
               else run_ask(gold, args.bo5))
    summary = summarize(results, args.mode)
    payload = {"mode": args.mode, "query": args.query if args.mode == "retrieve" else "service", "top_k": TOP_K,
               "simulated_corpus": str(args.simulate_corpus) if args.simulate_corpus else None, "gold_status": sorted({g["status"] for g in gold}),
               "summary": summary, "results": results}
    RUNS.mkdir(exist_ok=True)
    out = RUNS / f"{args.name or args.mode}.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
