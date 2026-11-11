import json
import math
from pathlib import Path

from google import genai
from google.cloud import firestore
from google.genai import types

PROJECT_ID = "lumen-poc-srao26"
EMBED_MODEL = "gemini-embedding-001"
EMBED_LOCATION = "us-east1"
DIMS = 768
PRICE_PER_MILLION_TOKENS = 0.15
DATA_DIR = Path(__file__).parent / "data"

ai = genai.Client(vertexai=True, project=PROJECT_ID, location=EMBED_LOCATION)
db = firestore.Client(project=PROJECT_ID)


def embed_document(text: str) -> list[float]:
    resp = ai.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT", output_dimensionality=DIMS
        ),
    )
    vector = resp.embeddings[0].values
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector]


def load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    total_chars = 0
    count = 0

    guidance = load("guidance_v1.json")
    for p in guidance["passages"]:
        text = f"{p['title']}. {p['text']}"
        total_chars += len(text)
        db.collection("corpus_guidance").document(p["id"]).set(
            {
                "id": p["id"],
                "section": p["section"],
                "title": p["title"],
                "condition": p["condition"],
                "text": p["text"],
                "corpus_version": guidance["version"],
                "embedding_model": EMBED_MODEL,
                "dims": DIMS,
                "embedding": embed_document(text),
            }
        )
        count += 1

    precedent = load("precedent_v1.json")
    for c in precedent["cases"]:
        text = f"{c['condition']}. {c['profile']}. Decision: {c['decision']}."
        total_chars += len(text)
        db.collection("corpus_precedent").document(c["case_no"]).set(
            {
                "case_no": c["case_no"],
                "year": c["year"],
                "profile": c["profile"],
                "condition": c["condition"],
                "decision": c["decision"],
                "loading_pct": c["loading_pct"],
                "tier": c["tier"],
                "corpus_version": precedent["version"],
                "embedding_model": EMBED_MODEL,
                "dims": DIMS,
                "embedding": embed_document(text),
            }
        )
        count += 1

    approx_tokens = total_chars // 4
    cost = approx_tokens / 1_000_000 * PRICE_PER_MILLION_TOKENS
    print(f"documents written: {count}")
    print(f"approx input tokens: {approx_tokens}")
    print(f"approx embedding cost: USD {cost:.6f}")


if __name__ == "__main__":
    main()
