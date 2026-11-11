import math

from google import genai
from google.cloud import firestore
from google.genai import types

from . import config

_ai = genai.Client(
    vertexai=True, project=config.PROJECT_ID, location=config.EMBED_LOCATION
)
_db = firestore.Client(project=config.PROJECT_ID)

CORPORA = {"guidance": "corpus_guidance", "precedent": "corpus_precedent"}
_cache: dict[str, list[dict]] = {}


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector]


def embed_query(text: str) -> list[float]:
    resp = _ai.models.embed_content(
        model=config.EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY", output_dimensionality=config.EMBED_DIMS
        ),
    )
    return _normalise(resp.embeddings[0].values)


def _load(corpus: str) -> list[dict]:
    if corpus not in _cache:
        collection = CORPORA[corpus]
        _cache[corpus] = [d.to_dict() for d in _db.collection(collection).stream()]
    return _cache[corpus]


def _to_hit(corpus: str, doc: dict, score: float) -> dict:
    if corpus == "guidance":
        citation_id = doc["id"]
        title = doc["title"]
        text = doc["text"]
    else:
        citation_id = "PR-" + doc["case_no"]
        title = "Precedent " + doc["case_no"]
        text = (
            f"{doc['condition']}. {doc['profile']}. Decision: {doc['decision']}. "
            f"Loading: {doc['loading_pct']}%. Review tier: {doc['tier']}."
        )
    return {
        "citation_id": citation_id,
        "corpus": corpus,
        "title": title,
        "text": text,
        "score": round(score, 4),
        "corpus_version": doc["corpus_version"],
    }


def search(query: str, corpus: str, k: int = 3) -> list[dict]:
    query_vector = embed_query(query)
    scored = []
    for doc in _load(corpus):
        score = sum(a * b for a, b in zip(query_vector, doc["embedding"]))
        scored.append((score, doc))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [_to_hit(corpus, doc, score) for score, doc in scored[:k]]


if __name__ == "__main__":
    import sys

    for hit in search(sys.argv[2], sys.argv[1], k=3):
        print(f"{hit['score']:.3f}  {hit['citation_id']}  {hit['title']}")
