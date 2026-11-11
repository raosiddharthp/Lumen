from datetime import datetime, timezone

import pytest

from app.signoff import SignoffError, apply_signoff

T1 = ["senior_underwriter"]
T2 = ["senior_underwriter", "cosigner_cmo_or_cuo"]
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


def make(signers, **extra):
    doc = {"status": "awaiting_signoff", "referral": {"signers": signers}}
    doc.update(extra)
    return doc


def sign(doc, role, decision="approve", name="A. Visser", reason=""):
    return apply_signoff(doc, role, name, decision, reason, now=NOW)


def test_tier_1_closes_on_one_approval():
    out = sign(make(T1), "senior_underwriter")
    assert out["status"] == "signed_off"
    assert out["signoffs"][0]["at"] == NOW.isoformat()


def test_tier_2_waits_for_both_signers():
    first = sign(make(T2), "senior_underwriter")
    assert first["status"] == "awaiting_signoff"
    second = sign(make(T2, signoffs=first["signoffs"]), "cosigner_cmo_or_cuo")
    assert second["status"] == "signed_off"
    assert len(second["signoffs"]) == 2


def test_a_decline_needs_a_reason_and_closes_the_case():
    with pytest.raises(SignoffError) as exc:
        sign(make(T2), "senior_underwriter", "decline")
    assert exc.value.code == "reason_required"
    out = sign(make(T2), "senior_underwriter", "decline", reason="Needs a specialist review.")
    assert out["status"] == "declined"


@pytest.mark.parametrize(
    "doc, kwargs, code",
    [
        (make(T1), {"role": "cosigner_cmo_or_cuo"}, "role_not_required"),
        (
            make(T2, signoffs=[{"role": "senior_underwriter", "decision": "approve"}]),
            {"role": "senior_underwriter"},
            "already_signed",
        ),
        (make(T1, status="signed_off"), {"role": "senior_underwriter"}, "closed"),
        (make(T1), {"role": "senior_underwriter", "decision": "maybe"}, "bad_decision"),
        (make(T1), {"role": "senior_underwriter", "name": "  "}, "name_required"),
    ],
)
def test_invalid_signoffs_are_refused(doc, kwargs, code):
    with pytest.raises(SignoffError) as exc:
        sign(doc, **kwargs)
    assert exc.value.code == code


def test_the_input_case_is_not_modified():
    doc = make(T2)
    sign(doc, "senior_underwriter")
    assert "signoffs" not in doc
    assert doc["status"] == "awaiting_signoff"
