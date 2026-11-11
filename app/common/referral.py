from dataclasses import dataclass

from .rating import Factors, Rating

POLICY_VERSION = "p1.0"
SUM_ASSURED_LIMIT = 750_000

MANDATORY_REFERRAL_RULES = {
    "ONC-RECUR": "RG-ONC-004",
    "ONC-S2-REFER": "RG-ONC-003",
    "ONC-S2-7Y": "RG-ONC-003",
    "ONC-S2-10Y": "RG-ONC-003",
    "HTN-3": "RG-CAR-001",
    "MI-NODATE": "RG-CAR-002",
    "MI-POSTPONE": "RG-CAR-002",
    "MI-1Y": "RG-CAR-002",
    "MI-3Y": "RG-CAR-002",
    "MI-STRESS": "RG-CAR-002",
    "DIA-COMP": "RG-DIA-002",
    "DIA-DECLINE": "RG-DIA-002",
}

TIER_SIGNERS = {
    1: ("senior_underwriter",),
    2: ("senior_underwriter", "cosigner_cmo_or_cuo"),
}


@dataclass(frozen=True)
class Referral:
    tier: int
    signers: tuple[str, ...]
    reasons: tuple[str, ...]
    guidance_refs: tuple[str, ...]
    policy_version: str = POLICY_VERSION

    @property
    def requires_human_signoff(self) -> bool:
        return True


def refer(
    factors: Factors,
    rating: Rating,
    grounding: str,
    precedent_ids: list[str],
) -> Referral:
    reasons: list[str] = []
    refs: list[str] = []

    if grounding != "passed":
        reasons.append("POL-03")
        refs.append("RG-GEN-001")

    if factors.sum_assured > SUM_ASSURED_LIMIT:
        reasons.append("POL-01")
        refs.append("RG-GEN-001")

    if rating.status == "decline":
        reasons.append("POL-02")
        refs.append("RG-GEN-001")

    if rating.status == "no_rating":
        reasons.append("POL-05")
        refs.append("RG-GEN-002")

    for rule_id in rating.rule_ids:
        if rule_id in MANDATORY_REFERRAL_RULES:
            reasons.append(f"POL-04:{rule_id}")
            refs.append(MANDATORY_REFERRAL_RULES[rule_id])

    if rating.status == "rated" and factors.condition != "none" and not precedent_ids:
        reasons.append("POL-06")

    tier = 2 if reasons else 1
    return Referral(
        tier=tier,
        signers=TIER_SIGNERS[tier],
        reasons=tuple(reasons),
        guidance_refs=tuple(dict.fromkeys(refs)),
    )
