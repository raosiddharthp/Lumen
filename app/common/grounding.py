import json
from dataclasses import dataclass

VERDICTS = ("supported", "unsupported", "contradicted")


class GroundingError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    cites: tuple[str, ...]


@dataclass(frozen=True)
class Verdict:
    claim_id: str
    verdict: str
    reason: str


def applicability_claims(factors: dict, citation_ids: list[str]) -> list[Claim]:
    summary = ", ".join(f"{k}={v}" for k, v in factors.items())
    return [
        Claim(
            claim_id=f"applies-{cid}",
            text=f"This case ({summary}) falls within the scope of this passage.",
            cites=(cid,),
        )
        for cid in citation_ids
    ]


def build_gate_prompt(claims: list[Claim], lookup) -> str:
    if not claims:
        raise GroundingError("NO_CLAIMS")
    ids = [c.claim_id for c in claims]
    if len(set(ids)) != len(ids):
        raise GroundingError("DUPLICATE_CLAIM")
    items = []
    for claim in claims:
        passages = []
        for cid in claim.cites:
            passage = lookup(cid)
            if passage is None:
                raise GroundingError("UNKNOWN_CITATION", cid)
            passages.append({"citation_id": cid, "text": passage["text"]})
        items.append(
            {"claim_id": claim.claim_id, "text": claim.text, "passages": passages}
        )
    return json.dumps({"claims": items}, indent=1)


def _strip_fences(text: str) -> str:
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    return body.strip()


def parse_verdicts(text: str, claims: list[Claim]) -> list[Verdict]:
    try:
        data = json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        raise GroundingError("NOT_JSON", str(exc)[:100])
    if not isinstance(data, list):
        raise GroundingError("SCHEMA", "expected a list of verdicts")
    by_id: dict[str, Verdict] = {}
    for item in data:
        if not isinstance(item, dict) or set(item) != {"claim_id", "verdict", "reason"}:
            raise GroundingError("SCHEMA", "each verdict needs exactly claim_id, verdict, reason")
        if item["verdict"] not in VERDICTS or not isinstance(item["reason"], str):
            raise GroundingError("SCHEMA", "bad verdict or reason")
        if item["claim_id"] in by_id:
            raise GroundingError("DUPLICATE_VERDICT", str(item["claim_id"]))
        by_id[item["claim_id"]] = Verdict(
            item["claim_id"], item["verdict"], item["reason"][:300]
        )
    if set(by_id) != {c.claim_id for c in claims}:
        raise GroundingError("CLAIM_MISMATCH")
    out = []
    for claim in claims:
        verdict = by_id[claim.claim_id]
        if not claim.cites and verdict.verdict == "supported":
            verdict = Verdict(claim.claim_id, "unsupported", "no cited passages")
        out.append(verdict)
    return out


def decide(claims: list[Claim], verdicts: list[Verdict]) -> str:
    if not claims or {v.claim_id for v in verdicts} != {c.claim_id for c in claims}:
        return "hard_stop"
    if all(v.verdict == "supported" for v in verdicts):
        return "passed"
    return "hard_stop"


def supported_citations(claims: list[Claim], verdicts: list[Verdict]) -> list[str]:
    ok = {v.claim_id for v in verdicts if v.verdict == "supported"}
    return list(
        dict.fromkeys(cid for c in claims if c.claim_id in ok for cid in c.cites)
    )
