"""Attach the text of every passage a case cites. Trusted code only (D8)."""
from types import SimpleNamespace

from app.common import draft, passages


def _ids(doc):
    ids = []
    for sentence in doc.get("draft") or []:
        ids.extend(sentence.get("cites", []))
    evidence = doc.get("evidence") or {}
    ids.extend(evidence.get("verified", []))
    ids.extend(evidence.get("dropped", []))
    return list(dict.fromkeys(ids))


def _corpus_lookup(citation_id):
    if citation_id in passages.known_ids():
        return passages.get_passage(citation_id)
    return None


def hydrate(doc, lookup=None):
    """Return a copy of the case with a `passages` map for every cited id."""
    lookup = lookup or _corpus_lookup
    found = {}
    for cid in _ids(doc):
        if cid == "CASE":
            found[cid] = {"title": "Case notes", "kind": "case", "text": doc.get("notes", "")}
        elif cid == "RATING":
            rating = doc.get("rating")
            text = draft.render_rating(SimpleNamespace(**rating)) if rating else "No rating was produced."
            found[cid] = {"title": "Rating engine output", "kind": "rating", "text": text}
        else:
            passage = lookup(cid)
            if passage:
                found[cid] = {
                    "title": passage.get("title", cid),
                    "kind": passage.get("corpus", ""),
                    "text": passage["text"],
                }
    return {**doc, "passages": found}
