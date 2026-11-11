from . import retrieval


def _hits():
    for corpus in retrieval.CORPORA:
        for doc in retrieval._load(corpus):
            yield retrieval._to_hit(corpus, doc, 0.0)


def known_ids() -> set[str]:
    return {h["citation_id"] for h in _hits()}


def get_passage(citation_id: str) -> dict | None:
    for hit in _hits():
        if hit["citation_id"] == citation_id:
            return {k: v for k, v in hit.items() if k != "score"}
    return None


if __name__ == "__main__":
    ids = sorted(known_ids())
    print(len(ids), "passages:", ids[:3], "...", ids[-2:])
    print(get_passage("RG-ONC-002")["text"][:120])
