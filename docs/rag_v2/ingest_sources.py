"""RAG v2 étape C : nouvelles sources libres (Wikipedia, Wikivoyage, FTC) pour knowledge_chunks_v2 UNIQUEMENT.

Deux commandes, à lancer depuis rag_backend avec le venv de BO5 (HF_HUB_OFFLINE=1) :
  prepare : vérifie la licence affichée sur chaque page, récupère le texte propre par l'API officielle,
            découpe (section d'abord, 256 tokens au plus préfixe « Document: … / Section: … » compris,
            donc rien n'est tronqué par MiniLM), calcule les
            embeddings (même modèle et même embedding_version que la v1) et écrit les passages dans
            rag_backend/data/rag_v2_sources/ (ignoré par git) + un manifeste SANS texte dans docs/rag_v2/.
  upload  : insère ces passages dans knowledge_chunks_v2 (upsert sur chunk_id) avec la clé service du .env
            de rag_backend, jamais affichée ; refuse de toucher knowledge_chunks ; compte la v1 avant / après.

Licence : le schéma n'a pas de champ dédié ; elle est rangée dans `topics` (« license:CC BY-SA 4.0 » ou
« license:Public domain »), l'auteur dans `author`, l'URL dans `source`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAG_BACKEND = HERE.parents[1] / "rag_backend"
OUT_DIR = RAG_BACKEND / "data" / "rag_v2_sources"
CHUNKS = OUT_DIR / "chunks.jsonl"
MANIFEST = HERE / "new_sources_manifest.json"
TABLE = "knowledge_chunks_v2"
TARGET_TOKENS = 256      # max_seq_length de MiniLM : au-delà, l'embedding ignore la fin du passage
SPECIAL_TOKENS = 2       # [CLS] et [SEP] ajoutés par le modèle
UA = "DressMeRAGv2/0.1 (university project; https://github.com/HackedMariam/dressme) python-urllib"

WP, WV = "https://en.wikipedia.org", "https://en.wikivoyage.org"
CC = "CC BY-SA 4.0"
# (titre de page, site, auteur, catégorie v1, thèmes ajoutés)
SOURCES = [
    ("Packing list", WV, "Wikivoyage contributors", "travel", ["travel"]),
    ("Wool", WP, "Wikipedia contributors", "fabrics", ["fabrics", "care"]),
    ("Linen", WP, "Wikipedia contributors", "fabrics", ["fabrics", "care"]),
    ("Cotton", WP, "Wikipedia contributors", "fabrics", ["fabrics"]),
    ("Laundry symbol", WP, "Wikipedia contributors", "care", ["care", "fabrics"]),
    ("Western dress codes", WP, "Wikipedia contributors", "occasions", ["occasions"]),
    ("Business casual", WP, "Wikipedia contributors", "occasions", ["occasions", "styling"]),
    ("Suit", WP, "Wikipedia contributors", "occasions", ["occasions", "styling"]),
    ("Color scheme", WP, "Wikipedia contributors", "color", ["color"]),
    ("Complementary colors", WP, "Wikipedia contributors", "color", ["color"]),
    ("Capsule wardrobe", WP, "Wikipedia contributors", "wardrobe", ["wardrobe", "styling"]),
    ("Female body shape", WP, "Wikipedia contributors", "body", ["body", "styling"]),
]
FTC = {"title": "Clothes Captioning: Complying with the Care Labeling Rule",
       "url": "https://www.ftc.gov/business-guidance/resources/clothes-captioning-complying-care-labeling-rule",
       "policy": "https://www.ftc.gov/policy-notices/website-policy",
       "author": "U.S. Federal Trade Commission", "category": "care", "topics": ["care", "fabrics"]}
DROP_SECTIONS = re.compile(r"^(see also|references|external links|further reading|notes|bibliography|sources|"
                           r"citations|footnotes|notes and references|works cited|gallery)$", re.IGNORECASE)


def get(url: str, params: dict | None = None, attempts: int = 5) -> str:
    """GET poli : une seconde entre deux requêtes, nouvelles tentatives sur 429/503 (Retry-After respecté)."""
    import time
    import urllib.error

    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(1, attempts + 1):
        time.sleep(1.0)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == attempts:
                raise SystemExit(f"HTTP {exc.code} sur {url.split('?')[0]}") from exc
            wait = int(exc.headers.get("Retry-After") or 0) or 5 * attempt
            print(f"  HTTP {exc.code} sur {url.split('?')[0]} : nouvel essai dans {wait} s", flush=True)
            time.sleep(wait)
    raise SystemExit("inaccessible")


# ------------------------------------------------------------------ licences et texte
def wiki_page(title: str, site: str) -> dict:
    """Texte brut par l'API officielle (TextExtracts : sans références ni boîtes de navigation)."""
    data = json.loads(get(f"{site}/w/api.php", {
        "action": "query", "format": "json", "redirects": 1, "titles": title, "formatversion": 2,
        "prop": "extracts|info|pageprops|revisions", "explaintext": 1, "exsectionformat": "wiki",
        "inprop": "url", "rvprop": "ids"}))
    page = data["query"]["pages"][0]
    if page.get("missing") or "disambiguation" in (page.get("pageprops") or {}):
        raise SystemExit(f"Page introuvable ou d'homonymie : {title} ({site})")
    html = get(page["fullurl"])                 # licence affichée sur la page elle-même
    if "creativecommons.org/licenses/by-sa/4.0" not in html:
        raise SystemExit(f"Licence CC BY-SA 4.0 non trouvée sur {page['fullurl']}")
    return {"title": page["title"], "url": page["fullurl"], "revision": page["revisions"][0]["revid"],
            "license": CC, "sections": wiki_sections(page["extract"], page["title"])}


