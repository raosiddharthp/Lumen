import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.drafting.agent import root_agent
from agents.gate.local import run_gate
from agents.research.local import SAMPLE
from app.common import config, passages
from app.common.draft import (
    DraftError,
    allowed_ids_for,
    build_draft_prompt,
    make_lookup,
    parse_draft,
)
from app.common.eventlog import record
from app.common.grounding import Claim
from app.common.rating import Factors, rate


async def run_draft(case_id: str, case_notes: str, rating, evidence_ids: list[str]):
    runner = InMemoryRunner(agent=root_agent, app_name="drafting")
    session = await runner.session_service.create_session(
        app_name="drafting", user_id=case_id
    )
    text, tok_in, tok_out = "", 0, 0
    inputs = {"evidence_ids": evidence_ids, "rating": rating}
    with record(case_id, "drafting", inputs) as run:
        prompt = build_draft_prompt(case_notes, rating, evidence_ids, passages.get_passage)
        msg = types.Content(role="user", parts=[types.Part(text=prompt)])
        async for event in runner.run_async(
            user_id=case_id, session_id=session.id, new_message=msg
        ):
            usage = getattr(event, "usage_metadata", None)
            if usage:
                tok_in += usage.prompt_token_count or 0
                tok_out += (usage.candidates_token_count or 0) + (getattr(usage, "thoughts_token_count", 0) or 0)
            if event.is_final_response() and event.content:
                text = event.content.parts[0].text
        try:
            claims = parse_draft(text, allowed_ids_for(evidence_ids))
        except DraftError as exc:
            run.finish({"raw": text, "error": exc.code}, status="error",
                       model=config.LLM_MODEL)
            raise
        run.finish({"claims": claims, "tokens_in": tok_in, "tokens_out": tok_out},
                   model=config.LLM_MODEL)
    return claims, (tok_in, tok_out)


FACTORS = Factors(
    condition="breast_cancer_stage1",
    years_since_treatment=6.7,
    recurrence=False,
    surveillance_clear=True,
    systolic=126,
    diastolic=80,
    medications=0,
    sum_assured=500000.0,
)
EVIDENCE = ["RG-ONC-002", "RG-ONC-001", "PR-A-19902"]
TAMPERED = [
    Claim("t1", "The rating engine assigns a loading of 50%.", ("RATING",)),
    Claim("t2", "The applicant has had a cancer recurrence.", ("CASE",)),
]


def show(title, claims, decision, verdicts, tokens):
    print(f"\n{title}: {decision}  (tokens in/out {tokens[0]}/{tokens[1]})")
    for claim, verdict in zip(claims, verdicts):
        print(f"  {claim.claim_id:<4} {verdict.verdict:<12} {verdict.reason}")


async def main():
    rating = rate(FACTORS)
    claims, tokens = await run_draft("DEMO-DRAFT", SAMPLE, rating, EVIDENCE)
    print(f"\nDraft: {len(claims)} sentences (tokens in/out {tokens[0]}/{tokens[1]})")
    for claim in claims:
        print(f"  {claim.claim_id:<4} [{', '.join(claim.cites)}] {claim.text}")
    lookup = make_lookup(passages.get_passage, SAMPLE, rating)
    d, v, t = await run_gate("DEMO-DRAFT", claims, "draft", lookup)
    show("Gate on the draft", claims, d, v, t)
    d, v, t = await run_gate("DEMO-DRAFT", TAMPERED, "draft", lookup)
    show("Gate on tampered claims", TAMPERED, d, v, t)


if __name__ == "__main__":
    asyncio.run(main())
