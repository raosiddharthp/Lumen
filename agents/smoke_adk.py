import asyncio

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.common import config
from app.common.llm import configure_vertex

configure_vertex()


async def main():
    agent = Agent(
        name="smoke",
        model=config.LLM_MODEL,
        instruction="Reply with the single word: pong",
    )
    runner = InMemoryRunner(agent=agent, app_name="smoke")
    session = await runner.session_service.create_session(
        app_name="smoke", user_id="u1"
    )
    msg = types.Content(role="user", parts=[types.Part(text="ping")])
    async for event in runner.run_async(
        user_id="u1", session_id=session.id, new_message=msg
    ):
        if event.is_final_response() and event.content:
            print("reply:", event.content.parts[0].text.strip())
            usage = getattr(event, "usage_metadata", None)
            if usage:
                print("tokens in/out:", usage.prompt_token_count,
                      usage.candidates_token_count)


asyncio.run(main())
