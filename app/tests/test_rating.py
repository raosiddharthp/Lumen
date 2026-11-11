from app.common.rating import Factors, rate


def test_anchor_case_a24471_standard_rate():
    r = rate(Factors(condition="breast_cancer_stage1", years_since_treatment=5.0,
                     sum_assured=500000))
    assert r.status == "rated" and r.loading_pct == 0
    assert r.guidance_refs == ["RG-ONC-002"]
    assert r.methodology_version == "v4.2"


def test_stage1_boundaries():
    def at(y):
        return rate(Factors(condition="breast_cancer_stage1", years_since_treatment=y))
    assert at(1.99).status == "postpone"
    assert at(2.0).loading_pct == 100
    assert at(2.99).loading_pct == 100
    assert at(3.0).loading_pct == 50
    assert at(4.99).loading_pct == 50
    assert at(5.0).loading_pct == 0


def test_recurrence_is_never_rated():
    r = rate(Factors(condition="breast_cancer_stage1", years_since_treatment=8,
                     recurrence=True))
    assert r.status == "no_rating" and r.loading_pct is None


def test_precedent_a19902_stage1_six_years():
    assert rate(Factors(condition="breast_cancer_stage1",
                        years_since_treatment=6)).loading_pct == 0


def test_precedent_a17540_stage1_three_and_half_years():
    assert rate(Factors(condition="breast_cancer_stage1",
                        years_since_treatment=3.5)).loading_pct == 50


def test_precedent_a20118_stage2_seven_years():
    assert rate(Factors(condition="breast_cancer_stage2plus",
                        years_since_treatment=7)).loading_pct == 50


def test_precedent_c14377_controlled_hypertension():
    r = rate(Factors(condition="hypertension", systolic=134, diastolic=84,
                     medications=1))
    assert r.loading_pct == 0


def test_precedent_c18826_myocardial_infarction():
    r = rate(Factors(condition="myocardial_infarction", years_since_treatment=4,
                     stress_test_normal=True))
    assert r.loading_pct == 50


def test_precedent_d16209_diabetes():
    assert rate(Factors(condition="diabetes_t2", hba1c=7.4)).loading_pct == 50


def test_precedent_o15031_offshore_no_medical_history():
    assert rate(Factors(condition="none", occupation="offshore")).loading_pct == 25


def test_occupation_is_added_to_medical_loading():
    r = rate(Factors(condition="breast_cancer_stage1", years_since_treatment=3.5,
                     occupation="offshore"))
    assert r.loading_pct == 75
    assert r.guidance_refs == ["RG-ONC-002", "RG-OCC-001"]


def test_two_diabetes_complications_decline():
    r = rate(Factors(condition="diabetes_t2", hba1c=7.0, complications=2))
    assert r.status == "decline"


def test_unknown_condition_is_never_guessed():
    r = rate(Factors(condition="rare_autoimmune"))
    assert r.status == "no_rating" and r.loading_pct is None
    assert r.guidance_refs == ["RG-GEN-002"]
