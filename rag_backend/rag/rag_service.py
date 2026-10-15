import os

from dotenv import load_dotenv
from openai import OpenAI

from rag.retriever import retrieve

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("LLM_API_KEY")
    or os.environ["OPENAI_API_KEY"],
    base_url=os.getenv("LLM_BASE_URL") or None,
)

MODEL = os.environ["LLM_MODEL"]


def answer_question(question: str, top_k: int = 5) -> dict:
    """Generate a DressMe answer grounded in retrieved knowledge."""

    passages = retrieve(question, top_k=top_k)

    if not passages:
        return {
            "answer": (
                "I couldn't find relevant information in "
                "the DressMe knowledge base."
            ),
            "sources": [],
        }

    context_parts = []

    for item in passages:
        context_parts.append(
            f"Source: {item.get('source', 'Unknown')}, "
            f"page: {item.get('page', 'Unknown')}\n"
            f"{item['content']}"
        )

    context = "\n\n---\n\n".join(context_parts)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are DressMe, a fashion and wardrobe assistant. "
                    "Answer using the supplied knowledge context. "
                    "Do not claim that the context says something it "
                    "does not. If the context is insufficient, say so. "
                    "You may use general reasoning, but distinguish it "
                    "from facts supported by the retrieved sources."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Retrieved knowledge:\n{context}"
                ),
            },
        ],
        temperature=0.3,
    )

    answer = response.choices[0].message.content or ""

    sources = [
        {
            "source": item.get("source"),
            "page": item.get("page"),
            "similarity": item.get("similarity"),
        }
        for item in passages
    ]

    return {
        "answer": answer,
        "sources": sources,
    }


if __name__ == "__main__":
    question = input("Ask DressMe: ")

    result = answer_question(question)

    print("\nDressMe:", result["answer"])
    print("\nSources:")

    for source in result["sources"]:
        print(
            f"- {source['source']}, "
            f"page {source['page']}, "
            f"similarity {source['similarity']:.3f}"
        )