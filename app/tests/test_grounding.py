import json

import pytest

from app.common.grounding import (
    Claim,
    GroundingError,
    Verdict,
    applicability_claims,
    build_gate_prompt,
    decide,
    parse_verdicts,
    supported_citations,
)

PASSAGES = {
    "RG-ONC-002": {"text": "Stage I: 5 years or more with no recurrence: no loading."},
    "PR-A-19902": {"text": "Stage I, 6 years. Decision: accept. Loading: 0%."},
}


def lookup(cid):
    return PASSAGES.get(cid)


C1 = Claim("c1", "Stage I at 5+ years carries no loading.", ("RG-ONC-002",))
C2 = Claim("c2", "A similar case was accepted at standard terms.", ("PR-A-19902",))


def v(cid, verdict="supported"):
    return {"claim_id": cid, "verdict": verdict, "reason": "ok"}


def code_of(fn, *args):
    with pytest.raises(GroundingError) as exc:
        fn(*args)
    return exc.value.code


def test_prompt_is_hydrated_from_the_corpus():
    data = json.loads(build_gate_prompt([C1, C2], lookup))
    assert [c["claim_id"] for c in data["claims"]] == ["c1", "c2"]
    assert data["claims"][0]["passages"][0]["text"].startswith("Stage I: 5 years")


def test_unknown_citation_is_refused_before_any_model_call():
    bad = Claim("c9", "x", ("RG-NOPE",))
    assert code_of(build_gate_prompt, [bad], lookup) == "UNKNOWN_CITATION"


def test_no_claims_is_refused():
    assert code_of(build_gate_prompt, [], lookup) == "NO_CLAIMS"


def test_duplicate_claim_ids_are_refused():
    assert code_of(build_gate_prompt, [C1, C1], lookup) == "DUPLICATE_CLAIM"


def test_valid_verdicts_parse():
    out = parse_verdicts(json.dumps([v("c1"), v("c2", "unsupported")]), [C1, C2])
    assert [x.verdict for x in out] == ["supported", "unsupported"]


def test_fenced_verdicts_parse():
    text = "```json\n" + json.dumps([v("c1"), v("c2")]) + "\n```"
    assert len(parse_verdicts(text, [C1, C2])) == 2


def test_missing_verdict_is_refused():
    assert code_of(parse_verdicts, json.dumps([v("c1")]), [C1, C2]) == "CLAIM_MISMATCH"


def test_invented_claim_id_is_refused():
    text = json.dumps([v("c1"), v("c2"), v("c3")])
    assert code_of(parse_verdicts, text, [C1, C2]) == "CLAIM_MISMATCH"


def test_unknown_verdict_value_is_refused():
    text = json.dumps([v("c1", "maybe"), v("c2")])
    assert code_of(parse_verdicts, text, [C1, C2]) == "SCHEMA"


def test_extra_keys_in_a_verdict_are_refused():
    item = dict(v("c1"), confidence=0.9)
    assert code_of(parse_verdicts, json.dumps([item, v("c2")]), [C1, C2]) == "SCHEMA"


def test_non_json_is_refused():
    assert code_of(parse_verdicts, "looks fine to me", [C1]) == "NOT_JSON"


def test_claim_without_citations_cannot_be_supported():
    bare = Claim("c5", "Unsourced.", ())
    out = parse_verdicts(json.dumps([v("c5")]), [bare])
    assert out[0].verdict == "unsupported"


def test_decide_passes_only_when_every_claim_is_supported():
    ok = [Verdict("c1", "supported", "r"), Verdict("c2", "supported", "r")]
    assert decide([C1, C2], ok) == "passed"
    one = [ok[0], Verdict("c2", "unsupported", "r")]
    assert decide([C1, C2], one) == "hard_stop"
    contra = [ok[0], Verdict("c2", "contradicted", "r")]
    assert decide([C1, C2], contra) == "hard_stop"


def test_decide_fails_closed_on_empty_or_partial():
    assert decide([], []) == "hard_stop"
    assert decide([C1, C2], [Verdict("c1", "supported", "r")]) == "hard_stop"


def test_supported_citations_keep_only_supported_claims():
    vs = [Verdict("c1", "supported", "r"), Verdict("c2", "unsupported", "r")]
    assert supported_citations([C1, C2], vs) == ["RG-ONC-002"]


def test_applicability_claims_one_per_citation():
    facts = {"condition": "breast_cancer_stage1", "years_since_treatment": 6.7}
    claims = applicability_claims(facts, ["RG-ONC-002", "PR-A-19902"])
    assert [c.cites for c in claims] == [("RG-ONC-002",), ("PR-A-19902",)]
    assert "breast_cancer_stage1" in claims[0].text
    assert len({c.claim_id for c in claims}) == 2


def test_precedent_claims_state_a_tolerance_and_guidance_claims_do_not():
    claims = applicability_claims({"condition": "x"}, ["RG-ONC-002", "PR-A-19902"])
    assert "within one year" not in claims[0].text
    assert "within one year" in claims[1].text
