import asyncio

import pytest

from app.common.casestore import MemoryStore
from app.common.eventlog import MemorySink, get_sink, set_sink
from app.common.grounding import Claim, Verdict
from app.common.research_result import FactorsIn, ResearchError, ResearchResult
from app.orchestrator import run_case


@pytest.fixture(autouse=True)
def memory_log():
    set_sink(MemorySink())
    yield
    set_sink(None)


def lookup(cid):
    return {"text": "passage"}


GOOD = ResearchResult(
    factors=FactorsIn(
        condition="breast_cancer_stage1",
        years_since_treatment=6.7,
        recurrence=False,
        surveillance_clear=True,
        sum_assured=500000,
    ),
    citations=["RG-ONC-002", "RG-ONC-003", "PR-A-19902"],
)
KEEP = ["RG-ONC-002", "PR-A-19902"]


class StubAgents:
    def __init__(self, research=(GOOD,), keep=KEEP, draft_outcomes=("passed",)):
        self.research_script = list(research)
        self.keep = set(keep)
        self.draft_outcomes = list(draft_outcomes)
        self.evidence_seen = None
        self.calls = {"research": 0, "applicability": 0, "draft": 0, "draft_gate": 0}

    async def research(self, case_id, notes):
        self.calls["research"] += 1
        index = min(self.calls["research"], len(self.research_script)) - 1
        item = self.research_script[index]
        if isinstance(item, Exception):
            raise item
        return item, (10, 5)

    async def draft(self, case_id, notes, rating, evidence_ids):
        self.calls["draft"] += 1
        self.evidence_seen = list(evidence_ids)
        return [Claim("s1", "Stage I breast cancer.", ("CASE",))], (10, 5)

    async def gate(self, case_id, claims, stage, lookup):
        if stage == "applicability":
            self.calls["applicability"] += 1
            verdicts = [
                Verdict(c.claim_id,
                        "supported" if c.cites[0] in self.keep else "unsupported",
                        "r")
                for c in claims
            ]
            return "hard_stop", verdicts, (10, 5)
        self.calls["draft_gate"] += 1
        index = min(self.calls["draft_gate"], len(self.draft_outcomes)) - 1
        outcome = self.draft_outcomes[index]
        verdict = "supported" if outcome == "passed" else "contradicted"
        return outcome, [Verdict(c.claim_id, verdict, "r") for c in claims], (10, 5)


def go(agents, notes="Notes."):
    store = MemoryStore()
    doc = asyncio.run(run_case("T-1", notes, agents, store, lookup=lookup))
    assert store.get("T-1") is doc
    return doc


def test_happy_path_is_tier_1_and_fully_grounded():
    doc = go(StubAgents())
    assert doc["status"] == "awaiting_signoff"
    assert doc["grounding"] == "passed"
    assert doc["referral"]["tier"] == 1 and doc["referral"]["reasons"] == []
    assert doc["rating"]["loading_pct"] == 0
    assert [s["verdict"] for s in doc["draft"]] == ["supported"]


def test_evidence_is_filtered_and_drafting_sees_only_verified_ids():
    agents = StubAgents()
    doc = go(agents)
    assert doc["evidence"] == {"verified": KEEP, "dropped": ["RG-ONC-003"]}
    assert agents.evidence_seen == KEEP


def test_no_verified_precedent_sends_the_case_to_tier_2():
    doc = go(StubAgents(keep=["RG-ONC-002"]))
    assert doc["referral"]["tier"] == 2
    assert "POL-06" in doc["referral"]["reasons"]


def test_research_is_retried_twice_then_succeeds():
    agents = StubAgents(
        research=[ResearchError("SCHEMA"), ResearchError("SCHEMA"), GOOD]
    )
    doc = go(agents)
    assert agents.calls["research"] == 3
    assert doc["stages"]["research"] == {"attempts": 3, "failure": None}
    assert doc["referral"]["tier"] == 1


def test_research_failing_three_times_still_produces_a_tier_2_case():
    agents = StubAgents(research=[ResearchError("SCHEMA")])
    doc = go(agents)
    assert agents.calls["research"] == 3
    assert doc["factors"] == {} and doc["draft"] is None
    assert doc["grounding"] == "hard_stop"
    assert {"POL-03", "POL-05"} <= set(doc["referral"]["reasons"])
    assert "ResearchError:SCHEMA" in doc["stages"]["research"]["failure"]


def test_draft_gate_rejecting_twice_then_passing_is_accepted():
    agents = StubAgents(draft_outcomes=["hard_stop", "hard_stop", "passed"])
    doc = go(agents)
    assert agents.calls["draft"] == 3
    assert doc["stages"]["draft"]["attempts"] == 3
    assert doc["grounding"] == "passed" and doc["draft"] is not None


def test_draft_gate_rejecting_every_attempt_hard_stops_and_keeps_the_draft():
    agents = StubAgents(draft_outcomes=["hard_stop"])
    doc = go(agents)
    assert agents.calls["draft"] == 3
    assert doc["draft"] is None
    assert doc["rejected_draft"][0]["verdict"] == "contradicted"
    assert doc["grounding"] == "hard_stop"
    assert doc["referral"]["tier"] == 2
    assert "POL-03" in doc["referral"]["reasons"]


def test_infrastructure_errors_are_not_retried():
    agents = StubAgents(research=[RuntimeError("model unavailable")])
    doc = go(agents)
    assert agents.calls["research"] == 1
    assert doc["stages"]["research"]["failure"] == "agent_error:RuntimeError"
    assert doc["referral"]["tier"] == 2


def test_no_citations_skips_the_applicability_gate():
    bare = ResearchResult(
        factors=FactorsIn(
            condition="breast_cancer_stage1",
            years_since_treatment=6.7,
            recurrence=False,
            surveillance_clear=True,
        ),
        citations=[],
    )
    agents = StubAgents(research=[bare])
    doc = go(agents)
    assert agents.calls["applicability"] == 0
    assert doc["evidence"]["verified"] == []
    assert "POL-06" in doc["referral"]["reasons"]


def test_tokens_are_summed_across_stages():
    doc = go(StubAgents())
    assert doc["tokens"] == {"in": 40, "out": 20}


def test_signoff_is_always_required_in_the_record():
    assert go(StubAgents())["referral"]["requires_human_signoff"] is True
    failed = go(StubAgents(research=[ResearchError("SCHEMA")]))
    assert failed["referral"]["requires_human_signoff"] is True


def test_the_run_is_logged_once_by_the_orchestrator():
    doc = go(StubAgents())
    events = get_sink().events
    assert [e["agent"] for e in events] == ["orchestrator"]
    assert events[0]["outputs"]["tier"] == doc["referral"]["tier"]
