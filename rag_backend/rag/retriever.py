import os

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from supabase import create_client

load_dotenv()

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or os.environ["SUPABASE_KEY"],
)

embedding_model = SentenceTransformer(MODEL_NAME)


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Retrieve relevant fashion knowledge from Supabase."""

    query_vector = embedding_model.encode(
        query,
        normalize_embeddings=True,
    ).tolist()

    response = supabase.rpc(
        "match_knowledge_chunks",
        {
            "query_embedding": query_vector,
            "match_count": top_k,
        },
    ).execute()

    return response.data or []


if __name__ == "__main__":
    question = input("Ask DressMe a fashion question: ")

    for result in retrieve(question):
        print(f"\nSource: {result['source']}, page: {result['page']}")
        print(f"Similarity: {result['similarity']:.3f}")
        print(result["content"])