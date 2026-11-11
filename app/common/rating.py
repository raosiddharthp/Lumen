from dataclasses import dataclass, field

METHODOLOGY_VERSION = "v4.2"

OCCUPATION = {
    "standard": (0, None),
    "offshore": (25, "OCC-OFFSHORE"),
    "work_at_height": (25, "OCC-HEIGHT"),
    "mining": (50, "OCC-MINING"),
}


@dataclass
class Factors:
    condition: str
    years_since_treatment: float | None = None
    recurrence: bool = False
    surveillance_clear: bool = True
    systolic: int | None = None
    diastolic: int | None = None
    medications: int = 0
    stress_test_normal: bool = False
    hba1c: float | None = None
    complications: int = 0
    occupation: str = "standard"
    sum_assured: int = 0


@dataclass
class Rating:
    status: str
    loading_pct: int | None
    rule_ids: list[str]
    guidance_refs: list[str]
    methodology_version: str = METHODOLOGY_VERSION
    notes: list[str] = field(default_factory=list)


def _no_rating(rule: str, ref: str, note: str):
    return ("no_rating", None, rule, ref, note)


def _breast_stage1(f: Factors):
    y = f.years_since_treatment
    if f.recurrence:
        return _no_rating("ONC-RECUR", "RG-ONC-004", "recurrence: refer or decline")
    if y is None:
        return _no_rating("ONC-NODATE", "RG-ONC-004", "completion date missing")
    if y < 2:
        return ("postpone", None, "ONC-S1-POSTPONE", "RG-ONC-002", "under 2 years")
    if y < 3:
        return ("rated", 100, "ONC-S1-2Y", "RG-ONC-002", "")
    if y < 5:
        return ("rated", 50, "ONC-S1-3Y", "RG-ONC-002", "")
    if not f.surveillance_clear:
        return _no_rating("ONC-S1-SURV", "RG-ONC-004", "surveillance not clear")
    return ("rated", 0, "ONC-S1-5Y", "RG-ONC-002", "")


def _breast_stage2plus(f: Factors):
    y = f.years_since_treatment
    if f.recurrence or y is None or y < 7 or not f.surveillance_clear:
        return _no_rating("ONC-S2-REFER", "RG-ONC-003", "outside pre-validated bands")
    if y < 10:
        return ("rated", 50, "ONC-S2-7Y", "RG-ONC-003", "medical officer review")
    return ("rated", 25, "ONC-S2-10Y", "RG-ONC-003", "medical officer review")


def _hypertension(f: Factors):
    if f.systolic is None or f.diastolic is None:
        return _no_rating("HTN-NODATA", "RG-CAR-001", "readings missing")
    if f.medications > 2:
        return _no_rating("HTN-MEDS", "RG-CAR-001", "more than two medications")
    if f.systolic >= 160 or f.diastolic >= 100:
        return ("rated", 50, "HTN-3", "RG-CAR-001", "medical officer review")
    if f.systolic >= 140 or f.diastolic >= 90:
        return ("rated", 25, "HTN-2", "RG-CAR-001", "")
    return ("rated", 0, "HTN-1", "RG-CAR-001", "")


def _myocardial_infarction(f: Factors):
    y = f.years_since_treatment
    if y is None:
        return _no_rating("MI-NODATE", "RG-CAR-002", "event date missing")
    if y < 1:
        return ("postpone", None, "MI-POSTPONE", "RG-CAR-002", "under 12 months")
    if y < 3:
        return ("rated", 100, "MI-1Y", "RG-CAR-002", "medical officer review")
    if f.stress_test_normal:
        return ("rated", 50, "MI-3Y", "RG-CAR-002", "medical officer review")
    return _no_rating("MI-STRESS", "RG-CAR-002", "no normal recent stress test")


def _diabetes(f: Factors):
    if f.complications > 1:
        return ("decline", None, "DIA-DECLINE", "RG-DIA-002", "multiple complications")
    if f.hba1c is None:
        return _no_rating("DIA-NODATA", "RG-DIA-001", "HbA1c missing")
    if f.complications == 1 or f.hba1c > 8.5:
        return ("rated", 100, "DIA-COMP", "RG-DIA-002", "medical officer review")
    if f.hba1c <= 7.0:
        return ("rated", 25, "DIA-1", "RG-DIA-001", "")
    return ("rated", 50, "DIA-2", "RG-DIA-001", "")


def _no_medical(f: Factors):
    return ("rated", 0, "NO-MEDICAL", None, "")


RULES = {
    "breast_cancer_stage1": _breast_stage1,
    "breast_cancer_stage2plus": _breast_stage2plus,
    "hypertension": _hypertension,
    "myocardial_infarction": _myocardial_infarction,
    "diabetes_t2": _diabetes,
    "none": _no_medical,
}


def rate(f: Factors) -> Rating:
    rule_fn = RULES.get(f.condition)
    if rule_fn is None:
        status, loading, rule, ref, note = _no_rating(
            "NO-RULE", "RG-GEN-002", "no guidance for this condition"
        )
    else:
        status, loading, rule, ref, note = rule_fn(f)

    rules = [rule]
    refs = [ref] if ref else []
    notes = [note] if note else []

    if status == "rated":
        if f.occupation not in OCCUPATION:
            return Rating("no_rating", None, ["OCC-UNKNOWN"], ["RG-OCC-001"],
                          notes=["unknown occupation"])
        extra, occ_rule = OCCUPATION[f.occupation]
        if occ_rule:
            loading += extra
            rules.append(occ_rule)
            refs.append("RG-OCC-001")

    return Rating(status, loading, rules, refs, notes=notes)
