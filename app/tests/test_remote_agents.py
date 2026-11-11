import asyncio
import json

import pytest

from agents.remote_agents import A2AAgents
from app.common.casestore import MemoryStore
from app.common.draft import DraftError
from app.common.eventlog import MemorySink, get_sink, set_sink
from app.common.grounding import Claim, GroundingError
from app.common.rating import Factors, rate
from app.common.research_result import ResearchError
from app.orchestrator import run_case


@pytest.fixture(autouse=True)
def memory_log():
    set_sink(MemorySink())
    yield
    set_sink(None)


IDS = {"RG-ONC-002", "PR-A-19902"}
PASSAGES = {
    "RG-ONC-002": {"text": "Stage I rule."},
    "PR-A-19902": {"text": "Precedent."},
}


class FakeTransport:
    def __init__(self, reply):
        self.reply = reply
        self.seen = []

    async def ask(self, user_id, text):
        self.seen.append(text)
        return self.reply(text) if callable(self.reply) else self.reply


RESEARCH_OK = json.dumps({
    "factors": {
        "condition": "breast_cancer_stage1",
        "years_since_treatment": 6.7,
        "recurrence": False,
        "surveillance_clear": True,
        "sum_assured": 500000,
    },
    "citations": ["RG-ONC-002", "PR-A-19902"],
})

DRAFT_OK = json.dumps([
    {"text": "Stage I breast cancer.", "cites": ["CASE"]},
    {"text": "Rated 0%.", "cites": ["RATING"]},
    {"text": "Guidance applies.", "cites": ["RG-ONC-002"]},
])


def all_supported(prompt):
    claims = json.loads(prompt)["claims"]
    return json.dumps([
        {"claim_id": c["claim_id"], "verdict": "supported", "reason": "ok"}
        for c in claims
    ])


def agents(research=RESEARCH_OK, gate=all_supported, draft=DRAFT_OK):
    return A2AAgents(
        FakeTransport(research),
        FakeTransport(gate),
        FakeTransport(draft),
        known_ids=lambda: IDS,
        lookup=PASSAGES.get,
    )


def test_research_reply_is_parsed_and_logged():
    result, tokens = asyncio.run(agents().research("T-1", "notes"))
    assert result.factors.condition == "breast_cancer_stage1"
    assert tokens == (0, 0)
    event = get_sink().events[-1]
    assert event["agent"] == "research" and event["inputs"]["transport"] == "a2a"


def test_malformed_research_reply_is_refused_and_logged_as_an_error():
    with pytest.raises(ResearchError):
        asyncio.run(agents(research="not json").research("T-1", "notes"))
    assert get_sink().events[-1]["status"] == "error"


def test_research_citation_outside_the_corpus_is_refused():
    bad = RESEARCH_OK.replace("PR-A-19902", "PR-NOPE")
    with pytest.raises(ResearchError) as exc:
        asyncio.run(agents(research=bad).research("T-1", "notes"))
    assert exc.value.code == "UNKNOWN_CITATION"


def test_gate_reply_becomes_a_decision():
    claims = [Claim("c1", "Stage I rule applies.", ("RG-ONC-002",))]
    decision, verdicts, _ = asyncio.run(agents().gate("T-1", claims, "draft", None))
    assert decision == "passed" and verdicts[0].verdict == "supported"


def test_gate_hard_stops_on_a_contradiction_and_refuses_malformed_replies():
    claims = [Claim("c1", "x", ("RG-ONC-002",))]

    def contradicted(prompt):
        return json.dumps([{"claim_id": "c1", "verdict": "contradicted", "reason": "no"}])

    decision, _, _ = asyncio.run(agents(gate=contradicted).gate("T-1", claims, "draft", None))
    assert decision == "hard_stop"
    with pytest.raises(GroundingError):
        asyncio.run(agents(gate="nonsense").gate("T-1", claims, "draft", None))


def test_gate_prompt_carries_the_passage_text():
    a = agents()
    claims = [Claim("c1", "x", ("RG-ONC-002",))]
    asyncio.run(a.gate("T-1", claims, "draft", None))
    assert "Stage I rule." in a._gate.seen[0]


def test_draft_reply_becomes_tagged_claims_and_untagged_replies_are_refused():
    rating = rate(Factors(condition="breast_cancer_stage1", years_since_treatment=6.7,
                          recurrence=False, surveillance_clear=True))
    claims, _ = asyncio.run(agents().draft("T-1", "notes", rating, ["RG-ONC-002"]))
    assert [c.claim_id for c in claims] == ["s1", "s2", "s3"]
    untagged = json.dumps([{"text": "No source.", "cites": []}])
    with pytest.raises(DraftError):
        asyncio.run(agents(draft=untagged).draft("T-1", "notes", rating, ["RG-ONC-002"]))


def test_a_full_case_runs_through_the_orchestrator_over_the_a2a_adapter():
    store = MemoryStore()
    doc = asyncio.run(run_case("T-1", "notes", agents(), store, lookup=PASSAGES.get))
    assert doc["grounding"] == "passed" and doc["referral"]["tier"] == 1
    assert doc["evidence"]["verified"] == ["RG-ONC-002", "PR-A-19902"]
    assert len(doc["draft"]) == 3
