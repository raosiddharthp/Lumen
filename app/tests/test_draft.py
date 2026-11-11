import json

import pytest

from app.common.draft import (
    DraftError,
    allowed_ids_for,
    build_draft_prompt,
    make_lookup,
    parse_draft,
    render_rating,
)
from app.common.rating import Factors, rate

RATING = rate(
    Factors(
        condition="breast_cancer_stage1",
        years_since_treatment=6.7,
        recurrence=False,
        surveillance_clear=True,
    )
)
ALLOWED = allowed_ids_for(["RG-ONC-002", "PR-A-19902"])
BASE = {
    "RG-ONC-002": {"text": "Stage I rule."},
    "PR-A-19902": {"text": "Precedent."},
}


def base_lookup(cid):
    return BASE.get(cid)


def item(text="Sentence.", cites=("CASE",)):
    return {"text": text, "cites": list(cites)}


def code_of(text):
    with pytest.raises(DraftError) as exc:
        parse_draft(text, ALLOWED)
    return exc.value.code


def test_rating_is_rendered_with_version_loading_and_rules():
    text = render_rating(RATING)
    assert "v4.2" in text and "loading 0" in text and "ONC-S1-5Y" in text


def test_unrated_case_renders_no_loading():
    text = render_rating(rate(Factors(condition="rare_autoimmune")))
    assert "loading none" in text and "no_rating" in text


def test_valid_draft_becomes_numbered_claims():
    text = json.dumps(
        [item("Stage I.", ("CASE", "RG-ONC-002")), item("Rated 0%.", ("RATING",))]
    )
    claims = parse_draft(text, ALLOWED)
    assert [c.claim_id for c in claims] == ["s1", "s2"]
    assert claims[0].cites == ("CASE", "RG-ONC-002")
    assert claims[1].text == "Rated 0%."


def test_fenced_draft_is_accepted():
    text = "```json\n" + json.dumps([item()]) + "\n```"
    assert len(parse_draft(text, ALLOWED)) == 1


def test_untagged_sentence_is_rejected():
    assert code_of(json.dumps([item(cites=())])) == "UNTAGGED"


def test_unknown_citation_is_rejected():
    assert code_of(json.dumps([item(cites=("RG-NOPE",))])) == "UNKNOWN_CITATION"


def test_evidence_that_was_not_provided_is_rejected():
    assert code_of(json.dumps([item(cites=("RG-ONC-003",))])) == "UNKNOWN_CITATION"


def test_extra_keys_are_rejected():
    bad = dict(item(), confidence=0.9)
    assert code_of(json.dumps([bad])) == "SCHEMA"


def test_empty_draft_is_rejected():
    assert code_of("[]") == "SCHEMA"


def test_too_many_sentences_are_rejected():
    assert code_of(json.dumps([item() for _ in range(13)])) == "TOO_LONG"


def test_overlong_sentence_is_rejected():
    assert code_of(json.dumps([item("x" * 401)])) == "SCHEMA"


def test_non_json_is_rejected():
    assert code_of("The case looks fine.") == "NOT_JSON"


def test_lookup_resolves_pseudo_ids_and_falls_back_to_the_corpus():
    lookup = make_lookup(base_lookup, "Case notes here.", RATING)
    assert lookup("CASE")["text"] == "Case notes here."
    assert lookup("RATING")["text"].startswith("Rating engine")
    assert lookup("RG-ONC-002")["text"] == "Stage I rule."
    assert lookup("RG-NOPE") is None


def test_draft_prompt_carries_notes_rating_and_passages():
    data = json.loads(build_draft_prompt("Notes.", RATING, ["RG-ONC-002"], base_lookup))
    assert data["case_notes"] == "Notes."
    assert data["rating"].startswith("Rating engine")
    assert data["passages"] == [{"citation_id": "RG-ONC-002", "text": "Stage I rule."}]
    with pytest.raises(DraftError):
        build_draft_prompt("Notes.", RATING, ["RG-NOPE"], base_lookup)


def test_allowed_ids_always_include_case_and_rating():
    assert {"CASE", "RATING", "RG-ONC-002"} <= allowed_ids_for(["RG-ONC-002"])
