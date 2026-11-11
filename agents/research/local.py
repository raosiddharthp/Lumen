import asyncio
import sys

from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.research.agent import root_agent
from app.common import config, passages
from app.common.eventlog import record
from app.common.rating import rate
from app.common.research_result import ResearchError, parse_result

SAMPLE = (
    "Applicant: 44-year-old accountant requesting EUR 500,000 life cover. "
    "Medical history: breast cancer, stage I, treated with lumpectomy and "
    "radiotherapy; treatment completed in March 2020. Annual surveillance "
    "mammograms since then have all been clear and there has been no "
    "recurrence. Blood pressure 126/80, no medication. No other conditions."
)


async def run_research(case_id: str, notes: str):
    runner = InMemoryRunner(agent=root_agent, app_name="research")
    session = await runner.session_service.create_session(
        app_name="research", user_id=case_id
    )
    msg = types.Content(role="user", parts=[types.Part(text=notes)])
    text, tok_in, tok_out = "", 0, 0
    with record(case_id, "research", {"notes": notes}) as run:
        async for event in runner.run_async(
            user_id=case_id, session_id=session.id, new_message=msg
        ):
            usage = getattr(event, "usage_metadata", None)
            if usage:
                tok_in += usage.prompt_token_count or 0
                tok_out += usage.candidates_token_count or 0
            if event.is_final_response() and event.content:
                text = event.content.parts[0].text
        final = await runner.session_service.get_session(
            app_name="research", user_id=case_id, session_id=session.id
        )
        retrieved = final.state.get("retrieved", [])
        try:
            result = parse_result(text, passages.known_ids())
        except ResearchError as exc:
            run.finish({"raw": text, "error": exc.code}, status="error",
                       model=config.LLM_MODEL)
            raise
        run.finish(
            {"result": result.model_dump(exclude_none=True), "retrieved": retrieved,
             "tokens_in": tok_in, "tokens_out": tok_out},
            model=config.LLM_MODEL,
        )
    return result, retrieved, (tok_in, tok_out)


if __name__ == "__main__":
    notes = sys.argv[1] if len(sys.argv) > 1 else SAMPLE
    result, retrieved, tokens = asyncio.run(run_research("LOCAL-001", notes))
    rating = rate(result.to_factors())
    print("factors:", result.factors.model_dump(exclude_none=True))
    print("citations:", result.citations)
    print("cited but never retrieved:",
          [c for c in result.citations if c not in retrieved])
    print("rating:", rating.status, rating.loading_pct, rating.rule_ids)
    print("tokens in/out:", *tokens)
