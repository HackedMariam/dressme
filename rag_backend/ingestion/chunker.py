import json
import re
from pathlib import Path

INPUT_FILE = Path("data/extracted_pages.json")
OUTPUT_FILE = Path("data/chunks.jsonl")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def slugify(source: str) -> str:
    """Build a filesystem-safe key so chunk ids stay unique per document."""
    slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    return slug or "unknown"


def clean_text(text: str) -> str:
    """Normalize whitespace without removing meaningful punctuation."""
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str) -> list[str]:
    """Split text into overlapping character-based chunks."""
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))

        # Prefer breaking at a word boundary.
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - CHUNK_OVERLAP, start + 1)

    return chunks


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        pages = json.load(file)

    total_chunks = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for page_data in pages:
            page_number = page_data["page"]
            source = page_data.get("source") or INPUT_FILE.name
            text = clean_text(page_data.get("text", ""))

            if not text:
                continue

            for index, chunk_text in enumerate(split_text(text)):
                record = {
                    "chunk_id": f"{slugify(source)}-p{page_number}-c{index}",
                    "source": source,
                    "page": page_number,
                    "text": chunk_text,
                }

                output.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )
                total_chunks += 1

    print(f"Pages processed: {len(pages)}")
    print(f"Chunks created: {total_chunks}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()