def wiki_sections(extract: str, title: str) -> list[tuple[str, str]]:
    sections, current, lines, dropped = [], "Introduction", [], False
    for line in extract.splitlines():
        heading = re.match(r"^(=+)\s*(.*?)\s*\1$", line.strip())
        if heading:
            if lines and not dropped:
                sections.append((current, "\n".join(lines).strip()))
            level, name = len(heading.group(1)), heading.group(2)
            if level == 2:
                dropped = bool(DROP_SECTIONS.match(name))
                current = name
            elif not dropped:
                current = name
            lines = []
            continue
        if not dropped:
            lines.append(line)
    if lines and not dropped:
        sections.append((current, "\n".join(lines).strip()))
    return [(name, text) for name, text in sections if text]


class FTCParser(HTMLParser):
    """Texte du contenu principal de la page FTC, découpé par titres h2/h3."""

    def __init__(self):
        super().__init__()
        self.in_main, self.skip, self.heading = 0, 0, None
        self.sections, self.current, self.buffer, self.htext = [], "Introduction", [], []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main += 1
        elif self.in_main and tag in ("script", "style", "nav", "footer", "form"):
            self.skip += 1
        elif self.in_main and tag in ("h2", "h3"):
            self.heading = tag
            self.htext = []
        elif self.in_main and tag in ("p", "li", "br", "div"):
            self.buffer.append("\n")

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main -= 1
        elif self.skip and tag in ("script", "style", "nav", "footer", "form"):
            self.skip -= 1
        elif self.heading == tag:
            self.flush()
            self.current = " ".join("".join(self.htext).split())
            self.heading = None

    def handle_data(self, data):
        if not self.in_main or self.skip:
            return
        (self.htext if self.heading else self.buffer).append(data)

    def flush(self):
        text = re.sub(r"\n\s*\n+", "\n\n", "".join(self.buffer)).strip()
        if text:
            self.sections.append((self.current or "Introduction", text))
        self.buffer = []


FTC_LOCAL = OUT_DIR / "ftc_clothes_captioning.html"   # page enregistrée depuis un navigateur (facultatif)


def ftc_page() -> dict | None:
    """Page FTC. ftc.gov refuse les scripts (HTTP 403) : sans copie locale enregistrée depuis un navigateur,
    la source est ignorée (aucun contournement du blocage)."""
    try:
        policy, html = get(FTC["policy"], attempts=1), get(FTC["url"], attempts=1)
        if "public domain" not in policy.lower():
            raise SystemExit("Mention « public domain » absente de la politique du site de la FTC")
    except SystemExit as error:
        if not FTC_LOCAL.exists():
            print(f"FTC ignorée : {error} ; enregistrer la page dans {FTC_LOCAL} pour l'ingérer", flush=True)
            return None
        html = FTC_LOCAL.read_text(encoding="utf-8")   # licence vérifiée à part (Website Policy de la FTC)
    parser = FTCParser()
    parser.feed(html)
    parser.flush()
    sections = [(name, text) for name, text in parser.sections
                if not re.match(r"^(your opportunity to comment|related|share this page)", name, re.IGNORECASE)]
    return {"title": FTC["title"], "url": FTC["url"], "revision": None, "license": "Public domain",
            "sections": sections}


# ------------------------------------------------------------------ découpage
def prefix(title: str, section: str) -> str:
    return f"Document: {title}\nSection: {section}\n\n"


def chunk_sections(doc: dict, tokenizer) -> list[tuple[str, str]]:
    """Section d'abord ; dans une section, paragraphes, puis phrases, puis mots, regroupés pour que le passage
    complet (préfixe Document/Section + [CLS]/[SEP] compris) tienne dans TARGET_TOKENS : rien n'est tronqué."""
    def tokens(text: str) -> int:
        return len(tokenizer.tokenize(text))

    def split(text: str, budget: int) -> list[str]:
        if tokens(text) <= budget:
            return [text]
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if len(sentences) > 1:
            return [part for s in sentences for part in split(s, budget)]
        words, parts, current = text.split(), [], []
        for word in words:                                # phrase trop longue : coupure entre deux mots
            if current and tokens(" ".join(current + [word])) > budget:
                parts.append(" ".join(current))
                current = []
            current.append(word)
        return parts + [" ".join(current)] if current else parts

    out = []
    for section, text in doc["sections"]:
        budget = TARGET_TOKENS - SPECIAL_TOKENS - tokens(prefix(doc["title"], section))
        pieces = [part for p in re.split(r"\n\s*\n|\n", text) if p.strip() for part in split(p.strip(), budget)]
        current: list[str] = []
        for piece in pieces:
            if current and tokens(" ".join(current + [piece])) > budget:
                out.append((section, " ".join(current)))
                current = []
            current.append(piece)
        if current:
            out.append((section, " ".join(current)))
    return out


