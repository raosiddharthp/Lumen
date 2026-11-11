import json

from .grounding import Claim, _strip_fences

PSEUDO_IDS = ("CASE", "RATING")
MAX_SENTENCES = 12
MAX_CHARS = 400


class DraftError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def allowed_ids_for(evidence_ids: list[str]) -> set[str]:
    return set(evidence_ids) | set(PSEUDO_IDS)


def render_rating(rating) -> str:
    loading = "none" if rating.loading_pct is None else f"{rating.loading_pct}%"
    rules = ", ".join(rating.rule_ids) or "none"
    return (
        f"Rating engine {rating.methodology_version}: status {rating.status}; "
        f"loading {loading}; rules {rules}."
    )


def make_lookup(base_lookup, case_notes: str, rating):
    pseudo = {
        "CASE": {"text": case_notes},
        "RATING": {"text": render_rating(rating)},
    }

    def lookup(citation_id: str):
        if citation_id in pseudo:
            return {"citation_id": citation_id, **pseudo[citation_id]}
        return base_lookup(citation_id)

    return lookup


def build_draft_prompt(case_notes: str, rating, evidence_ids: list[str], base_lookup) -> str:
    passages = []
    for cid in evidence_ids:
        passage = base_lookup(cid)
        if passage is None:
            raise DraftError("UNKNOWN_CITATION", cid)
        passages.append({"citation_id": cid, "text": passage["text"]})
    return json.dumps(
        {
            "case_notes": case_notes,
            "rating": render_rating(rating),
            "passages": passages,
        },
        indent=1,
    )


def parse_draft(text: str, allowed_ids: set[str]) -> list[Claim]:
    try:
        data = json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        raise DraftError("NOT_JSON", str(exc)[:100])
    if not isinstance(data, list) or not data:
        raise DraftError("SCHEMA", "expected a non-empty list")
    if len(data) > MAX_SENTENCES:
        raise DraftError("TOO_LONG", f"{len(data)} sentences")
    claims = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict) or set(item) != {"text", "cites"}:
            raise DraftError("SCHEMA", f"s{i} needs exactly text and cites")
        sentence, cites = item["text"], item["cites"]
        if not isinstance(sentence, str) or not sentence.strip():
            raise DraftError("SCHEMA", f"s{i} text is empty or not text")
        if len(sentence) > MAX_CHARS:
            raise DraftError("SCHEMA", f"s{i} text is too long")
        if not isinstance(cites, list) or not all(isinstance(c, str) for c in cites):
            raise DraftError("SCHEMA", f"s{i} cites must be a list of text")
        if not cites:
            raise DraftError("UNTAGGED", f"s{i}")
        unknown = [c for c in cites if c not in allowed_ids]
        if unknown:
            raise DraftError("UNKNOWN_CITATION", ", ".join(unknown))
        claims.append(Claim(f"s{i}", sentence.strip(), tuple(dict.fromkeys(cites))))
    return claims
