from app.common.hydrate import hydrate

RULE = {"citation_id": "RG-X-1", "corpus": "guidance", "title": "Rule one", "text": "Rule text."}


def fake_lookup(citation_id):
    return RULE if citation_id == "RG-X-1" else None


def make_doc(**extra):
    doc = {
        "notes": "Applicant notes.",
        "rating": {
            "status": "rated", "loading_pct": 0, "rule_ids": ["R1"],
            "methodology_version": "v4.2", "notes": [], "guidance_refs": [],
        },
        "draft": [
            {"id": "s1", "text": "a", "cites": ["CASE", "RATING"]},
            {"id": "s2", "text": "b", "cites": ["RG-X-1", "RG-X-1"]},
        ],
        "evidence": {"verified": ["RG-X-1"], "dropped": ["NOPE-1"]},
    }
    doc.update(extra)
    return doc


def test_the_case_notes_and_rating_become_pseudo_passages():
    found = hydrate(make_doc(), fake_lookup)["passages"]
    assert found["CASE"]["text"] == "Applicant notes."
    assert found["RATING"]["text"].startswith("Rating engine v4.2")


def test_a_corpus_passage_carries_its_title_kind_and_text():
    found = hydrate(make_doc(), fake_lookup)["passages"]
    assert found["RG-X-1"] == {"title": "Rule one", "kind": "guidance", "text": "Rule text."}


def test_unknown_ids_are_left_out():
    assert "NOPE-1" not in hydrate(make_doc(), fake_lookup)["passages"]


def test_the_input_is_not_modified():
    doc = make_doc()
    hydrate(doc, fake_lookup)
    assert "passages" not in doc


def test_a_missing_rating_is_reported_plainly():
    found = hydrate(make_doc(rating=None), fake_lookup)["passages"]
    assert found["RATING"]["text"] == "No rating was produced."


def test_a_case_with_no_citations_has_no_passages():
    assert hydrate({"notes": "x"}, fake_lookup)["passages"] == {}