def prepare() -> None:
    sys.path.insert(0, str(RAG_BACKEND))
    from config import get_settings
    from ingestion.quality import classify_topics, slugify, text_sha256
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    model = SentenceTransformer(settings.embedding_model)
    docs = [wiki_page(title, site) | {"author": author, "category": category, "topics": topics}
            for title, site, author, category, topics in SOURCES]
    ftc = ftc_page()
    if ftc:
        docs.append(ftc | {"author": FTC["author"], "category": FTC["category"], "topics": FTC["topics"]})

    records, manifest = [], []
    for doc in docs:
        document_id = hashlib.sha256(f"{doc['url']}#{doc['revision']}".encode("utf-8")).hexdigest()
        chunks = chunk_sections(doc, model.tokenizer)
        for index, (section, body) in enumerate(chunks):
            content = prefix(doc["title"], section) + body
            _, found = classify_topics(f"{section}\n{body}")
            topics = list(dict.fromkeys(doc["topics"] + found))[:5] + [f"license:{doc['license']}"]
            records.append({
                "chunk_id": f"v2-{slugify(doc['title'])}-c{index}", "document_id": document_id,
                "source": doc["url"], "title": doc["title"], "author": doc["author"], "page": None,
                "section": section, "category": doc["category"], "topics": topics, "chunk_index": index,
                "content_hash": text_sha256(content), "embedding_model": settings.embedding_model,
                "embedding_version": settings.embedding_version, "ocr": False, "text": content})
        # taille vue par le modèle : tokens spéciaux compris, sans troncature
        sizes = [len(model.tokenizer(r["text"], truncation=False)["input_ids"]) for r in records[-len(chunks):]]
        manifest.append({"title": doc["title"], "url": doc["url"], "revision": doc["revision"],
                         "author": doc["author"], "license": doc["license"], "category": doc["category"],
                         "sections": len({s for s, _ in chunks}), "chunks": len(chunks),
                         "tokens_max": max(sizes), "tokens_median": sorted(sizes)[len(sizes) // 2],
                         "chunks_over_256_tokens": sum(s > model.max_seq_length for s in sizes)})
        print(f"{doc['title']:58} {doc['license']:14} {len(chunks):3d} passages", flush=True)

    if any(d["chunks_over_256_tokens"] for d in manifest):
        raise SystemExit("Passage plus long que max_seq_length : il serait tronqué par MiniLM")
    embeddings = model.encode([r["text"] for r in records], batch_size=32, normalize_embeddings=True,
                              convert_to_numpy=True, show_progress_bar=False)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with CHUNKS.open("w", encoding="utf-8") as out:
        for record, vector in zip(records, embeddings, strict=True):
            out.write(json.dumps({**record, "embedding": [round(float(x), 7) for x in vector]}) + "\n")
    MANIFEST.write_text(json.dumps({"prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
                                    "embedding_model": settings.embedding_model,
                                    "embedding_version": settings.embedding_version,
                                    "max_seq_length": model.max_seq_length, "target_tokens": TARGET_TOKENS,
                                    "documents": manifest, "total_chunks": len(records)},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(records)} passages prêts (texte dans {OUT_DIR}, ignoré par git) ; manifeste sans texte : {MANIFEST}")


def upload() -> None:
    sys.path.insert(0, str(RAG_BACKEND))
    from rag.supabase_client import get_supabase

    client = get_supabase()

    def count(table: str) -> int:
        return client.table(table).select("chunk_id", count="exact").limit(1).execute().count

    v1_before, v2_before = count("knowledge_chunks"), count(TABLE)
    rows = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    now = datetime.now(UTC).isoformat()
    payload = [{**{k: v for k, v in r.items() if k != "text"}, "content": r["text"], "updated_at": now}
               for r in rows]
    for start in range(0, len(payload), 50):
        client.table(TABLE).upsert(payload[start:start + 50], on_conflict="chunk_id").execute()
    v1_after, v2_after = count("knowledge_chunks"), count(TABLE)
    if v1_after != v1_before:
        raise SystemExit(f"ALERTE : knowledge_chunks a changé ({v1_before} -> {v1_after})")
    print(f"knowledge_chunks (v1) : {v1_before} -> {v1_after} (inchangée) ; "
          f"{TABLE} : {v2_before} -> {v2_after} (+{v2_after - v2_before})")


if __name__ == "__main__":
    command = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    command.add_argument("command", choices=["prepare", "upload"])
    {"prepare": prepare, "upload": upload}[command.parse_args().command]()
