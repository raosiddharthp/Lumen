import asyncio

from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.gate.agent import root_agent
from app.common import config, passages
from app.common.eventlog import record
from app.common.grounding import (
    Claim,
    GroundingError,
    applicability_claims,
    build_gate_prompt,
    decide,
    parse_verdicts,
    supported_citations,
)


async def run_gate(case_id: str, claims: list[Claim], stage: str):
    runner = InMemoryRunner(agent=root_agent, app_name="gate")
    session = await runner.session_service.create_session(
        app_name="gate", user_id=case_id
    )
    text, tok_in, tok_out = "", 0, 0
    with record(case_id, "grounding_gate", {"stage": stage, "claims": claims}) as run:
        prompt = build_gate_prompt(claims, passages.get_passage)
        msg = types.Content(role="user", parts=[types.Part(text=prompt)])
        async for event in runner.run_async(
            user_id=case_id, session_id=session.id, new_message=msg
        ):
            usage = getattr(event, "usage_metadata", None)
            if usage:
                tok_in += usage.prompt_token_count or 0
                tok_out += usage.candidates_token_count or 0
            if event.is_final_response() and event.content:
                text = event.content.parts[0].text
        try:
            verdicts = parse_verdicts(text, claims)
        except GroundingError as exc:
            run.finish({"raw": text, "error": exc.code, "decision": "hard_stop"},
                       status="error", model=config.GATE_MODEL)
            raise
        decision = decide(claims, verdicts)
        run.finish({"decision": decision, "verdicts": verdicts,
                    "tokens_in": tok_in, "tokens_out": tok_out},
                   model=config.GATE_MODEL)
    return decision, verdicts, (tok_in, tok_out)


FACTORS = {
    "condition": "breast_cancer_stage1",
    "years_since_treatment": 6.7,
    "recurrence": False,
    "surveillance_clear": True,
    "sum_assured": 500000.0,
}
CITED = ["RG-ONC-002", "RG-ONC-003", "RG-ONC-001",
         "PR-A-19902", "PR-A-17540", "PR-A-20118"]

D1 = Claim("d1", "Stage I breast cancer with 5 or more years since treatment "
           "and no recurrence carries no loading.", ("RG-ONC-002",))
D2 = Claim("d2", "Stage I breast cancer at 6 years since treatment carries a "
           "50% loading.", ("RG-ONC-002",))
D3 = Claim("d3", "The applicant's latest mammogram shows a 2 cm lesion.",
           ("RG-ONC-002",))
D4 = Claim("d4", "A similar case was accepted at standard terms.", ())


def show(title, claims, decision, verdicts, tokens):
    print(f"\n{title}: {decision}  (tokens in/out {tokens[0]}/{tokens[1]})")
    for claim, verdict in zip(claims, verdicts):
        print(f"  {claim.claim_id:<22} {verdict.verdict:<12} {verdict.reason}")


async def main():
    app_claims = applicability_claims(FACTORS, CITED)
    d, v, t = await run_gate("DEMO-GATE", app_claims, "applicability")
    show("1 applicability of the six cited passages", app_claims, d, v, t)
    print("  kept:", supported_citations(app_claims, v))
    bad = [D1, D2, D3, D4]
    d, v, t = await run_gate("DEMO-GATE", bad, "draft")
    show("2 adversarial draft", bad, d, v, t)
    d, v, t = await run_gate("DEMO-GATE", [D1], "draft")
    show("3 clean draft", [D1], d, v, t)


if __name__ == "__main__":
    asyncio.run(main())
