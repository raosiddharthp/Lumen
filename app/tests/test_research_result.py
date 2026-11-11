from dataclasses import fields

import pytest

from app.common.rating import Factors, rate
from app.common.research_result import FactorsIn, ResearchError, parse_result

KNOWN = {"RG-ONC-002", "RG-GEN-002", "PR-A-19902"}

GOOD = (
    '{"factors": {"condition": "breast_cancer_stage1", '
    '"years_since_treatment": 5.5, "sum_assured": 500000}, '
    '"citations": ["RG-ONC-002", "PR-A-19902"]}'
)


def code_of(text):
    with pytest.raises(ResearchError) as exc:
        parse_result(text, KNOWN)
    return exc.value.code


def test_valid_result_parses():
    r = parse_result(GOOD, KNOWN)
    f = r.to_factors()
    assert isinstance(f, Factors)
    assert f.condition == "breast_cancer_stage1"
    assert f.years_since_treatment == 5.5
    assert r.citations == ["RG-ONC-002", "PR-A-19902"]


def test_fenced_json_is_accepted():
    assert parse_result("```json\n" + GOOD + "\n```", KNOWN).citations


def test_unknown_citation_is_rejected():
    assert code_of(GOOD.replace("RG-ONC-002", "RG-ONC-999")) == "UNKNOWN_CITATION"


def test_extra_fields_are_rejected():
    inner = '{"factors": {"condition": "none", "confidence": 0.99}, "citations": []}'
    top = '{"factors": {"condition": "none"}, "citations": [], "confidence": 0.9}'
    assert code_of(inner) == "SCHEMA"
    assert code_of(top) == "SCHEMA"


def test_out_of_range_value_is_rejected():
    bad = '{"factors": {"condition": "diabetes_t2", "hba1c": 99}, "citations": []}'
    assert code_of(bad) == "SCHEMA"


def test_non_json_is_rejected():
    assert code_of("I think it is stage one") == "NOT_JSON"


def test_unknown_condition_passes_through_to_no_rating():
    ok = '{"factors": {"condition": "rare_autoimmune"}, "citations": ["RG-GEN-002"]}'
    r = parse_result(ok, KNOWN)
    assert rate(r.to_factors()).status == "no_rating"


def test_precedent_ids_are_split_out():
    assert parse_result(GOOD, KNOWN).precedent_ids == ["PR-A-19902"]


def test_duplicate_citations_are_removed():
    dup = GOOD.replace('["RG-ONC-002", "PR-A-19902"]', '["RG-ONC-002", "RG-ONC-002"]')
    assert parse_result(dup, KNOWN).citations == ["RG-ONC-002"]


def test_every_schema_field_exists_on_factors():
    assert set(FactorsIn.model_fields) <= {f.name for f in fields(Factors)}
