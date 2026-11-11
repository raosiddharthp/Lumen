import asyncio

from google.adk.agents.remote_a2a_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    RemoteA2aAgent,
)
from google.adk.runners import InMemoryRunner
from google.genai import types

CARD = "http://localhost:8011" + AGENT_CARD_WELL_KNOWN_PATH
NOTES = (
    "Applicant: 44-year-old accountant requesting EUR 500,000 life cover. "
    "Breast cancer stage I, treatment completed March 2020, clear annual "
    "mammograms, no recurrence. No other conditions."
)


async def main():
    print("card url:", CARD)
    remote = RemoteA2aAgent(
        name="research_remote",
        agent_card=CARD,
        description="Research agent reached over A2A",
    )
    runner = InMemoryRunner(agent=remote, app_name="remote_smoke")
    session = await runner.session_service.create_session(
        app_name="remote_smoke", user_id="u1"
    )
    msg = types.Content(role="user", parts=[types.Part(text=NOTES)])
    events = 0
    async for event in runner.run_async(
        user_id="u1", session_id=session.id, new_message=msg
    ):
        events += 1
        if event.is_final_response() and event.content:
            print("final:", event.content.parts[0].text[:600])
    print("events:", events)


asyncio.run(main())
