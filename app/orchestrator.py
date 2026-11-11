import json
from dataclasses import asdict
from datetime import datetime, timezone

from .common.draft import DraftError, make_lookup
from .common.eventlog import record
from .common.grounding import GroundingError, applicability_claims, supported_citations
from .common.rating import Factors, rate
from .common.referral import refer
from .common.research_result import ResearchError

MAX_ATTEMPTS = 3


class NotGrounded(Exception):
    code = "gate_rejected"


def _plain(obj):
    return json.loads(json.dumps(asdict(obj), default=str))


async def _stage(call, errors):
    reason = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return attempt, await call(), None
        except errors as exc:
            reason = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
        except Exception as exc:
            return attempt, None, f"agent_error:{type(exc).__name__}"
    return MAX_ATTEMPTS, None, f"{reason} after {MAX_ATTEMPTS} attempts"


async def run_case(case_id, notes, agents, store, lookup=None):
    if lookup is None:
        from .common import passages

        lookup = passages.get_passage

    tokens = {"in": 0, "out": 0}
    stages = {}

    def add(t):
        tokens["in"] += t[0]
        tokens["out"] += t[1]

    with record(case_id, "orchestrator", {"notes_chars": len(notes)}) as run:
        grounding_ok = True
        research_ok = False
        factors = Factors(condition="unextracted")
        factor_dict, citations = {}, []

        attempts, out, why = await _stage(
            lambda: agents.research(case_id, notes), (ResearchError,)
        )
        stages["research"] = {"attempts": attempts, "failure": why}
        if out is not None:
            result, t = out
            add(t)
            factors = result.to_factors()
            factor_dict = result.factors.model_dump(exclude_none=True)
            citations = result.citations
            research_ok = True
        else:
            grounding_ok = False

        verified = []
        if citations:
            claims = applicability_claims(factor_dict, citations)
            attempts, out, why = await _stage(
                lambda: agents.gate(case_id, claims, "applicability", None),
                (GroundingError,),
            )
            stages["applicability"] = {"attempts": attempts, "failure": why}
            if out is None:
                grounding_ok = False
            else:
                _decision, verdicts, t = out
                add(t)
                verified = supported_citations(claims, verdicts)

        rating = rate(factors)

        draft_doc, rejected = None, None
        if research_ok:
            draft_lookup = make_lookup(lookup, notes, rating)
            last = {}

            async def draft_and_check():
                drafted, t1 = await agents.draft(case_id, notes, rating, verified)
                decision, verdicts, t2 = await agents.gate(
                    case_id, drafted, "draft", draft_lookup
                )
                add(t1)
                add(t2)
                merged = [
                    {"id": c.claim_id, "text": c.text, "cites": list(c.cites),
                     "verdict": v.verdict, "reason": v.reason}
                    for c, v in zip(drafted, verdicts)
                ]
                if decision != "passed":
                    last["rejected"] = merged
                    raise NotGrounded()
                return merged

            attempts, out, why = await _stage(
                draft_and_check, (DraftError, GroundingError, NotGrounded)
            )
            stages["draft"] = {"attempts": attempts, "failure": why}
            if out is None:
                grounding_ok = False
                rejected = last.get("rejected")
            else:
                draft_doc = out

        precedent_ids = [c for c in verified if c.startswith("PR-")]
        grounding = "passed" if grounding_ok else "hard_stop"
        referral = refer(factors, rating, grounding, precedent_ids)

        doc = {
            "case_id": case_id,
            "status": "awaiting_signoff",
            "created_at": datetime.now(timezone.utc),
            "notes": notes,
            "factors": factor_dict,
            "rating": _plain(rating),
            "evidence": {
                "verified": verified,
                "dropped": [c for c in citations if c not in verified],
            },
            "draft": draft_doc,
            "rejected_draft": rejected,
            "grounding": grounding,
            "referral": {
                **_plain(referral),
                "requires_human_signoff": referral.requires_human_signoff,
            },
            "stages": stages,
            "tokens": tokens,
            "versions": {
                "methodology": rating.methodology_version,
                "policy": referral.policy_version,
            },
        }
        store.save(doc)
        run.finish({
            "tier": referral.tier,
            "grounding": grounding,
            "reasons": list(referral.reasons),
            "stages": stages,
            "tokens": tokens,
        })
    return doc
