import asyncio

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from app.common import config
from app.common.llm import configure_vertex

configure_vertex()


def lookup(topic: str, tool_context: ToolContext) -> dict:
    """Look up the code word for a topic."""
    seen = tool_context.state.get("seen", [])
    tool_context.state["seen"] = seen + [topic]
    return {"fact": f"The code word for {topic} is KESTREL."}


async def main():
    agent = Agent(
        name="smoke_tools",
        model=config.LLM_MODEL,
        instruction=("Call the lookup tool once for the topic the user names, "
                     "then reply with the code word only."),
        tools=[lookup],
    )
    runner = InMemoryRunner(agent=agent, app_name="smoke_tools")
    session = await runner.session_service.create_session(
        app_name="smoke_tools", user_id="u1"
    )
    msg = types.Content(role="user", parts=[types.Part(text="topic: harbour")])
    calls, tok_in, tok_out = 0, 0, 0
    async for event in runner.run_async(
        user_id="u1", session_id=session.id, new_message=msg
    ):
        calls += len(event.get_function_calls())
        usage = getattr(event, "usage_metadata", None)
        if usage:
            tok_in += usage.prompt_token_count or 0
            tok_out += usage.candidates_token_count or 0
        if event.is_final_response() and event.content:
            print("reply:", event.content.parts[0].text.strip())
    final = await runner.session_service.get_session(
        app_name="smoke_tools", user_id="u1", session_id=session.id
    )
    print("tool calls:", calls)
    print("state seen:", final.state.get("seen"))
    print("tokens in/out:", tok_in, tok_out)


asyncio.run(main())
