import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

INPUT_FILE = Path("data/chunks.jsonl")
OUTPUT_FILE = Path("data/embedded_chunks.jsonl")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 32


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found. Run chunker.py first."
        )

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        records = [
            json.loads(line)
            for line in file
            if line.strip()
        ]

    if not records:
        raise ValueError("No chunks found to embed.")

    print(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    texts = [record["text"] for record in records]

    print(f"Generating embeddings for {len(texts)} chunks...")

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    )

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for record, embedding in zip(records, embeddings):
            result = {
                **record,
                "embedding": embedding.tolist(),
            }

            output.write(
                json.dumps(result, ensure_ascii=False) + "\n"
            )

    print(f"Chunks embedded: {len(embeddings)}")
    print(f"Vector dimensions: {embeddings.shape[1]}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()