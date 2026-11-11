import inspect

import pytest

from app.common.rating import Factors, rate
from app.common.referral import SUM_ASSURED_LIMIT, refer


def run(factors, grounding="passed", precedent=("PR-X",)):
    return refer(factors, rate(factors), grounding, list(precedent))


def test_anchor_case_is_tier_1():
    f = Factors(condition="breast_cancer_stage1", years_since_treatment=5.0,
                sum_assured=500000)
    r = run(f, precedent=("PR-A-19902",))
    assert r.tier == 1
    assert r.reasons == ()
    assert r.signers == ("senior_underwriter",)


def test_sum_assured_limit_is_strictly_above():
    at_limit = Factors(condition="none", sum_assured=SUM_ASSURED_LIMIT)
    above = Factors(condition="none", sum_assured=SUM_ASSURED_LIMIT + 1)
    assert run(at_limit).tier == 1
    r = run(above)
    assert r.tier == 2 and "POL-01" in r.reasons


def test_any_decline_is_tier_2():
    f = Factors(condition="diabetes_t2", hba1c=7.0, complications=2)
    r = run(f)
    assert r.tier == 2 and "POL-02" in r.reasons


def test_grounding_hard_stop_forces_tier_2():
    f = Factors(condition="breast_cancer_stage1", years_since_treatment=5.0)
    r = run(f, grounding="hard_stop")
    assert r.tier == 2 and "POL-03" in r.reasons


def test_unknown_grounding_state_fails_closed():
    f = Factors(condition="breast_cancer_stage1", years_since_treatment=5.0)
    assert "POL-03" in run(f, grounding="maybe").reasons
    assert "POL-03" in run(f, grounding=None).reasons


def test_mandatory_referral_condition_myocardial_infarction():
    f = Factors(condition="myocardial_infarction", years_since_treatment=4,
                stress_test_normal=True)
    r = run(f)
    assert r.tier == 2 and "POL-04:MI-3Y" in r.reasons


def test_mandatory_referral_condition_stage2():
    f = Factors(condition="breast_cancer_stage2plus", years_since_treatment=7)
    r = run(f)
    assert r.tier == 2 and "POL-04:ONC-S2-7Y" in r.reasons


def test_unrated_case_goes_to_tier_2():
    r = run(Factors(condition="rare_autoimmune"))
    assert r.tier == 2 and "POL-05" in r.reasons


def test_rated_medical_case_without_precedent_is_tier_2():
    f = Factors(condition="breast_cancer_stage1", years_since_treatment=5.0)
    r = run(f, precedent=())
    assert r.tier == 2 and "POL-06" in r.reasons


def test_no_medical_history_does_not_need_precedent():
    f = Factors(condition="none", occupation="offshore")
    assert run(f, precedent=()).tier == 1


def test_gate_takes_no_confidence_input():
    params = list(inspect.signature(refer).parameters)
    assert params == ["factors", "rating", "grounding", "precedent_ids"]


def test_human_signoff_is_always_required():
    tier1 = run(Factors(condition="none"))
    tier2 = run(Factors(condition="rare_autoimmune"))
    assert tier1.requires_human_signoff is True
    assert tier2.requires_human_signoff is True


REPLAY = [
    ("A-19902", Factors(condition="breast_cancer_stage1",
                        years_since_treatment=6, sum_assured=300000), 1),
    ("A-17540", Factors(condition="breast_cancer_stage1",
                        years_since_treatment=3.5), 1),
    ("A-20118", Factors(condition="breast_cancer_stage2plus",
                        years_since_treatment=7), 2),
    ("C-14377", Factors(condition="hypertension", systolic=134, diastolic=84,
                        medications=1), 1),
    ("C-18826", Factors(condition="myocardial_infarction",
                        years_since_treatment=4, stress_test_normal=True), 2),
    ("D-16209", Factors(condition="diabetes_t2", hba1c=7.4), 1),
    ("O-15031", Factors(condition="none", occupation="offshore"), 1),
    ("G-12984", Factors(condition="none", sum_assured=900000), 2),
]


@pytest.mark.parametrize(
    "case_no,factors,expected_tier", REPLAY, ids=[r[0] for r in REPLAY]
)
def test_precedent_tiers_replay(case_no, factors, expected_tier):
    result = run(factors, precedent=(f"PR-{case_no}",))
    assert result.tier == expected_tier
